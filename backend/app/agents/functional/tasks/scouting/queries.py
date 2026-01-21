"""
Queries task: Build diversified search queries for retrieval.

Node 3 in the scouting workflow.
"""

from typing import Optional, List
from langgraph.func import task
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from app.agents.config import OPENAI_MODEL
from app.core.logging import get_logger

logger = get_logger(__name__)

QUERIES_SYSTEM_PROMPT = """You are a search query optimizer for sports document retrieval. Generate 3-6 diversified search queries to find comprehensive information about a player.

Required queries (always include variations of these):
1. Player name only (for general mentions)
2. Player strengths and weaknesses
3. Player physical attributes (height, weight, position)

Optional queries based on sport/context:
- Sport-specific stats (shooting %, passing yards, etc.)
- Team history and career progression
- Playing style and tendencies
- Draft information and projections

Respond in JSON format only:
{
    "queries": [
        "query1",
        "query2",
        ...
    ]
}

Keep queries concise and focused. Avoid redundant queries."""


@task
def build_queries(
    player_name: str,
    sport_guess: str,
    query_hints: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> List[str]:
    """
    Build diversified search queries for RAG retrieval.

    Args:
        player_name: Target player name
        sport_guess: Guessed sport (nba/football/unknown)
        query_hints: Optional hints from plan or user feedback
        api_key: OpenAI API key
        model_name: Model to use

    Returns:
        List of 3-6 search queries
    """
    logger.info(f"[QUERIES] Building queries for {player_name}")

    # Always include these required queries
    required_queries = [
        player_name,
        f"{player_name} strengths weaknesses",
        f"{player_name} height weight position",
    ]

    # Add sport-specific queries
    sport_queries = _get_sport_queries(sport_guess, player_name)

    # Add hint-based queries
    hint_queries = []
    if query_hints:
        for hint in query_hints[:3]:  # Max 3 hints
            if player_name.lower() not in hint.lower():
                hint_queries.append(f"{player_name} {hint}")
            else:
                hint_queries.append(hint)

    # If no API key, return combined default queries
    if not api_key:
        all_queries = required_queries + sport_queries + hint_queries
        unique_queries = _dedupe_queries(all_queries)
        return unique_queries[:6]

    try:
        llm = ChatOpenAI(
            model=model_name or OPENAI_MODEL,
            api_key=api_key,
            temperature=0.3,
        )

        hint_text = ""
        if query_hints:
            hint_text = f"\nUser-provided hints: {', '.join(query_hints)}"

        messages = [
            SystemMessage(content=QUERIES_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Generate search queries for: {player_name}\n"
                    f"Sport: {sport_guess}{hint_text}"
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
            llm_queries = data.get("queries", [])
        except json.JSONDecodeError:
            logger.warning("[QUERIES] Failed to parse LLM response")
            llm_queries = []

        # Merge LLM queries with required queries
        all_queries = required_queries + llm_queries + sport_queries
        unique_queries = _dedupe_queries(all_queries)

        # Enforce 3-6 queries
        if len(unique_queries) < 3:
            unique_queries = required_queries
        elif len(unique_queries) > 6:
            unique_queries = unique_queries[:6]

        logger.info(f"[QUERIES] Generated {len(unique_queries)} queries")
        return unique_queries

    except Exception as e:
        logger.error(f"[QUERIES] Error generating queries: {e}")
        all_queries = required_queries + sport_queries
        return _dedupe_queries(all_queries)[:6]


def _get_sport_queries(sport_guess: str, player_name: str) -> List[str]:
    """Get sport-specific queries."""
    if sport_guess == "nba":
        return [
            f"{player_name} shooting percentage stats",
            f"{player_name} defensive rating",
        ]
    elif sport_guess == "football":
        return [
            f"{player_name} passing rushing stats",
            f"{player_name} combine measurements",
        ]
    else:
        return [f"{player_name} career statistics"]


def _dedupe_queries(queries: List[str]) -> List[str]:
    """Remove duplicate/similar queries."""
    seen = set()
    unique = []

    for q in queries:
        normalized = q.lower().strip()
        # Check if substantially similar query exists
        is_dup = False
        for s in seen:
            if normalized in s or s in normalized:
                is_dup = True
                break
        if not is_dup:
            seen.add(normalized)
            unique.append(q)

    return unique
