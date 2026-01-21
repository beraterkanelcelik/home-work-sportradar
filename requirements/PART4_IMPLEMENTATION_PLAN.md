# Part 4: Implementation Plan

## Final Design Decisions Summary

| Decision | Choice |
|----------|--------|
| Integration | Supervisor routes to ScoutingAgent |
| Agent Implementation | LangGraph @task functions |
| Report Storage | New ScoutingReport table |
| Architecture | Keep Temporal + Redis |
| Edit Loop | Restart from Node 3 (build_queries) |
| Low Confidence | Warning only |
| Batch Mode | Single player only (MVP) |
| HITL Gates | Both required for MVP |
| No Documents | Block and prompt upload |

---

## 1. Implementation Phases

### Phase 1: Foundation Layer

**Goal:** Create database models, services, and Pydantic schemas.

**Tasks:**
```
1.1 Create Player Django model
    - File: backend/app/db/models/player.py
    - Fields: identity, physical, scouting per schema
    - Indexes: sport, display_name, owner
    - Multi-tenancy: owner FK to User

1.2 Create ScoutingReport Django model
    - File: backend/app/db/models/scouting_report.py
    - Fields: player FK, report_text, report_summary, coverage, source_doc_ids
    - Index: player_id, created_at

1.3 Create database migrations
    - Run: make makemigrations
    - Run: make migrate
    - Verify: Tables created with correct constraints

1.4 Create Pydantic schemas
    - File: backend/app/schemas/scouting/player_fields.py
    - File: backend/app/schemas/scouting/evidence_pack.py
    - File: backend/app/schemas/scouting/report_draft.py
    - File: backend/app/schemas/scouting/workflow_state.py

1.5 Create PlayerService
    - File: backend/app/services/player_service.py
    - Methods: create, get_by_id, list_by_owner

1.6 Create ScoutingReportService
    - File: backend/app/services/scouting_report_service.py
    - Methods: create_with_player (atomic transaction)
```

**Dependencies:** None

**Verification:**
```bash
# Test models
docker-compose exec backend python manage.py shell
>>> from app.db.models import Player, ScoutingReport
>>> Player.objects.create(owner=user, display_name="Test", sport="nba")

# Test service
>>> from app.services.player_service import PlayerService
>>> PlayerService.create(owner=user, display_name="Test", sport="nba")
```

---

### Phase 2: RAG Pipeline Extension

**Goal:** Add multi-query support, deduplication, and EvidencePack output.

**Tasks:**
```
2.1 Create batch query function
    - File: backend/app/rag/pipelines/query_pipeline.py
    - Function: query_rag_batch(user_id, queries[], top_k, api_key)
    - Runs vector search for each query
    - Returns combined results

2.2 Add deduplication logic
    - Function: deduplicate_chunks(chunks[])
    - Primary key: (doc_id, chunk_id)
    - Fallback: normalized text hash
    - Returns unique chunks

2.3 Add chunk budget enforcement
    - Parameter: max_chunks=40
    - Sort by score, take top N
    - Truncate excess

2.4 Add EvidencePack output format
    - Convert results to EvidencePack schema
    - Include queries[], chunks[], coverage, confidence

2.5 Add coverage calculation
    - Function: calculate_coverage(chunks, expected_fields)
    - Returns: {found: [], missing: [], confidence: "low"|"med"|"high"}
```

**Dependencies:** Phase 1 (schemas)

**Verification:**
```python
from app.rag.pipelines.query_pipeline import query_rag_batch

queries = ["LeBron James", "LeBron James strengths", "LeBron James height"]
result = query_rag_batch(user_id, queries, top_k=30, api_key=key)

assert len(result.chunks) <= 40
assert result.confidence in ["low", "med", "high"]
```

---

### Phase 3: Scouting Task Functions

**Goal:** Implement all 9 nodes as @task functions.

