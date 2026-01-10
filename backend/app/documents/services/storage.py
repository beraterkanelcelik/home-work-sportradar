"""
File storage abstraction for documents.
Supports local filesystem (current) and S3 (future).
"""
import os
from pathlib import Path
from typing import Optional
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile


class StorageService:
    """Abstract storage service for document files."""
    
    def __init__(self):
        self.media_root = Path(settings.MEDIA_ROOT)
        self.media_root.mkdir(parents=True, exist_ok=True)
    
    def save_file(self, user_id: int, document_id: int, filename: str, file_content: bytes) -> str:
        """
        Save file to storage.
        
        Args:
            user_id: Owner user ID
            document_id: Document ID
            filename: Original filename
            file_content: File content as bytes
            
        Returns:
            Relative path to saved file
        """
        # Create user-specific directory structure: documents/{user_id}/{document_id}/
        relative_path = f"documents/{user_id}/{document_id}/{filename}"
        full_path = self.media_root / relative_path
        
        # Create directory if it doesn't exist
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save file
        with open(full_path, 'wb') as f:
            f.write(file_content)
        
        return relative_path
    
    def get_file_path(self, relative_path: str) -> Path:
        """
        Get full file path from relative path.
        
        Args:
            relative_path: Relative path from media root
            
        Returns:
            Full Path object
        """
        return self.media_root / relative_path
        return self.media_root / relative_path
    
    def get_file_content(self, relative_path: str) -> bytes:
        """
        Read file content.
        
        Args:
            relative_path: Relative path from media root
            
        Returns:
            File content as bytes
        """
        full_path = self.get_file_path(relative_path)
        with open(full_path, 'rb') as f:
            return f.read()
    
    def delete_file(self, relative_path: str) -> bool:
        """
        Delete file from storage.
        
        Args:
            relative_path: Relative path from media root
            
        Returns:
            True if deleted, False if not found
        """
        full_path = self.get_file_path(relative_path)
        if full_path.exists():
            full_path.unlink()
            # Try to remove empty parent directories
            try:
                full_path.parent.rmdir()  # Remove document_id directory
                full_path.parent.parent.rmdir()  # Remove user_id directory
            except OSError:
                pass  # Directory not empty or doesn't exist
            return True
        return False
    
    def get_signed_url(self, relative_path: str, expires_in: int = 3600) -> str:
        """
        Get signed URL for file access (for S3 in future).
        For local storage, returns a relative URL.
        
        Args:
            relative_path: Relative path from media root
            expires_in: Expiration time in seconds (for S3)
            
        Returns:
            URL to access the file
        """
        # For local storage, return relative URL
        return f"{settings.MEDIA_URL}{relative_path}"


# Singleton instance
storage_service = StorageService()
