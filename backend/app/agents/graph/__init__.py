"""
LangGraph StateGraph-based agent workflow.

This module implements the main agent workflow using LangGraph's StateGraph API,
with support for tool execution, HITL approval, and streaming events.

All data models use Pydantic for validation and type safety.
"""

from .workflow import get_workflow, run_workflow, create_workflow, stategraph_workflow_events
from .state import (
    AgentState,
    Task,
    TaskDict,
    create_task,
    create_initial_state,
    validate_task,
    validate_tasks,
    validate_approval_payload,
    validate_player_data,
    validate_workflow_input,
)
from .models import (
    # Enums
    TaskStatus,
    ApprovalType,
    EventType,
    # Request/Response
    AgentRequest,
    AgentResponse,
    WorkflowInput,
    ResumePayload,
    # Task models
    Task as TaskModel,
    TaskList,
    # Tool models
    SearchDocumentsInput,
    SearchDocumentsOutput,
    SavePlayerReportInput,
    SavePlayerReportOutput,
    # Player models
    PlayerData,
    # Approval models
    ApprovalPayload,
    # Event models
    TokenEvent,
    TasksUpdatedEvent,
    ToolStartEvent,
    ToolCompleteEvent,
    InterruptEvent,
    UpdateEvent,
    FinalEvent,
    ErrorEvent,
    DoneEvent,
    MessageSavedEvent,
)
from .streaming import EventCallbackHandler

__all__ = [
    # Workflow
    "get_workflow",
    "run_workflow",
    "create_workflow",
    "stategraph_workflow_events",
    # State
    "AgentState",
    "Task",
    "TaskDict",
    # State helpers
    "create_task",
    "create_initial_state",
    "validate_task",
    "validate_tasks",
    "validate_approval_payload",
    "validate_player_data",
    "validate_workflow_input",
    # Enums
    "TaskStatus",
    "ApprovalType",
    "EventType",
    # Request/Response models
    "AgentRequest",
    "AgentResponse",
    "WorkflowInput",
    "ResumePayload",
    # Task models
    "TaskModel",
    "TaskList",
    # Tool models
    "SearchDocumentsInput",
    "SearchDocumentsOutput",
    "SavePlayerReportInput",
    "SavePlayerReportOutput",
    # Player models
    "PlayerData",
    # Approval models
    "ApprovalPayload",
    # Event models
    "TokenEvent",
    "TasksUpdatedEvent",
    "ToolStartEvent",
    "ToolCompleteEvent",
    "InterruptEvent",
    "UpdateEvent",
    "FinalEvent",
    "ErrorEvent",
    "DoneEvent",
    "MessageSavedEvent",
    # Streaming
    "EventCallbackHandler",
]
