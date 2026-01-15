"""
Utility functions for user account management.
"""
from django.contrib.auth import get_user_model
from asgiref.sync import sync_to_async
from app.core.logging import get_logger

User = get_user_model()
logger = get_logger(__name__)


def increment_user_token_usage(user_id: int, tokens: int) -> None:
    """
    Increment token usage for a user (synchronous version).
    
    This is the centralized function to persist token usage to User.token_usage_count.
    This value is cumulative and never decreases, ensuring accurate all-time token tracking
    even when individual chats or sessions are deleted.
    
    Uses F() expressions for atomic updates to avoid race conditions and reduce lock contention.
    This optimization reduces database round trips and improves concurrency.
    
    Should be called whenever tokens are used:
    - LLM calls (chat completions)
    - Embedding model calls
    - Any other token-consuming operations
    
    For async contexts, use increment_user_token_usage_async instead.
    
    Args:
        user_id: User ID
        tokens: Number of tokens to add (must be >= 0)
    """
    if tokens <= 0:
        return
    
    try:
        # Use F() expression for atomic update - reduces lock contention and database round trips
        # This is more efficient than get() + save() as it's a single UPDATE query
        from django.db.models import F
        updated = User.objects.filter(id=user_id).update(
            token_usage_count=F('token_usage_count') + tokens
        )
        if updated > 0:
            logger.debug(f"Incremented token usage for user {user_id}: +{tokens} tokens (atomic update)")
        else:
            logger.warning(f"User {user_id} not found when trying to increment token usage")
    except Exception as e:
        logger.error(f"Error incrementing token usage for user {user_id}: {e}", exc_info=True)


async def increment_user_token_usage_async(user_id: int, tokens: int) -> None:
    """
    Increment token usage for a user (async version for use in async contexts).
    
    Uses F() expressions for atomic updates, reducing lock contention and database round trips.
    
    Args:
        user_id: User ID
        tokens: Number of tokens to add (must be >= 0)
    """
    if tokens <= 0:
        return
    
    try:
        # Use F() expression for atomic update - more efficient than get() + save()
        from django.db.models import F
        updated = await sync_to_async(
            lambda: User.objects.filter(id=user_id).update(
                token_usage_count=F('token_usage_count') + tokens
            )
        )()
        if updated > 0:
            logger.debug(f"Incremented token usage for user {user_id}: +{tokens} tokens (atomic update)")
        else:
            logger.warning(f"User {user_id} not found when trying to increment token usage")
    except Exception as e:
        logger.error(f"Error incrementing token usage for user {user_id}: {e}", exc_info=True)
