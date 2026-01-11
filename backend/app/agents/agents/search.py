"""
Search agent for document search and Q&A using RAG.
"""
from typing import List, Optional
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from app.agents.agents.base import BaseAgent
from app.core.logging import get_logger

logger = get_logger(__name__)


class SearchAgent(BaseAgent):
    """
    Agent that specializes in document search and Q&A using RAG.
    """
    
    def __init__(self, user_id: Optional[int] = None, model_name: Optional[str] = None):
        super().__init__(
            name="search",
            description="Searches through documents and answers questions using RAG",
            temperature=0.7,
            model_name=model_name
        )
        self.user_id = user_id
    
    def get_system_prompt(self) -> str:
        """Get system prompt for search agent."""
        return """You are a search agent specialized in finding and answering questions from user-uploaded documents.

Your primary tool is the rag_retrieval_tool, which searches through the user's uploaded documents to find relevant information.

When a user asks a question:
1. Use rag_retrieval_tool to search for relevant information in their documents
2. Analyze the retrieved context to provide accurate answers
3. Cite sources when referencing specific documents
4. If no relevant information is found, clearly state that

IMPORTANT: Always use the rag_retrieval_tool when the user asks questions that might be answered by their documents. 
Don't just say you can help - actually search and provide information from the documents.

Examples:
- User: "What does my resume say about my experience?" → Use rag_retrieval_tool with query="resume experience"
- User: "Find information about X" → Use rag_retrieval_tool with query="X"
- User: "What's in document Y?" → Use rag_retrieval_tool with query="Y" or document_ids=["Y"]

Be thorough in your searches and provide comprehensive answers based on the retrieved context."""
    
    def get_tools(self) -> List[BaseTool]:
        """Get tools available to search agent."""
        tools = []
        
        # Add RAG tool if user_id is available
        if self.user_id:
            try:
                from app.agents.tools.rag_tool import create_rag_tool
                rag_tool = create_rag_tool(self.user_id)
                tools.append(rag_tool)
                logger.debug(f"Added RAG tool to search agent for user {self.user_id}")
            except Exception as e:
                logger.warning(f"Failed to add RAG tool to search agent: {e}")
        
        return tools
