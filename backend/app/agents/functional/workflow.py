"""
Main workflow entrypoint for LangGraph Functional API.
"""
from typing import Optional, List, Dict, Any
from langgraph.func import entrypoint
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import HumanMessage, ToolMessage
from app.agents.functional.models import AgentRequest, AgentResponse, ToolProposal
from app.agents.functional.tasks import (
    supervisor_task,
    load_messages_task,
    check_summarization_needed_task,
    greeter_agent_task,
    search_agent_task,
    agent_task,
    tool_execution_task,
    agent_with_tool_results_task,
    save_message_task,
)
from app.agents.checkpoint import get_checkpoint_config
from app.core.logging import get_logger

logger = get_logger(__name__)


# Global checkpointer instance and context manager
_checkpointer = None
_checkpointer_cm = None


class CheckpointerWrapper:
    """
    Wrapper for PostgresSaver that handles connection timeouts.
    Recreates the checkpointer if connection is closed.
    """
    def __init__(self):
        self._checkpointer = None
        self._checkpointer_cm = None
        self._recreate_checkpointer()
    
    def _recreate_checkpointer(self):
        """Create a new checkpointer instance."""
        try:
            from app.settings import DATABASES
            from langgraph.checkpoint.postgres import PostgresSaver
            
            db_config = DATABASES['default']
            db_url = (
                f"postgresql://{db_config['USER']}:{db_config['PASSWORD']}"
                f"@{db_config['HOST']}:{db_config['PORT']}/{db_config['NAME']}"
            )
            
            # PostgresSaver.from_conn_string() returns a context manager
            # Enter it to get the actual checkpointer instance
            self._checkpointer_cm = PostgresSaver.from_conn_string(db_url)
            self._checkpointer = self._checkpointer_cm.__enter__()
            
            # Setup tables if needed
            try:
                self._checkpointer.setup()
            except Exception:
                pass  # Tables may already exist
            
            logger.info("Checkpointer created successfully")
        except Exception as e:
            logger.error(f"Failed to create checkpointer: {e}", exc_info=True)
            self._checkpointer = None
            self._checkpointer_cm = None
    
    def _get_checkpointer(self):
        """Get checkpointer, recreating if connection is closed."""
        if self._checkpointer is None:
            self._recreate_checkpointer()
        return self._checkpointer
    
    def __getattr__(self, name):
        """Delegate all attribute access to the underlying checkpointer."""
        checkpointer = self._get_checkpointer()
        if checkpointer is None:
            raise RuntimeError("Checkpointer is not available")
        
        try:
            attr = getattr(checkpointer, name)
        except AttributeError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        
        # Wrap methods to handle connection errors
        if callable(attr):
            def wrapper(*args, **kwargs):
                # Get the method from the current checkpointer
                current_checkpointer = self._get_checkpointer()
                if current_checkpointer is None:
                    raise RuntimeError("Checkpointer is not available")
                
                method = getattr(current_checkpointer, name)
                
                try:
                    return method(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).lower()
                    # Check for connection-related errors
                    if any(phrase in error_str for phrase in ['connection is closed', 'connection closed', 'the connection is closed']):
                        logger.warning(f"Connection closed, recreating checkpointer: {e}")
                        # Close old context manager if it exists
                        if self._checkpointer_cm and hasattr(self._checkpointer_cm, '__exit__'):
                            try:
                                self._checkpointer_cm.__exit__(None, None, None)
                            except Exception:
                                pass
                        self._recreate_checkpointer()
                        # Retry once with new checkpointer
                        current_checkpointer = self._get_checkpointer()
                        if current_checkpointer:
                            method = getattr(current_checkpointer, name)
                            return method(*args, **kwargs)
                    raise
            return wrapper
        return attr


def get_checkpointer() -> Optional[PostgresSaver]:
    """
    Get checkpointer instance (wrapper that handles connection timeouts).
    """
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = CheckpointerWrapper()
    return _checkpointer


# Create checkpointer instance for @entrypoint
# Note: @entrypoint requires an actual checkpointer instance, not a context manager
# We use a wrapper that automatically recreates the connection if it's closed
_checkpointer_instance = get_checkpointer()

# Auto-executable tools per agent
AUTO_EXECUTE_TOOLS = {
    "search": ["rag_retrieval_tool"],
    "greeter": ["rag_retrieval_tool"],
}


def extract_tool_proposals(tool_calls: List[Dict[str, Any]]) -> List[ToolProposal]:
    """
    Extract tool proposals from tool calls.
    
    Args:
        tool_calls: List of tool call dictionaries
        
    Returns:
        List of ToolProposal objects
    """
    proposals = []
    for tc in tool_calls:
        tool_name = tc.get("name") or tc.get("tool")
        tool_args = tc.get("args", {})
        if tool_name:
            proposals.append(ToolProposal(
                tool=tool_name,
                props=tool_args,
                query=""
            ))
    return proposals


