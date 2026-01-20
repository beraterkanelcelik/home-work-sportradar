#!/usr/bin/env python
"""
Wait for database to be ready before starting the application.
This script retries database connection until it succeeds or times out.
"""
import os
import sys
import time
from psycopg import OperationalError
import psycopg

def wait_for_db(max_retries=30, retry_delay=2):
    """
    Wait for database to be ready.

    Args:
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds

    Returns:
        True if database is ready, False otherwise
    """
    # Get database configuration
    db_host = os.getenv('DB_HOST', 'db')
    db_port = int(os.getenv('DB_PORT', '5432'))
    db_user = os.getenv('DB_USER', 'postgres')
    db_password = os.getenv('DB_PASSWORD', 'postgres')
    db_name = os.getenv('DB_NAME', 'ai_agents_db')

    print(f"Waiting for database at {db_host}:{db_port}...")

    for attempt in range(1, max_retries + 1):
        try:
            # First check if PostgreSQL server is ready (connect to postgres DB)
            conn = psycopg.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                dbname='postgres',
                connect_timeout=5,
            )
            conn.close()

            # Then check if target database exists and is accessible
            try:
                conn = psycopg.connect(
                    host=db_host,
                    port=db_port,
                    user=db_user,
                    password=db_password,
                    dbname=db_name,
                    connect_timeout=5,
                )
                conn.close()
            except Exception:
                # Target DB might not exist yet, but server is ready
                # This is okay - migrations will create it
                pass

            print(f"✓ Database is ready! (attempt {attempt}/{max_retries})")
            return True
        except (OperationalError, Exception) as e:
            if attempt < max_retries:
                print(f"✗ Database not ready yet (attempt {attempt}/{max_retries}): {e}")
                print(f"  Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print(f"✗ Database failed to become ready after {max_retries} attempts")
                print(f"  Last error: {e}")
                return False

    return False


if __name__ == '__main__':
    success = wait_for_db()
    sys.exit(0 if success else 1)
