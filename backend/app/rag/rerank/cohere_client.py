"""
Cohere reranker client implementation.
"""
import os
from typing import List, Tuple
from django.conf import settings
import cohere
from .client_base import RerankerClientBase


class CohereRerankerClient(RerankerClientBase):
    """Cohere reranker client."""
    
    def __init__(self, model_name: str = None, api_key: str = None):
        """
        Initialize Cohere reranker client.
        
        Args:
            model_name: Model name (defaults to RAG_RERANKER_MODEL setting)
            api_key: Cohere API key (defaults to COHERE_API_KEY env var)
        """
        self._model_name = model_name or getattr(settings, 'RAG_RERANKER_MODEL', 'cohere-rerank-english-v3.0')
        self._api_key = api_key or os.getenv('COHERE_API_KEY')
        
        if not self._api_key:
            raise ValueError("COHERE_API_KEY environment variable is required")
        
        self._client = cohere.Client(self._api_key)
        self._max_docs = 1000  # Cohere limit
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    @property
    def max_docs(self) -> int:
        return self._max_docs
    
    def rerank(
        self,
        query: str,
        docs: List[str],
        top_n: int
    ) -> List[Tuple[int, float]]:
        """
        Rerank documents using Cohere API.
        """
        if not docs:
            return []
        
        # Truncate docs if needed
        docs_to_rerank = docs[:self._max_docs]
        
        # Cohere rerank API
        try:
            response = self._client.rerank(
                model=self._model_name,
                query=query,
                documents=docs_to_rerank,
                top_n=min(top_n, len(docs_to_rerank))
            )
            
            # Extract results: (index, score)
            results = []
            for result in response.results:
                # Cohere returns indices relative to the input docs list
                original_index = result.index
                score = result.relevance_score
                results.append((original_index, score))
            
            return results
        except Exception as e:
            # Fallback: return original order with neutral scores
            # In production, you might want to log this error
            return [(i, 0.5) for i in range(min(top_n, len(docs_to_rerank)))]
