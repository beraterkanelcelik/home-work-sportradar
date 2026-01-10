"""
Graph node implementations.
"""
from typing import Dict, Any
from langchain_core.messages import AIMessage
from app.agents.graphs.state import AgentState
from app.agents.agents.supervisor import SupervisorAgent
from app.agents.agents.greeter import GreeterAgent
from app.agents.tools.registry import tool_registry
from app.db.models.message import Message as MessageModel
from app.db.models.session import ChatSession
from app.agents.config import OPENAI_MODEL
from app.core.logging import get_logger

logger = get_logger(__name__)

supervisor_agent = SupervisorAgent()
# Greeter agent will be created per-request with user_id
greeter_agent_cache = {}


def supervisor_node(state: AgentState) -> AgentState:
    """
    Supervisor node - main entry point that analyzes the message.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state
    """
    messages = state.get("messages", [])
    
    if not messages:
        return state
    
    # Set current agent
    state["current_agent"] = "supervisor"
    
    # Supervisor analyzes but doesn't respond directly
    # Routing happens in router function
    return state


def greeter_node(state: AgentState, config: dict = None) -> AgentState:
    """
    Greeter node - executes greeter agent.
    
    Args:
        state: Current graph state
        config: Optional runtime config (contains callbacks from graph.invoke())
        
    Returns:
        Updated state with greeter response
    """
    messages = state.get("messages", [])
    
    if not messages:
        return state
    
    state["current_agent"] = "greeter"
    
    try:
        # Get or create greeter agent with user_id for RAG tool access
        user_id = state.get("user_id")
        chat_session_id = state.get("chat_session_id")
        
        # Get model from session if available
        model_name = None
        if chat_session_id:
            try:
                session = ChatSession.objects.get(id=chat_session_id)
                if session.model_used:
                    model_name = session.model_used
            except ChatSession.DoesNotExist:
                pass
        
        # Create cache key that includes model to ensure model changes are reflected
        cache_key = f"{user_id}:{model_name or 'default'}"
        if cache_key not in greeter_agent_cache:
            greeter_agent_cache[cache_key] = GreeterAgent(user_id=user_id, model_name=model_name)
        greeter_agent = greeter_agent_cache.get(cache_key, GreeterAgent(user_id=user_id, model_name=model_name))
        
        # Pass config to agent.invoke() so callbacks propagate to LLM calls
        invoke_kwargs = {}
        if config:
            invoke_kwargs['config'] = config
        response = greeter_agent.invoke(messages, **invoke_kwargs)
        
        # Extract token usage from response if available
        tokens_used = 0
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0
        
        # Check usage_metadata first (OpenAI streaming format)
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = response.usage_metadata
            tokens_used = usage.get('total_tokens', 0)
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
            cached_tokens = usage.get('cached_tokens', 0) or usage.get('cached_input_tokens', 0) or usage.get('cache_creation_input_tokens', 0)
            state["metadata"]["token_usage"] = usage
            logger.debug(f"Token usage: {tokens_used} total (input: {input_tokens}, output: {output_tokens}, cached: {cached_tokens})")
        # Fallback to response_metadata.token_usage
        elif hasattr(response, 'response_metadata') and response.response_metadata:
            usage = response.response_metadata.get('token_usage', {})
            if usage:
                tokens_used = usage.get('total_tokens', 0)
                input_tokens = usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0)
                output_tokens = usage.get('completion_tokens', 0) or usage.get('output_tokens', 0)
                cached_tokens = usage.get('cached_tokens', 0)
                state["metadata"]["token_usage"] = usage
                logger.debug(f"Token usage: {tokens_used} total (input: {input_tokens}, output: {output_tokens}, cached: {cached_tokens})")
        
        # Add response to messages
        if isinstance(response, AIMessage):
            state["messages"].append(response)
        else:
            # Wrap in AIMessage if needed
            state["messages"].append(AIMessage(content=str(response.content)))
        
        # Save message to database if chat_session_id exists
        # Skip saving in streaming mode - streaming function handles saving after all tokens are accumulated
        metadata = state.get("metadata", {})
        execution_type = metadata.get("execution_type", "")
        is_streaming = execution_type == "streaming"
        
        chat_session_id = state.get("chat_session_id")
        if chat_session_id and not is_streaming:
            try:
                session = ChatSession.objects.get(id=chat_session_id)
                
                # Update model_used if not set
                if not session.model_used:
                    session.model_used = OPENAI_MODEL
                
                # Get tool calls from state (populated by tool_node)
                tool_calls_metadata = state.get("tool_calls", [])
                
                message_obj = MessageModel.objects.create(
                    session=session,
                    role="assistant",
                    content=response.content if hasattr(response, 'content') else str(response),
                    tokens_used=tokens_used,
                    metadata={
                        "agent_name": "greeter",
                        "tool_calls": tool_calls_metadata,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cached_tokens": cached_tokens,
                        "model": OPENAI_MODEL,
                    }
                )
                
                # Update session and user token usage
                if tokens_used > 0:
                    session.tokens_used += tokens_used
                    session.save(update_fields=['tokens_used', 'model_used'])
                    
                    # Use centralized utility function for token persistence
                    from app.account.utils import increment_user_token_usage
                    increment_user_token_usage(session.user.id, tokens_used)
                
                logger.debug(f"Saved greeter message to database for session {chat_session_id}, tokens: {tokens_used}")
            except ChatSession.DoesNotExist:
                logger.warning(f"Chat session {chat_session_id} not found when saving message")
            except Exception as e:
                logger.error(f"Error saving greeter message to database: {e}", exc_info=True)
        
    except Exception as e:
        logger.error(f"Error in greeter node: {e}", exc_info=True)
        # On error, add error message
        error_msg = AIMessage(content=f"I apologize, but I encountered an error: {str(e)}")
        state["messages"].append(error_msg)
    
    return state


