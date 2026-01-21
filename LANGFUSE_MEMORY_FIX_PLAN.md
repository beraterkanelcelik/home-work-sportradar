# Langfuse Memory Leak Fix Plan

## Problem Summary

The application creates **new Langfuse clients and callback handlers per request**, causing memory leaks. Each new client spawns background threads that never get released, leading to unbounded memory growth.

**Affected Files:**
- `backend/app/observability/tracing.py` - Creates new clients on every call
- `backend/app/agents/functional/workflow.py` - Calls `get_langfuse_client_for_user()` multiple times per workflow

**Evidence:**
- GitHub Issue #9368: Langfuse worker memory usage exceeds 90% with low CPU
- GitHub Discussion #3901: Memory leak when creating new `LangfuseCallbackHandler()` per invocation

---

## Solution: Per-User Client Caching with Proper Lifecycle Management

### Architecture

```
Before (Memory Leak):
Request 1 → New Langfuse Client → Background Threads (never released)
Request 2 → New Langfuse Client → Background Threads (never released)
Request 3 → New Langfuse Client → Background Threads (never released)
... memory grows unbounded ...

After (Fixed):
Request 1 → Cache Miss → Create Client → Cache[user_key] = client
Request 2 → Cache Hit → Reuse Client (same threads)
Request 3 → Cache Hit → Reuse Client (same threads)
... memory stable ...
```

---

## Todo List

### Phase 1: Implement Client Caching in tracing.py

- [ ] **1.1** Add thread-safe cache dictionary for Langfuse clients
- [ ] **1.2** Modify `get_langfuse_client_for_user()` to check cache before creating new client
- [ ] **1.3** Modify `get_callback_handler_for_user()` to reuse cached clients
- [ ] **1.4** Add `cleanup_user_client()` function for explicit cleanup when needed
- [ ] **1.5** Add `cleanup_all_clients()` function for shutdown scenarios

### Phase 2: Add Periodic Cleanup (Optional LRU)

- [ ] **2.1** Add TTL tracking for cached clients (e.g., 30 minutes idle)
- [ ] **2.2** Implement background cleanup task or LRU eviction
- [ ] **2.3** Call `client.flush()` before removing from cache

### Phase 3: Update Docker Compose Memory Limits

- [ ] **3.1** Add memory limit to backend service (512m limit, 256m reservation)
- [ ] **3.2** Reduce langfuse-web memory (1024m from 1536m)
- [ ] **3.3** Reduce ClickHouse memory (512m from 768m)

### Phase 4: Testing

- [ ] **4.1** Write unit test for client caching (same keys return same client)
- [ ] **4.2** Write unit test for different keys return different clients
- [ ] **4.3** Load test to verify memory stays stable under repeated requests

---

## Implementation Details

### 1. Modified `tracing.py`

```python
"""
Langfuse AI tracing and observability hooks (v3 SDK) - WITH CLIENT CACHING.
"""

import threading
from typing import Optional, Dict, Any
from langfuse.langchain import CallbackHandler
from app.core.config import LANGFUSE_BASE_URL, LANGFUSE_ENABLED
from app.core.logging import get_logger

logger = get_logger(__name__)

# Thread-safe cache for Langfuse clients (keyed by public_key)
_user_langfuse_clients: Dict[str, "Langfuse"] = {}
_user_callback_handlers: Dict[str, CallbackHandler] = {}
_client_lock = threading.Lock()


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
            logger.debug(f"Created and cached Langfuse client for key: {cache_key[:8]}...")
            return client
        except Exception as e:
            logger.error(f"Failed to create Langfuse client: {e}", exc_info=True)
            return None


def get_callback_handler_for_user(
    public_key: str, secret_key: str
) -> Optional[CallbackHandler]:
    """
    Get Langfuse CallbackHandler using cached client.

    Reuses the cached Langfuse client to prevent memory leaks.
    """
    if not LANGFUSE_ENABLED:
        return None
    if not public_key or not secret_key:
        return None

    cache_key = public_key

    with _client_lock:
        # Return cached handler if exists
        if cache_key in _user_callback_handlers:
            return _user_callback_handlers[cache_key]

        # Get or create client, then create handler
        try:
            client = get_langfuse_client_for_user(public_key, secret_key)
            if not client:
                return None

            handler = CallbackHandler(client=client)
            _user_callback_handlers[cache_key] = handler
            logger.debug(f"Created and cached CallbackHandler for key: {cache_key[:8]}...")
            return handler
        except Exception as e:
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
```

### 2. Docker Compose Memory Updates

```yaml
# Add to backend service
backend:
  mem_limit: 512m
  mem_reservation: 256m

# Reduce langfuse-web
langfuse-web:
  mem_limit: 1024m
  mem_reservation: 384m
  environment:
    NODE_OPTIONS: "--max-old-space-size=768"

# Reduce clickhouse
clickhouse:
  mem_limit: 512m
  mem_reservation: 256m
```

### 3. Register Cleanup on Shutdown (asgi.py or manage.py)

```python
import atexit
from app.observability.tracing import cleanup_all_clients

atexit.register(cleanup_all_clients)
```

---

## Expected Results

| Metric | Before | After |
|--------|--------|-------|
| Memory per request | +10-50MB (leaked) | ~0MB (reused) |
| Background threads | Unbounded growth | Fixed per user |
| Total memory (idle) | Growing | Stable |

---

## References

- [GitHub Issue #9368 - Worker Memory Usage](https://github.com/langfuse/langfuse/issues/9368)
- [GitHub Discussion #3901 - Memory Leak Fix](https://github.com/orgs/langfuse/discussions/3901)
- [Langfuse Scaling Guide](https://langfuse.com/self-hosting/scaling)
