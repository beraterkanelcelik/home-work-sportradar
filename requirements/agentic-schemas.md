````md
# MVP: Postgres (pgvector) Player Item + Scouting Report — One MD File

## Overview
- DB: **PostgreSQL** with **pgvector** enabled for document chunk embeddings.
- Write: **one-call create** (creates Player “item” + Scouting Report + links latest report).
- MVP rules:
  - **No existence check** (always create a new player row).
  - Optional fields: **store only what is found**; omit unknown.
  - Retrieval: query-only (no filters/reranker assumed).

---

## 1) Database Schema (DDL)

### 1.1 Players (“item”)
```sql
CREATE TABLE players (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Identity
  display_name      TEXT NOT NULL,
  sport             TEXT NOT NULL CHECK (sport IN ('nba','football','unknown')),

  positions         JSONB NULL,   -- ["SG","SF"] or ["QB"]
  teams             JSONB NULL,   -- ["LAL"] or ["KC Chiefs"] (freeform MVP)
  league            TEXT NULL,    -- "NBA", "NFL", ...
  aliases           JSONB NULL,   -- ["Steph Curry", "Wardell Curry"]

  -- Physical (optional)
  height_cm         INTEGER NULL CHECK (height_cm BETWEEN 80 AND 260),
  weight_kg         INTEGER NULL CHECK (weight_kg BETWEEN 30 AND 200),
  measurements      JSONB NULL,   -- {"wingspan_cm":208,"hand_size_in":9.5}

  -- Scouting (optional)
  strengths         JSONB NULL,   -- ["...","..."]
  weaknesses        JSONB NULL,
  style_tags        JSONB NULL,   -- ["3PT shooter","POA defender"]
  risk_notes        JSONB NULL,
  role_projection   TEXT NULL,

  -- Latest report link
  latest_report_id  UUID NULL
);

CREATE INDEX players_sport_idx ON players (sport);
CREATE INDEX players_display_name_idx ON players (display_name);
````

### 1.2 Scouting reports

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
  source_doc_ids    JSONB NULL     -- internal only: ["doc_a","doc_b"]
);

CREATE INDEX scouting_reports_player_id_idx ON scouting_reports (player_id);
CREATE INDEX scouting_reports_created_at_idx ON scouting_reports (created_at);
```

### 1.3 Document storage for RAG (reference design)

Use your existing ingestion/index tables if you already have them. This is a reference.

```sql
CREATE TABLE documents (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  owner_user_id TEXT NULL,
  title         TEXT NULL,
  filename      TEXT NULL,
  metadata      JSONB NULL
);

-- Set vector dimension to your embedding model (example: 1536)
CREATE TABLE document_chunks (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index  INTEGER NOT NULL,
  text         TEXT NOT NULL,
  embedding    vector(1536) NOT NULL,
  metadata     JSONB NULL
);

-- Example vector index (ivfflat). Adjust lists after testing & ANALYZE.
CREATE INDEX document_chunks_embedding_ivfflat_idx
  ON document_chunks USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE INDEX document_chunks_document_id_idx ON document_chunks (document_id);
```

---

## 2) JSON Schemas (Node Contracts)

### 2.1 PlayerFields (Extractor output)

* Optional fields are omitted if unknown.
* Nested `physical` and `scouting` are for clarity; DB write flattens to columns.

```json
{
  "$id": "PlayerFields",
  "type": "object",
  "additionalProperties": false,
  "required": ["display_name", "sport"],
  "properties": {
    "display_name": { "type": "string", "minLength": 1 },
    "sport": { "type": "string", "enum": ["nba", "football", "unknown"] },

    "positions": { "type": "array", "items": { "type": "string" }, "minItems": 1 },
    "teams": { "type": "array", "items": { "type": "string" } },
    "league": { "type": "string" },
    "aliases": { "type": "array", "items": { "type": "string" } },

    "physical": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "height_cm": { "type": "integer", "minimum": 80, "maximum": 260 },
        "weight_kg": { "type": "integer", "minimum": 30, "maximum": 200 },
        "measurements": {
          "type": "object",
          "additionalProperties": { "type": ["number", "string", "boolean", "null"] }
        }
      }
    },

    "scouting": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "strengths": { "type": "array", "items": { "type": "string" } },
        "weaknesses": { "type": "array", "items": { "type": "string" } },
        "style_tags": { "type": "array", "items": { "type": "string" } },
        "risk_notes": { "type": "array", "items": { "type": "string" } },
        "role_projection": { "type": "string" }
      }
    }
  }
}
```

### 2.2 EvidencePack (Retriever output)

Hard caps keep MVP fast and predictable.

