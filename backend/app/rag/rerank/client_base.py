"""
Base class for reranker clients.
"""
from abc import ABC, abstractmethod
from typing import List, Tuple


class RerankerClientBase(ABC):
    """Base interface for reranker providers."""
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the reranker model."""
        pass
    
    @property
    @abstractmethod
    def max_docs(self) -> int:
        """Maximum number of documents that can be reranked in one call."""
        pass
    
    @abstractmethod
    def rerank(
        self,
        query: str,
        docs: List[str],
        top_n: int
    ) -> List[Tuple[int, float]]:
        """
        Rerank documents by relevance to query.
        
        Args:
            query: Search query
            docs: List of document texts to rerank
            top_n: Number of top results to return
            
        Returns:
            List of (index, score) tuples, ordered by relevance (highest first)
            Index refers to position in original docs list
        """
        pass
