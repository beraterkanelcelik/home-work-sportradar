"""
Composition task: Generate scouting report from extracted data.

Node 6 in the scouting workflow.
"""

from typing import Optional, List
from langgraph.func import task
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from app.agents.functional.scouting.schemas import (
    PlayerFields,
    Coverage,
    ScoutingReportDraft,
    DbPayloadPreview,
    ReportPayload,
)
from app.agents.config import OPENAI_MODEL
from app.core.logging import get_logger

logger = get_logger(__name__)

COMPOSITION_SYSTEM_PROMPT = """You are a professional sports scout writing a comprehensive scouting report.

Use the provided player information and facts to write a detailed, objective report.

REPORT STRUCTURE (use all sections, adapt content to available info):

## Player Snapshot
- 3-5 bullet points summarizing the player

## Strengths
- Bullet points of key strengths (evidence-based)

## Weaknesses / Areas for Improvement
- Bullet points of limitations (evidence-based)

## Playing Style & Tendencies
- Short paragraph describing how the player plays

## Role Projection
- Short paragraph on projected role/fit

## Development Focus
- Bullet points on areas to develop

## Risk Assessment
- Any risk factors or concerns (if applicable)

## Information Gaps
- Note what information was NOT found (from coverage.missing)

RULES:
1. Be objective and professional
2. Cite specific evidence when possible
3. Don't fabricate information not in the facts
4. Acknowledge gaps in information
5. Keep the report concise but comprehensive

Also provide:
- report_summary: 5-8 bullet points summarizing the report

Respond in JSON format:
{
    "report_text": "Full markdown report...",
    "report_summary": ["summary point 1", "summary point 2", ...]
}"""


