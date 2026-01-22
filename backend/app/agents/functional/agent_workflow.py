"""
Unified Agent Workflow for LangGraph Functional API.

This is the main entrypoint for all agent interactions. It handles:
- Dynamic plan generation based on user intent
- Plan approval via HITL Gate A (Accept/Reject)
- Sequential plan execution
- Player approval via HITL Gate B (for save_player action)

Architecture:
    1. Analyze user message
    2. Generate dynamic ExecutionPlan
    3. HITL Gate A: Plan Approval (Accept/Reject)
    4. Execute plan steps sequentially
    5. HITL Gate B: Player Approval (if save_player step)
    6. Return final response
"""

from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
from queue import Full as QueueFull
from langgraph.func import entrypoint, task
from langgraph.types import interrupt, Command
from langgraph.errors import GraphInterrupt
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from app.agents.functional.models import AgentResponse, RoutingDecision, ToolResult
from app.agents.functional.scouting.schemas import (
    ExecutionPlan,
    PlanStep,
    EvidencePack,
    PlayerFields,
    Coverage,
    ScoutingReportDraft,
    DbPayloadPreview,
    CreatePlayerWithReportResponse,
    ChunkData,
)
from app.agents.functional.tasks.scouting import (
    generate_plan,
    retrieve_evidence,
    extract_fields,
    compose_report,
    prepare_preview,
    write_player_item,
    build_final_response,
)
from app.agents.functional.tasks.supervisor import route_to_agent
from app.agents.functional.tasks.agent import execute_agent, refine_with_tool_results
from app.agents.functional.tasks.tools import execute_tools
from app.agents.functional.workflow import (
    get_sync_checkpointer,
    get_event_queue_from_config,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


def emit_workflow_event(
    config: Optional[RunnableConfig],
    event_type: str,
    data: Dict[str, Any],
) -> None:
    """Emit a workflow event to the streaming queue if available."""
    if not config:
        return

    event_queue = get_event_queue_from_config(config)
    if not event_queue:
        return

    try:
        event_queue.put_nowait({"type": event_type, "data": data})
    except QueueFull:
        logger.debug(f"[WORKFLOW] Event queue full, dropping {event_type} event")
    except Exception as e:
        logger.debug(
            f"[WORKFLOW] Failed to emit {event_type} event: {e}", exc_info=True
        )


@dataclass
class WorkflowState:
    """Internal state for unified workflow."""

    # Request info
    user_id: int = 0
    session_id: int = 0
    message: str = ""
    api_key: str = ""
    run_id: Optional[str] = None

    # Plan info
    plan: Optional[ExecutionPlan] = None

    # Execution context (accumulated during plan execution)
    all_chunks: List[ChunkData] = field(default_factory=list)
    all_queries: List[str] = field(default_factory=list)
    player_fields: Optional[PlayerFields] = None
    raw_facts: List[str] = field(default_factory=list)
    coverage: Optional[Coverage] = None
    report_draft: Optional[ScoutingReportDraft] = None
    preview: Optional[DbPayloadPreview] = None

    # Results
    player_record_id: Optional[str] = None
    report_id: Optional[str] = None
    saved: bool = False
    answer_context: str = ""

    # Track completed step indices for resume (checkpoint doesn't restore step position)
    completed_steps: List[int] = field(default_factory=list)


# =============================================================================
# WORKFLOW STATE SERIALIZATION
# =============================================================================


def serialize_workflow_state(state: WorkflowState) -> Dict[str, Any]:
    """
    Serialize WorkflowState to a JSON-serializable dictionary.

    This is used to persist workflow state to session.metadata so it survives
    across HITL interrupts. Only serializes fields that are needed for resume.
    """
    return {
        # Plan info
        "plan": state.plan.model_dump() if state.plan else None,
        # Execution context (accumulated during plan execution)
        "all_chunks": [chunk.model_dump() for chunk in state.all_chunks],
        "all_queries": state.all_queries,
        "player_fields": state.player_fields.model_dump() if state.player_fields else None,
        "raw_facts": state.raw_facts,
        "coverage": state.coverage.model_dump() if state.coverage else None,
        "report_draft": state.report_draft.model_dump() if state.report_draft else None,
        "preview": state.preview.model_dump() if state.preview else None,
        # Results
        "player_record_id": state.player_record_id,
        "report_id": state.report_id,
        "saved": state.saved,
        "answer_context": state.answer_context,
        # Step tracking
        "completed_steps": state.completed_steps,
    }


def deserialize_workflow_state(state: WorkflowState, data: Dict[str, Any]) -> None:
    """
    Restore WorkflowState fields from a serialized dictionary.

    Modifies the state object in place to restore fields from persisted data.
    Handles missing fields gracefully for backward compatibility.
    """
    if not data:
        return

    # Restore plan
    if data.get("plan"):
        try:
            state.plan = ExecutionPlan.model_validate(data["plan"])
        except Exception as e:
            logger.warning(f"[WORKFLOW] Failed to restore plan: {e}")

    # Restore chunks
    if data.get("all_chunks"):
        try:
            state.all_chunks = [
                ChunkData.model_validate(chunk) for chunk in data["all_chunks"]
            ]
        except Exception as e:
            logger.warning(f"[WORKFLOW] Failed to restore all_chunks: {e}")

    # Restore queries
    if data.get("all_queries"):
        state.all_queries = data["all_queries"]

    # Restore player_fields
    if data.get("player_fields"):
        try:
            state.player_fields = PlayerFields.model_validate(data["player_fields"])
        except Exception as e:
            logger.warning(f"[WORKFLOW] Failed to restore player_fields: {e}")

    # Restore raw_facts
    if data.get("raw_facts"):
        state.raw_facts = data["raw_facts"]

    # Restore coverage
    if data.get("coverage"):
        try:
            state.coverage = Coverage.model_validate(data["coverage"])
        except Exception as e:
            logger.warning(f"[WORKFLOW] Failed to restore coverage: {e}")

    # Restore report_draft
    if data.get("report_draft"):
        try:
            state.report_draft = ScoutingReportDraft.model_validate(data["report_draft"])
        except Exception as e:
            logger.warning(f"[WORKFLOW] Failed to restore report_draft: {e}")

    # Restore preview
    if data.get("preview"):
        try:
            state.preview = DbPayloadPreview.model_validate(data["preview"])
        except Exception as e:
            logger.warning(f"[WORKFLOW] Failed to restore preview: {e}")

    # Restore results
    if data.get("player_record_id"):
        state.player_record_id = data["player_record_id"]
    if data.get("report_id"):
        state.report_id = data["report_id"]
    if data.get("saved"):
        state.saved = data["saved"]
    if data.get("answer_context"):
        state.answer_context = data["answer_context"]

    # Restore completed_steps
    if data.get("completed_steps"):
        state.completed_steps = data["completed_steps"]

    logger.info(
        f"[WORKFLOW] Restored state: plan={state.plan is not None}, "
        f"chunks={len(state.all_chunks)}, player_fields={state.player_fields is not None}, "
        f"report_draft={state.report_draft is not None}, preview={state.preview is not None}, "
        f"completed_steps={state.completed_steps}"
    )


def check_user_has_documents(user_id: int) -> bool:
    """Check if user has any indexed documents for RAG."""
    try:
        from app.db.models.document import Document

        return Document.objects.filter(
            owner_id=user_id, status=Document.Status.READY
        ).exists()
    except Exception as e:
        logger.warning(f"Error checking user documents: {e}")
        return False


def save_workflow_state_to_session(session_id: int, state: WorkflowState) -> None:
    """
    Save full WorkflowState to session metadata.

    This persists the workflow state across HITL interrupts, including:
    - completed_steps (which steps are done)
    - all_chunks, player_fields, report_draft, preview (actual data)

    Without this, resuming after Gate B would have empty state data
    even though steps were marked as completed.
    """
    try:
        from app.db.models.session import ChatSession

        session = ChatSession.objects.get(id=session_id)
        if session.metadata is None:
            session.metadata = {}

        # Serialize and store full workflow state
        session.metadata["workflow_state"] = serialize_workflow_state(state)
        session.save(update_fields=["metadata"])

        logger.info(
            f"[WORKFLOW] Saved workflow_state to session {session_id}: "
            f"completed_steps={state.completed_steps}, "
            f"chunks={len(state.all_chunks)}, "
            f"has_preview={state.preview is not None}"
        )
    except Exception as e:
        logger.warning(f"[WORKFLOW] Failed to save workflow_state: {e}")


def load_workflow_state_from_session(session_id: int, state: WorkflowState) -> bool:
    """
    Load full WorkflowState from session metadata.

    Restores all workflow state fields including:
    - completed_steps (which steps are done)
    - all_chunks, player_fields, report_draft, preview (actual data)

    Returns True if state was restored, False otherwise.
    """
    try:
        from app.db.models.session import ChatSession

        session = ChatSession.objects.get(id=session_id)

        # Try new workflow_state format first
        if session.metadata and "workflow_state" in session.metadata:
            stored_state = session.metadata["workflow_state"]
            deserialize_workflow_state(state, stored_state)
            logger.info(
                f"[WORKFLOW] Loaded workflow_state from session {session_id}: "
                f"completed_steps={state.completed_steps}"
            )
            return True

        # Backward compatibility: try old completed_steps format
        if session.metadata and "completed_steps" in session.metadata:
            state.completed_steps = session.metadata["completed_steps"]
            logger.info(
                f"[WORKFLOW] Loaded completed_steps (legacy) from session {session_id}: "
                f"{state.completed_steps}"
            )
            return True

        return False
    except Exception as e:
        logger.warning(f"[WORKFLOW] Failed to load workflow_state: {e}")
        return False


def clear_workflow_state_from_session(session_id: int) -> None:
    """
    Clear workflow state from session metadata.

    Called when workflow completes successfully.
    Removes both new workflow_state and legacy completed_steps.
    """
    try:
        from app.db.models.session import ChatSession

        session = ChatSession.objects.get(id=session_id)
        modified = False

        if session.metadata:
            # Clear new format
            if "workflow_state" in session.metadata:
                del session.metadata["workflow_state"]
                modified = True

            # Clear legacy format for backward compatibility
            if "completed_steps" in session.metadata:
                del session.metadata["completed_steps"]
                modified = True

        if modified:
            session.save(update_fields=["metadata"])
            logger.info(f"[WORKFLOW] Cleared workflow_state from session {session_id}")
    except Exception as e:
        logger.warning(f"[WORKFLOW] Failed to clear workflow_state: {e}")


def request_plan_approval(
    plan: ExecutionPlan,
    session_id: int,
) -> Dict[str, Any]:
    """
    Request plan approval via HITL Gate A.

    User can Accept or Reject the plan.
    """
    logger.info(
        f"[WORKFLOW] [HITL-A] Requesting plan approval: {plan.intent}, "
        f"{len(plan.steps)} steps, session={session_id}"
    )

    # Convert plan to dict for interrupt payload
    plan_dict = plan.model_dump()

    decision = interrupt(
        {
            "type": "plan_approval",
            "session_id": session_id,
            "plan": plan_dict,
            "player_name": plan.player_name,
            "sport_guess": plan.sport_guess,
            "intent": plan.intent,
            "steps": [
                {
                    "action": step.action,
                    "description": step.description,
                    "params": step.params,
                }
                for step in plan.steps
            ],
        }
    )

    approved = decision.get("approved", True) if decision else True
    logger.info(f"[WORKFLOW] [HITL-A] Plan approval decision: approved={approved}")

    return decision or {"approved": True}


def request_player_approval(
    preview: DbPayloadPreview,
    report_draft: ScoutingReportDraft,
    session_id: int,
) -> Dict[str, Any]:
    """
    Request player item approval via HITL Gate B.

    User can Approve or Reject saving the player.
    """
    logger.info(
        f"[WORKFLOW] [HITL-B] Requesting player approval for "
        f"{preview.player.display_name}, session={session_id}"
    )

    player_dict = preview.player.model_dump(exclude_none=True)

    decision = interrupt(
        {
            "type": "player_approval",
            "session_id": session_id,
            "player_fields": player_dict,
            "report_summary": report_draft.report_summary,
            "report_text": report_draft.report_text,
        }
    )

    action = decision.get("action", "approve") if decision else "approve"
    logger.info(f"[WORKFLOW] [HITL-B] Player approval decision: action={action}")

    return decision or {"action": "approve"}


# ============================================================================
# STEP EXECUTORS
# ============================================================================


def execute_rag_search_step(
    step: PlanStep,
    state: WorkflowState,
    config: Optional[RunnableConfig],
) -> Dict[str, Any]:
    """Execute a rag_search step."""
    query = step.params.get("query", "")
    if not query:
        return {"success": False, "error": "No query provided"}

    logger.info(f"[WORKFLOW] Executing rag_search: {query[:50]}...")

    evidence = retrieve_evidence(
        user_id=state.user_id,
        queries=[query],
        api_key=state.api_key,
        max_chunks=15,
    ).result()

    # Accumulate chunks
    state.all_chunks.extend(evidence.chunks)
    state.all_queries.append(query)

    # Build context for answer step
    if evidence.chunks:
        chunk_texts = [f"- {c.text[:300]}..." for c in evidence.chunks[:5]]
        state.answer_context += f"\n\n**Search: {query}**\n" + "\n".join(chunk_texts)

    return {
        "success": True,
        "chunks_found": len(evidence.chunks),
        "confidence": evidence.confidence,
    }


def execute_extract_player_step(
    step: PlanStep,
    state: WorkflowState,
    config: Optional[RunnableConfig],
) -> Dict[str, Any]:
    """Execute an extract_player step."""
    logger.info(f"[WORKFLOW] Executing extract_player for {state.plan.player_name}")

    if not state.all_chunks:
        return {"success": False, "error": "No evidence available"}

    # Dedupe and sort chunks
    seen_ids = set()
    unique_chunks = []
    for chunk in state.all_chunks:
        if chunk.chunk_id not in seen_ids:
            seen_ids.add(chunk.chunk_id)
            unique_chunks.append(chunk)
    unique_chunks.sort(key=lambda c: c.score, reverse=True)
    unique_chunks = unique_chunks[:40]

    evidence_pack = EvidencePack(
        queries=state.all_queries,
        chunks=unique_chunks,
        coverage=Coverage(found=[], missing=[]),
        confidence="med" if len(unique_chunks) > 10 else "low",
    )

    player_fields, raw_facts, coverage = extract_fields(
        evidence_pack=evidence_pack,
        player_name=state.plan.player_name or "Unknown Player",
        sport_guess=state.plan.sport_guess or "unknown",
        api_key=state.api_key,
    ).result()

    state.player_fields = player_fields
    state.raw_facts = raw_facts
    state.coverage = coverage

    return {
        "success": True,
        "facts_extracted": len(raw_facts),
    }


def execute_compose_report_step(
    step: PlanStep,
    state: WorkflowState,
    config: Optional[RunnableConfig],
) -> Dict[str, Any]:
    """Execute a compose_report step."""
    logger.info(f"[WORKFLOW] Executing compose_report")

    if not state.player_fields:
        return {"success": False, "error": "No player data available"}

    feedback = step.params.get("feedback")

    report_draft = compose_report(
        player_fields=state.player_fields,
        raw_facts=state.raw_facts,
        coverage=state.coverage or Coverage(found=[], missing=[]),
        feedback=feedback,
        api_key=state.api_key,
    ).result()

    state.report_draft = report_draft

    # Prepare preview
    source_doc_ids = list(set(chunk.doc_id for chunk in state.all_chunks))
    state.preview = prepare_preview(
        report_draft=report_draft,
        source_doc_ids=source_doc_ids,
    ).result()

    return {
        "success": True,
        "report_length": len(report_draft.report_text),
    }


def execute_update_report_step(
    step: PlanStep,
    state: WorkflowState,
    config: Optional[RunnableConfig],
) -> Dict[str, Any]:
    """Execute an update_report step."""
    logger.info("[WORKFLOW] Executing update_report")

    feedback = step.params.get("feedback", "")
    # TODO: Load existing report and merge with new evidence

    if state.player_fields:
        report_draft = compose_report(
            player_fields=state.player_fields,
            raw_facts=state.raw_facts,
            coverage=state.coverage or Coverage(found=[], missing=[]),
            feedback=feedback,
            api_key=state.api_key,
        ).result()

        state.report_draft = report_draft
        source_doc_ids = list(set(chunk.doc_id for chunk in state.all_chunks))
        state.preview = prepare_preview(
            report_draft=report_draft,
            source_doc_ids=source_doc_ids,
        ).result()

        return {"success": True}

    return {"success": False, "error": "No player data to update"}


def execute_save_player_step(
    step: PlanStep,
    state: WorkflowState,
    config: Optional[RunnableConfig],
) -> Dict[str, Any]:
    """
    Execute a save_player step.

    This triggers HITL Gate B for player approval.
    """
    logger.info(f"[WORKFLOW] Executing save_player")

    if not state.preview or not state.report_draft:
        return {"success": False, "error": "No report to save"}

    # Emit player preview event
    emit_workflow_event(
        config,
        "player_preview",
        {
            "player_fields": state.preview.player.model_dump(exclude_none=True),
            "report_summary": state.report_draft.report_summary,
            "report_text": state.report_draft.report_text,
            "db_payload_preview": state.preview.model_dump(exclude_none=True),
        },
    )

    # HITL Gate B
    decision = request_player_approval(
        preview=state.preview,
        report_draft=state.report_draft,
        session_id=state.session_id,
    )

    action = decision.get("action", "approve")

    if action == "approve":
        try:
            write_result = write_player_item(
                preview=state.preview,
                user_id=state.user_id,
                run_id=state.run_id,
                request_text=state.message,
            ).result()

            state.player_record_id = write_result.player_id
            state.report_id = write_result.report_id
            state.saved = True

            return {
                "success": True,
                "player_id": write_result.player_id,
                "report_id": write_result.report_id,
            }
        except Exception as e:
            logger.error(f"[WORKFLOW] Failed to save: {e}")
            return {"success": False, "error": str(e)}

    elif action == "reject":
        state.saved = False
        return {"success": True, "rejected": True}

    return {"success": False, "error": f"Unknown action: {action}"}


def execute_answer_step(
    step: PlanStep,
    state: WorkflowState,
    config: Optional[RunnableConfig],
) -> Dict[str, Any]:
    """Execute an answer step - generates final response."""
    logger.info("[WORKFLOW] Executing answer step")
    # Answer generation happens after plan execution
    return {"success": True}


# ============================================================================
# PLAN EXECUTION
# ============================================================================


def execute_plan_steps(
    state: WorkflowState,
    config: Optional[RunnableConfig],
) -> List[Dict[str, Any]]:
    """
    Execute all steps in the plan sequentially.

    Skips steps that have already been completed (tracked in state.completed_steps).
    This is important for resume after HITL Gate B - we don't want to re-run
    steps 1-6 when resuming from step 7.

    Completed steps are persisted to session metadata so they survive across
    HITL interrupts (state object is recreated on each workflow invocation).

    Returns list of step results.
    """
    if not state.plan:
        return []

    # Load previously stored workflow state from database (for resume scenarios)
    # This is critical because WorkflowState is recreated fresh on each invocation
    # Without this, we'd have completed_steps but empty data (chunks, player_fields, etc.)
    if not state.completed_steps and state.session_id:
        if load_workflow_state_from_session(state.session_id, state):
            logger.info(
                f"[WORKFLOW] Restored workflow state from session: "
                f"completed_steps={state.completed_steps}"
            )

    step_results = []
    total_steps = len(state.plan.steps)

    for idx, step in enumerate(state.plan.steps):
        # Skip already completed steps (for resume scenarios)
        if idx in state.completed_steps:
            logger.info(
                f"[WORKFLOW] Step {idx + 1}/{total_steps}: {step.action} - SKIPPED (already completed)"
            )
            # Emit completed status for UI consistency
            emit_workflow_event(
                config,
                "plan_step_progress",
                {
                    "step_index": idx,
                    "total_steps": total_steps,
                    "status": "completed",
                    "step_name": step.description,
                    "action": step.action,
                },
            )
            continue

        logger.info(
            f"[WORKFLOW] Step {idx + 1}/{total_steps}: {step.action} - {step.description}"
        )

        # Emit step start
        emit_workflow_event(
            config,
            "plan_step_progress",
            {
                "step_index": idx,
                "total_steps": total_steps,
                "status": "in_progress",
                "step_name": step.description,
                "action": step.action,
            },
        )

        try:
            # Execute based on action type
            if step.action == "rag_search":
                result = execute_rag_search_step(step, state, config)
            elif step.action == "extract_player":
                result = execute_extract_player_step(step, state, config)
            elif step.action == "compose_report":
                result = execute_compose_report_step(step, state, config)
            elif step.action == "update_report":
                result = execute_update_report_step(step, state, config)
            elif step.action == "save_player":
                result = execute_save_player_step(step, state, config)
            elif step.action == "answer":
                result = execute_answer_step(step, state, config)
            else:
                result = {"success": False, "error": f"Unknown action: {step.action}"}

            step_results.append({"step": idx, "action": step.action, **result})

            # Mark step as completed (important for resume after HITL gates)
            state.completed_steps.append(idx)

            # Persist full workflow state to database so it survives HITL interrupts
            # This saves not just completed_steps, but also all_chunks, player_fields, etc.
            if state.session_id:
                save_workflow_state_to_session(state.session_id, state)

            # Emit step complete
            emit_workflow_event(
                config,
                "plan_step_progress",
                {
                    "step_index": idx,
                    "total_steps": total_steps,
                    "status": "completed",
                    "step_name": step.description,
                    "action": step.action,
                },
            )

        except GraphInterrupt:
            # Save full workflow state before interrupt so resume has all data
            # This is critical - without this, resume would have empty state data
            if state.session_id:
                save_workflow_state_to_session(state.session_id, state)
                logger.info(
                    f"[WORKFLOW] Saved workflow state before interrupt: "
                    f"completed_steps={state.completed_steps}, has_preview={state.preview is not None}"
                )
            # Re-raise GraphInterrupt so HITL gates work properly
            # This allows save_player step to pause for player approval
            raise
        except Exception as e:
            logger.error(f"[WORKFLOW] Step {idx} failed: {e}", exc_info=True)
            step_results.append(
                {
                    "step": idx,
                    "action": step.action,
                    "success": False,
                    "error": str(e),
                }
            )
            emit_workflow_event(
                config,
                "plan_step_progress",
                {
                    "step_index": idx,
                    "total_steps": total_steps,
                    "status": "error",
                    "step_name": step.description,
                    "error": str(e),
                },
            )

    # Clear workflow state from session when workflow completes successfully
    if state.session_id:
        clear_workflow_state_from_session(state.session_id)

    return step_results


def generate_final_response(state: WorkflowState) -> AgentResponse:
    """Generate final response based on plan intent and results."""

    intent = state.plan.intent if state.plan else "general_chat"

    if intent == "scouting_report":
        if state.saved and state.report_draft:
            return AgentResponse(
                type="answer",
                reply=(
                    f"I've created and saved the scouting report for {state.plan.player_name}.\n\n"
                    f"**Summary:**\n"
                    + "\n".join(
                        f"- {point}" for point in state.report_draft.report_summary[:5]
                    )
                ),
                agent_name="scouting",
            )
        elif state.report_draft:
            return AgentResponse(
                type="answer",
                reply=(
                    f"Here's the scouting report for {state.plan.player_name} (not saved):\n\n"
                    f"{state.report_draft.report_text}"
                ),
                agent_name="scouting",
            )
        else:
            return AgentResponse(
                type="answer",
                reply="I couldn't generate a complete scouting report. Please try again with more specific information.",
                agent_name="scouting",
            )

    elif intent == "info_query":
        if state.answer_context:
            # Use LLM to synthesize answer from context
            # For now, return the raw context
            return AgentResponse(
                type="answer",
                reply=f"Based on the documents I found:\n{state.answer_context}",
                agent_name="search",
            )
        else:
            return AgentResponse(
                type="answer",
                reply="I couldn't find relevant information in your documents.",
                agent_name="search",
            )

    elif intent == "update_report":
        if state.saved:
            return AgentResponse(
                type="answer",
                reply="The report has been updated successfully.",
                agent_name="scouting",
            )
        else:
            return AgentResponse(
                type="answer",
                reply="The report update was not saved.",
                agent_name="scouting",
            )

    else:
        # general_chat
        return AgentResponse(
            type="answer",
            reply="How can I help you with scouting today?",
            agent_name="greeter",
        )


# ============================================================================
# MAIN WORKFLOW ENTRYPOINT
# ============================================================================

_workflow_checkpointer = None
try:
    _workflow_checkpointer = get_sync_checkpointer()
except Exception as e:
    logger.debug(f"Workflow checkpointer creation deferred: {e}")


@entrypoint(checkpointer=_workflow_checkpointer)
def agent_workflow(
    request: Union[Dict[str, Any], Command, Any],
    config: Optional[RunnableConfig] = None,
) -> AgentResponse:
    """
    Unified agent workflow entrypoint.

    Flow:
    1. Parse request
    2. Generate dynamic plan based on intent
    3. HITL Gate A: Plan approval (Accept/Reject)
    4. Execute plan steps sequentially
    5. HITL Gate B: Player approval (if save_player step)
    6. Return final response
    """
    # Handle Command for resume
    if isinstance(request, Command):
        logger.info("[WORKFLOW] Resuming from interrupt via Command")
        resume_payload = (
            request.resume
            if hasattr(request, "resume") and isinstance(request.resume, dict)
            else {}
        )
        session_id = resume_payload.get("session_id")
        if not session_id:
            return AgentResponse(
                type="answer",
                reply="Error: Resume requires session context",
                agent_name="system",
            )

        # Load context from session
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
            logger.warning(f"[WORKFLOW] Failed to load resume context: {e}")

        api_key = ""
        if user_id:
            try:
                from app.agents.api_key_context import APIKeyContext

                try:
                    api_key_ctx = APIKeyContext.from_user(user_id)
                except Exception:
                    api_key_ctx = APIKeyContext.from_env()
                api_key = api_key_ctx.openai_api_key or ""
            except Exception as e:
                logger.warning(f"[WORKFLOW] Failed to load API key on resume: {e}")

        request = {
            "user_id": user_id,
            "session_id": session_id,
            "message": message_text,
            "api_key": api_key,
            "run_id": None,
        }

    # Parse request
    if hasattr(request, "model_dump"):
        request_dict = request.model_dump()
    elif hasattr(request, "dict"):
        request_dict = request.dict()
    elif isinstance(request, dict):
        request_dict = request
    else:
        request_dict = {
            "user_id": getattr(request, "user_id", 0),
            "session_id": getattr(request, "session_id", 0),
            "message": getattr(request, "query", "") or getattr(request, "message", ""),
            "api_key": getattr(request, "openai_api_key", "") or "",
            "run_id": getattr(request, "run_id", None),
        }

    # Normalize field names
    if "query" in request_dict and not request_dict.get("message"):
        request_dict["message"] = request_dict["query"]
    if "openai_api_key" in request_dict and not request_dict.get("api_key"):
        request_dict["api_key"] = request_dict["openai_api_key"] or ""

    # Initialize state
    state = WorkflowState(
        user_id=request_dict.get("user_id", 0),
        session_id=request_dict.get("session_id", 0),
        message=request_dict.get("message", ""),
        api_key=request_dict.get("api_key", ""),
        run_id=request_dict.get("run_id"),
    )

    logger.info(
        f"[WORKFLOW] Starting workflow for user={state.user_id}, "
        f"session={state.session_id}, message={state.message[:50]}..."
    )

    # Check for documents
    if not check_user_has_documents(state.user_id):
        return AgentResponse(
            type="answer",
            reply=(
                "I don't have any documents to search through yet. "
                "Please upload some documents first, then I can help you."
            ),
            agent_name="system",
        )

    # =========================================================================
    # Step 1: Generate Plan
    # =========================================================================
    emit_workflow_event(
        config,
        "workflow_status",
        {
            "phase": "planning",
            "status": "in_progress",
            "message": "Analyzing request and generating plan",
        },
    )

    plan = generate_plan(
        message=state.message,
        player_name=None,  # Let planner detect
        sport_guess=None,
        api_key=state.api_key,
    ).result()

    state.plan = plan

    logger.info(
        f"[WORKFLOW] Generated plan: intent={plan.intent}, "
        f"player={plan.player_name}, steps={len(plan.steps)}"
    )

    emit_workflow_event(
        config,
        "workflow_status",
        {
            "phase": "planning",
            "status": "completed",
            "message": "Plan generated",
        },
    )

    # Emit plan proposal for frontend
    emit_workflow_event(
        config,
        "plan_proposal",
        {
            "intent": plan.intent,
            "player_name": plan.player_name,
            "sport_guess": plan.sport_guess,
            "reasoning": plan.reasoning,
            "steps": [
                {
                    "action": step.action,
                    "description": step.description,
                }
                for step in plan.steps
            ],
        },
    )

    # =========================================================================
    # Step 2: HITL Gate A - Plan Approval
    # =========================================================================
    plan_decision = request_plan_approval(plan, state.session_id)

    if not plan_decision.get("approved", True):
        logger.info("[WORKFLOW] Plan rejected by user")
        return AgentResponse(
            type="answer",
            reply="Plan was rejected. Please let me know how I can help differently.",
            agent_name="system",
        )

    # =========================================================================
    # Step 3: Execute Plan Steps
    # =========================================================================
    emit_workflow_event(
        config,
        "workflow_status",
        {
            "phase": "execution",
            "status": "in_progress",
            "message": "Executing plan",
        },
    )

    step_results = execute_plan_steps(state, config)

    emit_workflow_event(
        config,
        "workflow_status",
        {
            "phase": "execution",
            "status": "completed",
            "message": "Plan execution complete",
        },
    )

    # =========================================================================
    # Step 4: Generate Final Response
    # =========================================================================
    response = generate_final_response(state)

    logger.info(f"[WORKFLOW] Complete: intent={plan.intent}, saved={state.saved}")

    return response


# Legacy alias
scouting_workflow = agent_workflow
