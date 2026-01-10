"""
Mock embedding client for testing.
"""
import random
from typing import List
from django.conf import settings
from .client_base import EmbeddingsClientBase


class MockEmbeddingsClient(EmbeddingsClientBase):
    """Mock embedding client that returns random vectors for testing."""
    
    def __init__(self, model_name: str = "mock-embedding", dimensions: int = None):
        """
        Initialize mock embedding client.
        
        Args:
            model_name: Mock model name
            dimensions: Vector dimensions (defaults to RAG_EMBEDDING_DIMENSIONS)
        """
        self._model_name = model_name
        self._dimensions = dimensions or getattr(settings, 'RAG_EMBEDDING_DIMENSIONS', 1536)
        self._max_batch_size = 1000
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    @property
    def dimensions(self) -> int:
        return self._dimensions
    
    @property
    def max_batch_size(self) -> int:
        return self._max_batch_size
    
    def embed_texts(self, texts: List[str], user_id: int = None) -> List[List[float]]:
        """
        Generate random embeddings for texts.
        
        Args:
            texts: List of texts to embed
            user_id: Optional user ID (ignored for mock client)
        """
        embeddings = []
        for text in texts:
            # Generate deterministic-ish embedding based on text hash
            random.seed(hash(text) % (2**32))
            embedding = [random.gauss(0, 1) for _ in range(self._dimensions)]
            # Normalize
            norm = sum(x**2 for x in embedding) ** 0.5
            embedding = [x / norm for x in embedding]
            embeddings.append(embedding)
        return embeddings
    
    def embed_query(self, text: str, user_id: int = None) -> List[float]:
        """
        Generate random embedding for query.
        
        Args:
            text: Query text to embed
            user_id: Optional user ID (ignored for mock client)
        """
        random.seed(hash(text) % (2**32))
        embedding = [random.gauss(0, 1) for _ in range(self._dimensions)]
        norm = sum(x**2 for x in embedding) ** 0.5
        return [x / norm for x in embedding]
