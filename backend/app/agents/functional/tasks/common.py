"""
Common task utilities for LangGraph Functional API.
"""

import json
from typing import List, Dict, Any, Optional
from langgraph.func import task
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from app.services.chat_service import get_messages
from app.db.models.session import ChatSession
from app.agents.config import OPENAI_MODEL
from app.core.logging import get_logger
from app.rag.chunking.tokenizer import count_tokens

logger = get_logger(__name__)

# Maximum size for tool outputs before truncation (50KB)
MAX_TOOL_OUTPUT_SIZE = 50_000


def truncate_tool_output(output: Any) -> Any:
    """
    Truncate large tool outputs to prevent unbounded memory growth.

    Args:
        output: Tool output (any type)

    Returns:
        Truncated output if too large, original output otherwise
    """
    try:
        serialized = json.dumps(output, default=str)
        if len(serialized) > MAX_TOOL_OUTPUT_SIZE:
            return {
                "truncated": True,
                "preview": serialized[:1000],
                "size": len(serialized),
                "original_size": len(serialized),
            }
        return output
    except Exception as e:
        logger.warning(f"Error truncating tool output: {e}")
        return {"error": "Failed to serialize tool output", "type": str(type(output))}


async def _get_workflow_messages(
    session_id: int, user_id: int
) -> Optional[List[BaseMessage]]:
    """
    Try to get messages from active Temporal workflow buffer.

    Args:
        session_id: Chat session ID
        user_id: User ID

    Returns:
        List of BaseMessage objects if workflow is active, None otherwise
    """
    try:
        from app.agents.temporal.workflow_manager import get_workflow_id
        from app.core.temporal import get_temporal_client

        client = await get_temporal_client()
        workflow_id = get_workflow_id(user_id, session_id)
        workflow_handle = client.get_workflow_handle(workflow_id)

        # Check if workflow is running
        try:
            description = await workflow_handle.describe()
            if description.status.name != "RUNNING":
                return None
        except Exception:
            # Workflow doesn't exist or can't be described
            return None

        # Query workflow for messages
        try:
            workflow_messages = await workflow_handle.query("get_messages")

            # Convert workflow message dicts to LangChain messages
            messages = []
            for msg_data in workflow_messages:
                role = msg_data.get("role", "assistant")
                content = msg_data.get("content", "")
                metadata = msg_data.get("metadata", {})

                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    aimessage = AIMessage(content=content)
                    if metadata:
                        aimessage.response_metadata = metadata
                    messages.append(aimessage)
                elif role == "system":
                    messages.append(SystemMessage(content=content))

            logger.debug(
                f"Loaded {len(messages)} messages from workflow buffer for session {session_id}"
            )
            return messages
        except Exception as e:
            logger.debug(f"Failed to query workflow messages: {e}")
            return None
    except Exception as e:
        logger.debug(f"Error getting workflow messages: {e}")
        return None


@task
def load_messages_task(
    session_id: Optional[int], checkpointer: Any, thread_id: str
) -> List[BaseMessage]:
    """
    Load conversation history from workflow buffer, checkpoint, or database.

    Priority:
    1. Active Temporal workflow buffer (for active sessions)
    2. LangGraph checkpoint (for workflow state)
    3. Database (for closed sessions or fallback)

    Args:
        session_id: Chat session ID
        checkpointer: LangGraph checkpointer instance
        thread_id: Thread ID for checkpoint

    Returns:
        List of LangChain BaseMessage objects
    """
    messages = []

    # Try to load from active workflow buffer first (optimization for active sessions)
    if session_id and _is_temporal_context():
        try:
            # Extract user_id from context if available
            # Note: In Temporal activity, we can get user_id from activity info or state
            # For now, try to get from session
            from app.db.models.session import ChatSession

            try:
                session = ChatSession.objects.get(id=session_id)
                user_id = session.user_id

                # Use sync_to_async to call async function from sync context
                from asgiref.sync import async_to_sync

                workflow_messages = async_to_sync(_get_workflow_messages)(
                    session_id, user_id
                )

                if workflow_messages:
                    logger.debug(
                        f"Loaded {len(workflow_messages)} messages from workflow buffer for session {session_id}"
                    )
                    return workflow_messages
            except ChatSession.DoesNotExist:
                pass
            except Exception as e:
                logger.debug(f"Failed to load from workflow buffer: {e}")
        except Exception as e:
            logger.debug(f"Error checking workflow buffer: {e}")

    # Try to load from checkpoint
    if checkpointer:
        try:
            checkpoint_config = {"configurable": {"thread_id": thread_id}}
            checkpoint = checkpointer.get(checkpoint_config)
            if checkpoint and "messages" in checkpoint:
                messages = checkpoint["messages"]
                logger.debug(
                    f"Loaded {len(messages)} messages from checkpoint for thread {thread_id}"
                )
                return messages
        except Exception as e:
            logger.warning(
                f"Failed to load from checkpoint: {e}, falling back to database"
            )

    # Fallback to database loading
    if session_id:
        try:
            # Only load messages that should be included in LLM context
            # UI-only messages (status updates, plans) are excluded
            db_messages = get_messages(session_id, for_llm=True)

            # Convert to LangChain message format
            for msg in db_messages:
                if msg.role == "user":
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    aimessage = AIMessage(content=msg.content)
                    if msg.metadata:
                        aimessage.response_metadata = msg.metadata
                    messages.append(aimessage)
                elif msg.role == "system":
                    messages.append(SystemMessage(content=msg.content))

            logger.debug(
                f"Loaded {len(messages)} messages from database for session {session_id}"
            )
        except Exception as e:
            logger.error(f"Error loading messages from database: {e}", exc_info=True)

    return messages


