"""
Graph nodes for the StateGraph workflow.

Each node is a function that takes state and config, and returns state updates.
Nodes use Pydantic models from models.py for validation where appropriate.
"""

from typing import Dict, Any, Optional
from pydantic import ValidationError
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from .state import AgentState, TaskDict
from .tools import TOOLS, TOOL_EXECUTORS
from .prompts import AGENT_SYSTEM_PROMPT
from .events import (
    emit_tasks_updated,
    emit_tool_start,
    emit_tool_complete,
    emit_approval_required,
    emit_plan_proposal,
    emit_plan_step_progress,
    emit_status,
)
from .models import (
    ApprovalPayload,
    ApprovalType,
    SearchDocumentsInput,
    SavePlayerReportInput,
)
from app.agents.graph.streaming import EventCallbackHandler
from app.core.logging import get_logger

logger = get_logger(__name__)


def _get_langfuse_callback(config: RunnableConfig) -> Optional[Any]:
    """
    Get Langfuse CallbackHandler from config for LLM call tracing.

    Returns None if Langfuse is not configured or credentials are missing.
    """
    configurable = config.get("configurable", {})

    public_key = configurable.get("langfuse_public_key")
    secret_key = configurable.get("langfuse_secret_key")
    trace_id = configurable.get("trace_id")

    if not public_key or not secret_key:
        logger.debug("[LANGFUSE] No Langfuse credentials in config, skipping LLM tracing")
        return None

    try:
        from app.observability.tracing import get_callback_handler_for_user

        handler = get_callback_handler_for_user(
            public_key=public_key,
            secret_key=secret_key,
            trace_id=trace_id,
        )

        if handler:
            logger.debug(f"[LANGFUSE] Created CallbackHandler for LLM tracing (trace_id={trace_id[:8] if trace_id else 'none'}...)")
        return handler

    except Exception as e:
        logger.warning(f"[LANGFUSE] Failed to create CallbackHandler: {e}")
        return None


def agent_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Main agent node - reasons and decides next action.

    The agent:
    1. Reviews conversation and current state
    2. If there's an approved plan, executes it step by step
    3. Decides to call a tool OR respond
    4. After gathering info, calls save_player_report for scouting requests
    """
    logger.info(f"[AGENT_NODE] Processing for session={state['session_id']}")

    # Emit status for frontend display
    emit_status(config, "agent", "Processing request...")

    # Get event queue and status messages for streaming
    configurable = config.get("configurable", {})
    event_queue = configurable.get("event_queue")
    status_messages = configurable.get("status_messages", {})

    # Set up callbacks: streaming + Langfuse tracing
    callbacks = []

    # Add event streaming callback for frontend
    if event_queue:
        callbacks.append(EventCallbackHandler(event_queue, status_messages))

    # Add Langfuse callback for LLM call tracing (generations, tokens, latency)
    langfuse_callback = _get_langfuse_callback(config)
    if langfuse_callback:
        callbacks.append(langfuse_callback)
        logger.debug("[AGENT_NODE] Langfuse callback attached for LLM tracing")

    # Create LLM with tools
    llm = ChatOpenAI(
        model="gpt-4o",
        api_key=state["api_key"],
        temperature=0.3,
        streaming=True,
        callbacks=callbacks,
    ).bind_tools(TOOLS)

    # Build context message
    context_parts = []

    # Check if we have an approved plan to execute
    plan = state.get("plan")
    plan_approved = state.get("plan_approved", False)
    current_step_index = state.get("current_step_index", 0)
    player_name = state.get("player_name")

    if plan and plan_approved:
        # Calculate remaining steps
        remaining_steps = [s for s in plan[current_step_index:] if s.get("action") == "search"]
        completed_steps = plan[:current_step_index]

        # Build plan execution context
        plan_context = f"""
## APPROVED PLAN EXECUTION

You have an approved plan to execute for player: {player_name}

**Plan Status:** Step {current_step_index + 1} of {len(plan)}

**Remaining Search Steps:**
"""
        for i, step in enumerate(remaining_steps):
            plan_context += f"\n{i+1}. {step.get('description', 'Search')} - Query: \"{step.get('query', '')}\""

        # Check if all searches are done (current_step_index >= number of search steps)
        search_steps = [s for s in plan if s.get("action") == "search"]
        all_searches_done = current_step_index >= len(search_steps)

        if all_searches_done and state.get("rag_context"):
            plan_context += """

