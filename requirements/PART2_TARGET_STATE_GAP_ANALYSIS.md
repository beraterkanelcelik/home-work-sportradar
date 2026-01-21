# Part 2: Target State & Gap Analysis

## Design Decisions (Confirmed)

Based on stakeholder input, the following architectural decisions are finalized:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Integration Strategy | New routed agent | Supervisor routes `scouting_report` intent to ScoutingAgent |
| Agent Implementation | LangGraph @task functions | Simpler, matches current pattern, internal LLM calls |
| Report Storage | New ScoutingReport table | Dedicated table per schema, structured queries, player history |
| Architecture | Keep Temporal + Redis | Proven, HITL support, streaming works |

---

## 1. Target State Architecture

### 1.1 High-Level Flow

```
User: "Generate a scouting report for LeBron James"
                    ↓
            Django API (existing)
                    ↓
            Temporal Workflow (existing)
                    ↓
            LangGraph @entrypoint
                    ↓
        ┌───────────────────────┐
        │   route_to_agent()    │ → Supervisor detects intent: "scouting_report"
        └───────────────────────┘
                    ↓
        ┌───────────────────────┐
        │  scouting_workflow()  │ → New sub-workflow with 9 nodes
        └───────────────────────┘
                    ↓
            [Node 1-9 execution with 2 HITL gates]
                    ↓
            Player record + ScoutingReport created
                    ↓
            Response streamed via Redis pub/sub
```

### 1.2 New Scouting Workflow (9 Nodes)

```
Node 1: intake_and_route
├── Input: user request text
├── Output: intent, player_name, sport_guess
├── Interrupt: if player_name missing → clarification request
└── Task type: @task with LLM

Node 2: draft_plan
├── Input: player_name, sport_guess
├── Output: plan_steps[] (4-7 steps), query_hints[]
└── Task type: @task with LLM

    ┌─── HITL Gate A: Plan Approval ───┐
    │ User approves/edits plan         │
    │ Resume: updated plan_steps       │
    └──────────────────────────────────┘

Node 3: build_queries
├── Input: player_name, sport_guess, query_hints
├── Output: queries[] (3-6 diversified)
├── Rules:
│   - Always: {player_name}
│   - Always: {player_name} strengths weaknesses
│   - Always: {player_name} height weight position
│   - Optional: sport-specific queries
└── Task type: @task with LLM (query generation)

Node 4: retrieve_evidence
├── Input: queries[]
├── Output: EvidencePack {queries, chunks[], coverage, confidence}
├── Rules:
│   - Run vector search for each query
│   - Deduplicate by doc_id + chunk_id or text hash
│   - Enforce chunk budget (max 40)
└── Task type: @task (non-LLM, calls RAG pipeline)

Node 5: extract_fields
├── Input: chunks[]
├── Output: player_fields{}, raw_facts[], coverage
├── Rules:
│   - Extract atomic facts from chunks
│   - Map to PlayerFields schema (omit unknown)
│   - Track coverage (found vs missing)
└── Task type: @task with LLM (structured extraction)

Node 6: compose_report
├── Input: raw_facts[], player_fields{}, coverage
├── Output: ScoutingReportDraft {report_text, report_summary[], db_payload_preview}
├── Template sections:
│   - Snapshot (3-5 bullets)
│   - Strengths (bullets)
│   - Weaknesses/limitations (bullets)
│   - Play style & tendencies
│   - Role projection
│   - Development focus (bullets)
│   - Risk notes (optional)
│   - What I couldn't find (from coverage)
└── Task type: @task with LLM (composition)

Node 7: preview_and_approval
├── Input: db_payload_preview
├── Show: player_fields, report_summary, full report (expandable)
└── Task type: @task (non-LLM, prepares interrupt)

    ┌─── HITL Gate B: Create Player Item? ───┐
    │ Options:                                │
    │   - Approved → proceed to Node 8        │
    │   - Rejected → skip Node 8, return report│
    │   - Edit (wording) → re-run Node 6 only │
    │   - Edit (content) → re-run Nodes 3-6   │
    └─────────────────────────────────────────┘

Node 8: write_player_item
├── Input: db_payload_preview
├── Output: player_record_id, report_id
├── Action: Create Player + ScoutingReport in single transaction
└── Task type: @task (non-LLM, DB operation)

Node 9: final_response
├── Input: scouting_report, player_record_id, saved_status
├── Output: AgentResponse with full report and metadata
└── Task type: @task (non-LLM, response assembly)
```

