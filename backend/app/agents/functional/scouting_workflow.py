"""
Scouting Report workflow entrypoint for LangGraph Functional API.

Implements the 9-node scouting flow with 2 HITL gates:
- Gate A: Plan Approval (after Node 2)
- Gate B: Player Approval (after Node 7)

Supports edit loops:
- edit_wording: Re-run compose_report only
- edit_content: Re-run from build_queries with updated hints
"""

from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
from queue import Full as QueueFull
from langgraph.func import entrypoint
from langgraph.types import interrupt, Command
from langchain_core.runnables import RunnableConfig

from app.agents.functional.models import AgentResponse
from app.agents.functional.scouting.schemas import (
    IntakeResult,
    PlanProposal,
    EvidencePack,
    PlayerFields,
    Coverage,
    ScoutingReportDraft,
    DbPayloadPreview,
    CreatePlayerWithReportResponse,
)
from app.agents.functional.tasks.scouting import (
    intake_and_route_scouting,
    draft_plan,
    build_queries,
    retrieve_evidence,
    extract_fields,
    compose_report,
    prepare_preview,
    write_player_item,
    build_final_response,
)
from app.agents.functional.workflow import (
    get_sync_checkpointer,
    get_event_queue_from_config,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# Maximum edit iterations to prevent infinite loops
MAX_EDIT_ITERATIONS = 5


def emit_scouting_event(
    config: Optional[RunnableConfig],
    event_type: str,
    data: Dict[str, Any],
) -> None:
    """Emit a scouting-specific event to the streaming queue if available."""
    if not config:
        return

    event_queue = get_event_queue_from_config(config)
    if not event_queue:
        return

    try:
        event_queue.put_nowait({"type": event_type, "data": data})
    except QueueFull:
        logger.debug(f"[SCOUTING] Event queue full, dropping {event_type} event")
    except Exception as e:
        logger.debug(
            f"[SCOUTING] Failed to emit {event_type} event: {e}", exc_info=True
        )


@dataclass
class ScoutingState:
    """Internal state for scouting workflow."""

    # Request info
    user_id: int = 0
    session_id: int = 0
    message: str = ""
    api_key: str = ""
    run_id: Optional[str] = None

    # Node 1 output
    player_name: str = ""
    sport_guess: str = "unknown"

    # Node 2 output
    plan_steps: List[str] = field(default_factory=list)
    query_hints: List[str] = field(default_factory=list)

    # Node 3 output
    queries: List[str] = field(default_factory=list)

    # Node 4 output
    evidence_pack: Optional[EvidencePack] = None

    # Node 5 output
    player_fields: Optional[PlayerFields] = None
    raw_facts: List[str] = field(default_factory=list)
    coverage: Optional[Coverage] = None

    # Node 6 output
    report_draft: Optional[ScoutingReportDraft] = None

    # Node 7 output
    preview: Optional[DbPayloadPreview] = None

    # Node 8 output
    player_record_id: Optional[str] = None
    report_id: Optional[str] = None
    saved: bool = False

    # Edit tracking
    edit_iterations: int = 0


def check_user_has_documents(user_id: int) -> bool:
    """
    Check if user has any indexed documents for RAG.

    Args:
        user_id: User ID

    Returns:
        True if user has at least one READY document
    """
    try:
        from app.db.models.document import Document

        return Document.objects.filter(
            owner_id=user_id, status=Document.Status.READY
        ).exists()
    except Exception as e:
        logger.warning(f"Error checking user documents: {e}")
        return False


def request_plan_approval(
    player_name: str,
    sport_guess: str,
    plan_steps: List[str],
    query_hints: List[str],
    session_id: int,
) -> Dict[str, Any]:
    """
    Request plan approval via HITL Gate A.

    Uses LangGraph's interrupt() to pause execution and wait for user decision.

    Args:
        player_name: Target player name
        sport_guess: Guessed sport
        plan_steps: Proposed plan steps
        query_hints: Proposed query hints
        session_id: Session ID for correlation

    Returns:
        Decision dict with approved/edited plan
    """
    logger.info(
        f"[SCOUTING] [HITL-A] Requesting plan approval for {player_name}, "
        f"session={session_id}"
    )

    decision = interrupt(
        {
            "type": "plan_approval",
            "session_id": session_id,
            "player_name": player_name,
            "sport_guess": sport_guess,
            "plan_steps": plan_steps,
            "query_hints": query_hints,
        }
    )

    logger.info(
        f"[SCOUTING] [HITL-A] Plan approval decision received, "
        f"edited={decision.get('edited', False)}"
    )

    return decision or {"approved": True}


def request_player_approval(
    preview: DbPayloadPreview,
    report_summary: List[str],
    report_text: str,
    session_id: int,
) -> Dict[str, Any]:
    """
    Request player item approval via HITL Gate B.

    Uses LangGraph's interrupt() to pause execution and wait for user decision.

    Args:
        preview: Database payload preview
        report_summary: Report summary bullets
        report_text: Full report text
        session_id: Session ID for correlation

    Returns:
        Decision dict with action (approve/reject/edit_wording/edit_content)
    """
    logger.info(
        f"[SCOUTING] [HITL-B] Requesting player approval for "
        f"{preview.player.display_name}, session={session_id}"
    )

    # Convert to dict for interrupt payload
    player_dict = preview.player.model_dump(exclude_none=True)

    decision = interrupt(
        {
            "type": "player_approval",
            "session_id": session_id,
            "player_fields": player_dict,
            "report_summary": report_summary,
            "report_text": report_text,
        }
    )

    action = decision.get("action", "approve") if decision else "approve"
    logger.info(f"[SCOUTING] [HITL-B] Player approval decision: action={action}")

    return decision or {"action": "approve"}


# Get checkpointer for scouting workflow
_scouting_checkpointer = None
try:
    _scouting_checkpointer = get_sync_checkpointer()
except Exception as e:
    logger.debug(f"Scouting checkpointer creation deferred: {e}")


@entrypoint(checkpointer=_scouting_checkpointer)
def scouting_workflow(
    request: Union[Dict[str, Any], Command],
    config: Optional[RunnableConfig] = None,
) -> AgentResponse:
    """
    Main entrypoint for scouting report workflow.

    Implements the 9-node flow with 2 HITL gates and edit loops.

    Request dict should contain:
        - message: User's scouting request
        - user_id: User ID
        - session_id: Session ID
        - api_key: OpenAI API key
        - run_id: Optional run correlation ID

    When resuming from interrupt, LangGraph handles Command internally.

    Args:
        request: Request dict or Command for resume

    Returns:
        AgentResponse with scouting report
    """
    # Handle Command for resume (LangGraph handles checkpoint restore)
    if isinstance(request, Command):
        logger.info("[SCOUTING] Resuming from interrupt")
        resume_payload = (
            request.resume
            if hasattr(request, "resume") and isinstance(request.resume, dict)
            else {}
        )
        session_id = resume_payload.get("session_id")
        if not session_id:
            logger.error("[SCOUTING] Resume missing session_id")
            return AgentResponse(
                type="answer",
                reply="Error: Resume requires session context",
                agent_name="scouting",
            )

        user_id = 0
        message_text = ""
        try:
            from app.db.models.session import ChatSession
            from app.db.models.message import Message

            session = ChatSession.objects.only("user_id").get(id=session_id)
            user_id = session.user_id

            last_message = (
                Message.objects.filter(session_id=session_id, role="user")
                .order_by("-created_at")
                .first()
            )
            if last_message and last_message.content:
                message_text = last_message.content
        except Exception as e:
            logger.warning(f"[SCOUTING] Failed to load resume context: {e}")

        api_key = ""
        if user_id:
            try:
                from app.agents.api_key_context import APIKeyContext
                from asgiref.sync import sync_to_async

                # Use sync version here since scouting_workflow runs in sync context
                # But wrap with try/except to handle Django async context detection
                try:
                    api_key_ctx = APIKeyContext.from_user(user_id)
                except Exception:
                    # If we get async context error, use the env fallback
                    api_key_ctx = APIKeyContext.from_env()
                api_key = api_key_ctx.openai_api_key or ""
            except Exception as e:
                logger.warning(f"[SCOUTING] Failed to load API key on resume: {e}")

        request = {
            "user_id": user_id,
            "session_id": session_id,
            "message": message_text,
            "api_key": api_key,
            "run_id": None,
        }

    # Extract request parameters
    state = ScoutingState(
        user_id=request.get("user_id", 0),
        session_id=request.get("session_id", 0),
        message=request.get("message", ""),
        api_key=request.get("api_key", ""),
        run_id=request.get("run_id"),
    )

    logger.info(
        f"[SCOUTING] Starting workflow for user={state.user_id}, "
        f"session={state.session_id}"
    )

    # Pre-check: User must have documents
    if not check_user_has_documents(state.user_id):
        logger.warning(f"[SCOUTING] User {state.user_id} has no documents")
        return AgentResponse(
            type="answer",
            reply=(
                "I cannot generate a scouting report because you haven't uploaded "
                "any documents yet. Please upload scouting documents, player profiles, "
                "or related materials first, then try again."
            ),
            agent_name="scouting",
        )

    # =========================================================================
    # Node 1: Intake and Route (Step 1)
    # =========================================================================
    # Note: We don't know total steps yet, so we emit with total_steps=0
    # The frontend should handle this gracefully
    emit_scouting_event(
        config,
        "plan_step_progress",
        {
            "step_index": 0,
            "total_steps": 0,  # Unknown yet
            "status": "in_progress",
            "step_name": "Analyzing request and identifying player",
        },
    )

    try:
        intake_result: IntakeResult = intake_and_route_scouting(
            message=state.message,
            api_key=state.api_key,
        ).result()

        state.player_name = intake_result.player_name
        state.sport_guess = intake_result.sport_guess

        emit_scouting_event(
            config,
            "plan_step_progress",
            {
                "step_index": 0,
                "total_steps": 0,
                "status": "completed",
                "step_name": "Analyzing request and identifying player",
                "result": f"Identified: {state.player_name} ({state.sport_guess})",
            },
        )

        logger.info(
            f"[SCOUTING] Node 1 complete: player={state.player_name}, "
            f"sport={state.sport_guess}"
        )
    except ValueError as e:
        # Player name extraction failed
        return AgentResponse(
            type="answer",
            reply=str(e),
            agent_name="scouting",
            clarification=str(e),
        )

    # =========================================================================
    # Node 2: Draft Plan (Step 2)
    # =========================================================================
    emit_scouting_event(
        config,
        "plan_step_progress",
        {
            "step_index": 1,
            "total_steps": 0,  # Unknown yet
            "status": "in_progress",
            "step_name": "Drafting scouting plan",
        },
    )

    plan_result: PlanProposal = draft_plan(
        player_name=state.player_name,
        sport_guess=state.sport_guess,
        api_key=state.api_key,
    ).result()

    state.plan_steps = plan_result.plan_steps
    state.query_hints = plan_result.query_hints

    emit_scouting_event(
        config,
        "plan_step_progress",
        {
            "step_index": 1,
            "total_steps": len(state.plan_steps),
            "status": "completed",
            "step_name": "Drafting scouting plan",
            "result": f"Generated {len(state.plan_steps)} steps",
        },
    )

    emit_scouting_event(
        config,
        "plan_proposal",
        {
            "player_name": state.player_name,
            "sport_guess": state.sport_guess,
            "plan_steps": state.plan_steps,
            "query_hints": state.query_hints,
        },
    )

    logger.info(f"[SCOUTING] Node 2 complete: {len(state.plan_steps)} steps")

    # =========================================================================
    # HITL Gate A: Plan Approval
    # =========================================================================
    plan_decision = request_plan_approval(
        player_name=state.player_name,
        sport_guess=state.sport_guess,
        plan_steps=state.plan_steps,
        query_hints=state.query_hints,
        session_id=state.session_id,
    )

    # Update state with any edits
    if plan_decision.get("edited"):
        state.plan_steps = plan_decision.get("plan_steps", state.plan_steps)
        state.query_hints = plan_decision.get("query_hints", state.query_hints)
        logger.info("[SCOUTING] Plan updated from user edits")

    # =========================================================================
    # Edit Loop: Nodes 3-7 with potential re-runs
    # =========================================================================
    # Track total steps for progress (steps 1-2 already done, now doing 3-7+)
    total_steps = len(state.plan_steps)
    current_step = 0  # 0-indexed, will increment as we start each step

    while state.edit_iterations < MAX_EDIT_ITERATIONS:
        state.edit_iterations += 1

        # ---------------------------------------------------------------------
        # Node 3: Build Queries (Step 3)
        # ---------------------------------------------------------------------
        current_step = 2  # Step 3 (0-indexed = 2)
        emit_scouting_event(
            config,
            "plan_step_progress",
            {
                "step_index": current_step,
                "total_steps": total_steps,
                "status": "in_progress",
                "step_name": "Building search queries",
            },
        )

        state.queries = build_queries(
            player_name=state.player_name,
            sport_guess=state.sport_guess,
            query_hints=state.query_hints,
            api_key=state.api_key,
        ).result()

        emit_scouting_event(
            config,
            "plan_step_progress",
            {
                "step_index": current_step,
                "total_steps": total_steps,
                "status": "completed",
                "step_name": "Building search queries",
                "result": f"Generated {len(state.queries)} queries",
            },
        )

        logger.info(f"[SCOUTING] Node 3 complete: {len(state.queries)} queries")

        # ---------------------------------------------------------------------
        # Node 4: Retrieve Evidence (Step 4)
        # ---------------------------------------------------------------------
        current_step = 3  # Step 4 (0-indexed = 3)
        emit_scouting_event(
            config,
            "plan_step_progress",
            {
                "step_index": current_step,
                "total_steps": total_steps,
                "status": "in_progress",
                "step_name": "Retrieving evidence from documents",
            },
        )

        state.evidence_pack = retrieve_evidence(
            user_id=state.user_id,
            queries=state.queries,
            api_key=state.api_key,
        ).result()

        emit_scouting_event(
            config,
            "plan_step_progress",
            {
                "step_index": current_step,
                "total_steps": total_steps,
                "status": "completed",
                "step_name": "Retrieving evidence from documents",
                "result": f"Found {len(state.evidence_pack.chunks)} chunks, confidence={state.evidence_pack.confidence}",
            },
        )

        logger.info(
            f"[SCOUTING] Node 4 complete: {len(state.evidence_pack.chunks)} chunks, "
            f"confidence={state.evidence_pack.confidence}"
        )

        # ---------------------------------------------------------------------
        # Node 5: Extract Fields (Step 5)
        # ---------------------------------------------------------------------
        current_step = 4  # Step 5 (0-indexed = 4)
        emit_scouting_event(
            config,
            "plan_step_progress",
            {
                "step_index": current_step,
                "total_steps": total_steps,
                "status": "in_progress",
                "step_name": "Extracting player attributes",
            },
        )

        player_fields, raw_facts, coverage = extract_fields(
            evidence_pack=state.evidence_pack,
            player_name=state.player_name,
            sport_guess=state.sport_guess,
            api_key=state.api_key,
        ).result()

        state.player_fields = player_fields
        state.raw_facts = raw_facts
        state.coverage = coverage

        emit_scouting_event(
            config,
            "plan_step_progress",
            {
                "step_index": current_step,
                "total_steps": total_steps,
                "status": "completed",
                "step_name": "Extracting player attributes",
                "result": f"Extracted {len(state.raw_facts)} facts",
            },
        )

        emit_scouting_event(
            config,
            "coverage_report",
            {
                "found": state.coverage.found if state.coverage else [],
                "missing": state.coverage.missing if state.coverage else [],
                "confidence": state.evidence_pack.confidence
                if state.evidence_pack
                else "low",
                "chunk_count": len(state.evidence_pack.chunks)
                if state.evidence_pack
                else 0,
            },
        )

        logger.info(
            f"[SCOUTING] Node 5 complete: {len(state.raw_facts)} facts extracted"
        )

        # Inner loop for compose-only re-runs
        compose_feedback = None
        while True:
            # -----------------------------------------------------------------
            # Node 6: Compose Report (Step 6)
            # -----------------------------------------------------------------
            current_step = 5  # Step 6 (0-indexed = 5)
            emit_scouting_event(
                config,
                "plan_step_progress",
                {
                    "step_index": current_step,
                    "total_steps": total_steps,
                    "status": "in_progress",
                    "step_name": "Composing scouting report",
                },
            )

            state.report_draft = compose_report(
                player_fields=state.player_fields,
                raw_facts=state.raw_facts,
                coverage=state.coverage,
                feedback=compose_feedback,
                api_key=state.api_key,
            ).result()

            emit_scouting_event(
                config,
                "plan_step_progress",
                {
                    "step_index": current_step,
                    "total_steps": total_steps,
                    "status": "completed",
                    "step_name": "Composing scouting report",
                    "result": f"Generated {len(state.report_draft.report_text)} characters",
                },
            )

            logger.info(
                f"[SCOUTING] Node 6 complete: "
                f"{len(state.report_draft.report_text)} chars"
            )

            # -----------------------------------------------------------------
            # Node 7: Prepare Preview (Step 7)
            # -----------------------------------------------------------------
            current_step = 6  # Step 7 (0-indexed = 6)
            emit_scouting_event(
                config,
                "plan_step_progress",
                {
                    "step_index": current_step,
                    "total_steps": total_steps,
                    "status": "in_progress",
                    "step_name": "Preparing preview for approval",
                },
            )

            # Extract source doc IDs from evidence
            source_doc_ids = list(
                set(chunk.doc_id for chunk in state.evidence_pack.chunks)
            )

            state.preview = prepare_preview(
                report_draft=state.report_draft,
                source_doc_ids=source_doc_ids,
            ).result()

            emit_scouting_event(
                config,
                "plan_step_progress",
                {
                    "step_index": current_step,
                    "total_steps": total_steps,
                    "status": "completed",
                    "step_name": "Preparing preview for approval",
                    "result": "Preview ready",
                },
            )

            logger.info("[SCOUTING] Node 7 complete: preview ready")

            preview_payload = {
                "player_fields": state.preview.player.model_dump(exclude_none=True),
                "report_summary": state.report_draft.report_summary,
                "report_text": state.report_draft.report_text,
                "db_payload_preview": state.preview.model_dump(exclude_none=True),
            }
            emit_scouting_event(config, "player_preview", preview_payload)

            # -----------------------------------------------------------------
            # HITL Gate B: Player Approval
            # -----------------------------------------------------------------
            player_decision = request_player_approval(
                preview=state.preview,
                report_summary=state.report_draft.report_summary,
                report_text=state.report_draft.report_text,
                session_id=state.session_id,
            )

            action = player_decision.get("action", "approve")
            feedback = player_decision.get("feedback")

            if action == "approve":
                # ---------------------------------------------------------
                # Node 8: Write Player Item
                # ---------------------------------------------------------
                try:
                    write_result: CreatePlayerWithReportResponse = write_player_item(
                        preview=state.preview,
                        user_id=state.user_id,
                        run_id=state.run_id,
                        request_text=state.message,
                    ).result()

                    state.player_record_id = write_result.player_id
                    state.report_id = write_result.report_id
                    state.saved = True

                    logger.info(
                        f"[SCOUTING] Node 8 complete: player={state.player_record_id}"
                    )
                except Exception as e:
                    logger.error(f"[SCOUTING] Node 8 failed: {e}")
                    state.saved = False

                # Exit loops
                break

            elif action == "reject":
                # Skip write, return report anyway
                state.saved = False
                logger.info("[SCOUTING] User rejected save, returning report only")
                break

            elif action == "edit_wording":
                # Re-run compose only with feedback
                compose_feedback = feedback
                logger.info("[SCOUTING] Re-running compose with wording feedback")
                continue

            elif action == "edit_content":
                # Re-run from build_queries with updated hints
                if feedback:
                    state.query_hints.append(feedback)
                logger.info(
                    "[SCOUTING] Re-running from build_queries with content feedback"
                )
                break  # Break inner loop, continue outer loop

            else:
                # Unknown action, default to approve
                logger.warning(
                    f"[SCOUTING] Unknown action: {action}, defaulting to approve"
                )
                state.saved = False
                break

        # Check if we should exit outer loop
        if action in ("approve", "reject"):
            break

    # =========================================================================
    # Node 9: Build Final Response
    # =========================================================================
    response = build_final_response(
        report_draft=state.report_draft,
        player_record_id=state.player_record_id,
        report_id=state.report_id,
        saved=state.saved,
        coverage=state.coverage,
        player_name=state.player_name,
    ).result()

    logger.info(
        f"[SCOUTING] Workflow complete: saved={state.saved}, "
        f"iterations={state.edit_iterations}"
    )

    return response