**Tasks:**
```
3.1 intake_and_route_scouting task
    - File: backend/app/agents/functional/tasks/scouting/intake.py
    - Input: user request text
    - Output: intent, player_name, sport_guess
    - Uses LLM for extraction
    - Returns error if player_name not found

3.2 draft_plan task
    - File: backend/app/agents/functional/tasks/scouting/plan.py
    - Input: player_name, sport_guess
    - Output: plan_steps[], query_hints[]
    - Uses LLM with plan template
    - Enforces 4-7 steps

3.3 build_queries task
    - File: backend/app/agents/functional/tasks/scouting/queries.py
    - Input: player_name, sport_guess, query_hints
    - Output: queries[] (3-6)
    - Uses LLM for diversification
    - Always includes required queries

3.4 retrieve_evidence task
    - File: backend/app/agents/functional/tasks/scouting/retrieval.py
    - Input: user_id, queries[]
    - Output: EvidencePack
    - Calls query_rag_batch
    - Non-LLM task

3.5 extract_fields task
    - File: backend/app/agents/functional/tasks/scouting/extraction.py
    - Input: chunks[]
    - Output: player_fields{}, raw_facts[], coverage
    - Uses LLM for structured extraction
    - Schema-validated output

3.6 compose_report task
    - File: backend/app/agents/functional/tasks/scouting/composition.py
    - Input: raw_facts[], player_fields{}, coverage
    - Output: ScoutingReportDraft
    - Uses LLM with report template
    - Includes all sections

3.7 prepare_preview task
    - File: backend/app/agents/functional/tasks/scouting/preview.py
    - Input: ScoutingReportDraft
    - Output: db_payload_preview
    - Non-LLM task
    - Formats for approval UI

3.8 write_player_item task
    - File: backend/app/agents/functional/tasks/scouting/write.py
    - Input: db_payload_preview
    - Output: player_record_id, report_id
    - Calls ScoutingReportService.create_with_player
    - Non-LLM task

3.9 build_final_response task
    - File: backend/app/agents/functional/tasks/scouting/response.py
    - Input: report, player_id, saved_status
    - Output: AgentResponse
    - Non-LLM task
```

**Dependencies:** Phase 1, Phase 2

**Verification:**
```python
# Test individual tasks
from tests.test_helpers import create_test_entrypoint
from app.agents.functional.tasks.scouting.intake import intake_and_route_scouting

test_ep = create_test_entrypoint(intake_and_route_scouting)
result = test_ep.invoke(("Generate scouting report for LeBron James",), config)

assert result.player_name == "LeBron James"
assert result.sport_guess == "nba"
```

---

### Phase 4: Scouting Workflow

**Goal:** Wire tasks into complete workflow with HITL gates.

**Tasks:**
```
4.1 Create scouting_workflow entrypoint
    - File: backend/app/agents/functional/scouting_workflow.py
    - @entrypoint decorator with checkpointer
    - Wires all 9 nodes in sequence

4.2 Implement HITL Gate A (Plan Approval)
    - After draft_plan task
    - interrupt() with type="plan_approval"
    - Handle resume: approved vs edited
    - Pass updated plan to build_queries

4.3 Implement HITL Gate B (Player Approval)
    - After prepare_preview task
    - interrupt() with type="player_approval"
    - Handle actions: approve, reject, edit_wording, edit_content

4.4 Implement edit loops
    - edit_wording: re-run compose_report only
    - edit_content: re-run from build_queries
    - Pass feedback to re-run tasks

4.5 Add document check
    - Before starting: check user has documents
    - If no documents: return error with upload prompt
    - Function: check_user_has_documents(user_id)

4.6 Add workflow state management
    - ScoutingWorkflowState dataclass
    - Pass between nodes
    - Checkpoint at each node
```

**Dependencies:** Phase 3

**Workflow Structure:**
```python
@entrypoint(checkpointer=postgres_checkpointer)
def scouting_workflow(request: ScoutingRequest) -> AgentResponse:
    state = ScoutingWorkflowState()

    # Check documents exist
    if not check_user_has_documents(request.user_id):
        return error_response("Please upload documents before generating a scouting report.")

    # Node 1: Intake
    intake_result = intake_and_route_scouting(request.message).result()
    state.player_name = intake_result.player_name
    state.sport_guess = intake_result.sport_guess

    # Node 2: Draft Plan
    plan_result = draft_plan(state.player_name, state.sport_guess).result()
    state.plan_steps = plan_result.plan_steps
    state.query_hints = plan_result.query_hints

    # HITL Gate A: Plan Approval
    approval = interrupt({
        "type": "plan_approval",
        "player_name": state.player_name,
        "plan_steps": state.plan_steps,
        "query_hints": state.query_hints
    })
    if approval.get("edited"):
        state.plan_steps = approval["plan_steps"]
        state.query_hints = approval.get("query_hints", state.query_hints)

    # Node 3-6 with potential edit loop
    while True:
        # Node 3: Build Queries
        state.queries = build_queries(state.player_name, state.sport_guess, state.query_hints).result()

        # Node 4: Retrieve Evidence
        state.evidence_pack = retrieve_evidence(request.user_id, state.queries).result()

        # Node 5: Extract Fields
        extraction = extract_fields(state.evidence_pack.chunks).result()
        state.player_fields = extraction.player_fields
        state.raw_facts = extraction.raw_facts
        state.coverage = extraction.coverage

        # Node 6: Compose Report
        state.report_draft = compose_report(state.raw_facts, state.player_fields, state.coverage).result()

        # Node 7: Prepare Preview
        preview = prepare_preview(state.report_draft).result()

        # HITL Gate B: Player Approval
        decision = interrupt({
            "type": "player_approval",
            "player_fields": state.player_fields,
            "report_summary": state.report_draft.report_summary,
            "report_text": state.report_draft.report_text,
            "db_payload_preview": preview
        })

        if decision["action"] == "approve":
            # Node 8: Write Player Item
            write_result = write_player_item(preview, request.user_id).result()
            state.player_record_id = write_result.player_id
            state.report_id = write_result.report_id
            state.saved = True
            break

        elif decision["action"] == "reject":
            state.saved = False
            break

        elif decision["action"] == "edit_wording":
            # Re-run compose only
            state.report_draft = compose_report(
                state.raw_facts,
                state.player_fields,
                state.coverage,
                feedback=decision.get("feedback")
            ).result()
            continue

        elif decision["action"] == "edit_content":
            # Re-run from build_queries
            if decision.get("feedback"):
                state.query_hints.append(decision["feedback"])
            continue

    # Node 9: Final Response
    return build_final_response(state).result()
```

