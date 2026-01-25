# Simple single-stage build for reliability
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy application code
COPY . /app

# 🔒 CRITICAL: Normalize line endings for Windows-created shell scripts
RUN sed -i 's/\r$//' /app/create_databases.sh

# Make scripts executable
RUN chmod +x /app/create_databases.sh /app/create_minio_bucket.py

# Create directory for static files
RUN mkdir -p /app/staticfiles

# Expose port
EXPOSE 8000

# Default command (docker-compose overrides this)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
