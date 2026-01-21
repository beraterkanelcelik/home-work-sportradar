"""
Extraction task: Extract structured player fields from evidence.

Node 5 in the scouting workflow.
"""

from typing import Optional, List, Dict, Any, Tuple
from langgraph.func import task
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from app.agents.functional.scouting.schemas import (
    EvidencePack,
    PlayerFields,
    PhysicalAttributes,
    ScoutingAttributes,
    Coverage,
)
from app.agents.config import OPENAI_MODEL
from app.core.logging import get_logger

logger = get_logger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a sports data extraction specialist. Extract structured player information from the provided evidence chunks.

IMPORTANT RULES:
1. Only extract information explicitly stated in the evidence
2. Do NOT hallucinate or infer information not present
3. If a field cannot be determined from evidence, OMIT it entirely
4. Convert measurements to standard units (height in cm, weight in kg)

Extract the following fields (include only if evidence supports):

REQUIRED:
- display_name: Player's full name
- sport: "nba" | "football" | "unknown"

OPTIONAL IDENTITY:
- positions: Array of positions played ["SG", "SF"] or ["QB", "WR"]
- teams: Array of teams ["LAL", "MIA"]
- league: League name "NBA", "NFL"
- aliases: Alternative names

OPTIONAL PHYSICAL:
- height_cm: Height in centimeters (convert from feet/inches if needed)
- weight_kg: Weight in kilograms (convert from pounds if needed)
- measurements: Other measurements {"wingspan_cm": 208, "hand_size_in": 9.5}

OPTIONAL SCOUTING:
- strengths: Array of strengths
- weaknesses: Array of weaknesses
- style_tags: Play style descriptors ["3PT shooter", "rim protector"]
- risk_notes: Risk factors
- role_projection: Projected role description

Also extract raw_facts: Array of atomic facts/statements from the evidence (5-15 items).

Respond in JSON format:
{
    "player_fields": { ... },
    "raw_facts": ["fact1", "fact2", ...]
}"""


@task
def extract_fields(
    evidence_pack: EvidencePack,
    player_name: str,
    sport_guess: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Tuple[PlayerFields, List[str], Coverage]:
    """
    Extract structured player fields from evidence.

    Args:
        evidence_pack: Retrieved evidence chunks
        player_name: Target player name
        sport_guess: Guessed sport
        api_key: OpenAI API key
        model_name: Model to use

    Returns:
        Tuple of (PlayerFields, raw_facts, coverage)
    """
    logger.info(f"[EXTRACTION] Extracting fields for {player_name}")

    if not api_key:
        raise ValueError("OpenAI API key is required for extraction")

    # Prepare evidence text
    evidence_text = _prepare_evidence_text(evidence_pack)

    if not evidence_text.strip():
        logger.warning("[EXTRACTION] No evidence text to extract from")
        return (
            PlayerFields(display_name=player_name, sport=sport_guess),
            [],
            evidence_pack.coverage,
        )

    try:
        llm = ChatOpenAI(
            model=model_name or OPENAI_MODEL,
            api_key=api_key,
            temperature=0,
        )

        messages = [
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Extract information for player: {player_name}\n"
                    f"Expected sport: {sport_guess}\n\n"
                    f"Evidence:\n{evidence_text}"
                )
            ),
        ]

        response = llm.invoke(messages)
        content = response.content.strip()

        # Parse JSON response
        import json
        try:
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"[EXTRACTION] Failed to parse LLM response: {e}")
            return (
                PlayerFields(display_name=player_name, sport=sport_guess),
                [],
                evidence_pack.coverage,
            )

        # Build PlayerFields from extracted data
        player_data = data.get("player_fields", {})
        raw_facts = data.get("raw_facts", [])

        player_fields = _build_player_fields(player_data, player_name, sport_guess)

        logger.info(
            f"[EXTRACTION] Extracted {len(raw_facts)} facts, "
            f"fields: positions={player_fields.positions is not None}, "
            f"physical={player_fields.physical is not None}"
        )

        return (player_fields, raw_facts, evidence_pack.coverage)

    except Exception as e:
        logger.error(f"[EXTRACTION] Error during extraction: {e}", exc_info=True)
        return (
            PlayerFields(display_name=player_name, sport=sport_guess),
            [],
            evidence_pack.coverage,
        )


def _prepare_evidence_text(evidence_pack: EvidencePack) -> str:
    """Prepare evidence text for LLM."""
    chunks_text = []
    for i, chunk in enumerate(evidence_pack.chunks[:30], 1):  # Limit to top 30
        chunks_text.append(f"[{i}] {chunk.text}")

    return "\n\n".join(chunks_text)


def _build_player_fields(
    data: Dict[str, Any],
    default_name: str,
    default_sport: str,
) -> PlayerFields:
    """Build PlayerFields from extracted data."""

    # Build physical attributes if present
    physical = None
    physical_data = data.get("physical", {})
    if not physical_data:
        # Check for flat fields
        if data.get("height_cm") or data.get("weight_kg"):
            physical_data = {
                "height_cm": data.get("height_cm"),
                "weight_kg": data.get("weight_kg"),
                "measurements": data.get("measurements"),
            }

    if physical_data and any(physical_data.values()):
        physical = PhysicalAttributes(
            height_cm=physical_data.get("height_cm"),
            weight_kg=physical_data.get("weight_kg"),
            measurements=physical_data.get("measurements"),
        )

    # Build scouting attributes if present
    scouting = None
    scouting_data = data.get("scouting", {})
    if not scouting_data:
        # Check for flat fields
        if any(data.get(f) for f in ["strengths", "weaknesses", "style_tags", "risk_notes", "role_projection"]):
            scouting_data = {
                "strengths": data.get("strengths"),
                "weaknesses": data.get("weaknesses"),
                "style_tags": data.get("style_tags"),
                "risk_notes": data.get("risk_notes"),
                "role_projection": data.get("role_projection"),
            }

    if scouting_data and any(scouting_data.values()):
        scouting = ScoutingAttributes(
            strengths=scouting_data.get("strengths"),
            weaknesses=scouting_data.get("weaknesses"),
            style_tags=scouting_data.get("style_tags"),
            risk_notes=scouting_data.get("risk_notes"),
            role_projection=scouting_data.get("role_projection"),
        )

    return PlayerFields(
        display_name=data.get("display_name") or default_name,
        sport=data.get("sport") or default_sport,
        positions=data.get("positions"),
        teams=data.get("teams"),
        league=data.get("league"),
        aliases=data.get("aliases"),
        physical=physical,
        scouting=scouting,
    )
