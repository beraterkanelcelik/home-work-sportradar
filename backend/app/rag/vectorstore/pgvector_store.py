"""
PostgreSQL vector store using pgvector.
"""
from typing import List, Tuple, Optional
from django.db.models import Q
from pgvector.django import L2Distance
from app.db.models.chunk import DocumentChunk, ChunkEmbedding
from app.db.models.document import Document
from .base import VectorStoreBase


class PgVectorStore(VectorStoreBase):
    """PostgreSQL vector store implementation using pgvector."""
    
    def upsert_embeddings(
        self,
        chunks: List[DocumentChunk],
        embeddings: List[List[float]],
        embedding_model: str
    ) -> None:
        """
        Upsert embeddings for chunks.
        """
        if len(chunks) != len(embeddings):
            raise ValueError("Number of chunks must match number of embeddings")
        
        for chunk, embedding in zip(chunks, embeddings):
            # Create or update embedding
            chunk_embedding, created = ChunkEmbedding.objects.update_or_create(
                chunk=chunk,
                defaults={
                    'embedding': embedding,
                    'embedding_model': embedding_model
                }
            )
    
    def query(
        self,
        query_vector: List[float],
        top_k: int,
        owner_id: int,
        document_ids: Optional[List[int]] = None
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Query for similar chunks using vector similarity.
        """
        # Build base query: only READY documents owned by user
        base_query = Q(
            chunk__document__owner_id=owner_id,
            chunk__document__status=Document.Status.READY
        )
        
        # Add document filter if provided
        if document_ids:
            base_query &= Q(chunk__document_id__in=document_ids)
        
        # Query embeddings ordered by L2 distance (lower is more similar)
        # Note: pgvector uses L2Distance for cosine similarity when vectors are normalized
        embeddings = ChunkEmbedding.objects.filter(base_query).annotate(
            distance=L2Distance('embedding', query_vector)
        ).order_by('distance')[:top_k]
        
        # Convert to (chunk, score) tuples
        # Score is 1 / (1 + distance) for similarity (0-1 range)
        results = []
        for emb in embeddings:
            distance = float(emb.distance) if hasattr(emb, 'distance') else 1.0
            # Convert distance to similarity score (inverse, normalized)
            # For normalized vectors, L2 distance ranges from 0 to 2
            # Similarity = 1 - (distance / 2)
            similarity = max(0.0, 1.0 - (distance / 2.0))
            results.append((emb.chunk, similarity))
        
        return results
    
    def delete_by_document(self, document_id: int) -> None:
        """
        Delete all embeddings for a document.
        """
        ChunkEmbedding.objects.filter(chunk__document_id=document_id).delete()
