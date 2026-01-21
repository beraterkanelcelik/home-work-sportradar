# Agentic Scouting Report Flow - Migration Requirements

## Overview

This document set provides comprehensive requirements for migrating the existing multi-agent platform to support the new **Agentic Scouting Report Flow** as defined in `agentic-concept.md` and `agentic-schemas.md`.

## Document Structure

| Document | Purpose |
|----------|---------|
| [Part 1: Current State Analysis](./PART1_CURRENT_STATE_ANALYSIS.md) | Analysis of existing architecture, component inventory, reuse assessment |
| [Part 2: Target State & Gap Analysis](./PART2_TARGET_STATE_GAP_ANALYSIS.md) | Target architecture, 9-node flow design, data models, gap analysis |
| [Part 3: Migration Requirements](./PART3_MIGRATION_REQUIREMENTS.md) | Functional/non-functional requirements, API contracts, error handling |
| [Part 4: Implementation Plan](./PART4_IMPLEMENTATION_PLAN.md) | 7-phase implementation plan, dependencies, checklist, success criteria |

## Confirmed Design Decisions

| Decision | Choice |
|----------|--------|
| Integration Strategy | Supervisor routes `scouting_report` intent to ScoutingAgent |
| Agent Implementation | LangGraph @task functions (not full Agent classes) |
| Report Storage | New `ScoutingReport` table per schema |
| Architecture | Keep Temporal + Redis (existing infrastructure) |
| Edit Loop | Restart from Node 3 (build_queries) with updated query_hints |
| Low Confidence | Warning only - user decides whether to proceed |
| Batch Mode | Single player only for MVP |
| HITL Gates | Both Plan Approval (A) and Player Approval (B) required |
| No Documents | Block flow and prompt user to upload documents |

## High-Level Flow

```
User Request: "Generate scouting report for LeBron James"
                          ↓
                   [Supervisor Routing]
                   intent: scouting_report
                          ↓
              ┌───────────────────────┐
              │   Scouting Workflow    │
              │      (9 Nodes)         │
              └───────────────────────┘
                          ↓
Node 1: Intake → Extract player_name, sport_guess
Node 2: Draft Plan → Generate 4-7 step plan
        ↓
    [HITL Gate A: Plan Approval]
        ↓
Node 3: Build Queries → 3-6 diversified queries
Node 4: Retrieve Evidence → Multi-query RAG, dedupe, budget
Node 5: Extract Fields → Structured player_fields, raw_facts
Node 6: Compose Report → Sport-agnostic scouting report
Node 7: Prepare Preview → Format for approval UI
        ↓
    [HITL Gate B: Player Approval]
        ↓
        ├── Approve → Node 8: Write to DB → Node 9: Return
        ├── Reject → Node 9: Return (no write)
        ├── Edit Wording → Loop to Node 6
        └── Edit Content → Loop to Node 3
```

## New Database Tables

### Players
```sql
- id (UUID)
- display_name, sport (required)
- positions, teams, league, aliases (optional)
- height_cm, weight_kg, measurements (optional)
- strengths, weaknesses, style_tags, risk_notes, role_projection (optional)
- latest_report_id (FK)
```

### Scouting Reports
```sql
- id (UUID)
- player_id (FK, required)
- report_text (required)
- report_summary, coverage, source_doc_ids (optional)
- run_id, request_text (audit)
```

## New Files Summary

```
backend/app/
├── agents/
│   ├── agents/scouting.py           # ScoutingAgent class
│   └── functional/
│       ├── scouting_workflow.py     # Main workflow entrypoint
│       └── tasks/scouting/          # 9 task functions
├── db/models/
│   ├── player.py                    # Player model
│   └── scouting_report.py           # ScoutingReport model
├── services/
│   ├── player_service.py            # CRUD operations
│   └── scouting_report_service.py   # Atomic create
└── schemas/scouting/                # Pydantic schemas
```

## Implementation Phases

1. **Foundation** - Models, services, schemas
2. **RAG Extension** - Multi-query, dedup, EvidencePack
3. **Task Functions** - All 9 nodes as @task
4. **Workflow** - Wire tasks with HITL gates
5. **Agent Integration** - Connect to Supervisor
6. **API Integration** - Handle new interrupt types
7. **Testing** - Unit, integration, E2E

## Quick Start for Implementation

Start with Phase 1 (Foundation Layer):

```bash
# 1. Create model files
# backend/app/db/models/player.py
# backend/app/db/models/scouting_report.py

# 2. Run migrations
make makemigrations
make migrate

# 3. Create schemas
# backend/app/schemas/scouting/*.py

# 4. Create services
# backend/app/services/player_service.py
# backend/app/services/scouting_report_service.py

# 5. Verify
docker-compose exec backend python manage.py shell
>>> from app.db.models import Player, ScoutingReport
>>> # Should import without errors
```

Then proceed through phases 2-7 in order.

## Questions/Clarifications

If any ambiguities arise during implementation, refer to:
- `agentic-concept.md` - Conceptual flow design
- `agentic-schemas.md` - Database and JSON schemas
- This requirements document set

---

*Generated for Agentic Scouting Report Flow MVP Migration*
