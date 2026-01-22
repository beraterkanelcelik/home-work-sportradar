"""
Pydantic models for StateGraph workflow request/response.

This module provides validated data models for the entire agentic flow:
- Request/Response models for workflow input/output
- Task models for agent task tracking
- Tool input/output schemas for validation
- Event models for SSE streaming
- Player data models for scouting reports
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional, Literal
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class TaskStatus(str, Enum):
    """Valid task statuses."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class ApprovalType(str, Enum):
    """Valid approval types for HITL flow."""
    SAVE_PLAYER = "save_player"
    PLAN_APPROVAL = "plan_approval"


class EventType(str, Enum):
    """Valid SSE event types."""
    TOKEN = "token"
    TASKS_UPDATED = "tasks_updated"
    TOOL_START = "tool_start"
    TOOL_COMPLETE = "tool_complete"
    INTERRUPT = "interrupt"
    UPDATE = "update"
    FINAL = "final"
    DONE = "done"
    ERROR = "error"
    MESSAGE_SAVED = "message_saved"


# =============================================================================
# Task Models
# =============================================================================

class Task(BaseModel):
    """A single task in the agent's task list."""

    id: str = Field(..., description="Unique task identifier")
    description: str = Field(..., min_length=1, description="Task description")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current task status")
    result: Optional[str] = Field(default=None, description="Task result/output")

    class Config:
        use_enum_values = True


class TaskList(BaseModel):
    """List of tasks for validation."""

    tasks: List[Task] = Field(default_factory=list)


# =============================================================================
# Tool Input/Output Models
# =============================================================================

class SearchDocumentsInput(BaseModel):
    """Input schema for search_documents tool."""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")

    @field_validator('query')
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Query cannot be empty or whitespace')
        return v.strip()


class SearchDocumentsOutput(BaseModel):
    """Output schema for search_documents tool."""

    results: str = Field(..., description="Formatted search results")
    chunk_count: int = Field(default=0, ge=0, description="Number of chunks found")


class SavePlayerReportInput(BaseModel):
    """Input schema for save_player_report tool."""

    player_name: str = Field(..., min_length=1, max_length=200, description="Player's full name")
    report_summary: str = Field(..., min_length=1, max_length=500, description="Brief report summary")

    @field_validator('player_name')
    @classmethod
    def player_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Player name cannot be empty')
        return v.strip()


class SavePlayerReportOutput(BaseModel):
    """Output schema for save_player_report tool."""

    success: bool = Field(..., description="Whether the save operation succeeded")
    player_id: Optional[str] = Field(default=None, description="Created player ID")
    report_id: Optional[str] = Field(default=None, description="Created report ID")
    message: Optional[str] = Field(default=None, description="Success/error message")
    error: Optional[str] = Field(default=None, description="Error message if failed")


# =============================================================================
# Player Data Models
# =============================================================================

class PlayerData(BaseModel):
    """Structured player data for scouting reports."""

    display_name: str = Field(..., min_length=1, description="Player's display name")
    position: Optional[str] = Field(default=None, description="Playing position")
    team: Optional[str] = Field(default=None, description="Current team")
    nationality: Optional[str] = Field(default=None, description="Player nationality")
    age: Optional[int] = Field(default=None, ge=0, le=100, description="Player age")
    height: Optional[str] = Field(default=None, description="Player height")
    weight: Optional[str] = Field(default=None, description="Player weight")
    preferred_foot: Optional[Literal["left", "right", "both"]] = Field(default=None)
    strengths: Optional[List[str]] = Field(default=None, description="Player strengths")
    weaknesses: Optional[List[str]] = Field(default=None, description="Player weaknesses")
    market_value: Optional[str] = Field(default=None, description="Estimated market value")

    @field_validator('display_name')
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Display name cannot be empty')
        return v.strip()


# =============================================================================
# Approval Payload Models
# =============================================================================

class ApprovalPayload(BaseModel):
    """Payload for HITL approval requests."""

    player_name: str = Field(..., description="Player name for approval display")
    report_summary: Optional[str] = Field(default=None, description="Report summary for preview")
    player_data: Optional[Dict[str, Any]] = Field(default=None, description="Full player data")
    session_id: int = Field(..., description="Chat session ID")
    report_text: Optional[str] = Field(default=None, description="Full report text")


# =============================================================================
# Event Models
# =============================================================================

class TokenEvent(BaseModel):
    """Token streaming event."""

    type: Literal["token"] = "token"
    value: str = Field(..., description="Token value")


