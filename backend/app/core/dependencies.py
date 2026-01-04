"""
Dependency injection utilities.
"""
from typing import Optional
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

User = get_user_model()


def get_current_user(request) -> Optional[User]:
    """
    Get current authenticated user from request.
    Supports both JWT and session authentication.
    """
    # Try JWT authentication first
    jwt_auth = JWTAuthentication()
    try:
        validated_token = jwt_auth.get_validated_token(jwt_auth.get_raw_token(jwt_auth.get_header(request)))
        user = jwt_auth.get_user(validated_token)
        return user
    except (InvalidToken, AttributeError, TypeError):
        pass
    
    # Fall back to session authentication
    if hasattr(request, 'user') and request.user.is_authenticated:
        return request.user
    
    return None


def require_auth(request):
    """
    Check if request is authenticated.
    Raises exception if not authenticated.
    """
    user = get_current_user(request)
    if not user:
        from django.http import JsonResponse
        return JsonResponse({'error': 'Authentication required'}, status=401)
    return user