**ALL SEARCHES COMPLETE!**

You have gathered all the information. Now you MUST:
1. Compile the findings into a comprehensive scouting report
2. Call the `save_player_report` tool with:
   - player_name: The player's name
   - report_summary: A 1-2 sentence summary of your findings

This will trigger the player preview for user approval before saving to the database.
DO NOT just respond with text - you MUST call the save_player_report tool!
"""
        elif remaining_steps:
            plan_context += """

**INSTRUCTION:** Execute the next search step by calling `search_documents` with the query above.
Do NOT respond with text - call the tool immediately!
"""

        context_parts.append(plan_context)
        logger.info(f"[AGENT_NODE] Plan execution: step={current_step_index}, total={len(plan)}, searches_done={all_searches_done}")

    if state.get("tasks"):
        task_list = "\n".join([
            f"[{'x' if t['status'] == 'completed' else ' '}] {t['description']}"
            for t in state["tasks"]
        ])
        context_parts.append(f"Current tasks:\n{task_list}")

    if state.get("rag_context"):
        # Truncate for context but indicate there's more
        rag_preview = state['rag_context'][:3000]
        if len(state['rag_context']) > 3000:
            rag_preview += "\n... [truncated, full context available]"
        context_parts.append(f"Information gathered from searches:\n{rag_preview}")

    context_msg = "\n\n".join(context_parts) if context_parts else "No context yet."

    # Invoke LLM
    messages = [
        SystemMessage(content=AGENT_SYSTEM_PROMPT),
        *state["messages"],
    ]

    # Add context as system message if we have any
    if context_parts:
        messages.append(SystemMessage(content=f"[Current State]\n{context_msg}"))

    response = llm.invoke(messages)

    logger.info(f"[AGENT_NODE] Response: has_tool_calls={bool(response.tool_calls)}")

    emit_status(config, "agent", "Request processed", is_completed=True)
    return {
        "messages": [response],
    }


# =============================================================================
# Planner Prompt
# =============================================================================

PLANNER_SYSTEM_PROMPT = """You are a planning assistant for sports scouting.
Analyze the user's request and create a structured execution plan.

For scouting report requests, generate search steps to gather comprehensive information.

Respond with valid JSON only, no markdown formatting:
{
  "player_name": "extracted player name or null",
  "sport_guess": "guessed sport (football, basketball, etc.) or null",
  "is_scouting_request": true/false,
  "plan": [
    {
      "action": "search",
      "description": "Search for player's basic information and career history",
      "query": "player name basic information career history"
    },
    {
      "action": "search",
      "description": "Search for player's statistics and performance",
      "query": "player name statistics performance"
    },
    {
      "action": "search",
      "description": "Search for player's strengths and weaknesses",
      "query": "player name strengths weaknesses analysis"
    },
    {
      "action": "synthesize",
      "description": "Compile findings into comprehensive scouting report",
      "query": null
    }
  ]
}

