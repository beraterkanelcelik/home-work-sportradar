"""
Text extraction from various file formats.
Enhanced with multiple PDF extraction backends and OCR support.
"""
import io
from typing import Tuple, Dict, Any, Optional, List
from pathlib import Path
from django.conf import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


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
            - metadata: Additional metadata (language, extraction_method, etc.)
        """
        raise NotImplementedError


class PDFPlumberExtractor(TextExtractor):
    """Extract text from PDF files using pdfplumber (best quality, layout-aware)."""
    
    @staticmethod
    def extract(file_path: Path, mime_type: str) -> Tuple[str, Dict[int, Dict[str, int]], Dict[str, Any]]:
        """
        Extract text from PDF file using pdfplumber.
        
        Returns:
            (text, page_map, metadata)
        """
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("pdfplumber is required. Install with: pip install pdfplumber")
        
        text_parts = []
        page_map = {}
        current_char = 0
        tables = []
        
        with pdfplumber.open(file_path) as pdf:
            num_pages = len(pdf.pages)
            
            for page_num, page in enumerate(pdf.pages, start=1):
                # Extract text
                page_text = page.extract_text()
                
                # Extract tables if any
                page_tables = page.extract_tables()
                if page_tables:
                    for table in page_tables:
                        # Convert table to text representation
                        table_text = '\n'.join([' | '.join([str(cell) if cell else '' for cell in row]) for row in table])
                        tables.append({
                            'page': page_num,
                            'text': table_text
                        })
                
                if page_text:
                    start_char = current_char
                    text_parts.append(page_text)
                    current_char += len(page_text)
                    end_char = current_char
                    
                    page_map[page_num] = {
                        'start_char': start_char,
                        'end_char': end_char
                    }
                    
                    # Add newline between pages
                    if page_num < num_pages:
                        text_parts.append('\n\n')
                        current_char += 2
        
        full_text = ''.join(text_parts)
        
        # Append tables at the end if any
        if tables:
            full_text += '\n\n--- Tables ---\n\n'
            for table in tables:
                full_text += f"Page {table['page']}:\n{table['text']}\n\n"
        
        metadata = {
            'num_pages': num_pages,
            'language': 'en',
            'extraction_method': 'pdfplumber',
            'tables_found': len(tables)
        }
        
        return full_text, page_map, metadata


class PyMuPDFExtractor(TextExtractor):
    """Extract text from PDF files using PyMuPDF (fitz) - fast and robust."""
    
    @staticmethod
    def extract(file_path: Path, mime_type: str) -> Tuple[str, Dict[int, Dict[str, int]], Dict[str, Any]]:
        """
        Extract text from PDF file using PyMuPDF.
        
        Returns:
            (text, page_map, metadata)
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("PyMuPDF is required. Install with: pip install PyMuPDF")
        
        text_parts = []
        page_map = {}
        current_char = 0
        
        doc = fitz.open(file_path)
        num_pages = len(doc)
        
        try:
            for page_num in range(num_pages):
                page = doc[page_num]
                page_text = page.get_text()
                
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
        finally:
            doc.close()
        
        full_text = ''.join(text_parts)
        metadata = {
            'num_pages': num_pages,
            'language': 'en',
            'extraction_method': 'pymupdf'
        }
        
        return full_text, page_map, metadata


class PyPDFExtractor(TextExtractor):
    """Extract text from PDF files using pypdf (basic fallback)."""
    
    @staticmethod
    def extract(file_path: Path, mime_type: str) -> Tuple[str, Dict[int, Dict[str, int]], Dict[str, Any]]:
        """
        Extract text from PDF file using pypdf.
        
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
            'language': 'en',
            'extraction_method': 'pypdf'
        }
        
        return full_text, page_map, metadata


class OCRPDFExtractor(TextExtractor):
    """Extract text from scanned PDFs using OCR (Tesseract)."""
    
    @staticmethod
    def extract(file_path: Path, mime_type: str) -> Tuple[str, Dict[int, Dict[str, int]], Dict[str, Any]]:
        """
        Extract text from scanned PDF using OCR.
        
        Returns:
            (text, page_map, metadata)
        """
        try:
            from pdf2image import convert_from_path
            import pytesseract
        except ImportError:
            raise ImportError("OCR dependencies required. Install with: pip install pdf2image pytesseract Pillow")
        
        try:
            # Convert PDF pages to images
            images = convert_from_path(file_path)
            num_pages = len(images)
        except Exception as e:
            raise RuntimeError(f"Failed to convert PDF to images: {e}. Make sure poppler is installed.")
        
        text_parts = []
        page_map = {}
        current_char = 0
        
        for page_num, image in enumerate(images, start=1):
            # Perform OCR on image
            page_text = pytesseract.image_to_string(image)
            
            if page_text:
                start_char = current_char
                text_parts.append(page_text)
                current_char += len(page_text)
                end_char = current_char
                
                page_map[page_num] = {
                    'start_char': start_char,
                    'end_char': end_char
                }
                
                # Add newline between pages
                if page_num < num_pages:
                    text_parts.append('\n\n')
                    current_char += 2
        
        full_text = ''.join(text_parts)
        metadata = {
            'num_pages': num_pages,
            'language': 'en',
            'extraction_method': 'ocr'
        }
        
        return full_text, page_map, metadata


class SmartPDFExtractor(TextExtractor):
    """
    PDF extractor that uses a single configured backend.
    """
    
    @staticmethod
    def extract(file_path: Path, mime_type: str) -> Tuple[str, Dict[int, Dict[str, int]], Dict[str, Any]]:
        """
        Extract text from PDF using the configured backend only.
        """
        preferred = getattr(settings, 'PDF_EXTRACTOR_PREFERENCE', 'pypdf')
        extractor_map = {
            'pdfplumber': PDFPlumberExtractor,
            'pymupdf': PyMuPDFExtractor,
            'pypdf': PyPDFExtractor,
            'ocr': OCRPDFExtractor,
        }

        extractor_name = preferred if preferred in extractor_map else 'pypdf'
        if extractor_name != preferred:
            logger.warning(
                "Unknown PDF_EXTRACTOR_PREFERENCE '%s', using '%s'",
                preferred,
                extractor_name,
            )

        extractor_class = extractor_map[extractor_name]

        try:
            logger.debug(f"Extracting PDF with {extractor_name}")
            text, page_map, metadata = extractor_class.extract(file_path, mime_type)
            logger.info(f"Successfully extracted text using {extractor_name}")
            return text, page_map, metadata
        except Exception as exc:
            logger.warning(f"{extractor_name} extraction failed: {exc}")
            raise RuntimeError(
                f"PDF extraction failed using {extractor_name}. Error: {exc}"
            ) from exc


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
            'language': 'en',
            'extraction_method': 'plain_text'
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
        return SmartPDFExtractor()
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