def agent_node(state: AgentState, config: dict = None) -> AgentState:
    """
    Generic agent node - executes the agent specified in next_agent.
    
    Args:
        state: Current graph state
        config: Optional runtime config (contains callbacks from graph.invoke())
        
    Returns:
        Updated state
    """
    messages = state.get("messages", [])
    next_agent_name = state.get("next_agent", "greeter")
    
    # Validate next_agent_name is not None
    if not next_agent_name or next_agent_name == "None":
        logger.warning(f"next_agent is None or 'None', defaulting to greeter")
        next_agent_name = "greeter"
        state["next_agent"] = "greeter"
    
    if not messages:
        return state
    
    state["current_agent"] = next_agent_name
    
    try:
        # Pass config to agent.invoke() so callbacks propagate to LLM calls
        invoke_kwargs = {}
        if config:
            invoke_kwargs['config'] = config
        
        # Route to specific agent based on supervisor's decision
        if next_agent_name == "gmail":
            # Placeholder for Gmail agent (to be implemented)
            response = AIMessage(
                content="Gmail agent is not yet implemented. This feature will be available soon."
            )
            tokens_used = 0
            input_tokens = 0
            output_tokens = 0
            cached_tokens = 0
        elif next_agent_name == "greeter":
            # Get or create greeter agent with user_id for RAG tool access
            user_id = state.get("user_id")
            if user_id and user_id not in greeter_agent_cache:
                greeter_agent_cache[user_id] = GreeterAgent(user_id=user_id)
            greeter_agent = greeter_agent_cache.get(user_id, GreeterAgent())
            
            # Greeter agent
            response = greeter_agent.invoke(messages, **invoke_kwargs)
            
            # Extract token usage from response if available
            tokens_used = 0
            input_tokens = 0
            output_tokens = 0
            cached_tokens = 0
            
            # Check usage_metadata first (OpenAI streaming format)
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                tokens_used = usage.get('total_tokens', 0)
                input_tokens = usage.get('input_tokens', 0)
                output_tokens = usage.get('output_tokens', 0)
                cached_tokens = usage.get('cached_tokens', 0) or usage.get('cached_input_tokens', 0) or usage.get('cache_creation_input_tokens', 0)
                state["metadata"]["token_usage"] = usage
                logger.debug(f"Token usage: {tokens_used} total (input: {input_tokens}, output: {output_tokens}, cached: {cached_tokens})")
            # Fallback to response_metadata.token_usage
            elif hasattr(response, 'response_metadata') and response.response_metadata:
                usage = response.response_metadata.get('token_usage', {})
                if usage:
                    tokens_used = usage.get('total_tokens', 0)
                    input_tokens = usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0)
                    output_tokens = usage.get('completion_tokens', 0) or usage.get('output_tokens', 0)
                    cached_tokens = usage.get('cached_tokens', 0)
                    state["metadata"]["token_usage"] = usage
                    logger.debug(f"Token usage: {tokens_used} total (input: {input_tokens}, output: {output_tokens}, cached: {cached_tokens})")
        else:
            # Unknown agent - this should not happen if supervisor is working correctly
            logger.error(f"Unknown agent '{next_agent_name}' - supervisor should only route to available agents")
            raise ValueError(f"Agent '{next_agent_name}' is not implemented. Supervisor routed to invalid agent.")
        
        if not isinstance(response, AIMessage):
            response = AIMessage(content=str(response.content))
        
        state["messages"].append(response)
        
        # Save to database
        # Skip saving in streaming mode - streaming function handles saving after all tokens are accumulated
        metadata = state.get("metadata", {})
        execution_type = metadata.get("execution_type", "")
        is_streaming = execution_type == "streaming"
        
        chat_session_id = state.get("chat_session_id")
        if chat_session_id and not is_streaming:
            try:
                session = ChatSession.objects.get(id=chat_session_id)
                
                # Update model_used if not set
                if not session.model_used:
                    session.model_used = OPENAI_MODEL
                
                # Get tool calls from state (populated by tool_node)
                tool_calls_metadata = state.get("tool_calls", [])
                
                message_obj = MessageModel.objects.create(
                    session=session,
                    role="assistant",
                    content=response.content if hasattr(response, 'content') else str(response),
                    tokens_used=tokens_used,
                    metadata={
                        "agent_name": next_agent_name,
                        "tool_calls": tool_calls_metadata,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cached_tokens": cached_tokens,
                        "model": OPENAI_MODEL,
                    }
                )
                
                # Update session and user token usage
                if tokens_used > 0:
                    session.tokens_used += tokens_used
                    session.save(update_fields=['tokens_used', 'model_used'])
                    
                    # Use centralized utility function for token persistence
                    from app.account.utils import increment_user_token_usage
                    increment_user_token_usage(session.user.id, tokens_used)
                
                logger.debug(f"Saved agent message to database for session {chat_session_id}, tokens: {tokens_used}")
            except ChatSession.DoesNotExist:
                logger.warning(f"Chat session {chat_session_id} not found when saving message")
            except Exception as e:
                logger.error(f"Error saving agent message to database: {e}", exc_info=True)
        
    except Exception as e:
        logger.error(f"Error in agent node: {e}", exc_info=True)
        error_msg = AIMessage(content=f"I apologize, but I encountered an error: {str(e)}")
        state["messages"].append(error_msg)
    
    return state


