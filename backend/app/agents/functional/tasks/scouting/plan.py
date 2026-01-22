"""
Dynamic Plan Generation for Agent Workflow.

This module generates executable plans based on user intent.
Plans drive the actual execution - each step maps to a concrete action.

Node 2 in the workflow (after intake/routing).
"""

import json
from typing import Optional, List
from langgraph.func import task
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from app.agents.functional.scouting.schemas import ExecutionPlan, PlanStep, PlanProposal
from app.agents.config import OPENAI_MODEL
from app.core.logging import get_logger

logger = get_logger(__name__)

PLAN_SYSTEM_PROMPT = """You are a sports scouting AI planner. Analyze the user's request and generate an execution plan.

AVAILABLE ACTIONS:
1. rag_search - Search the user's uploaded documents for specific information
   params: {"query": "search query string"}
   
2. extract_player - Extract structured player data (name, positions, physical attributes, strengths/weaknesses) from retrieved evidence
   params: {} (uses accumulated evidence from rag_search steps)
   
3. compose_report - Generate a comprehensive scouting report from extracted player data
   params: {} (uses extracted player fields)
   
4. update_report - Update an existing saved report with new information or revisions
   params: {"feedback": "what to add or change"}
   
5. save_player - Save the player profile and report to the database (requires user approval)
   params: {}
   
6. answer - Generate a final response summarizing findings or answering a question
   params: {}

INTENT TYPES:
- "info_query": User wants information about a player (simple RAG + answer)
- "scouting_report": User wants a full scouting report created and saved
- "update_report": User wants to modify an existing saved report
- "general_chat": General conversation, greeting, or non-player query

PLANNING RULES:
1. For simple info queries ("tell me about X", "what are X's stats"):
   - Use 2-3 rag_search steps for different aspects
   - End with answer step
   - Do NOT include extract_player, compose_report, or save_player
   
2. For scouting report requests ("scout X", "create report on X", "analyze X"):
   - Use 3-4 rag_search steps covering: general info, strengths/weaknesses, physical attributes, stats
   - Include extract_player step
   - Include compose_report step
   - Include save_player step (user will approve before save)
   
3. For update requests ("add more about defense", "update the report"):
   - Use 1-2 rag_search steps for the new information
   - Include update_report step with the feedback
   - Include save_player step
   
4. For general chat:
   - Single answer step

OUTPUT FORMAT (JSON only):
{
    "intent": "info_query" | "scouting_report" | "update_report" | "general_chat",
    "player_name": "Player Name" or null,
    "sport_guess": "nba" | "football" | "unknown" or null,
    "reasoning": "Brief explanation of the plan",
    "steps": [
        {
            "action": "rag_search",
            "description": "Search for LeBron James career statistics",
            "params": {"query": "LeBron James career statistics"}
        },
        ...
    ]
}

Be specific in search queries - include the player name and specific aspect to search for."""


def _generate_default_scouting_plan(
    player_name: str, sport_guess: str
) -> ExecutionPlan:
    """Generate a default scouting report plan."""
    return ExecutionPlan(
        intent="scouting_report",
        player_name=player_name,
        sport_guess=sport_guess,
        reasoning=f"Creating comprehensive scouting report for {player_name}",
        steps=[
            PlanStep(
                action="rag_search",
                description=f"Search for {player_name} general player information",
                params={"query": f"{player_name} player profile background"},
            ),
            PlanStep(
                action="rag_search",
                description=f"Search for {player_name} strengths and weaknesses",
                params={"query": f"{player_name} strengths weaknesses scouting"},
            ),
            PlanStep(
                action="rag_search",
                description=f"Search for {player_name} physical attributes and measurements",
                params={"query": f"{player_name} height weight physical measurements"},
            ),
            PlanStep(
                action="rag_search",
                description=f"Search for {player_name} statistics and performance",
                params={"query": f"{player_name} stats performance statistics"},
            ),
            PlanStep(
                action="extract_player",
                description="Extract structured player data from evidence",
                params={},
            ),
            PlanStep(
                action="compose_report",
                description="Generate comprehensive scouting report",
                params={},
            ),
            PlanStep(
                action="save_player",
                description="Save player profile and report to database",
                params={},
            ),
        ],
    )


def _generate_default_info_plan(player_name: str, query: str) -> ExecutionPlan:
    """Generate a default info query plan."""
    return ExecutionPlan(
        intent="info_query",
        player_name=player_name,
        sport_guess="unknown",
        reasoning=f"Searching for information about {player_name}",
        steps=[
            PlanStep(
                action="rag_search",
                description=f"Search for {player_name} information",
                params={
                    "query": query
                    if player_name.lower() in query.lower()
                    else f"{player_name} {query}"
                },
            ),
            PlanStep(
                action="answer",
                description="Summarize findings",
                params={},
            ),
        ],
    )


