"""
Query pipeline: orchestrates query embedding, vector search, reranking, and context formatting.
"""
import time
from typing import List, Optional, Dict, Any
from django.conf import settings
from app.rag.embeddings import OpenAIEmbeddingsClient, MockEmbeddingsClient
from app.rag.vectorstore import PgVectorStore
from app.rag.rerank import CohereRerankerClient
from app.rag.prompts.context_formatter import ContextFormatter
from app.observability.tracing import get_langfuse_client


def query_rag(
    user_id: int,
    query: str,
    top_k: int = None,
    top_n: int = None,
    document_ids: Optional[List[int]] = None
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
    top_k = top_k or getattr(settings, 'RAG_TOP_K', 30)
    top_n = top_n or getattr(settings, 'RAG_TOP_N', 8)
    
    # Initialize components
    vector_store = PgVectorStore()
    formatter = ContextFormatter()
    
    # Determine embedding client
    import os
    if os.getenv('OPENAI_API_KEY'):
        embeddings_client = OpenAIEmbeddingsClient()
    else:
        embeddings_client = MockEmbeddingsClient()
    
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
    with langfuse_trace("vector_search", {'top_k': top_k}):
        chunks_with_scores = vector_store.query(
            query_vector=query_vector,
            top_k=top_k,
            owner_id=user_id,
            document_ids=document_ids
        )
    
    if not chunks_with_scores:
        return {
            'items': [],
            'debug': {
                'retrieved': 0,
                'reranked': 0,
                'returned': 0,
                'latency_ms': int((time.time() - start_time) * 1000)
            }
        }
    
    # Step 3: Rerank (if reranker available)
    reranked_chunks = chunks_with_scores
    
    try:
        if os.getenv('COHERE_API_KEY'):
            reranker = CohereRerankerClient()
            
            # Prepare texts for reranking
            chunk_texts = [chunk.content for chunk, _ in chunks_with_scores]
            # Truncate for reranking efficiency (rerankers have token limits)
            max_rerank_length = 500  # characters per chunk
            truncated_texts = [text[:max_rerank_length] for text in chunk_texts]
            
            with langfuse_trace("rerank", {'count': len(truncated_texts)}):
                # Rerank top candidates (rerank more than we need, then take top_n)
                rerank_count = min(30, len(chunks_with_scores))
                rerank_texts = truncated_texts[:rerank_count]
                
                rerank_results = reranker.rerank(
                    query=query,
                    docs=rerank_texts,
                    top_n=min(top_n, rerank_count)
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
    result['debug']['latency_ms'] = int((time.time() - start_time) * 1000)
    
    return result
