"""
Preview task: Prepare database payload for approval UI.

Node 7 in the scouting workflow.
"""

from typing import Optional, List
from langgraph.func import task
from app.agents.functional.scouting.schemas import (
    ScoutingReportDraft,
    DbPayloadPreview,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


@task
def prepare_preview(
    report_draft: ScoutingReportDraft,
    source_doc_ids: Optional[List[str]] = None,
) -> DbPayloadPreview:
    """
    Prepare database payload preview for approval UI.

    This is a simple pass-through that enriches the draft's
    db_payload_preview with any additional metadata.

    Args:
        report_draft: Composed report draft
        source_doc_ids: Optional list of source document IDs

    Returns:
        DbPayloadPreview ready for HITL approval
    """
    logger.info("[PREVIEW] Preparing database payload preview")

    preview = report_draft.db_payload_preview

    # Add source document IDs if provided
    if source_doc_ids and preview.report:
        preview.report.source_doc_ids = source_doc_ids

    logger.info(
        f"[PREVIEW] Preview ready: player={preview.player.display_name}, "
        f"summary_points={len(preview.report.report_summary or [])}"
    )

    return preview
