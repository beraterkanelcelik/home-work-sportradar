"""
Text extraction from various file formats.
"""
import io
from typing import Tuple, Dict, Any, Optional
from pathlib import Path


class TextExtractor:
    """Base class for text extractors."""
    
    @staticmethod
    def extract(file_path: Path, mime_type: str) -> Tuple[str, Dict[int, Dict[str, int]], Dict[str, Any]]:
        """
        Extract text from file.
        
        Args:
            file_path: Path to file
            mime_type: MIME type of file
            
        Returns:
            Tuple of (text, page_map, metadata)
            - text: Full extracted text
            - page_map: Dict mapping page_num to {start_char, end_char}
            - metadata: Additional metadata (language, etc.)
        """
        raise NotImplementedError


class PDFExtractor(TextExtractor):
    """Extract text from PDF files using pypdf."""
    
    @staticmethod
    def extract(file_path: Path, mime_type: str) -> Tuple[str, Dict[int, Dict[str, int]], Dict[str, Any]]:
        """
        Extract text from PDF file.
        
        Returns:
            (text, page_map, metadata)
        """
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportError("pypdf is required for PDF extraction. Install with: pip install pypdf")
        
        text_parts = []
        page_map = {}
        current_char = 0
        
        with open(file_path, 'rb') as f:
            pdf = PdfReader(f)
            num_pages = len(pdf.pages)
            
            for page_num in range(num_pages):
                page = pdf.pages[page_num]
                page_text = page.extract_text()
                
                if page_text:
                    start_char = current_char
                    text_parts.append(page_text)
                    current_char += len(page_text)
                    end_char = current_char
                    
                    page_map[page_num + 1] = {  # 1-indexed pages
                        'start_char': start_char,
                        'end_char': end_char
                    }
                    
                    # Add newline between pages
                    if page_num < num_pages - 1:
                        text_parts.append('\n\n')
                        current_char += 2
        
        full_text = ''.join(text_parts)
        metadata = {
            'num_pages': num_pages,
            'language': 'en'  # Could detect language later
        }
        
        return full_text, page_map, metadata


class PlainTextExtractor(TextExtractor):
    """Extract text from plain text files."""
    
    @staticmethod
    def extract(file_path: Path, mime_type: str) -> Tuple[str, Dict[int, Dict[str, int]], Dict[str, Any]]:
        """
        Extract text from plain text file.
        """
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        
        # Simple page map: treat entire file as page 1
        page_map = {
            1: {
                'start_char': 0,
                'end_char': len(text)
            }
        }
        
        metadata = {
            'num_pages': 1,
            'language': 'en'
        }
        
        return text, page_map, metadata


class MarkdownExtractor(TextExtractor):
    """Extract text from Markdown files."""
    
    @staticmethod
    def extract(file_path: Path, mime_type: str) -> Tuple[str, Dict[int, Dict[str, int]], Dict[str, Any]]:
        """
        Extract text from Markdown file (treats as plain text for now).
        """
        # For now, treat markdown as plain text
        # Could strip markdown syntax later if needed
        return PlainTextExtractor.extract(file_path, mime_type)


def get_extractor(mime_type: str) -> TextExtractor:
    """
    Get appropriate extractor for MIME type.
    
    Args:
        mime_type: MIME type string
        
    Returns:
        TextExtractor instance
    """
    mime_type_lower = mime_type.lower()
    
    if 'pdf' in mime_type_lower or mime_type_lower == 'application/pdf':
        return PDFExtractor()
    elif 'markdown' in mime_type_lower or mime_type_lower == 'text/markdown':
        return MarkdownExtractor()
    elif mime_type_lower.startswith('text/'):
        return PlainTextExtractor()
    else:
        # Default to plain text for unknown types
        return PlainTextExtractor()


def extract_text(file_path: Path, mime_type: str) -> Tuple[str, Dict[int, Dict[str, int]], Dict[str, Any]]:
    """
    Convenience function to extract text from file.
    
    Args:
        file_path: Path to file
        mime_type: MIME type of file
        
    Returns:
        (text, page_map, metadata)
    """
    extractor = get_extractor(mime_type)
    return extractor.extract(file_path, mime_type)
