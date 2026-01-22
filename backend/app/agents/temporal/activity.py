"""
Temporal activities for running LangGraph workflows and publishing to Redis.
"""

import json
import os
import asyncio
import time
import contextlib
from temporalio import activity
from temporalio.exceptions import ApplicationError
from pydantic import BaseModel, validator
from typing import Dict, Any, Optional
from app.agents.api_key_context import APIKeyContext
from app.agents.functional.models import AgentRequest
from app.agents.functional.workflow import ai_agent_workflow_events
from langgraph.types import Command
from app.core.redis import get_redis_client, RobustRedisPublisher, get_message_buffer
from app.core.logging import get_logger
from app.settings import REDIS_PUBLISH_CONCURRENCY

logger = get_logger(__name__)


class ChatActivityInput(BaseModel):
    """Validated activity input."""

    chat_id: int
    state: Dict[str, Any]

    @validator("state")
    def validate_state(cls, v):
        """Validate state dictionary."""
        # Ensure required fields
        if "user_id" not in v:
            raise ValueError("state must contain user_id")
        # Limit state size to prevent unbounded growth
        state_size = len(json.dumps(v, default=str))
        if state_size > 1_000_000:  # 1MB limit
            raise ValueError(f"state too large: {state_size} bytes")
        return v


class ChatActivityOutput(BaseModel):
    """Structured activity output."""

    status: str  # "completed", "interrupted", "error"
    message_id: Optional[int] = None
    error: Optional[str] = None
    interrupt_data: Optional[Dict] = None
    event_count: int = 0
    has_response: bool = False


class PublishTaskTracker:
    """
    Tracks async publish tasks for proper cleanup before activity returns.

    This prevents CancelledError exceptions when the activity completes while
    publish tasks are still in-flight. Without tracking, orphaned tasks get
    cancelled when the event loop shuts down.
    """

    def __init__(self, semaphore: asyncio.Semaphore):
        self._tasks: set[asyncio.Task] = set()
        self._semaphore = semaphore

    def create_task(self, coro, event_type: str, event_count: int) -> asyncio.Task:
        """Create and track a publish task."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)

        # Add done callback for cleanup and semaphore release
        task.add_done_callback(lambda t: self._on_task_done(t, event_type, event_count))
        return task

    def _on_task_done(
        self, task: asyncio.Task, event_type: str, event_count: int
    ) -> None:
        """Handle task completion: remove from tracking, release semaphore, log errors."""
        # Remove from tracking set
        self._tasks.discard(task)

        # Log any errors (but not cancellation - that's expected during cleanup)
        try:
            if not task.cancelled() and task.exception():
                logger.error(
                    f"[REDIS_PUBLISH] Publish task failed for {event_type} (event_count={event_count}): {task.exception()}"
                )
        except Exception:
            pass  # Ignore errors in callback
        finally:
            # Always release semaphore
            try:
                self._semaphore.release()
            except Exception:
                pass

    async def wait_for_pending(self, timeout: float = 5.0) -> None:
        """
        Wait for all pending publish tasks to complete with timeout.

        Args:
            timeout: Maximum seconds to wait for tasks to complete
        """
        if not self._tasks:
            return

        pending_count = len(self._tasks)
        logger.debug(
            f"[REDIS_PUBLISH] Waiting for {pending_count} pending publish tasks (timeout={timeout}s)"
        )

        try:
            # Copy set since it may be modified during iteration
            pending = list(self._tasks)
            if pending:
                done, not_done = await asyncio.wait(
                    pending, timeout=timeout, return_when=asyncio.ALL_COMPLETED
                )

                if not_done:
                    logger.warning(
                        f"[REDIS_PUBLISH] {len(not_done)} publish tasks did not complete within {timeout}s, cancelling"
                    )
                    for task in not_done:
                        task.cancel()
                    # Wait briefly for cancellation to propagate
                    await asyncio.gather(*not_done, return_exceptions=True)
                else:
                    logger.debug(
                        f"[REDIS_PUBLISH] All {len(done)} pending publish tasks completed"
                    )
        except Exception as e:
            logger.warning(f"[REDIS_PUBLISH] Error waiting for pending tasks: {e}")


def _handle_publish_task_done(
    task: asyncio.Task, event_type: str, event_count: int, semaphore: asyncio.Semaphore
) -> None:
    """
    Callback to handle publish task completion, log errors, and release semaphore.

    DEPRECATED: Use PublishTaskTracker instead for new code.

    Args:
        task: Completed publish task
        event_type: Event type for logging
        event_count: Event count for logging
        semaphore: Semaphore to release
    """
    try:
        if not task.cancelled() and task.exception():
            logger.error(
                f"[REDIS_PUBLISH] Publish task failed for {event_type} (event_count={event_count}): {task.exception()}"
            )
    except Exception:
        pass  # Ignore errors in callback
    finally:
        # Always release semaphore, even if there was an error
        try:
            semaphore.release()
        except Exception:
            pass  # Ignore semaphore release errors


async def _serialize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serialize event for Redis publishing, handling Pydantic models.

    Args:
        event: Event dictionary

    Returns:
        Serializable event dictionary
    """
    serializable_event = event.copy() if isinstance(event, dict) else event

    # Convert AgentResponse objects to dicts
    if isinstance(serializable_event, dict) and "response" in serializable_event:
        response = serializable_event["response"]
        if hasattr(response, "model_dump"):  # Pydantic v2
            serializable_event["response"] = response.model_dump()
        elif hasattr(response, "dict"):  # Pydantic v1
            serializable_event["response"] = response.dict()

    return serializable_event


