"""
User management endpoints.
"""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from app.core.dependencies import get_current_user
from app.account.services.user_service import (
    get_user_profile,
    update_user_profile,
    get_token_usage_stats,
)


@csrf_exempt
@require_http_methods(["GET"])
def get_current_user_endpoint(request):
    """Get current authenticated user profile."""
    user = get_current_user(request)
    if not user:
        return JsonResponse(
            {'error': 'Authentication required'},
            status=401
        )
    
    return JsonResponse({
        'id': user.id,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'created_at': user.created_at.isoformat(),
        'token_usage_count': user.token_usage_count,
    })


@csrf_exempt
@require_http_methods(["PUT"])
def update_current_user(request):
    """Update current authenticated user profile."""
    user = get_current_user(request)
    if not user:
        return JsonResponse(
            {'error': 'Authentication required'},
            status=401
        )
    
    try:
        data = json.loads(request.body)
        updated_user = update_user_profile(user.id, data)
        
        if not updated_user:
            return JsonResponse(
                {'error': 'User not found'},
                status=404
            )
        
        return JsonResponse({
            'message': 'Profile updated successfully',
            'user': {
                'id': updated_user.id,
                'email': updated_user.email,
                'first_name': updated_user.first_name,
                'last_name': updated_user.last_name,
            },
        })
    
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_user_stats(request):
    """Get token usage statistics for current user."""
    user = get_current_user(request)
    if not user:
        return JsonResponse(
            {'error': 'Authentication required'},
            status=401
        )
    
    stats = get_token_usage_stats(user.id)
    
    if not stats:
        return JsonResponse(
            {'error': 'User not found'},
            status=404
        )
    
    return JsonResponse(stats)
