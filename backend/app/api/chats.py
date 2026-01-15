"""
Chat session and message endpoints.
"""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from app.core.dependencies import get_current_user
from app.core.logging import get_logger
from app.services.chat_service import (
    create_session,
    get_user_sessions,
    get_session,
    delete_session,
    delete_all_sessions,
    add_message,
    get_messages,
    get_session_stats,
    update_session_model,
    update_session_title,
)

logger = get_logger(__name__)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def chat_sessions(request):
    """List or create chat sessions."""
    user = get_current_user(request)
    if not user:
        return JsonResponse(
            {'error': 'Authentication required'},
            status=401
        )
    
    if request.method == 'GET':
        # List user's chat sessions
        sessions = get_user_sessions(user.id)
        sessions_data = [
            {
                'id': session.id,
                'title': session.title,
                'tokens_used': session.tokens_used,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
            }
            for session in sessions
        ]
        return JsonResponse({'sessions': sessions_data})
    
    elif request.method == 'POST':
        # Create new chat session
        try:
            data = json.loads(request.body) if request.body else {}
            title = data.get('title', None)
            session = create_session(user.id, title)
            return JsonResponse({
                'id': session.id,
                'title': session.title,
                'created_at': session.created_at.isoformat(),
            }, status=201)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET", "DELETE", "PATCH"])
