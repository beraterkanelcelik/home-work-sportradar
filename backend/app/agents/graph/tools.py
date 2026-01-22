"""
LangChain tools for the StateGraph agent workflow.

Architecture:
- @tool decorated functions define the SCHEMA for the LLM (name, description, args)
- TOOL_EXECUTORS contains the ACTUAL implementations called by tool_node
- This separation allows injecting runtime context (user_id, api_key) that
  the LLM doesn't have access to

The tool_node in nodes.py:
1. Receives tool calls from the LLM
2. Looks up the executor in TOOL_EXECUTORS
3. Calls the executor with injected context

Pydantic Validation:
- Tool inputs are validated using Pydantic models before execution
- Tool outputs are validated using Pydantic models for consistency
"""

from typing import Dict, Any
from pydantic import ValidationError
from langchain_core.tools import tool
from app.rag.pipelines.query_pipeline import query_rag_batch
from app.services.scouting_report_service import create_with_player
from app.core.logging import get_logger
from .models import (
    SearchDocumentsInput,
    SearchDocumentsOutput,
    SavePlayerReportInput,
    SavePlayerReportOutput,
    PlayerData,
)

logger = get_logger(__name__)


# =============================================================================
# Tool Schemas (for LLM binding via .bind_tools())
# =============================================================================

@tool
def search_documents(query: str) -> str:
    """
    Search user's uploaded documents for information about players, stats, or any topic.

    Use this tool to find relevant information from the user's document library.
    You can search for player names, statistics, strengths, weaknesses, or any
    other information that might be in scouting reports or documents.

    Args:
        query: What to search for. Be specific for better results.
               Examples: "Messi career statistics", "Haaland physical attributes",
               "player strengths and weaknesses"

    Returns:
        Relevant text excerpts from the user's documents with source citations.
    """
    # Schema-only: actual execution in TOOL_EXECUTORS
    raise NotImplementedError(
        "search_documents is schema-only. Execution happens via TOOL_EXECUTORS in tool_node."
    )


@tool
def save_player_report(player_name: str, report_summary: str) -> str:
    """
    Save a player scouting report to the database.

    IMPORTANT: This tool triggers user approval (HITL Gate 2).
    The system will show the user a player preview and ask for confirmation.

    WHEN TO CALL THIS TOOL:
    - Call this AUTOMATICALLY after completing all search steps in a scouting plan
    - Do NOT wait for user to ask - the workflow requires this tool to proceed
    - After this tool is called, the user sees a player preview and can approve/reject

    Args:
        player_name: Full name of the player (e.g., "Erling Haaland")
        report_summary: Brief 1-2 sentence summary of the report contents

    Returns:
        Confirmation message with player_id and report_id after user approval.
    """
    # Schema-only: actual execution in TOOL_EXECUTORS
    raise NotImplementedError(
        "save_player_report is schema-only. Execution happens via TOOL_EXECUTORS in tool_node."
    )


# Export tools for binding to LLM
TOOLS = [search_documents, save_player_report]


# =============================================================================
# Tool Implementations (called by tool_node with injected context)
# =============================================================================

def execute_search_documents(query: str, user_id: int, api_key: str) -> str:
    """
    Execute RAG search on user's documents.

    Args:
        query: Search query string
        user_id: User ID for multi-tenant document filtering
        api_key: OpenAI API key for embeddings

    Returns:
        Formatted search results with source citations

    Raises:
        ValidationError: If query is invalid
    """
    # Validate input with Pydantic
    try:
        validated_input = SearchDocumentsInput(query=query)
        query = validated_input.query  # Use validated/cleaned query
    except ValidationError as e:
        logger.warning(f"[TOOL] search_documents validation error: {e}")
        return f"Invalid query: {e.errors()[0]['msg']}"

    logger.info(f"[TOOL] search_documents: query={query[:50]}... user_id={user_id}")

    try:
        result = query_rag_batch(
            user_id=user_id,
            queries=[query],
            max_chunks=10,
            api_key=api_key,
        )

        chunks = result.get("chunks", [])
        if not chunks:
            output = SearchDocumentsOutput(
                results="No relevant documents found for this query.",
                chunk_count=0
            )
            return output.results

        # Format results - chunks is a list of (DocumentChunk, score) tuples
        formatted = []
        for chunk, score in chunks[:5]:
            # DocumentChunk has .content and .document.title
            source = chunk.document.title if hasattr(chunk, "document") and chunk.document else "Unknown source"
            content = chunk.content if hasattr(chunk, "content") else str(chunk)
            content = content[:500] if len(content) > 500 else content
            formatted.append(f"**[{source}]**\n{content}")

        logger.info(f"[TOOL] search_documents: found {len(chunks)} chunks, returning top {len(formatted)}")

        output = SearchDocumentsOutput(
            results="\n\n---\n\n".join(formatted),
            chunk_count=len(chunks)
        )
        return output.results

    except ValidationError as e:
        logger.error(f"[TOOL] search_documents output validation error: {e}", exc_info=True)
        return f"Error formatting results: {str(e)}"
    except Exception as e:
        logger.error(f"[TOOL] search_documents error: {e}", exc_info=True)
        return f"Error searching documents: {str(e)}"


