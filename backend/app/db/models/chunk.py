"""
Document chunk model with vector embeddings.
"""
from django.db import models
# from django.contrib.postgres.fields import VectorField
# from .document import Document

# TODO: Create Chunk model with pgvector
# class Chunk(models.Model):
#     document = models.ForeignKey(Document, on_delete=models.CASCADE)
#     content = models.TextField()
#     chunk_index = models.IntegerField()
#     # Vector embedding (pgvector)
#     embedding = VectorField(dimensions=1536)  # OpenAI ada-002 dimensions
#     created_at = models.DateTimeField(auto_now_add=True)
#     
#     class Meta:
#         db_table = 'chunks'
#         indexes = [
#             models.Index(fields=['document', 'chunk_index']),
#         ]