@task
def generate_plan(
    message: str,
    player_name: Optional[str] = None,
    sport_guess: Optional[str] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> ExecutionPlan:
    """
    Generate a dynamic execution plan based on user intent.

    Args:
        message: User's message/request
        player_name: Pre-identified player name (if any)
        sport_guess: Pre-identified sport (if any)
        api_key: OpenAI API key
        model_name: Model to use

    Returns:
        ExecutionPlan with concrete steps to execute
    """
    logger.info(f"[PLAN] Generating plan for: {message[:100]}...")

    if not api_key:
        logger.warning("[PLAN] No API key, using default plan")
        if player_name:
            return _generate_default_scouting_plan(
                player_name, sport_guess or "unknown"
            )
        return ExecutionPlan(
            intent="general_chat",
            player_name=None,
            sport_guess=None,
            reasoning="No API key available, defaulting to chat response",
            steps=[
                PlanStep(
                    action="answer",
                    description="Respond to user",
                    params={},
                ),
            ],
        )

    try:
        llm = ChatOpenAI(
            model=model_name or OPENAI_MODEL,
            api_key=api_key,
            temperature=0.2,
        )

        context = f"User message: {message}"
        if player_name:
            context += f"\nIdentified player: {player_name}"
        if sport_guess:
            context += f"\nIdentified sport: {sport_guess}"

        messages = [
            SystemMessage(content=PLAN_SYSTEM_PROMPT),
            HumanMessage(content=context),
        ]

        response = llm.invoke(messages)
        content = response.content.strip()

        # Parse JSON response
        try:
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"[PLAN] Failed to parse LLM response: {e}")
            if player_name:
                return _generate_default_scouting_plan(
                    player_name, sport_guess or "unknown"
                )
            return _generate_default_info_plan(player_name or "player", message)

        # Build ExecutionPlan from response
        intent = data.get("intent", "info_query")
        plan_player_name = data.get("player_name") or player_name
        plan_sport = data.get("sport_guess") or sport_guess
        reasoning = data.get("reasoning", "Generated plan based on user request")

        steps_data = data.get("steps", [])
        if not steps_data:
            logger.warning("[PLAN] No steps in LLM response, using defaults")
            if plan_player_name and intent == "scouting_report":
                return _generate_default_scouting_plan(
                    plan_player_name, plan_sport or "unknown"
                )
            return _generate_default_info_plan(plan_player_name or "player", message)

        # Convert step dicts to PlanStep objects
        steps = []
        for step_data in steps_data:
            try:
                step = PlanStep(
                    action=step_data.get("action", "answer"),
                    description=step_data.get("description", "Execute step"),
                    params=step_data.get("params", {}),
                )
                steps.append(step)
            except Exception as e:
                logger.warning(f"[PLAN] Failed to parse step: {e}")
                continue

        if not steps:
            logger.warning("[PLAN] No valid steps parsed, using defaults")
            if plan_player_name:
                return _generate_default_scouting_plan(
                    plan_player_name, plan_sport or "unknown"
                )
            return _generate_default_info_plan("player", message)

        plan = ExecutionPlan(
            intent=intent,
            player_name=plan_player_name,
            sport_guess=plan_sport,
            reasoning=reasoning,
            steps=steps,
            target_report_id=data.get("target_report_id"),
        )

        logger.info(
            f"[PLAN] Generated {plan.intent} plan with {len(plan.steps)} steps "
            f"for player={plan.player_name}"
        )

        return plan

    except Exception as e:
        logger.error(f"[PLAN] Error generating plan: {e}", exc_info=True)
        if player_name:
            return _generate_default_scouting_plan(
                player_name, sport_guess or "unknown"
            )
        return ExecutionPlan(
            intent="general_chat",
            player_name=None,
            sport_guess=None,
            reasoning=f"Error during planning: {str(e)}",
            steps=[
                PlanStep(
                    action="answer",
                    description="Respond to user",
                    params={},
                ),
            ],
        )


# =============================================================================
# Legacy function for backward compatibility
# =============================================================================


@task
def draft_plan(
    player_name: str,
    sport_guess: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> PlanProposal:
    """
    DEPRECATED: Use generate_plan() instead.

    This function is kept for backward compatibility.
    It generates a simple plan with string descriptions (old format).
    """
    logger.warning("[PLAN] draft_plan is deprecated, use generate_plan instead")

    # Generate the new-style plan
    execution_plan = generate_plan(
        message=f"Create a scouting report for {player_name}",
        player_name=player_name,
        sport_guess=sport_guess,
        api_key=api_key,
        model_name=model_name,
    ).result()

    # Convert to old format
    plan_steps = [step.description for step in execution_plan.steps]

    # Extract query hints from rag_search steps
    query_hints = []
    for step in execution_plan.steps:
        if step.action == "rag_search" and "query" in step.params:
            query_hints.append(step.params["query"])

    return PlanProposal(
        plan_steps=plan_steps,
        query_hints=query_hints[:4],  # Max 4 hints
    )
