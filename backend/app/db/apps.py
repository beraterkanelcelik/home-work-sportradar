"""
Database models app configuration.
"""
from django.apps import AppConfig


class DbConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.db'
    verbose_name = 'Database Models'
    
    def ready(self):
        # Import models here to avoid circular imports
        # Note: User model is now in app.account.models
        from .models import session, message  # noqa