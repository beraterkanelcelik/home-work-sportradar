# Part 3: Migration Requirements & Design Decisions

## Confirmed Design Decisions Summary

| Decision | Choice |
|----------|--------|
| Integration | Supervisor routes to ScoutingAgent |
| Agent Implementation | LangGraph @task functions |
| Report Storage | New ScoutingReport table |
| Architecture | Keep Temporal + Redis |
| Edit Loop | Restart from Node 3 (build_queries) |
| Low Confidence | Warning only, user decides |
| Batch Mode | Single player only (MVP) |

---

## 1. Functional Requirements

### 1.1 Intent Detection (FR-01)

**Requirement:** System shall detect scouting report requests and route to scouting workflow.

**Acceptance Criteria:**
- Supervisor recognizes keywords: "scouting report", "scout", "player profile", "analyze player"
- Extracts player_name from request text using NLP
- Guesses sport from context (nba/football/unknown)
- If player_name cannot be extracted, interrupts for clarification

**Example Inputs:**
```
"Generate a scouting report for LeBron James"
→ intent: scouting_report, player_name: "LeBron James", sport_guess: "nba"

"Scout Patrick Mahomes strengths and weaknesses"
→ intent: scouting_report, player_name: "Patrick Mahomes", sport_guess: "football"

"Create a player analysis"
→ intent: scouting_report, player_name: null → interrupt for clarification
```

---

### 1.2 Plan Generation (FR-02)

**Requirement:** System shall generate a 4-7 step plan for user approval.

**Acceptance Criteria:**
- Plan steps are concrete and actionable
- Plan includes query_hints based on sport and context
- User can approve, edit steps, or add query_hints
- Edited plan is used for subsequent execution

**Default Plan Template:**
```
1. Confirm target player context from request
2. Retrieve relevant information from uploaded documents
3. Extract optional player fields (physical, scouting attributes)
4. Draft scouting report with findings
5. Prepare player database item preview
6. Request approval to save player item
7. Save player item and return results
```

---

### 1.3 Query Diversification (FR-03)

**Requirement:** System shall generate 3-6 diversified queries for retrieval.

**Acceptance Criteria:**
- Always includes:
  - `{player_name}` (exact name query)
  - `{player_name} strengths weaknesses` (scouting focus)
  - `{player_name} height weight position` (physical attributes)
- Conditionally includes sport-specific queries:
  - NBA: `{player_name} shooting percentage`, `{player_name} defensive rating`
  - Football: `{player_name} passing yards`, `{player_name} completion rate`
- Incorporates user-provided query_hints
- Deduplicates similar queries

---

### 1.4 Evidence Retrieval (FR-04)

**Requirement:** System shall retrieve and deduplicate chunks with strict budget.

**Acceptance Criteria:**
- Executes vector search for each query (existing RAG pipeline)
- Deduplicates chunks by:
  - Primary: `doc_id + chunk_id` combination
  - Fallback: normalized text hash (for cross-document dedup)
- Enforces hard cap: **max 40 chunks** to downstream
- Produces coverage report: `{found: [...], missing: [...]}`
- Assigns confidence: low (< 30%), med (30-70%), high (> 70%)

**Confidence Calculation:**
```python
expected_fields = ["positions", "teams", "height", "weight", "strengths", "weaknesses"]
found_count = count_fields_with_evidence(chunks, expected_fields)
confidence = found_count / len(expected_fields)
```

---

### 1.5 Structured Extraction (FR-05)

**Requirement:** System shall extract structured fields from retrieved chunks.

**Acceptance Criteria:**
- Produces `raw_facts[]`: atomic bullet points from evidence
- Produces `player_fields{}`: structured data per PlayerFields schema
- Omits fields not supported by evidence (no hallucination)
- Carries forward coverage metadata

**PlayerFields Schema (extract only supported):**
```python
{
    "display_name": "LeBron James",      # Required
    "sport": "nba",                       # Required
    "positions": ["SF", "PF"],            # Optional
    "teams": ["LAL", "CLE", "MIA"],       # Optional
    "league": "NBA",                      # Optional
    "physical": {
        "height_cm": 206,
        "weight_kg": 113
    },
    "scouting": {
        "strengths": ["Court vision", "Playmaking", "Durability"],
        "weaknesses": ["Free throw shooting", "3PT consistency"],
        "style_tags": ["Point forward", "Transition leader"],
        "role_projection": "Elite playmaker, can lead any offensive system"
    }
}
```

