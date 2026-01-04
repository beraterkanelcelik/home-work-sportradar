"""
Django admin configuration.
"""
from django.contrib import admin
from app.db.models.session import ChatSession
from app.db.models.message import Message

# Note: User admin is now in app.account.admin


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    """Chat session admin."""
    list_display = ('id', 'user', 'title', 'tokens_used', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('title', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-updated_at',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Message admin."""
    list_display = ('id', 'session', 'role', 'content_preview', 'tokens_used', 'created_at')
    list_filter = ('role', 'created_at')
    search_fields = ('content', 'session__title')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'