```json
{
  "$id": "EvidencePack",
  "type": "object",
  "additionalProperties": false,
  "required": ["queries", "chunks", "coverage", "confidence"],
  "properties": {
    "queries": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1,
      "maxItems": 6
    },
    "chunks": {
      "type": "array",
      "maxItems": 40,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["doc_id", "chunk_id", "text", "score"],
        "properties": {
          "doc_id": { "type": "string" },
          "chunk_id": { "type": "string" },
          "text": { "type": "string", "minLength": 1 },
          "score": { "type": "number" }
        }
      }
    },
    "coverage": {
      "type": "object",
      "additionalProperties": false,
      "required": ["found", "missing"],
      "properties": {
        "found": { "type": "array", "items": { "type": "string" } },
        "missing": { "type": "array", "items": { "type": "string" } }
      }
    },
    "confidence": { "type": "string", "enum": ["low", "med", "high"] }
  }
}
```

### 2.3 ScoutingReportDraft (Composer output + Preview at HITL “Create item?”)

```json
{
  "$id": "ScoutingReportDraft",
  "type": "object",
  "additionalProperties": false,
  "required": ["report_text", "report_summary", "db_payload_preview"],
  "properties": {
    "report_text": { "type": "string", "minLength": 1 },
    "report_summary": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 3,
      "maxItems": 12
    },
    "db_payload_preview": {
      "type": "object",
      "additionalProperties": false,
      "required": ["player", "report"],
      "properties": {
        "player": { "$ref": "PlayerFields" },
        "report": {
          "type": "object",
          "additionalProperties": false,
          "required": ["report_text"],
          "properties": {
            "report_text": { "type": "string" },
            "report_summary": { "type": "array", "items": { "type": "string" } },
            "coverage": {
              "type": "object",
              "additionalProperties": false,
              "required": ["found", "missing"],
              "properties": {
                "found": { "type": "array", "items": { "type": "string" } },
                "missing": { "type": "array", "items": { "type": "string" } }
              }
            },
            "source_doc_ids": { "type": "array", "items": { "type": "string" } }
          }
        }
      }
    }
  }
}
```

---

## 3) One-Call Create API (DB Write Contract)

### 3.1 Request: CreatePlayerWithReportRequest

Creates:

1. `players` row
2. `scouting_reports` row
3. updates `players.latest_report_id`

All in a single transaction.

```json
{
  "$id": "CreatePlayerWithReportRequest",
  "type": "object",
  "additionalProperties": false,
  "required": ["player", "report"],
  "properties": {
    "run_id": { "type": "string" },
    "request_text": { "type": "string" },

    "player": { "$ref": "PlayerFields" },

    "report": {
      "type": "object",
      "additionalProperties": false,
      "required": ["report_text"],
      "properties": {
        "report_text": { "type": "string", "minLength": 1 },
        "report_summary": { "type": "array", "items": { "type": "string" } },
        "coverage": {
          "type": "object",
          "additionalProperties": false,
          "required": ["found", "missing"],
          "properties": {
            "found": { "type": "array", "items": { "type": "string" } },
            "missing": { "type": "array", "items": { "type": "string" } }
          }
        },
        "source_doc_ids": { "type": "array", "items": { "type": "string" } }
      }
    }
  }
}
```

### 3.2 Response: CreatePlayerWithReportResponse

```json
{
  "$id": "CreatePlayerWithReportResponse",
  "type": "object",
  "additionalProperties": false,
  "required": ["player_id", "report_id"],
  "properties": {
    "player_id": { "type": "string" },
    "report_id": { "type": "string" }
  }
}
```

---

## 4) Mapping Notes (JSON -> Columns)

### 4.1 PlayerFields -> players

* `player.display_name` -> `players.display_name`

* `player.sport` -> `players.sport`

* `player.positions` -> `players.positions` (JSONB)

* `player.teams` -> `players.teams` (JSONB)

* `player.league` -> `players.league`

* `player.aliases` -> `players.aliases` (JSONB)

* `player.physical.height_cm` -> `players.height_cm`

* `player.physical.weight_kg` -> `players.weight_kg`

* `player.physical.measurements` -> `players.measurements` (JSONB)

* `player.scouting.strengths` -> `players.strengths` (JSONB)

* `player.scouting.weaknesses` -> `players.weaknesses` (JSONB)

* `player.scouting.style_tags` -> `players.style_tags` (JSONB)

* `player.scouting.risk_notes` -> `players.risk_notes` (JSONB)

* `player.scouting.role_projection` -> `players.role_projection`

### 4.2 report -> scouting_reports

* `report.report_text` -> `scouting_reports.report_text`
* `report.report_summary` -> `scouting_reports.report_summary` (JSONB)
* `report.coverage` -> `scouting_reports.coverage` (JSONB)
* `report.source_doc_ids` -> `scouting_reports.source_doc_ids` (JSONB)
* `run_id`, `request_text` -> optional audit/correlation fields

### 4.3 Atomic transaction requirement

In one transaction:

1. Insert `players`
2. Insert `scouting_reports` with `player_id`
3. Update `players.latest_report_id = scouting_reports.id`

---

## 5) MVP Caps & Conventions

* EvidencePack: `queries <= 6`, `chunks <= 40`
* Report summary: `<= 12` bullets
* Omit unknown optional fields (avoid null spam)
* `sport` defaults to `"unknown"` if not inferable

```
```
