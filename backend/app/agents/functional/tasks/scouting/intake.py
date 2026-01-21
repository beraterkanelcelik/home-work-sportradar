"""
Intake task: Parse user request and extract player information.

Node 1 in the scouting workflow.
"""

from typing import Optional
from langgraph.func import task
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from app.agents.functional.scouting.schemas import IntakeResult
from app.agents.config import OPENAI_MODEL
from app.core.logging import get_logger

logger = get_logger(__name__)

INTAKE_SYSTEM_PROMPT = """You are a sports analyst assistant. Your task is to analyze a user's request and extract:

1. **intent**: The user's intent (should be "scouting_report" for player analysis requests)
2. **player_name**: The full name of the player being requested
3. **sport_guess**: The sport the player plays ("nba" for basketball, "football" for American football, "unknown" if unclear)

Respond in JSON format only:
{
    "intent": "scouting_report",
    "player_name": "Full Player Name",
    "sport_guess": "nba" | "football" | "unknown"
}

Rules:
- Extract the most likely full name from the request
- Use context clues to determine sport (NBA team names, football positions, etc.)
- If you cannot determine the player name, set player_name to null
- Always return valid JSON"""


@task
def intake_and_route_scouting(
    message: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> IntakeResult:
    """
    Parse user request and extract player information.

    Args:
        message: User's request text
        api_key: OpenAI API key
        model_name: Model to use (defaults to OPENAI_MODEL)

    Returns:
        IntakeResult with intent, player_name, sport_guess

    Raises:
        ValueError: If player_name cannot be extracted
    """
    logger.info(f"[INTAKE] Processing request: {message[:100]}...")

    if not api_key:
        raise ValueError("OpenAI API key is required")

    llm = ChatOpenAI(
        model=model_name or OPENAI_MODEL,
        api_key=api_key,
        temperature=0,
    )

    messages = [
        SystemMessage(content=INTAKE_SYSTEM_PROMPT),
        HumanMessage(content=f"User request: {message}"),
    ]

    response = llm.invoke(messages)
    content = response.content.strip()

    # Parse JSON response
    import json
    try:
        # Handle potential markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"[INTAKE] Failed to parse LLM response: {content}")
        raise ValueError(f"Failed to parse intake response: {e}")

    player_name = data.get("player_name")
    if not player_name:
        logger.warning("[INTAKE] Could not extract player name from request")
        raise ValueError(
            "Could not identify the player name from your request. "
            "Please specify the player's full name."
        )

    result = IntakeResult(
        intent=data.get("intent", "scouting_report"),
        player_name=player_name,
        sport_guess=data.get("sport_guess", "unknown"),
    )

    logger.info(
        f"[INTAKE] Extracted: player={result.player_name}, "
        f"sport={result.sport_guess}"
    )

    return result