def tool_node(state: AgentState) -> AgentState:
    """
    Tool execution node - executes tools when needed.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with tool results
    """
    messages = state.get("messages", [])
    current_agent = state.get("current_agent", "greeter")
    
    if not messages:
        return state
    
    # Get last message (should be AIMessage with tool calls)
    last_message = messages[-1] if messages else None
    
    if not last_message or not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
        logger.warning("tool_node called but no tool calls found in last message")
        return state
    
    logger.info(f"Executing {len(last_message.tool_calls)} tool calls in tool_node for agent {current_agent}")
    
    # Get tools for current agent - need to get them from the agent instance
    # Since tools are created per-user, we need to get them from the agent
    tools = []
    user_id = state.get("user_id")
    chat_session_id = state.get("chat_session_id")
    
    if current_agent == "greeter" and user_id:
        # Get greeter agent with tools
        # Get model from session if available
        model_name = None
        if chat_session_id:
            try:
                session = ChatSession.objects.get(id=chat_session_id)
                if session.model_used:
                    model_name = session.model_used
            except ChatSession.DoesNotExist:
                pass
        
        # Create cache key that includes model
        cache_key = f"{user_id}:{model_name or 'default'}"
        if cache_key in greeter_agent_cache:
            greeter_agent = greeter_agent_cache[cache_key]
            tools = greeter_agent.get_tools()
        else:
            greeter_agent = GreeterAgent(user_id=user_id, model_name=model_name)
            greeter_agent_cache[cache_key] = greeter_agent
            tools = greeter_agent.get_tools()
    else:
        # Fallback to registry
        tools = tool_registry.get_tools_for_agent(current_agent)
    
    tool_map = {tool.name: tool for tool in tools}
    logger.debug(f"Available tools for {current_agent}: {list(tool_map.keys())}")
    
    # Execute tool calls
    tool_results = []
    from langchain_core.messages import ToolMessage
    
    for tool_call in last_message.tool_calls:
        tool_name = tool_call.get("name")
        tool_id = tool_call.get("id")
        tool_args = tool_call.get("args", {})
        
        logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
        
        if tool_name in tool_map:
            try:
                result = tool_map[tool_name].invoke(tool_args)
                
                # Extract document IDs from RAG tool results for reference
                doc_ids = []
                if tool_name == "rag_retrieval_tool" and tool_args.get("document_ids"):
                    doc_ids = tool_args.get("document_ids", [])
                elif tool_name == "rag_retrieval_tool":
                    # If no specific document_ids, we'll extract from result citations
                    # For now, we'll leave it empty - can be enhanced later
                    pass
                
                tool_call_data = {
                    "tool": tool_name,
                    "name": tool_name,  # For frontend compatibility
                    "args": tool_args,
                    "result": str(result),  # Store as string for JSON serialization
                    "document_ids": doc_ids,  # Store document IDs for references
                }
                
                tool_results.append({
                    "tool": tool_name,
                    "result": result,
                })
                
                # Ensure tool_calls list exists
                if "tool_calls" not in state:
                    state["tool_calls"] = []
                state["tool_calls"].append(tool_call_data)
                
                # Also store in metadata for easier access
                if "metadata" not in state:
                    state["metadata"] = {}
                if "tool_calls" not in state["metadata"]:
                    state["metadata"]["tool_calls"] = []
                state["metadata"]["tool_calls"].append(tool_call_data)
                
                # Add tool result as ToolMessage to state
                tool_message = ToolMessage(
                    content=str(result),
                    tool_call_id=tool_id if tool_id else f"call_{tool_name}",
                    name=tool_name
                )
                state["messages"].append(tool_message)
                
                logger.info(f"Tool {tool_name} executed successfully, result length: {len(str(result))}")
            except Exception as e:
                logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
                error_result = f"Error executing tool: {str(e)}"
                tool_results.append({
                    "tool": tool_name,
                    "error": str(e),
                })
                state["tool_calls"].append({
                    "tool": tool_name,
                    "name": tool_name,
                    "args": tool_args,
                    "error": str(e),
                })
                # Add error as ToolMessage
                tool_message = ToolMessage(
                    content=error_result,
                    tool_call_id=tool_id if tool_id else f"call_{tool_name}",
                    name=tool_name
                )
                state["messages"].append(tool_message)
        else:
            logger.warning(f"Tool {tool_name} not found in tool_map. Available tools: {list(tool_map.keys())}")
            error_result = f"Tool {tool_name} is not available"
            state["tool_calls"].append({
                "tool": tool_name,
                "name": tool_name,
                "args": tool_args,
                "error": error_result,
            })
            tool_message = ToolMessage(
                content=error_result,
                tool_call_id=tool_id if tool_id else f"call_{tool_name}",
                name=tool_name
            )
            state["messages"].append(tool_message)
    
    # Add tool results to state metadata
    state["metadata"]["tool_results"] = tool_results
    
    return state
