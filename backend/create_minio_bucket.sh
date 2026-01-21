#!/bin/bash
# Script to initialize MinIO bucket for Langfuse

set -e

echo "Checking MinIO setup..."

# Wait for MinIO to be ready
until curl -f http://minio:9000/minio/health/ready; do
  echo "Waiting for MinIO..."
  sleep 2
done

# Create bucket if it doesn't exist
echo "Creating langfuse-events bucket..."
curl -X PUT http://minio:9000/langfuse-events \
  -H "Authorization: AWS4-HMAC-SHA256 Credential=minio/minio" \
  2>/dev/null || echo "Bucket langfuse-events already exists or failed to create"

echo "MinIO setup complete."