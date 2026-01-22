"""
Chat service layer for business logic.
"""

from typing import List, Dict, Any, Optional
from django.utils import timezone
from app.db.models.session import ChatSession
from app.db.models.message import Message
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_session(user_id: int, title: Optional[str] = None) -> ChatSession:
    """
    Create a new chat session.

    Optimized to use select_related to prefetch user when needed.
    Uses direct user_id assignment to avoid unnecessary user fetch during creation.

    Args:
        user_id: User ID
        title: Optional session title

    Returns:
        Created ChatSession object with user prefetched
    """
    from django.contrib.auth import get_user_model
    from django.db import transaction

    User = get_user_model()

    # Use transaction.atomic() for consistency
    with transaction.atomic():
        # Verify user exists (minimal query with only id)
        User.objects.only("id").get(id=user_id)

        # Create session with user_id directly (avoids fetching user object)
        session = ChatSession.objects.create(
            user_id=user_id,
            title=title,
        )

        # Prefetch user for later access (single query with select_related)
        # This ensures session.user is available without triggering additional queries
        session = ChatSession.objects.select_related("user").get(id=session.id)

    logger.debug(f"Created chat session {session.id} for user {user_id}")
    return session


def get_user_sessions(user_id: int) -> List[ChatSession]:
    """
    Get all chat sessions for a user.

    Args:
        user_id: User ID

    Returns:
        List of ChatSession objects
    """
    return ChatSession.objects.filter(user_id=user_id).order_by("-updated_at")


def get_session(user_id: int, session_id: int) -> Optional[ChatSession]:
    """
    Get a specific chat session.

    Args:
        user_id: User ID
        session_id: Session ID

    Returns:
        ChatSession object or None if not found
    """
    try:
        return ChatSession.objects.get(id=session_id, user_id=user_id)
    except ChatSession.DoesNotExist:
        return None


def update_session_model(
    user_id: int, session_id: int, model_name: str
) -> Optional[ChatSession]:
    """
    Update the model used for a chat session.

    Args:
        user_id: User ID
        session_id: Session ID
        model_name: Model name to set

    Returns:
        Updated ChatSession object or None if not found
    """
    try:
        session = ChatSession.objects.get(id=session_id, user_id=user_id)
        session.model_used = model_name
        session.save(update_fields=["model_used", "updated_at"])
        logger.debug(f"Updated model for session {session_id} to {model_name}")
        return session
    except ChatSession.DoesNotExist:
        return None


def update_session_title(
    user_id: int, session_id: int, title: str
) -> Optional[ChatSession]:
    """
    Update the title of a chat session.

    Args:
        user_id: User ID
        session_id: Session ID
        title: New title

    Returns:
        Updated ChatSession object or None if not found
    """
    try:
        session = ChatSession.objects.get(id=session_id, user_id=user_id)
        session.title = title
        session.save(update_fields=["title", "updated_at"])
        logger.debug(f"Updated title for session {session_id} to {title}")
        return session
    except ChatSession.DoesNotExist:
        return None


def delete_session(user_id: int, session_id: int) -> bool:
    """
    Delete a chat session and terminate its Temporal workflow.

    Args:
        user_id: User ID
        session_id: Session ID

    Returns:
        True if deleted, False if not found
    """
    try:
        session = ChatSession.objects.get(id=session_id, user_id=user_id)

        # Terminate Temporal workflow before deleting session
        try:
            from asgiref.sync import async_to_sync
            from app.agents.temporal.workflow_manager import terminate_workflow

            # Use async_to_sync instead of creating new event loop
            # This avoids "Future attached to different loop" errors
            async_to_sync(terminate_workflow)(user_id, session_id)
        except Exception as e:
            logger.warning(
                f"Failed to terminate workflow for session {session_id}: {e}"
            )
            # Continue with deletion even if workflow termination fails

        session.delete()
        logger.debug(f"Deleted chat session {session_id} for user {user_id}")
        return True
    except ChatSession.DoesNotExist:
        return False