async def _publish_event_async(
    publisher: RobustRedisPublisher,
    channel: str,
    event: Dict[str, Any],
    event_count: int,
    message_buffer=None,
) -> None:
    """
    Background task for non-blocking Redis publish using RobustRedisPublisher.

    Args:
        publisher: RobustRedisPublisher instance
        channel: Redis channel name
        event: Event dictionary to publish
        event_count: Event count for logging
        message_buffer: Optional MessageBuffer for storing events
    """
    try:
        serializable_event = await _serialize_event(event)

        # Publish using robust publisher with retry logic
        success = await publisher.publish(channel, serializable_event)

        if success:
            # Add to message buffer for catch-up support
            if message_buffer:
                await message_buffer.add(channel, serializable_event)

            event_type = event.get("type", "unknown")
            # Only log non-token events for debugging (token events are too verbose)
            if event_type != "token":
                logger.debug(
                    f"[REDIS_PUBLISH] Published event type={event_type} to {channel} (event_count={event_count})"
                )
        else:
            event_type = event.get("type", "unknown")
            logger.warning(
                f"[REDIS_PUBLISH] Failed to publish event type={event_type} to {channel} (event_count={event_count})"
            )
    except Exception as e:
        logger.error(f"[REDIS_PUBLISH] Error in background publish: {e}", exc_info=True)


