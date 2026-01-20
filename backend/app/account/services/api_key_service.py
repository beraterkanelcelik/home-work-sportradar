"""
API key management service.

Handles storage and retrieval of user API keys with encryption.
"""

from typing import Dict, Any, Optional

from app.account.models import User
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_user_api_keys_status(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Get API key status for a user (set/not set, NOT actual values).

    Args:
        user_id: User ID

    Returns:
        Dictionary with key status information
    """
    try:
        user = User.objects.get(id=user_id)
        return {
            "openai_api_key": {
                "is_set": user.has_custom_openai_key(),
                "source": "user" if user.has_custom_openai_key() else "unset",
            },
            "langfuse_public_key": {
                "is_set": bool(user._langfuse_public_key),
                "source": "user" if user._langfuse_public_key else "unset",
            },
            "langfuse_secret_key": {
                "is_set": bool(user._langfuse_secret_key),
                "source": "user" if user._langfuse_secret_key else "unset",
            },
            "langfuse_keys_complete": user.has_custom_langfuse_keys(),
        }
    except User.DoesNotExist:
        logger.warning(f"User {user_id} not found when getting API key status")
        return None


def update_user_api_keys(
    user_id: int,
    openai_api_key: Optional[str] = None,
    langfuse_public_key: Optional[str] = None,
    langfuse_secret_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update user API keys (encrypts and stores).

    Args:
        user_id: User ID
        openai_api_key: Optional OpenAI API key (None = don't change, '' = clear)
        langfuse_public_key: Optional Langfuse public key
        langfuse_secret_key: Optional Langfuse secret key

    Returns:
        Updated key status
    """
    try:
        user = User.objects.get(id=user_id)
        fields_to_update = []

        # Update OpenAI key
        if openai_api_key is not None:
            user.openai_api_key = openai_api_key
            fields_to_update.append("_openai_api_key")
            logger.info(f"Updated OpenAI API key for user {user_id}")

        # Update Langfuse keys
        if langfuse_public_key is not None:
            user.langfuse_public_key = langfuse_public_key
            fields_to_update.append("_langfuse_public_key")
            logger.info(f"Updated Langfuse public key for user {user_id}")

        if langfuse_secret_key is not None:
            user.langfuse_secret_key = langfuse_secret_key
            fields_to_update.append("_langfuse_secret_key")
            logger.info(f"Updated Langfuse secret key for user {user_id}")

        if fields_to_update:
            user.save(update_fields=fields_to_update)

        return get_user_api_keys_status(user_id)

    except User.DoesNotExist:
        logger.warning(f"User {user_id} not found when updating API keys")
        return None


def clear_user_api_keys(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Clear all API keys for a user.

    Args:
        user_id: User ID

    Returns:
        Updated key status
    """
    try:
        user = User.objects.get(id=user_id)
        user.clear_api_keys()
        logger.info(f"Cleared all API keys for user {user_id}")
        return get_user_api_keys_status(user_id)

    except User.DoesNotExist:
        logger.warning(f"User {user_id} not found when clearing API keys")
        return None


def get_effective_openai_key(user_id: int) -> str:
    """
    Get the effective OpenAI API key for a user.

    Returns user's custom key if set; otherwise returns empty string.
    """
    try:
        user = User.objects.get(id=user_id)
        if user.has_custom_openai_key():
            return user.openai_api_key
    except User.DoesNotExist:
        pass

    return ""


def get_effective_langfuse_keys(user_id: int) -> Dict[str, str]:
    """
    Get the effective Langfuse keys for a user.

    Returns user's custom keys if both are set; otherwise returns empty strings.
    """
    try:
        user = User.objects.get(id=user_id)
        if user.has_custom_langfuse_keys():
            return {
                "public_key": user.langfuse_public_key,
                "secret_key": user.langfuse_secret_key,
            }
    except User.DoesNotExist:
        pass

    return {
        "public_key": "",
        "secret_key": "",
    }
