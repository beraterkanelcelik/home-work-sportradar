"""
Context formatter for RAG results.
Deduplicates, merges adjacent chunks, and formats for agent consumption.
"""
import hashlib
from typing import List, Dict, Any
from django.conf import settings
from app.db.models.chunk import DocumentChunk
from app.db.models.document import Document


class ContextFormatter:
    """Formats RAG chunks into agent-ready context blocks."""
    
    def __init__(self, max_tokens: int = None):
        """
        Initialize context formatter.
        
        Args:
            max_tokens: Maximum tokens in context (defaults to RAG_MAX_CONTEXT_TOKENS)
        """
        self.max_tokens = max_tokens or getattr(settings, 'RAG_MAX_CONTEXT_TOKENS', 4000)
        # Rough estimate: 1 token ≈ 4 characters
        self.max_chars = self.max_tokens * 4
    
    def format_context(
        self,
        chunks_with_scores: List[tuple]
    ) -> Dict[str, Any]:
        """
        Format chunks into context blocks for agents.
        
        Args:
            chunks_with_scores: List of (chunk, score) tuples from reranking
            
        Returns:
            Dict with 'items' (formatted chunks) and 'debug' (metadata)
        """
        if not chunks_with_scores:
            return {
                'items': [],
                'debug': {
                    'retrieved': 0,
                    'reranked': 0,
                    'returned': 0,
                    'deduplicated': 0,
                    'merged': 0
                }
            }
        
        # Deduplicate near-identical chunks
        deduplicated = self._deduplicate_chunks(chunks_with_scores)
        
        # Merge adjacent chunks from same document
        merged = self._merge_adjacent_chunks(deduplicated)
        
        # Apply length cap
        final_chunks = self._apply_length_cap(merged)
        
        # Format for agent consumption
        items = []
        for chunk, score in final_chunks:
            doc = chunk.document
            item = {
                'doc_id': doc.id,
                'doc_title': doc.title,
                'chunk_id': chunk.id,
                'chunk_index': chunk.chunk_index,
                'content': chunk.content,
                'score': score,
                'metadata': {
                    **chunk.metadata,
                    'page': chunk.metadata.get('page'),
                }
            }
            items.append(item)
        
        return {
            'items': items,
            'debug': {
                'retrieved': len(chunks_with_scores),
                'reranked': len(chunks_with_scores),
                'returned': len(items),
                'deduplicated': len(chunks_with_scores) - len(deduplicated),
                'merged': len(deduplicated) - len(merged)
            }
        }
    
    def _deduplicate_chunks(
        self,
        chunks_with_scores: List[tuple]
    ) -> List[tuple]:
        """
        Remove near-identical chunks based on content hash.
        """
        seen_hashes = set()
        deduplicated = []
        
        for chunk, score in chunks_with_scores:
            # Use content_hash if available, otherwise compute
            content_hash = chunk.content_hash if hasattr(chunk, 'content_hash') else \
                hashlib.sha256(chunk.content.encode('utf-8')).hexdigest()
            
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                deduplicated.append((chunk, score))
        
        return deduplicated
    
    def _merge_adjacent_chunks(
        self,
        chunks_with_scores: List[tuple]
    ) -> List[tuple]:
        """
        Merge adjacent chunks from the same document.
        """
        if not chunks_with_scores:
            return []
        
        merged = []
        current_group = []
        current_doc_id = None
        
        # Sort by document and chunk_index
        sorted_chunks = sorted(chunks_with_scores, key=lambda x: (x[0].document_id, x[0].chunk_index))
        
        for chunk, score in sorted_chunks:
            # Check if this chunk is adjacent to the previous one
            if (current_doc_id == chunk.document_id and
                current_group and
                chunk.chunk_index == current_group[-1][0].chunk_index + 1):
                # Adjacent chunk from same document - add to group
                current_group.append((chunk, score))
            else:
                # New group - save previous group and start new one
                if current_group:
                    merged_chunk, merged_score = self._merge_chunk_group(current_group)
                    merged.append((merged_chunk, merged_score))
                
                current_group = [(chunk, score)]
                current_doc_id = chunk.document_id
        
        # Don't forget the last group
        if current_group:
            merged_chunk, merged_score = self._merge_chunk_group(current_group)
            merged.append((merged_chunk, merged_score))
        
        return merged
    
    def _merge_chunk_group(self, group: List[tuple]) -> tuple:
        """
        Merge a group of adjacent chunks into one.
        """
        if len(group) == 1:
            return group[0]
        
        # Use first chunk as base
        base_chunk, base_score = group[0]
        
        # Combine content
        contents = [chunk.content for chunk, _ in group]
        merged_content = '\n\n'.join(contents)
        
        # Create a pseudo-chunk object (or modify the first one)
        # For simplicity, we'll create a new chunk-like object
        class MergedChunk:
            def __init__(self, base_chunk, merged_content):
                self.id = base_chunk.id
                self.document_id = base_chunk.document_id
                self.document = base_chunk.document
                self.chunk_index = base_chunk.chunk_index
                self.content = merged_content
                self.content_hash = hashlib.sha256(merged_content.encode('utf-8')).hexdigest()
                self.metadata = base_chunk.metadata.copy()
        
        merged_chunk = MergedChunk(base_chunk, merged_content)
        
        # Average score
        avg_score = sum(score for _, score in group) / len(group)
        
        return merged_chunk, avg_score
    
    def _apply_length_cap(self, chunks_with_scores: List[tuple]) -> List[tuple]:
        """
        Apply maximum context length cap.
        """
        total_chars = 0
        capped = []
        
        for chunk, score in chunks_with_scores:
            chunk_chars = len(chunk.content)
            if total_chars + chunk_chars <= self.max_chars:
                capped.append((chunk, score))
                total_chars += chunk_chars
            else:
                # Try to fit partial chunk
                remaining = self.max_chars - total_chars
                if remaining > 100:  # Only if meaningful amount remains
                    # Truncate chunk
                    class TruncatedChunk:
                        def __init__(self, base_chunk, truncated_content):
                            self.id = base_chunk.id
                            self.document_id = base_chunk.document_id
                            self.document = base_chunk.document
                            self.chunk_index = base_chunk.chunk_index
                            self.content = truncated_content
                            self.content_hash = base_chunk.content_hash
                            self.metadata = base_chunk.metadata
                    
                    truncated = TruncatedChunk(chunk, chunk.content[:remaining] + '...')
                    capped.append((truncated, score))
                break
        
        return capped