---

## 2. Data Model Changes

### 2.1 New Models (DDL from agentic-schemas.md)

#### Players Table

```sql
CREATE TABLE players (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Identity (required)
  display_name      TEXT NOT NULL,
  sport             TEXT NOT NULL CHECK (sport IN ('nba','football','unknown')),

  -- Identity (optional)
  positions         JSONB NULL,   -- ["SG","SF"] or ["QB"]
  teams             JSONB NULL,   -- ["LAL"] or ["KC Chiefs"]
  league            TEXT NULL,    -- "NBA", "NFL"
  aliases           JSONB NULL,   -- ["Steph Curry", "Wardell Curry"]

  -- Physical (optional)
  height_cm         INTEGER NULL CHECK (height_cm BETWEEN 80 AND 260),
  weight_kg         INTEGER NULL CHECK (weight_kg BETWEEN 30 AND 200),
  measurements      JSONB NULL,   -- {"wingspan_cm":208}

  -- Scouting (optional)
  strengths         JSONB NULL,
  weaknesses        JSONB NULL,
  style_tags        JSONB NULL,   -- ["3PT shooter","POA defender"]
  risk_notes        JSONB NULL,
  role_projection   TEXT NULL,

  -- Latest report link
  latest_report_id  UUID NULL
);

CREATE INDEX players_sport_idx ON players (sport);
CREATE INDEX players_display_name_idx ON players (display_name);
```

#### Scouting Reports Table

```sql
CREATE TABLE scouting_reports (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id         UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

  run_id            TEXT NULL,     -- workflow/run correlation
  request_text      TEXT NULL,     -- original user request

  report_text       TEXT NOT NULL,
  report_summary    JSONB NULL,    -- ["bullet1","bullet2",...]
  coverage          JSONB NULL,    -- {"found":[...], "missing":[...]}
  source_doc_ids    JSONB NULL     -- ["doc_a","doc_b"]
);

CREATE INDEX scouting_reports_player_id_idx ON scouting_reports (player_id);
CREATE INDEX scouting_reports_created_at_idx ON scouting_reports (created_at);
```

### 2.2 Django Model Equivalents

```python
# backend/app/db/models/player.py

class Player(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Owner for multi-tenancy
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='players')

    # Identity
    display_name = models.TextField()
    sport = models.CharField(max_length=20, choices=[
        ('nba', 'NBA'),
        ('football', 'Football'),
        ('unknown', 'Unknown')
    ])
    positions = models.JSONField(null=True, blank=True)
    teams = models.JSONField(null=True, blank=True)
    league = models.CharField(max_length=50, null=True, blank=True)
    aliases = models.JSONField(null=True, blank=True)

    # Physical
    height_cm = models.IntegerField(null=True, blank=True)
    weight_kg = models.IntegerField(null=True, blank=True)
    measurements = models.JSONField(null=True, blank=True)

    # Scouting
    strengths = models.JSONField(null=True, blank=True)
    weaknesses = models.JSONField(null=True, blank=True)
    style_tags = models.JSONField(null=True, blank=True)
    risk_notes = models.JSONField(null=True, blank=True)
    role_projection = models.TextField(null=True, blank=True)

    # Latest report
    latest_report = models.ForeignKey(
        'ScoutingReport',
        on_delete=models.SET_NULL,
        null=True,
        related_name='+'
    )


class ScoutingReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='scouting_reports')
    created_at = models.DateTimeField(auto_now_add=True)

    run_id = models.CharField(max_length=255, null=True, blank=True)
    request_text = models.TextField(null=True, blank=True)

    report_text = models.TextField()
    report_summary = models.JSONField(null=True, blank=True)
    coverage = models.JSONField(null=True, blank=True)
    source_doc_ids = models.JSONField(null=True, blank=True)
```

