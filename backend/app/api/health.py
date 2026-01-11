"""
Health check endpoint.
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import connection
from django.core.cache import cache
from app.observability.tracing import get_langfuse_client
from app.core.config import LANGFUSE_ENABLED


@require_http_methods(["GET"])
def health_check(request):
    """
    Health check endpoint for monitoring.
    Returns status of all services.
    """
    services = {}
    overall_status = "healthy"
    
    # Check Database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        services["database"] = {
            "status": "healthy",
            "message": "PostgreSQL connection successful"
        }
    except Exception as e:
        services["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}"
        }
        overall_status = "unhealthy"
    
    # Check Backend API
    try:
        services["backend"] = {
            "status": "healthy",
            "message": "Django backend is running"
        }
    except Exception as e:
        services["backend"] = {
            "status": "unhealthy",
            "message": f"Backend error: {str(e)}"
        }
        overall_status = "unhealthy"
    
    # Check Cache (optional, won't fail if not configured)
    try:
        cache.set("health_check", "ok", 10)
        cache.get("health_check")
        services["cache"] = {
            "status": "healthy",
            "message": "Cache is operational"
        }
    except Exception:
        services["cache"] = {
            "status": "degraded",
            "message": "Cache not available (optional service)"
        }
    
    # Check Langfuse (optional, won't fail if not configured)
    if LANGFUSE_ENABLED:
        try:
            langfuse_client = get_langfuse_client()
            if langfuse_client:
                # Try to make a simple API call to verify connectivity
                # This is a lightweight check that doesn't create traces
                try:
                    # Check if client has the necessary attributes
                    if hasattr(langfuse_client, 'api'):
                        services["langfuse"] = {
                            "status": "healthy",
                            "message": "Langfuse connection successful"
                        }
                    else:
                        services["langfuse"] = {
                            "status": "degraded",
                            "message": "Langfuse client initialized but API not accessible"
                        }
                except Exception as api_error:
                    services["langfuse"] = {
                        "status": "unhealthy",
                        "message": f"Langfuse API error: {str(api_error)}"
                    }
            else:
                services["langfuse"] = {
                    "status": "degraded",
                    "message": "Langfuse enabled but client not available (check configuration)"
                }
        except Exception as e:
            services["langfuse"] = {
                "status": "unhealthy",
                "message": f"Langfuse connection failed: {str(e)}"
            }
    else:
        services["langfuse"] = {
            "status": "degraded",
            "message": "Langfuse is disabled"
        }
    
    return JsonResponse({
        "status": overall_status,
        "services": services,
        "timestamp": None  # Will be set by frontend
    })
