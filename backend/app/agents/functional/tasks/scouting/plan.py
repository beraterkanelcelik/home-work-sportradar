"""
Plan task: Generate execution plan for scouting report.

Node 2 in the scouting workflow.
"""

from typing import Optional, List
from langgraph.func import task
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from app.agents.functional.scouting.schemas import PlanProposal
from app.agents.config import OPENAI_MODEL
from app.core.logging import get_logger

logger = get_logger(__name__)

PLAN_SYSTEM_PROMPT = """You are a sports analyst planning a scouting report. Generate a concise plan (4-7 steps) for creating a comprehensive player analysis.

The plan should cover:
1. Confirming player identity and context
2. Retrieving relevant information from documents
3. Extracting key attributes (physical, skills, stats)
4. Drafting the scouting report
5. Preparing structured data
6. Requesting approval
7. Saving results

Also suggest 2-4 query_hints - specific topics to search for based on the player and sport.

Respond in JSON format only:
{
    "plan_steps": [
        "Step 1 description",
        "Step 2 description",
        ...
    ],
    "query_hints": [
        "hint1",
        "hint2"
    ]
}

Keep steps action-oriented and specific to the player/sport context."""


DEFAULT_PLAN_STEPS = [
    "Confirm target player identity and sport context",
    "Retrieve relevant information from uploaded documents",
    "Extract player attributes (physical measurements, positions, teams)",
    "Identify strengths, weaknesses, and playing style",
    "Draft comprehensive scouting report",
    "Prepare structured player database entry",
    "Request approval to save player record",
]


@task
def draft_plan(
    player_name: str,
    sport_guess: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> PlanProposal:
    """
    Generate a plan for the scouting report workflow.

    Args:
        player_name: Target player name
        sport_guess: Guessed sport (nba/football/unknown)
        api_key: OpenAI API key
        model_name: Model to use

    Returns:
        PlanProposal with plan_steps and query_hints
    """
    logger.info(f"[PLAN] Drafting plan for {player_name} ({sport_guess})")

    # Default query hints based on sport
    default_hints = _get_default_hints(sport_guess, player_name)

    if not api_key:
        logger.warning("[PLAN] No API key, using default plan")
        return PlanProposal(
            plan_steps=DEFAULT_PLAN_STEPS,
            query_hints=default_hints,
        )

    try:
        llm = ChatOpenAI(
            model=model_name or OPENAI_MODEL,
            api_key=api_key,
            temperature=0.3,
        )

        messages = [
            SystemMessage(content=PLAN_SYSTEM_PROMPT),
            HumanMessage(
                content=f"Create a plan for scouting report on {player_name} ({sport_guess} player)"
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
        except json.JSONDecodeError:
            logger.warning("[PLAN] Failed to parse LLM response, using defaults")
            return PlanProposal(
                plan_steps=DEFAULT_PLAN_STEPS,
                query_hints=default_hints,
            )

        plan_steps = data.get("plan_steps", DEFAULT_PLAN_STEPS)
        query_hints = data.get("query_hints", default_hints)

        # Enforce 4-7 steps
        if len(plan_steps) < 4:
            plan_steps = DEFAULT_PLAN_STEPS
        elif len(plan_steps) > 7:
            plan_steps = plan_steps[:7]

        result = PlanProposal(
            plan_steps=plan_steps,
            query_hints=query_hints,
        )

        logger.info(
            f"[PLAN] Generated {len(result.plan_steps)} steps, "
            f"{len(result.query_hints)} hints"
        )

        return result

    except Exception as e:
        logger.error(f"[PLAN] Error generating plan: {e}")
        return PlanProposal(
            plan_steps=DEFAULT_PLAN_STEPS,
            query_hints=default_hints,
        )


def _get_default_hints(sport_guess: str, player_name: str) -> List[str]:
    """Get default query hints based on sport."""
    base_hints = [f"{player_name} career highlights"]

    if sport_guess == "nba":
        return base_hints + [
            "shooting percentage",
            "defensive stats",
            "playoff performance",
        ]
    elif sport_guess == "football":
        return base_hints + [
            "passing yards",
            "rushing stats",
            "combine measurements",
        ]
    else:
        return base_hints + [
            "statistics",
            "achievements",
        ]
