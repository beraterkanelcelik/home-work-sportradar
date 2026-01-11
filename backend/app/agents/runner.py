"""
Agent execution and event streaming using LangGraph Functional API.
"""
import uuid
import os
from typing import Dict, Any, Iterator, Optional, List
from app.agents.functional.workflow import ai_agent_workflow
from app.agents.functional.models import AgentRequest, AgentResponse
from app.agents.checkpoint import get_checkpoint_config
from app.agents.config import LANGCHAIN_TRACING_V2, LANGCHAIN_PROJECT, LANGFUSE_ENABLED
from app.core.logging import get_logger
from app.observability.tracing import get_callback_handler, prepare_trace_context, flush_traces

logger = get_logger(__name__)

# Enable LangSmith tracing if configured (optional, for compatibility)
if LANGCHAIN_TRACING_V2:
    os.environ['LANGCHAIN_TRACING_V2'] = 'true'
    os.environ['LANGCHAIN_PROJECT'] = LANGCHAIN_PROJECT


def execute_agent(
    user_id: int,
    chat_session_id: int,
    message: str,
    plan_steps: Optional[List[Dict[str, Any]]] = None,
    flow: str = "main"
) -> Dict[str, Any]:
    """
    Execute agent using Functional API with input message.
    
    Args:
        user_id: User ID
        chat_session_id: Chat session ID
        message: User message
        
    Returns:
        Dictionary with execution results
    """
    from langfuse import get_client, propagate_attributes
    
    # Generate deterministic trace ID using Langfuse SDK
    langfuse = get_client() if LANGFUSE_ENABLED else None
    if langfuse:
        trace_seed = f"{chat_session_id}-{user_id}-{uuid.uuid4()}"
        trace_id = langfuse.create_trace_id(seed=trace_seed)
    else:
        trace_id = str(uuid.uuid4())
    
    # Get checkpoint config
    config = get_checkpoint_config(chat_session_id)
    
    # Add Langfuse callback to config if enabled
    if LANGFUSE_ENABLED:
        callback_handler = get_callback_handler()
        if callback_handler:
            if isinstance(config, dict):
                if 'callbacks' not in config:
                    config['callbacks'] = []
                if callback_handler not in config['callbacks']:
                    config['callbacks'].append(callback_handler)
                if 'configurable' not in config:
                    config['configurable'] = {}
    
    # Prepare request
    request = AgentRequest(
        query=message,
        session_id=chat_session_id,
        user_id=user_id,
        org_slug=None,
        org_roles=[],
        app_roles=[],
        flow="main"
    )
    
    # Execute workflow with checkpoint context
    try:
        logger.info(f"Executing agent for user {user_id}, session {chat_session_id}, trace: {trace_id}")
        
        # Use propagate_attributes for Langfuse tracing
        if LANGFUSE_ENABLED:
            trace_context = prepare_trace_context(
                user_id=user_id,
                session_id=chat_session_id,
                metadata={
                    "chat_session_id": chat_session_id,
                    "execution_type": "functional",
                    "trace_id": trace_id,
                }
            )
            
            with propagate_attributes(**trace_context):
                response = ai_agent_workflow.invoke(request, config=config)
        else:
            response = ai_agent_workflow.invoke(request, config=config)
        
        # Flush traces if Langfuse is enabled
        if LANGFUSE_ENABLED:
            flush_traces()
        
        logger.info(f"Agent execution completed successfully. Agent: {response.agent_name}")
        
        result = {
            "success": True,
            "response": response.reply or "",
            "agent": response.agent_name,
            "tool_calls": response.tool_calls,
            "trace_id": trace_id,
        }
        
        # Include type and plan if this is a plan_proposal response
        if response.type == "plan_proposal":
            result["type"] = "plan_proposal"
            if response.plan:
                result["plan"] = response.plan
        
        # Include clarification and raw_tool_outputs if present
        if response.clarification:
            result["clarification"] = response.clarification
        
        if response.raw_tool_outputs:
            result["raw_tool_outputs"] = response.raw_tool_outputs
        
        return result
    except Exception as e:
        logger.error(
            f"Error executing agent for user {user_id}, session {chat_session_id}: {e}",
            exc_info=True
        )
        
        # Flush traces even on error
        if LANGFUSE_ENABLED:
            flush_traces()
        
        return {
            "success": False,
            "error": str(e),
            "response": f"I apologize, but I encountered an error: {str(e)}",
            "trace_id": trace_id,
        }


