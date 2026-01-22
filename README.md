# Sports Scouting Agent

A production-grade agentic web application for sports player scouting. The agent accepts natural language goals, generates execution plans, and performs real actions across server and client.

![Demo](./docs/demo.gif)

**[Watch Full Demo on YouTube](https://youtube.com/your-video-link)**

---

## Quick Start

### 1. Environment Setup

```bash
cp .env.example .env
```

### 2. Launch Services

```bash
docker-compose up -d
```

Wait for all services to be healthy (~60 seconds on first run).

### 3. Configure Observability (Required)

Navigate to **http://localhost:3001** (Langfuse) and:

1. **Register** an account
2. **Create Organization** → Create **Project**
3. Go to **Settings** → **API Keys** → Generate **Public Key** and **Secret Key**

### 4. Application Setup

1. Open **http://localhost:3000**
2. Register/Login
3. Go to **Profile Settings**
4. Enter your:
   - OpenAI API Key
   - Langfuse Public Key
   - Langfuse Secret Key
5. Press **Save**

You're ready to scout players.

---

## What This App Does

![Status Demo](./docs/status.gif)

A scouting agent that demonstrates:

| Requirement | Implementation |
|-------------|----------------|
| **Agent Behavior** | Accepts freeform goals → Generates search plan → Executes steps autonomously |
| **Activity Log** | Real-time task panel showing plan steps, tool executions, success/failure states |
| **Server Actions (3+)** | `search_documents` (RAG), `save_player_report` (DB persist), plan generation (LLM workflow) |
| **Client Actions (2+)** | Dynamic plan panel rendering, player preview card with approval UI |
| **Knowledge System** | RAG with pgvector embeddings, session history, accumulated search context |
| **User Approval** | Two HITL gates: Plan approval + Save approval (no silent destructive actions) |
| **Frontend Quality** | Conversation view, plan panel, trace log, saved reports page |

---

## Server-Side Tools

| Tool | Description | Real Work |
|------|-------------|-----------|
| `search_documents` | RAG retrieval via pgvector | Embedding search, returns ranked chunks |
| `save_player_report` | Persists scouting report | Creates Player + ScoutingReport records |
| `list_reports` | Query existing reports | DB lookup with filtering, prevents duplicates |
| `plan_generation` | LLM-powered planning | Analyzes request, generates 3-5 search steps |

---

## Client-Side Actions

| Action | Trigger | Observable Behavior |
|--------|---------|---------------------|
| Plan Panel Update | `plan_proposal` event | Right sidebar populates with search steps + approve button |
| Player Preview Card | `player_preview` event | Modal shows extracted player data with approve/reject |
| Task Progress | `tasks_updated` event | Real-time checkmarks on completed steps |
| Token Streaming | `token` events | Character-by-character response rendering |

---

## Knowledge System

**Where it lives:**
- PostgreSQL with pgvector extension
- Document chunks with embeddings

**How it's used:**
- Agent searches knowledge base via `search_documents` tool
- RAG context accumulates across plan steps
- UI shows "Searching knowledge base..." during retrieval
- Report composition uses all gathered context

---

## Architecture

### System Overview

```mermaid
flowchart TB
    subgraph Client["Frontend (React + Zustand)"]
        UI[Chat UI]
        SSE[SSE Stream]
        State[Zustand Store]
    end

    subgraph Backend["Backend (Django + ASGI)"]
        API[REST API]
        WM[Workflow Manager]
    end

    subgraph Temporal["Temporal Orchestration"]
        TS[Temporal Server]
        TW[Temporal Worker]
    end

    subgraph StateGraph["LangGraph StateGraph"]
        PN[Planner]
        AN[Agent]
        TN[Tools]
        CN[Composer]
    end

    subgraph Infra["Infrastructure"]
        PG[(PostgreSQL)]
        RD[(Redis)]
        LF[Langfuse]
    end

    UI -->|HTTP| API
    API -->|Signal| TS
    TS -->|Execute| TW
    TW --> StateGraph
    StateGraph -->|Publish| RD
    RD -->|Subscribe| SSE
    SSE --> State --> UI
    StateGraph -->|Checkpoint| PG
    StateGraph -->|Trace| LF
```

### Agent Workflow (StateGraph)

```mermaid
flowchart TD
    START((Start)) --> PN[Planner Node]

    PN -->|Scouting| PA[Plan Approval]
    PN -->|Chat| AN[Agent Node]

    PA -->|"HITL Gate 1"| AN

    AN -->|Tool Call| TN[Tool Node]
    AN -->|Save Request| CN[Compose Node]
    AN -->|Done| END((End))

    TN --> AN

    CN -->|Preview Ready| AP[Approval Node]

    AP -->|"HITL Gate 2"| AN

    style PA fill:#f9f,stroke:#333
    style AP fill:#f9f,stroke:#333
    style CN fill:#bbf,stroke:#333
```

### Real-Time Streaming

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as Django
    participant TW as Temporal
    participant RD as Redis

    FE->>API: POST /stream
    API->>TW: signal_with_start

    loop Each Node
        TW->>RD: PUBLISH events
        RD-->>FE: SSE (tokens/tasks)
    end

    TW->>RD: interrupt
    RD-->>FE: Show Approval UI
    FE->>API: POST /approve
    API->>TW: resume signal
    TW->>RD: final
    RD-->>FE: Done
```

See [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) for more diagrams.

**Core Stack:**
- **Frontend:** React 18 + Zustand + SSE streaming
- **Backend:** Django 5 + ASGI + REST
- **Orchestration:** Temporal (durable workflows, signal-based)
- **Agent Graph:** LangGraph StateGraph (6-node workflow)
- **Real-time:** Redis Pub/Sub with backpressure
- **Observability:** Langfuse v3 (per-user tracing)
- **Storage:** PostgreSQL + pgvector

**Key Design Decisions:**
- Temporal ensures workflow durability across failures
- Redis pub/sub enables real-time token streaming
- Two-gate HITL prevents unintended data persistence
- Per-user Langfuse isolation for multi-tenant tracing

---

## Security Considerations

- **API Key Isolation:** Per-user OpenAI/Langfuse credentials
- **Data Isolation:** All records filtered by `user_id`/`owner`
- **No Silent Actions:** Destructive operations require explicit approval
- **Input Validation:** Pydantic schemas on all API endpoints
- **Rate Limiting:** Concurrent stream limits per user

See [docs/security_check.md](./docs/security_check.md) for security audit notes.

---

## Tradeoffs

| Decision | Tradeoff |
|----------|----------|
| Temporal over simple queues | Added complexity, but gained durability + visibility |
| LangGraph over raw LangChain | Learning curve, but cleaner state management |
| Redis pub/sub over WebSocket | Simpler infra, but slightly higher latency |
| In-memory message buffer | Fast streaming, requires bulk persist on close |

---

## Future Improvements

- **Dynamic Sub-Agent Creation:** Spawn specialized agents (stats analyst, injury scout, transfer market) based on query type for faster, more robust scouting
- **Multi-Sport Support:** Extended schemas for NFL, NHL, MLB
- **Document Ingestion UI:** Upload scouting PDFs directly
- **Comparison Mode:** Side-by-side player analysis
- **Export Functionality:** PDF/CSV report generation
- **Webhook Integrations:** Notify external systems on report creation

---

## Project Structure

```
.
├── backend/
│   └── app/
│       ├── agents/          # LangGraph + Temporal workflows
│       │   ├── graph/       # StateGraph nodes, state, tools
│       │   └── temporal/    # Workflow definitions
│       ├── api/             # REST endpoints
│       ├── db/              # Django models
│       ├── rag/             # Retrieval pipeline
│       └── observability/   # Langfuse integration
├── frontend/
│   └── src/
│       ├── app/             # Pages
│       ├── components/      # UI components
│       ├── state/           # Zustand stores
│       └── lib/             # SSE streaming
├── docs/                    # Architecture diagrams
└── docker-compose.yml
```

---

## Services

| Service | Port | Purpose |
|---------|------|---------|
| Frontend | 3000 | React application |
| Backend | 8000 | Django API |
| Langfuse | 3001 | Observability UI |
| Temporal UI | 8080 | Workflow monitoring |
| PostgreSQL | 5432 | Primary database |
| Redis | 6379 | Pub/sub messaging |

---

## License

MIT
