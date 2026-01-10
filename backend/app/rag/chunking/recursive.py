"""
Recursive character text splitter implementation.
Similar to LangChain's RecursiveCharacterTextSplitter.
Enhanced with accurate token counting.
"""
from typing import List, Dict, Any, Optional
from .base import ChunkingStrategyBase, ChunkingConfig, Chunk
from .tokenizer import count_tokens


class RecursiveCharacterTextSplitter(ChunkingStrategyBase):
    """
    Recursively splits text by trying different separators.
    Falls back to character-level splitting if no separators work.
    """
    
    def split(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[Chunk]:
        """
        Split text into chunks using recursive strategy.
        
        Args:
            text: Text to split
            metadata: Optional metadata to attach to chunks
            
        Returns:
            List of Chunk objects
        """
        if not text:
            return []
        
        chunks = []
        current_offset = 0
        
        # Split recursively
        splits = self._split_text(text, current_offset, metadata or {})
        
        for idx, (content, start, end, chunk_meta) in enumerate(splits):
            chunk = Chunk(
                content=content,
                chunk_index=idx,
                start_offset=start,
                end_offset=end,
                metadata={**(metadata or {}), **chunk_meta}
            )
            chunks.append(chunk)
        
        return chunks
    
    def _split_text(self, text: str, start_offset: int, base_metadata: Dict[str, Any]) -> List[tuple]:
        """
        Recursively split text.
        
        Returns:
            List of tuples: (content, start_offset, end_offset, metadata)
        """
        if len(text) <= self.config.chunk_size_chars:
            # Text fits in one chunk
            return [(text, start_offset, start_offset + len(text), base_metadata)]
        
        chunks = []
        current_start = start_offset
        remaining_text = text
        
        while len(remaining_text) > self.config.chunk_size_chars:
            # Try to find a good split point using separators
            chunk_text, remaining_text = self._split_at_separator(
                remaining_text,
                self.config.chunk_size_chars,
                self.config.overlap_chars
            )
            
            if chunk_text:
                chunk_end = current_start + len(chunk_text)
                chunks.append((chunk_text, current_start, chunk_end, base_metadata.copy()))
                current_start = chunk_end - self.config.overlap_chars
                
                # Add overlap from previous chunk
                if chunks and self.config.overlap_chars > 0:
                    overlap_start = max(0, len(chunk_text) - self.config.overlap_chars)
                    remaining_text = chunk_text[overlap_start:] + remaining_text
            else:
                # Fallback: split at character level
                chunk_text = remaining_text[:self.config.chunk_size_chars]
                chunk_end = current_start + len(chunk_text)
                chunks.append((chunk_text, current_start, chunk_end, base_metadata.copy()))
                remaining_text = remaining_text[self.config.chunk_size_chars - self.config.overlap_chars:]
                current_start = chunk_end - self.config.overlap_chars
        
        # Add remaining text as final chunk
        if remaining_text and len(remaining_text) >= self.config.min_chunk_size:
            chunks.append((remaining_text, current_start, current_start + len(remaining_text), base_metadata.copy()))
        
        return chunks
    
    def _split_at_separator(self, text: str, chunk_size: int, overlap: int) -> tuple:
        """
        Try to split text at a good separator.
        
        Returns:
            Tuple of (chunk_text, remaining_text)
        """
        # Try each separator in order
        for separator in self.config.separators:
            if separator == '':
                # Last resort: split at character level
                if len(text) > chunk_size:
                    return text[:chunk_size], text[chunk_size - overlap:]
                return None, text
            
            # Find last occurrence of separator before chunk_size
            if separator in text:
                # Find all occurrences
                parts = text.split(separator)
                current_chunk = []
                current_length = 0
                
                for part in parts:
                    part_with_sep = part + separator if current_chunk else part
                    if current_length + len(part_with_sep) <= chunk_size:
                        current_chunk.append(part)
                        current_length += len(part_with_sep)
                    else:
                        # Found split point
                        if current_chunk:
                            chunk_text = separator.join(current_chunk)
                            remaining = separator.join([part] + parts[parts.index(part) + 1:])
                            
                            # Add overlap
                            if overlap > 0 and len(chunk_text) > overlap:
                                overlap_text = chunk_text[-overlap:]
                                remaining = overlap_text + remaining
                            
                            return chunk_text, remaining
                        else:
                            # Part is too large, split it
                            return part[:chunk_size], part[chunk_size - overlap:] + separator + separator.join(parts[parts.index(part) + 1:])
                
                # All parts fit in one chunk
                return None, text
        
        # No separator found, split at character level
        if len(text) > chunk_size:
            return text[:chunk_size], text[chunk_size - overlap:]
        return None, text
