"""
Chat message model.
"""

from django.db import models
from .session import ChatSession


class Message(models.Model):
    """Message model for storing chat messages."""

    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    ]

    # Sender type determines if message should be included in LLM context
    SENDER_TYPE_CHOICES = [
        (
            "llm",
            "LLM Context",
        ),  # Include in LLM calls (user questions, assistant answers)
        (
            "ui",
            "UI Only",
        ),  # Display only, exclude from LLM (status updates, plans, progress)
    ]

    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    tokens_used = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    sender_type = models.CharField(
        max_length=10,
        choices=SENDER_TYPE_CHOICES,
        default="llm",
        help_text="Determines if message is included in LLM context or UI-only",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "messages"
        ordering = ["created_at"]
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        indexes = [
            models.Index(fields=["session", "role", "-created_at"]),
            models.Index(fields=["session", "sender_type", "-created_at"]),
            # Note: JSON field indexes (e.g., metadata__run_id) require PostgreSQL
            # and may need to be created via raw SQL migration for optimal performance
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."
