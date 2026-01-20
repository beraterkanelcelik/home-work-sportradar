"""
API key context helpers for per-user keys.

Provides a thin abstraction to resolve the effective OpenAI and Langfuse keys
for a given user. When keys are not set, empty strings are returned.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from app.account.services.api_key_service import (
    get_effective_openai_key,
    get_effective_langfuse_keys,
)


@dataclass
class APIKeyContext:
    openai_api_key: Optional[str] = None
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None

    @classmethod
    def from_user(cls, user_id: Optional[int]):
        if user_id is None:
            return cls.from_env()

        openai_key = get_effective_openai_key(user_id)
        langfuse_keys = get_effective_langfuse_keys(user_id)
        return cls(
            openai_api_key=openai_key,
            langfuse_public_key=langfuse_keys.get("public_key", ""),
            langfuse_secret_key=langfuse_keys.get("secret_key", ""),
        )

    @classmethod
    def from_env(cls):
        return cls(
            openai_api_key="",
            langfuse_public_key="",
            langfuse_secret_key="",
        )

    def langfuse_tuple(self) -> Tuple[str, str]:
        return self.langfuse_public_key or "", self.langfuse_secret_key or ""
