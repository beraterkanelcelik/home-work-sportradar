"""
Database session management.
"""
from django.db import connection

# TODO: Configure database connection pooling if needed
# For Django, connection is managed automatically


def get_db_connection():
    """
    Get database connection.
    """
    return connection
