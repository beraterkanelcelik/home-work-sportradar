"""
Authentication service.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from app.core.security import generate_tokens

User = get_user_model()


def create_user(email: str, password: str, first_name: str = '', last_name: str = ''):
    """
    Create a new user.
    Returns: (user, tokens_dict) or raises ValidationError
    """
    try:
        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        tokens = generate_tokens(user)
        return user, tokens
    except IntegrityError:
        raise ValidationError("A user with this email already exists.")
    except Exception as e:
        raise ValidationError(f"Error creating user: {str(e)}")


def authenticate_user(email: str, password: str):
    """
    Verify user credentials.
    Returns: (user, tokens_dict) or None if invalid
    """
    user = authenticate(username=email, password=password)
    if user and user.is_active:
        tokens = generate_tokens(user)
        return user, tokens
    return None, None


def change_password(user, old_password: str, new_password: str):
    """
    Change user password.
    Returns: True if successful, False if old password is incorrect
    """
    if not user.check_password(old_password):
        return False
    
    user.set_password(new_password)
    user.save()
    return True


def refresh_token(refresh_token_string: str):
    """
    Generate new access token from refresh token.
    Returns: dict with 'access' token or None if invalid
    """
    from app.core.security import refresh_token as refresh_token_func
    return refresh_token_func(refresh_token_string)
