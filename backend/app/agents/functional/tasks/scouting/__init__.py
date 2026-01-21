"""
Scouting workflow task functions for LangGraph Functional API.

These tasks implement the 9-node scouting report flow:
1. intake_and_route_scouting - Parse request, extract player_name
2. draft_plan - Generate 4-7 step plan
3. build_queries - Generate 3-6 diversified queries
4. retrieve_evidence - Multi-query RAG retrieval
5. extract_fields - Extract structured player fields
6. compose_report - Generate scouting report
7. prepare_preview - Format for approval UI
8. write_player_item - Create player + report in DB
9. build_final_response - Assemble final response
"""

from .intake import intake_and_route_scouting
from .plan import draft_plan
from .queries import build_queries
from .retrieval import retrieve_evidence
from .extraction import extract_fields
from .composition import compose_report
from .preview import prepare_preview
from .write import write_player_item
from .response import build_final_response

__all__ = [
    "intake_and_route_scouting",
    "draft_plan",
    "build_queries",
    "retrieve_evidence",
    "extract_fields",
    "compose_report",
    "prepare_preview",
    "write_player_item",
    "build_final_response",
]