def stream_agent_events(
    user_id: int,
    chat_session_id: int,
    message: str,
    plan_steps: Optional[List[Dict[str, Any]]] = None,
    flow: str = "main"
) -> Iterator[Dict[str, Any]]:
    """
    Stream agent execution events using Functional API streaming.
    
    Note: Functional API streaming may work differently than Graph API.
    For now, we'll use the workflow's stream() method if available,
    otherwise fall back to non-streaming execution.
    
    Args:
        user_id: User ID
        chat_session_id: Chat session ID
        message: User message
        
    Yields:
        Event dictionaries with type and data
    """
    from langfuse import get_client, propagate_attributes
    
    # Generate deterministic trace ID using Langfuse SDK
    langfuse = get_client() if LANGFUSE_ENABLED else None
    if langfuse:
        trace_seed = f"{chat_session_id}-{user_id}-{uuid.uuid4()}"
        trace_id = langfuse.create_trace_id(seed=trace_seed)
    else:
        trace_id = str(uuid.uuid4())
    
    # Get checkpoint config
    config = get_checkpoint_config(chat_session_id)
    
    # Add Langfuse callback to config if enabled
    if LANGFUSE_ENABLED:
        callback_handler = get_callback_handler()
        if callback_handler:
            if isinstance(config, dict):
                if 'callbacks' not in config:
                    config['callbacks'] = []
                if callback_handler not in config['callbacks']:
                    config['callbacks'].append(callback_handler)
                if 'configurable' not in config:
                    config['configurable'] = {}
    
    # Prepare request
    request = AgentRequest(
        query=message,
        session_id=chat_session_id,
        user_id=user_id,
        org_slug=None,
        org_roles=[],
        app_roles=[],
        flow=flow,
        plan_steps=plan_steps
    )
    
    try:
        logger.info(f"Streaming agent events for user {user_id}, session {chat_session_id}, trace: {trace_id}, flow: {flow}")
        
        # Prepare trace context for propagate_attributes
        trace_context = prepare_trace_context(
            user_id=user_id,
            session_id=chat_session_id,
            metadata={
                "chat_session_id": chat_session_id,
                "execution_type": "streaming",
                "trace_id": trace_id,
            }
        )
        
        # Use proper streaming with Functional API
        # Stream both messages (LLM tokens) and updates (workflow state)
        accumulated_content = ""
        tokens_used = 0
        tool_calls = []
        agent_name = None
        final_response = None
        
        if LANGFUSE_ENABLED:
            with propagate_attributes(**trace_context):
                # Stream workflow execution with messages and updates
                for event in ai_agent_workflow.stream(
                    request,
                    config=config,
                    stream_mode=["messages", "updates"]
                ):
                    # Handle streaming events
                    # Event format: (mode, data) tuple when using multiple stream modes
                    if isinstance(event, tuple) and len(event) == 2:
                        mode, data = event
                        
                        if mode == "messages":
                            # Stream LLM tokens in real-time
                            # data format: (message_chunk, metadata) tuple
                            if isinstance(data, tuple) and len(data) == 2:
                                message_chunk, metadata = data
                                
                                # Only stream tokens from agent responses, not supervisor
                                if message_chunk and hasattr(message_chunk, 'content'):
                                    chunk_content = message_chunk.content or ""
                                    if chunk_content:
                                        # Handle incremental content (OpenAI streaming format)
                                        if chunk_content.startswith(accumulated_content):
                                            # New content is extension of previous
                                            delta = chunk_content[len(accumulated_content):]
                                            if delta:
                                                accumulated_content = chunk_content
                                                yield {"type": "token", "data": delta}
                                        else:
                                            # New content chunk
                                            accumulated_content += chunk_content
                                            yield {"type": "token", "data": chunk_content}
                                
                                # Extract token usage from message chunk if available
                                if hasattr(message_chunk, 'usage_metadata') and message_chunk.usage_metadata:
                                    usage = message_chunk.usage_metadata
                                    tokens_used = usage.get('total_tokens', 0)
                        
                        elif mode == "updates":
                            # Stream workflow state updates
                            # data format: dict with state updates
                            if isinstance(data, dict):
                                # Track agent name and tool calls from updates
                                if "agent_name" in data:
                                    agent_name = data.get("agent_name")
                                # Tool calls might be in updates
                                if "tool_calls" in data:
                                    tool_calls = data.get("tool_calls", [])
        else:
            # Non-Langfuse path
            for event in ai_agent_workflow.stream(
                request,
                config=config,
                stream_mode=["messages", "updates"]
            ):
                if isinstance(event, tuple) and len(event) == 2:
                    mode, data = event
                    
                    if mode == "messages":
                        if isinstance(data, tuple) and len(data) == 2:
                            message_chunk, metadata = data
                            if message_chunk and hasattr(message_chunk, 'content'):
                                chunk_content = message_chunk.content or ""
                                if chunk_content:
                                    if chunk_content.startswith(accumulated_content):
                                        delta = chunk_content[len(accumulated_content):]
                                        if delta:
                                            accumulated_content = chunk_content
                                            yield {"type": "token", "data": delta}
                                    else:
                                        accumulated_content += chunk_content
                                        yield {"type": "token", "data": chunk_content}
                    
                    elif mode == "updates":
                        if isinstance(data, dict):
                            if "agent_name" in data:
                                agent_name = data.get("agent_name")
                            if "tool_calls" in data:
                                tool_calls = data.get("tool_calls", [])
        
        # Get final response by invoking once more (or use accumulated state)
        # Note: In streaming mode, we may need to invoke to get final response
        # For now, we'll use the accumulated content
        if accumulated_content:
            # Save message if not already saved by workflow
            if chat_session_id:
                try:
                    from app.services.chat_service import add_message
                    from app.db.models.session import ChatSession
                    from app.agents.config import OPENAI_MODEL
                    
                    session = ChatSession.objects.get(id=chat_session_id)
                    if not session.model_used:
                        session.model_used = OPENAI_MODEL
                        session.save(update_fields=['model_used'])
                    
                    metadata = {
                        "agent_name": agent_name or "greeter",
                        "tool_calls": tool_calls,
                    }
                    if tokens_used > 0:
                        metadata.update({
                            "input_tokens": 0,  # Will be updated from final response
                            "output_tokens": 0,
                            "cached_tokens": 0,
                            "model": OPENAI_MODEL,
                        })
                    
                    add_message(
                        session_id=chat_session_id,
                        role="assistant",
                        content=accumulated_content,
                        tokens_used=tokens_used,
                        metadata=metadata
                    )
                except Exception as e:
                    logger.error(f"Error saving streamed message: {e}", exc_info=True)
        
        # Flush traces if Langfuse is enabled
        if LANGFUSE_ENABLED:
            flush_traces()
        
        # Yield completion event
        yield {
            "type": "done",
            "data": {
                "final_text": accumulated_content,
                "tokens_used": tokens_used,
                "trace_id": trace_id,
            }
        }
        
    except Exception as e:
        logger.error(
            f"Error streaming agent events for user {user_id}, session {chat_session_id}: {e}",
            exc_info=True
        )
        
        if LANGFUSE_ENABLED:
            flush_traces()
        
        yield {
            "type": "error",
            "data": {
                "error": str(e),
                "trace_id": trace_id,
            }
        }