---

### Phase 5: Agent Integration

**Goal:** Connect scouting workflow to existing agent system.

**Tasks:**
```
5.1 Create ScoutingAgent class
    - File: backend/app/agents/agents/scouting.py
    - Minimal agent that delegates to scouting_workflow
    - System prompt for context (not used directly)

5.2 Register in AgentFactory
    - File: backend/app/agents/factory.py
    - Add: "scouting": ScoutingAgent

5.3 Extend Supervisor routing
    - File: backend/app/agents/agents/supervisor.py
    - Add "scouting" to ROUTING_TARGETS
    - Add SCOUTING_KEYWORDS for detection
    - Extract player_name in routing metadata

5.4 Update main workflow dispatch
    - File: backend/app/agents/functional/workflow.py
    - If routing_decision.agent == "scouting":
        return scouting_workflow(...)
    - Pass necessary context

5.5 Add new event types to streaming
    - File: backend/app/agents/functional/streaming.py
    - Add: plan_proposal, coverage_report, player_preview
    - Update EventCallbackHandler if needed
```

**Dependencies:** Phase 4

**Verification:**
```python
# Test routing
from app.agents.agents.supervisor import SupervisorAgent

supervisor = SupervisorAgent(user_id, "gpt-4o-mini", api_key)
decision = supervisor.route_message("Generate scouting report for LeBron James")

assert decision.agent == "scouting"
assert decision.metadata["player_name"] == "LeBron James"
```

---

### Phase 6: API & Frontend Integration

**Goal:** Handle new interrupt types and events in API layer.

**Tasks:**
```
6.1 Extend resume endpoint
    - File: backend/app/api/chats.py
    - Handle type="plan_approval" payload
    - Handle type="player_approval" payload
    - Validate action values

6.2 Add SSE event handling
    - Verify new event types flow through Redis
    - Test: plan_proposal, coverage_report, player_preview

6.3 Document API changes
    - Update API documentation
    - Include payload examples
```

**Dependencies:** Phase 5

**Note:** Frontend UI changes are out of scope for backend migration. Frontend team will implement approval UI components separately.

---

### Phase 7: Testing & Validation

**Goal:** Comprehensive test coverage.

**Tasks:**
```
7.1 Unit tests for each task
    - File: backend/tests/test_scouting_tasks.py
    - Test each task in isolation
    - Mock LLM responses for determinism

7.2 Integration tests for workflow
    - File: backend/tests/test_scouting_workflow.py
    - Test full flow with approve path
    - Test full flow with reject path
    - Test edit_wording loop
    - Test edit_content loop

7.3 HITL interrupt/resume tests
    - Test checkpoint at Gate A
    - Test checkpoint at Gate B
    - Test resume after delay

7.4 Error handling tests
    - No documents scenario
    - Player name extraction failure
    - Low confidence warning
    - Database write failure

7.5 E2E smoke test
    - Full flow with real LLM
    - Verify Redis events
    - Verify database records
```

**Verification:**
```bash
# Run all scouting tests
docker-compose exec backend python manage.py test tests.test_scouting_tasks
docker-compose exec backend python manage.py test tests.test_scouting_workflow
```

---

## 2. Dependency Graph

