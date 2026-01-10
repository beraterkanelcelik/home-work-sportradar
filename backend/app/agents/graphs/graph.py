"""
Main LangGraph definition for supervisor-based multi-agent system.
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from app.agents.graphs.state import AgentState
from app.agents.graphs.nodes import supervisor_node, greeter_node, agent_node, tool_node
from app.agents.graphs.routers import route_message
from app.agents.checkpoint import get_checkpoint_saver
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_agent_graph(checkpoint_saver: BaseCheckpointSaver = None) -> StateGraph:
    """
    Create and compile the agent graph.
    
    Args:
        checkpoint_saver: Optional checkpoint saver (uses default if None)
        
    Returns:
        Compiled StateGraph
    """
    # Create state graph
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("greeter", greeter_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tool", tool_node)
    
    # Set entry point
    graph.set_entry_point("supervisor")
    
    # Add conditional edges from supervisor
    graph.add_conditional_edges(
        "supervisor",
        route_message,
        {
            "greeter": "greeter",
            "agent": "agent",
            "end": END,
        }
    )
    
    # Add conditional edges from greeter and agent - check for tool calls
    def should_continue(state: AgentState) -> str:
        """Check if agent made tool calls and route accordingly."""
        messages = state.get("messages", [])
        if not messages:
            return "end"
        
        last_message = messages[-1]
        # Check if last message has tool calls
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tool"
        return "end"
    
    graph.add_conditional_edges(
        "greeter",
        should_continue,
        {
            "tool": "tool",
            "end": END,
        }
    )
    
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tool": "tool",
            "end": END,
        }
    )
    
    # After tool execution, route back to the agent that called it
    def route_after_tool(state: AgentState) -> str:
        """Route back to the agent that called the tool."""
        current_agent = state.get("current_agent", "greeter")
        if current_agent == "greeter":
            return "greeter"
        else:
            return "agent"
    
    graph.add_conditional_edges(
        "tool",
        route_after_tool,
        {
            "greeter": "greeter",
            "agent": "agent",
        }
    )
    
    # Compile with checkpoint if provided
    if checkpoint_saver:
        try:
            compiled_graph = graph.compile(checkpointer=checkpoint_saver)
            logger.debug("Graph compiled with checkpoint persistence")
        except Exception as e:
            logger.error(f"Failed to compile graph with checkpoint: {e}", exc_info=True)
            logger.warning("Falling back to graph without checkpoint")
            compiled_graph = graph.compile()
    else:
        compiled_graph = graph.compile()
        logger.debug("Graph compiled without checkpoint persistence")
    
    return compiled_graph
