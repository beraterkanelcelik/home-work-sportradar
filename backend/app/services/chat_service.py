"""
Chat service for managing chat sessions and messages.
"""
from django.contrib.auth import get_user_model
from app.db.models.session import ChatSession
from app.db.models.message import Message

User = get_user_model()


def create_session(user_id, title=None):
    """
    Create a new chat session.
    Returns: ChatSession object
    """
    user = User.objects.get(id=user_id)
    session = ChatSession.objects.create(
        user=user,
        title=title or 'New Chat'
    )
    return session


def get_user_sessions(user_id):
    """
    Get all chat sessions for a user.
    Returns: QuerySet of ChatSession objects
    """
    return ChatSession.objects.filter(user_id=user_id).order_by('-updated_at')


def get_session(user_id, session_id):
    """
    Get a specific chat session with messages.
    Returns: ChatSession object or None if not found or not owned by user
    """
    try:
        session = ChatSession.objects.get(id=session_id, user_id=user_id)
        return session
    except ChatSession.DoesNotExist:
        return None


def delete_session(user_id, session_id):
    """
    Delete a chat session.
    Returns: True if deleted, False if not found or not owned by user
    """
    try:
        session = ChatSession.objects.get(id=session_id, user_id=user_id)
        session.delete()
        return True
    except ChatSession.DoesNotExist:
        return False


def add_message(session_id, role, content, tokens_used=0, metadata=None):
    """
    Add a message to a chat session.
    Returns: Message object
    """
    session = ChatSession.objects.get(id=session_id)
    message = Message.objects.create(
        session=session,
        role=role,
        content=content,
        tokens_used=tokens_used,
        metadata=metadata or {}
    )
    
    # Update session's updated_at timestamp
    session.save(update_fields=['updated_at'])
    
    return message


def get_messages(session_id):
    """
    Get all messages in a chat session.
    Returns: QuerySet of Message objects
    """
    return Message.objects.filter(session_id=session_id).order_by('created_at')
