# Part 1: Current State Analysis

## 1. Executive Summary

This document analyzes the current multi-agent platform architecture to identify components that will be reused, modified, or replaced during the migration to the new Agentic Scouting Report Flow.

---

## 2. Current Architecture Overview

### 2.1 Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | React 18 + Vite | Chat UI, document upload, real-time streaming |
| API | Django 5.0 | REST endpoints, authentication |
| Workflow | Temporal | Durable workflow orchestration, signals, activities |
| Agent Runtime | LangGraph Functional API | Agent execution, checkpointing, interrupts |
| Streaming | Redis pub/sub | Real-time event delivery via SSE |
| Vector Store | PostgreSQL + pgvector | Document embeddings, similarity search |
| Observability | Langfuse | Tracing, token usage, latency metrics |

### 2.2 Data Flow Diagram

```
User Request → Django API → Temporal Workflow → LangGraph Tasks → Agent Execution
                                    ↓
                             Redis pub/sub → SSE → Frontend
                                    ↓
                             PostgreSQL (checkpoints + vectors)
```

---

## 3. Component Inventory

### 3.1 Orchestration Layer

#### Temporal Workflow (`backend/app/agents/temporal/workflow.py`)

**Current Behavior:**
- Long-running workflow per chat session (`chat-{user_id}-{session_id}`)
- Signal-based: `new_message`, `resume`, `add_message_to_buffer`
- In-memory message buffering during session
- Bulk persistence on workflow close (5-min inactivity timeout)
- Deduplication via hash: `run_id > parent_message_id > content_hash`

**Key Signals:**
```python
@workflow.signal
def new_message(message, plan_steps, flow, run_id, parent_message_id)

@workflow.signal
def resume(resume_payload)
```

**Migration Relevance:** ✅ REUSABLE
- Signal pattern fits new HITL gates (Plan Approval, Create Player Approval)
- Resume mechanism aligns with edit/refine loop

---

#### Temporal Activity (`backend/app/agents/temporal/activity.py`)

**Current Behavior:**
- Executes `ai_agent_workflow_events()` async generator
- Publishes events to Redis with backpressure control
- Detects interrupt events for HITL
- Signals workflow to buffer messages

**Migration Relevance:** ✅ REUSABLE WITH MODIFICATIONS
- Event publishing pattern needed for new flow
- New event types required: `plan_proposal`, `player_preview`, `coverage_report`

---

### 3.2 Agent System

#### Supervisor Agent (`backend/app/agents/agents/supervisor.py`)

**Current Behavior:**
- Routes messages to: `greeter`, `search`, `gmail`, `config`, `process`
- Two routing strategies: keyword-based → structured output fallback
- Returns `RoutingDecision` with `agent`, `confidence`, `reasoning`

**Migration Relevance:** ⚠️ NEEDS EXTENSION
- New intent: `scouting_report` must be added
- New routing target: `scouting` flow (not a single agent, but a multi-step pipeline)

---

#### Agent Factory (`backend/app/agents/factory.py`)

**Current Registry:**
```python
AGENT_REGISTRY = {
    "greeter": GreeterAgent,
    "search": SearchAgent,
    "supervisor": SupervisorAgent,
    "planner": PlannerAgent,
}
```

**Migration Relevance:** ⚠️ NEEDS EXTENSION
- New conceptual "agents": Retriever, Extractor, Composer
- These are not standalone agents but specialized tasks within scouting flow
- Decision needed: Register as agents or implement as @task functions?

---

#### SearchAgent (`backend/app/agents/agents/search.py`)

**Current Behavior:**
- Uses `rag_retrieval_tool` to query vector store
- Token trimming if context exceeds 80%
- Returns context + citations

**Migration Relevance:** ✅ PARTIALLY REUSABLE
- RAG tool can be reused by Retriever
- Query diversification logic needs to be added (3-6 queries per player)

---

### 3.3 LangGraph Workflow

#### Entrypoint (`backend/app/agents/functional/workflow.py`)

