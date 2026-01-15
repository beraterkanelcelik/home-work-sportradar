"""
Planner agent for multi-step task decomposition.
"""
from typing import List, Optional
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from app.agents.agents.base import BaseAgent
from app.core.logging import get_logger

logger = get_logger(__name__)


class PlannerAgent(BaseAgent):
    """
    Agent that analyzes queries and generates structured execution plans.

    This agent is designed to identify multi-step tasks and break them down
    into sequential actions that can be executed by other agents.
    """

    def __init__(self, user_id: Optional[int] = None, model_name: Optional[str] = None):
        super().__init__(
            name="planner",
            description="Planning agent for multi-step task decomposition and execution planning",
            temperature=0.3,  # Lower temperature for more structured, consistent output
            model_name=model_name
        )
        self.user_id = user_id

    def get_system_prompt(self) -> str:
        """Get system prompt for planner agent."""
        return """You are a planning agent that breaks down complex tasks into executable steps.

Your role is to:
1. Analyze user queries to determine if they require multiple steps
2. Generate structured plans for multi-step operations
3. Identify the appropriate agents and tools for each step
4. Ensure steps are in logical sequential order

A task requires planning if it involves:
- Multiple tool calls (e.g., "search for X, then email the results")
- Sequential operations (e.g., "get data, analyze it, create report")
- Multi-part requests (e.g., "do A, B, and C")
- Operations that depend on previous results

For single-step tasks or simple queries, indicate that no planning is needed.

For multi-step tasks, break them down into a sequence of actions where each step specifies:
- The action type (tool execution or direct answer)
- The tool name (if applicable)
- The tool arguments
- Which agent should handle the step
- Context for the agent

Be concise and precise in your planning. Focus on the essential steps needed to complete the task."""

    def get_tools(self) -> List[BaseTool]:
        """
        Get tools available to planner agent.

        The planner typically doesn't need tools as it focuses on analysis
        and planning rather than execution.
        """
        return []
