"""
Retrieval task: Execute multi-query RAG and produce EvidencePack.

Node 4 in the scouting workflow.
"""

from typing import Optional, List
from langgraph.func import task
from app.agents.functional.scouting.schemas import EvidencePack, ChunkData, Coverage
from app.rag.pipelines.query_pipeline import query_rag_batch, to_evidence_pack
from app.core.logging import get_logger

logger = get_logger(__name__)


@task
def retrieve_evidence(
    user_id: int,
    queries: List[str],
    api_key: Optional[str] = None,
    document_ids: Optional[List[int]] = None,
    max_chunks: int = 40,
) -> EvidencePack:
    """
    Execute multi-query RAG retrieval and produce EvidencePack.

    Args:
        user_id: User ID for multi-tenant filtering
        queries: List of search queries (3-6)
        api_key: OpenAI API key for embeddings
        document_ids: Optional document filter
        max_chunks: Maximum chunks to return (default 40)

    Returns:
        EvidencePack with chunks, coverage, and confidence
    """
    logger.info(f"[RETRIEVAL] Starting with {len(queries)} queries for user {user_id}")

    if not queries:
        logger.warning("[RETRIEVAL] No queries provided")
        return EvidencePack(
            queries=[],
            chunks=[],
            coverage=Coverage(found=[], missing=[]),
            confidence="low",
        )

    if not api_key:
        raise ValueError("OpenAI API key is required for retrieval")

    try:
        # Execute batch query
        batch_result = query_rag_batch(
            user_id=user_id,
            queries=queries,
            top_k_per_query=15,
            max_chunks=max_chunks,
            document_ids=document_ids,
            api_key=api_key,
            dedupe_method="doc_chunk_id",
        )

        # Convert to EvidencePack format
        evidence_dict = to_evidence_pack(batch_result)

        # Build Pydantic models
        chunks = [
            ChunkData(
                doc_id=c["doc_id"],
                chunk_id=c["chunk_id"],
                text=c["text"],
                score=c["score"],
            )
            for c in evidence_dict.get("chunks", [])
        ]

        coverage = Coverage(
            found=evidence_dict.get("coverage", {}).get("found", []),
            missing=evidence_dict.get("coverage", {}).get("missing", []),
        )

        evidence_pack = EvidencePack(
            queries=evidence_dict.get("queries", queries),
            chunks=chunks,
            coverage=coverage,
            confidence=evidence_dict.get("confidence", "low"),
        )

        logger.info(
            f"[RETRIEVAL] Retrieved {len(evidence_pack.chunks)} chunks, "
            f"confidence={evidence_pack.confidence}"
        )

        return evidence_pack

    except Exception as e:
        logger.error(f"[RETRIEVAL] Error during retrieval: {e}", exc_info=True)
        # Return empty evidence pack on error
        return EvidencePack(
            queries=queries,
            chunks=[],
            coverage=Coverage(found=[], missing=[]),
            confidence="low",
        )
