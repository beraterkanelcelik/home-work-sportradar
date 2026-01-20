"""
Encryption utilities for sensitive data storage.

Uses Fernet symmetric encryption with Django's SECRET_KEY as the base.
"""
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _get_fernet_key() -> bytes:
    """
    Derive a Fernet-compatible key from Django's SECRET_KEY.

    Fernet requires a 32-byte base64-encoded key.
    We use SHA-256 to derive a consistent 32-byte key from SECRET_KEY.

    Returns:
        Base64-encoded 32-byte key suitable for Fernet
    """
    secret_key = settings.SECRET_KEY.encode('utf-8')
    # Use SHA-256 to get exactly 32 bytes
    key_bytes = hashlib.sha256(secret_key).digest()
    # Fernet requires base64-encoded key
    return base64.urlsafe_b64encode(key_bytes)


def _get_fernet() -> Fernet:
    """Get Fernet instance for encryption/decryption."""
    return Fernet(_get_fernet_key())


def encrypt_value(value: str) -> str:
    """
    Encrypt a string value.

    Args:
        value: Plain text value to encrypt

    Returns:
        Encrypted value as base64 string
    """
    if not value:
        return ""

    try:
        fernet = _get_fernet()
        encrypted_bytes = fernet.encrypt(value.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise ValueError("Failed to encrypt value") from e


def decrypt_value(encrypted_value: str) -> str:
    """
    Decrypt an encrypted string value.

    Args:
        encrypted_value: Encrypted value as base64 string

    Returns:
        Decrypted plain text value
    """
    if not encrypted_value:
        return ""

    try:
        fernet = _get_fernet()
        decrypted_bytes = fernet.decrypt(encrypted_value.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except InvalidToken:
        logger.error("Decryption failed: invalid token (key may have changed)")
        raise ValueError("Failed to decrypt value: invalid token")
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise ValueError("Failed to decrypt value") from e


def is_encrypted(value: str) -> bool:
    """
    Check if a value appears to be encrypted (Fernet format).

    Fernet tokens start with 'gAAAAA' in base64.

    Args:
        value: String to check

    Returns:
        True if value appears to be Fernet-encrypted
    """
    if not value or len(value) < 10:
        return False
    return value.startswith('gAAAAA')
