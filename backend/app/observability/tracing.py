"""
Langfuse AI tracing and observability hooks (v3 SDK) - WITH CLIENT CACHING.

SDK v3 uses OpenTelemetry and works with Langfuse server v3+.
Reference: https://python.reference.langfuse.com/langfuse
"""

import threading
import time
from typing import Optional, Dict, Any
from langfuse.langchain import CallbackHandler
from app.core.config import (
    LANGFUSE_BASE_URL,
    LANGFUSE_ENABLED,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# Thread-safe cache for Langfuse clients (keyed by public_key)
_user_langfuse_clients: Dict[str, Any] = {}
_user_callback_handlers: Dict[str, CallbackHandler] = {}
_callback_failure_timestamps: Dict[str, float] = {}
_client_lock = threading.Lock()
_CALLBACK_HANDLER_TIMEOUT_SECONDS = 2.0
_CALLBACK_FAILURE_TTL_SECONDS = 60.0


def get_langfuse_client():
    """Env-backed Langfuse client is disabled (per-user keys only)."""
    return None


def get_langfuse_client_for_user(public_key: str, secret_key: str):
    """
    Get or create a cached Langfuse client for user-provided keys.

    Clients are cached by public_key to prevent memory leaks from
    creating new clients (and their background threads) on every request.
    """
    if not LANGFUSE_ENABLED:
        return None
    if not public_key or not secret_key:
        return None

    cache_key = public_key

    with _client_lock:
        # Return cached client if exists
        if cache_key in _user_langfuse_clients:
            return _user_langfuse_clients[cache_key]

        # Create new client and cache it
        try:
            from langfuse import Langfuse

            client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=LANGFUSE_BASE_URL,
            )
            _user_langfuse_clients[cache_key] = client
            logger.debug(
                f"Created and cached Langfuse client for key: {cache_key[:8]}..."
            )
            return client
        except Exception as e:
            logger.error(f"Failed to create Langfuse client: {e}", exc_info=True)
            return None


def get_callback_handler() -> Optional[CallbackHandler]:
    """Env-backed CallbackHandler is disabled (per-user keys only)."""
    return None


def get_callback_handler_for_user(
    public_key: str,
    secret_key: str,
    trace_id: Optional[str] = None,
) -> Optional[CallbackHandler]:
    """
    Get Langfuse CallbackHandler using cached client.

    Reuses the cached Langfuse client to prevent memory leaks. If a trace_id
    is provided, a new handler is created per trace to ensure correct
    association with the current trace.
    """
    if not LANGFUSE_ENABLED:
        return None
    if not public_key or not secret_key:
        return None

    cache_key = public_key
    use_cache = trace_id is None

    with _client_lock:
        if use_cache and cache_key in _user_callback_handlers:
            return _user_callback_handlers[cache_key]

        last_failure = _callback_failure_timestamps.get(cache_key)
        if last_failure and (time.time() - last_failure) < _CALLBACK_FAILURE_TTL_SECONDS:
            return None

    trace_context = {"trace_id": trace_id} if trace_id else None

    try:
        client = get_langfuse_client_for_user(public_key, secret_key)
        if not client:
            with _client_lock:
                _callback_failure_timestamps[cache_key] = time.time()
            return None

        handler_holder: Dict[str, Optional[CallbackHandler]] = {"handler": None}
        error_holder: Dict[str, Optional[Exception]] = {"error": None}

        def _build_handler() -> None:
            try:
                handler_holder["handler"] = CallbackHandler(
                    public_key=public_key,
                    trace_context=trace_context,
                    update_trace=True,
                )
            except Exception as e:
                error_holder["error"] = e

        worker = threading.Thread(target=_build_handler, daemon=True)
        worker.start()
        worker.join(_CALLBACK_HANDLER_TIMEOUT_SECONDS)

        if worker.is_alive():
            with _client_lock:
                _callback_failure_timestamps[cache_key] = time.time()
            logger.warning(
                f"Langfuse CallbackHandler creation timed out after {_CALLBACK_HANDLER_TIMEOUT_SECONDS}s"
            )
            return None

        if error_holder["error"]:
            raise error_holder["error"]

        handler = handler_holder["handler"]
        if handler is None:
            with _client_lock:
                _callback_failure_timestamps[cache_key] = time.time()
            return None

        if use_cache:
            with _client_lock:
                existing = _user_callback_handlers.get(cache_key)
                if existing:
                    return existing
                _user_callback_handlers[cache_key] = handler
            logger.debug(
                f"Created and cached CallbackHandler for key: {cache_key[:8]}..."
            )

        return handler
    except Exception as e:
        with _client_lock:
            _callback_failure_timestamps[cache_key] = time.time()
        logger.error(f"Failed to create CallbackHandler: {e}", exc_info=True)
        return None


def cleanup_user_client(public_key: str):
    """
    Remove and flush a specific user's Langfuse client from cache.

    Call this when a user logs out or changes their API keys.
    """
    with _client_lock:
        if public_key in _user_langfuse_clients:
            client = _user_langfuse_clients.pop(public_key)
            try:
                client.flush()
                client.shutdown()
            except Exception as e:
                logger.warning(f"Error during client cleanup: {e}")

        _user_callback_handlers.pop(public_key, None)


def cleanup_all_clients():
    """
    Flush and shutdown all cached Langfuse clients.

    Call this during application shutdown.
    """
    with _client_lock:
        for key, client in list(_user_langfuse_clients.items()):
            try:
                client.flush()
                client.shutdown()
                logger.debug(f"Cleaned up Langfuse client: {key[:8]}...")
            except Exception as e:
                logger.warning(f"Error cleaning up client {key[:8]}: {e}")

        _user_langfuse_clients.clear()
        _user_callback_handlers.clear()


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
    context: Dict[str, Any] = {
        "user_id": str(user_id),
    }

    if session_id:
        context["session_id"] = str(session_id)

    if metadata:
        metadata_payload: Dict[str, Any] = {}
        for key, value in metadata.items():
            if value is None:
                continue
            metadata_payload[str(key)] = value if isinstance(value, str) else str(value)
        if metadata_payload:
            context["metadata"] = metadata_payload

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
