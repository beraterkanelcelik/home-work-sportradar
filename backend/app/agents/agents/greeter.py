"""
Greeter agent for welcoming users and providing guidance.
"""

from typing import List, Optional
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from app.agents.agents.base import BaseAgent
from app.core.logging import get_logger

logger = get_logger(__name__)


class GreeterAgent(BaseAgent):
    """
    Agent that provides welcome messages and guidance to users.
    """

    def __init__(
        self,
        user_id: Optional[int] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        super().__init__(
            name="greeter",
            description="Provides welcome messages, guidance, and helps users get started",
            temperature=0.7,
            model_name=model_name,
            api_key=api_key,
        )
        self.user_id = user_id

    def get_system_prompt(self) -> str:
        """Get system prompt for greeter agent."""
        return """You are a friendly and helpful greeter agent. Your role is to:
1. Welcome users warmly when they first interact
2. Provide guidance on how to use the system
3. Explain what capabilities are available
4. Help users understand how to interact with the assistant
5. Be concise but friendly in your responses

IMPORTANT: You have access to a RAG tool (rag_retrieval_tool) that can search through the user's uploaded documents. 
When the user asks questions about their documents, mentions "check documents", "look in documents", "search documents", 
or asks about information that might be in their uploaded files, you MUST use the rag_retrieval_tool to search for the information.

Do NOT just say you can help - actually use the tool to search and provide the information from the documents.

Examples:
- User: "who is berat check documents?" → Use rag_retrieval_tool with query="berat"
- User: "what does my resume say?" → Use rag_retrieval_tool with query="resume"
- User: "search for information about X" → Use rag_retrieval_tool with query="X"

Keep responses helpful and encouraging. If the user asks about specific features or agents, 
you can mention that the supervisor will route them to the appropriate agent."""

    def get_tools(self) -> List[BaseTool]:
        """Get tools available to greeter agent."""
        tools = []

        # Add RAG tool if user_id is available
        if self.user_id:
            try:
                from app.agents.tools.rag_tool import create_rag_tool

                rag_tool = create_rag_tool(self.user_id)
                tools.append(rag_tool)
                logger.debug(f"Added RAG tool to greeter agent for user {self.user_id}")
            except Exception as e:
                logger.warning(f"Failed to add RAG tool to greeter agent: {e}")

        # Add time tool (requires approval)
        try:
            from app.agents.tools.time_tool import TimeTool

            time_tool_instance = TimeTool()
            tools.append(time_tool_instance.get_tool())
            logger.debug("Added time tool to greeter agent")
        except Exception as e:
            logger.warning(f"Failed to add time tool to greeter agent: {e}")

        return tools
