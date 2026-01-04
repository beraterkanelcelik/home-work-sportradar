"""
Authentication endpoints (signup, login, logout, refresh, change-password).
"""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import login as django_login, logout as django_logout
from app.account.services.auth_service import (
    create_user,
    authenticate_user,
    change_password,
    refresh_token as refresh_token_service,
)
from app.core.dependencies import get_current_user


@csrf_exempt
@require_http_methods(["POST"])
def signup(request):
    """User registration endpoint."""
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
        password = data.get('password', '')
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        
        if not email or not password:
            return JsonResponse(
                {'error': 'Email and password are required'},
                status=400
            )
        
        user, tokens = create_user(email, password, first_name, last_name)
        
        # Also create session for web authentication
        django_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        
        return JsonResponse({
            'message': 'User created successfully',
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            },
            'access': tokens['access'],
            'refresh': tokens['refresh'],
        }, status=201)
    
    except ValueError as e:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def login(request):
    """User login endpoint."""
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not email or not password:
            return JsonResponse(
                {'error': 'Email and password are required'},
                status=400
            )
        
        user, tokens = authenticate_user(email, password)
        
        if not user:
            return JsonResponse(
                {'error': 'Invalid credentials'},
                status=401
            )
        
        # Also create session for web authentication
        django_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        
        return JsonResponse({
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            },
            'access': tokens['access'],
            'refresh': tokens['refresh'],
        })
    
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def refresh(request):
    """Token refresh endpoint."""
    try:
        data = json.loads(request.body)
        refresh_token_string = data.get('refresh', '')
        
        if not refresh_token_string:
            return JsonResponse(
                {'error': 'Refresh token is required'},
                status=400
            )
        
        result = refresh_token_service(refresh_token_string)
        
        if not result:
            return JsonResponse(
                {'error': 'Invalid refresh token'},
                status=401
            )
        
        return JsonResponse({
            'access': result['access'],
        })
    
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def logout(request):
    """User logout endpoint."""
    try:
        # Logout from session
        django_logout(request)
        
        return JsonResponse({
            'message': 'Logout successful',
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def change_password(request):
    """Change password endpoint."""
    try:
        user = get_current_user(request)
        if not user:
            return JsonResponse(
                {'error': 'Authentication required'},
                status=401
            )
        
        data = json.loads(request.body)
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')
        
        if not old_password or not new_password:
            return JsonResponse(
                {'error': 'Old password and new password are required'},
                status=400
            )
        
        success = change_password(user, old_password, new_password)
        
        if not success:
            return JsonResponse(
                {'error': 'Invalid old password'},
                status=400
            )
        
        return JsonResponse({
            'message': 'Password changed successfully',
        })
    
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
