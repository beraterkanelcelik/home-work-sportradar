"""
Document chunk models with vector embeddings.
"""
import hashlib
from django.db import models
from django.conf import settings
from .document import Document

# Import pgvector VectorField
try:
    from pgvector.django import VectorField
except ImportError:
    # Fallback: will raise error if used without pgvector installed
    VectorField = None


class DocumentChunk(models.Model):
    """Represents a logical chunk of text from a document."""
    
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='chunks',
        db_index=True
    )
    chunk_index = models.IntegerField(db_index=True)
    content = models.TextField()
    content_hash = models.CharField(max_length=64, db_index=True)  # SHA-256 of content
    start_offset = models.IntegerField(null=True, blank=True)  # Character offset in original text
    end_offset = models.IntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # page numbers, headings, etc.
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'document_chunks'
        ordering = ['document', 'chunk_index']
        indexes = [
            models.Index(fields=['document', 'chunk_index']),
            models.Index(fields=['document', 'content_hash']),
        ]
        unique_together = [['document', 'chunk_index']]
    
    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.document.title}"
    
    def save(self, *args, **kwargs):
        """Calculate content_hash before saving."""
        if not self.content_hash and self.content:
            self.content_hash = hashlib.sha256(self.content.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)


class ChunkEmbedding(models.Model):
    """Stores vector embeddings for document chunks."""
    
    chunk = models.OneToOneField(
        DocumentChunk,
        on_delete=models.CASCADE,
        related_name='embedding'
    )
    embedding = VectorField(dimensions=1536, null=True) if VectorField else models.TextField(null=True)
    embedding_model = models.CharField(max_length=100, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'chunk_embeddings'
        indexes = [
            models.Index(fields=['embedding_model']),
        ]
        # HNSW index will be added via migration
        # indexes = [
        #     HnswIndex(
        #         name='chunk_embedding_hnsw_idx',
        #         fields=['embedding'],
        #         m=16,
        #         ef_construction=64,
        #         opclasses=['vector_l2_ops']
        #     )
        # ]
    
    def __str__(self):
        return f"Embedding for {self.chunk} ({self.embedding_model})"
