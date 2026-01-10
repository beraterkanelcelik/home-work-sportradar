"""
Base classes for chunking strategies.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from django.conf import settings


@dataclass
class ChunkingConfig:
    """Configuration for text chunking."""
    chunk_size: int = None  # Approximate tokens (will use chars * 0.25 as rough estimate)
    overlap: int = None  # Overlap in tokens
    separators: List[str] = None
    min_chunk_size: int = 50  # Minimum chunk size in characters
    
    def __post_init__(self):
        """Set defaults from settings if not provided."""
        if self.chunk_size is None:
            self.chunk_size = getattr(settings, 'RAG_CHUNK_SIZE', 1000)
        if self.overlap is None:
            self.overlap = getattr(settings, 'RAG_CHUNK_OVERLAP', 150)
        if self.separators is None:
            # Default separators: paragraphs, sentences, words
            self.separators = ['\n\n', '\n', '. ', ' ', '']
        
        # Convert token estimates to character estimates (rough: 1 token ≈ 4 chars)
        self.chunk_size_chars = self.chunk_size * 4
        self.overlap_chars = self.overlap * 4


@dataclass
class Chunk:
    """Represents a single chunk of text."""
    content: str
    chunk_index: int
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ChunkingStrategyBase:
    """Base class for chunking strategies."""
    
    def __init__(self, config: Optional[ChunkingConfig] = None):
        self.config = config or ChunkingConfig()
    
    def split(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[Chunk]:
        """
        Split text into chunks.
        
        Args:
            text: Text to split
            metadata: Optional metadata to attach to chunks
            
        Returns:
            List of Chunk objects
        """
        raise NotImplementedError
