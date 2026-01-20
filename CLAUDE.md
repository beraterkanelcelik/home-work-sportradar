# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Agent Playground is a production-ready multi-agent platform built on LangGraph Functional API. It features real-time streaming, full observability via Langfuse, intelligent routing via a supervisor agent, and RAG with PostgreSQL + pgvector.

**Stack:** Django 5.0 backend, React 18 + Vite frontend, PostgreSQL 16 + pgvector, Redis (pub/sub for streaming), Temporal (workflow orchestration), Langfuse (tracing)

## Common Commands

All commands run via Docker Compose. Use `make help` to see available targets.

```bash
# Start/stop services
make up                    # Start all services
make up-observability      # Start with Langfuse, ClickHouse, MinIO, Temporal UI
make down                  # Stop services
make logs                  # Follow all logs
make logs-backend          # Follow backend logs only

# Database
make migrate               # Run Django migrations
make makemigrations        # Create new migrations
make shell-db              # Open psql shell

# Development shells
make shell-backend         # Bash into backend container

# Testing
make test                  # Run all tests

# Run specific tests
docker-compose exec backend python manage.py test tests.test_workflow
docker-compose exec backend python manage.py test tests.test_workflow.TestExtractToolProposals
docker-compose exec backend python manage.py test tests.test_workflow.TestExtractToolProposals.test_extract_tool_proposals_basic
```

## Architecture

### Data Flow
```
React UI → Django API → Temporal workflows → LangGraph Functional tasks
Streaming: Redis pub/sub → SSE → UI
State & RAG: PostgreSQL (checkpoints + pgvector)
Tracing: Langfuse
```

### Multi-Agent System
- **Supervisor Agent** (`backend/app/agents/agents/supervisor.py`): Routes user messages to specialized agents
- **Specialized Agents**: Greeter, Planner, Search agents in `backend/app/agents/agents/`
- **Agent Factory** (`backend/app/agents/factory.py`): Dynamic agent instantiation

### LangGraph Functional API
The workflow uses LangGraph's Functional API with decorators:
- `@entrypoint` for workflow entry in `backend/app/agents/functional/workflow.py`
- `@task` decorators for discrete operations in `backend/app/agents/functional/tasks/`
- PostgreSQL checkpointing for state persistence
- Interrupt mechanism for tool approval workflows

### Key Directories
- `backend/app/agents/` - Agent runtime, tools, LangGraph workflow
- `backend/app/rag/` - Chunking, embeddings, vector store, reranking
- `backend/app/documents/` - Document processing pipeline (PDF/MD/TXT extraction, OCR)
- `backend/app/api/` - REST endpoints
- `backend/app/db/models/` - Django models (ChatSession, Message, Document, Chunk)
- `frontend/src/state/` - Zustand stores (useAuthStore, useChatStore)
- `frontend/src/lib/` - API clients, streaming utilities

### Streaming Implementation
SSE streaming via `AgentRunner` class in `backend/app/agents/runner.py`. Events published to Redis, consumed by frontend. Event types include: task_start, task_complete, tool_proposal, plan_proposal.

### RAG Pipeline
- **Chunking**: Recursive (default) or semantic in `backend/app/rag/chunking/`
- **Embeddings**: OpenAI text-embedding-3-small
- **Vector Store**: pgvector in PostgreSQL
- **Reranking**: Cohere rerank-english-v3.0
- Config: chunk_size=1000 tokens, overlap=150, top_k=30, top_n=8 (after rerank)

## Testing Patterns

### Testing LangGraph @task Functions
Use the helper in `backend/tests/test_helpers.py`:
```python
from tests.test_helpers import create_test_entrypoint, get_test_config

def test_execute_agent():
    test_entrypoint = create_test_entrypoint(execute_agent_task)
    config = get_test_config()
    result = test_entrypoint.invoke((messages, agent_name, user_id), config=config)
```

### Test Categories
- Unit tests: `tests/test_workflow.py`, `test_agents.py`, `test_tools.py`, etc.
- Integration tests: `tests/test_integration.py`
- E2E tests: `tests/test_e2e.py`
- Load/stress tests: `tests/test_load_stress.py`, `test_scalability_levels.py`

## Environment Variables

Required in `.env`:
```
OPENAI_MODEL=gpt-4o-mini
```

Optional for observability:
```
LANGFUSE_ENABLED=true
```

Per-user credentials (OpenAI, Langfuse) are set in the Profile page.


## Service URLs

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Langfuse: http://localhost:3001 (if enabled)
- Temporal UI: http://localhost:8080 (with observability profile)
