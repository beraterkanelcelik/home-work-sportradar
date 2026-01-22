"""
PostgreSQL checkpoint adapter for LangGraph Functional API.
"""
import threading
import time
from typing import Optional, Dict, Any
from langgraph.checkpoint.postgres import PostgresSaver
from app.core.logging import get_logger

logger = get_logger(__name__)

# Sync checkpointer singleton
_sync_checkpointer: Optional[PostgresSaver] = None
_checkpointer_lock = threading.Lock()


def build_db_url() -> str:
    """
    Build database connection URL from Django settings.

    Returns:
        PostgreSQL connection string
    """
    from app.settings import DATABASES

    db_config = DATABASES["default"]
    return (
        f"postgresql://{db_config['USER']}:{db_config['PASSWORD']}"
        f"@{db_config['HOST']}:{db_config['PORT']}/{db_config['NAME']}"
    )


def get_sync_checkpointer() -> Optional[PostgresSaver]:
    """
    Get cached sync checkpointer with long-lived connection (lazy initialization).

    Creates a PostgresSaver with a persistent connection for the lifetime of the process.
    Uses lazy initialization to avoid connecting at import time (database may not be ready).
    Thread-safe singleton pattern ensures only one connection is created.

    Returns None if database is not available (allows module to import).

    Returns:
        PostgresSaver instance with persistent connection, or None if database unavailable
    """
    global _sync_checkpointer

    if _sync_checkpointer is not None:
        return _sync_checkpointer

    with _checkpointer_lock:
        # Double-check pattern
        if _sync_checkpointer is not None:
            return _sync_checkpointer

        try:
            from psycopg import Connection

            db_url = build_db_url()
            # Create a long-lived connection with autocommit enabled
            # This is the recommended approach for persistent checkpointers
            # Retry connection with exponential backoff if database isn't ready
            max_retries = 5
            retry_delay = 1.0

            conn = None
            for attempt in range(max_retries):
                try:
                    conn = Connection.connect(
                        db_url, autocommit=True, prepare_threshold=0, connect_timeout=2
                    )
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.debug(
                            f"Failed to connect to database (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s: {e}"
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        # On final failure, log but don't raise - allows module to import
                        logger.debug(
                            f"Database not available at import time, checkpointer will be created lazily on first use: {e}"
                        )
                        return None

            if conn is None:
                return None

            # Create PostgresSaver with the connection
            checkpointer = PostgresSaver(conn)

            # Initialize database tables (required by LangGraph)
            # This is safe to call multiple times - it only creates tables if they don't exist
            try:
                checkpointer.setup()
                logger.info("Checkpointer tables initialized successfully")
            except Exception as e:
                # Tables may already exist, or there might be a connection issue
                logger.warning(
                    f"Checkpointer setup warning (tables may already exist): {e}"
                )

            logger.info("Checkpointer created successfully")
            _sync_checkpointer = checkpointer
            return checkpointer
        except Exception as e:
            # Log error but return None to allow module import
            logger.warning(
                f"Failed to create checkpointer (will retry on first use): {e}"
            )
            return None


def get_checkpoint_config(chat_session_id: int) -> Dict[str, Any]:
    """
    Get checkpoint configuration for a chat session.
    Uses chat_session_id as the thread_id for checkpoint isolation.
    """
    return {
        "configurable": {
            "thread_id": f"chat_session_{chat_session_id}",
        }
    }
