"""
Security utilities (JWT, password hashing).
"""
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model

User = get_user_model()


def generate_tokens(user):
    """
    Generate JWT access and refresh tokens for a user.
    Returns: dict with 'access' and 'refresh' tokens
    """
    refresh = RefreshToken.for_user(user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }


def refresh_token(refresh_token_string):
    """
    Generate new access token from refresh token.
    Returns: dict with 'access' token or None if invalid
    """
    try:
        refresh = RefreshToken(refresh_token_string)
        return {
            'access': str(refresh.access_token),
        }
    except Exception:
        return None
