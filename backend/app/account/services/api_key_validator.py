"""
API key validation helpers.

Performs lightweight validation for OpenAI and Langfuse keys to avoid storing
invalid credentials. Network calls are best-effort and return informative
errors instead of raising.
"""

from typing import Tuple
import os

from app.core.logging import get_logger

logger = get_logger(__name__)


def validate_openai_key(key: str) -> Tuple[bool, str]:
    """Validate an OpenAI API key by calling the models endpoint.

    Returns (is_valid, message).
    """
    if not key:
        return False, "OpenAI API key is required"

    # Basic format check
    if not key.startswith("sk-"):
        return False, "OpenAI API key should start with 'sk-'"

    try:
        # Import lazily to avoid import cost when not used
        from openai import OpenAI

        client = OpenAI(api_key=key)
        # Lightweight call; errors will be caught below
        client.models.list()
        return True, "OpenAI key validated successfully"
    except Exception as exc:  # Broad catch to keep UX simple
        logger.warning(f"OpenAI key validation failed: {exc}")
        return (
            False,
            "Unable to validate OpenAI key. Please verify the key and try again.",
        )


def validate_langfuse_keys(public_key: str, secret_key: str) -> Tuple[bool, str]:
    """Validate Langfuse keys using the Langfuse client auth check.

    Returns (is_valid, message).
    """
    if not public_key or not secret_key:
        return False, "Both Langfuse public and secret keys are required"

    if not public_key.startswith("pk-"):
        return False, "Langfuse public key should start with 'pk-'"
    if not secret_key.startswith("sk-"):
        return False, "Langfuse secret key should start with 'sk-'"

    base_url = os.getenv("LANGFUSE_BASE_URL", "http://langfuse:3000")

    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=base_url,
        )
        # auth_check returns bool in v3 SDK
        if hasattr(client, "auth_check"):
            ok = client.auth_check()
            if ok is True:
                return True, "Langfuse keys validated successfully"
        # Fallback: attempt a lightweight call
        if hasattr(client, "fetch_project"):
            client.fetch_project()
            return True, "Langfuse keys validated successfully"
        return False, "Unable to validate Langfuse keys"
    except Exception as exc:
        logger.warning(f"Langfuse key validation failed: {exc}")
        return False, "Unable to validate Langfuse keys. Please verify and try again."
