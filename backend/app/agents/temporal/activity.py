"""
Temporal activities for running LangGraph workflows and publishing to Redis.
"""
import json
import os
import asyncio
import time
from temporalio import activity
from temporalio.exceptions import ApplicationError
from pydantic import BaseModel, validator
from typing import Dict, Any, Optional
from app.agents.runner import AgentRunner
from app.core.redis import get_redis_client, RobustRedisPublisher, get_message_buffer
from app.core.logging import get_logger
from app.settings import REDIS_PUBLISH_CONCURRENCY

logger = get_logger(__name__)


class ChatActivityInput(BaseModel):
    """Validated activity input."""
    chat_id: int
    state: Dict[str, Any]
    
    @validator('state')
    def validate_state(cls, v):
        """Validate state dictionary."""
        # Ensure required fields
        if 'user_id' not in v:
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


def _handle_publish_task_done(task: asyncio.Task, event_type: str, event_count: int, semaphore: asyncio.Semaphore) -> None:
    """
    Callback to handle publish task completion, log errors, and release semaphore.
    
    Args:
        task: Completed publish task
        event_type: Event type for logging
        event_count: Event count for logging
        semaphore: Semaphore to release
    """
    try:
        if task.exception():
            logger.error(f"[REDIS_PUBLISH] Publish task failed for {event_type} (event_count={event_count}): {task.exception()}", exc_info=True)
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
        if hasattr(response, 'model_dump'):  # Pydantic v2
            serializable_event["response"] = response.model_dump()
        elif hasattr(response, 'dict'):  # Pydantic v1
            serializable_event["response"] = response.dict()
    
    return serializable_event