async def _run_chat_activity_async(
    input_data: Any,
    api_key_ctx: Optional[APIKeyContext] = None,
) -> Dict[str, Any]:
    """
    Activity with proper error handling and heartbeating.

    Args:
        input_data: ChatActivityInput (Pydantic model or dict)

    Returns:
        ChatActivityOutput as dict
    """
    try:
        # Validate input using Pydantic
        if isinstance(input_data, dict):
            validated_input = ChatActivityInput(**input_data)
        elif isinstance(input_data, ChatActivityInput):
            validated_input = input_data
        else:
            # Try to convert dataclass to dict then validate
            if hasattr(input_data, "__dict__"):
                validated_input = ChatActivityInput(**input_data.__dict__)
            else:
                raise ValueError(f"Invalid input_data type: {type(input_data)}")

        chat_id = validated_input.chat_id
        state = validated_input.state
        user_id = state["user_id"]

        # Extract message and other parameters
        message = state.get("message", "")
        session_id = state.get("session_id", chat_id)

        logger.info(
            f"[ACTIVITY_START] Starting activity for chat_id={chat_id}, message_preview={message[:50] if message else '(empty)'}..., user_id={user_id}, session_id={session_id}"
        )

        # Check if this is a resume operation (has resume_payload)
        resume_payload = state.get("resume_payload")
        is_resume = resume_payload is not None

        # Allow empty message for resume operations, but require it for initial runs
        if not message and not is_resume:
            logger.error(f"[ACTIVITY_ERROR] No message in state for chat_id={chat_id}")
            return ChatActivityOutput(
                status="error", error="No message provided", event_count=0
            ).dict()

        # Initialize Redis and Langfuse
        redis_client = await get_redis_client()
        tenant_id = state.get("tenant_id") or user_id
        tenant_id = str(tenant_id)
        channel = f"chat:{tenant_id}:{chat_id}"

        # Send initial heartbeat
        activity.heartbeat({"status": "initialized", "chat_id": chat_id})

        # Fetch API keys
        if api_key_ctx is None:
            api_key_ctx = await APIKeyContext.from_user_async(user_id)

        # Create root Langfuse trace if enabled (for activity-level tracing)
        trace_id = None
        langfuse_trace = None
        from app.agents.config import LANGFUSE_ENABLED

        if LANGFUSE_ENABLED:
            try:
                import uuid
                from app.observability.tracing import get_langfuse_client_for_user

                langfuse = None
                if api_key_ctx.langfuse_public_key and api_key_ctx.langfuse_secret_key:
                    langfuse = get_langfuse_client_for_user(
                        api_key_ctx.langfuse_public_key,
                        api_key_ctx.langfuse_secret_key,
                    )

                if langfuse:
                    # Generate deterministic trace ID
                    trace_seed = f"{chat_id}-{user_id}-{uuid.uuid4()}"
                    trace_id = (
                        langfuse.create_trace_id(seed=trace_seed)
                        if hasattr(langfuse, "create_trace_id")
                        else str(uuid.uuid4())
                    )

                    # Create root trace using start_observation with trace_context
                    # Use trace_context to set the trace_id - this creates/associates with the trace
                    # Use as_type="span" for the root observation (trace is created automatically)
                    # user_id and session_id are stored in metadata for trace identification
                    langfuse_trace = langfuse.start_observation(
                        as_type="span",
                        trace_context={"trace_id": trace_id},
                        name="chat_activity",
                        metadata={
                            "chat_id": chat_id,
                            "user_id": str(user_id) if user_id else None,
                            "session_id": str(chat_id) if chat_id else None,
                            "flow": state.get("flow", "main"),
                        },
                    )
                    logger.info(
                        f"[LANGFUSE] Created root trace id={trace_id} for chat_id={chat_id}"
                    )
            except Exception as e:
                logger.warning(f"Failed to create Langfuse trace: {e}", exc_info=True)

        # Check for resume_payload (from human-in-the-loop interrupt resume)
        resume_payload = state.get("resume_payload")
        if resume_payload:
            logger.info(
                f"[HITL] [ACTIVITY_RESUME] Activity re-run with resume_payload: session={chat_id}, run_id={resume_payload.get('run_id')}"
            )

        # Build AgentRequest or Command for resume
        if resume_payload:
            request = Command(resume=resume_payload)
            logger.info(
                f"[HITL] Injected resume_payload into workflow: session={chat_id}, run_id={resume_payload.get('run_id')}"
            )
        else:
            request = AgentRequest(
                query=state.get("message", ""),
                session_id=chat_id,
                user_id=user_id,
                org_slug=state.get("org_slug"),
                org_roles=state.get("org_roles", []),
                app_roles=state.get("app_roles", []),
                flow=state.get("flow", "main"),
                plan_steps=state.get("plan_steps"),
                trace_id=trace_id,
                run_id=state.get("run_id"),
                parent_message_id=state.get("parent_message_id"),
                openai_api_key=api_key_ctx.openai_api_key,
                langfuse_public_key=api_key_ctx.langfuse_public_key,
                langfuse_secret_key=api_key_ctx.langfuse_secret_key,
            )

        # Streaming mode: use .stream() and publish to Redis
        logger.info(f"[ACTIVITY] Executing in stream mode: session={chat_id}")

        # Initialize Redis and build channel for streaming
        tenant_id = state.get("tenant_id") or user_id
        tenant_id = str(tenant_id)  # Ensure it's a string
        channel = f"chat:{tenant_id}:{chat_id}"
        logger.info(
            f"Starting chat activity for chat_id={chat_id}, channel={channel} (tenant_id={tenant_id}, user_id={user_id})"
        )

        # Get Redis client and create robust publisher
        try:
            redis_client = await get_redis_client()
            publisher = RobustRedisPublisher(redis_client)
            message_buffer = await get_message_buffer()
        except Exception as e:
            logger.error(
                f"Failed to get Redis client for stream mode chat_id={chat_id}: {e}",
                exc_info=True,
            )
            redis_client = None
            publisher = None
            message_buffer = None

        event_count = [0]  # Use list for mutable closure
        final_response = None
        interrupt_data = None  # Track interrupt data for resume
        interrupt_output = None
        message_id = None

        HEARTBEAT_INTERVAL = 10

        async def heartbeat_loop():
            try:
                while True:
                    activity.heartbeat(
                        {
                            "status": "running",
                            "chat_id": chat_id,
                            "event_count": event_count[0],
                        }
                    )
                    await asyncio.sleep(HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                return

        # Semaphore for backpressure: cap concurrent publish operations
        publish_semaphore = asyncio.Semaphore(REDIS_PUBLISH_CONCURRENCY)
        # Track publish tasks for proper cleanup before activity returns
        publish_tracker = PublishTaskTracker(publish_semaphore)

        heartbeat_task = asyncio.create_task(heartbeat_loop())

        # Run workflow using ai_agent_workflow_events()
        # Publish to Redis directly in the loop (non-blocking) to ensure tasks execute properly
        try:
            accumulated_content = ""
            tokens_used = 0
            async for event in ai_agent_workflow_events(
                request,
                session_id=chat_id,
                user_id=user_id,
                trace_id=trace_id,
            ):
                # Check for cancellation
                if activity.is_cancelled():
                    raise ApplicationError("Activity cancelled", non_retryable=True)

                event_type = event.get("type", "unknown")
                if event_type == "token":
                    accumulated_content += event.get("value", "")
                event_count[0] += 1

                # Publish event to Redis (fire-and-forget, non-blocking with backpressure)
                if publisher:
                    # DESIGN NOTE: Backpressure strategy
                    # Current approach: semaphore throttles ALL events (including tokens)
                    # - When Redis is slow, this slows down token consumption, which can slow upstream LLM streaming
                    # - This protects the system from unbounded memory growth (current priority)
                    # Alternative approach (for "best-effort tokens"):
                    # - Drop token events when semaphore saturated, but always publish interrupt/final/error
                    # - This keeps LLM streaming fast but may drop some tokens under load
                    # Current choice: throttle all events to protect system stability

                    # Acquire semaphore before creating task (prevents unbounded in-flight tasks)
                    current_count = event_count[0]
                    try:
                        await publish_semaphore.acquire()
                        publish_tracker.create_task(
                            _publish_event_async(
                                publisher, channel, event, current_count, message_buffer
                            ),
                            event_type,
                            current_count,
                        )
                        # Note: No need for asyncio.sleep(0) - semaphore already throttles and tasks will execute
                    except Exception as e:
                        # If task creation fails, release semaphore
                        try:
                            publish_semaphore.release()
                        except Exception:
                            pass
                        logger.error(
                            f"[REDIS_PUBLISH] Failed to create publish task for {event_type} (event_count={current_count}): {e}",
                            exc_info=True,
                        )

                # Check for interrupt (LangGraph native interrupt pattern)
                if event.get("type") == "interrupt":
                    interrupt_data = event.get("data") or event.get("interrupt")
                    logger.info(
                        f"[HITL] [INTERRUPT] Workflow interrupted for chat_id={chat_id}, interrupt_data={interrupt_data}"
                    )
                    # Publish interrupt event to Redis for frontend (tracked for cleanup)
                    if publisher:
                        try:
                            await publish_semaphore.acquire()
                            publish_tracker.create_task(
                                _publish_event_async(
                                    publisher,
                                    channel,
                                    event,
                                    event_count[0],
                                    message_buffer,
                                ),
                                "interrupt",
                                event_count[0],
                            )
                        except Exception as e:
                            try:
                                publish_semaphore.release()
                            except Exception:
                                pass
                            logger.warning(
                                f"[REDIS_PUBLISH] Failed to publish interrupt event: {e}"
                            )
                    interrupt_output = ChatActivityOutput(
                        status="interrupted",
                        interrupt_data=interrupt_data,
                        event_count=event_count[0],
                    ).dict()
                    break

                # Capture final response (for message_saved event and DB persistence)
                if event.get("type") == "final":
                    final_response = event.get("response")
                    if final_response and hasattr(final_response, "token_usage"):
                        tokens_used = final_response.token_usage.get("total_tokens", 0)

                    # Save assistant message to DB IMMEDIATELY for durability
                    # This ensures messages aren't lost if user refreshes before workflow closes
                    if final_response:
                        try:
                            from asgiref.sync import sync_to_async
                            from app.services.chat_service import add_message
                            from app.agents.config import OPENAI_MODEL

                            # Extract message data from response
                            content = (
                                final_response.reply
                                if hasattr(final_response, "reply")
                                else str(final_response)
                            )
                            metadata = {}
                            tokens_used = 0

                            if hasattr(final_response, "token_usage"):
                                tokens_used = final_response.token_usage.get(
                                    "total_tokens", 0
                                )
                                metadata.update(
                                    {
                                        "input_tokens": final_response.token_usage.get(
                                            "input_tokens", 0
                                        ),
                                        "output_tokens": final_response.token_usage.get(
                                            "output_tokens", 0
                                        ),
                                        "cached_tokens": final_response.token_usage.get(
                                            "cached_tokens", 0
                                        ),
                                        "model": OPENAI_MODEL,
                                    }
                                )

                            if hasattr(final_response, "agent_name"):
                                metadata["agent_name"] = final_response.agent_name

                            if hasattr(final_response, "tool_calls"):
                                metadata["tool_calls"] = final_response.tool_calls

                            # Save to DB immediately for durability
                            saved_message = await sync_to_async(add_message)(
                                session_id=chat_id,
                                role="assistant",
                                content=content,
                                tokens_used=tokens_used,
                                metadata=metadata,
                            )
                            message_id = saved_message.id
                            logger.info(
                                f"Saved new assistant message ID={message_id} session={chat_id}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"[MESSAGE_SAVE] Failed to save assistant message to DB: {e}, will retry on workflow close",
                                exc_info=True,
                            )
                            message_id = None

                            # Fallback: Add to workflow buffer for persistence on workflow close
                            try:
                                from app.agents.temporal.workflow_manager import (
                                    get_workflow_id,
                                )
                                from app.core.temporal import get_temporal_client

                                client = await get_temporal_client()
                                workflow_id = get_workflow_id(user_id, chat_id)
                                workflow_handle = client.get_workflow_handle(
                                    workflow_id
                                )

                                await workflow_handle.signal(
                                    "add_message_to_buffer",
                                    args=("assistant", content, metadata, tokens_used),
                                )
                                logger.info(
                                    f"[WORKFLOW_BUFFER] Added assistant message to workflow buffer as fallback for session {chat_id}"
                                )
                            except Exception as buffer_error:
                                logger.error(
                                    f"[WORKFLOW_BUFFER] Failed to add message to workflow buffer: {buffer_error}"
                                )
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

        # Wait for all pending publish tasks before returning
        # This prevents CancelledError when activity returns with in-flight tasks
        await publish_tracker.wait_for_pending(timeout=5.0)

        if interrupt_output is not None:
            return interrupt_output

        # Emit message_saved event for assistant message after final event
        # Now with real DB ID since we save immediately
        if final_response and redis_client and chat_id and publisher:
            try:
                message_saved_event = {
                    "type": "message_saved",
                    "data": {
                        "role": "assistant",
                        "db_id": message_id,  # Real DB ID (or None if save failed)
                        "session_id": chat_id,
                        "buffered": message_id
                        is None,  # Only buffered if DB save failed
                    },
                }
                # Track message_saved event for proper cleanup
                await publish_semaphore.acquire()
                publish_tracker.create_task(
                    _publish_event_async(
                        publisher,
                        channel,
                        message_saved_event,
                        event_count[0] + 1,
                        message_buffer,
                    ),
                    "message_saved",
                    event_count[0] + 1,
                )
                logger.info(
                    f"[MESSAGE_SAVED_EVENT] Emitted assistant message event for session={chat_id} db_id={message_id}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to emit message_saved event for assistant message: {e}",
                    exc_info=True,
                )

        if final_response and publisher:
            # Include response data in done event so frontend gets the reply without needing to reload
            response_data = {}
            if hasattr(final_response, "reply"):
                response_data["reply"] = final_response.reply
            if hasattr(final_response, "type"):
                response_data["type"] = final_response.type
            if hasattr(final_response, "agent_name"):
                response_data["agent_name"] = final_response.agent_name

            done_event = {
                "type": "done",
                "data": {
                    "final_text": accumulated_content,
                    "tokens_used": tokens_used,
                    "trace_id": trace_id,
                    "response": response_data if response_data else None,
                },
            }
            try:
                await publish_semaphore.acquire()
                publish_tracker.create_task(
                    _publish_event_async(
                        publisher,
                        channel,
                        done_event,
                        event_count[0] + 1,
                        message_buffer,
                    ),
                    "done",
                    event_count[0] + 1,
                )
            except Exception as e:
                logger.warning(f"Failed to publish done event: {e}")

        # Wait for final publish tasks before proceeding to cleanup
        await publish_tracker.wait_for_pending(timeout=5.0)

        # End Langfuse trace if created and flush traces
        if langfuse_trace:
            try:
                langfuse_trace.end()
                logger.debug(f"[LANGFUSE] Ended trace id={trace_id}")
            except Exception as e:
                logger.warning(f"Failed to end Langfuse trace: {e}", exc_info=True)

        # Flush Langfuse traces to ensure they're sent
        if LANGFUSE_ENABLED:
            try:
                from app.observability.tracing import flush_traces

                flush_traces()
                logger.debug(f"[LANGFUSE] Flushed traces for chat_id={chat_id}")
            except Exception as e:
                logger.warning(f"Failed to flush Langfuse traces: {e}", exc_info=True)

        # Interrupt should have been handled above - if we reach here, workflow completed normally

        # Send final heartbeat
        activity.heartbeat(
            {"status": "completed", "chat_id": chat_id, "event_count": event_count[0]}
        )
        logger.info(f"Chat activity completed for chat_id={chat_id}")

        # Message ID is not available yet since message is in workflow buffer
        # Will be assigned when messages are persisted on workflow close
        message_id = None

        # Return structured output
        return ChatActivityOutput(
            status="completed",
            message_id=message_id,
            event_count=event_count[0],
            has_response=bool(final_response),
        ).dict()

    except ApplicationError:
        raise  # Don't wrap ApplicationError
    except Exception as e:
        logger.exception(
            f"Activity error for chat {validated_input.chat_id if 'validated_input' in locals() else 'unknown'}"
        )
        # Wrap in ApplicationError for proper handling
        raise ApplicationError(
            str(e),
            type="CHAT_ACTIVITY_ERROR",
            non_retryable=False,  # Allow retry for transient errors
        )


@activity.defn
def run_chat_activity(input_data: Any) -> Dict[str, Any]:
    """
    Synchronous wrapper to run async chat activity in thread pool.

    Running the async activity in a dedicated event loop keeps the worker
    event loop free to process workflow tasks, preventing workflow task timeouts
    during long LLM calls.
    """
    api_key_ctx = None
    try:
        user_id = None
        if isinstance(input_data, dict):
            user_id = (input_data.get("state") or {}).get("user_id")
        elif isinstance(input_data, ChatActivityInput):
            user_id = input_data.state.get("user_id")

        if user_id is not None:
            try:
                api_key_ctx = APIKeyContext.from_user(user_id)
            except Exception as e:
                # May fail due to Django async context detection
                logger.debug(
                    f"Sync API key fetch failed, will retry in async context: {e}"
                )
                api_key_ctx = None  # Will be fetched in async context
        else:
            api_key_ctx = APIKeyContext.from_env()
    except Exception as e:
        logger.warning(f"Failed to load API keys for activity: {e}")

    return asyncio.run(_run_chat_activity_async(input_data, api_key_ctx=api_key_ctx))


@activity.defn
async def bulk_persist_messages_activity(
    chat_id: int, messages: list
) -> Dict[str, Any]:
    """
    Bulk persist messages to database using efficient batch operations.

    This activity is called when a workflow closes to persist all buffered messages
    in a single transaction, reducing database overhead significantly.

    Args:
        chat_id: Chat session ID
        messages: List of message dictionaries from workflow buffer
                 Each dict should have: role, content, metadata, tokens_used, timestamp

    Returns:
        Dictionary with persistence results
    """
    from asgiref.sync import sync_to_async
    from app.db.models.message import Message
    from app.db.models.session import ChatSession
    from app.account.utils import increment_user_token_usage
    from app.agents.config import OPENAI_MODEL

    try:
        logger.info(
            f"[BULK_PERSIST] Starting bulk persist for session {chat_id} with {len(messages)} messages"
        )

        # Use sync_to_async to wrap Django ORM operations
        @sync_to_async
        def persist_messages():
            # Get session
            try:
                session = ChatSession.objects.get(id=chat_id)
            except ChatSession.DoesNotExist:
                logger.error(f"[BULK_PERSIST] Session {chat_id} not found")
                return {"success": False, "error": "Session not found", "persisted": 0}

            # Update model_used if not set
            if not session.model_used:
                session.model_used = OPENAI_MODEL
                session.save(update_fields=["model_used"])

            # Prepare Message objects for bulk_create
            message_objects = []
            total_tokens = 0

            for msg_data in messages:
                role = msg_data.get("role", "assistant")
                content = msg_data.get("content", "")
                metadata = msg_data.get("metadata", {})
                tokens_used = msg_data.get("tokens_used", 0)

                message_objects.append(
                    Message(
                        session=session,
                        role=role,
                        content=content,
                        tokens_used=tokens_used,
                        metadata=metadata,
                    )
                )
                total_tokens += tokens_used

            # Bulk create all messages in one query with optimized batch size
            # Use larger batch size (500) for better performance with increased DB memory
            if message_objects:
                from django.db import transaction
                from django.db.models import F
                from django.utils import timezone

                # Use transaction for atomicity
                with transaction.atomic():
                    created_messages = Message.objects.bulk_create(
                        message_objects,
                        batch_size=500,  # Increased from 100 for better performance
                        ignore_conflicts=False,
                    )
                    logger.info(
                        f"[BULK_PERSIST] Created {len(created_messages)} messages for session {chat_id}"
                    )

                    # Update session token usage atomically using F() expressions
                    if total_tokens > 0:
                        ChatSession.objects.filter(id=chat_id).update(
                            tokens_used=F("tokens_used") + total_tokens,
                            updated_at=timezone.now(),
                        )

                        # Update user token usage
                        increment_user_token_usage(session.user.id, total_tokens)

                return {
                    "success": True,
                    "persisted": len(created_messages),
                    "total_tokens": total_tokens,
                }
            else:
                logger.warning(
                    f"[BULK_PERSIST] No messages to persist for session {chat_id}"
                )
                return {"success": True, "persisted": 0, "total_tokens": 0}

        result = await persist_messages()
        logger.info(
            f"[BULK_PERSIST] Completed bulk persist for session {chat_id}: {result}"
        )
        return result

    except Exception as e:
        logger.error(
            f"[BULK_PERSIST] Error bulk persisting messages for session {chat_id}: {e}",
            exc_info=True,
        )
        raise ApplicationError(
            f"Failed to bulk persist messages: {str(e)}",
            type="BULK_PERSIST_ERROR",
            non_retryable=False,  # Allow retry for transient errors
        )