Rules:
- For scouting requests, generate 3-5 search steps covering different aspects
- Each search step should have a specific, targeted query
- Include a final "synthesize" step to compile the report
- For simple questions, set is_scouting_request to false and plan to empty array
- Always extract player_name if one is mentioned"""


def planner_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Planner node - analyzes request and generates execution plan.

    For scouting requests:
    1. Extracts player name
    2. Generates structured search plan
    3. Emits plan_proposal event
    4. Returns state for plan_approval interrupt

    For simple questions:
    - Skips planning, lets agent handle directly
    """
    import json

    logger.info(f"[PLANNER_NODE] Generating plan for session={state['session_id']}")

    # Emit status for frontend display
    emit_status(config, "planner", "Generating plan...")

    # Get event queue and status messages for streaming
    configurable = config.get("configurable", {})
    event_queue = configurable.get("event_queue")
    status_messages = configurable.get("status_messages", {})

    # Get the user's message
    user_message = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            user_message = msg.content
            break

    if not user_message:
        logger.warning("[PLANNER_NODE] No user message found")
        emit_status(config, "planner", "Plan generated", is_completed=True)
        return {
            "plan": None,
            "plan_approved": True,  # Skip approval if no plan needed
        }

    # Set up callbacks: streaming + Langfuse tracing
    callbacks = []

    # Add event streaming callback for frontend status messages
    if event_queue:
        callbacks.append(EventCallbackHandler(event_queue, status_messages))

    # Add Langfuse callback for LLM call tracing
    langfuse_callback = _get_langfuse_callback(config)
    if langfuse_callback:
        callbacks.append(langfuse_callback)

    planner_llm = ChatOpenAI(
        model="gpt-4o-mini",  # Use faster model for planning
        api_key=state["api_key"],
        temperature=0,
        callbacks=callbacks,
    )

    try:
        response = planner_llm.invoke([
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=f"Create a plan for this request: {user_message}"),
        ])

        # Parse JSON response
        response_text = response.content.strip()
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        plan_data = json.loads(response_text)

        is_scouting = plan_data.get("is_scouting_request", False)
        player_name = plan_data.get("player_name")
        sport_guess = plan_data.get("sport_guess")
        raw_plan = plan_data.get("plan", [])

        if not is_scouting or not raw_plan:
            logger.info("[PLANNER_NODE] Not a scouting request or empty plan, skipping")
            emit_status(config, "planner", "Plan generated", is_completed=True)
            return {
                "plan": None,
                "plan_approved": True,
                "player_name": player_name,
                "sport_guess": sport_guess,
            }

        # Format plan for frontend - add required fields
        formatted_plan = []
        for i, step in enumerate(raw_plan):
            formatted_plan.append({
                "action": step.get("action", "search"),
                "tool": "search_documents" if step.get("action") == "search" else None,
                "query": step.get("query"),
                "agent": "scouting",
                "description": step.get("description", ""),
                "status": "pending",
            })

        logger.info(f"[PLANNER_NODE] Generated plan with {len(formatted_plan)} steps for player={player_name}")

        # Emit plan proposal as update event (for frontend to show plan early)
        emit_plan_proposal(
            config,
            formatted_plan,
            player_name=player_name,
            sport_guess=sport_guess,
            session_id=state["session_id"],
        )
        logger.debug(f"[PLANNER_NODE] Emitted plan_proposal update event")

        # Build approval payload for interrupt
        approval_payload = {
            "type": "plan_proposal",
            "plan": formatted_plan,
            "plan_index": 0,
            "plan_total": len(formatted_plan),
            "player_name": player_name,
            "sport_guess": sport_guess,
            "session_id": state["session_id"],
        }

        emit_status(config, "planner", "Plan generated", is_completed=True)
        return {
            "plan": formatted_plan,
            "plan_approved": False,
            "player_name": player_name,
            "sport_guess": sport_guess,
            "needs_user_approval": True,
            "approval_type": ApprovalType.PLAN_APPROVAL.value,
            "approval_payload": approval_payload,
        }

    except json.JSONDecodeError as e:
        logger.error(f"[PLANNER_NODE] Failed to parse plan JSON: {e}")
        emit_status(config, "planner", "Plan generated", is_completed=True)
        return {
            "plan": None,
            "plan_approved": True,
        }
    except Exception as e:
        logger.error(f"[PLANNER_NODE] Error generating plan: {e}", exc_info=True)
        emit_status(config, "planner", "Plan generated", is_completed=True)
        return {
            "plan": None,
            "plan_approved": True,
        }