@task
def compose_report(
    player_fields: PlayerFields,
    raw_facts: List[str],
    coverage: Coverage,
    feedback: Optional[str] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> ScoutingReportDraft:
    """
    Compose a scouting report from extracted data.

    Args:
        player_fields: Structured player data
        raw_facts: Atomic facts from evidence
        coverage: Coverage analysis (found/missing)
        feedback: Optional user feedback for revision
        api_key: OpenAI API key
        model_name: Model to use

    Returns:
        ScoutingReportDraft with report text and summary
    """
    logger.info(f"[COMPOSITION] Composing report for {player_fields.display_name}")

    if not api_key:
        raise ValueError("OpenAI API key is required for composition")

    try:
        llm = ChatOpenAI(
            model=model_name or OPENAI_MODEL,
            api_key=api_key,
            temperature=0.4,  # Slightly higher for creative writing
        )

        # Prepare context
        context = _prepare_context(player_fields, raw_facts, coverage)

        user_content = f"Write a scouting report for:\n\n{context}"
        if feedback:
            user_content += f"\n\nUser feedback for revision:\n{feedback}"

        messages = [
            SystemMessage(content=COMPOSITION_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
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
        except json.JSONDecodeError:
            # If JSON parsing fails, treat entire response as report
            logger.warning("[COMPOSITION] Failed to parse JSON, using raw response")
            data = {
                "report_text": content,
                "report_summary": _generate_default_summary(player_fields),
            }

        report_text = data.get("report_text", "")
        report_summary = data.get("report_summary", [])

        # Ensure we have a summary
        if not report_summary:
            report_summary = _generate_default_summary(player_fields)

        # Enforce summary length
        if len(report_summary) < 3:
            report_summary = _generate_default_summary(player_fields)
        elif len(report_summary) > 12:
            report_summary = report_summary[:12]

        # Build database payload preview
        db_payload_preview = DbPayloadPreview(
            player=player_fields,
            report=ReportPayload(
                report_text=report_text,
                report_summary=report_summary,
                coverage=coverage,
                source_doc_ids=None,  # Filled later if needed
            ),
        )

        draft = ScoutingReportDraft(
            report_text=report_text,
            report_summary=report_summary,
            db_payload_preview=db_payload_preview,
        )

        logger.info(
            f"[COMPOSITION] Generated report: {len(report_text)} chars, "
            f"{len(report_summary)} summary points"
        )

        return draft

    except Exception as e:
        logger.error(f"[COMPOSITION] Error composing report: {e}", exc_info=True)
        # Return minimal valid draft
        default_text = _generate_fallback_report(player_fields, raw_facts, coverage)
        default_summary = _generate_default_summary(player_fields)

        return ScoutingReportDraft(
            report_text=default_text,
            report_summary=default_summary,
            db_payload_preview=DbPayloadPreview(
                player=player_fields,
                report=ReportPayload(
                    report_text=default_text,
                    report_summary=default_summary,
                    coverage=coverage,
                ),
            ),
        )


def _prepare_context(
    player_fields: PlayerFields,
    raw_facts: List[str],
    coverage: Coverage,
) -> str:
    """Prepare context string for LLM."""
    lines = [
        f"# Player: {player_fields.display_name}",
        f"Sport: {player_fields.sport}",
    ]

    if player_fields.positions:
        lines.append(f"Positions: {', '.join(player_fields.positions)}")
    if player_fields.teams:
        lines.append(f"Teams: {', '.join(player_fields.teams)}")
    if player_fields.league:
        lines.append(f"League: {player_fields.league}")

    if player_fields.physical:
        if player_fields.physical.height_cm:
            lines.append(f"Height: {player_fields.physical.height_cm} cm")
        if player_fields.physical.weight_kg:
            lines.append(f"Weight: {player_fields.physical.weight_kg} kg")

    if player_fields.scouting:
        if player_fields.scouting.strengths:
            lines.append(f"Strengths: {', '.join(player_fields.scouting.strengths)}")
        if player_fields.scouting.weaknesses:
            lines.append(f"Weaknesses: {', '.join(player_fields.scouting.weaknesses)}")
        if player_fields.scouting.style_tags:
            lines.append(f"Style: {', '.join(player_fields.scouting.style_tags)}")
        if player_fields.scouting.role_projection:
            lines.append(f"Role Projection: {player_fields.scouting.role_projection}")

    lines.append("\n## Raw Facts from Evidence:")
    for i, fact in enumerate(raw_facts[:20], 1):
        lines.append(f"{i}. {fact}")

    lines.append("\n## Coverage Analysis:")
    lines.append(f"Information found for: {', '.join(coverage.found) or 'None'}")
    lines.append(f"Information missing: {', '.join(coverage.missing) or 'None'}")

    return "\n".join(lines)


def _generate_default_summary(player_fields: PlayerFields) -> List[str]:
    """Generate default summary from player fields."""
    summary = [f"Scouting report for {player_fields.display_name}"]

    if player_fields.positions:
        summary.append(f"Plays {', '.join(player_fields.positions)}")
    if player_fields.teams:
        summary.append(f"Associated with {', '.join(player_fields.teams[:2])}")
    if player_fields.scouting and player_fields.scouting.strengths:
        summary.append(f"Key strengths: {', '.join(player_fields.scouting.strengths[:2])}")
    if player_fields.scouting and player_fields.scouting.weaknesses:
        summary.append(f"Areas to develop: {', '.join(player_fields.scouting.weaknesses[:2])}")

    # Ensure minimum 3 items
    while len(summary) < 3:
        summary.append(f"Sport: {player_fields.sport}")

    return summary[:8]


def _generate_fallback_report(
    player_fields: PlayerFields,
    raw_facts: List[str],
    coverage: Coverage,
) -> str:
    """Generate fallback report when LLM fails."""
    lines = [
        f"# Scouting Report: {player_fields.display_name}",
        "",
        "## Player Snapshot",
        f"- Sport: {player_fields.sport}",
    ]

    if player_fields.positions:
        lines.append(f"- Positions: {', '.join(player_fields.positions)}")
    if player_fields.teams:
        lines.append(f"- Teams: {', '.join(player_fields.teams)}")

    lines.append("")
    lines.append("## Key Facts")
    for fact in raw_facts[:10]:
        lines.append(f"- {fact}")

    if coverage.missing:
        lines.append("")
        lines.append("## Information Not Available")
        lines.append(f"- {', '.join(coverage.missing)}")

    return "\n".join(lines)
