"""
Write task: Create player and report in database.

Node 8 in the scouting workflow.
"""

from typing import Optional
from langgraph.func import task
from app.agents.functional.scouting.schemas import (
    DbPayloadPreview,
    CreatePlayerWithReportResponse,
)
from app.services import scouting_report_service
from app.core.logging import get_logger

logger = get_logger(__name__)


@task
def write_player_item(
    preview: DbPayloadPreview,
    user_id: int,
    run_id: Optional[str] = None,
    request_text: Optional[str] = None,
) -> CreatePlayerWithReportResponse:
    """
    Create player and scouting report in database.

    Uses atomic transaction to create:
    1. Player record
    2. ScoutingReport record
    3. Link player.latest_report to new report

    Args:
        preview: Database payload preview (approved by user)
        user_id: User ID (owner)
        run_id: Optional workflow run correlation ID
        request_text: Optional original user request

    Returns:
        CreatePlayerWithReportResponse with player_id and report_id
    """
    logger.info(
        f"[WRITE] Creating player record for {preview.player.display_name}"
    )

    try:
        # Convert Pydantic models to dicts
        player_dict = preview.player.model_dump(exclude_none=True)
        report_dict = preview.report.model_dump(exclude_none=True)

        # Convert coverage if it's a Pydantic model
        if "coverage" in report_dict and hasattr(report_dict["coverage"], "model_dump"):
            report_dict["coverage"] = report_dict["coverage"].model_dump()

        # Use service to create in atomic transaction
        player_id, report_id = scouting_report_service.create_with_player_from_request(
            owner_id=user_id,
            request_dict={
                "player": player_dict,
                "report": report_dict,
                "run_id": run_id,
                "request_text": request_text,
            },
        )

        logger.info(
            f"[WRITE] Created player {player_id} with report {report_id}"
        )

        return CreatePlayerWithReportResponse(
            player_id=player_id,
            report_id=report_id,
        )

    except Exception as e:
        logger.error(f"[WRITE] Error creating player record: {e}", exc_info=True)
        raise ValueError(f"Failed to save player record: {e}")
