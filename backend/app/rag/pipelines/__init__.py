"""
RAG pipelines for indexing and querying.
"""
from .index_pipeline import index_document
from .query_pipeline import query_rag

__all__ = ['index_document', 'query_rag']
