"""
Account app configuration.
"""
from django.apps import AppConfig


class AccountConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.account'
    label = 'account'
    verbose_name = 'Account Management'