def plan_approval_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    HITL plan approval node.

    Uses LangGraph's interrupt() to pause and wait for user approval.
    The interrupt payload contains the plan data for the frontend to display.
    When resumed with Command(resume={approved: true/false}), continues or aborts.
    """
    logger.info(f"[PLAN_APPROVAL_NODE] Requesting plan approval for session={state['session_id']}")

    # Emit status for frontend display
    emit_status(config, "plan_approval", "Awaiting plan approval...")

    # Build the interrupt payload that frontend expects
    interrupt_payload = {
        "type": "plan_approval",
        "plan": state.get("approval_payload"),
        "session_id": state["session_id"],
    }

    logger.info(f"[PLAN_APPROVAL_NODE] Calling interrupt() with payload type={interrupt_payload.get('type')}")

    # Use LangGraph's interrupt() to pause the graph and pass our custom payload
    # This payload will be available in __interrupt__ and sent to the frontend
    resume_value = interrupt(interrupt_payload)

    # Code below runs AFTER the user resumes the workflow
    logger.info(f"[PLAN_APPROVAL_NODE] Resumed with value: {resume_value}")

    # Check if user approved or rejected
    approved = True  # Default to approved
    if isinstance(resume_value, dict):
        approved = resume_value.get("approved", True)

    if not approved:
        logger.info(f"[PLAN_APPROVAL_NODE] Plan rejected by user for session={state['session_id']}")
        emit_status(config, "plan_approval", "Plan rejected", is_completed=True)
        # Return state that will lead to END (no plan to execute)
        return {
            "needs_user_approval": False,
            "approval_type": None,
            "approval_payload": None,
            "plan": None,  # Clear the plan
            "plan_approved": False,
        }

    # Plan was approved - continue execution
    emit_status(config, "plan_approval", "Plan approved", is_completed=True)
    return {
        "needs_user_approval": False,
        "approval_type": None,
        "approval_payload": None,
        "plan_approved": True,
        "current_step_index": 0,  # Start from first step
    }


def tool_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Execute tools called by the agent.

    Tools auto-execute except save_player_report which needs approval.
    Uses Pydantic models for validation of tool inputs and approval payloads.

    When a plan is active, emits plan_step_progress events for the frontend.
    """
    logger.info(f"[TOOL_NODE] Executing tools for session={state['session_id']}")

    # Emit status for frontend display
    emit_status(config, "tools", "Executing tools...")

    last_message = state["messages"][-1]
    tool_calls = last_message.tool_calls

    results = []
    rag_context = state.get("rag_context", "")
    needs_approval = False
    approval_payload = None

    # Plan tracking
    plan = state.get("plan")
    current_step_index = state.get("current_step_index", 0)
    total_steps = len(plan) if plan else 0
    tool_call_count = 0

    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        logger.info(f"[TOOL_NODE] Executing {tool_name}")
        emit_tool_start(config, tool_name, tool_args)

        # Get step name from plan if available
        step_index = current_step_index + tool_call_count
        step_name = tool_name
        if plan and step_index < len(plan):
            step_name = plan[step_index].get("description", tool_name)

        # Emit plan step progress: in_progress
        if plan and total_steps > 0:
            emit_plan_step_progress(
                config,
                step_index,
                total_steps,
                "in_progress",
                step_name,
            )

        # Handle save tool specially (needs approval)
        if tool_name == "save_player_report":
            needs_approval = True

            # Validate tool input using Pydantic
            try:
                validated_input = SavePlayerReportInput(
                    player_name=tool_args.get("player_name", "Unknown"),
                    report_summary=tool_args.get("report_summary", "")
                )
                player_name = validated_input.player_name
                report_summary = validated_input.report_summary
            except ValidationError as e:
                logger.warning(f"[TOOL_NODE] save_player_report input validation error: {e}")
                player_name = tool_args.get("player_name", "Unknown")
                report_summary = tool_args.get("report_summary", "")

            # Build validated approval payload
            try:
                validated_payload = ApprovalPayload(
                    player_name=player_name,
                    report_summary=report_summary,
                    player_data=state.get("player_data"),
                    session_id=state["session_id"],
                    report_text=rag_context,  # Include gathered context for report
                )
                approval_payload = validated_payload.model_dump()
            except ValidationError as e:
                logger.warning(f"[TOOL_NODE] ApprovalPayload validation error: {e}")
                # Fall back to dict if validation fails
                approval_payload = {
                    "player_name": player_name,
                    "report_summary": report_summary,
                    "player_data": state.get("player_data"),
                    "session_id": state["session_id"],
                }

            # Don't execute yet - will execute after approval
            results.append(ToolMessage(
                content="Awaiting user approval to save...",
                tool_call_id=tool_call["id"],
            ))
            continue

        # Execute tool
        executor = TOOL_EXECUTORS.get(tool_name)
        if not executor:
            results.append(ToolMessage(
                content=f"Unknown tool: {tool_name}",
                tool_call_id=tool_call["id"],
            ))
            continue

        try:
            # Inject user context and validate inputs
            if tool_name == "search_documents":
                # Validate search input
                try:
                    validated_input = SearchDocumentsInput(
                        query=tool_args.get("query", "")
                    )
                    query = validated_input.query
                except ValidationError as e:
                    logger.warning(f"[TOOL_NODE] search_documents validation error: {e}")
                    query = tool_args.get("query", "")

                result = executor(
                    query=query,
                    user_id=state["user_id"],
                    api_key=state["api_key"],
                )
                # Accumulate RAG context
                rag_context += f"\n\n### Search: {query}\n{result}"
            else:
                result = executor(**tool_args)

            emit_tool_complete(config, tool_name, True)

            # Emit plan step progress: completed
            if plan and total_steps > 0:
                emit_plan_step_progress(
                    config,
                    step_index,
                    total_steps,
                    "completed",
                    step_name,
                    result=str(result)[:200],  # Truncate for event size
                )

            results.append(ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"],
            ))

        except Exception as e:
            logger.error(f"[TOOL_NODE] Error executing {tool_name}: {e}")
            emit_tool_complete(config, tool_name, False)

            # Emit plan step progress: error
            if plan and total_steps > 0:
                emit_plan_step_progress(
                    config,
                    step_index,
                    total_steps,
                    "error",
                    step_name,
                    result=str(e),
                )

            results.append(ToolMessage(
                content=f"Error: {str(e)}",
                tool_call_id=tool_call["id"],
            ))

        tool_call_count += 1

    emit_status(config, "tools", "Tools executed", is_completed=True)
    return {
        "messages": results,
        "rag_context": rag_context,
        "needs_user_approval": needs_approval,
        "approval_type": ApprovalType.SAVE_PLAYER.value if needs_approval else None,
        "approval_payload": approval_payload,
        "current_step_index": current_step_index + tool_call_count,  # Track progress through plan
    }