class TasksUpdatedEvent(BaseModel):
    """Tasks updated event."""

    type: Literal["tasks_updated"] = "tasks_updated"
    data: Dict[str, Any] = Field(..., description="Tasks data")


class ToolStartEvent(BaseModel):
    """Tool execution start event."""

    type: Literal["tool_start"] = "tool_start"
    data: Dict[str, Any] = Field(..., description="Tool start data including tool name")


class ToolCompleteEvent(BaseModel):
    """Tool execution complete event."""

    type: Literal["tool_complete"] = "tool_complete"
    data: Dict[str, Any] = Field(..., description="Tool completion data")


class InterruptEvent(BaseModel):
    """HITL interrupt event."""

    type: Literal["interrupt"] = "interrupt"
    data: Dict[str, Any] = Field(..., description="Interrupt payload")
    interrupt: Optional[Dict[str, Any]] = Field(default=None, description="Interrupt data (alias)")


class UpdateEvent(BaseModel):
    """Status update event."""

    type: Literal["update"] = "update"
    data: Dict[str, Any] = Field(..., description="Update data")


class FinalEvent(BaseModel):
    """Final response event."""

    type: Literal["final"] = "final"
    response: Optional[Any] = Field(default=None, description="Final response object")


class ErrorEvent(BaseModel):
    """Error event."""

    type: Literal["error"] = "error"
    error: str = Field(..., description="Error message")


class DoneEvent(BaseModel):
    """Workflow done event."""

    type: Literal["done"] = "done"
    data: Dict[str, Any] = Field(default_factory=dict, description="Completion data")


class MessageSavedEvent(BaseModel):
    """Message saved to database event."""

    type: Literal["message_saved"] = "message_saved"
    data: Dict[str, Any] = Field(..., description="Message save data")


# =============================================================================
# Request/Response Models
# =============================================================================

class AgentRequest(BaseModel):
    """Input request for the agent workflow."""

    query: str = Field(..., min_length=1, description="User's query/message")
    session_id: Optional[int] = Field(default=None, ge=1, description="Chat session ID")
    user_id: Optional[int] = Field(default=None, ge=1, description="User ID")
    run_id: Optional[str] = Field(default=None, description="Correlation ID for workflow tracking")
    trace_id: Optional[str] = Field(default=None, description="Langfuse trace ID")
    openai_api_key: Optional[str] = Field(default=None, description="Per-user OpenAI API key")
    langfuse_public_key: Optional[str] = Field(default=None, description="Per-user Langfuse public key")
    langfuse_secret_key: Optional[str] = Field(default=None, description="Per-user Langfuse secret key")

    @field_validator('query')
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Query cannot be empty or whitespace')
        return v.strip()


class AgentResponse(BaseModel):
    """Final agent response."""

    type: Literal["answer", "plan_proposal"] = Field(default="answer", description="Response type")
    reply: Optional[str] = Field(default=None, description="Agent's reply text")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="Tool calls made")
    token_usage: Dict[str, int] = Field(default_factory=dict, description="Token usage stats")
    agent_name: Optional[str] = Field(default=None, description="Name of the agent")
    interrupt_data: Optional[Dict[str, Any]] = Field(default=None, description="HITL interrupt payload")


# =============================================================================
# Workflow State Validation Models
# =============================================================================

class WorkflowInput(BaseModel):
    """Validated input for starting a workflow."""

    message: str = Field(..., min_length=1, description="User message")
    user_id: int = Field(..., ge=1, description="User ID")
    session_id: int = Field(..., ge=1, description="Session ID")
    api_key: str = Field(..., min_length=1, description="OpenAI API key")
    run_id: Optional[str] = Field(default=None, description="Run ID for tracking")

    @field_validator('message')
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Message cannot be empty or whitespace')
        return v.strip()

    @field_validator('api_key')
    @classmethod
    def api_key_valid(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('API key cannot be empty')
        return v


class ResumePayload(BaseModel):
    """Payload for resuming from HITL interrupt."""

    # For plan approval
    approved: Optional[bool] = Field(default=None, description="Whether the plan was approved")

    # For player approval (action-based)
    action: Optional[Literal["approve", "reject"]] = Field(
        default=None, description="Player approval action"
    )

    # Common fields
    run_id: Optional[str] = Field(default=None, description="Run ID for tracking")
    player_data: Optional[Dict[str, Any]] = Field(default=None, description="Player data for save")
    report_text: Optional[str] = Field(default=None, description="Report text for save")
