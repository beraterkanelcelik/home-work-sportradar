"""
State definitions for the StateGraph workflow.

Uses TypedDict for LangGraph compatibility while providing validation
helpers that use the Pydantic models from models.py.
"""

from typing import TypedDict, Annotated, Optional, List, Dict, Any
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

from .models import (
    Task as TaskModel,
    TaskStatus,
    ApprovalPayload,
    PlayerData,
    WorkflowInput,
)


class TaskDict(TypedDict):
    """TypedDict version of Task for LangGraph state compatibility."""
    id: str
    description: str
    status: str  # "pending" | "in_progress" | "completed"
    result: Optional[str]


# Alias for backward compatibility
Task = TaskDict


class PlanStepDict(TypedDict):
    """TypedDict for a single plan step."""
    action: str
    tool: Optional[str]
    query: Optional[str]
    agent: str
    description: str
    status: str  # "pending" | "in_progress" | "completed" | "error"


class AgentState(TypedDict):
    """
    State that flows through the graph.

    Note: Uses TypedDict for LangGraph compatibility. For validation,
    use the helper functions validate_* below.
    """

    # Core identifiers
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: int
    session_id: int
    api_key: str
    model: str  # Selected model from chat UI (e.g., "gpt-4o", "gpt-4o-mini")

    # Agent's dynamic task list
    tasks: List[TaskDict]

    # Accumulated context from tools
    rag_context: str
    player_data: Optional[Dict[str, Any]]

    # Composed report data (from compose_report_node)
    report_text: Optional[str]  # Full report narrative
    report_summary: Optional[List[str]]  # Key findings bullet points

    # HITL control
    needs_user_approval: bool
    approval_type: Optional[str]  # "save_player" | "plan_approval" | None
    approval_payload: Optional[Dict[str, Any]]

    # Output
    final_response: Optional[str]

    # Plan tracking (for scouting workflow)
    plan: Optional[List[Dict[str, Any]]]  # The execution plan
    plan_approved: bool  # Whether plan has been approved
    current_step_index: int  # Which step is executing (0-based)
    player_name: Optional[str]  # Extracted player name from request
    sport_guess: Optional[str]  # Guessed sport type


# =============================================================================
# Validation Helpers
# =============================================================================

def validate_task(task_dict: Dict[str, Any]) -> TaskModel:
    """
    Validate a task dictionary using Pydantic model.

    Args:
        task_dict: Raw task dictionary

    Returns:
        Validated TaskModel instance

    Raises:
        ValidationError: If task data is invalid
    """
    return TaskModel(**task_dict)


def validate_tasks(tasks: List[Dict[str, Any]]) -> List[TaskModel]:
    """
    Validate a list of tasks.

    Args:
        tasks: List of raw task dictionaries

    Returns:
        List of validated TaskModel instances
    """
    return [validate_task(t) for t in tasks]


def create_task(
    task_id: str,
    description: str,
    status: str = "pending",
    result: Optional[str] = None
) -> TaskDict:
    """
    Create a validated task and return as TypedDict for state compatibility.

    Args:
        task_id: Unique task identifier
        description: Task description
        status: Task status (pending, in_progress, completed)
        result: Optional task result

    Returns:
        Validated task as TypedDict
    """
    # Validate using Pydantic model
    validated = TaskModel(
        id=task_id,
        description=description,
        status=TaskStatus(status),
        result=result
    )
    # Return as dict for TypedDict compatibility
    return {
        "id": validated.id,
        "description": validated.description,
        "status": validated.status,
        "result": validated.result,
    }


def validate_approval_payload(payload: Dict[str, Any]) -> ApprovalPayload:
    """
    Validate an approval payload dictionary.

    Args:
        payload: Raw approval payload dictionary

    Returns:
        Validated ApprovalPayload instance
    """
    return ApprovalPayload(**payload)


def validate_player_data(player_dict: Dict[str, Any]) -> PlayerData:
    """
    Validate player data dictionary.

    Args:
        player_dict: Raw player data dictionary

    Returns:
        Validated PlayerData instance
    """
    return PlayerData(**player_dict)


def validate_workflow_input(input_dict: Dict[str, Any]) -> WorkflowInput:
    """
    Validate workflow input dictionary.

    Args:
        input_dict: Raw workflow input dictionary

    Returns:
        Validated WorkflowInput instance

    Raises:
        ValidationError: If input data is invalid
    """
    return WorkflowInput(**input_dict)


def create_initial_state(
    message: str,
    user_id: int,
    session_id: int,
    api_key: str,
    run_id: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a validated initial state for the workflow.

    Args:
        message: User's message
        user_id: User ID
        session_id: Session ID
        api_key: OpenAI API key
        run_id: Optional run ID for tracking
        model: Optional model name (defaults to "gpt-4o-mini")

    Returns:
        Initial state dictionary ready for workflow

    Raises:
        ValidationError: If input parameters are invalid
    """
    from langchain_core.messages import HumanMessage

    # Validate input
    validated_input = WorkflowInput(
        message=message,
        user_id=user_id,
        session_id=session_id,
        api_key=api_key,
        run_id=run_id,
    )

    # Default model if not specified
    selected_model = model or "gpt-4o-mini"

    return {
        "messages": [HumanMessage(content=validated_input.message)],
        "user_id": validated_input.user_id,
        "session_id": validated_input.session_id,
        "api_key": validated_input.api_key,
        "model": selected_model,
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
