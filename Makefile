.PHONY: help build up down restart logs shell migrate test clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build all Docker images
	docker-compose build

up: ## Start all services
	docker-compose up -d

down: ## Stop all services
	docker-compose down

restart: ## Restart all services
	docker-compose restart

logs: ## Show logs from all services
	docker-compose logs -f

logs-backend: ## Show backend logs
	docker-compose logs -f backend

logs-frontend: ## Show frontend logs
	docker-compose logs -f frontend

logs-db: ## Show database logs
	docker-compose logs -f db

shell-backend: ## Open shell in backend container
	docker-compose exec backend bash

shell-db: ## Open psql in database
	docker-compose exec db psql -U postgres -d ai_agents_db

migrate: ## Run database migrations
	docker-compose exec backend python manage.py migrate

makemigrations: ## Create new migrations
	docker-compose exec backend python manage.py makemigrations

superuser: ## Create Django superuser (interactive - may not work on Windows)
	docker-compose exec backend python manage.py createsuperuser

superuser-create: ## Create Django superuser non-interactively (usage: make superuser-create EMAIL=admin@example.com PASSWORD=password)
	docker-compose exec backend python create_superuser.py $(EMAIL) $(PASSWORD)

test: ## Run tests
	docker-compose exec backend python manage.py test

clean: ## Remove all containers and volumes
	docker-compose down -v
	docker system prune -f
