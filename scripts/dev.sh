#!/bin/bash
# Development script to start all services

echo "Starting development environment..."

# Start all services
docker-compose up -d

echo "Waiting for services to be ready..."
sleep 5

# Run migrations
echo "Running database migrations..."
docker-compose exec backend python manage.py migrate

echo "Development environment is ready!"
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "Nginx: http://localhost"
