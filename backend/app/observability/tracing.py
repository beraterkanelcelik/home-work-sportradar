"""
Langfuse AI tracing and observability hooks (v3 SDK).

SDK v3 uses OpenTelemetry and works with Langfuse server v3+.
Reference: https://python.reference.langfuse.com/langfuse
"""

from typing import Optional, Dict, Any
from langfuse.langchain import CallbackHandler
from app.core.config import (
    LANGFUSE_BASE_URL,
    LANGFUSE_ENABLED,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_langfuse_client():
    """Env-backed Langfuse client is disabled (per-user keys only)."""
    return None


def get_langfuse_client_for_user(public_key: str, secret_key: str):
    """Create a Langfuse client for user-provided keys (no singleton)."""
    if not LANGFUSE_ENABLED:
        return None
    if not public_key or not secret_key:
        return None
    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=LANGFUSE_BASE_URL,
        )
    except Exception as e:
        logger.error(f"Failed to create Langfuse client for user: {e}", exc_info=True)
        return None


def get_callback_handler() -> Optional[CallbackHandler]:
    """Env-backed CallbackHandler is disabled (per-user keys only)."""
    return None


def get_callback_handler_for_user(
    public_key: str, secret_key: str
) -> Optional[CallbackHandler]:
    """Get Langfuse CallbackHandler using user-provided keys."""
    if not LANGFUSE_ENABLED:
        return None
    if not public_key or not secret_key:
        return None
    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=public_key, secret_key=secret_key, host=LANGFUSE_BASE_URL
        )
        return CallbackHandler(client=client)
    except Exception as e:
        logger.error(f"Failed to create CallbackHandler for user: {e}", exc_info=True)
        return None


def prepare_trace_context(
    user_id: int,
    session_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Prepare trace context for propagate_attributes().

    This returns a dictionary that can be used with propagate_attributes()
    to set user_id, session_id, and metadata on traces.

    Args:
        user_id: User ID
        session_id: Optional session ID
        metadata: Optional additional metadata

    Returns:
        Dictionary with user_id, session_id, and metadata for propagate_attributes()
    """
    context = {
        "user_id": str(user_id),
    }

    if session_id:
        context["session_id"] = str(session_id)

    if metadata:
        # Convert metadata values to strings (required by propagate_attributes)
        for key, value in metadata.items():
            context[f"metadata.{key}"] = (
                str(value) if not isinstance(value, str) else value
            )

    return context


def flush_traces():
    """
    Flush all pending traces to Langfuse.

    This ensures traces are sent immediately rather than waiting for background processes.
    Should be called in short-lived applications or before shutdown.
    """
    if not LANGFUSE_ENABLED:
        return

    try:
        client = get_langfuse_client()
        if client and hasattr(client, "flush"):
            client.flush()
            logger.debug("Flushed Langfuse traces")
    except Exception as e:
        logger.error(f"Failed to flush Langfuse traces: {e}", exc_info=True)


def shutdown_client():
    """
    Gracefully shutdown the Langfuse client.

    This flushes all pending data and waits for background threads to finish.
    Should be called before application exit.
    """
    if not LANGFUSE_ENABLED:
        return

    try:
        client = get_langfuse_client()
        if client and hasattr(client, "shutdown"):
            client.shutdown()
            logger.debug("Shutdown Langfuse client")
    except Exception as e:
        logger.error(f"Failed to shutdown Langfuse client: {e}", exc_info=True)
