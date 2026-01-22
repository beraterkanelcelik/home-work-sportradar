"""
Event emission utilities for the StateGraph workflow.

Provides functions to emit typed events to the SSE stream.
Uses Pydantic models for event validation where appropriate.
"""

from typing import Optional, Dict, Any, List
from queue import Queue, Full
from pydantic import ValidationError
from langchain_core.runnables import RunnableConfig
from app.core.logging import get_logger
from .models import (
    TasksUpdatedEvent,
    ToolStartEvent,
    ToolCompleteEvent,
    InterruptEvent,
    TokenEvent,
    Task as TaskModel,
    TaskStatus,
)

logger = get_logger(__name__)


def get_event_queue(config: Optional[RunnableConfig]) -> Optional[Queue]:
    """Extract event queue from config."""
    if not config:
        return None
    return config.get("configurable", {}).get("event_queue")


def emit_event(
    config: Optional[RunnableConfig],
    event_type: str,
    data: Dict[str, Any],
) -> None:
    """
    Emit event to SSE stream.

    Args:
        config: RunnableConfig containing event_queue
        event_type: Type of event (token, tasks_updated, etc.)
        data: Event payload data
    """
    queue = get_event_queue(config)
    if not queue:
        return

    try:
        queue.put_nowait({
            "type": event_type,
            "data": data,
        })
        logger.debug(f"[EVENT] Emitted {event_type}")
    except Full:
        logger.debug(f"[EVENT] Queue full, dropped {event_type}")


def emit_tasks_updated(config: RunnableConfig, tasks: List[Dict[str, Any]]) -> None:
    """
    Emit task list update with validation.

    Args:
        config: RunnableConfig containing event_queue
        tasks: List of task dictionaries
    """
    # Validate each task before emitting
    validated_tasks = []
    for t in tasks:
        try:
            validated = TaskModel(
                id=t.get("id", ""),
                description=t.get("description", ""),
                status=TaskStatus(t.get("status", "pending")),
                result=t.get("result"),
            )
            validated_tasks.append({
                "id": validated.id,
                "description": validated.description,
                "status": validated.status,
            })
        except ValidationError as e:
            logger.warning(f"[EVENT] Task validation error: {e}, using raw task")
            validated_tasks.append({
                "id": t.get("id", "unknown"),
                "description": t.get("description", ""),
                "status": t.get("status", "pending"),
            })

    emit_event(config, "tasks_updated", {"tasks": validated_tasks})


def emit_tool_start(config: RunnableConfig, tool_name: str, args: Dict[str, Any]) -> None:
    """
    Emit tool execution start event.

    Args:
        config: RunnableConfig containing event_queue
        tool_name: Name of the tool being executed
        args: Tool arguments (not included in event for security)
    """
    if not tool_name:
        logger.warning("[EVENT] emit_tool_start called with empty tool_name")
        return

    emit_event(config, "tool_start", {
        "tool": tool_name,
        "description": f"Running {tool_name}...",
    })


def emit_tool_complete(config: RunnableConfig, tool_name: str, success: bool) -> None:
    """
    Emit tool execution complete event.

    Args:
        config: RunnableConfig containing event_queue
        tool_name: Name of the tool that completed
        success: Whether the tool execution succeeded
    """
    if not tool_name:
        logger.warning("[EVENT] emit_tool_complete called with empty tool_name")
        return

    emit_event(config, "tool_complete", {
        "tool": tool_name,
        "success": success,
    })


def emit_approval_required(
    config: RunnableConfig,
    approval_type: str,
    payload: Dict[str, Any]
) -> None:
    """
    Emit approval request (HITL) event.

    Args:
        config: RunnableConfig containing event_queue
        approval_type: Type of approval (e.g., "save_player")
        payload: Approval payload data
    """
    if not approval_type:
        logger.warning("[EVENT] emit_approval_required called with empty approval_type")
        return

    if not payload:
        logger.warning("[EVENT] emit_approval_required called with empty payload")
        payload = {}

    # Create interrupt event data
    event_data = {
        "type": approval_type,
        **payload,
    }

    emit_event(config, "interrupt", event_data)


