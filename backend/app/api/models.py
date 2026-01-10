"""
Model configuration endpoints.
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from app.core.dependencies import get_current_user
from app.core.logging import get_logger

logger = get_logger(__name__)

# Available models - centralized configuration
AVAILABLE_MODELS = [
    {
        'id': 'gpt-4o-mini',
        'name': 'GPT-4o Mini',
        'description': 'Fast and efficient',
        'provider': 'openai'
    },
    {
        'id': 'gpt-4o',
        'name': 'GPT-4o',
        'description': 'Most capable model',
        'provider': 'openai'
    },
    {
        'id': 'gpt-4-turbo',
        'name': 'GPT-4 Turbo',
        'description': 'High performance',
        'provider': 'openai'
    },
    {
        'id': 'gpt-3.5-turbo',
        'name': 'GPT-3.5 Turbo',
        'description': 'Fast and affordable',
        'provider': 'openai'
    },
]


@csrf_exempt
@require_http_methods(["GET"])
def get_available_models(request):
    """
    Get list of available models.
    
    Returns:
    {
        "models": [
            {
                "id": "gpt-4o-mini",
                "name": "GPT-4o Mini",
                "description": "Fast and efficient",
                "provider": "openai"
            },
            ...
        ]
    }
    """
    user = get_current_user(request)
    if not user:
        return JsonResponse(
            {'error': 'Authentication required'},
            status=401
        )
    
    return JsonResponse({
        'models': AVAILABLE_MODELS
    })