---

### 1.6 Report Composition (FR-06)

**Requirement:** System shall generate a sport-agnostic scouting report.

**Acceptance Criteria:**
- Uses template with flexible sections:
  - **Snapshot:** 3-5 bullet summary
  - **Strengths:** Evidence-backed bullets
  - **Weaknesses/Limitations:** Evidence-backed bullets
  - **Play Style & Tendencies:** Short narrative
  - **Role Projection:** Short narrative
  - **Development Focus:** Improvement areas
  - **Risk Notes:** Optional, if evidence supports
  - **What I Couldn't Find:** From coverage.missing
- Tolerates missing information gracefully
- Cites source documents where possible

---

### 1.7 HITL Plan Approval (FR-07)

**Requirement:** System shall pause for plan approval before retrieval.

**Acceptance Criteria:**
- Displays: player_name, sport_guess, plan_steps[], query_hints[]
- User options:
  - **Approve:** Proceed with plan as-is
  - **Edit:** Modify plan_steps and/or query_hints
- Edited values are used in subsequent nodes
- Timeout: Configurable (default: no timeout, wait indefinitely)

---

### 1.8 HITL Player Approval (FR-08)

**Requirement:** System shall pause for player item approval before database write.

**Acceptance Criteria:**
- Displays:
  - Structured `player_fields` (collapsible card)
  - `report_summary[]` (5-8 bullets)
  - Full `report_text` (expandable)
- User options:
  - **Approve:** Create player item in database
  - **Reject:** Skip database write, return report only
  - **Edit Wording:** Re-run compose_report (Node 6) only
  - **Edit Content:** Re-run from build_queries (Node 3) with feedback
- Edit feedback is passed to re-run nodes

---

### 1.9 Database Write (FR-09)

**Requirement:** System shall create player and report in single transaction.

**Acceptance Criteria:**
- Atomic transaction:
  1. INSERT into `players`
  2. INSERT into `scouting_reports` with `player_id`
  3. UPDATE `players.latest_report_id`
- Returns `player_record_id` and `report_id`
- On failure: rolls back, returns error
- MVP: Always creates new player (no existence check)

---

### 1.10 Response Assembly (FR-10)

**Requirement:** System shall return complete response with status.

**Acceptance Criteria:**
- Response includes:
  - `scouting_report`: Full report text
  - `player_record_id`: If saved (null if rejected)
  - `report_id`: If saved (null if rejected)
  - `saved`: Boolean status
  - `coverage`: What was found/missing
- Streamed to frontend via existing Redis pub/sub

---

## 2. Non-Functional Requirements

### 2.1 Performance (NFR-01)

| Metric | Target | Rationale |
|--------|--------|-----------|
| Query build time | < 2s | LLM call for query generation |
| Retrieval time | < 5s | Multi-query vector search |
| Extraction time | < 10s | LLM structured extraction |
| Composition time | < 15s | LLM report generation |
| Total E2E (no edits) | < 60s | User experience |
| Edit loop iteration | < 30s | Re-run subset of nodes |

### 2.2 Reliability (NFR-02)

| Requirement | Implementation |
|-------------|----------------|
| Checkpoint recovery | LangGraph PostgreSQL checkpointer saves state at each node |
| Timeout handling | Temporal activity timeout: 5 minutes per activity |
| Retry policy | 3 retries with exponential backoff for transient failures |
| Graceful degradation | If reranker unavailable, fallback to vector-only retrieval |

### 2.3 Observability (NFR-03)

| Trace Point | Metadata |
|-------------|----------|
| `scouting_workflow_start` | player_name, sport_guess, session_id |
| `plan_generated` | plan_steps count, query_hints count |
| `queries_built` | query count, diversification score |
| `evidence_retrieved` | chunk count, coverage, confidence |
| `fields_extracted` | field count, raw_facts count |
| `report_composed` | section count, word count |
| `player_created` | player_id, report_id |

### 2.4 Scalability (NFR-04)

