"""
Semantic chunking strategy that preserves sentence and paragraph boundaries.
Uses spaCy for sentence boundary detection when available.
"""
from typing import List, Dict, Any, Optional
import re
from .base import ChunkingStrategyBase, ChunkingConfig, Chunk
from .tokenizer import count_tokens
from app.core.logging import get_logger

logger = get_logger(__name__)

# Cache for spaCy model
_spacy_model = None


def get_spacy_model():
    """Get or load spaCy model for sentence segmentation."""
    global _spacy_model
    
    if _spacy_model is not None:
        return _spacy_model
    
    try:
        import spacy
        # Try to load English model
        try:
            _spacy_model = spacy.load("en_core_web_sm")
            logger.info("Loaded spaCy model for semantic chunking")
        except OSError:
            logger.warning("spaCy English model not found. Install with: python -m spacy download en_core_web_sm")
            logger.warning("Falling back to regex-based sentence detection")
            _spacy_model = False  # Mark as unavailable
        return _spacy_model
    except ImportError:
        logger.warning("spaCy not available, using regex-based sentence detection")
        _spacy_model = False
        return _spacy_model


def split_into_sentences(text: str) -> List[str]:
    """
    Split text into sentences using spaCy if available, otherwise regex.
    
    Args:
        text: Text to split
        
    Returns:
        List of sentences
    """
    spacy_model = get_spacy_model()
    
    if spacy_model and spacy_model is not False:
        # Use spaCy for accurate sentence segmentation
        doc = spacy_model(text)
        sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
        return sentences
    else:
        # Fallback: regex-based sentence splitting
        # Match sentence endings followed by whitespace or end of string
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])\s*$'
        sentences = re.split(sentence_pattern, text)
        # Filter out empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences


def split_into_paragraphs(text: str) -> List[str]:
    """
    Split text into paragraphs.
    
    Args:
        text: Text to split
        
    Returns:
        List of paragraphs
    """
    # Split on double newlines (paragraph breaks)
    paragraphs = re.split(r'\n\s*\n', text)
    # Filter out empty paragraphs
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    return paragraphs


class SemanticTextSplitter(ChunkingStrategyBase):
    """
    Semantic text splitter that preserves sentence and paragraph boundaries.
    Avoids splitting mid-sentence.
    """
    
    def split(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[Chunk]:
        """
        Split text into chunks using semantic boundaries.
        
        Args:
            text: Text to split
            metadata: Optional metadata to attach to chunks
            
        Returns:
            List of Chunk objects
        """
        if not text:
            return []
        
        chunks = []
        
        # Split into paragraphs first
        paragraphs = split_into_paragraphs(text)
        
        current_chunk_parts = []
        current_chunk_size = 0
        chunk_start_offset = 0
        
        # Track position in original text
        text_position = 0
        
        for para_idx, paragraph in enumerate(paragraphs):
            # Find paragraph offset in original text
            para_offset = text.find(paragraph, text_position)
            if para_offset == -1:
                para_offset = text_position
            text_position = para_offset + len(paragraph)
            
            # Split paragraph into sentences
            sentences = split_into_sentences(paragraph)
            
            for sent_idx, sentence in enumerate(sentences):
                # Count tokens in sentence
                sent_tokens = count_tokens(sentence, self.config.tokenizer_model) if self.config.use_tiktoken else len(sentence) // 4
                
                # Find sentence position in paragraph
                sent_in_para_offset = paragraph.find(sentence)
                if sent_in_para_offset == -1:
                    sent_in_para_offset = 0
                
                # Check if adding this sentence would exceed chunk size
                if current_chunk_parts and (current_chunk_size + sent_tokens) > self.config.chunk_size:
                    # Current chunk is full, save it
                    chunk_text = ' '.join(current_chunk_parts)
                    chunk_end_offset = chunk_start_offset + len(chunk_text)
                    
                    chunks.append(Chunk(
                        content=chunk_text,
                        chunk_index=len(chunks),
                        start_offset=chunk_start_offset,
                        end_offset=chunk_end_offset,
                        metadata={**(metadata or {}), 'chunk_type': 'semantic'}
                    ))
                    
                    # Start new chunk with overlap
                    if self.config.overlap > 0 and len(current_chunk_parts) > 0:
                        # Add last few sentences as overlap
                        overlap_sentences = []
                        overlap_tokens = 0
                        for part in reversed(current_chunk_parts):
                            part_tokens = count_tokens(part, self.config.tokenizer_model) if self.config.use_tiktoken else len(part) // 4
                            if overlap_tokens + part_tokens <= self.config.overlap:
                                overlap_sentences.insert(0, part)
                                overlap_tokens += part_tokens
                            else:
                                break
                        current_chunk_parts = overlap_sentences
                        current_chunk_size = overlap_tokens
                        # Find start offset of overlap in original text
                        if overlap_sentences:
                            overlap_text = ' '.join(overlap_sentences)
                            # Search backwards from current position
                            search_start = max(0, chunk_start_offset - len(overlap_text) * 2)
                            overlap_pos = text.find(overlap_text, search_start, chunk_end_offset)
                            if overlap_pos != -1:
                                chunk_start_offset = overlap_pos
                            else:
                                # Fallback: use end of previous chunk minus overlap
                                chunk_start_offset = chunk_end_offset - len(overlap_text)
                    else:
                        current_chunk_parts = []
                        current_chunk_size = 0
                        chunk_start_offset = para_offset + sent_in_para_offset
                
                # Add sentence to current chunk
                if not current_chunk_parts:
                    # First sentence in chunk, set start offset
                    chunk_start_offset = para_offset + sent_in_para_offset
                
                current_chunk_parts.append(sentence)
                current_chunk_size += sent_tokens
            
            # Add paragraph separator if not last paragraph
            if para_idx < len(paragraphs) - 1:
                current_chunk_parts.append('\n\n')
                current_chunk_size += count_tokens('\n\n', self.config.tokenizer_model) if self.config.use_tiktoken else 1
        
        # Add final chunk if there's remaining content
        if current_chunk_parts:
            chunk_text = ' '.join(current_chunk_parts)
            # Find actual position in text
            if chunk_start_offset < len(text):
                # Verify the chunk text matches at this position
                actual_text = text[chunk_start_offset:chunk_start_offset + len(chunk_text)]
                if actual_text.strip() != chunk_text.strip():
                    # Try to find the actual position
                    found_pos = text.find(chunk_text[:min(50, len(chunk_text))], chunk_start_offset)
                    if found_pos != -1:
                        chunk_start_offset = found_pos
            chunk_end_offset = chunk_start_offset + len(chunk_text)
            
            # Only add if meets minimum size
            if len(chunk_text) >= self.config.min_chunk_size:
                chunks.append(Chunk(
                    content=chunk_text,
                    chunk_index=len(chunks),
                    start_offset=chunk_start_offset,
                    end_offset=chunk_end_offset,
                    metadata={**(metadata or {}), 'chunk_type': 'semantic'}
                ))
        
        return chunks
