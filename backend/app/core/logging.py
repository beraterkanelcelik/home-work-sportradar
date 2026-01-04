"""
Logging configuration.
"""
import logging
import sys

# TODO: Configure logging with LangSmith integration
# from app.observability.tracing import setup_langsmith_logging


def setup_logging():
    """
    Setup application logging.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # TODO: Add LangSmith logging integration
    # setup_langsmith_logging()


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.
    """
    return logging.getLogger(name)
