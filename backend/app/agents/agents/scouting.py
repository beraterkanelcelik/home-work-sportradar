"""
Scouting agent for generating player scouting reports.

This agent delegates to the scouting_workflow for the full 9-node flow.
It primarily exists for registration in the agent factory and routing purposes.
"""

from typing import List, Optional
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.tools import BaseTool
from app.agents.agents.base import BaseAgent
from app.core.logging import get_logger

logger = get_logger(__name__)


class ScoutingAgent(BaseAgent):
    """
    Scouting agent that generates comprehensive player scouting reports.

    This agent is a lightweight wrapper that delegates actual work to
    the scouting_workflow, which implements the full 9-node flow with
    HITL gates for plan and player approval.

    The agent exists primarily for:
    - Registration in AgentFactory
    - Routing by SupervisorAgent
    - Providing metadata for the workflow
    """

    def __init__(
        self,
        user_id: Optional[int] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        super().__init__(
            name="scouting",
            description=(
                "Generates comprehensive scouting reports for sports players. "
                "Analyzes uploaded documents to extract player attributes, "
                "strengths, weaknesses, and projections."
            ),
            temperature=0.3,
            model_name=model_name,
            api_key=api_key,
        )
        self.user_id = user_id

    def get_system_prompt(self) -> str:
        """Get system prompt for scouting agent."""
        return """You are a professional sports scout specializing in player analysis.

Your role is to:
1. Analyze player information from uploaded documents
2. Extract key attributes (physical, skills, stats)
3. Identify strengths and weaknesses
4. Project player roles and development paths
5. Generate comprehensive scouting reports

You provide objective, evidence-based analysis without speculation.
When information is missing, you acknowledge the gaps clearly.

For full scouting reports, use the scouting workflow which provides:
- Plan approval before retrieval
- Evidence-based extraction
- Structured report generation
- Player record creation with approval"""

    def get_tools(self) -> List[BaseTool]:
        """Scouting agent delegates to workflow, no direct tools needed."""
        return []

    def invoke(self, messages: List[BaseMessage], **kwargs) -> AIMessage:
        """
        Handle direct invocation (for simple queries).

        For full scouting reports, the main workflow dispatches to
        scouting_workflow directly. This invoke handles edge cases
        where the agent is called directly.
        """
        logger.info(f"[SCOUTING_AGENT] Direct invoke with {len(messages)} messages")

        # For direct invocation, provide guidance about using the workflow
        # The main workflow should dispatch to scouting_workflow for full reports
        return super().invoke(messages, **kwargs)

    def should_use_workflow(self, message: str) -> bool:
        """
        Determine if a message should trigger the full scouting workflow.

        Args:
            message: User message text

        Returns:
            True if the message is a scouting report request
        """
        message_lower = message.lower()

        scouting_indicators = [
            "scouting report",
            "scout",
            "player profile",
            "player analysis",
            "analyze player",
            "player strengths",
            "player weaknesses",
            "generate report for",
            "create report for",
            "scouting on",
        ]

        return any(indicator in message_lower for indicator in scouting_indicators)