def delete_all_sessions(user_id: int) -> int:
    """
    Delete all chat sessions for a user and terminate their Temporal workflows.

    Args:
        user_id: User ID

    Returns:
        Number of sessions deleted
    """
    # Get session IDs before deletion
    session_ids = list(
        ChatSession.objects.filter(user_id=user_id).values_list("id", flat=True)
    )
    deleted_count = len(session_ids)

    # Terminate all workflows for this user
    try:
        from asgiref.sync import async_to_sync
        from app.agents.temporal.workflow_manager import (
            terminate_all_workflows_for_user,
        )

        # Use async_to_sync instead of creating new event loop
        # This avoids "Future attached to different loop" errors
        async_to_sync(terminate_all_workflows_for_user)(user_id)
    except Exception as e:
        logger.warning(f"Failed to terminate workflows for user {user_id}: {e}")
        # Continue with deletion even if workflow termination fails

    # Delete all sessions
    ChatSession.objects.filter(user_id=user_id).delete()
    logger.debug(f"Deleted {deleted_count} chat sessions for user {user_id}")
    return deleted_count


def add_message(
    session_id, role, content, tokens_used=0, metadata=None, sender_type="llm"
):
    """
    Add a message to a chat session.
    Updates session and user token usage if tokens_used > 0.

    Optimized to use F() expressions for atomic updates, reducing lock contention
    and database round trips. Uses select_related to fetch user in same query.

    Args:
        session_id: Session ID
        role: Message role (user, assistant, system)
        content: Message content
        tokens_used: Number of tokens used (default 0)
        metadata: Optional metadata dict
        sender_type: 'llm' for LLM context messages, 'ui' for UI-only messages (default 'llm')

    Returns: Message object
    """
    from django.db import transaction
    from django.db.models import F
    from django.utils import timezone

    # Use transaction.atomic() to ensure all operations succeed or fail together
    # Use select_related to fetch user in same query, reducing round trips
    with transaction.atomic():
        # Fetch session with user in single query (select_related optimization)
        session = ChatSession.objects.select_related("user").get(id=session_id)

        # Create message
        message = Message.objects.create(
            session=session,
            role=role,
            content=content,
            tokens_used=tokens_used,
            metadata=metadata or {},
            sender_type=sender_type,
        )

        # Update session token usage and timestamp using F() expression (atomic, reduces lock contention)
        if tokens_used > 0:
            # Use F() expression for atomic update - single UPDATE query, no lock contention
            ChatSession.objects.filter(id=session_id).update(
                tokens_used=F("tokens_used") + tokens_used, updated_at=timezone.now()
            )

            # Use centralized utility function for token persistence (also uses F() now)
            from app.account.utils import increment_user_token_usage

            increment_user_token_usage(session.user.id, tokens_used)
        else:
            # Just update timestamp if no tokens
            ChatSession.objects.filter(id=session_id).update(updated_at=timezone.now())

    logger.debug(
        f"Added message to session {session_id}: role={role}, tokens={tokens_used}, sender_type={sender_type}"
    )

    return message


def get_messages(session_id, sender_type=None, for_llm=False):
    """
    Get messages for a chat session.

    Args:
        session_id: Session ID
        sender_type: Optional filter for sender_type ('llm' or 'ui')
        for_llm: If True, only return messages with sender_type='llm' (for LLM context)

    Returns:
        QuerySet of Message objects
    """
    queryset = Message.objects.filter(session_id=session_id)

    if for_llm:
        # Only return messages that should be included in LLM context
        queryset = queryset.filter(sender_type="llm")
    elif sender_type:
        queryset = queryset.filter(sender_type=sender_type)

    return queryset.order_by("created_at")


