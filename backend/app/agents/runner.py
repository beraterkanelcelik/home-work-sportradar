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
from langchain_core.load import dumpd

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
        
        # Use astream_events() to capture LLM token events via callbacks
        # This works regardless of state structure (unlike stream_mode=["messages"])
        accumulated_content = ""
        tokens_used = 0
        tool_calls = []
        agent_name = None
        
        # Map task/node names to user-friendly status messages
        status_messages = {
            "supervisor_task": "Routing to agent...",
            "load_messages_task": "Loading conversation history...",
            "check_summarization_needed_task": "Checking if summarization needed...",
            "greeter_agent_task": "Processing with greeter agent...",
            "search_agent_task": "Searching documents...",
            "agent_task": "Processing with agent...",
            "tool_execution_task": "Executing tools...",
            "agent_with_tool_results_task": "Processing tool results...",
            "save_message_task": "Saving message...",
        }
        
        # Use stream_events to capture all events including LLM tokens
        # PostgresSaver doesn't support async operations (aget_tuple), so we use sync stream_events
        # Run in a separate thread to avoid blocking
        from queue import Queue
        from threading import Thread
        
        event_queue = Queue()
        exception_holder = [None]
        # Use list to allow modification in nested function
        content_accumulator = [accumulated_content]
        tokens_accumulator = [tokens_used]
        
        def run_stream_events():
            """Run stream_events in a separate thread."""
            def process_events():
                """Process stream_events (sync version)."""
                event_count = 0
                try:
                    logger.info(f"Starting stream_events for session {chat_session_id}, request: {request.query[:50]}...")
                    
                    # Use propagate_attributes for Langfuse tracing
                    if LANGFUSE_ENABLED:
                        context_mgr = propagate_attributes(**trace_context)
                    else:
                        from contextlib import nullcontext
                        context_mgr = nullcontext()
                    
                    with context_mgr:
                        try:
                            # Use stream() with custom callback handler to capture LLM tokens
                            # PostgresSaver doesn't support async, so we can't use astream_events()
                            # Instead, we use stream() and capture tokens via on_llm_new_token callbacks
                            from langchain_core.callbacks import BaseCallbackHandler
                            
                            class StreamingCallbackHandler(BaseCallbackHandler):
                                """Callback handler to capture LLM token streaming events."""
                                
                                def __init__(self, event_queue, content_accumulator, tokens_accumulator, status_messages, session_id=None):
                                    super().__init__()
                                    self.event_queue = event_queue
                                    self.content_accumulator = content_accumulator
                                    self.tokens_accumulator = tokens_accumulator
                                    self.status_messages = status_messages
                                    self.current_chain = None
                                    self.chain_stack = []  # Track chain hierarchy
                                    self.skip_tokens_for_chains = set()  # Chains to skip token streaming
                                    self.is_supervisor_llm = False  # Track if current LLM is for supervisor routing
                                    self.supervisor_in_stack = False  # Track if supervisor is in chain stack
                                    # Known agent names that supervisor might output
                                    self.agent_names = {"greeter", "search", "gmail", "config", "process"}
                                    self.session_id = session_id  # Not used for status messages (they're ephemeral)
                                    self.active_tasks = {}  # Track active tasks: {task_name: status_text}
                                
                                def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs) -> None:
                                    """Track LLM start to identify supervisor routing calls."""
                                    try:
                                        # Check if supervisor flag was already set in on_chain_start
                                        if self.is_supervisor_llm:
                                            return
                                        
                                        # Check if we're in a supervisor task context
                                        run_name = kwargs.get("run_name", "")
                                        parent_run_id = kwargs.get("parent_run_id")
                                        
                                        # Check chain stack for supervisor (most reliable)
                                        is_supervisor_context = self.supervisor_in_stack
                                        
                                        if not is_supervisor_context:
                                            for chain in self.chain_stack:
                                                if chain and "supervisor" in str(chain).lower():
                                                    is_supervisor_context = True
                                                    self.supervisor_in_stack = True
                                                    break
                                        
                                        # Also check run_name
                                        if not is_supervisor_context and run_name and "supervisor" in run_name.lower():
                                            is_supervisor_context = True
                                            self.supervisor_in_stack = True
                                        
                                        # Check current chain
                                        if not is_supervisor_context and self.current_chain and "supervisor" in str(self.current_chain).lower():
                                            is_supervisor_context = True
                                            self.supervisor_in_stack = True
                                        
                                        # Check serialized data for supervisor references
                                        if not is_supervisor_context and isinstance(serialized, dict):
                                            serialized_str = str(serialized).lower()
                                            if "supervisor" in serialized_str or "supervisoragent" in serialized_str:
                                                is_supervisor_context = True
                                                self.supervisor_in_stack = True
                                        
                                        # Mark this LLM call as supervisor routing if in supervisor context
                                        # Supervisor LLM only outputs agent names (short tokens like "greeter")
                                        self.is_supervisor_llm = is_supervisor_context
                                    except Exception as e:
                                        logger.debug(f"Error in on_llm_start: {e}")
                                
                                def on_llm_end(self, response, **kwargs) -> None:
                                    """Reset supervisor flag and capture token usage."""
                                    self.is_supervisor_llm = False
                                    if hasattr(response, 'usage_metadata') and response.usage_metadata:
                                        usage = response.usage_metadata
                                        self.tokens_accumulator[0] = usage.get('total_tokens', 0)
                                
                                def on_llm_new_token(self, token: str, **kwargs) -> None:
                                    """Capture LLM token chunks, but skip supervisor routing tokens."""
                                    # Skip tokens from supervisor LLM (it just outputs agent name like "greeter")
                                    if self.is_supervisor_llm:
                                        return
                                    
                                    # Additional validation: supervisor only outputs short agent names
                                    # If token is very short (1-10 chars) and matches known agent name, skip it
                                    token_lower = token.strip().lower()
                                    if len(token_lower) <= 10 and token_lower in self.agent_names:
                                        # Check if we're in supervisor context
                                        if self.supervisor_in_stack or (self.current_chain and "supervisor" in str(self.current_chain).lower()):
                                            return
                                        # Also check chain stack
                                        for chain in self.chain_stack:
                                            if chain and "supervisor" in str(chain).lower():
                                                return
                                    
                                    # Also check chain context as fallback
                                    should_skip = False
                                    if self.current_chain and "supervisor" in str(self.current_chain).lower():
                                        should_skip = True
                                    # Check chain stack for supervisor
                                    if not should_skip:
                                        for chain in self.chain_stack:
                                            if chain and "supervisor" in str(chain).lower():
                                                should_skip = True
                                                break
                                    
                                    if should_skip:
                                        return
                                    
                                    if token:
                                        self.content_accumulator[0] += token
                                        self.event_queue.put({"type": "token", "data": token})
                                
                                def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs) -> None:
                                    """Capture chain/task start events."""
                                    try:
                                        # For LangGraph Functional API, serialized can be None
                                        # Task name is often in kwargs['name'] instead
                                        chain_name = ""
                                        
                                        # Try to get name from kwargs first (LangGraph Functional API pattern)
                                        name_from_kwargs = kwargs.get("name", "")
                                        
                                        # Also try serialized if available
                                        if serialized and isinstance(serialized, dict):
                                            chain_name = serialized.get("name", "")
                                            if not chain_name:
                                                chain_id = serialized.get("id")
                                                if isinstance(chain_id, list) and chain_id:
                                                    chain_name = chain_id[-1]
                                                elif isinstance(chain_id, str):
                                                    chain_name = chain_id
                                        
                                        # Use name from kwargs if chain_name is empty
                                        if not chain_name and name_from_kwargs:
                                            chain_name = name_from_kwargs
                                        
                                        # Check kwargs for run_name and tags which might contain task info
                                        run_name = kwargs.get("run_name", "")
                                        tags = kwargs.get("tags", [])
                                        metadata = kwargs.get("metadata", {})
                                        
                                        
                                        # Extract function name from serialized if available
                                        # LangGraph Functional API may store function names in the chain data
                                        function_name = None
                                        if isinstance(serialized, dict):
                                            # Check various possible locations for function name
                                            if "id" in serialized:
                                                chain_id = serialized.get("id")
                                                if isinstance(chain_id, list):
                                                    # Look for function name in the ID list
                                                    for item in chain_id:
                                                        if isinstance(item, str) and "_task" in item:
                                                            function_name = item
                                                            break
                                                elif isinstance(chain_id, str) and "_task" in chain_id:
                                                    function_name = chain_id
                                        
                                        # Use run_name if available, otherwise use chain_name
                                        effective_name = run_name or chain_name or function_name or ""
                                        
                                        # DETECT SUPERVISOR CONTEXT EARLY - Set flag when supervisor task is detected
                                        if effective_name and "supervisor" in effective_name.lower():
                                            self.supervisor_in_stack = True
                                            # Mark that any LLM called from this point is supervisor routing
                                            self.is_supervisor_llm = True
                                        
                                        # Check tags for task name (LangGraph might put task name in tags)
                                        task_name_from_tags = None
                                        if tags:
                                            for tag in tags:
                                                if isinstance(tag, str) and tag in self.status_messages:
                                                    task_name_from_tags = tag
                                                    break
                                                # Also check if tag contains task name
                                                for known_task in self.status_messages.keys():
                                                    if known_task in str(tag).lower():
                                                        task_name_from_tags = known_task
                                                        break
                                        
                                        # Track chain hierarchy
                                        self.chain_stack.append(effective_name)
                                        self.current_chain = effective_name
                                        
                                        # Extract task name - try multiple strategies
                                        task_name = task_name_from_tags
                                        
                                        # Strategy 1: Use function name if it matches a known task
                                        if not task_name and function_name:
                                            func_lower = function_name.lower()
                                            for known_task in self.status_messages.keys():
                                                if known_task.lower() == func_lower or known_task.lower() in func_lower:
                                                    task_name = known_task
                                                    break
                                        
                                        # Strategy 2: Direct match against known tasks
                                        if not task_name:
                                            candidate = effective_name.lower() if effective_name else ""
                                            for known_task in self.status_messages.keys():
                                                # Exact match or task name is substring of candidate
                                                if known_task.lower() == candidate or known_task.lower() in candidate:
                                                    task_name = known_task
                                                    break
                                                # Or candidate is substring of task name (for nested chains)
                                                if candidate and candidate in known_task.lower():
                                                    task_name = known_task
                                                    break
                                        
                                        # Strategy 3: Pattern matching for Functional API task names
                                        if not task_name and effective_name:
                                            candidate = effective_name.lower()
                                            if "supervisor" in candidate:
                                                task_name = "supervisor_task"
                                            elif "greeter" in candidate and ("agent" in candidate or "task" in candidate):
                                                task_name = "greeter_agent_task"
                                            elif "search" in candidate and ("agent" in candidate or "task" in candidate):
                                                task_name = "search_agent_task"
                                            elif "load" in candidate and "message" in candidate:
                                                task_name = "load_messages_task"
                                            elif "tool" in candidate and "execution" in candidate:
                                                task_name = "tool_execution_task"
                                            elif "save" in candidate and "message" in candidate:
                                                task_name = "save_message_task"
                                            elif "summarization" in candidate:
                                                task_name = "check_summarization_needed_task"
                                        
                                        # Strategy 4: Check if chain name contains task function name pattern
                                        if not task_name and effective_name:
                                            # Look for patterns like "supervisor_task", "greeter_agent_task" etc.
                                            for known_task in self.status_messages.keys():
                                                # Remove _task suffix for matching
                                                task_base = known_task.replace("_task", "").lower()
                                                if task_base in effective_name.lower():
                                                    task_name = known_task
                                                    break
                                        
                                        # Send status update if task identified
                                        if task_name:
                                            if task_name in self.status_messages:
                                                status = self.status_messages[task_name]
                                                logger.info(f"Sending status update: {status} for task: {task_name}")
                                                # Track this task as active (no DB persistence - status messages are ephemeral UI feedback)
                                                if task_name not in self.active_tasks:
                                                    self.active_tasks[task_name] = {"status": status}
                                                
                                                # Send as regular update (for real-time display only - no DB persistence)
                                                self.event_queue.put({"type": "update", "data": {"status": status, "task": task_name}})
                                            else:
                                                # Generic status update for unmatched tasks
                                                status_text = f"Running {task_name}..."
                                                # Track this task as active (no DB persistence - status messages are ephemeral UI feedback)
                                                if task_name not in self.active_tasks:
                                                    self.active_tasks[task_name] = {"status": status_text}
                                                # Send as regular update (for real-time display only - no DB persistence)
                                                self.event_queue.put({"type": "update", "data": {"status": status_text, "task": task_name}})
                                    
                                    except Exception as e:
                                        logger.error(f"Error in StreamingCallbackHandler.on_chain_start callback: {e}", exc_info=True)
                                
                                def on_chain_end(self, outputs: Any, **kwargs) -> None:
                                    """Track chain end to update current chain and save completed status."""
                                    try:
                                        # Also check chain name from kwargs (LangGraph Functional API pattern)
                                        chain_name_from_kwargs = kwargs.get("name", "")
                                        
                                        if self.chain_stack:
                                            popped = self.chain_stack.pop()
                                            self.current_chain = self.chain_stack[-1] if self.chain_stack else None
                                            
                                            # Check if this was a task we're tracking
                                            # Use chain_name from kwargs if available, otherwise use popped
                                            chain_to_check = chain_name_from_kwargs if chain_name_from_kwargs else str(popped) if popped else ""
                                            
                                            if chain_to_check:
                                                chain_lower = chain_to_check.lower()
                                                # Find matching task
                                                for task_name in self.status_messages.keys():
                                                    # Check if chain name matches task name
                                                    task_lower = task_name.lower()
                                                    # Special case: ai_agent_workflow should match agent_task
                                                    if chain_lower == "ai_agent_workflow" and task_name == "agent_task":
                                                        # Task completed - update status message to past tense
                                                        if task_name in self.active_tasks and self.session_id:
                                                            task_info = self.active_tasks[task_name]
                                                            status_text = task_info.get("status", "")
                                                            message_id = task_info.get("message_id")
                                                            
                                                            # Convert to past tense
                                                            past_tense_map = {
                                                                "Processing with agent...": "Processed with agent",
                                                                "Routing to agent...": "Routed to agent",
                                                                "Loading conversation history...": "Loaded conversation history",
                                                                "Processing with greeter agent...": "Processed with greeter agent",
                                                                "Searching documents...": "Searched documents",
                                                                "Executing tools...": "Executed tools",
                                                                "Processing tool results...": "Processed tool results",
                                                                "Checking if summarization needed...": "Checked if summarization needed",
                                                                "Saving message...": "Saved message",
                                                            }
                                                            past_status = past_tense_map.get(status_text, status_text.replace("ing...", "ed").replace("ing", "ed"))
                                                            
                                                            # Send update event to frontend for real-time update (no DB persistence)
                                                            self.event_queue.put({
                                                                "type": "update", 
                                                                "data": {
                                                                    "status": past_status, 
                                                                    "task": task_name,
                                                                    "is_completed": True
                                                                }
                                                            })
                                                            
                                                            # Remove from active tasks (status messages are ephemeral, no DB update needed)
                                                            del self.active_tasks[task_name]
                                                        break
                                                    elif task_lower in chain_lower or chain_lower in task_lower:
                                                        # Task completed - update status message to past tense
                                                        if task_name in self.active_tasks and self.session_id:
                                                            task_info = self.active_tasks[task_name]
                                                            status_text = task_info.get("status", "")
                                                            message_id = task_info.get("message_id")
                                                            
                                                            # Convert to past tense
                                                            past_tense_map = {
                                                                "Processing with agent...": "Processed with agent",
                                                                "Routing to agent...": "Routed to agent",
                                                                "Loading conversation history...": "Loaded conversation history",
                                                                "Processing with greeter agent...": "Processed with greeter agent",
                                                                "Searching documents...": "Searched documents",
                                                                "Executing tools...": "Executed tools",
                                                                "Processing tool results...": "Processed tool results",
                                                                "Checking if summarization needed...": "Checked if summarization needed",
                                                                "Saving message...": "Saved message",
                                                            }
                                                            past_status = past_tense_map.get(status_text, status_text.replace("ing...", "ed").replace("ing", "ed"))
                                                            
                                                            # Send update event to frontend for real-time update (no DB persistence)
                                                            self.event_queue.put({
                                                                "type": "update", 
                                                                "data": {
                                                                    "status": past_status, 
                                                                    "task": task_name,
                                                                    "is_completed": True
                                                                }
                                                            })
                                                            
                                                            # Remove from active tasks (status messages are ephemeral, no DB update needed)
                                                            del self.active_tasks[task_name]
                                                        break
                                            
                                            # If we popped supervisor, reset the flag
                                            if popped and "supervisor" in str(popped).lower():
                                                self.supervisor_in_stack = any(
                                                    chain and "supervisor" in str(chain).lower() 
                                                    for chain in self.chain_stack
                                                )
                                                # Only reset supervisor LLM flag if supervisor is completely out of stack
                                                if not self.supervisor_in_stack:
                                                    self.is_supervisor_llm = False
                                    except Exception:
                                        pass
                                
                                def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
                                    """Capture tool execution start."""
                                    try:
                                        if serialized is None:
                                            return
                                        tool_name = serialized.get("name", "") if isinstance(serialized, dict) else ""
                                        if tool_name:
                                            # Send status update for tool execution (status updates are fine during streaming)
                                            logger.info(f"Sending tool status update: Executing {tool_name}...")
                                            self.event_queue.put({"type": "update", "data": {"status": f"Executing {tool_name}...", "tool": tool_name}})
                                    except Exception as e:
                                        logger.error(f"Error in StreamingCallbackHandler.on_tool_start callback: {e}", exc_info=True)
                                
                                def on_tool_end(self, output: Any, **kwargs) -> None:
                                    """Tool execution completed - update status to executed."""
                                    try:
                                        # Extract tool name from kwargs
                                        tool_name = None
                                        if isinstance(kwargs.get("name"), str):
                                            tool_name = kwargs["name"]
                                        elif isinstance(kwargs.get("serialized"), dict):
                                            tool_name = kwargs["serialized"].get("name", "")
                                        
                                        if tool_name:
                                            # Update tool status to executed
                                            logger.info(f"Tool {tool_name} executed")
                                            self.event_queue.put({"type": "update", "data": {"status": f"Executed {tool_name}", "tool": tool_name}})
                                    except Exception as e:
                                        logger.error(f"Error in StreamingCallbackHandler.on_tool_end callback: {e}", exc_info=True)
                            
                            # Create streaming callback handler
                            streaming_callback = StreamingCallbackHandler(
                                event_queue,
                                content_accumulator,
                                tokens_accumulator,
                                status_messages,
                                session_id=None  # No DB persistence for status messages (ephemeral UI feedback only)
                            )
                            
                            # Add streaming callback to config
                            if 'callbacks' not in config:
                                config['callbacks'] = []
                            config['callbacks'].append(streaming_callback)
                            
                            # Use stream() - this works with PostgresSaver (sync checkpoint)
                            # The LLM's .invoke() calls in tasks will auto-stream tokens via callbacks
                            final_state = None
                            for chunk in ai_agent_workflow.stream(request, config=config):
                                # stream() yields state dictionaries (LangGraph Functional API)
                                # The final chunk contains the state with the AgentResponse
                                final_state = chunk  # Capture final state
                                event_count += 1
                            
                            logger.info(f"Workflow stream() completed: {event_count} chunks, {len(content_accumulator[0])} chars")
                            
                            # Extract AgentResponse from final state
                            # LangGraph Functional API stream() returns state dicts
                            # The return value is typically under the workflow name key (e.g., 'ai_agent_workflow')
                            agent_name = None
                            tool_calls = None
                            
                            if final_state and isinstance(final_state, dict):
                                # Try different ways to extract the response
                                # The state might contain the response directly or under a key
                                response_data = None
                                
                                # Check if state has the workflow name as a key (LangGraph pattern)
                                if 'ai_agent_workflow' in final_state:
                                    response_data = final_state['ai_agent_workflow']
                                elif 'response' in final_state:
                                    response_data = final_state['response']
                                elif 'result' in final_state:
                                    response_data = final_state['result']
                                elif 'output' in final_state:
                                    response_data = final_state['output']
                                else:
                                    # State might be the response itself (check if it has AgentResponse fields)
                                    if any(key in final_state for key in ['agent_name', 'reply', 'tool_calls', 'type']):
                                        response_data = final_state
                                
                                # Extract agent_name and tool_calls from response_data
                                if response_data:
                                    if isinstance(response_data, dict):
                                        agent_name = response_data.get('agent_name')
                                        tool_calls = response_data.get('tool_calls')
                                    elif isinstance(response_data, AgentResponse):
                                        agent_name = response_data.agent_name
                                        tool_calls = response_data.tool_calls
                                else:
                                    # Try to extract directly from state
                                    agent_name = final_state.get('agent_name')
                                    tool_calls = final_state.get('tool_calls')
                            
                            # Send final tool_calls and agent_name via update event if we have them
                            if agent_name or tool_calls:
                                logger.info(f"Extracted from state - agent_name: {agent_name}, tool_calls count: {len(tool_calls) if tool_calls else 0}")
                                
                                update_data = {}
                                if agent_name:
                                    update_data["agent_name"] = agent_name
                                if tool_calls:
                                    # Format tool_calls for frontend
                                    formatted_tool_calls = []
                                    for tc in tool_calls:
                                        formatted_tc = {
                                            "name": tc.get("name") or tc.get("tool", ""),
                                            "tool": tc.get("name") or tc.get("tool", ""),
                                            "args": tc.get("args", {}),
                                            "status": tc.get("status", "completed"),
                                        }
                                        if tc.get("id"):
                                            formatted_tc["id"] = tc.get("id")
                                        if tc.get("output"):
                                            formatted_tc["output"] = tc.get("output")
                                        if tc.get("error"):
                                            formatted_tc["error"] = tc.get("error")
                                        formatted_tool_calls.append(formatted_tc)
                                    update_data["tool_calls"] = formatted_tool_calls
                                
                                if update_data:
                                    logger.info(f"Sending final update event: {len(update_data.get('tool_calls', []))} tool_calls, agent: {update_data.get('agent_name')}")
                                    event_queue.put({
                                        "type": "update",
                                        "data": update_data
                                    })
                            else:
                                logger.warning(f"Could not extract agent_name or tool_calls from final state. State type: {type(final_state)}, keys: {list(final_state.keys()) if isinstance(final_state, dict) else 'N/A'}")
                            
                            # Mark agent_task as completed when workflow finishes
                            if "agent_task" in streaming_callback.active_tasks and chat_session_id:
                                task_info = streaming_callback.active_tasks["agent_task"]
                                status_text = task_info.get("status", "")
                                message_id = task_info.get("message_id")
                                
                                if status_text == "Processing with agent...":
                                    past_status = "Processed with agent"
                                    
                                    # Send update event to frontend for real-time update (no DB persistence)
                                    event_queue.put({
                                        "type": "update", 
                                        "data": {
                                            "status": past_status, 
                                            "task": "agent_task",
                                            "is_completed": True
                                        }
                                    })
                                    
                                    # Remove from active tasks (status messages are ephemeral, no DB update needed)
                                    del streaming_callback.active_tasks["agent_task"]
                        except RuntimeError as stream_error:
                            # Handle Django auto-reload shutdown gracefully
                            if "cannot schedule new futures after interpreter shutdown" in str(stream_error):
                                logger.warning("Workflow stream interrupted by Django reload - this is expected during development")
                                # Don't raise - just exit gracefully
                                return
                            else:
                                logger.error(f"Error in event stream processing: {stream_error}", exc_info=True)
                                raise
                        except Exception as stream_error:
                            logger.error(f"Error in event stream processing: {stream_error}", exc_info=True)
                            raise
                    
                    logger.info(f"stream_events completed: {event_count} events processed, accumulated_content: {len(content_accumulator[0])} chars")
                    if event_count == 0:
                        logger.warning(f"No events were captured from stream_events! This might indicate the workflow didn't execute.")
                except RuntimeError as e:
                    # Handle Django auto-reload shutdown gracefully
                    if "cannot schedule new futures after interpreter shutdown" in str(e):
                        logger.warning("Workflow stream interrupted by Django reload - this is expected during development")
                        # Don't set exception - just exit gracefully
                    else:
                        logger.error(f"Error in process_events: {e}", exc_info=True)
                        exception_holder[0] = e
                except Exception as e:
                    logger.error(f"Error in process_events: {e}", exc_info=True)
                    exception_holder[0] = e
                finally:
                    # Signal completion
                    event_queue.put(None)
            
            try:
                process_events()
            except Exception as e:
                logger.error(f"Error in run_stream_events: {e}", exc_info=True)
                exception_holder[0] = e
                event_queue.put(None)
        
        # Start stream_events in background thread
        thread = Thread(target=run_stream_events, daemon=True)
        thread.start()
        
        # Yield events from queue
        while True:
            try:
                event_dict = event_queue.get(timeout=300)  # 5 minute timeout
                if event_dict is None:
                    # Generator finished
                    break
                if exception_holder[0]:
                    raise exception_holder[0]
                yield event_dict
            except Exception as e:
                logger.error(f"Error reading from event queue: {e}", exc_info=True)
                break
        
        # Update accumulated content and tokens from accumulators
        accumulated_content = content_accumulator[0]
        tokens_used = tokens_accumulator[0]
        
        # Note: Message is already saved by save_message_task in the workflow
        # No need for fallback logic - astream_events captures all tokens
        # tool_calls are sent via update event after stream completes (see line 706-736)
        
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
