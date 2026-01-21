"""
Response task: Build final agent response.

Node 9 in the scouting workflow.
"""

from typing import Optional, Dict, Any
from langgraph.func import task
from app.agents.functional.models import AgentResponse
from app.agents.functional.scouting.schemas import (
    ScoutingReportDraft,
    Coverage,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


@task
def build_final_response(
    report_draft: ScoutingReportDraft,
    player_record_id: Optional[str],
    report_id: Optional[str],
    saved: bool,
    coverage: Coverage,
    player_name: str,
) -> AgentResponse:
    """
    Build final agent response for the scouting workflow.

    Args:
        report_draft: The composed report draft
        player_record_id: Created player UUID (None if not saved)
        report_id: Created report UUID (None if not saved)
        saved: Whether the record was saved
        coverage: Coverage analysis
        player_name: Target player name

    Returns:
        AgentResponse with full report and metadata
    """
    logger.info(
        f"[RESPONSE] Building final response for {player_name}, saved={saved}"
    )

    # Build reply text with status
    reply_parts = [report_draft.report_text]

    if saved:
        reply_parts.append("\n\n---")
        reply_parts.append(f"\n*Player record saved successfully.*")
    else:
        reply_parts.append("\n\n---")
        reply_parts.append(f"\n*Report generated (player record not saved).*")

    # Add coverage note if there were gaps
    if coverage.missing:
        reply_parts.append(f"\n\n**Note:** Limited information found for: {', '.join(coverage.missing)}")

    reply = "\n".join(reply_parts)

    # Build metadata
    metadata: Dict[str, Any] = {
        "workflow": "scouting",
        "player_name": player_name,
        "saved": saved,
        "coverage": {
            "found": coverage.found,
            "missing": coverage.missing,
        },
    }

    if player_record_id:
        metadata["player_id"] = player_record_id
    if report_id:
        metadata["report_id"] = report_id

    response = AgentResponse(
        type="answer",
        reply=reply,
        agent_name="scouting",
        raw_tool_outputs=[{
            "type": "scouting_report",
            "player_name": player_name,
            "report_summary": report_draft.report_summary,
            "saved": saved,
            "player_id": player_record_id,
            "report_id": report_id,
        }],
    )

    logger.info(
        f"[RESPONSE] Final response built: {len(reply)} chars, saved={saved}"
    )

    return response
