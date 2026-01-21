"""
ASGI config for mysite project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import atexit
import os
from django.core.asgi import get_asgi_application
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from app.observability.tracing import cleanup_all_clients

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

# Register cleanup function for Langfuse clients on shutdown
atexit.register(cleanup_all_clients)

# Get the ASGI application
django_asgi_app = get_asgi_application()

# Wrap with static files handler for development
# In production, static files should be served by nginx or a CDN
application = ASGIStaticFilesHandler(django_asgi_app)
