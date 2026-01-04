"""
LangGraph definition.
"""
# from langgraph.graph import StateGraph
# from .state import AgentState
# from .nodes import retrieve_context_node, llm_node

# TODO: Define LangGraph
# def create_agent_graph(user_id: int):
#     """
#     Create agent graph for a user.
#     """
#     graph = StateGraph(AgentState)
#     
#     # Add nodes
#     graph.add_node("retrieve", retrieve_context_node)
#     graph.add_node("llm", llm_node)
#     
#     # Add edges
#     graph.set_entry_point("retrieve")
#     graph.add_edge("retrieve", "llm")
#     graph.add_edge("llm", END)
#     
#     return graph.compile()
