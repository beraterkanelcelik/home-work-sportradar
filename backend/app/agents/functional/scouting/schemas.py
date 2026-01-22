"""
Pydantic schemas for the Scouting Report workflow.

These schemas define contracts between nodes in the scouting workflow,
matching the specifications in agentic-schemas.md.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal
from dataclasses import dataclass, field


# =============================================================================
# Physical & Scouting Attributes (nested in PlayerFields)
# =============================================================================


class PhysicalAttributes(BaseModel):
    """Physical measurements for a player (optional fields)."""

    height_cm: Optional[int] = Field(
        None, ge=80, le=260, description="Height in centimeters"
    )
    weight_kg: Optional[int] = Field(
        None, ge=30, le=200, description="Weight in kilograms"
    )
    measurements: Optional[Dict[str, Any]] = Field(
        None, description="Additional measurements e.g. wingspan_cm, hand_size_in"
    )


class ScoutingAttributes(BaseModel):
    """Scouting evaluation attributes (optional fields)."""

    strengths: Optional[List[str]] = Field(None, description="Player strengths")
    weaknesses: Optional[List[str]] = Field(
        None, description="Player weaknesses/limitations"
    )
    style_tags: Optional[List[str]] = Field(
        None, description="Style descriptors e.g. '3PT shooter', 'POA defender'"
    )
    risk_notes: Optional[List[str]] = Field(None, description="Risk factors")
    role_projection: Optional[str] = Field(
        None, description="Projected role description"
    )


# =============================================================================
# PlayerFields (Extractor output)
# =============================================================================


class PlayerFields(BaseModel):
    """
    Structured player fields extracted from evidence.

    Only includes fields supported by retrieved evidence.
    Unknown fields should be omitted (not set to null).
    """

    # Required
    display_name: str = Field(..., min_length=1, description="Player display name")
    sport: Literal["nba", "football", "unknown"] = Field(..., description="Sport type")

    # Optional identity
    positions: Optional[List[str]] = Field(
        None, min_length=1, description="Player positions"
    )
    teams: Optional[List[str]] = Field(None, description="Teams played for")
    league: Optional[str] = Field(None, description="League name")
    aliases: Optional[List[str]] = Field(None, description="Alternative names")

    # Nested optional attributes
    physical: Optional[PhysicalAttributes] = Field(
        None, description="Physical measurements"
    )
    scouting: Optional[ScoutingAttributes] = Field(
        None, description="Scouting evaluation"
    )

    class Config:
        extra = "forbid"  # Disallow extra fields


# =============================================================================
# EvidencePack (Retriever output)
# =============================================================================


class ChunkData(BaseModel):
    """A single retrieved chunk from vector search."""

    doc_id: str = Field(..., description="Document ID")
    chunk_id: str = Field(..., description="Chunk ID within document")
    text: str = Field(..., min_length=1, description="Chunk text content")
    score: float = Field(..., description="Similarity score")


class Coverage(BaseModel):
    """Coverage report: what was found vs missing."""

    found: List[str] = Field(
        default_factory=list, description="Fields with evidence found"
    )
    missing: List[str] = Field(
        default_factory=list, description="Fields without evidence"
    )


class EvidencePack(BaseModel):
    """
    Evidence pack from retriever.

    Contains queries used, retrieved chunks, coverage analysis,
    and confidence assessment.
    """

    queries: List[str] = Field(
        ..., min_length=1, max_length=6, description="Queries executed"
    )
    chunks: List[ChunkData] = Field(
        default_factory=list, max_length=40, description="Retrieved chunks (max 40)"
    )
    coverage: Coverage = Field(..., description="Coverage analysis")
    confidence: Literal["low", "med", "high"] = Field(
        ..., description="Confidence level"
    )

    class Config:
        extra = "forbid"


# =============================================================================
# ScoutingReportDraft (Composer output)
# =============================================================================


class ReportPayload(BaseModel):
    """Report data for database storage."""

    report_text: str = Field(..., min_length=1, description="Full report text")
    report_summary: Optional[List[str]] = Field(None, description="Summary bullets")
    coverage: Optional[Coverage] = Field(None, description="Coverage metadata")
    source_doc_ids: Optional[List[str]] = Field(None, description="Source document IDs")


class DbPayloadPreview(BaseModel):
    """Preview of data to be written to database."""

    player: PlayerFields = Field(..., description="Player fields to create")
    report: ReportPayload = Field(..., description="Report data to create")


class ScoutingReportDraft(BaseModel):
    """
    Scouting report draft from composer.

    Contains the full report text, summary bullets,
    and preview of database payload for HITL approval.
    """

    report_text: str = Field(..., min_length=1, description="Full scouting report")
    report_summary: List[str] = Field(
        ..., min_length=3, max_length=12, description="Summary bullets (3-12)"
    )
    db_payload_preview: DbPayloadPreview = Field(
        ..., description="Database payload preview"
    )

    class Config:
        extra = "forbid"


# =============================================================================
# One-Call Create API (DB Write Contract)
# =============================================================================


class CreatePlayerWithReportRequest(BaseModel):
    """Request to create player and scouting report in single transaction."""

    run_id: Optional[str] = Field(None, description="Workflow run correlation ID")
    request_text: Optional[str] = Field(None, description="Original user request")
    player: PlayerFields = Field(..., description="Player data")
    report: ReportPayload = Field(..., description="Report data")


class CreatePlayerWithReportResponse(BaseModel):
    """Response from creating player with report."""

    player_id: str = Field(..., description="Created player UUID")
    report_id: str = Field(..., description="Created scouting report UUID")


# =============================================================================
# Workflow State and Intermediate Schemas
# =============================================================================


class IntakeResult(BaseModel):
    """Result from intake_and_route_scouting task."""

    intent: str = Field(..., description="Detected intent")
    player_name: str = Field(..., description="Extracted player name")
    sport_guess: Literal["nba", "football", "unknown"] = Field(
        ..., description="Guessed sport type"
    )


class PlanProposal(BaseModel):
    """Plan proposal for HITL Gate A approval (DEPRECATED - use ExecutionPlan)."""

    plan_steps: List[str] = Field(
        ..., min_length=4, max_length=7, description="Plan steps"
    )
    query_hints: List[str] = Field(
        default_factory=list, description="Query hints for retrieval"
    )


# =============================================================================
# Dynamic Execution Plan (New Architecture)
# =============================================================================


class PlanStep(BaseModel):
    """
    Executable plan step.

    Each step represents a concrete action the agent will take.
    Steps are executed sequentially after user approval.
    """

    action: Literal[
        "rag_search",  # Search user's documents
        "extract_player",  # Extract structured player data from evidence
        "compose_report",  # Generate scouting report from extracted data
        "update_report",  # Update an existing saved report
        "save_player",  # Save player + report to DB (triggers HITL Gate B)
        "answer",  # Generate final response from context
    ] = Field(..., description="Action type to execute")

    description: str = Field(
        ..., min_length=1, description="Human-readable step description for UI"
    )

    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Action-specific parameters (e.g., query for rag_search)",
    )


class ExecutionPlan(BaseModel):
    """
    Agent-generated dynamic execution plan.

    The planner analyzes user intent and generates a plan with concrete steps.
    Simple queries get 1-2 steps, full scouting reports get 5-7 steps.
    """

    intent: Literal[
        "info_query", "scouting_report", "update_report", "general_chat"
    ] = Field(..., description="Detected intent type")

    player_name: Optional[str] = Field(
        None, description="Target player name (if applicable)"
    )

    sport_guess: Optional[Literal["nba", "football", "unknown"]] = Field(
        None, description="Guessed sport type"
    )

    reasoning: str = Field(
        ..., description="Brief explanation of why this plan was generated"
    )

    steps: List[PlanStep] = Field(
        ..., min_length=1, max_length=10, description="Ordered list of steps to execute"
    )

    # For update_report intent
    target_report_id: Optional[str] = Field(
        None, description="ID of report to update (for update_report intent)"
    )

    class Config:
        extra = "forbid"


class ApprovalDecision(BaseModel):
    """Decision from HITL Gate B (player approval)."""

    action: Literal["approve", "reject", "edit_wording", "edit_content"] = Field(
        ..., description="User action"
    )
    feedback: Optional[str] = Field(
        None, description="Optional feedback for edit actions"
    )


@dataclass
class ScoutingWorkflowState:
    """
    State passed between nodes in scouting workflow.

    This dataclass tracks all intermediate results as the
    workflow progresses through the 9 nodes.
    """

    # From Node 1: Intake
    intent: str = ""
    player_name: str = ""
    sport_guess: Literal["nba", "football", "unknown"] = "unknown"

    # From Node 2: Draft Plan
    plan_steps: List[str] = field(default_factory=list)
    query_hints: List[str] = field(default_factory=list)

    # From Node 3: Build Queries
    queries: List[str] = field(default_factory=list)

    # From Node 4: Retrieve Evidence
    evidence_pack: Optional[EvidencePack] = None

    # From Node 5: Extract Fields
    player_fields: Optional[PlayerFields] = None
    raw_facts: List[str] = field(default_factory=list)
    coverage: Optional[Coverage] = None

    # From Node 6: Compose Report
    report_draft: Optional[ScoutingReportDraft] = None

    # From Node 8: Write Player Item
    player_record_id: Optional[str] = None
    report_id: Optional[str] = None
    saved: bool = False

    # Error tracking
    error: Optional[str] = None
