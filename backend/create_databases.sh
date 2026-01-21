#!/bin/bash
# Script to ensure required databases exist

set -e

echo "Checking database setup..."

# Wait for database to be ready
until pg_isready -h db -p 5432 -U app; do
  echo "Waiting for database..."
  sleep 2
done

# Create databases if they don't exist
psql -h db -p 5432 -U app -d postgres -c "CREATE DATABASE langfuse_db;" 2>/dev/null || echo "langfuse_db already exists"
psql -h db -p 5432 -U app -d postgres -c "CREATE DATABASE temporal_db;" 2>/dev/null || echo "temporal_db already exists"

echo "Database setup complete."