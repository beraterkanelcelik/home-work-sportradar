"""
Base class for embedding clients.
"""
from abc import ABC, abstractmethod
from typing import List


class EmbeddingsClientBase(ABC):
    """Base interface for embedding providers."""
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the embedding model."""
        pass
    
    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Dimension of embedding vectors."""
        pass
    
    @property
    @abstractmethod
    def max_batch_size(self) -> int:
        """Maximum number of texts to embed in a single batch."""
        pass
    
    @abstractmethod
    def embed_texts(self, texts: List[str], user_id: int = None) -> List[List[float]]:
        """
        Embed multiple texts.
        
        Args:
            texts: List of text strings to embed
            user_id: Optional user ID for token usage tracking
            
        Returns:
            List of embedding vectors (each is a list of floats)
        """
        pass
    
    @abstractmethod
    def embed_query(self, text: str, user_id: int = None) -> List[float]:
        """
        Embed a single query text.
        
        Args:
            text: Query text to embed
            user_id: Optional user ID for token usage tracking
            
        Returns:
            Embedding vector as list of floats
        """
        pass