---

## 3. Schema Contracts (JSON Schemas)

### 3.1 Workflow State Schema

```python
@dataclass
class ScoutingWorkflowState:
    """State passed between nodes in scouting workflow"""

    # From Node 1
    intent: str
    player_name: str
    sport_guess: Literal["nba", "football", "unknown"]

    # From Node 2
    plan_steps: List[str]
    query_hints: List[str]

    # From Node 3
    queries: List[str]

    # From Node 4
    evidence_pack: EvidencePack

    # From Node 5
    player_fields: PlayerFields
    raw_facts: List[str]
    coverage: Coverage

    # From Node 6
    report_draft: ScoutingReportDraft

    # From Node 8
    player_record_id: Optional[str]
    report_id: Optional[str]
    saved: bool
```

### 3.2 Inter-Node Contracts (from agentic-schemas.md)

| Schema | Producer Node | Consumer Nodes |
|--------|---------------|----------------|
| `EvidencePack` | Node 4 (retrieve_evidence) | Node 5 (extract_fields) |
| `PlayerFields` | Node 5 (extract_fields) | Node 6 (compose_report), Node 8 (write) |
| `ScoutingReportDraft` | Node 6 (compose_report) | Node 7 (preview), Node 8 (write) |
| `CreatePlayerWithReportRequest` | Node 7 (preview) | Node 8 (write) |
| `CreatePlayerWithReportResponse` | Node 8 (write) | Node 9 (final_response) |

---

## 4. Gap Analysis

### 4.1 Orchestration Gaps

| Current | Gap | Target |
|---------|-----|--------|
| Single routing decision | Need sub-workflow dispatch | Supervisor → ScoutingAgent → scouting_workflow |
| Single interrupt type | Need typed interrupts | `plan_approval`, `player_approval` with different payloads |
| Linear flow | Need conditional loops | Edit feedback → re-run compose-only or full retrieval |
| Tool approval only | Need approval for generated content | Plan approval, player preview approval |

### 4.2 RAG Pipeline Gaps

| Current | Gap | Target |
|---------|-----|--------|
| Single query per request | Need multi-query (3-6) | build_queries task with diversification |
| Return all matching chunks | Need deduplication | Dedup by doc_id+chunk_id or text hash |
| No chunk budget | Need hard cap | Max 40 chunks to downstream |
| Format for chat context | Need EvidencePack schema | Structured output with coverage/confidence |

### 4.3 Agent System Gaps

| Current | Gap | Target |
|---------|-----|--------|
| Supervisor routes to agents | Need "scouting_report" intent | Extend RoutingDecision with new intent |
| Agents are standalone | Need orchestrated flow | ScoutingAgent delegates to scouting_workflow |
| No Extractor capability | Need structured extraction | extract_fields task with LLM |
| No Composer capability | Need report composition | compose_report task with LLM |

### 4.4 Database Gaps

| Current | Gap | Target |
|---------|-----|--------|
| No Player model | Need Player table | Create with identity, physical, scouting fields |
| No ScoutingReport model | Need ScoutingReport table | Create linked to Player |
| No one-call create | Need atomic transaction | Service method: create player + report + link |

### 4.5 Streaming/Events Gaps

| Current | Gap | Target |
|---------|-----|--------|
| Event types: token, update, interrupt, final | Need new types | plan_proposal, coverage_report, player_preview, report_draft |
| Single interrupt handler | Need typed interrupt routing | Frontend routes based on interrupt.type |

---

## 5. New Components Required

### 5.1 New Task Functions

| Task | Purpose | LLM? |
|------|---------|------|
| `intake_and_route_scouting` | Parse request, extract player_name, sport_guess | Yes |
| `draft_plan` | Generate 4-7 step plan | Yes |
| `build_queries` | Generate 3-6 diversified queries | Yes |
| `retrieve_evidence` | Run multi-query RAG, dedupe, budget | No |
| `extract_fields` | Extract raw_facts, player_fields from chunks | Yes |
| `compose_report` | Generate scouting report from facts | Yes |
| `prepare_preview` | Format db_payload_preview for approval | No |
| `write_player_item` | Create Player + ScoutingReport atomically | No |
| `build_final_response` | Assemble AgentResponse | No |

