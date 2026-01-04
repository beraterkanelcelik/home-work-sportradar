"""
User service for profile management and token usage stats.
"""
from django.contrib.auth import get_user_model
from django.db.models import Sum
from datetime import datetime, timedelta
from app.db.models.session import ChatSession
from app.db.models.message import Message

User = get_user_model()


def get_user_profile(user_id):
    """
    Get user profile with basic information.
    Returns: User object
    """
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return None


def update_user_profile(user_id, data):
    """
    Update user profile information.
    Returns: Updated user object or None if not found
    """
    try:
        user = User.objects.get(id=user_id)
        
        if 'first_name' in data:
            user.first_name = data['first_name']
        if 'last_name' in data:
            user.last_name = data['last_name']
        if 'email' in data:
            # Check if email is already taken by another user
            if User.objects.filter(email=data['email']).exclude(id=user_id).exists():
                raise ValueError("Email already in use")
            user.email = data['email']
        
        user.save()
        return user
    except User.DoesNotExist:
        return None
    except Exception as e:
        raise ValueError(str(e))


def get_token_usage_stats(user_id):
    """
    Calculate token usage statistics for a user.
    Returns: dict with token usage stats
    """
    user = get_user_profile(user_id)
    if not user:
        return None
    
    # Total tokens used
    total_tokens = user.token_usage_count
    
    # Tokens used this month
    start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sessions_this_month = ChatSession.objects.filter(
        user_id=user_id,
        created_at__gte=start_of_month
    )
    tokens_this_month = sessions_this_month.aggregate(
        total=Sum('tokens_used')
    )['total'] or 0
    
    # Tokens used in last 30 days
    thirty_days_ago = datetime.now() - timedelta(days=30)
    sessions_last_30_days = ChatSession.objects.filter(
        user_id=user_id,
        created_at__gte=thirty_days_ago
    )
    tokens_last_30_days = sessions_last_30_days.aggregate(
        total=Sum('tokens_used')
    )['total'] or 0
    
    return {
        'total_tokens': total_tokens,
        'tokens_this_month': tokens_this_month,
        'tokens_last_30_days': tokens_last_30_days,
        'account_created': user.created_at.isoformat(),
    }
