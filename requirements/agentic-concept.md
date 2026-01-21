# Agentic Scouting Report Flow (MVP) — Concept

## Goal
Design an agentic flow (LangGraph Functional API friendly) that:
- Uses user-uploaded documents already indexed for RAG.
- Generates a scouting report for a requested player (NBA/football).
- Builds a Player DB model (“item”) with optional fields (fill what is found, omit unknown).
- Includes Human-in-the-Loop (HITL) approval for **plan** and for **creating the player item**.
- Avoids existence checks, rerankers, or retrieval filters in MVP.

---

## Agents (Conceptual Roles)

### 1) Supervisor (Planner + Router)
**Responsibilities**
- Parse request and route to correct flow (MVP: scouting report).
- Draft a short plan (4–7 steps).
- Manage HITL gates (Plan Approval, Write Approval).
- Decide whether to re-run compose-only vs retrieval+compose after user feedback.

**Outputs**
- `intent`
- `player_name`
- `sport_guess` (nba / football / unknown)
- `plan_steps[]`
- `query_hints[]`

---

### 2) Retriever (RAG Specialist)
**Responsibilities**
- Create a small diversified set of queries (3–6) to compensate for no filters/reranker.
- Retrieve chunks from vector store and deduplicate.
- Enforce a strict chunk budget for speed.

**Outputs**
- `queries[]`
- `chunks[]` (deduped)
- `coverage` (what was found vs missing)
- `confidence` (low/med/high)

---

### 3) Extractor (Structurer)
**Responsibilities**
- Convert retrieved chunks into:
  - `raw_facts[]` (atomic bullets for composer)
  - `player_fields{}` (optional fields only; omit unknown)

**Outputs**
- `player_fields{}`
- `raw_facts[]`
- `coverage` (carried forward)

---

### 4) Composer (Scouting Writer)
**Responsibilities**
- Produce a sport-agnostic scouting report that tolerates missing info.
- Prepare a DB payload preview combining structured fields and report.

**Outputs**
- `scouting_report` (text)
- `report_summary[]` (5–8 bullets)
- `db_payload_preview{}`

---

### 5) DB Writer (Operator, Non-LLM)
**Responsibilities**
- Create the Player item record using `db_payload_preview`.
- No existence check in MVP (always create/insert or simplest upsert).

**Outputs**
- `player_record_id`

---

## Player Item Model (Common Concept, Optional Fields)
Store what is supported by retrieved evidence; otherwise omit.

### Identity
- `display_name`
- `sport` (nba / football / unknown)
- `positions[]` (optional)
- `teams[]` (optional)
- `league` (optional)
- `aliases[]` (optional)

### Physical (optional)
- `height?`
- `weight?`
- `measurements?` (generic map if needed)

### Scouting (optional)
- `strengths[]`
- `weaknesses[]`
- `style_tags[]`
- `risk_notes[]`
- `role_projection` (short text)

### Artifact
- `latest_scouting_report` (text)
- `report_generated_at` / metadata (if desired)

---

## Agentic Flow (Functional API Friendly)

### Node 1 — Intake & Route
**Input:** user request text  
**Output:** `intent`, `player_name` (best-effort), `sport_guess`  
**If `player_name` missing:** interrupt for a single clarification.

---

### Node 2 — Draft Plan (Supervisor)
Produce a short plan (4–7 steps max), e.g.:
1) Confirm target player context from request
2) Retrieve relevant info from uploaded docs
3) Extract optional player fields
4) Draft scouting report
5) Prepare player DB item preview
6) Ask approval to save
7) Save player item + return result

#### HITL Gate A — Plan Approval
Pause until user approves or edits plan.
- If edited: update `plan_steps` and optionally `query_hints`.

---

### Node 3 — Build Queries (Retriever Helper)
Create 3–6 diversified queries. Rules:
- Always include:
  - `{player_name}`
  - `{player_name} strengths weaknesses`
  - `{player_name} height weight position`
- Add 1–2 sport-specific queries if `sport_guess` known.
- Keep query count small and dedupe similar queries.

---

### Node 4 — Retrieve Evidence (Retriever)
Run vector search for each query; produce `evidence_pack`.
- Deduplicate chunks (doc_id + chunk_id or normalized text hash)
- Enforce a strict chunk budget before downstream steps

Outputs: `chunks[]`, `coverage`, `confidence`

---

### Node 5 — Extract Structured Fields (Extractor)
From `chunks[]`:
- Produce `raw_facts[]` (atomic bullets)
- Map supported facts into `player_fields{}` (omit unknown fields)

Outputs: `player_fields{}`, `raw_facts[]`, `coverage`

---

### Node 6 — Compose Report (Composer)
Use a sport-agnostic template:

**Scouting Report Structure**
- Snapshot (3–5 bullets)
- Strengths (bullets)
- Weaknesses / limitations (bullets)
- Play style & tendencies (short)
- Role projection (short)
- Development focus (bullets)
- Risk notes (optional)
- What I couldn’t find (from `coverage`, 1–3 bullets)

Outputs:
- `scouting_report`
- `report_summary[]`
- `db_payload_preview` = `player_fields + latest_scouting_report + metadata`

---

### Node 7 — Preview & Approval (Supervisor)
Show preview:
- Structured `player_fields`
- `report_summary`
- Full report (expandable)

#### HITL Gate B — “Create Player Item?”
- If **approved** → proceed to write
- If **rejected** → skip write, return report anyway
- If **edit requested**:
  - Wording/format edits → re-run **Composer only**
  - Missing info / focus changes → re-run **Build Queries → Retrieve → Extract → Compose**

This forms the core loop: **preview → refine → preview → approve**.

---

### Node 8 — Write Player Item (DB Writer)
Create the player item using `db_payload_preview`.
Output: `player_record_id`

---

### Node 9 — Final Response
Return:
- `scouting_report`
- `player_record_id` if created
- “saved/not saved” status

---

## Efficiency Rules (MVP)
- Prefer small, diversified query sets over complex retrieval logic.
- Deduplicate aggressively.
- Enforce a hard cap on chunks forwarded to Extractor/Composer.
- On user feedback, re-run the smallest necessary portion:
  - Compose-only for wording/template tweaks
  - Full retrieval loop only when evidence needs to change

---