# =============================================================================
# Report Composition Prompt
# =============================================================================

COMPOSER_SYSTEM_PROMPT = """You are a professional sports scouting report writer.
Given search results about a player, compose a comprehensive scouting report.

Your task is to:
1. Extract structured player information
2. Identify strengths and weaknesses
3. Write a professional report narrative

Respond with valid JSON only, no markdown formatting:
{
  "player_profile": {
    "display_name": "Full player name",
    "sport": "football" or "basketball" or "nba",
    "positions": ["Position1", "Position2"],
    "teams": ["Current Team"],
    "league": "League name if known",
    "physical": {
      "height_cm": null or number,
      "weight_kg": null or number
    }
  },
  "scouting_assessment": {
    "strengths": ["Strength 1", "Strength 2", "Strength 3"],
    "weaknesses": ["Weakness 1", "Weakness 2"],
    "style_tags": ["Tag1", "Tag2"],
    "role_projection": "Brief description of player's potential role"
  },
  "report_summary": [
    "Key finding 1 in a complete sentence",
    "Key finding 2 in a complete sentence",
    "Key finding 3 in a complete sentence"
  ],
  "report_text": "A comprehensive 3-5 paragraph professional scouting report narrative that covers:\\n\\n1. Player overview and background\\n2. Technical abilities and playing style\\n3. Physical attributes and athleticism\\n4. Areas for improvement\\n5. Overall assessment and potential"
}

Guidelines:
- Extract only information that is present in the search results
- Use null for fields where information is not available
- Write the report_text as a professional scouting narrative
- Include specific details and observations from the search results
- Be objective and analytical in tone
- The report_text should be substantial (at least 200 words)"""


def compose_report_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Compose a comprehensive scouting report from gathered search results.

    This node:
    1. Takes all RAG context (search results)
    2. Uses an LLM to extract structured player data
    3. Generates a professional report narrative
    4. Prepares the approval payload for the player preview
    """
    import json

    logger.info(f"[COMPOSE_REPORT_NODE] Composing report for session={state['session_id']}")

    # Emit status for frontend display
    emit_status(config, "compose_report", "Composing report...")

    # Get event queue and config
    configurable = config.get("configurable", {})
    event_queue = configurable.get("event_queue")
    status_messages = configurable.get("status_messages", {})

    # Get the RAG context (search results)
    rag_context = state.get("rag_context", "")
    player_name = state.get("player_name", "Unknown Player")
    sport_guess = state.get("sport_guess", "unknown")

    if not rag_context:
        logger.warning("[COMPOSE_REPORT_NODE] No RAG context available")
        emit_status(config, "compose_report", "Report composed", is_completed=True)
        # Fall back to basic report
        return {
            "player_data": {
                "display_name": player_name,
                "sport": sport_guess,
            },
            "report_text": f"No detailed information found for {player_name}.",
            "report_summary": [f"Limited information available for {player_name}."],
        }

    # Set up callbacks
    callbacks = []
    if event_queue:
        callbacks.append(EventCallbackHandler(event_queue, status_messages))

    langfuse_callback = _get_langfuse_callback(config)
    if langfuse_callback:
        callbacks.append(langfuse_callback)

    # Create LLM for composition
    composer_llm = ChatOpenAI(
        model="gpt-4o",  # Use full model for quality composition
        api_key=state["api_key"],
        temperature=0.5,  # Slightly higher for more creative writing
        callbacks=callbacks,
    )

    try:
        # Prepare the prompt with search results
        composition_prompt = f"""Compose a scouting report for player: {player_name}
