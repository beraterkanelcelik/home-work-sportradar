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
    
    # When using PgBouncer, connect directly to target database (wildcard routing)
    # When using direct PostgreSQL, try postgres DB first (always exists)
    use_pgbouncer = db_host == 'pgbouncer' or db_port == 6432
    
    if use_pgbouncer:
        # PgBouncer: connect directly to target database (wildcard * handles any DB)
        db_config = {
            'host': db_host,
            'port': db_port,
            'user': db_user,
            'password': db_password,
            'dbname': db_name,  # Connect directly to target DB
            'connect_timeout': 5,
        }
    else:
        # Direct PostgreSQL: try postgres DB first, then target DB
        db_configs = [
            {
                'host': db_host,
                'port': db_port,
                'user': db_user,
                'password': db_password,
                'dbname': 'postgres',  # Connect to postgres DB first (always exists)
                'connect_timeout': 5,
            },
            {
                'host': db_host,
                'port': db_port,
                'user': db_user,
                'password': db_password,
                'dbname': db_name,  # Then check target DB
                'connect_timeout': 5,
            }
        ]
    
    print(f"Waiting for database at {db_host}:{db_port}...")
    
    for attempt in range(1, max_retries + 1):
        try:
            if use_pgbouncer:
                # PgBouncer: single connection attempt
                conn = psycopg.connect(**db_config)
                conn.close()
            else:
                # Direct PostgreSQL: check server first, then target DB
                conn = psycopg.connect(**db_configs[0])
                conn.close()
                
                # Then check if target database exists and is accessible
                try:
                    conn = psycopg.connect(**db_configs[1])
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
