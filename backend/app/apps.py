"""
Django app configuration.
"""

from django.apps import AppConfig


class AppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app"
    verbose_name = "Agent Playground"

    def ready(self):
        """Initialize app when Django is ready."""
        # Logging will be initialized lazily when needed
        pass