def bulk_add_messages(session_id: int, messages: List[Dict[str, Any]]) -> int:
    """
    Bulk add messages to a chat session using efficient batch operations.

    This function uses bulk_create for efficient batch inserts, reducing
    database round trips from N individual inserts to 1 bulk insert.
    Uses database transactions for atomicity and better performance.

    Args:
        session_id: Chat session ID
        messages: List of message dictionaries, each with:
                 - role: str (user, assistant, system)
                 - content: str
                 - tokens_used: int (default 0)
                 - metadata: dict (default {})
                 - sender_type: str ('llm' or 'ui', default 'llm')

    Returns:
        Number of messages created
    """
    from django.db import transaction

    try:
        # Use a single transaction for all operations
        with transaction.atomic():
            # Use skip_locked=True to avoid blocking on locked rows - improves concurrency
            # This allows other operations to proceed instead of waiting for locks
            session = ChatSession.objects.select_for_update(skip_locked=True).get(
                id=session_id
            )

            # Prepare Message objects for bulk_create
            message_objects = []
            total_tokens = 0

            for msg_data in messages:
                role = msg_data.get("role", "assistant")
                content = msg_data.get("content", "")
                tokens_used = msg_data.get("tokens_used", 0)
                metadata = msg_data.get("metadata", {})
                sender_type = msg_data.get("sender_type", "llm")

                message_objects.append(
                    Message(
                        session=session,
                        role=role,
                        content=content,
                        tokens_used=tokens_used,
                        metadata=metadata or {},
                        sender_type=sender_type,
                    )
                )
                total_tokens += tokens_used

            # Bulk create all messages in one query with optimized batch size
            # Batch size of 500 is optimal for most PostgreSQL configurations
            if message_objects:
                created_messages = Message.objects.bulk_create(
                    message_objects,
                    batch_size=500,  # Increased from 100 for better performance
                    ignore_conflicts=False,  # Fail on conflicts for data integrity
                )
                logger.info(
                    f"Bulk created {len(created_messages)} messages for session {session_id}"
                )

                # Update session token usage in single query (within same transaction)
                if total_tokens > 0:
                    # Use F() expressions for atomic updates to avoid race conditions
                    from django.db.models import F

                    ChatSession.objects.filter(id=session_id).update(
                        tokens_used=F("tokens_used") + total_tokens,
                        updated_at=timezone.now(),
                    )

                    # Update user token usage (also atomic)
                    from app.account.utils import increment_user_token_usage

                    increment_user_token_usage(session.user.id, total_tokens)
                else:
                    session.save(update_fields=["updated_at"])

                return len(created_messages)
            else:
                logger.warning(f"No messages to bulk create for session {session_id}")
                return 0

    except ChatSession.DoesNotExist:
        logger.error(f"Session {session_id} not found for bulk_add_messages")
        raise
    except Exception as e:
        logger.error(
            f"Error bulk adding messages to session {session_id}: {e}", exc_info=True
        )
        raise


def get_session_stats(session_id: int) -> Dict[str, Any]:
    """
    Get statistics for a chat session using Langfuse Metrics API.

    Message counts are retrieved from database, while token usage, costs,
    and agent/tool analytics come from Langfuse Metrics API v2.

    Args:
        session_id: Session ID

    Returns:
        Dictionary with session statistics

    Raises:
        ValueError: If Langfuse metrics are unavailable
        ChatSession.DoesNotExist: If session not found
    """
    from app.services.langfuse_metrics import get_session_metrics_from_langfuse

    # 1. Get session from database (for metadata)
    session = ChatSession.objects.select_related("user").get(id=session_id)

    # 2. Get message counts from database (simpler, more reliable)
    messages = Message.objects.filter(session_id=session_id)
    user_messages = messages.filter(role="user").count()
    assistant_messages = messages.filter(role="assistant").count()
    total_messages = messages.count()

    # 3. Query Langfuse Metrics API
    public_key = None
    secret_key = None
    if session.user and session.user.has_custom_langfuse_keys():
        public_key = session.user.langfuse_public_key
        secret_key = session.user.langfuse_secret_key

    langfuse_metrics = get_session_metrics_from_langfuse(
        session_id,
        public_key=public_key,
        secret_key=secret_key,
    )
    if not langfuse_metrics:
        raise ValueError(
            "Langfuse metrics unavailable. Ensure Langfuse is enabled and session has traces."
        )

    # 4. Combine database + Langfuse data
    return {
        "session_id": session_id,
        "title": session.title,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "total_messages": total_messages,
        "user_messages": user_messages,
        "assistant_messages": assistant_messages,
        # From Langfuse Metrics API:
        "total_tokens": langfuse_metrics.get("total_tokens", 0),
        "message_tokens": langfuse_metrics.get(
            "total_tokens", 0
        ),  # Use total_tokens as message_tokens
        "input_tokens": langfuse_metrics.get("input_tokens", 0),
        "output_tokens": langfuse_metrics.get("output_tokens", 0),
        "cached_tokens": langfuse_metrics.get("cached_tokens", 0),
        "model_used": session.model_used,
        "cost": langfuse_metrics.get(
            "cost",
            {
                "total": 0.0,
                "input": 0.0,
                "output": 0.0,
                "cached": 0.0,
            },
        ),
        "agent_usage": langfuse_metrics.get("agent_usage", {}),
        "tool_usage": langfuse_metrics.get("tool_usage", {}),
        "activity_timeline": langfuse_metrics.get(
            "activity_timeline", []
        ),  # User-friendly activity log
    }
