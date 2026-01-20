"""
Embedding client implementations.
"""

from .client_base import EmbeddingsClientBase
from .openai_client import OpenAIEmbeddingsClient

__all__ = ["EmbeddingsClientBase", "OpenAIEmbeddingsClient"]