```
Phase 1 (Foundation)
    │
    ├──────────────────┐
    ↓                  ↓
Phase 2 (RAG)     Phase 3 (Tasks)
    │                  │
    └────────┬─────────┘
             ↓
        Phase 4 (Workflow)
             │
             ↓
        Phase 5 (Agent Integration)
             │
             ↓
        Phase 6 (API Integration)
             │
             ↓
        Phase 7 (Testing)
```

---

## 3. Risk Mitigation

### Risk 1: LLM Extraction Quality
**Risk:** LLM may extract incorrect player_name or hallucinate fields.
**Mitigation:**
- Strict Pydantic validation
- Confidence thresholds
- Human approval gate before write

### Risk 2: Edit Loop Infinite Cycles
**Risk:** User repeatedly requests edits, never approves.
**Mitigation:**
- Max edit iterations (e.g., 5)
- Timeout after extended inactivity
- Clear UI feedback on loop count

### Risk 3: Checkpoint Storage Growth
**Risk:** Checkpoints accumulate for long-running flows.
**Mitigation:**
- Existing checkpoint cleanup (already implemented)
- Monitor checkpoint table size
- Purge old checkpoints periodically

### Risk 4: RAG Query Explosion
**Risk:** 6 queries × top_k=30 = 180 initial chunks.
**Mitigation:**
- Strict deduplication
- Hard cap at 40 chunks
- Monitor retrieval latency

---

## 4. Implementation Checklist

### Phase 1: Foundation
- [ ] Create `backend/app/db/models/player.py`
- [ ] Create `backend/app/db/models/scouting_report.py`
- [ ] Update `backend/app/db/models/__init__.py`
- [ ] Run `make makemigrations`
- [ ] Run `make migrate`
- [ ] Create `backend/app/schemas/scouting/` directory
- [ ] Create `player_fields.py` schema
- [ ] Create `evidence_pack.py` schema
- [ ] Create `report_draft.py` schema
- [ ] Create `workflow_state.py` dataclass
- [ ] Create `backend/app/services/player_service.py`
- [ ] Create `backend/app/services/scouting_report_service.py`

### Phase 2: RAG Extension
- [ ] Add `query_rag_batch()` function
- [ ] Add `deduplicate_chunks()` function
- [ ] Add chunk budget enforcement
- [ ] Add `calculate_coverage()` function
- [ ] Add EvidencePack output format

### Phase 3: Task Functions
- [ ] Create `backend/app/agents/functional/tasks/scouting/` directory
- [ ] Implement `intake.py` (intake_and_route_scouting)
- [ ] Implement `plan.py` (draft_plan)
- [ ] Implement `queries.py` (build_queries)
- [ ] Implement `retrieval.py` (retrieve_evidence)
- [ ] Implement `extraction.py` (extract_fields)
- [ ] Implement `composition.py` (compose_report)
- [ ] Implement `preview.py` (prepare_preview)
- [ ] Implement `write.py` (write_player_item)
- [ ] Implement `response.py` (build_final_response)

### Phase 4: Workflow
- [ ] Create `backend/app/agents/functional/scouting_workflow.py`
- [ ] Implement HITL Gate A (plan_approval)
- [ ] Implement HITL Gate B (player_approval)
- [ ] Implement edit_wording loop
- [ ] Implement edit_content loop
- [ ] Add document check
- [ ] Add workflow state management

### Phase 5: Agent Integration
- [ ] Create `backend/app/agents/agents/scouting.py`
- [ ] Register in `factory.py`
- [ ] Extend Supervisor routing
- [ ] Update main workflow dispatch
- [ ] Add new event types to streaming

### Phase 6: API Integration
- [ ] Extend resume endpoint for plan_approval
- [ ] Extend resume endpoint for player_approval
- [ ] Verify SSE event flow
- [ ] Update API documentation

### Phase 7: Testing
- [ ] Create `tests/test_scouting_tasks.py`
- [ ] Create `tests/test_scouting_workflow.py`
- [ ] Add HITL interrupt/resume tests
- [ ] Add error handling tests
- [ ] Run E2E smoke test

---

## 5. Success Criteria

### Functional
- [ ] "Generate scouting report for [player]" routes to scouting workflow
- [ ] Plan approval gate pauses and resumes correctly
- [ ] Player approval gate handles all 4 actions (approve/reject/edit_wording/edit_content)
- [ ] Edit loops execute correct subset of nodes
- [ ] Player and ScoutingReport created in database on approve
- [ ] Report returned without database write on reject
- [ ] Events stream to frontend via Redis

### Non-Functional
- [ ] Full flow completes in < 60s (excluding user wait time)
- [ ] Checkpoints restore correctly after resume
- [ ] No data leakage between users (multi-tenancy)
- [ ] All tests pass

---

*End of Part 4*
