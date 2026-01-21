"""
Player service layer for business logic.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from django.db import transaction
from app.db.models.player import Player
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_player(
    owner_id: int,
    display_name: str,
    sport: str = "unknown",
    positions: Optional[List[str]] = None,
    teams: Optional[List[str]] = None,
    league: Optional[str] = None,
    aliases: Optional[List[str]] = None,
    height_cm: Optional[int] = None,
    weight_kg: Optional[int] = None,
    measurements: Optional[Dict[str, Any]] = None,
    strengths: Optional[List[str]] = None,
    weaknesses: Optional[List[str]] = None,
    style_tags: Optional[List[str]] = None,
    risk_notes: Optional[List[str]] = None,
    role_projection: Optional[str] = None,
) -> Player:
    """
    Create a new player record.

    MVP: Always creates new player (no existence check).

    Args:
        owner_id: User ID who owns this player
        display_name: Player display name (required)
        sport: Sport type (nba/football/unknown)
        positions: Optional list of positions
        teams: Optional list of teams
        league: Optional league name
        aliases: Optional alternative names
        height_cm: Optional height in cm (80-260)
        weight_kg: Optional weight in kg (30-200)
        measurements: Optional additional measurements
        strengths: Optional list of strengths
        weaknesses: Optional list of weaknesses
        style_tags: Optional style descriptors
        risk_notes: Optional risk factors
        role_projection: Optional role projection text

    Returns:
        Created Player object
    """
    with transaction.atomic():
        player = Player.objects.create(
            owner_id=owner_id,
            display_name=display_name,
            sport=sport,
            positions=positions,
            teams=teams,
            league=league,
            aliases=aliases,
            height_cm=height_cm,
            weight_kg=weight_kg,
            measurements=measurements,
            strengths=strengths,
            weaknesses=weaknesses,
            style_tags=style_tags,
            risk_notes=risk_notes,
            role_projection=role_projection,
        )

    logger.info(f"Created player {player.id} ({display_name}) for user {owner_id}")
    return player


def create_player_from_fields(owner_id: int, player_fields: Dict[str, Any]) -> Player:
    """
    Create a player from PlayerFields schema dict.

    Handles nested physical and scouting attributes by flattening.

    Args:
        owner_id: User ID who owns this player
        player_fields: Dict matching PlayerFields schema

    Returns:
        Created Player object
    """
    # Extract nested attributes
    physical = player_fields.pop("physical", None) or {}
    scouting = player_fields.pop("scouting", None) or {}

    # Flatten physical attributes
    height_cm = physical.get("height_cm")
    weight_kg = physical.get("weight_kg")
    measurements = physical.get("measurements")

    # Flatten scouting attributes
    strengths = scouting.get("strengths")
    weaknesses = scouting.get("weaknesses")
    style_tags = scouting.get("style_tags")
    risk_notes = scouting.get("risk_notes")
    role_projection = scouting.get("role_projection")

    return create_player(
        owner_id=owner_id,
        display_name=player_fields.get("display_name"),
        sport=player_fields.get("sport", "unknown"),
        positions=player_fields.get("positions"),
        teams=player_fields.get("teams"),
        league=player_fields.get("league"),
        aliases=player_fields.get("aliases"),
        height_cm=height_cm,
        weight_kg=weight_kg,
        measurements=measurements,
        strengths=strengths,
        weaknesses=weaknesses,
        style_tags=style_tags,
        risk_notes=risk_notes,
        role_projection=role_projection,
    )


def get_player_by_id(owner_id: int, player_id: UUID) -> Optional[Player]:
    """
    Get a player by ID, ensuring ownership.

    Args:
        owner_id: User ID (for multi-tenancy check)
        player_id: Player UUID

    Returns:
        Player object or None if not found
    """
    try:
        return Player.objects.get(id=player_id, owner_id=owner_id)
    except Player.DoesNotExist:
        return None


def list_players_by_owner(
    owner_id: int,
    sport: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Player]:
    """
    List players for a user with optional filtering.

    Args:
        owner_id: User ID
        sport: Optional sport filter
        limit: Max results (default 50)
        offset: Pagination offset

    Returns:
        List of Player objects
    """
    queryset = Player.objects.filter(owner_id=owner_id)

    if sport:
        queryset = queryset.filter(sport=sport)

    return list(queryset.order_by("-created_at")[offset : offset + limit])


def update_player_latest_report(player_id: UUID, report_id: UUID) -> bool:
    """
    Update player's latest_report FK.

    Args:
        player_id: Player UUID
        report_id: ScoutingReport UUID

    Returns:
        True if updated, False if player not found
    """
    updated = Player.objects.filter(id=player_id).update(latest_report_id=report_id)
    if updated:
        logger.debug(f"Updated player {player_id} latest_report to {report_id}")
    return updated > 0


def delete_player(owner_id: int, player_id: UUID) -> bool:
    """
    Delete a player and all associated reports.

    Args:
        owner_id: User ID (for multi-tenancy check)
        player_id: Player UUID

    Returns:
        True if deleted, False if not found
    """
    try:
        player = Player.objects.get(id=player_id, owner_id=owner_id)
        player.delete()
        logger.info(f"Deleted player {player_id} for user {owner_id}")
        return True
    except Player.DoesNotExist:
        return False
