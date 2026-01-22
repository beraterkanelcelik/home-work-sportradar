"""
Scouting workflow task functions for LangGraph Functional API.

These tasks implement the dynamic plan-driven scouting workflow:

Plan Generation:
- generate_plan - Generate dynamic execution plan based on intent

Execution Actions:
- retrieve_evidence - RAG search (rag_search action)
- extract_fields - Extract structured player data (extract_player action)
- compose_report - Generate scouting report (compose_report action)
- write_player_item - Save to database (save_player action)
- build_final_response - Generate final response (answer action)

Legacy (deprecated):
- intake_and_route_scouting - Use supervisor routing instead
- draft_plan - Use generate_plan instead
- build_queries - Queries now generated in plan steps
- prepare_preview - Merged into compose_report
"""

from .intake import intake_and_route_scouting
from .plan import draft_plan, generate_plan
from .queries import build_queries
from .retrieval import retrieve_evidence
from .extraction import extract_fields
from .composition import compose_report
from .preview import prepare_preview
from .write import write_player_item
from .response import build_final_response

__all__ = [
    # New dynamic plan
    "generate_plan",
    # Execution actions
    "retrieve_evidence",
    "extract_fields",
    "compose_report",
    "write_player_item",
    "build_final_response",
    # Legacy (deprecated)
    "intake_and_route_scouting",
    "draft_plan",
    "build_queries",
    "prepare_preview",
]
