# AI Agent Test Website

A monorepo project for building and testing AI agents using Django, LangChain, LangGraph, PostgreSQL with pgvector, and React + Vite frontend.

## Project Structure

```
TestAgentProject/
├─ README.md
├─ .gitignore
├─ .env.example
├─ docker-compose.yml          # Root level orchestration
├─ Makefile                    # Convenience commands
├─ scripts/                    # Utility scripts
│  ├─ dev.sh
│  └─ seed_demo_data.py
│
├─ infra/                      # Infrastructure configs
│  ├─ postgres/
│  │  ├─ init.sql
│  │  └─ extensions.sql       # pgvector extension
│  └─ nginx/
│     └─ nginx.conf
│
├─ backend/                    # Django backend
│  ├─ Dockerfile
│  ├─ requirements.txt
│  ├─ manage.py
│  ├─ .env.example
│  ├─ tests/
│  └─ app/                     # Main Django app
│     ├─ settings.py
│     ├─ urls.py
│     ├─ api/                   # API endpoints
│     ├─ core/                  # Core utilities
│     ├─ db/                    # Database models
│     ├─ services/              # Business logic
│     ├─ rag/                   # RAG components
│     ├─ agents/                # LangGraph agents
│     └─ observability/         # Tracing
│
└─ frontend/                   # React + Vite frontend
   ├─ Dockerfile
   ├─ package.json
   ├─ vite.config.ts
   ├─ tailwind.config.js
   ├─ .env.example
   └─ src/
      ├─ app/
      ├─ components/
      ├─ lib/
      └─ state/
```

## Prerequisites

- Docker and Docker Compose
- Git (optional)

## Quick Start

1. **Create environment file:**
   ```bash
   copy .env.example .env
   # On macOS/Linux: cp .env.example .env
   ```

2. **Edit `.env` file** with your API keys and configuration

3. **Start all services:**
   ```bash
   make up
   # Or: docker-compose up -d
   ```

4. **Run migrations:**
   ```bash
   make migrate
   ```

5. **Access the application:**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - Nginx Proxy: http://localhost
   - Admin: http://localhost/admin/

## Makefile Commands

```bash
make help          # Show all available commands
make build         # Build all Docker images
make up            # Start all services
make down          # Stop all services
make restart       # Restart all services
make logs          # Show logs from all services
make migrate       # Run database migrations
make superuser     # Create Django superuser
make test          # Run tests
make clean         # Remove all containers and volumes
```

## Development

### Backend Development

```bash
# Open backend shell
make shell-backend

# Create migrations
make makemigrations

# Run migrations
make migrate

# Run tests
make test
```

### Frontend Development

The frontend runs in development mode with hot-reload enabled. Changes are automatically reflected.

### Database Access

```bash
# Open psql shell
make shell-db

# Or directly
docker-compose exec db psql -U postgres -d ai_agents_db
```

## Architecture

### Backend (Django)

- **API Layer** (`app/api/`): REST API endpoints
- **Core** (`app/core/`): Configuration, security, logging
- **Database** (`app/db/`): Models and database operations
- **Services** (`app/services/`): Business logic
- **RAG** (`app/rag/`): Document processing and vector search
- **Agents** (`app/agents/`): LangGraph agent definitions
- **Observability** (`app/observability/`): LangSmith tracing

### Frontend (React + Vite)

- **Framework**: React 18 with Vite
- **UI**: Tailwind CSS + shadcn/ui components
- **State Management**: Zustand
- **Routing**: React Router
- **API Client**: Axios with interceptors
- **Streaming**: SSE (Server-Sent Events) for agent responses

### Database (PostgreSQL + pgvector)

- Multi-tenant architecture with user isolation
- Vector embeddings for RAG
- All queries filtered by `user_id`

## Features

- ✅ Multi-user authentication (JWT)
- ✅ Chat sessions and messages
- ✅ Document upload and ingestion
- ✅ RAG with pgvector
- ✅ LangGraph agents
- ✅ LangSmith tracing
- ✅ Hot-reload for development

## API Endpoints

- `GET /api/health/` - Health check
- `POST /api/auth/signup/` - User registration
- `POST /api/auth/login/` - User login
- `GET /api/users/me/` - Get current user
- `GET /api/chats/` - List chat sessions
- `POST /api/chats/` - Create chat session
- `GET /api/documents/` - List documents
- `POST /api/documents/` - Upload document
- `POST /api/agent/run/` - Run agent

## Environment Variables

See `.env.example` for all required environment variables:

- Django configuration
- PostgreSQL connection
- LangSmith API keys
- OpenAI API keys

## Documentation

- [Django Documentation](https://docs.djangoproject.com/)
- [LangChain Documentation](https://python.langchain.com/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [React Documentation](https://react.dev/)
- [Vite Documentation](https://vitejs.dev/)
- [Tailwind CSS Documentation](https://tailwindcss.com/)
- [shadcn/ui Documentation](https://ui.shadcn.com/)

## License

MIT
