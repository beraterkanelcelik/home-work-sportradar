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
from app.account.services.api_key_service import (
    get_user_api_keys_status,
    update_user_api_keys,
    clear_user_api_keys,
)
from django.utils import timezone
from app.account.services.api_key_validator import validate_api_keys_bundle


@csrf_exempt
@require_http_methods(["GET"])
def get_current_user_endpoint(request):
    """Get current authenticated user profile."""
    user = get_current_user(request)
    if not user:
        return JsonResponse({"error": "Authentication required"}, status=401)

    return JsonResponse(
        {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "created_at": user.created_at.isoformat(),
            "token_usage_count": user.token_usage_count,
        }
    )


@csrf_exempt
@require_http_methods(["PUT"])
def update_current_user(request):
    """Update current authenticated user profile."""
    user = get_current_user(request)
    if not user:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        data = json.loads(request.body)
        updated_user = update_user_profile(user.id, data)

        if not updated_user:
            return JsonResponse({"error": "User not found"}, status=404)

        return JsonResponse(
            {
                "message": "Profile updated successfully",
                "user": {
                    "id": updated_user.id,
                    "email": updated_user.email,
                    "first_name": updated_user.first_name,
                    "last_name": updated_user.last_name,
                },
            }
        )

    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_user_stats(request):
    """Get token usage statistics for current user."""
    user = get_current_user(request)
    if not user:
        return JsonResponse({"error": "Authentication required"}, status=401)

    stats = get_token_usage_stats(user.id)

    if not stats:
        return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse(stats)


@csrf_exempt
@require_http_methods(["GET"])
def get_user_api_keys(request):
    """Return API key status for current user (never returns raw keys)."""
    user = get_current_user(request)
    if not user:
        return JsonResponse({"error": "Authentication required"}, status=401)
    status_payload = get_user_api_keys_status(user.id)
    if status_payload is None:
        return JsonResponse({"error": "User not found"}, status=404)
    return JsonResponse(status_payload)


@csrf_exempt
@require_http_methods(["PUT"])
def update_user_api_keys_endpoint(request):
    """Validate and persist user-provided API keys."""
    user = get_current_user(request)
    if not user:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    openai_key = data.get("openai_api_key")
    langfuse_public = data.get("langfuse_public_key")
    langfuse_secret = data.get("langfuse_secret_key")

    key_values = [openai_key, langfuse_public, langfuse_secret]
    non_empty_keys = [value for value in key_values if value not in (None, "")]
    empty_keys = [value for value in key_values if value == ""]

    if non_empty_keys:
        if len(non_empty_keys) != 3:
            return JsonResponse(
                {
                    "error": "OpenAI and both Langfuse keys must be provided together"
                },
                status=400,
            )
        ok, msg = validate_api_keys_bundle(
            openai_key or "",
            langfuse_public or "",
            langfuse_secret or "",
        )
        if not ok:
            return JsonResponse({"error": msg}, status=400)

        status_payload = update_user_api_keys(
            user_id=user.id,
            openai_api_key=openai_key,
            langfuse_public_key=langfuse_public,
            langfuse_secret_key=langfuse_secret,
            api_keys_validated=True,
            api_keys_validated_at=timezone.now(),
        )
    elif empty_keys:
        if len(empty_keys) != 3:
            return JsonResponse(
                {
                    "error": "OpenAI and both Langfuse keys must be provided together"
                },
                status=400,
            )
        status_payload = update_user_api_keys(
            user_id=user.id,
            openai_api_key=openai_key,
            langfuse_public_key=langfuse_public,
            langfuse_secret_key=langfuse_secret,
            api_keys_validated=False,
        )
    else:
        status_payload = update_user_api_keys(
            user_id=user.id,
            openai_api_key=openai_key,
            langfuse_public_key=langfuse_public,
            langfuse_secret_key=langfuse_secret,
        )
    if status_payload is None:
        return JsonResponse({"error": "User not found"}, status=404)
    return JsonResponse({"message": "API keys updated", "status": status_payload})


@csrf_exempt
@require_http_methods(["DELETE"])
def clear_user_api_keys_endpoint(request):
    """Clear all custom API keys for the current user."""
    user = get_current_user(request)
    if not user:
        return JsonResponse({"error": "Authentication required"}, status=401)

    status_payload = clear_user_api_keys(user.id)
    if status_payload is None:
        return JsonResponse({"error": "User not found"}, status=404)
    return JsonResponse({"message": "API keys cleared", "status": status_payload})