def chat_session_detail(request, session_id):
    """Get, update, or delete specific chat session."""
    user = get_current_user(request)
    if not user:
        return JsonResponse(
            {'error': 'Authentication required'},
            status=401
        )
    
    if request.method == 'GET':
        # Get chat session details
        session = get_session(user.id, session_id)
        if not session:
            return JsonResponse(
                {'error': 'Chat session not found'},
                status=404
            )
        
        # NOTE: Don't create workflow here - workflows should only be created when there's
        # an actual message to process. Creating it here would send an empty signal and cause
        # duplicate processing when the user sends their first message.
        # Workflow will be created automatically when stream_agent is called with a message.
        
        return JsonResponse({
            'id': session.id,
            'title': session.title,
            'tokens_used': session.tokens_used,
            'model_used': session.model_used,
            'created_at': session.created_at.isoformat(),
            'updated_at': session.updated_at.isoformat(),
        })
    
    elif request.method == 'PATCH':
        # Update chat session (e.g., model or title)
        try:
            data = json.loads(request.body) if request.body else {}
            model_name = data.get('model_used')
            title = data.get('title')
            
            session = get_session(user.id, session_id)
            if not session:
                return JsonResponse(
                    {'error': 'Chat session not found'},
                    status=404
                )
            
            updated_fields = []
            if model_name is not None:
                session = update_session_model(user.id, session_id, model_name)
                updated_fields.append('model_used')
            
            if title is not None:
                session = update_session_title(user.id, session_id, title)
                updated_fields.append('title')
            
            if not updated_fields:
                return JsonResponse(
                    {'error': 'No fields to update. Provide model_used or title.'},
                    status=400
                )
            
            return JsonResponse({
                'id': session.id,
                'title': session.title,
                'model_used': session.model_used,
                'message': 'Session updated successfully'
            })
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error updating session: {e}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)
    
    elif request.method == 'DELETE':
        # Delete chat session
        success = delete_session(user.id, session_id)
        if not success:
            return JsonResponse(
                {'error': 'Chat session not found'},
                status=404
            )
        return JsonResponse({'message': 'Chat session deleted successfully'})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def chat_messages(request, session_id):
    """Get or send messages in a chat session."""
    user = get_current_user(request)
    if not user:
        return JsonResponse(
            {'error': 'Authentication required'},
            status=401
        )
    
    # Verify session belongs to user
    session = get_session(user.id, session_id)
    if not session:
        return JsonResponse(
            {'error': 'Chat session not found'},
            status=404
        )
    
    if request.method == 'GET':
        # Get messages in session
        # Try to get from active workflow buffer first (optimization for active sessions)
        messages_data = []
        
        try:
            from asgiref.sync import async_to_sync
            from app.agents.temporal.workflow_manager import get_workflow_messages
            
            # Try to get messages from workflow buffer
            workflow_messages = async_to_sync(get_workflow_messages)(user.id, session_id)
            
            if workflow_messages:
                # Convert workflow message dicts to API format
                messages_data = [
                    {
                        'id': None,  # Messages in buffer don't have DB IDs yet
                        'role': msg.get('role', 'assistant'),
                        'content': msg.get('content', ''),
                        'tokens_used': msg.get('tokens_used', 0),
                        'created_at': None,  # Timestamp is in msg.get('timestamp')
                        'metadata': msg.get('metadata', {}),
                        'buffered': True,  # Indicates message is in workflow buffer
                    }
                    for msg in workflow_messages
                ]
                logger.debug(f"Retrieved {len(messages_data)} messages from workflow buffer for session {session_id}")
            else:
                # Fallback to database
                messages = get_messages(session_id)
                messages_data = [
                    {
                        'id': msg.id,
                        'role': msg.role,
                        'content': msg.content,
                        'tokens_used': msg.tokens_used,
                        'created_at': msg.created_at.isoformat(),
                        'metadata': msg.metadata or {},
                    }
                    for msg in messages
                ]
                logger.debug(f"Retrieved {len(messages_data)} messages from database for session {session_id}")
        except Exception as e:
            # Fallback to database on any error
            logger.warning(f"Failed to get messages from workflow buffer, falling back to database: {e}")
            messages = get_messages(session_id)
            messages_data = [
                {
                    'id': msg.id,
                    'role': msg.role,
                    'content': msg.content,
                    'tokens_used': msg.tokens_used,
                    'created_at': msg.created_at.isoformat(),
                    'metadata': msg.metadata or {},
                }
                for msg in messages
            ]
        
        return JsonResponse({'messages': messages_data})
    
    elif request.method == 'POST':
        # Send message and get agent response
        try:
            data = json.loads(request.body)
            content = data.get('content', '').strip()
            
            if not content:
                return JsonResponse(
                    {'error': 'Message content is required'},
                    status=400
                )
            
            # This endpoint is deprecated - use /api/agent/stream/ for agent execution
            # POST to /api/chats/<session_id>/messages/ is only for adding messages without agent execution
            # For agent execution, clients should use the streaming endpoint
            return JsonResponse({
                'error': 'This endpoint does not support agent execution. Use /api/agent/stream/ for agent responses.'
            }, status=400)
        
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_all_chat_sessions(request):
    """Delete all chat sessions for the current user."""
    user = get_current_user(request)
    if not user:
        return JsonResponse(
            {'error': 'Authentication required'},
            status=401
        )
    
    try:
        deleted_count = delete_all_sessions(user.id)
        return JsonResponse({
            'message': f'Deleted {deleted_count} chat session(s) successfully',
            'deleted_count': deleted_count
        })
    except Exception as e:
        logger.error(f"Error deleting all sessions for user {user.id}: {e}", exc_info=True)
        return JsonResponse(
            {'error': 'Failed to delete all sessions'},
            status=500
        )


@csrf_exempt
@require_http_methods(["GET"])
def chat_session_stats(request, session_id):
    """Get statistics for a chat session."""
    user = get_current_user(request)
    if not user:
        return JsonResponse(
            {'error': 'Authentication required'},
            status=401
        )
    
    # Verify session belongs to user
    session = get_session(user.id, session_id)
    if not session:
        return JsonResponse(
            {'error': 'Chat session not found'},
            status=404
        )
    
    try:
        stats = get_session_stats(session_id)
        return JsonResponse(stats)
    except ValueError as e:
        # Langfuse metrics unavailable
        return JsonResponse(
            {'error': str(e)},
            status=503  # Service Unavailable
        )
    except Exception as e:
        logger.error(f"Error getting session stats: {e}", exc_info=True)
        return JsonResponse(
            {'error': 'Failed to get session statistics'},
            status=500
        )
