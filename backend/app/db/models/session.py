"""
Chat session model.
"""
from django.db import models
from django.conf import settings


class ChatSession(models.Model):
    """Chat session model for storing conversation sessions."""
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_sessions'
    )
    title = models.CharField(max_length=255, blank=True, null=True)
    tokens_used = models.IntegerField(default=0)
    model_used = models.CharField(max_length=100, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'chat_sessions'
        ordering = ['-updated_at']
        verbose_name = 'Chat Session'
        verbose_name_plural = 'Chat Sessions'
    
    def __str__(self):
        return f"{self.user.email} - {self.title or 'Untitled'} ({self.created_at})"
