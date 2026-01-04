"""
Configuration management.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Django settings
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-change-this-in-production')
DEBUG = os.getenv('DEBUG', 'True') == 'True'

# Database configuration
DB_NAME = os.getenv('DB_NAME', 'ai_agents_db')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
DB_HOST = os.getenv('DB_HOST', 'db')
DB_PORT = os.getenv('DB_PORT', '5432')

# LangSmith configuration
LANGCHAIN_API_KEY = os.getenv('LANGCHAIN_API_KEY', '')
LANGCHAIN_TRACING_V2 = os.getenv('LANGCHAIN_TRACING_V2', 'false') == 'true'
LANGCHAIN_PROJECT = os.getenv('LANGCHAIN_PROJECT', 'django-app')
LANGCHAIN_ENDPOINT = os.getenv('LANGCHAIN_ENDPOINT', '')

# OpenAI configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