**Current Flow:**
```
@entrypoint ai_agent_workflow()
├── route_to_agent() → RoutingDecision
├── execute_agent() → AgentResponse (may include tool_calls)
├── Check tools_requiring_approval
├── interrupt() if HITL needed
├── execute_tools() → ToolResults
├── refine_with_tool_results() → Final AgentResponse
└── Return response
```

**Migration Relevance:** ⚠️ SIGNIFICANT CHANGES NEEDED
- New flow has 9 nodes vs current ~4 nodes
- Two HITL gates vs current tool-approval only
- Loop structure for edit/refine cycles

---

#### Task Functions (`backend/app/agents/functional/tasks/`)

**Current Tasks:**
| Task | Input | Output |
|------|-------|--------|
| `route_to_agent` | messages, config | RoutingDecision |
| `execute_agent` | agent_name, messages | AgentResponse |
| `execute_tools` | tool_calls, agent_name | List[ToolResult] |
| `refine_with_tool_results` | agent_name, messages, results | AgentResponse |

**Migration Relevance:** ✅ PATTERN REUSABLE
- Same `@task` decorator pattern for new nodes
- New tasks needed: `build_queries`, `retrieve_evidence`, `extract_fields`, `compose_report`, etc.

---

### 3.4 RAG Pipeline

#### Query Pipeline (`backend/app/rag/pipelines/query_pipeline.py`)

**Current Behavior:**
```python
query_rag(user_id, query, top_k=30, top_n=8, document_ids, api_key)
├── Embed query (OpenAI text-embedding-3-small)
├── Vector search (pgvector, filtered by user_id)
├── Rerank (Cohere rerank-english-v3.0, optional)
└── Format context (markdown with citations)
```

**Migration Relevance:** ✅ REUSABLE WITH EXTENSION
- Core retrieval mechanism stays same
- Need: batch queries (3-6 per player), deduplication, chunk budget enforcement
- New output format: `EvidencePack` schema

---

#### Index Pipeline (`backend/app/rag/pipelines/index_pipeline.py`)

**Current Behavior:**
- Extract text (PDF/MD/TXT/DOCX with OCR)
- Chunk (recursive or semantic, 1000 tokens, 150 overlap)
- Embed chunks (OpenAI)
- Upsert to pgvector

**Migration Relevance:** ✅ NO CHANGES NEEDED
- Document indexing is upstream of scouting flow
- Existing indexed documents are the input source

---

### 3.5 Database Models

#### Chat Models (`backend/app/db/models/`)

| Model | Fields | Migration Relevance |
|-------|--------|---------------------|
| `ChatSession` | user, title, tokens_used, model_used, metadata | ✅ Keep for session tracking |
| `Message` | session, role, content, tokens_used, metadata | ✅ Keep for message history |

#### Document Models

| Model | Fields | Migration Relevance |
|-------|--------|---------------------|
| `Document` | owner, title, mime_type, status, chunks_count | ✅ Keep (source for RAG) |
| `DocumentChunk` | document, chunk_index, content, metadata | ✅ Keep (retrieval target) |
| `ChunkEmbedding` | chunk, embedding, embedding_model | ✅ Keep (vector storage) |

#### NEW Models Required (from agentic-schemas.md)

| Model | Purpose |
|-------|---------|
| `Player` | Structured player data (identity, physical, scouting fields) |
| `ScoutingReport` | Generated report linked to player |

---

### 3.6 Streaming & Events

#### EventCallbackHandler (`backend/app/agents/functional/streaming.py`)

**Current Event Types:**
```python
{"type": "token", "value": "..."}           # LLM streaming
{"type": "update", "data": {...}}           # Task lifecycle
{"type": "interrupt", "data": {...}}        # HITL pause
{"type": "final", "data": {...}}            # Complete response
{"type": "error", "data": {...}}            # Error condition
```

**Migration Relevance:** ⚠️ NEEDS EXTENSION
- New event types for scouting flow:
  - `plan_proposal` - Show plan for approval
  - `coverage_report` - What was found/missing
  - `player_preview` - Structured fields + report summary for approval
  - `report_draft` - Full report for review

---

## 4. Interrupt/HITL Mechanism Analysis

### 4.1 Current Implementation