async def _publish_event_async(
    publisher: RobustRedisPublisher,
    channel: str,
    event: Dict[str, Any],
    event_count: int,
    message_buffer = None
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

            event_type = event.get('type', 'unknown')
            # Only log non-token events for debugging (token events are too verbose)
            if event_type != "token":
                logger.debug(f"[REDIS_PUBLISH] Published event type={event_type} to {channel} (event_count={event_count})")
        else:
            event_type = event.get('type', 'unknown')
            logger.warning(f"[REDIS_PUBLISH] Failed to publish event type={event_type} to {channel} (event_count={event_count})")
    except Exception as e:
        logger.error(f"[REDIS_PUBLISH] Error in background publish: {e}", exc_info=True)


@activity.defn
async def run_chat_activity(input_data: Any) -> Dict[str, Any]:
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
            if hasattr(input_data, '__dict__'):
                validated_input = ChatActivityInput(**input_data.__dict__)
            else:
                raise ValueError(f"Invalid input_data type: {type(input_data)}")
        
        chat_id = validated_input.chat_id
        state = validated_input.state
        user_id = state["user_id"]
        
        # Extract message and other parameters
        message = state.get("message", "")
        session_id = state.get("session_id", chat_id)
        
        logger.info(f"[ACTIVITY_START] Starting activity for chat_id={chat_id}, message_preview={message[:50] if message else '(empty)'}..., user_id={user_id}, session_id={session_id}")

        # Check if this is a resume operation (has resume_payload)
        resume_payload = state.get("resume_payload")
        is_resume = resume_payload is not None

        # Allow empty message for resume operations, but require it for initial runs
        if not message and not is_resume:
            logger.error(f"[ACTIVITY_ERROR] No message in state for chat_id={chat_id}")
            return ChatActivityOutput(
                status="error",
                error="No message provided",
                event_count=0
            ).dict()
        
        # Initialize Redis and Langfuse
        redis_client = await get_redis_client()
        tenant_id = state.get("tenant_id") or user_id
        tenant_id = str(tenant_id)
        channel = f"chat:{tenant_id}:{chat_id}"
        
        # Heartbeat tracking
        last_heartbeat = time.time()
        HEARTBEAT_INTERVAL = 10
        
        async def maybe_heartbeat():
            nonlocal last_heartbeat
            now = time.time()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                activity.heartbeat(f"Processing chat {chat_id}")
                last_heartbeat = now
        
        # Send initial heartbeat
        activity.heartbeat({"status": "initialized", "chat_id": chat_id})
        
        # Create root Langfuse trace if enabled (for activity-level tracing)
        trace_id = None
        langfuse_trace = None
        from app.agents.config import LANGFUSE_ENABLED
        if LANGFUSE_ENABLED:
            try:
                from langfuse import get_client
                import uuid
                langfuse = get_client()
                if langfuse:
                    # Generate deterministic trace ID
                    user_id = state.get("user_id")
                    trace_seed = f"{chat_id}-{user_id}-{uuid.uuid4()}"
                    trace_id = langfuse.create_trace_id(seed=trace_seed) if hasattr(langfuse, 'create_trace_id') else str(uuid.uuid4())
                    
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
                        }
                    )
                    logger.info(f"[LANGFUSE] Created root trace id={trace_id} for chat_id={chat_id}")
            except Exception as e:
                logger.warning(f"Failed to create Langfuse trace: {e}", exc_info=True)
        
        # Check for resume_payload (from human-in-the-loop interrupt resume)
        resume_payload = state.get("resume_payload")
        if resume_payload:
            logger.info(f"[HITL] [ACTIVITY_RESUME] Activity re-run with resume_payload: session={chat_id}")
        
        # Create AgentRunner - this handles request building, trace context, etc.
        # If resume_payload is provided, runner will use Command(resume=...) instead of AgentRequest
        runner = AgentRunner(
            user_id=state.get("user_id"),
            chat_session_id=chat_id,
            message=state.get("message", ""),
            plan_steps=state.get("plan_steps"),
            flow=state.get("flow", "main"),
            trace_id=trace_id,  # Pass activity-generated trace_id to runner
            org_slug=state.get("org_slug"),
            org_roles=state.get("org_roles", []),
            app_roles=state.get("app_roles", []),
            resume_payload=resume_payload,  # Pass resume_payload for interrupt resume
            run_id=state.get("run_id"),  # Correlation ID for /run polling
            parent_message_id=state.get("parent_message_id"),  # Parent message ID for correlation
        )
        
        if resume_payload:
            logger.info(f"[HITL] Injected resume_payload into AgentRunner: session={chat_id}")
        
        # Streaming mode: use .stream() and publish to Redis
        logger.info(f"[ACTIVITY] Executing in stream mode: session={chat_id}")
        
        # Initialize Redis and build channel for streaming
        tenant_id = state.get("tenant_id") or user_id
        tenant_id = str(tenant_id)  # Ensure it's a string
        channel = f"chat:{tenant_id}:{chat_id}"
        logger.info(f"Starting chat activity for chat_id={chat_id}, channel={channel} (tenant_id={tenant_id}, user_id={user_id})")
        
        # Get Redis client and create robust publisher
        try:
            redis_client = await get_redis_client()
            publisher = RobustRedisPublisher(redis_client)
            message_buffer = await get_message_buffer()
        except Exception as e:
            logger.error(f"Failed to get Redis client for stream mode chat_id={chat_id}: {e}", exc_info=True)
            redis_client = None
            publisher = None
            message_buffer = None
        
        # Heartbeat tracking
        last_heartbeat = time.time()
        HEARTBEAT_INTERVAL = 10
        
        async def maybe_heartbeat():
            nonlocal last_heartbeat
            now = time.time()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                activity.heartbeat(f"Processing chat {chat_id}")
                last_heartbeat = now
        
        final_response = None
        event_count = [0]  # Use list for mutable closure
        interrupt_data = None  # Track interrupt data for resume
        message_id = None
        
        # Semaphore for backpressure: cap concurrent publish operations
        publish_semaphore = asyncio.Semaphore(REDIS_PUBLISH_CONCURRENCY)
        
        # Run workflow using AgentRunner.stream()
        # Publish to Redis directly in the loop (non-blocking) to ensure tasks execute properly
        async for event in runner.stream():
            await maybe_heartbeat()
            
            # Check for cancellation
            if activity.is_cancelled():
                raise ApplicationError("Activity cancelled", non_retryable=True)
            
            event_type = event.get('type', 'unknown')
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
                    task = asyncio.create_task(_publish_event_async(publisher, channel, event, current_count, message_buffer))
                    # Add done callback to release semaphore and log errors
                    # Semaphore is released in callback, not here, to ensure it's always released
                    task.add_done_callback(lambda t, et=event_type, ec=current_count, sem=publish_semaphore: _handle_publish_task_done(t, et, ec, sem))
                    # Note: No need for asyncio.sleep(0) - semaphore already throttles and tasks will execute
                except Exception as e:
                    # If task creation fails, release semaphore
                    try:
                        publish_semaphore.release()
                    except Exception:
                        pass
                    logger.error(f"[REDIS_PUBLISH] Failed to create publish task for {event_type} (event_count={current_count}): {e}", exc_info=True)
            
            
            # Check for interrupt (LangGraph native interrupt pattern)
            if event.get("type") == "interrupt":
                interrupt_data = event.get("data") or event.get("interrupt")
                logger.info(f"[HITL] [INTERRUPT] Workflow interrupted for chat_id={chat_id}, interrupt_data={interrupt_data}")
                # Publish interrupt event to Redis for frontend
                if publisher:
                    asyncio.create_task(_publish_event_async(publisher, channel, event, event_count[0], message_buffer))
                return ChatActivityOutput(
                    status="interrupted",
                    interrupt_data=interrupt_data,
                    event_count=event_count[0]
                ).dict()
            
            # Capture final response (for message_saved event and workflow buffer)
            if event.get("type") == "final":
                final_response = event.get("response")
                
                # Add assistant message to workflow buffer instead of immediate DB write
                # This optimizes DB operations by batching writes on workflow close
                if final_response:
                    try:
                        from app.agents.temporal.workflow_manager import get_workflow_id
                        from app.core.temporal import get_temporal_client
                        
                        # Get workflow handle to signal
                        client = await get_temporal_client()
                        workflow_id = get_workflow_id(user_id, chat_id)
                        workflow_handle = client.get_workflow_handle(workflow_id)
                        
                        # Extract message data from response
                        content = final_response.reply if hasattr(final_response, 'reply') else str(final_response)
                        metadata = {}
                        tokens_used = 0
                        
                        if hasattr(final_response, 'token_usage'):
                            tokens_used = final_response.token_usage.get("total_tokens", 0)
                            metadata.update({
                                "input_tokens": final_response.token_usage.get("input_tokens", 0),
                                "output_tokens": final_response.token_usage.get("output_tokens", 0),
                                "cached_tokens": final_response.token_usage.get("cached_tokens", 0),
                            })
                        
                        if hasattr(final_response, 'agent_name'):
                            metadata["agent_name"] = final_response.agent_name
                        
                        if hasattr(final_response, 'tool_calls'):
                            metadata["tool_calls"] = final_response.tool_calls
                        
                        # Signal workflow to add message to buffer
                        await workflow_handle.signal(
                            "add_message_to_buffer",
                            args=("assistant", content, metadata, tokens_used)
                        )
                        logger.info(f"[WORKFLOW_BUFFER] Added assistant message to workflow buffer for session {chat_id}")
                    except Exception as e:
                        logger.warning(f"[WORKFLOW_BUFFER] Failed to add message to workflow buffer: {e}, will fall back to DB write")
                        # Continue - save_message_task will handle DB write as fallback
        
        # Emit message_saved event for assistant message after final event
        # Note: Message is now in workflow buffer, will be persisted on workflow close
        # For frontend compatibility, we emit a temporary event indicating message is buffered
        if final_response and redis_client and chat_id:
            try:
                # Message is in workflow buffer, not yet in DB
                # Emit event with temporary indicator that message will be persisted on workflow close
                message_saved_event = {
                    "type": "message_saved",
                    "data": {
                        "role": "assistant",
                        "db_id": None,  # Will be assigned when persisted on workflow close
                        "session_id": chat_id,
                        "buffered": True,  # Indicates message is in workflow buffer
                    }
                }
                # Use fire-and-forget for message_saved event
                asyncio.create_task(_publish_event_async(publisher, channel, message_saved_event, event_count[0] + 1, message_buffer))
                logger.info(f"[MESSAGE_SAVED_EVENT] Emitted buffered assistant message event for session={chat_id}")
            except Exception as e:
                logger.warning(f"Failed to emit message_saved event for assistant message: {e}", exc_info=True)
        
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
        activity.heartbeat({"status": "completed", "chat_id": chat_id, "event_count": event_count[0]})
        logger.info(f"Chat activity completed for chat_id={chat_id}")
        
        # Message ID is not available yet since message is in workflow buffer
        # Will be assigned when messages are persisted on workflow close
        message_id = None
        
        # Return structured output
        return ChatActivityOutput(
            status="completed",
            message_id=message_id,
            event_count=event_count[0],
            has_response=bool(final_response)
        ).dict()
        
    except ApplicationError:
        raise  # Don't wrap ApplicationError
    except Exception as e:
        logger.exception(f"Activity error for chat {validated_input.chat_id if 'validated_input' in locals() else 'unknown'}")
        # Wrap in ApplicationError for proper handling
        raise ApplicationError(
            str(e),
            type="CHAT_ACTIVITY_ERROR",
            non_retryable=False  # Allow retry for transient errors
        )