def is_auto_executable(tool_name: str, agent_name: str) -> bool:
    """
    Check if a tool is auto-executable for the given agent.
    
    Args:
        tool_name: Name of the tool
        agent_name: Name of the agent
        
    Returns:
        True if tool is auto-executable
    """
    auto_tools = AUTO_EXECUTE_TOOLS.get(agent_name, [])
    return tool_name in auto_tools


@entrypoint(checkpointer=_checkpointer_instance)
def ai_agent_workflow(request: AgentRequest) -> AgentResponse:
    """
    Main entrypoint for AI agent workflow using Functional API.
    
    Handles both regular execution and plan execution.
    
    Args:
        request: AgentRequest with query, session_id, user_id, etc.
                 If plan_steps is provided, executes plan instead of routing.
        
    Returns:
        AgentResponse with reply, tool_calls, token_usage, etc.
    """
    from langfuse import get_client
    from app.agents.config import LANGFUSE_ENABLED
    
    # Create trace for workflow if Langfuse is enabled
    langfuse = None
    trace_span = None
    if LANGFUSE_ENABLED:
        try:
            langfuse = get_client()
            if langfuse:
                # Use start_observation() to get the observation object directly
                # (start_as_current_observation returns a context manager)
                trace_span = langfuse.start_observation(
                    as_type="span",
                    name="ai_agent_workflow",
                    metadata={
                        "flow": request.flow,
                        "has_plan_steps": bool(request.plan_steps),
                        "user_id": str(request.user_id) if request.user_id else None,
                        "session_id": str(request.session_id) if request.session_id else None,
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to create Langfuse trace for workflow: {e}")
    
    try:
        # Get thread ID for checkpoint
        thread_id = f"chat_session_{request.session_id}" if request.session_id else f"user_{request.user_id}"
        checkpoint_config = get_checkpoint_config(request.session_id) if request.session_id else {"configurable": {"thread_id": thread_id}}
        
        # Get checkpointer instance (wrapper handles connection management)
        checkpointer = get_checkpointer()
        
        # Check if this is plan execution
        if request.plan_steps:
            return _execute_plan_workflow(request, checkpoint_config, checkpointer, thread_id)
        
        # Regular workflow execution
        # Load messages from checkpoint or database
        messages = load_messages_task(
            session_id=request.session_id,
            checkpointer=checkpointer,
            thread_id=thread_id
        ).result()
        
        # Add user message if not already present
        if not messages or not isinstance(messages[-1], HumanMessage) or messages[-1].content != request.query:
            messages = messages + [HumanMessage(content=request.query)]
        
        # Supervisor routing
        routing = supervisor_task(
            query=request.query,
            messages=messages,
            config=checkpoint_config
        ).result()
        
        logger.info(f"Supervisor routed to agent: {routing.agent}")
        
        # Check for clarification request
        if routing.require_clarification:
            return AgentResponse(
                type="answer",
                reply=routing.query,
                clarification=routing.query,
                agent_name="supervisor"
            )
        
        # Route to appropriate agent
        if routing.agent == "greeter":
            response = greeter_agent_task(
                query=routing.query,
                messages=messages,
                user_id=request.user_id,
                model_name=None,
                config=checkpoint_config
            ).result()
        elif routing.agent == "search":
            response = search_agent_task(
                query=routing.query,
                messages=messages,
                user_id=request.user_id,
                model_name=None,
                config=checkpoint_config
            ).result()
        else:
            response = agent_task(
                agent_name=routing.agent,
                query=routing.query,
                messages=messages,
                user_id=request.user_id,
                tool_results=None,
                model_name=None,
                config=checkpoint_config
            ).result()
        
        # Handle tool calls with proposal flow
        if response.tool_calls:
            logger.info(f"Found {len(response.tool_calls)} tool calls")
            
            # Create AIMessage with tool_calls from the response
            # This is required before adding ToolMessages (OpenAI API requirement)
            from langchain_core.messages import AIMessage
            
            # Build tool_calls with proper IDs
            tool_calls_with_ids = []
            for tc in response.tool_calls:
                tool_call_id = tc.get("id")
                if not tool_call_id:
                    # Generate ID if not present (fallback)
                    tool_call_id = f"{tc.get('name') or tc.get('tool', '')}_{hash(str(tc.get('args', {})))}"
                
                tool_calls_with_ids.append({
                    "name": tc.get("name") or tc.get("tool", ""),
                    "args": tc.get("args", {}),
                    "id": tool_call_id
                })
            
            ai_message_with_tool_calls = AIMessage(
                content=response.reply or "",
                tool_calls=tool_calls_with_ids
            )
            messages = messages + [ai_message_with_tool_calls]
            
            # Extract tool proposals
            tool_proposals = extract_tool_proposals(response.tool_calls)
            
            # Separate auto-executable from pending
            auto_executable = [
                p for p in tool_proposals
                if is_auto_executable(p.tool, routing.agent)
            ]
            pending = [
                p for p in tool_proposals
                if not is_auto_executable(p.tool, routing.agent)
            ]
            
            # Auto-execute tools in parallel if any
            if auto_executable:
                logger.info(f"Auto-executing {len(auto_executable)} tools")
                tool_calls_auto = [
                    {"name": p.tool, "args": p.props}
                    for p in auto_executable
                ]
                
                tool_results = tool_execution_task(
                    tool_calls=tool_calls_auto,
                    user_id=request.user_id,
                    agent_name=routing.agent,
                    chat_session_id=request.session_id,
                    config=checkpoint_config
                ).result()
                
                # Add tool results as ToolMessages
                # Match tool_call_id with the id from the AIMessage tool_calls
                tool_messages = []
                for tr in tool_results:
                    # Find matching tool_call_id from the AIMessage we just created
                    tool_call_id = None
                    for tc in ai_message_with_tool_calls.tool_calls:
                        if tc.get("name") == tr.tool:
                            tool_call_id = tc.get("id")
                            break
                    
                    if not tool_call_id:
                        # Fallback: try to get from response.tool_calls
                        for tc in response.tool_calls:
                            if (tc.get("name") or tc.get("tool")) == tr.tool:
                                tool_call_id = tc.get("id")
                                break
                    
                    if not tool_call_id:
                        # Final fallback to generated ID
                        tool_call_id = f"{tr.tool}_{hash(str(tr.args))}"
                    
                    tool_msg = ToolMessage(
                        content=str(tr.output) if tr.output else tr.error,
                        tool_call_id=tool_call_id,
                        name=tr.tool
                    )
                    tool_messages.append(tool_msg)
                
                # Add tool messages to conversation
                messages = messages + tool_messages
                
                # Re-invoke agent with tool results (refine)
                response = agent_with_tool_results_task(
                    agent_name=routing.agent,
                    query=routing.query,
                    messages=messages,
                    tool_results=tool_results,
                    user_id=request.user_id,
                    model_name=None,
                    config=checkpoint_config
                ).result()
                
                # Check for more tool calls after refine
                if response.tool_calls:
                    # Extract new proposals
                    new_proposals = extract_tool_proposals(response.tool_calls)
                    # Filter out already auto-executed tools
                    pending = [
                        p for p in new_proposals
                        if not is_auto_executable(p.tool, routing.agent)
                    ]
            
            # Create plan proposal if pending tools
            if pending:
                logger.info(f"Creating plan proposal with {len(pending)} pending tools")
                plan_steps = [
                    {
                        "action": "tool",
                        "tool": p.tool,
                        "props": p.props,
                        "agent": routing.agent,
                        "query": routing.query,
                    }
                    for p in pending
                ]
                return AgentResponse(
                    type="plan_proposal",
                    plan={
                        "type": "plan_proposal",
                        "plan": plan_steps,
                        "plan_index": 0,
                        "plan_total": len(plan_steps),
                    },
                    agent_name=routing.agent
                )
        
        # Save message to database if session_id provided
        # Save both regular answers and plan proposals
        if request.session_id and (response.reply or response.type == "plan_proposal"):
            save_message_task(
                response=response,
                session_id=request.session_id,
                user_id=request.user_id,
                tool_calls=response.tool_calls
            ).result()
        
        # Update trace with final response
        if trace_span:
            try:
                trace_span.update(
                    output={
                        "type": response.type,
                        "agent_name": response.agent_name,
                        "has_reply": bool(response.reply),
                        "tool_calls_count": len(response.tool_calls) if response.tool_calls else 0,
                    }
                )
                trace_span.end()
            except Exception as e:
                logger.warning(f"Failed to update Langfuse trace: {e}")
            finally:
                # Ensure span is ended even if update fails
                try:
                    if trace_span:
                        trace_span.end()
                except Exception:
                    pass
        
        return response
        
    except Exception as e:
        logger.error(f"Error in ai_agent_workflow: {e}", exc_info=True)
        
        # Update trace with error
        if trace_span:
            try:
                trace_span.update(
                    output=None,
                    level="ERROR",
                    status_message=str(e)
                )
            except Exception:
                pass
            finally:
                # Ensure span is ended
                try:
                    if trace_span:
                        trace_span.end()
                except Exception:
                    pass
        
        return AgentResponse(
            type="answer",
            reply=f"I apologize, but I encountered an error: {str(e)}",
            agent_name="system"
        )


def _execute_plan_workflow(
    request: AgentRequest,
    checkpoint_config: Dict[str, Any],
    checkpointer: Optional[PostgresSaver],
    thread_id: str
) -> AgentResponse:
    """
    Execute plan workflow (internal helper function).
    
    Args:
        request: AgentRequest with plan_steps
        checkpoint_config: Checkpoint configuration
        checkpointer: Checkpointer instance
        thread_id: Thread ID for checkpoint
        
    Returns:
        AgentResponse with combined results
    """
    from langfuse import get_client
    from app.agents.config import LANGFUSE_ENABLED
    
    # Create trace for plan execution if Langfuse is enabled
    langfuse = None
    plan_span = None
    if LANGFUSE_ENABLED:
        try:
            langfuse = get_client()
            if langfuse:
                # Use start_observation() to get the observation object directly
                plan_span = langfuse.start_observation(
                    as_type="span",
                    name="plan_execution",
                    metadata={
                        "plan_steps_count": len(request.plan_steps) if request.plan_steps else 0,
                        "user_id": str(request.user_id) if request.user_id else None,
                        "session_id": str(request.session_id) if request.session_id else None,
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to create Langfuse trace for plan execution: {e}")
    
    try:
        
        # Load messages
        messages = load_messages_task(
            session_id=request.session_id,
            checkpointer=checkpointer,
            thread_id=thread_id
        ).result()
        
        results: List[str] = []
        raw_tool_outputs: List[Dict[str, Any]] = []
        
        # Process each plan step
        for step in request.plan_steps or []:
            action = step.get("action")
            
            if action == "answer":
                answer = step.get("answer", "")
                if answer:
                    results.append(answer)
                continue
            
            if action == "tool":
                tool_name = step.get("tool")
                tool_args = step.get("props", {})
                agent_name = step.get("agent", "greeter")
                step_query = step.get("query", request.query)
                
                # Execute tool
                tool_calls = [{"name": tool_name, "args": tool_args}]
                tool_results = tool_execution_task(
                    tool_calls=tool_calls,
                    user_id=request.user_id,
                    agent_name=agent_name,
                    chat_session_id=request.session_id,
                    config=checkpoint_config
                ).result()
                
                if tool_results:
                    tool_result = tool_results[0]
                    
                    # Store raw output
                    raw_tool_outputs.append({
                        "tool": tool_result.tool,
                        "args": tool_result.args,
                        "output": tool_result.output,
                    })
                    
                    # Add tool result as ToolMessage
                    tool_msg = ToolMessage(
                        content=str(tool_result.output) if tool_result.output else tool_result.error,
                        tool_call_id=f"{tool_result.tool}_{hash(str(tool_result.args))}",
                        name=tool_result.tool
                    )
                    messages = messages + [tool_msg]
                    
                    # Post-process with agent
                    if tool_result.output is not None or tool_result.error:
                        agent_response = agent_with_tool_results_task(
                            agent_name=agent_name,
                            query=step_query,
                            messages=messages,
                            tool_results=tool_results,
                            user_id=request.user_id,
                            model_name=None,
                            config=checkpoint_config
                        ).result()
                        
                        if agent_response.reply:
                            results.append(agent_response.reply)
        
        # Combine results
        final_text = "\n".join(results) if results else ""
        
        # Save message if session_id provided
        if request.session_id and final_text:
            final_response = AgentResponse(
                type="answer",
                reply=final_text,
                agent_name=request.plan_steps[0].get("agent", "greeter") if request.plan_steps else "greeter"
            )
            save_message_task(
                response=final_response,
                session_id=request.session_id,
                user_id=request.user_id,
                tool_calls=[]
            ).result()
        
        # Update plan execution trace
        if plan_span:
            try:
                plan_span.update(
                    output={
                        "steps_completed": len(results),
                        "tools_executed": len(raw_tool_outputs) if raw_tool_outputs else 0,
                        "final_text_length": len(final_text),
                    }
                )
                plan_span.end()
            except Exception as e:
                logger.warning(f"Failed to update Langfuse plan execution trace: {e}")
        
        return AgentResponse(
            type="answer",
            reply=final_text,
            raw_tool_outputs=raw_tool_outputs if raw_tool_outputs else None,
            agent_name=request.plan_steps[0].get("agent", "greeter") if request.plan_steps else "greeter"
        )
    except Exception as e:
        logger.error(f"Error in plan execution: {e}", exc_info=True)
        
        # Update plan execution trace with error
        if plan_span:
            try:
                plan_span.update(
                    output=None,
                    level="ERROR",
                    status_message=str(e)
                )
            except Exception:
                pass
            finally:
                # Ensure span is ended
                try:
                    if plan_span:
                        plan_span.end()
                except Exception:
                    pass
        
        return AgentResponse(
            type="answer",
            reply=f"I apologize, but I encountered an error executing the plan: {str(e)}",
            agent_name="system"
        )