Sport: {sport_guess}

Here are the search results gathered from documents:

{rag_context}

Based on this information, create a comprehensive scouting report following the JSON format specified."""

        response = composer_llm.invoke([
            SystemMessage(content=COMPOSER_SYSTEM_PROMPT),
            HumanMessage(content=composition_prompt),
        ])

        # Parse the JSON response
        response_text = response.content.strip()
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])
            if response_text.startswith("json"):
                response_text = response_text[4:]

        report_data = json.loads(response_text)

        # Extract the composed data
        player_profile = report_data.get("player_profile", {})
        scouting_assessment = report_data.get("scouting_assessment", {})
        report_summary = report_data.get("report_summary", [])
        report_text = report_data.get("report_text", "")

        # Build player_data for approval
        player_data = {
            "display_name": player_profile.get("display_name", player_name),
            "sport": player_profile.get("sport", sport_guess),
            "positions": player_profile.get("positions", []),
            "teams": player_profile.get("teams", []),
            "league": player_profile.get("league"),
            "physical": player_profile.get("physical", {}),
            "scouting": {
                "strengths": scouting_assessment.get("strengths", []),
                "weaknesses": scouting_assessment.get("weaknesses", []),
                "style_tags": scouting_assessment.get("style_tags", []),
                "role_projection": scouting_assessment.get("role_projection"),
            },
        }

        logger.info(f"[COMPOSE_REPORT_NODE] Successfully composed report for {player_name}")
        logger.info(f"[COMPOSE_REPORT_NODE] Report text length: {len(report_text)} chars")

        emit_status(config, "compose_report", "Report composed", is_completed=True)

        # Build approval payload for player preview
        approval_payload = {
            "type": ApprovalType.SAVE_PLAYER.value,
            "player_name": player_data.get("display_name", player_name),
            "player_data": player_data,
            "report_summary": report_summary,
            "report_text": report_text,
            "session_id": state["session_id"],
        }

        return {
            "player_data": player_data,
            "report_text": report_text,
            "report_summary": report_summary,
            "needs_user_approval": True,
            "approval_type": ApprovalType.SAVE_PLAYER.value,
            "approval_payload": approval_payload,
        }

    except json.JSONDecodeError as e:
        logger.error(f"[COMPOSE_REPORT_NODE] Failed to parse composition JSON: {e}")
        emit_status(config, "compose_report", "Report composed", is_completed=True)
        # Fall back to basic report using raw context
        return {
            "player_data": {
                "display_name": player_name,
                "sport": sport_guess,
            },
            "report_text": rag_context[:5000],  # Truncate if too long
            "report_summary": [f"Scouting report for {player_name} compiled from available documents."],
            "needs_user_approval": True,
            "approval_type": ApprovalType.SAVE_PLAYER.value,
            "approval_payload": {
                "type": ApprovalType.SAVE_PLAYER.value,
                "player_name": player_name,
                "player_data": {"display_name": player_name, "sport": sport_guess},
                "report_summary": [f"Scouting report for {player_name}"],
                "report_text": rag_context[:5000],
                "session_id": state["session_id"],
            },
        }
    except Exception as e:
        logger.error(f"[COMPOSE_REPORT_NODE] Error composing report: {e}", exc_info=True)
        emit_status(config, "compose_report", "Report composed", is_completed=True)
        # Fall back to basic report
        return {
            "player_data": {
                "display_name": player_name,
                "sport": sport_guess,
            },
            "report_text": rag_context[:5000] if rag_context else f"Report for {player_name}",
            "report_summary": [f"Scouting report for {player_name}"],
            "needs_user_approval": True,
            "approval_type": ApprovalType.SAVE_PLAYER.value,
            "approval_payload": {
                "type": ApprovalType.SAVE_PLAYER.value,
                "player_name": player_name,
                "player_data": {"display_name": player_name, "sport": sport_guess},
                "report_summary": [f"Report for {player_name}"],
                "report_text": rag_context[:5000] if rag_context else "",
                "session_id": state["session_id"],
            },
        }


def approval_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    HITL approval node for save_player.

    Uses LangGraph's interrupt() to pause and wait for user approval.
    The interrupt payload contains the player data for the frontend to display.
    When resumed with Command(resume={...}), processes the decision and executes save.
    """
    logger.info(f"[APPROVAL_NODE] Requesting save_player approval for session={state['session_id']}")

    # Emit status for frontend display
    emit_status(config, "approval", "Awaiting player approval...")

    # Build the interrupt payload that frontend expects
    approval_payload = state.get("approval_payload", {})
    interrupt_payload = {
        "type": state["approval_type"],  # "save_player"
        **approval_payload,
    }

    # Use LangGraph's interrupt() to pause the graph
    resume_value = interrupt(interrupt_payload)

    # Code below runs AFTER the user resumes the workflow
    logger.info(f"[APPROVAL_NODE] Resumed with value: {resume_value}")

    # Check user's decision
    action = "approve"  # Default
    if isinstance(resume_value, dict):
        action = resume_value.get("action", "approve")
        # Also check 'approved' field for backward compatibility
        if "approved" in resume_value and not resume_value.get("approved"):
            action = "reject"

    if action == "reject":
        logger.info(f"[APPROVAL_NODE] Player save rejected for session={state['session_id']}")
        emit_status(config, "approval", "Save cancelled", is_completed=True)
        # Add a message indicating rejection
        return {
            "needs_user_approval": False,
            "approval_type": None,
            "approval_payload": None,
            "messages": [AIMessage(content="Player save cancelled. Let me know if you'd like to make any changes or create a different report.")],
        }

    # User approved - execute the save!
    logger.info(f"[APPROVAL_NODE] Player approved, executing save for session={state['session_id']}")

    try:
        # Get data from approval payload
        player_name = approval_payload.get("player_name", "Unknown Player")
        report_text = approval_payload.get("report_text", state.get("rag_context", ""))
        player_data = approval_payload.get("player_data") or {}
        user_id = state["user_id"]

        # Execute the save
        executor = TOOL_EXECUTORS.get("save_player_report")
        if executor:
            emit_tool_start(config, "save_player_report", {"player_name": player_name})

            result = executor(
                player_name=player_name,
                player_data=player_data,
                report_text=report_text,
                user_id=user_id,
            )

            # Result is a dict with success, player_id, report_id, message
            if result.get("success"):
                emit_tool_complete(config, "save_player_report", True)
                logger.info(f"[APPROVAL_NODE] Successfully saved player_id={result.get('player_id')} report_id={result.get('report_id')}")

                # Create success message
                success_message = f"""Player and scouting report saved successfully!

**Player:** {player_name}
**Player ID:** {result.get('player_id')}
**Report ID:** {result.get('report_id')}

The report has been saved and is now available in your Scout Reports page."""

                emit_status(config, "approval", "Player saved", is_completed=True)
                return {
                    "needs_user_approval": False,
                    "approval_type": None,
                    "approval_payload": None,
                    "messages": [AIMessage(content=success_message)],
                    "player_data": {
                        "player_id": result.get("player_id"),
                        "report_id": result.get("report_id"),
                        "player_name": player_name,
                    },
                }
            else:
                emit_tool_complete(config, "save_player_report", False)
                error_msg = result.get("error", "Unknown error")
                logger.error(f"[APPROVAL_NODE] Save failed: {error_msg}")
                emit_status(config, "approval", "Save failed", is_completed=True)
                return {
                    "needs_user_approval": False,
                    "approval_type": None,
                    "approval_payload": None,
                    "messages": [AIMessage(content=f"Error saving player report: {error_msg}. Please try again.")],
                }
        else:
            logger.error("[APPROVAL_NODE] save_player_report executor not found")
            emit_status(config, "approval", "Save failed", is_completed=True)
            return {
                "needs_user_approval": False,
                "approval_type": None,
                "approval_payload": None,
                "messages": [AIMessage(content="Error: Could not save player report. Please try again.")],
            }

    except Exception as e:
        logger.error(f"[APPROVAL_NODE] Error saving player: {e}", exc_info=True)
        emit_tool_complete(config, "save_player_report", False)
        emit_status(config, "approval", "Save failed", is_completed=True)
        return {
            "needs_user_approval": False,
            "approval_type": None,
            "approval_payload": None,
            "messages": [AIMessage(content=f"Error saving player report: {str(e)}. Please try again.")],
        }
