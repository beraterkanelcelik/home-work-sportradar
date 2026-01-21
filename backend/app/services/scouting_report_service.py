"""
Scouting Report service layer for business logic.
"""
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from django.db import transaction
from app.db.models.player import Player
from app.db.models.scouting_report import ScoutingReport
from app.services import player_service
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_scouting_report(
    player_id: UUID,
    report_text: str,
    report_summary: Optional[List[str]] = None,
    coverage: Optional[Dict[str, Any]] = None,
    source_doc_ids: Optional[List[str]] = None,
    run_id: Optional[str] = None,
    request_text: Optional[str] = None,
) -> ScoutingReport:
    """
    Create a scouting report for an existing player.

    Args:
        player_id: Player UUID
        report_text: Full report text (required)
        report_summary: Summary bullets
        coverage: Coverage metadata {found: [...], missing: [...]}
        source_doc_ids: Source document IDs
        run_id: Workflow run correlation ID
        request_text: Original user request

    Returns:
        Created ScoutingReport object
    """
    with transaction.atomic():
        report = ScoutingReport.objects.create(
            player_id=player_id,
            report_text=report_text,
            report_summary=report_summary,
            coverage=coverage,
            source_doc_ids=source_doc_ids,
            run_id=run_id,
            request_text=request_text,
        )

    logger.info(f"Created scouting report {report.id} for player {player_id}")
    return report


def create_with_player(
    owner_id: int,
    player_fields: Dict[str, Any],
    report_data: Dict[str, Any],
    run_id: Optional[str] = None,
    request_text: Optional[str] = None,
) -> Tuple[Player, ScoutingReport]:
    """
    Create player and scouting report in a single atomic transaction.

    This is the One-Call Create API per agentic-schemas.md:
    1. Insert players row
    2. Insert scouting_reports row with player_id
    3. Update players.latest_report_id

    Args:
        owner_id: User ID who owns the player
        player_fields: Dict matching PlayerFields schema
        report_data: Dict with report_text, report_summary, coverage, source_doc_ids
        run_id: Optional workflow run correlation ID
        request_text: Optional original user request

    Returns:
        Tuple of (Player, ScoutingReport)

    Raises:
        Exception: If transaction fails (rolls back)
    """
    with transaction.atomic():
        # 1. Create player
        player = player_service.create_player_from_fields(owner_id, player_fields.copy())

        # 2. Create scouting report
        report = ScoutingReport.objects.create(
            player=player,
            report_text=report_data.get("report_text"),
            report_summary=report_data.get("report_summary"),
            coverage=report_data.get("coverage"),
            source_doc_ids=report_data.get("source_doc_ids"),
            run_id=run_id,
            request_text=request_text,
        )

        # 3. Update player's latest_report
        player.latest_report = report
        player.save(update_fields=["latest_report", "updated_at"])

    logger.info(
        f"Created player {player.id} with report {report.id} for user {owner_id}"
    )
    return player, report


def create_with_player_from_request(
    owner_id: int,
    request_dict: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Create player and report from CreatePlayerWithReportRequest dict.

    Convenience wrapper that returns string UUIDs matching API contract.

    Args:
        owner_id: User ID
        request_dict: Dict matching CreatePlayerWithReportRequest schema

    Returns:
        Tuple of (player_id: str, report_id: str)
    """
    player, report = create_with_player(
        owner_id=owner_id,
        player_fields=request_dict.get("player", {}),
        report_data=request_dict.get("report", {}),
        run_id=request_dict.get("run_id"),
        request_text=request_dict.get("request_text"),
    )
    return str(player.id), str(report.id)


def get_report_by_id(player_id: UUID, report_id: UUID) -> Optional[ScoutingReport]:
    """
    Get a scouting report by ID.

    Args:
        player_id: Player UUID (for validation)
        report_id: Report UUID

    Returns:
        ScoutingReport object or None if not found
    """
    try:
        return ScoutingReport.objects.get(id=report_id, player_id=player_id)
    except ScoutingReport.DoesNotExist:
        return None


def list_reports_by_player(
    player_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> List[ScoutingReport]:
    """
    List scouting reports for a player.

    Args:
        player_id: Player UUID
        limit: Max results (default 20)
        offset: Pagination offset

    Returns:
        List of ScoutingReport objects
    """
    return list(
        ScoutingReport.objects.filter(player_id=player_id)
        .order_by("-created_at")[offset : offset + limit]
    )


def get_latest_report(player_id: UUID) -> Optional[ScoutingReport]:
    """
    Get the most recent scouting report for a player.

    Args:
        player_id: Player UUID

    Returns:
        Most recent ScoutingReport or None
    """
    return (
        ScoutingReport.objects.filter(player_id=player_id)
        .order_by("-created_at")
        .first()
    )


def delete_report(report_id: UUID) -> bool:
    """
    Delete a scouting report.

    Args:
        report_id: Report UUID

    Returns:
        True if deleted, False if not found
    """
    try:
        report = ScoutingReport.objects.get(id=report_id)
        player_id = report.player_id

        # Check if this was the latest report
        player = Player.objects.filter(id=player_id, latest_report_id=report_id).first()

        with transaction.atomic():
            report.delete()

            # If deleted report was latest, update player
            if player:
                new_latest = get_latest_report(player_id)
                player.latest_report = new_latest
                player.save(update_fields=["latest_report", "updated_at"])

        logger.info(f"Deleted scouting report {report_id}")
        return True
    except ScoutingReport.DoesNotExist:
        return False