@activity.defn
async def bulk_persist_messages_activity(chat_id: int, messages: list) -> Dict[str, Any]:
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
        logger.info(f"[BULK_PERSIST] Starting bulk persist for session {chat_id} with {len(messages)} messages")
        
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
                session.save(update_fields=['model_used'])
            
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
                        metadata=metadata
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
                        ignore_conflicts=False
                    )
                    logger.info(f"[BULK_PERSIST] Created {len(created_messages)} messages for session {chat_id}")
                    
                    # Update session token usage atomically using F() expressions
                    if total_tokens > 0:
                        ChatSession.objects.filter(id=chat_id).update(
                            tokens_used=F('tokens_used') + total_tokens,
                            updated_at=timezone.now()
                        )
                        
                        # Update user token usage
                        increment_user_token_usage(session.user.id, total_tokens)
                
                return {
                    "success": True,
                    "persisted": len(created_messages),
                    "total_tokens": total_tokens
                }
            else:
                logger.warning(f"[BULK_PERSIST] No messages to persist for session {chat_id}")
                return {"success": True, "persisted": 0, "total_tokens": 0}
        
        result = await persist_messages()
        logger.info(f"[BULK_PERSIST] Completed bulk persist for session {chat_id}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"[BULK_PERSIST] Error bulk persisting messages for session {chat_id}: {e}", exc_info=True)
        raise ApplicationError(
            f"Failed to bulk persist messages: {str(e)}",
            type="BULK_PERSIST_ERROR",
            non_retryable=False  # Allow retry for transient errors
        )
