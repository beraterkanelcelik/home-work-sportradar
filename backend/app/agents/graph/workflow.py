"""
StateGraph workflow for the agent.

This module defines the workflow graph and provides functions to run it
with proper validation using Pydantic models.
"""

from typing import Optional, Union, Dict, Any, AsyncIterator
from pydantic import ValidationError
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from threading import Thread
from queue import Queue as ThreadQueue, Empty

from .state import AgentState, create_initial_state, validate_workflow_input
from .nodes import agent_node, tool_node, approval_node, planner_node, plan_approval_node, compose_report_node
from .models import WorkflowInput, ResumePayload, ApprovalType
from app.core.logging import get_logger

logger = get_logger(__name__)


def route_after_planner(state: AgentState) -> str:
    """Determine next node after planner."""

    # If plan needs approval
    if state.get("needs_user_approval") and state.get("approval_type") == ApprovalType.PLAN_APPROVAL.value:
        return "plan_approval"

    # No plan needed or already approved, go to agent
    return "agent"


def route_after_agent(state: AgentState) -> str:
    """Determine next node after agent."""

    last_message = state["messages"][-1]

    # If agent called tools
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    # If waiting for approval (save_player)
    if state.get("needs_user_approval"):
        return "approval"

    # Agent finished
    return END


def route_after_tools(state: AgentState) -> str:
    """Determine next node after tools."""

    # If save_player tool needs approval, go to compose_report first
    if state.get("needs_user_approval") and state.get("approval_type") == ApprovalType.SAVE_PLAYER.value:
        return "compose_report"

    # Otherwise back to agent
    return "agent"


