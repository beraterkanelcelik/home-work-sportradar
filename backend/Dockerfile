# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
# Install NumPy first with explicit version to ensure compatibility
# NumPy 1.26.x doesn't have X86_V2 baseline by default, avoiding CPU compatibility issues
RUN pip install --upgrade pip && \
    pip install --no-cache-dir "numpy>=1.26.0,<2.0.0" && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

# Set working directory
WORKDIR /app

# Create directory for static files
RUN mkdir -p /app/staticfiles

# Expose Django default port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
# Use uvicorn for ASGI support (required for async views)
CMD ["uvicorn", "app.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