| Constraint | Value | Rationale |
|------------|-------|-----------|
| Max queries per request | 6 | Prevent excessive API calls |
| Max chunks to extraction | 40 | LLM context limit, speed |
| Max report length | 2000 words | Readability, token cost |
| Max concurrent scouting flows | 10 per user | Resource protection |

---

## 3. Technical Specifications

### 3.1 New Files to Create

```
backend/app/agents/
├── agents/
│   └── scouting.py              # ScoutingAgent class
├── functional/
│   ├── scouting_workflow.py     # @entrypoint for scouting flow
│   └── tasks/
│       ├── scouting/
│       │   ├── __init__.py
│       │   ├── intake.py        # intake_and_route_scouting
│       │   ├── plan.py          # draft_plan
│       │   ├── queries.py       # build_queries
│       │   ├── retrieval.py     # retrieve_evidence
│       │   ├── extraction.py    # extract_fields
│       │   ├── composition.py   # compose_report
│       │   ├── preview.py       # prepare_preview
│       │   ├── write.py         # write_player_item
│       │   └── response.py      # build_final_response
│       └── ...

backend/app/db/models/
├── player.py                     # Player model
└── scouting_report.py            # ScoutingReport model

backend/app/services/
├── player_service.py             # PlayerService
└── scouting_report_service.py    # ScoutingReportService

backend/app/schemas/
└── scouting/
    ├── __init__.py
    ├── player_fields.py          # PlayerFields Pydantic model
    ├── evidence_pack.py          # EvidencePack Pydantic model
    ├── report_draft.py           # ScoutingReportDraft Pydantic model
    └── workflow_state.py         # ScoutingWorkflowState dataclass
```

### 3.2 Files to Modify

```
backend/app/agents/
├── agents/
│   └── supervisor.py             # Add "scouting" routing target
├── factory.py                    # Register ScoutingAgent
├── functional/
│   └── workflow.py               # Add scouting workflow dispatch
│   └── streaming.py              # Add new event types

backend/app/rag/pipelines/
└── query_pipeline.py             # Add batch query support, dedup

backend/app/db/models/
└── __init__.py                   # Export new models

backend/app/api/
└── chats.py                      # Handle new interrupt types in resume
```

### 3.3 Database Migrations

```python
# Migration: 0001_create_player_model.py
operations = [
    migrations.CreateModel(
        name='Player',
        fields=[
            ('id', models.UUIDField(primary_key=True, default=uuid.uuid4)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('owner', models.ForeignKey('auth.User', on_delete=models.CASCADE)),
            ('display_name', models.TextField()),
            ('sport', models.CharField(max_length=20)),
            # ... all fields from schema
        ],
    ),
    migrations.AddIndex(
        model_name='player',
        index=models.Index(fields=['sport'], name='players_sport_idx'),
    ),
    migrations.AddIndex(
        model_name='player',
        index=models.Index(fields=['display_name'], name='players_display_name_idx'),
    ),
]

# Migration: 0002_create_scouting_report_model.py
operations = [
    migrations.CreateModel(
        name='ScoutingReport',
        fields=[
            ('id', models.UUIDField(primary_key=True, default=uuid.uuid4)),
            ('player', models.ForeignKey('Player', on_delete=models.CASCADE)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('run_id', models.CharField(max_length=255, null=True)),
            ('request_text', models.TextField(null=True)),
            ('report_text', models.TextField()),
            ('report_summary', models.JSONField(null=True)),
            ('coverage', models.JSONField(null=True)),
            ('source_doc_ids', models.JSONField(null=True)),
        ],
    ),
    migrations.AddField(
        model_name='player',
        name='latest_report',
        field=models.ForeignKey('ScoutingReport', null=True, on_delete=models.SET_NULL),
    ),
]
```

---

## 4. API Contracts

### 4.1 Existing Endpoint Modifications

#### POST /api/chat/{session_id}/resume/

**Current Payload:**
```json
{
  "type": "tool_approval",
  "decisions": [{"tool_call_id": "...", "approved": true}]
}
```

**Extended Payload:**
```json
{
  "type": "plan_approval",
  "approved": true,
  "plan_steps": ["..."],
  "query_hints": ["..."]
}
```