### 5.2 New Agent

| Agent | Purpose |
|-------|---------|
| `ScoutingAgent` | Entry point for scouting flow, orchestrates scouting_workflow |

### 5.3 New Services

| Service | Purpose |
|---------|---------|
| `PlayerService` | CRUD operations for Player model |
| `ScoutingReportService` | CRUD + create_with_player transaction |

### 5.4 New Event Types

| Event Type | Payload | UI Action |
|------------|---------|-----------|
| `plan_proposal` | {plan_steps[], player_name, sport_guess} | Show approval UI with editable plan |
| `coverage_report` | {found[], missing[], confidence} | Display in sidebar/expandable |
| `player_preview` | {player_fields, report_summary[]} | Show structured preview card |
| `report_draft` | {report_text, expandable: true} | Show full report in expandable section |

---

## 6. Integration Points

### 6.1 Supervisor Extension

```python
# Current routing targets
ROUTING_TARGETS = ["greeter", "search", "gmail", "config", "process"]

# New routing target
ROUTING_TARGETS = ["greeter", "search", "gmail", "config", "process", "scouting"]

# New intent detection keywords
SCOUTING_KEYWORDS = [
    "scouting report",
    "scout",
    "player profile",
    "analyze player",
    "player analysis",
    "player strengths",
    "player weaknesses"
]
```

### 6.2 Workflow Entrypoint Extension

```python
@entrypoint(checkpointer=postgres_checkpointer)
def ai_agent_workflow(request: AgentRequest | Command) -> AgentResponse:
    # ... existing setup ...

    routing_decision = route_to_agent(messages, config, api_key).result()

    if routing_decision.agent == "scouting":
        # Delegate to scouting sub-workflow
        return scouting_workflow(
            request=request,
            player_name=routing_decision.metadata.get("player_name"),
            sport_guess=routing_decision.metadata.get("sport_guess"),
            config=config
        )
    else:
        # Existing agent execution path
        response = execute_agent(routing_decision.agent, messages, ...).result()
        # ...
```

### 6.3 HITL Gate Integration

```python
# Plan Approval (Gate A)
def draft_plan(...) -> PlanProposal:
    # ... generate plan ...

    # Interrupt for approval
    approval = interrupt({
        "type": "plan_approval",
        "plan_steps": plan_steps,
        "query_hints": query_hints,
        "player_name": player_name,
        "sport_guess": sport_guess
    })

    # Resume with updated plan
    if approval.get("edited"):
        return PlanProposal(
            plan_steps=approval["plan_steps"],
            query_hints=approval.get("query_hints", query_hints)
        )
    return PlanProposal(plan_steps=plan_steps, query_hints=query_hints)
```

```python
# Player Approval (Gate B)
def preview_and_approval(...) -> ApprovalDecision:
    # Interrupt for approval
    decision = interrupt({
        "type": "player_approval",
        "player_fields": player_fields,
        "report_summary": report_summary,
        "report_text": report_text,
        "db_payload_preview": db_payload_preview
    })

    return ApprovalDecision(
        action=decision["action"],  # "approve" | "reject" | "edit_wording" | "edit_content"
        feedback=decision.get("feedback")
    )
```

---

## 7. Questions for Next Phase

### Q5: Edit Loop Boundaries
When user requests "edit content" (requiring re-retrieval), should we:
- **Option A:** Re-run from Node 3 (build_queries) with updated query_hints
- **Option B:** Re-run from Node 4 (retrieve_evidence) with same queries but new focus
- **Option C:** Let user specify which nodes to re-run

### Q6: Coverage Confidence Thresholds
What thresholds should trigger warnings?
- **Low confidence:** < 30% of expected fields found
- **Medium confidence:** 30-70% of expected fields found
- **High confidence:** > 70% of expected fields found

Should low confidence automatically suggest re-retrieval?

### Q7: Player Deduplication (Future)
MVP creates new player each time. For future:
- How should we handle existing players?
- Match by display_name + sport? Aliases?
- Upsert vs create new version?

---

*End of Part 2*