@task
def check_summarization_needed_task(
    messages: List[BaseMessage],
    token_threshold: int = 40000,
    model_name: Optional[str] = None,
) -> bool:
    """
    Check if summarization is needed based on message token count.

    Args:
        messages: List of conversation messages
        token_threshold: Token threshold to trigger summarization
        model_name: Optional model name for token counting

    Returns:
        True if summarization is needed, False otherwise
    """
    try:
        # Calculate total token count for all messages
        total_tokens = 0
        for message in messages:
            if hasattr(message, "content") and message.content:
                content = str(message.content)
                tokens = count_tokens(content, model_name)
                total_tokens += tokens

        logger.debug(
            f"Total message tokens: {total_tokens}, threshold: {token_threshold}"
        )

        needs_summarization = total_tokens >= token_threshold

        if needs_summarization:
            logger.info(
                f"Summarization needed: {total_tokens} tokens >= {token_threshold} threshold"
            )

        return needs_summarization
    except Exception as e:
        logger.error(f"Error checking summarization need: {e}", exc_info=True)
        return False


def _is_temporal_context() -> bool:
    """
    Check if code is running in a Temporal activity context.

    Returns:
        True if in Temporal activity, False otherwise
    """
    try:
        from temporalio import activity

        # Try to get activity info - if this succeeds, we're in an activity
        activity.info()
        return True
    except (RuntimeError, AttributeError, ImportError):
        # Not in Temporal activity context
        return False


@task
def save_message_task(
    response: Any,  # AgentResponse
    session_id: int,
    user_id: int,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    run_id: Optional[str] = None,
    parent_message_id: Optional[int] = None,
) -> bool:
    """
    Save agent response message to database or workflow buffer.

    If running in Temporal context, message is added to workflow buffer instead of DB.
    Messages in buffer are persisted in bulk on workflow close for optimization.

    Args:
        response: AgentResponse to save
        session_id: Chat session ID
        user_id: User ID
        tool_calls: Optional tool calls metadata
        run_id: Optional correlation ID
        parent_message_id: Optional parent message ID

    Returns:
        True if successful
    """
    # Check if we're in Temporal context - if so, skip DB write
    # Messages will be added to workflow buffer by the activity after execution
    if _is_temporal_context():
        logger.debug(
            f"[Temporal] Skipping DB write for message in session {session_id} - will be added to workflow buffer"
        )
        # Return True to indicate "success" (message will be handled by activity)
        return True

    try:
        from app.db.models.message import Message
        from app.services.chat_service import add_message

        session = ChatSession.objects.get(id=session_id)

        # Update model_used if not set
        if not session.model_used:
            session.model_used = OPENAI_MODEL
            session.save(update_fields=["model_used"])

        # Prepare metadata
        final_tool_calls = (
            tool_calls if tool_calls is not None else (response.tool_calls or [])
        )

        # Ensure all tool_calls have status field
        for tc in final_tool_calls:
            if "status" not in tc:
                if tc.get("output") or tc.get("result"):
                    tc["status"] = "completed"
                elif tc.get("error"):
                    tc["status"] = "error"
                else:
                    tc["status"] = "pending"

            # Truncate large outputs
            if "output" in tc and tc["output"] is not None:
                tc["output"] = truncate_tool_output(tc["output"])
            if "result" in tc and tc["result"] is not None:
                tc["result"] = truncate_tool_output(tc["result"])

        metadata = {
            "agent_name": response.agent_name or "greeter",
            "tool_calls": final_tool_calls,
        }

        if run_id:
            metadata["run_id"] = run_id
        if parent_message_id:
            metadata["parent_message_id"] = parent_message_id

        if response.type == "plan_proposal":
            metadata["response_type"] = "plan_proposal"
            if response.plan:
                metadata["plan"] = response.plan

        if response.clarification:
            metadata["clarification"] = response.clarification

        if response.raw_tool_outputs:
            truncated_outputs = [
                truncate_tool_output(output) for output in response.raw_tool_outputs
            ]
            metadata["raw_tool_outputs"] = truncated_outputs

        if response.token_usage:
            metadata.update(
                {
                    "input_tokens": response.token_usage.get("input_tokens", 0),
                    "output_tokens": response.token_usage.get("output_tokens", 0),
                    "cached_tokens": response.token_usage.get("cached_tokens", 0),
                    "model": OPENAI_MODEL,
                }
            )

        content = response.reply or ""
        if response.type == "plan_proposal" and response.plan:
            plan_steps = response.plan.get("plan", [])
            content = f"Plan proposal with {len(plan_steps)} step(s) to execute."

        # Check for existing message with same run_id
        existing_message = None
        if run_id:
            try:
                existing_message = (
                    Message.objects.filter(
                        session_id=session_id, role="assistant", metadata__run_id=run_id
                    )
                    .order_by("-created_at")
                    .first()
                )
            except Exception as e:
                logger.warning(
                    f"Error checking for existing message with run_id={run_id}: {e}"
                )

        if existing_message:
            existing_message.content = content
            existing_message.tokens_used = (
                response.token_usage.get("total_tokens", 0)
                if response.token_usage
                else existing_message.tokens_used
            )
            existing_message.metadata = metadata
            existing_message.save()
            logger.info(
                f"Updated existing assistant message ID={existing_message.id} session={session_id}"
            )
            return True
        else:
            message = add_message(
                session_id=session_id,
                role="assistant",
                content=content,
                tokens_used=response.token_usage.get("total_tokens", 0)
                if response.token_usage
                else 0,
                metadata=metadata,
            )
            logger.info(
                f"Saved new assistant message ID={message.id} session={session_id}"
            )
            return True
    except Exception as e:
        logger.error(f"Error saving message: {e}", exc_info=True)
        return False
