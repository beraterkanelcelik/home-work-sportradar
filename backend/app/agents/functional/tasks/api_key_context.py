"""Task helper to resolve APIKeyContext for workflows."""

from typing import Optional
from langgraph.func import task
from app.agents.api_key_context import APIKeyContext


@task
def get_api_key_context(user_id: Optional[int]) -> APIKeyContext:
    return APIKeyContext.from_user(user_id)
