"""
PostgreSQL checkpoint adapter for LangGraph Functional API.
"""
from typing import Optional, Dict, Any
from langgraph.checkpoint.postgres import PostgresSaver
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_checkpoint_config(chat_session_id: int) -> Dict[str, Any]:
    """
    Get checkpoint configuration for a chat session.
    Uses chat_session_id as the thread_id for checkpoint isolation.
    """
    return {
        "configurable": {
            "thread_id": f"chat_session_{chat_session_id}",
        }
    }