def create_workflow(checkpointer: Optional[PostgresSaver] = None):
    """Create the agent workflow graph.

    Flow:
    - START → planner (generates plan for scouting requests)
    - planner → plan_approval (HITL for plan approval) OR agent (skip for simple queries)
    - plan_approval → agent (execute approved plan)
    - agent → tools → agent (loop until done)
    - tools → compose_report (when save_player is called) → approval (HITL) → agent
    - agent → END
    """

    # Build graph
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("planner", planner_node)
    graph.add_node("plan_approval", plan_approval_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("compose_report", compose_report_node)  # New: dedicated report composition
    graph.add_node("approval", approval_node)

    # Add edges
    # Start with planner to detect scouting requests
    graph.add_edge(START, "planner")

    # Planner routes to plan_approval (for scouting) or agent (for simple queries)
    graph.add_conditional_edges("planner", route_after_planner)

    # After plan is approved, go to agent to execute
    graph.add_edge("plan_approval", "agent")

    # Agent routes to tools, approval, or END
    graph.add_conditional_edges("agent", route_after_agent)

    # After tools, back to agent (or to compose_report if save_player)
    graph.add_conditional_edges("tools", route_after_tools)

    # After compose_report, go to approval for user confirmation
    graph.add_edge("compose_report", "approval")

    # After save_player approval, back to agent
    graph.add_edge("approval", "agent")

    # Compile - nodes use interrupt() directly for HITL pauses
    return graph.compile(
        checkpointer=checkpointer,
    )


# Singleton workflow instance
_workflow = None
_checkpointer = None


def get_workflow():
    """Get or create workflow instance."""
    global _workflow, _checkpointer

    if _workflow is None:
        from app.agents.checkpoint import get_sync_checkpointer
        _checkpointer = get_sync_checkpointer()
        _workflow = create_workflow(_checkpointer)
        logger.info("[WORKFLOW] Created StateGraph workflow")

    return _workflow


def run_workflow(
    request: Union[Dict[str, Any], Command],
    config: Dict[str, Any],
) -> AgentState:
    """
    Run the workflow with a request.

    Args:
        request: Either a dict with workflow input or a Command for resume
        config: Workflow configuration including thread_id and event_queue

    Returns:
        Final AgentState after workflow execution

    Raises:
        ValidationError: If request data is invalid
    """
    workflow = get_workflow()

    # Handle resume via Command
    if isinstance(request, Command):
        # Validate resume payload if present
        if hasattr(request, "resume") and isinstance(request.resume, dict):
            try:
                validated_resume = ResumePayload(**request.resume)
                logger.debug(f"[WORKFLOW] Resume payload validated: approved={validated_resume.approved}")
            except ValidationError as e:
                logger.warning(f"[WORKFLOW] Resume payload validation error: {e}")
                # Continue anyway, the resume might still work

        return workflow.invoke(request, config)

    # Validate and create initial state
    try:
        validated_input = validate_workflow_input(request)
        logger.debug(f"[WORKFLOW] Input validated: session_id={validated_input.session_id}")

        initial_state = create_initial_state(
            message=validated_input.message,
            user_id=validated_input.user_id,
            session_id=validated_input.session_id,
            api_key=validated_input.api_key,
            run_id=validated_input.run_id,
        )
    except ValidationError as e:
        logger.error(f"[WORKFLOW] Input validation error: {e}")
        # Fall back to unvalidated state creation for backward compatibility
        from langchain_core.messages import HumanMessage

        initial_state = {
            "messages": [HumanMessage(content=request.get("message", ""))],
            "user_id": request.get("user_id", 0),
            "session_id": request.get("session_id", 0),
            "api_key": request.get("api_key", ""),
            "tasks": [],
            "rag_context": "",
            "player_data": None,
            "report_text": None,
            "report_summary": None,
            "needs_user_approval": False,
            "approval_type": None,
            "approval_payload": None,
            "final_response": None,
            # Plan tracking
            "plan": None,
            "plan_approved": False,
            "current_step_index": 0,
            "player_name": None,
            "sport_guess": None,
        }

    return workflow.invoke(initial_state, config)


async def stategraph_workflow_events(
    request: Union[Dict[str, Any], Command],
    session_id: Optional[int] = None,
    user_id: Optional[int] = None,
    trace_id: Optional[str] = None,
    api_key: Optional[str] = None,
    langfuse_public_key: Optional[str] = None,
    langfuse_secret_key: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Async event-emitting wrapper around the StateGraph workflow.
    Yields structured events during workflow execution.

    Uses Pydantic models for validation of inputs and events.

    Args:
        request: Dict with message, user_id, session_id, api_key
                 Or Command(resume=...) when resuming from interrupt.
        session_id: Optional session_id (required when request is Command)
        user_id: Optional user_id (required when request is Command)
        trace_id: Optional trace_id for Langfuse observability
        api_key: Optional OpenAI API key
        langfuse_public_key: Optional per-user Langfuse public key
        langfuse_secret_key: Optional per-user Langfuse secret key

    Yields:
        Event dictionaries with type and data
    """
    import asyncio
    from app.agents.graph.streaming import EventCallbackHandler
    from app.agents.graph.models import AgentResponse, ErrorEvent

    # Extract IDs from request if not provided
    if isinstance(request, dict):
        session_id = session_id or request.get("session_id")
        user_id = user_id or request.get("user_id")
        api_key = api_key or request.get("api_key")

        # Validate request dict (non-blocking, just log warnings)
        try:
            validated = WorkflowInput(
                message=request.get("message", ""),
                user_id=request.get("user_id", 1),
                session_id=request.get("session_id", 1),
                api_key=request.get("api_key", ""),
                run_id=request.get("run_id"),
            )
            logger.debug(f"[STATEGRAPH] Request validated: session_id={validated.session_id}")
        except ValidationError as e:
            logger.warning(f"[STATEGRAPH] Request validation warning: {e}")
            # Don't fail, continue with unvalidated request

    # Status messages for EventCallbackHandler
    status_messages = {
        "planner_node": "Generating plan...",
        "planner": "Generating plan...",
        "plan_approval_node": "Awaiting plan approval...",
        "agent_node": "Processing with agent...",
        "tool_node": "Executing tools...",
        "approval_node": "Awaiting approval...",
        "search_documents": "Searching documents...",
        "save_player_report": "Preparing to save report...",
    }

    # Create thread-safe queue for events from callbacks
    MAX_QUEUE_SIZE = 10000
    event_queue = ThreadQueue(maxsize=MAX_QUEUE_SIZE)

    # Create event callback handler for streaming
    callback_handler = EventCallbackHandler(event_queue, status_messages)

    # Build thread_id for checkpointing
    # IMPORTANT: Use session-only thread_id to enable conversational memory!
    # LangGraph's PostgresSaver will load previous checkpoint (including messages)
    # and merge with new initial_state via the add_messages reducer.
    #
    # Flow:
    # 1. New message → thread_id = "chat_session_51" → loads previous messages from checkpoint
    # 2. HITL interrupt → checkpoint saved with same thread_id
    # 3. Resume → same thread_id → loads interrupted state, Command.resume continues execution
    #
    # The run_id is only used for logging/tracking, NOT for checkpoint identification.
    run_id = None
    if isinstance(request, dict):
        run_id = request.get("run_id")
    elif isinstance(request, Command) and hasattr(request, "resume") and isinstance(request.resume, dict):
        run_id = request.resume.get("run_id")

    # Always use session-based thread_id for checkpoint continuity
    if session_id:
        thread_id = f"chat_session_{session_id}"
    elif user_id:
        thread_id = f"user_{user_id}"
    else:
        thread_id = "default"

    logger.info(f"[STATEGRAPH] Using thread_id={thread_id} (session={session_id}, run_id={run_id} for tracking)")

    # Build config with Langfuse credentials for node-level tracing
    # NOTE: We don't include callback_handler in "callbacks" because each node (agent_node, planner_node)
    # creates its own EventCallbackHandler from the event_queue in configurable.
    # Adding it to "callbacks" would cause double token emission (both config callbacks and LLM callbacks fire).
    # Instead, we pass event_queue and status_messages via configurable for nodes to use.
    config = {
        "configurable": {
            "thread_id": thread_id,
            "event_queue": event_queue,
            "status_messages": status_messages,  # For EventCallbackHandler in nodes
            # Langfuse credentials for LLM call tracing
            "trace_id": trace_id,
            "session_id": session_id,  # For Langfuse session-level grouping
            "langfuse_public_key": langfuse_public_key,
            "langfuse_secret_key": langfuse_secret_key,
        },
    }

    # Track final response and interrupt
    final_response_holder = [None]
    interrupt_holder = [None]
    exception_holder = [None]

    def run_workflow_thread():
        """Run workflow in background thread."""
        try:
            workflow = get_workflow()

            # Build initial state or use Command for resume
            if isinstance(request, Command):
                # Resume from interrupt
                for chunk in workflow.stream(request, config=config):
                    logger.debug(f"[STATEGRAPH_CHUNK] Resume chunk keys={list(chunk.keys()) if isinstance(chunk, dict) else 'N/A'}")

                    if isinstance(chunk, dict) and "__interrupt__" in chunk:
                        interrupt_holder[0] = chunk["__interrupt__"]
                        logger.info(f"[STATEGRAPH] Interrupt detected during resume session={session_id}")
                        break

                    # Extract final response from last message
                    if isinstance(chunk, dict):
                        for node_name, node_output in chunk.items():
                            if node_name == "agent" and isinstance(node_output, dict):
                                messages = node_output.get("messages", [])
                                if messages and not getattr(messages[-1], "tool_calls", None):
                                    # Agent produced final response
                                    content = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
                                    final_response_holder[0] = AgentResponse(
                                        type="answer",
                                        reply=content,
                                        agent_name="stategraph_agent",
                                    )
            else:
                # New request - build initial state
                from langchain_core.messages import HumanMessage

                # Get model from request (selected by user in chat UI)
                selected_model = request.get("model", "gpt-4o-mini")
                max_tokens = request.get("max_tokens")  # Optional: limit response tokens (for benchmarking)

                initial_state = {
                    "messages": [HumanMessage(content=request.get("message", ""))],
                    "user_id": request.get("user_id", 0),
                    "session_id": request.get("session_id", 0),
                    "api_key": request.get("api_key", ""),
                    "model": selected_model,
                    "max_tokens": max_tokens,
                    "tasks": [],
                    "rag_context": "",
                    "player_data": None,
                    "report_text": None,
                    "report_summary": None,
                    "needs_user_approval": False,
                    "approval_type": None,
                    "approval_payload": None,
                    "final_response": None,
                    # Plan tracking
                    "plan": None,
                    "plan_approved": False,
                    "current_step_index": 0,
                    "player_name": None,
                    "sport_guess": None,
                }

                for chunk in workflow.stream(initial_state, config=config):
                    logger.debug(f"[STATEGRAPH_CHUNK] Chunk keys={list(chunk.keys()) if isinstance(chunk, dict) else 'N/A'}")

                    if isinstance(chunk, dict) and "__interrupt__" in chunk:
                        interrupt_holder[0] = chunk["__interrupt__"]
                        logger.info(f"[STATEGRAPH] Interrupt detected session={session_id}")
                        break

                    # Extract final response from agent node output
                    if isinstance(chunk, dict):
                        for node_name, node_output in chunk.items():
                            if node_name == "agent" and isinstance(node_output, dict):
                                messages = node_output.get("messages", [])
                                if messages and not getattr(messages[-1], "tool_calls", None):
                                    content = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
                                    final_response_holder[0] = AgentResponse(
                                        type="answer",
                                        reply=content,
                                        agent_name="stategraph_agent",
                                    )

        except Exception as e:
            logger.error(f"[STATEGRAPH] Error in workflow: {e}", exc_info=True)
            exception_holder[0] = e

    # Start workflow in background thread
    workflow_thread = Thread(target=run_workflow_thread, daemon=True)
    workflow_thread.start()
    logger.info(f"[STATEGRAPH] Started workflow thread for session={session_id}")

    # Yield events from queue while workflow runs
    workflow_done = False
    timeout_count = 0
    max_timeout = 60000  # 10 minutes (60000 * 0.01s = 600 seconds)
    events_yielded = 0

    while not workflow_done:
        try:
            event = event_queue.get_nowait()
            timeout_count = 0  # Reset timeout on event received
            event_type = event.get("type", "unknown")
            events_yielded += 1

            if event_type != "token":
                logger.debug(f"[STATEGRAPH_EVENT] #{events_yielded} type={event_type}")

            yield event

            if event_type == "final":
                workflow_done = True
                break

        except Empty:
            # Only count timeout when thread is alive
            # If thread is dead, we should exit after draining
            if not workflow_thread.is_alive():
                workflow_done = True
                # Drain remaining events
                try:
                    while True:
                        event = event_queue.get_nowait()
                        yield event
                except Empty:
                    pass
                break

            # Thread is still alive, wait for events
            timeout_count += 1
            if timeout_count >= max_timeout:
                logger.warning(f"[STATEGRAPH] Timeout waiting for events, thread still alive for session={session_id}")
                # Don't exit - wait for thread to finish
                timeout_count = 0  # Reset and keep waiting

            await asyncio.sleep(0.01)

    # Check for interrupt
    if interrupt_holder[0]:
        interrupt_data = interrupt_holder[0]
        logger.debug(f"[STATEGRAPH] Raw interrupt_holder: type={type(interrupt_data)}, value={interrupt_data}")

        if isinstance(interrupt_data, (list, tuple)) and len(interrupt_data) > 0:
            interrupt_value = interrupt_data[0]
            logger.debug(f"[STATEGRAPH] Interrupt value: type={type(interrupt_value)}")
            if hasattr(interrupt_value, "value"):
                interrupt_data = interrupt_value.value
                logger.debug(f"[STATEGRAPH] Extracted interrupt value: {type(interrupt_data)}")

        # Log the interrupt type for debugging
        if isinstance(interrupt_data, dict):
            logger.info(f"[STATEGRAPH] Interrupt payload type={interrupt_data.get('type')} for session={session_id}")

        yield {
            "type": "interrupt",
            "data": interrupt_data,
            "interrupt": interrupt_data,
        }
        logger.info(f"[STATEGRAPH] Yielded interrupt event for session={session_id}")
        return

    # Check for exception
    if exception_holder[0]:
        yield {
            "type": "error",
            "error": str(exception_holder[0]),
        }
        return

    # Emit final response
    if final_response_holder[0]:
        yield {
            "type": "final",
            "response": final_response_holder[0],
        }
        logger.info(f"[STATEGRAPH] Yielded final response for session={session_id}")
