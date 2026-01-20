"""
Index pipeline: orchestrates document extraction, chunking, embedding, and vector storage.
"""

import time
from typing import Optional
from django.conf import settings
from app.db.models.document import Document, DocumentText
from app.db.models.chunk import DocumentChunk
from app.documents.services.extractor import extract_text
from app.documents.services.storage import storage_service
from app.rag.chunking import (
    RecursiveCharacterTextSplitter,
    SemanticTextSplitter,
    ChunkingConfig,
    count_tokens,
)
from app.rag.embeddings import OpenAIEmbeddingsClient

from app.rag.vectorstore import PgVectorStore
from app.observability.tracing import get_langfuse_client


def index_document(
    document_id: int, user_id: int, api_key: Optional[str] = None
) -> None:
    """
    Full indexing pipeline for a document.

    Steps:
    1. Extract text from file
    2. Chunk text
    3. Embed chunks
    4. Upsert vectors
    5. Update document status

    Args:
        document_id: Document ID to index
        user_id: Owner user ID (for verification)
    """
    document = Document.objects.get(id=document_id, owner_id=user_id)

    # Initialize components
    langfuse = get_langfuse_client()
    vector_store = PgVectorStore()

    # Context manager for langfuse (handles None case)
    # For Langfuse v3, we'll use a simple no-op context manager if client is None
    # Otherwise, use the start_as_current_span context manager directly
    def langfuse_trace(name, metadata=None):
        if langfuse:
            try:
                # start_as_current_span returns a context manager
                # We'll use it directly and not try to update metadata for now
                return langfuse.start_as_current_span(name=name)
            except (AttributeError, TypeError):
                # If the method doesn't exist or fails, return a no-op context manager
                pass

        # No-op context manager when langfuse is not available
        class NoOpContext:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        return NoOpContext()

    # Determine embedding client
    if not api_key:
        raise ValueError("OpenAI API key is required for indexing")

    embeddings_client = OpenAIEmbeddingsClient(api_key=api_key)

    try:
        # Update status to EXTRACTING
        document.status = Document.Status.EXTRACTED
        document.save(update_fields=["status"])

        # Step 1: Extract text
        with langfuse_trace("extract_text", {"document_id": document_id}):
            file_path = storage_service.get_file_path(document.file.name)
            text, page_map, metadata = extract_text(file_path, document.mime_type)

            # Store extracted text
            DocumentText.objects.update_or_create(
                document=document,
                defaults={
                    "text": text,
                    "page_map": page_map,
                    "language": metadata.get("language", "en"),
                },
            )

        document.status = Document.Status.EXTRACTED
        document.save(update_fields=["status"])

        # Step 2: Chunk text
        with langfuse_trace("chunk_text", {"document_id": document_id}):
            chunking_config = ChunkingConfig()

            # Select chunking strategy based on settings
            chunking_strategy = getattr(settings, "RAG_CHUNKING_STRATEGY", "recursive")
            if chunking_strategy == "semantic":
                splitter = SemanticTextSplitter(config=chunking_config)
            else:
                splitter = RecursiveCharacterTextSplitter(config=chunking_config)

            # Get page info for metadata
            extracted_text = DocumentText.objects.get(document=document)
            chunks = splitter.split(
                text,
                metadata={
                    "document_id": document_id,
                    "extraction_method": metadata.get("extraction_method", "unknown"),
                },
            )

            # Add page numbers to chunk metadata
            for chunk in chunks:
                if chunk.start_offset is not None:
                    # Find which page this chunk belongs to
                    for page_num, page_info in page_map.items():
                        if (
                            page_info["start_char"]
                            <= chunk.start_offset
                            < page_info["end_char"]
                        ):
                            chunk.metadata["page"] = page_num
                            break

        # Step 3: Create DocumentChunk records
        document.status = Document.Status.INDEXING
        document.save(update_fields=["status"])

        # Delete existing chunks (for re-indexing)
        DocumentChunk.objects.filter(document=document).delete()

        chunk_objects = []
        for chunk in chunks:
            chunk_obj = DocumentChunk.objects.create(
                document=document,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                metadata=chunk.metadata,
            )
            chunk_objects.append(chunk_obj)

        # Step 4: Embed chunks
        with langfuse_trace(
            "embed_chunks",
            {"document_id": document_id, "chunk_count": len(chunk_objects)},
        ):
            chunk_texts = [chunk.content for chunk in chunk_objects]
            # Pass user_id for token usage tracking
            embeddings = embeddings_client.embed_texts(chunk_texts, user_id=user_id)

        # Step 5: Upsert vectors
        with langfuse_trace("upsert_vectors", {"document_id": document_id}):
            vector_store.upsert_embeddings(
                chunks=chunk_objects,
                embeddings=embeddings,
                embedding_model=embeddings_client.model_name,
            )

        # Step 6: Update document status and counters
        document.status = Document.Status.READY
        document.chunks_count = len(chunk_objects)
        # Accurate token count using tiktoken if available
        document.tokens_estimate = count_tokens(text, chunking_config.tokenizer_model)
        document.error_message = None
        document.save(
            update_fields=["status", "chunks_count", "tokens_estimate", "error_message"]
        )

    except Exception as e:
        # Mark as failed
        document.status = Document.Status.FAILED
        document.error_message = str(e)
        document.save(update_fields=["status", "error_message"])
        raise
