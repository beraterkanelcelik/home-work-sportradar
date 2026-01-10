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
    
    Uses User.token_usage_count as the source of truth for total_tokens (persistent, 
    never decreases even when chats are deleted). Uses Langfuse Metrics API for 
    detailed breakdowns (input/output/cached tokens, costs, etc.).
    
    Returns: dict with token usage stats
    """
    user = get_user_profile(user_id)
    if not user:
        return None
    
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    
    # User.token_usage_count is the source of truth for total tokens
    # This is cumulative and never decreases, even when chats are deleted
    total_tokens_from_user = user.token_usage_count
    logger.info(f"User {user_id} total tokens from User model: {total_tokens_from_user}")
    
    # Try to get detailed metrics from Langfuse for breakdowns
    langfuse_metrics = None
    try:
        from app.services.langfuse_metrics import get_user_metrics_from_langfuse
        logger.info(f"Attempting to get Langfuse metrics for user {user_id}")
        langfuse_metrics = get_user_metrics_from_langfuse(user_id)
        
        if langfuse_metrics:
            logger.info(f"Langfuse metrics retrieved for user {user_id}: total_tokens={langfuse_metrics.get('total_tokens', 0)}")
        else:
            logger.info(f"Langfuse metrics returned None for user {user_id}")
    except Exception as e:
        # Log but don't fail - we'll use User model for total tokens
        logger.warning(f"Langfuse metrics unavailable for user {user_id}: {e}", exc_info=True)
    
    # Use User.token_usage_count as source of truth for total_tokens
    # Use Langfuse for detailed breakdowns if available
    if langfuse_metrics:
        # Return comprehensive metrics with User model total_tokens as source of truth
        return {
            'total_tokens': total_tokens_from_user,  # Source of truth from User model
            'input_tokens': langfuse_metrics.get('input_tokens', 0),
            'output_tokens': langfuse_metrics.get('output_tokens', 0),
            'cached_tokens': langfuse_metrics.get('cached_tokens', 0),
            'tokens_this_month': langfuse_metrics.get('tokens_this_month', 0),
            'input_tokens_this_month': langfuse_metrics.get('input_tokens_this_month', 0),
            'output_tokens_this_month': langfuse_metrics.get('output_tokens_this_month', 0),
            'tokens_last_30_days': langfuse_metrics.get('tokens_last_30_days', 0),
            'input_tokens_last_30_days': langfuse_metrics.get('input_tokens_last_30_days', 0),
            'output_tokens_last_30_days': langfuse_metrics.get('output_tokens_last_30_days', 0),
            'total_cost': langfuse_metrics.get('total_cost', 0.0),
            'cost_this_month': langfuse_metrics.get('cost_this_month', 0.0),
            'cost_last_30_days': langfuse_metrics.get('cost_last_30_days', 0.0),
            'agent_usage': langfuse_metrics.get('agent_usage', {}),
            'tool_usage': langfuse_metrics.get('tool_usage', {}),
            'total_sessions': langfuse_metrics.get('total_sessions', 0),
            'sessions_this_month': langfuse_metrics.get('sessions_this_month', 0),
            'sessions_last_30_days': langfuse_metrics.get('sessions_last_30_days', 0),
            'account_created': langfuse_metrics.get('account_created') or user.created_at.isoformat(),
        }
    
    # Fallback to database aggregation if Langfuse unavailable
    logger.info(f"Using database fallback for user {user_id} token stats")
    
    total_tokens = total_tokens_from_user
    
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
    
    total_sessions = ChatSession.objects.filter(user_id=user_id).count()
    
    logger.info(f"Database stats for user {user_id}: total_tokens={total_tokens}, tokens_this_month={tokens_this_month}, tokens_last_30_days={tokens_last_30_days}, total_sessions={total_sessions}")
    
    return {
        'total_tokens': total_tokens,
        'input_tokens': 0,  # Not available from database
        'output_tokens': 0,  # Not available from database
        'cached_tokens': 0,  # Not available from database
        'tokens_this_month': tokens_this_month,
        'input_tokens_this_month': 0,
        'output_tokens_this_month': 0,
        'tokens_last_30_days': tokens_last_30_days,
        'input_tokens_last_30_days': 0,
        'output_tokens_last_30_days': 0,
        'total_cost': 0.0,
        'cost_this_month': 0.0,
        'cost_last_30_days': 0.0,
        'agent_usage': {},
        'tool_usage': {},
        'total_sessions': total_sessions,
        'sessions_this_month': sessions_this_month.count(),
        'sessions_last_30_days': sessions_last_30_days.count(),
        'account_created': user.created_at.isoformat(),
    }
