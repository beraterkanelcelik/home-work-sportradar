"""
LangGraph Functional API implementation.
"""

from app.agents.functional.agent_workflow import agent_workflow

# Legacy alias for backward compatibility
ai_agent_workflow = agent_workflow

__all__ = ["agent_workflow", "ai_agent_workflow"]