def execute_save_player_report(
    player_name: str,
    player_data: dict,
    report_text: str,
    user_id: int,
) -> Dict[str, Any]:
    """
    Save player and scouting report to database.

    This is called AFTER user approval via the HITL flow.

    Args:
        player_name: Player's display name
        player_data: Dict with player fields (display_name, position, team, etc.)
        report_text: Full report text content
        user_id: Owner user ID

    Returns:
        Dict with success status, player_id, and report_id
    """
    logger.info(f"[TOOL] save_player_report: player={player_name} user_id={user_id}")

    try:
        # Validate player_name input
        try:
            validated_input = SavePlayerReportInput(
                player_name=player_name,
                report_summary=report_text[:500] if report_text else "No summary"
            )
            player_name = validated_input.player_name
        except ValidationError as e:
            logger.warning(f"[TOOL] save_player_report input validation error: {e}")
            output = SavePlayerReportOutput(
                success=False,
                error=f"Invalid input: {e.errors()[0]['msg']}"
            )
            return output.model_dump()

        # Ensure player_data has required fields and validate
        if not player_data:
            player_data = {}
        if "display_name" not in player_data:
            player_data["display_name"] = player_name

        # Validate player data with Pydantic (non-strict, allows extra fields)
        try:
            validated_player = PlayerData(
                display_name=player_data.get("display_name", player_name),
                position=player_data.get("position"),
                team=player_data.get("team"),
                nationality=player_data.get("nationality"),
                age=player_data.get("age"),
                height=player_data.get("height"),
                weight=player_data.get("weight"),
                preferred_foot=player_data.get("preferred_foot"),
                strengths=player_data.get("strengths"),
                weaknesses=player_data.get("weaknesses"),
                market_value=player_data.get("market_value"),
            )
            # Update player_data with validated/cleaned values
            player_data["display_name"] = validated_player.display_name
        except ValidationError as e:
            logger.warning(f"[TOOL] save_player_report player_data validation error: {e}")
            # Continue with original data but log the issue
            pass

        # Build report_data dict for create_with_player
        report_data = {
            "report_text": report_text,
            "report_summary": [report_text[:200]] if report_text else [],
        }

        # create_with_player returns (Player, ScoutingReport) tuple
        player, report = create_with_player(
            owner_id=user_id,
            player_fields=player_data,
            report_data=report_data,
        )

        logger.info(f"[TOOL] save_player_report: created player_id={player.id} report_id={report.id}")

        # Validate and return output
        output = SavePlayerReportOutput(
            success=True,
            player_id=str(player.id),
            report_id=str(report.id),
            message=f"Successfully saved report for {player_name}",
        )
        return output.model_dump()

    except ValidationError as e:
        logger.error(f"[TOOL] save_player_report output validation error: {e}", exc_info=True)
        return SavePlayerReportOutput(
            success=False,
            error=f"Output validation error: {str(e)}"
        ).model_dump()
    except Exception as e:
        logger.error(f"[TOOL] save_player_report error: {e}", exc_info=True)
        return SavePlayerReportOutput(
            success=False,
            error=str(e)
        ).model_dump()


# =============================================================================
# Tool Executor Registry
# =============================================================================

TOOL_EXECUTORS = {
    "search_documents": execute_search_documents,
    "save_player_report": execute_save_player_report,
}