**Location:** `backend/app/agents/functional/workflow.py`

```python
# Current: Tool approval only
if tools_requiring_approval:
    approval_decisions = interrupt({
        "type": "tool_approval",
        "tools": [...],
        "session_id": session_id
    })
```

**Resume Flow:**
1. Frontend receives `interrupt` event
2. User makes approval decisions
3. Frontend sends `resume_payload` to `/api/chat/{id}/resume/`
4. Temporal workflow receives `resume` signal
5. LangGraph `Command(resume=resume_payload)` continues execution

### 4.2 New HITL Requirements

| Gate | Trigger | User Options | Resume Action |
|------|---------|--------------|---------------|
| **Plan Approval** | After Node 2 (Draft Plan) | Approve / Edit plan | Update `plan_steps`, optionally `query_hints` |
| **Create Player Approval** | After Node 7 (Preview) | Approve / Reject / Edit | Write / Skip write / Re-run compose or full retrieval |

**Gap Analysis:**
- Current: Single interrupt type (`tool_approval`)
- New: Multiple interrupt types with different payloads and resume behaviors
- Need: Interrupt type routing in workflow

---

## 5. API Layer Analysis

### 5.1 Current Endpoints

```
POST   /api/chat/sessions/              - Create session
GET    /api/chat/sessions/{id}/stream/  - Stream response (SSE)
POST   /api/chat/sessions/{id}/resume/  - Resume interrupted workflow
```

### 5.2 New Endpoints Needed

| Endpoint | Purpose |
|----------|---------|
| `POST /api/players/` | Create player record (DB Writer) |
| `GET /api/players/{id}/` | Retrieve player with latest report |
| `GET /api/players/` | List players (optional, for future) |

**Note:** The One-Call Create API (`CreatePlayerWithReportRequest`) will be implemented as internal service, called by DB Writer task, not directly exposed.

---

## 6. Reuse Summary Matrix

| Component | Status | Notes |
|-----------|--------|-------|
| Temporal Workflow | ✅ Reuse | Add new signal types |
| Temporal Activity | ✅ Reuse | Add new event types |
| LangGraph @entrypoint | ⚠️ Extend | New flow with 9 nodes |
| LangGraph @task pattern | ✅ Reuse | Create new task functions |
| Supervisor routing | ⚠️ Extend | Add `scouting_report` intent |
| RAG query_pipeline | ⚠️ Extend | Multi-query, dedup, budget |
| RAG index_pipeline | ✅ Reuse | No changes |
| Redis pub/sub | ✅ Reuse | Add new event types |
| PostgreSQL checkpointing | ✅ Reuse | No changes |
| EventCallbackHandler | ⚠️ Extend | New event types |
| Chat models | ✅ Reuse | No changes |
| Document models | ✅ Reuse | No changes |
| Player/Report models | 🆕 New | Create per schema |

---

## 7. Questions Identified

### Q1: Integration Strategy
Should the scouting flow be:
- **Option A:** A new agent that Supervisor routes to (like SearchAgent)
- **Option B:** A separate workflow that bypasses Supervisor entirely
- **Option C:** A new "flow type" parameter that triggers specialized handling

### Q2: Agent vs Task Granularity
The concept document defines 5 "agents" (Supervisor, Retriever, Extractor, Composer, DB Writer). Should these be:
- **Option A:** Full Agent classes (like SearchAgent) with LLM + system prompt + tools
- **Option B:** LangGraph @task functions that internally use LLM calls
- **Option C:** Hybrid - some as Agents, some as tasks (e.g., DB Writer is non-LLM task)

### Q3: State Persistence Strategy
For the edit/refine loop (Node 7), how should intermediate state be persisted?
- **Option A:** Full checkpoint on every node (current approach)
- **Option B:** Checkpoint only at HITL gates
- **Option C:** In-memory during loop, checkpoint on approval

### Q4: Report Storage
Should scouting reports be stored:
- **Option A:** In `Message.metadata` (extends current model)
- **Option B:** In new `ScoutingReport` table (per schema)
- **Option C:** Both (for audit trail + structured access)

---

*End of Part 1*
