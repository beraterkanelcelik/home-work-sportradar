"""
Base class for vector stores.
"""
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
from app.db.models.chunk import DocumentChunk


class VectorStoreBase(ABC):
    """Base interface for vector stores."""
    
    @abstractmethod
    def upsert_embeddings(
        self,
        chunks: List[DocumentChunk],
        embeddings: List[List[float]],
        embedding_model: str
    ) -> None:
        """
        Upsert embeddings for chunks.
        
        Args:
            chunks: List of DocumentChunk objects
            embeddings: List of embedding vectors (one per chunk)
            embedding_model: Name of embedding model used
        """
        pass
    
    @abstractmethod
    def query(
        self,
        query_vector: List[float],
        top_k: int,
        owner_id: int,
        document_ids: Optional[List[int]] = None
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Query for similar chunks.
        
        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            owner_id: Filter by owner (multi-tenant)
            document_ids: Optional list of document IDs to filter by
            
        Returns:
            List of (chunk, similarity_score) tuples, ordered by similarity
        """
        pass
    
    @abstractmethod
    def delete_by_document(self, document_id: int) -> None:
        """
        Delete all embeddings for a document.
        
        Args:
            document_id: Document ID to delete embeddings for
        """
        pass
