"""
Query pipeline: orchestrates query embedding, vector search, reranking, and context formatting.

Extended for scouting workflow with:
- query_rag_batch: Multi-query retrieval with deduplication
- deduplicate_chunks: Remove duplicate chunks across queries
- calculate_coverage: Assess what fields were found vs missing
- to_evidence_pack: Convert results to EvidencePack schema
"""

import time
import hashlib
from typing import List, Optional, Dict, Any, Tuple, Set
from django.conf import settings
import os

from app.rag.embeddings import OpenAIEmbeddingsClient

from app.rag.vectorstore import PgVectorStore
from app.rag.rerank import CohereRerankerClient
from app.rag.prompts.context_formatter import ContextFormatter
from app.observability.tracing import get_langfuse_client
from app.core.logging import get_logger

logger = get_logger(__name__)


def query_rag(
    user_id: int,
    query: str,
    top_k: int = None,
    top_n: int = None,
    document_ids: Optional[List[int]] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query RAG pipeline.

    Steps:
    1. Embed query
    2. Vector search (top_k)
    3. Rerank (top 20-30)
    4. Format context blocks

    Args:
        user_id: User ID for multi-tenant filtering
        query: Search query text
        top_k: Initial retrieval count (defaults to RAG_TOP_K)
        top_n: Final chunks after reranking (defaults to RAG_TOP_N)
        document_ids: Optional list of document IDs to filter by

    Returns:
        Dict with 'items' (formatted chunks) and 'debug' (metadata)
    """
    start_time = time.time()
    langfuse = get_langfuse_client()

    # Defaults from settings
    top_k = top_k or getattr(settings, "RAG_TOP_K", 30)
    top_n = top_n or getattr(settings, "RAG_TOP_N", 8)

    # Initialize components
    vector_store = PgVectorStore()
    formatter = ContextFormatter()

    if not api_key:
        raise ValueError("OpenAI API key is required for RAG queries")

    embeddings_client = OpenAIEmbeddingsClient(api_key=api_key)

    # Context manager for langfuse (handles None case)
    # For Langfuse v3, we'll use a simple no-op context manager if client is None
    # Otherwise, use the start_as_current_span context manager directly
    def langfuse_trace(name, metadata=None):
        if langfuse:
            try:
                # start_as_current_span returns a context manager
                # We'll use it directly and not try to update metadata for now
                return langfuse.start_as_current_span(name=name)
            except (AttributeError, TypeError):
                # If the method doesn't exist or fails, return a no-op context manager
                pass

        # No-op context manager when langfuse is not available
        class NoOpContext:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        return NoOpContext()

    # Step 1: Embed query
    with langfuse_trace("embed_query"):
        # Pass user_id for token usage tracking
        query_vector = embeddings_client.embed_query(query, user_id=user_id)

    # Step 2: Vector search
    with langfuse_trace("vector_search", {"top_k": top_k}):
        chunks_with_scores = vector_store.query(
            query_vector=query_vector,
            top_k=top_k,
            owner_id=user_id,
            document_ids=document_ids,
        )

    if not chunks_with_scores:
        return {
            "items": [],
            "debug": {
                "retrieved": 0,
                "reranked": 0,
                "returned": 0,
                "latency_ms": int((time.time() - start_time) * 1000),
            },
        }

    # Step 3: Rerank (if reranker available)
    reranked_chunks = chunks_with_scores

    try:
        if os.getenv("COHERE_API_KEY"):
            reranker = CohereRerankerClient()

            # Prepare texts for reranking
            chunk_texts = [chunk.content for chunk, _ in chunks_with_scores]
            # Truncate for reranking efficiency (rerankers have token limits)
            max_rerank_length = 500  # characters per chunk
            truncated_texts = [text[:max_rerank_length] for text in chunk_texts]

            with langfuse_trace("rerank", {"count": len(truncated_texts)}):
                # Rerank top candidates (rerank more than we need, then take top_n)
                rerank_count = min(30, len(chunks_with_scores))
                rerank_texts = truncated_texts[:rerank_count]

                rerank_results = reranker.rerank(
                    query=query, docs=rerank_texts, top_n=min(top_n, rerank_count)
                )

                # Reorder chunks based on rerank results
                reranked_chunks = []
                for idx, score in rerank_results:
                    if idx < len(chunks_with_scores):
                        original_chunk, _ = chunks_with_scores[idx]
                        reranked_chunks.append((original_chunk, float(score)))
    except Exception as e:
        # If reranking fails, use original vector search results
        # In production, you might want to log this
        pass

    # Step 4: Format context
    with langfuse_trace("format_context"):
        result = formatter.format_context(reranked_chunks)

    # Add latency to debug info
    result["debug"]["latency_ms"] = int((time.time() - start_time) * 1000)

    return result


# =============================================================================
# Scouting Workflow Extensions
# =============================================================================

# Expected fields for coverage calculation
EXPECTED_SCOUTING_FIELDS = [
    "positions",
    "teams",
    "league",
    "height",
    "weight",
    "strengths",
    "weaknesses",
    "style",
    "draft",
]

# Keywords that indicate a field was found in evidence
FIELD_KEYWORDS = {
    "positions": ["position", "plays at", "guard", "forward", "center", "quarterback", "receiver", "linebacker"],
    "teams": ["team", "plays for", "signed with", "drafted by", "traded to"],
    "league": ["nba", "nfl", "league", "ncaa", "college"],
    "height": ["height", "tall", "feet", "inches", "cm", "6'", "7'", "5'"],
    "weight": ["weight", "pounds", "lbs", "kg", "kilograms"],
    "strengths": ["strength", "excels", "excellent", "great at", "best", "elite", "strong"],
    "weaknesses": ["weakness", "struggles", "needs improvement", "limited", "poor", "lacks"],
    "style": ["style", "plays like", "tendency", "tendencies", "approach", "technique"],
    "draft": ["draft", "picked", "selection", "prospect", "combine"],
}


def deduplicate_chunks(
    chunks_with_scores: List[Tuple[Any, float]],
    method: str = "doc_chunk_id",
) -> List[Tuple[Any, float]]:
    """
    Deduplicate chunks from multiple queries.

    Args:
        chunks_with_scores: List of (chunk, score) tuples
        method: Deduplication method
            - "doc_chunk_id": By document_id + chunk_id (default)
            - "text_hash": By normalized text hash
            - "both": Use doc_chunk_id first, text_hash as fallback

    Returns:
        Deduplicated list of (chunk, score) tuples, keeping highest score
    """
    seen: Dict[str, Tuple[Any, float]] = {}

    for chunk, score in chunks_with_scores:
        # Generate dedup key based on method
        if method == "text_hash":
            # Normalize text: lowercase, strip whitespace
            normalized = chunk.content.lower().strip()
            key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        elif method == "both":
            # Use composite key
            doc_id = getattr(chunk, "document_id", None) or getattr(chunk, "doc_id", "unknown")
            chunk_id = getattr(chunk, "id", None) or getattr(chunk, "chunk_id", "unknown")
            normalized = chunk.content.lower().strip()
            text_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
            key = f"{doc_id}:{chunk_id}:{text_hash}"
        else:  # doc_chunk_id (default)
            doc_id = getattr(chunk, "document_id", None) or getattr(chunk, "doc_id", "unknown")
            chunk_id = getattr(chunk, "id", None) or getattr(chunk, "chunk_id", "unknown")
            key = f"{doc_id}:{chunk_id}"

        # Keep chunk with highest score
        if key not in seen or score > seen[key][1]:
            seen[key] = (chunk, score)

    # Sort by score descending
    result = sorted(seen.values(), key=lambda x: x[1], reverse=True)
    return result


def calculate_coverage(
    chunks: List[Any],
    expected_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Calculate coverage: what fields have evidence vs what's missing.

    Args:
        chunks: List of chunk objects with content attribute
        expected_fields: Fields to check (defaults to EXPECTED_SCOUTING_FIELDS)

    Returns:
        Dict with:
        - found: List of fields with evidence
        - missing: List of fields without evidence
        - confidence: "low" | "med" | "high"
    """
    if expected_fields is None:
        expected_fields = EXPECTED_SCOUTING_FIELDS

    # Combine all chunk text for analysis
    all_text = " ".join(
        getattr(chunk, "content", str(chunk)).lower()
        for chunk in chunks
    )

    found = []
    missing = []

    for field in expected_fields:
        keywords = FIELD_KEYWORDS.get(field, [field])
        # Check if any keyword appears in the text
        if any(kw.lower() in all_text for kw in keywords):
            found.append(field)
        else:
            missing.append(field)

    # Calculate confidence based on coverage percentage
    if len(expected_fields) > 0:
        coverage_pct = len(found) / len(expected_fields)
    else:
        coverage_pct = 0.0

    if coverage_pct >= 0.7:
        confidence = "high"
    elif coverage_pct >= 0.3:
        confidence = "med"
    else:
        confidence = "low"

    return {
        "found": found,
        "missing": missing,
        "confidence": confidence,
        "coverage_pct": round(coverage_pct * 100, 1),
    }


def query_rag_batch(
    user_id: int,
    queries: List[str],
    top_k_per_query: int = 15,
    max_chunks: int = 40,
    document_ids: Optional[List[int]] = None,
    api_key: Optional[str] = None,
    dedupe_method: str = "doc_chunk_id",
) -> Dict[str, Any]:
    """
    Execute multiple queries and combine results with deduplication.

    For scouting workflow: runs 3-6 diversified queries, deduplicates,
    and enforces a hard chunk budget.

    Args:
        user_id: User ID for multi-tenant filtering
        queries: List of query strings (3-6 recommended)
        top_k_per_query: Results per query before deduplication (default 15)
        max_chunks: Hard cap on final chunks (default 40 per spec)
        document_ids: Optional document ID filter
        api_key: OpenAI API key
        dedupe_method: Deduplication method ("doc_chunk_id", "text_hash", "both")

    Returns:
        Dict with:
        - chunks: List of (chunk, score) tuples (max max_chunks)
        - queries: Queries executed
        - coverage: Coverage analysis
        - confidence: Confidence level
        - debug: Metadata
    """
    start_time = time.time()

    if not queries:
        return {
            "chunks": [],
            "queries": [],
            "coverage": {"found": [], "missing": EXPECTED_SCOUTING_FIELDS},
            "confidence": "low",
            "debug": {"total_retrieved": 0, "after_dedup": 0, "final": 0},
        }

    if not api_key:
        raise ValueError("OpenAI API key is required for RAG queries")

    # Initialize components
    vector_store = PgVectorStore()
    embeddings_client = OpenAIEmbeddingsClient(api_key=api_key)

    all_chunks: List[Tuple[Any, float]] = []
    query_results = {}

    # Execute each query
    for query in queries:
        try:
            # Embed query
            query_vector = embeddings_client.embed_query(query, user_id=user_id)

            # Vector search
            chunks_with_scores = vector_store.query(
                query_vector=query_vector,
                top_k=top_k_per_query,
                owner_id=user_id,
                document_ids=document_ids,
            )

            query_results[query] = len(chunks_with_scores)
            all_chunks.extend(chunks_with_scores)

        except Exception as e:
            logger.warning(f"Query failed: {query[:50]}... Error: {e}")
            query_results[query] = 0

    total_retrieved = len(all_chunks)

    # Deduplicate
    deduped_chunks = deduplicate_chunks(all_chunks, method=dedupe_method)
    after_dedup = len(deduped_chunks)

    # Enforce chunk budget
    final_chunks = deduped_chunks[:max_chunks]

    # Calculate coverage
    chunk_objects = [chunk for chunk, _ in final_chunks]
    coverage_result = calculate_coverage(chunk_objects)

    latency_ms = int((time.time() - start_time) * 1000)

    logger.info(
        f"query_rag_batch: {len(queries)} queries, "
        f"{total_retrieved} retrieved, {after_dedup} after dedup, "
        f"{len(final_chunks)} final, confidence={coverage_result['confidence']}"
    )

    return {
        "chunks": final_chunks,
        "queries": queries,
        "coverage": {
            "found": coverage_result["found"],
            "missing": coverage_result["missing"],
        },
        "confidence": coverage_result["confidence"],
        "debug": {
            "total_retrieved": total_retrieved,
            "after_dedup": after_dedup,
            "final": len(final_chunks),
            "per_query": query_results,
            "latency_ms": latency_ms,
            "coverage_pct": coverage_result["coverage_pct"],
        },
    }


def to_evidence_pack(
    batch_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Convert query_rag_batch result to EvidencePack schema format.

    Args:
        batch_result: Result from query_rag_batch

    Returns:
        Dict matching EvidencePack schema:
        - queries: List[str]
        - chunks: List[ChunkData]
        - coverage: Coverage
        - confidence: "low" | "med" | "high"
    """
    chunks_data = []

    for chunk, score in batch_result.get("chunks", []):
        # Extract IDs handling both ORM objects and dicts
        doc_id = getattr(chunk, "document_id", None)
        if doc_id is None:
            doc_id = getattr(chunk, "doc_id", "unknown")

        chunk_id = getattr(chunk, "id", None)
        if chunk_id is None:
            chunk_id = getattr(chunk, "chunk_id", "unknown")

        text = getattr(chunk, "content", str(chunk))

        chunks_data.append({
            "doc_id": str(doc_id),
            "chunk_id": str(chunk_id),
            "text": text,
            "score": float(score),
        })

    return {
        "queries": batch_result.get("queries", []),
        "chunks": chunks_data,
        "coverage": batch_result.get("coverage", {"found": [], "missing": []}),
        "confidence": batch_result.get("confidence", "low"),
    }
