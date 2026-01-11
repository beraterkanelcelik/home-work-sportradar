"""
Middleware setup for LangGraph Functional API.
"""
from typing import Any, Optional
from langchain_core.runnables import Runnable
from langgraph.checkpoint.base import BaseCheckpointSaver
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_agent_with_summarization(
    agent: Runnable,
    model_name: str,
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> Runnable:
    """
    Wrap agent with SummarizationMiddleware from LangChain.
    
    SummarizationMiddleware automatically summarizes conversation history when
    approaching token limits, preserving recent messages while compressing older context.
    
    Note: SummarizationMiddleware is designed for agents created with `create_agent()`.
    For our custom BaseAgent, we apply it if the agent supports `with_config()`.
    If not, we return the agent as-is (summarization will be handled by checkpointing).
    
    Args:
        agent: Agent runnable to wrap
        model_name: Model name for summarization (uses cheaper model if available)
        checkpointer: Optional checkpointer for state persistence
        
    Returns:
        Wrapped agent with SummarizationMiddleware or original agent if unavailable
    """
    try:
        from langchain.agents.middleware import SummarizationMiddleware
        from langchain_openai import ChatOpenAI
        from app.agents.config import OPENAI_API_KEY
        
        # Use a cheaper model for summarization (e.g., gpt-4o-mini)
        # If model_name is already a mini model, use it; otherwise use default mini
        summary_model = "gpt-4o-mini" if "mini" not in model_name.lower() else model_name
        
        summarization_middleware = SummarizationMiddleware(
            model=ChatOpenAI(
                model=summary_model,
                api_key=OPENAI_API_KEY,
                temperature=0,
            ),
            trigger=("tokens", 40000),  # Trigger summarization at 4000 tokens
            keep=("messages", 20),  # Keep last 20 messages
        )
        
        # Try to wrap agent with middleware
        # Note: This works for agents created with create_agent()
        # For our custom BaseAgent, we check if with_config is available
        if hasattr(agent, 'with_config'):
            try:
                wrapped_agent = agent.with_config({
                    "middleware": [summarization_middleware],
                })
                logger.debug(f"Wrapped agent with SummarizationMiddleware (trigger: 4000 tokens, keep: 20 messages)")
                return wrapped_agent
            except Exception as e:
                logger.debug(f"Agent doesn't support middleware wrapping: {e}, using agent as-is")
                return agent
        else:
            # Agent doesn't support with_config, return as-is
            # Summarization will be handled by checkpointing and message management
            logger.debug("Agent doesn't support with_config, summarization handled by checkpointing")
            return agent
            
    except ImportError:
        logger.debug("SummarizationMiddleware not available (langchain.agents.middleware), using agent as-is")
        return agent
    except Exception as e:
        logger.warning(f"Error setting up SummarizationMiddleware: {e}, using agent as-is")
        return agent