def emit_token(config: RunnableConfig, token: str) -> None:
    """
    Emit streaming token event.

    Args:
        config: RunnableConfig containing event_queue
        token: Token string to emit
    """
    if not token:
        return  # Don't emit empty tokens

    emit_event(config, "token", {"value": token})


def emit_error(config: RunnableConfig, error: str) -> None:
    """
    Emit error event.

    Args:
        config: RunnableConfig containing event_queue
        error: Error message
    """
    if not error:
        error = "Unknown error occurred"

    emit_event(config, "error", {"error": error})


def emit_plan_proposal(
    config: RunnableConfig,
    plan: List[Dict[str, Any]],
    player_name: Optional[str] = None,
    sport_guess: Optional[str] = None,
    session_id: Optional[int] = None,
) -> None:
    """
    Emit plan proposal for HITL approval.

    This is emitted as an 'update' event with type 'plan_proposal' so the
    frontend can display the plan in the PlanPanel and show approve/reject buttons.

    The plan data structure matches what PlanPanel expects:
    - plan.type: 'plan_proposal'
    - plan.plan: Array of steps
    - plan.plan_total: Number of steps

    Args:
        config: RunnableConfig containing event_queue
        plan: List of plan steps, each with action, tool, query, agent, description
        player_name: Optional extracted player name
        sport_guess: Optional guessed sport
        session_id: Optional session ID
    """
    if not plan:
        logger.warning("[EVENT] emit_plan_proposal called with empty plan")
        return

    # Structure the plan data as PlanPanel expects it
    # PlanPanel accesses plan.plan for the steps array
    plan_data = {
        "type": "plan_proposal",
        "plan": plan,  # The steps array
        "plan_index": 0,
        "plan_total": len(plan),
        "player_name": player_name,
        "sport_guess": sport_guess,
        "session_id": session_id,
    }

    emit_event(config, "update", {
        "type": "plan_proposal",
        "plan": plan_data,  # Nested structure so frontend can access plan.plan
    })
    logger.info(f"[EVENT] Emitted plan_proposal with {len(plan)} steps")


def emit_status(
    config: RunnableConfig,
    task: str,
    status: str,
    is_completed: bool = False,
) -> None:
    """
    Emit status update event for frontend display.

    This emits a status message that appears in the chat UI showing
    what the agent is currently doing (e.g., "Generating plan...", "Searching documents...").

    Args:
        config: RunnableConfig containing event_queue
        task: Task identifier (e.g., "planner", "agent", "search_documents")
        status: Status message to display (e.g., "Generating plan...")
        is_completed: Whether the task has completed (changes styling in UI)
    """
    if not task or not status:
        return

    emit_event(config, "update", {
        "task": task,
        "status": status,
        "is_completed": is_completed,
    })
    logger.debug(f"[EVENT] Emitted status: task={task}, status={status}, completed={is_completed}")


def emit_plan_step_progress(
    config: RunnableConfig,
    step_index: int,
    total_steps: int,
    status: str,
    step_name: str,
    result: Optional[str] = None,
) -> None:
    """
    Emit plan step progress update.

    This is emitted as a 'plan_step_progress' event so the frontend can
    update the PlanPanel with the current execution state.

    Args:
        config: RunnableConfig containing event_queue
        step_index: Current step index (0-based)
        total_steps: Total number of steps in the plan
        status: Step status ('pending', 'in_progress', 'completed', 'error')
        step_name: Display name for the step
        result: Optional result text for completed steps
    """
    if total_steps <= 0:
        logger.debug(f"[EVENT] Skipping plan_step_progress with total_steps={total_steps}")
        return

    emit_event(config, "plan_step_progress", {
        "type": "plan_step_progress",
        "step_index": step_index,
        "total_steps": total_steps,
        "status": status,
        "step_name": step_name,
        "result": result,
    })
    logger.debug(f"[EVENT] Emitted plan_step_progress: step {step_index + 1}/{total_steps} = {status}")
