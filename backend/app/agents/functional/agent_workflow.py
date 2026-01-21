"""
Unified Agent Workflow for LangGraph Functional API.

This is the main entrypoint for all agent interactions. It handles:
- Supervisor routing (greeter, search, scouting)
- Scouting flow with 2 HITL gates (plan approval, player approval)
- Simple greeting responses
- RAG-based search with LLM synthesis

Architecture:
    Node 0: Supervisor Routing
        ├── greeter → LLM greeting → return AgentResponse
        ├── search → RAG + LLM → return AgentResponse
        └── scouting → continue to Node 1
    Node 1: Intake (scouting)
    Node 2: Draft Plan (scouting)
    HITL Gate A: Plan Approval
    Nodes 3-7: Build/Retrieve/Extract/Compose/Preview
    HITL Gate B: Player Approval
    Nodes 8-9: Write/Respond
"""

from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
from queue import Full as QueueFull
from langgraph.func import entrypoint, task
from langgraph.types import interrupt, Command
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from app.agents.functional.models import AgentResponse, RoutingDecision, ToolResult
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
from app.agents.functional.tasks.supervisor import route_to_agent
from app.agents.functional.tasks.agent import execute_agent, refine_with_tool_results
from app.agents.functional.tasks.tools import execute_tools
from app.agents.functional.workflow import (
    get_sync_checkpointer,
    get_event_queue_from_config,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# Maximum edit iterations to prevent infinite loops
MAX_EDIT_ITERATIONS = 5


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

    # Routing info
    routed_agent: str = ""
    routing_confidence: float = 0.0

    # Scouting-specific state (Node 1 output)
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
        f"[WORKFLOW] [HITL-A] Requesting plan approval for {player_name}, "
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
        f"[WORKFLOW] [HITL-A] Plan approval decision received, "
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
        f"[WORKFLOW] [HITL-B] Requesting player approval for "
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
    logger.info(f"[WORKFLOW] [HITL-B] Player approval decision: action={action}")

    return decision or {"action": "approve"}


def request_tool_approval(
    tool_calls: List[Dict[str, Any]],
    session_id: int,
) -> Dict[str, Any]:
    """
    Request tool approval via HITL interrupt.

    Args:
        tool_calls: List of tool calls to approve
        session_id: Session ID for correlation

    Returns:
        Decision dict with approvals per tool
    """
    logger.info(
        f"[WORKFLOW] [HITL-TOOL] Requesting tool approval for "
        f"{len(tool_calls)} tools, session={session_id}"
    )

    decision = interrupt(
        {
            "type": "tool_approval",
            "session_id": session_id,
            "tool_calls": tool_calls,
        }
    )

    logger.info(f"[WORKFLOW] [HITL-TOOL] Tool approval decision received")

    return decision or {"approvals": {}}


def tool_requires_approval(tool_name: str) -> bool:
    """Check if a tool requires human approval before execution."""
    # Tools that can run without approval
    AUTO_APPROVE_TOOLS = {
        "rag_retrieval_tool",  # RAG is safe - just reads user's own docs
    }
    return tool_name not in AUTO_APPROVE_TOOLS


# ============================================================================
# ROUTE HANDLERS
# ============================================================================


def handle_greeter_route(
    state: WorkflowState,
    messages: List,
    config: Optional[RunnableConfig],
) -> AgentResponse:
    """
    Handle greeter route - friendly LLM greeting response.

    Args:
        state: Workflow state
        messages: Conversation history
        config: Runtime config

    Returns:
        AgentResponse with greeting
    """
    logger.info(f"[WORKFLOW] Handling greeter route for user={state.user_id}")

    emit_workflow_event(
        config,
        "agent_start",
        {"agent_name": "greeter"},
    )

    # Execute greeter agent
    response = execute_agent(
        agent_name="greeter",
        messages=messages,
        user_id=state.user_id,
        config=config,
        api_key=state.api_key,
    ).result()

    # Handle tool calls if greeter wants to use RAG
    if response.tool_calls:
        response = _handle_tool_execution(
            response=response,
            messages=messages,
            state=state,
            config=config,
        )

    logger.info(f"[WORKFLOW] Greeter response: {len(response.reply)} chars")
    return response


def handle_search_route(
    state: WorkflowState,
    messages: List,
    config: Optional[RunnableConfig],
) -> AgentResponse:
    """
    Handle search route - RAG retrieval + LLM synthesis.

    Args:
        state: Workflow state
        messages: Conversation history
        config: Runtime config

    Returns:
        AgentResponse with search results
    """
    logger.info(f"[WORKFLOW] Handling search route for user={state.user_id}")

    emit_workflow_event(
        config,
        "agent_start",
        {"agent_name": "search"},
    )

    # Check if user has documents
    if not check_user_has_documents(state.user_id):
        logger.warning(f"[WORKFLOW] User {state.user_id} has no documents for search")
        return AgentResponse(
            type="answer",
            reply=(
                "I don't have any documents to search through yet. "
                "Please upload some documents first, then I can help you search and find information in them."
            ),
            agent_name="search",
        )

    # Execute search agent
    response = execute_agent(
        agent_name="search",
        messages=messages,
        user_id=state.user_id,
        config=config,
        api_key=state.api_key,
    ).result()

    # Handle tool calls (RAG retrieval)
    if response.tool_calls:
        response = _handle_tool_execution(
            response=response,
            messages=messages,
            state=state,
            config=config,
        )

    logger.info(f"[WORKFLOW] Search response: {len(response.reply)} chars")
    return response


def _handle_tool_execution(
    response: AgentResponse,
    messages: List,
    state: WorkflowState,
    config: Optional[RunnableConfig],
) -> AgentResponse:
    """
    Handle tool execution with optional approval.

    Args:
        response: Agent response with tool_calls
        messages: Conversation history
        state: Workflow state
        config: Runtime config

    Returns:
        AgentResponse after tool execution and refinement
    """
    tool_calls = response.tool_calls
    if not tool_calls:
        return response

    logger.info(f"[WORKFLOW] Processing {len(tool_calls)} tool calls")

    # Partition tools into auto-approve and needs-approval
    auto_tools = []
    approval_tools = []

    for tc in tool_calls:
        tool_name = tc.get("name") or tc.get("tool", "")
        if tool_requires_approval(tool_name):
            approval_tools.append(tc)
        else:
            auto_tools.append(tc)

    # Request approval for tools that need it
    approved_tools = auto_tools.copy()

    if approval_tools:
        emit_workflow_event(
            config,
            "tool_approval_required",
            {"tool_calls": approval_tools},
        )

        decision = request_tool_approval(approval_tools, state.session_id)
        approvals = decision.get("approvals", {})

        for tc in approval_tools:
            tool_id = tc.get("id", "")
            if approvals.get(tool_id, {}).get("approved", False):
                # Apply any edited args
                if "args" in approvals.get(tool_id, {}):
                    tc["args"] = approvals[tool_id]["args"]
                approved_tools.append(tc)
            else:
                logger.info(f"[WORKFLOW] Tool {tc.get('name')} rejected by user")

    if not approved_tools:
        return AgentResponse(
            type="answer",
            reply="I was going to use some tools, but they were not approved. How else can I help you?",
            agent_name=response.agent_name,
        )

    # Execute approved tools
    tool_results = execute_tools(
        tool_calls=approved_tools,
        agent_name=response.agent_name,
        user_id=state.user_id,
        api_key=state.api_key,
        config=config,
    ).result()

    # Build messages with tool results
    from langchain_core.messages import AIMessage as AIM, ToolMessage as TM

    updated_messages = list(messages)

    # Add AI message with tool calls
    updated_messages.append(
        AIM(
            content=response.reply or "",
            tool_calls=approved_tools,
        )
    )

    # Add tool result messages
    for result in tool_results:
        updated_messages.append(
            TM(
                content=result.output or result.error or "",
                tool_call_id=result.tool_call_id,
                name=result.tool,
            )
        )

    # Refine with tool results
    refined = refine_with_tool_results(
        agent_name=response.agent_name,
        messages=updated_messages,
        tool_results=tool_results,
        user_id=state.user_id,
        config=config,
        api_key=state.api_key,
    ).result()

    return refined


# ============================================================================
# SCOUTING FLOW
# ============================================================================


def run_scouting_flow(
    state: WorkflowState,
    config: Optional[RunnableConfig],
) -> AgentResponse:
    """
    Run the full scouting workflow (Nodes 1-9).

    Args:
        state: Workflow state with user info
        config: Runtime config

    Returns:
        AgentResponse with scouting report
    """
    logger.info(
        f"[WORKFLOW] Starting scouting flow for user={state.user_id}, "
        f"session={state.session_id}"
    )

    emit_workflow_event(
        config,
        "agent_start",
        {"agent_name": "scouting"},
    )

    # Pre-check: User must have documents
    if not check_user_has_documents(state.user_id):
        logger.warning(f"[WORKFLOW] User {state.user_id} has no documents")
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
    emit_workflow_event(
        config,
        "plan_step_progress",
        {
            "step_index": 0,
            "total_steps": 0,
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

        emit_workflow_event(
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
            f"[WORKFLOW] Node 1 complete: player={state.player_name}, "
            f"sport={state.sport_guess}"
        )
    except ValueError as e:
        return AgentResponse(
            type="answer",
            reply=str(e),
            agent_name="scouting",
            clarification=str(e),
        )

    # =========================================================================
    # Node 2: Draft Plan (Step 2)
    # =========================================================================
    emit_workflow_event(
        config,
        "plan_step_progress",
        {
            "step_index": 1,
            "total_steps": 0,
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

    emit_workflow_event(
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

    emit_workflow_event(
        config,
        "plan_proposal",
        {
            "player_name": state.player_name,
            "sport_guess": state.sport_guess,
            "plan_steps": state.plan_steps,
            "query_hints": state.query_hints,
        },
    )

    logger.info(f"[WORKFLOW] Node 2 complete: {len(state.plan_steps)} steps")

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
        logger.info("[WORKFLOW] Plan updated from user edits")

    # =========================================================================
    # Edit Loop: Nodes 3-7 with potential re-runs
    # =========================================================================
    total_steps = len(state.plan_steps)
    action = "approve"  # Default action for loop control

    while state.edit_iterations < MAX_EDIT_ITERATIONS:
        state.edit_iterations += 1

        # ---------------------------------------------------------------------
        # Node 3: Build Queries (Step 3)
        # ---------------------------------------------------------------------
        current_step = 2
        emit_workflow_event(
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

        emit_workflow_event(
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

        logger.info(f"[WORKFLOW] Node 3 complete: {len(state.queries)} queries")

        # ---------------------------------------------------------------------
        # Node 4: Retrieve Evidence (Step 4)
        # ---------------------------------------------------------------------
        current_step = 3
        emit_workflow_event(
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

        emit_workflow_event(
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
            f"[WORKFLOW] Node 4 complete: {len(state.evidence_pack.chunks)} chunks, "
            f"confidence={state.evidence_pack.confidence}"
        )

        # ---------------------------------------------------------------------
        # Node 5: Extract Fields (Step 5)
        # ---------------------------------------------------------------------
        current_step = 4
        emit_workflow_event(
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

        emit_workflow_event(
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

        emit_workflow_event(
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
            f"[WORKFLOW] Node 5 complete: {len(state.raw_facts)} facts extracted"
        )

        # Inner loop for compose-only re-runs
        compose_feedback = None
        while True:
            # -----------------------------------------------------------------
            # Node 6: Compose Report (Step 6)
            # -----------------------------------------------------------------
            current_step = 5
            emit_workflow_event(
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

            emit_workflow_event(
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
                f"[WORKFLOW] Node 6 complete: "
                f"{len(state.report_draft.report_text)} chars"
            )

            # -----------------------------------------------------------------
            # Node 7: Prepare Preview (Step 7)
            # -----------------------------------------------------------------
            current_step = 6
            emit_workflow_event(
                config,
                "plan_step_progress",
                {
                    "step_index": current_step,
                    "total_steps": total_steps,
                    "status": "in_progress",
                    "step_name": "Preparing preview for approval",
                },
            )

            source_doc_ids = list(
                set(chunk.doc_id for chunk in state.evidence_pack.chunks)
            )

            state.preview = prepare_preview(
                report_draft=state.report_draft,
                source_doc_ids=source_doc_ids,
            ).result()

            emit_workflow_event(
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

            logger.info("[WORKFLOW] Node 7 complete: preview ready")

            preview_payload = {
                "player_fields": state.preview.player.model_dump(exclude_none=True),
                "report_summary": state.report_draft.report_summary,
                "report_text": state.report_draft.report_text,
                "db_payload_preview": state.preview.model_dump(exclude_none=True),
            }
            emit_workflow_event(config, "player_preview", preview_payload)

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
                        f"[WORKFLOW] Node 8 complete: player={state.player_record_id}"
                    )
                except Exception as e:
                    logger.error(f"[WORKFLOW] Node 8 failed: {e}")
                    state.saved = False

                break

            elif action == "reject":
                state.saved = False
                logger.info("[WORKFLOW] User rejected save, returning report only")
                break

            elif action == "edit_wording":
                compose_feedback = feedback
                logger.info("[WORKFLOW] Re-running compose with wording feedback")
                continue

            elif action == "edit_content":
                if feedback:
                    state.query_hints.append(feedback)
                logger.info(
                    "[WORKFLOW] Re-running from build_queries with content feedback"
                )
                break

            else:
                logger.warning(
                    f"[WORKFLOW] Unknown action: {action}, defaulting to approve"
                )
                state.saved = False
                break

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
        f"[WORKFLOW] Scouting complete: saved={state.saved}, "
        f"iterations={state.edit_iterations}"
    )

    return response


# ============================================================================
# MAIN WORKFLOW ENTRYPOINT
# ============================================================================

# Get checkpointer for workflow
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

    Handles all agent types through supervisor routing:
    - greeter: Friendly LLM greeting
    - search: RAG + LLM document search
    - scouting: Full 9-node scouting flow with HITL gates

    Request can be:
        - Dict with message, user_id, session_id, api_key, run_id
        - AgentRequest Pydantic model (will be converted to dict)
        - Command for resume from interrupt

    When resuming from interrupt, LangGraph handles Command internally.

    Args:
        request: Request dict or Command for resume

    Returns:
        AgentResponse with agent's reply
    """
    # Handle Command for resume (LangGraph handles checkpoint restore)
    if isinstance(request, Command):
        logger.info("[WORKFLOW] Resuming from interrupt via Command")
        resume_payload = (
            request.resume
            if hasattr(request, "resume") and isinstance(request.resume, dict)
            else {}
        )
        session_id = resume_payload.get("session_id")
        if not session_id:
            logger.error("[WORKFLOW] Resume missing session_id")
            return AgentResponse(
                type="answer",
                reply="Error: Resume requires session context",
                agent_name="system",
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

    # Handle AgentRequest Pydantic model - convert to dict for uniform access
    if hasattr(request, "model_dump"):
        # Pydantic v2
        request_dict = request.model_dump()
    elif hasattr(request, "dict"):
        # Pydantic v1
        request_dict = request.dict()
    elif isinstance(request, dict):
        request_dict = request
    else:
        # Fallback - try to access attributes directly
        request_dict = {
            "user_id": getattr(request, "user_id", 0),
            "session_id": getattr(request, "session_id", 0),
            "message": getattr(request, "query", "") or getattr(request, "message", ""),
            "api_key": getattr(request, "openai_api_key", "") or "",
            "run_id": getattr(request, "run_id", None),
        }

    # Map 'query' to 'message' if present (AgentRequest uses 'query')
    if "query" in request_dict and "message" not in request_dict:
        request_dict["message"] = request_dict["query"]
    elif "query" in request_dict and not request_dict.get("message"):
        request_dict["message"] = request_dict["query"]

    # Map 'openai_api_key' to 'api_key' if present
    if "openai_api_key" in request_dict and "api_key" not in request_dict:
        request_dict["api_key"] = request_dict["openai_api_key"] or ""
    elif "openai_api_key" in request_dict and not request_dict.get("api_key"):
        request_dict["api_key"] = request_dict["openai_api_key"] or ""

    # Extract request parameters
    state = WorkflowState(
        user_id=request_dict.get("user_id", 0),
        session_id=request_dict.get("session_id", 0),
        message=request_dict.get("message", ""),
        api_key=request_dict.get("api_key", ""),
        run_id=request_dict.get("run_id"),
    )

    logger.info(
        f"[WORKFLOW] Starting workflow for user={state.user_id}, "
        f"session={state.session_id}, message_preview={state.message[:50]}..."
    )

    # =========================================================================
    # Node 0: Supervisor Routing
    # =========================================================================
    emit_workflow_event(
        config,
        "plan_step_progress",
        {
            "step_index": -1,
            "total_steps": 0,
            "status": "in_progress",
            "step_name": "Analyzing request",
        },
    )

    # Build messages for routing
    messages = [HumanMessage(content=state.message)]

    # Route to appropriate agent
    routing: RoutingDecision = route_to_agent(
        messages=messages,
        config=config,
        api_key=state.api_key,
    ).result()

    state.routed_agent = routing.agent
    state.routing_confidence = routing.confidence or 0.0

    logger.info(
        f"[WORKFLOW] Supervisor routed to: {routing.agent} "
        f"(confidence={state.routing_confidence:.2f})"
    )

    emit_workflow_event(
        config,
        "plan_step_progress",
        {
            "step_index": -1,
            "total_steps": 0,
            "status": "completed",
            "step_name": "Analyzing request",
            "result": f"Routed to {routing.agent}",
        },
    )

    # Handle clarification request
    if routing.require_clarification and routing.clarification_question:
        return AgentResponse(
            type="answer",
            reply=routing.clarification_question,
            clarification=routing.clarification_question,
            agent_name="supervisor",
        )

    # =========================================================================
    # Route to appropriate handler
    # =========================================================================
    if routing.agent == "greeter":
        return handle_greeter_route(state, messages, config)

    elif routing.agent == "search":
        return handle_search_route(state, messages, config)

    elif routing.agent == "scouting":
        return run_scouting_flow(state, config)

    else:
        # Fallback to greeter for unknown agents
        logger.warning(
            f"[WORKFLOW] Unknown agent {routing.agent}, falling back to greeter"
        )
        return handle_greeter_route(state, messages, config)


# Legacy alias for backward compatibility
scouting_workflow = agent_workflow