```json
{
  "type": "player_approval",
  "action": "approve" | "reject" | "edit_wording" | "edit_content",
  "feedback": "Optional feedback for edit actions"
}
```

### 4.2 New Event Types (SSE)

#### plan_proposal Event
```json
{
  "type": "plan_proposal",
  "data": {
    "player_name": "LeBron James",
    "sport_guess": "nba",
    "plan_steps": ["Step 1...", "Step 2..."],
    "query_hints": ["playoff performance", "leadership"]
  }
}
```

#### coverage_report Event
```json
{
  "type": "coverage_report",
  "data": {
    "found": ["positions", "teams", "strengths"],
    "missing": ["height", "weight", "draft_position"],
    "confidence": "med",
    "chunk_count": 28
  }
}
```

#### player_preview Event
```json
{
  "type": "player_preview",
  "data": {
    "player_fields": {
      "display_name": "LeBron James",
      "sport": "nba",
      "positions": ["SF", "PF"],
      "scouting": {
        "strengths": ["Playmaking", "Court vision"],
        "weaknesses": ["3PT consistency"]
      }
    },
    "report_summary": [
      "Elite playmaker with exceptional court vision",
      "Can play multiple positions effectively",
      "..."
    ],
    "report_text": "Full report text...",
    "db_payload_preview": {...}
  }
}
```

---

## 5. Error Handling

### 5.1 Error Categories

| Error Type | Handling | User Message |
|------------|----------|--------------|
| Player name extraction failed | Interrupt for clarification | "I couldn't identify the player name. Please specify." |
| No documents found | Warning, proceed | "No uploaded documents found. Report based on limited info." |
| Low confidence (< 30%) | Warning in coverage | "Limited information found. Consider uploading more documents." |
| LLM timeout | Retry 3x, then fail | "Report generation timed out. Please try again." |
| Database write failed | Rollback, return report | "Couldn't save player. Report returned without saving." |

### 5.2 Retry Policy

```python
RETRY_POLICY = {
    "max_attempts": 3,
    "initial_interval": timedelta(seconds=1),
    "maximum_interval": timedelta(seconds=10),
    "backoff_coefficient": 2,
    "non_retryable_errors": [
        "PlayerNameNotFound",
        "UserCancelled"
    ]
}
```

---

## 6. Testing Requirements

### 6.1 Unit Tests

| Test | Coverage |
|------|----------|
| `test_intake_extracts_player_name` | Various request formats |
| `test_plan_generation_length` | 4-7 steps enforced |
| `test_query_diversification` | Required queries present |
| `test_chunk_deduplication` | No duplicates in output |
| `test_chunk_budget_enforced` | Max 40 chunks |
| `test_extraction_omits_unknown` | No hallucinated fields |
| `test_report_sections_present` | Template compliance |
| `test_atomic_transaction` | Rollback on partial failure |

### 6.2 Integration Tests

| Test | Scenario |
|------|----------|
| `test_full_scouting_flow_approve` | User approves at both gates |
| `test_full_scouting_flow_reject` | User rejects at Gate B |
| `test_edit_wording_loop` | User edits wording, re-compose |
| `test_edit_content_loop` | User edits content, re-retrieve |
| `test_low_confidence_warning` | Warning shown, proceed works |
| `test_interrupt_resume` | Checkpoint restore works |

### 6.3 E2E Tests

| Test | Scenario |
|------|----------|
| `test_scouting_ui_flow` | Full UI interaction |
| `test_scouting_streaming` | Events reach frontend |
| `test_scouting_with_real_docs` | Actual document retrieval |

---

## 7. Security Considerations

### 7.1 Multi-Tenancy

- All queries MUST filter by `owner_id` / `user_id`
- Player records linked to owner (cannot access other users' players)
- RAG retrieval limited to user's documents

### 7.2 Input Validation

- Player name: Max 200 characters, sanitized
- Query hints: Max 10 hints, max 100 chars each
- Feedback text: Max 1000 characters
- Plan steps: Max 10 steps, max 500 chars each

### 7.3 Rate Limiting

- Max 10 scouting requests per user per hour
- Max 3 concurrent scouting workflows per user

---

*End of Part 3*
