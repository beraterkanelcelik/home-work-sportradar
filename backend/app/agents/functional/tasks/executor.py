"""
Plan Executor - Executes dynamic plans step by step.

This module takes an ExecutionPlan and runs each step sequentially,
accumulating context as it goes.
"""

from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from langgraph.func import task
from langgraph.types import interrupt

from app.agents.functional.scouting.schemas import (
    ExecutionPlan,
    PlanStep,
    EvidencePack,
    ChunkData,
    Coverage,
    PlayerFields,
    ScoutingReportDraft,
    DbPayloadPreview,
    CreatePlayerWithReportResponse,
)
from app.agents.functional.tasks.scouting.retrieval import retrieve_evidence
from app.agents.functional.tasks.scouting.extraction import extract_fields
from app.agents.functional.tasks.scouting.composition import compose_report
from app.agents.functional.tasks.scouting.preview import prepare_preview
from app.agents.functional.tasks.scouting.write import write_player_item
from app.agents.functional.models import AgentResponse
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExecutionContext:
    """
    Accumulated context during plan execution.

    Each step can read from and write to this context.
    """

    # User/session info
    user_id: int = 0
    session_id: int = 0
    api_key: str = ""
    original_message: str = ""
    run_id: Optional[str] = None

    # Plan info
    player_name: Optional[str] = None
    sport_guess: Optional[str] = None

    # Accumulated from rag_search steps
    all_chunks: List[ChunkData] = field(default_factory=list)
    all_queries: List[str] = field(default_factory=list)

    # From extract_player step
    player_fields: Optional[PlayerFields] = None
    raw_facts: List[str] = field(default_factory=list)
    coverage: Optional[Coverage] = None

    # From compose_report step
    report_draft: Optional[ScoutingReportDraft] = None
    preview: Optional[DbPayloadPreview] = None

    # From save_player step
    player_record_id: Optional[str] = None
    report_id: Optional[str] = None
    saved: bool = False

    # For answer step
    answer_context: str = ""


def execute_rag_search(
    step: PlanStep,
    context: ExecutionContext,
) -> Dict[str, Any]:
    """
    Execute a rag_search step.

    Searches user's documents and accumulates results in context.
    """
    query = step.params.get("query", "")
    if not query:
        logger.warning("[EXECUTOR] rag_search step has no query param")
        return {"success": False, "error": "No query provided"}

    logger.info(f"[EXECUTOR] Executing rag_search: {query}")

    # Retrieve evidence for this single query
    evidence = retrieve_evidence(
        user_id=context.user_id,
        queries=[query],
        api_key=context.api_key,
        max_chunks=15,  # Smaller per-query limit since we aggregate
    ).result()

    # Accumulate chunks and queries
    context.all_chunks.extend(evidence.chunks)
    context.all_queries.append(query)

    # Build context string for answer step
    if evidence.chunks:
        chunk_texts = [f"- {c.text[:200]}..." for c in evidence.chunks[:5]]
        context.answer_context += f"\n\nSearch for '{query}':\n" + "\n".join(
            chunk_texts
        )

    return {
        "success": True,
        "chunks_found": len(evidence.chunks),
        "confidence": evidence.confidence,
    }


def execute_extract_player(
    step: PlanStep,
    context: ExecutionContext,
) -> Dict[str, Any]:
    """
    Execute an extract_player step.

    Extracts structured player data from accumulated evidence.
    """
    logger.info(f"[EXECUTOR] Executing extract_player for {context.player_name}")

    if not context.all_chunks:
        logger.warning("[EXECUTOR] No evidence chunks to extract from")
        return {"success": False, "error": "No evidence available"}

    # Build EvidencePack from accumulated chunks
    # Dedupe chunks by chunk_id
    seen_ids = set()
    unique_chunks = []
    for chunk in context.all_chunks:
        if chunk.chunk_id not in seen_ids:
            seen_ids.add(chunk.chunk_id)
            unique_chunks.append(chunk)

    # Sort by score and limit
    unique_chunks.sort(key=lambda c: c.score, reverse=True)
    unique_chunks = unique_chunks[:40]

    evidence_pack = EvidencePack(
        queries=context.all_queries,
        chunks=unique_chunks,
        coverage=Coverage(found=[], missing=[]),
        confidence="med" if len(unique_chunks) > 10 else "low",
    )

    # Extract fields
    player_fields, raw_facts, coverage = extract_fields(
        evidence_pack=evidence_pack,
        player_name=context.player_name or "Unknown Player",
        sport_guess=context.sport_guess or "unknown",
        api_key=context.api_key,
    ).result()

    context.player_fields = player_fields
    context.raw_facts = raw_facts
    context.coverage = coverage

    return {
        "success": True,
        "facts_extracted": len(raw_facts),
        "fields": {
            "positions": player_fields.positions,
            "teams": player_fields.teams,
            "has_physical": player_fields.physical is not None,
            "has_scouting": player_fields.scouting is not None,
        },
    }


def execute_compose_report(
    step: PlanStep,
    context: ExecutionContext,
) -> Dict[str, Any]:
    """
    Execute a compose_report step.

    Generates scouting report from extracted player data.
    """
    logger.info(f"[EXECUTOR] Executing compose_report for {context.player_name}")

    if not context.player_fields:
        logger.warning("[EXECUTOR] No player fields to compose report from")
        return {"success": False, "error": "No player data available"}

    feedback = step.params.get("feedback")

    report_draft = compose_report(
        player_fields=context.player_fields,
        raw_facts=context.raw_facts,
        coverage=context.coverage or Coverage(found=[], missing=[]),
        feedback=feedback,
        api_key=context.api_key,
    ).result()

    context.report_draft = report_draft

    # Prepare preview for HITL Gate B
    source_doc_ids = list(set(chunk.doc_id for chunk in context.all_chunks))
    context.preview = prepare_preview(
        report_draft=report_draft,
        source_doc_ids=source_doc_ids,
    ).result()

    return {
        "success": True,
        "report_length": len(report_draft.report_text),
        "summary_points": len(report_draft.report_summary),
    }


def execute_update_report(
    step: PlanStep,
    context: ExecutionContext,
) -> Dict[str, Any]:
    """
    Execute an update_report step.

    Updates an existing saved report with new information.
    """
    logger.info("[EXECUTOR] Executing update_report")

    feedback = step.params.get("feedback", "")
    target_report_id = step.params.get("report_id")

    # TODO: Implement report update logic
    # 1. Load existing report from DB
    # 2. Merge new evidence with existing
    # 3. Re-compose report with feedback

    # For now, just compose a new report with feedback
    if context.player_fields:
        report_draft = compose_report(
            player_fields=context.player_fields,
            raw_facts=context.raw_facts,
            coverage=context.coverage or Coverage(found=[], missing=[]),
            feedback=feedback,
            api_key=context.api_key,
        ).result()

        context.report_draft = report_draft

        source_doc_ids = list(set(chunk.doc_id for chunk in context.all_chunks))
        context.preview = prepare_preview(
            report_draft=report_draft,
            source_doc_ids=source_doc_ids,
        ).result()

        return {"success": True, "report_length": len(report_draft.report_text)}

    return {"success": False, "error": "No player data to update"}


def execute_save_player(
    step: PlanStep,
    context: ExecutionContext,
    emit_event: callable,
) -> Tuple[Dict[str, Any], bool]:
    """
    Execute a save_player step.

    This triggers HITL Gate B for player approval before saving.

    Returns:
        Tuple of (result_dict, should_continue)
    """
    logger.info(f"[EXECUTOR] Executing save_player for {context.player_name}")

    if not context.preview:
        logger.warning("[EXECUTOR] No preview available for save")
        return {"success": False, "error": "No report to save"}, True

    # Emit player preview event for frontend
    preview_payload = {
        "player_fields": context.preview.player.model_dump(exclude_none=True),
        "report_summary": context.report_draft.report_summary
        if context.report_draft
        else [],
        "report_text": context.report_draft.report_text if context.report_draft else "",
        "db_payload_preview": context.preview.model_dump(exclude_none=True),
    }
    emit_event("player_preview", preview_payload)

    # HITL Gate B: Player approval
    logger.info(
        f"[EXECUTOR] [HITL-B] Requesting player approval for {context.player_name}"
    )

    decision = interrupt(
        {
            "type": "player_approval",
            "session_id": context.session_id,
            "player_fields": context.preview.player.model_dump(exclude_none=True),
            "report_summary": context.report_draft.report_summary
            if context.report_draft
            else [],
            "report_text": context.report_draft.report_text
            if context.report_draft
            else "",
        }
    )

    action = decision.get("action", "approve") if decision else "approve"
    logger.info(f"[EXECUTOR] [HITL-B] Player approval decision: {action}")

    if action == "approve":
        # Write to database
        try:
            write_result: CreatePlayerWithReportResponse = write_player_item(
                preview=context.preview,
                user_id=context.user_id,
                run_id=context.run_id,
                request_text=context.original_message,
            ).result()

            context.player_record_id = write_result.player_id
            context.report_id = write_result.report_id
            context.saved = True

            return {
                "success": True,
                "player_id": write_result.player_id,
                "report_id": write_result.report_id,
            }, True

        except Exception as e:
            logger.error(f"[EXECUTOR] Failed to save player: {e}")
            return {"success": False, "error": str(e)}, True

    elif action == "reject":
        context.saved = False
        return {"success": True, "rejected": True}, True

    else:
        # Unknown action, continue without saving
        return {"success": False, "error": f"Unknown action: {action}"}, True


def execute_answer(
    step: PlanStep,
    context: ExecutionContext,
) -> Dict[str, Any]:
    """
    Execute an answer step.

    Generates a final response from accumulated context.
    """
    logger.info("[EXECUTOR] Executing answer step")

    # The actual answer generation will be done by the workflow
    # after plan execution completes
    return {"success": True}


@task
def execute_plan(
    plan: ExecutionPlan,
    user_id: int,
    session_id: int,
    api_key: str,
    original_message: str,
    run_id: Optional[str] = None,
    emit_event: Optional[callable] = None,
) -> Tuple[ExecutionContext, List[Dict[str, Any]]]:
    """
    Execute a plan step by step.

    Args:
        plan: The execution plan to run
        user_id: User ID
        session_id: Session ID
        api_key: OpenAI API key
        original_message: Original user message
        run_id: Optional run ID for correlation
        emit_event: Optional callback to emit workflow events

    Returns:
        Tuple of (final context, list of step results)
    """
    logger.info(
        f"[EXECUTOR] Starting plan execution: {plan.intent} with {len(plan.steps)} steps"
    )

    # Initialize context
    context = ExecutionContext(
        user_id=user_id,
        session_id=session_id,
        api_key=api_key,
        original_message=original_message,
        run_id=run_id,
        player_name=plan.player_name,
        sport_guess=plan.sport_guess,
    )

    # Default emit_event to no-op
    if emit_event is None:
        emit_event = lambda event_type, data: None

    step_results = []

    for idx, step in enumerate(plan.steps):
        logger.info(
            f"[EXECUTOR] Step {idx + 1}/{len(plan.steps)}: {step.action} - {step.description}"
        )

        # Emit step start event
        emit_event(
            "plan_step_progress",
            {
                "step_index": idx,
                "total_steps": len(plan.steps),
                "status": "in_progress",
                "step_name": step.description,
                "action": step.action,
            },
        )

        try:
            # Execute based on action type
            if step.action == "rag_search":
                result = execute_rag_search(step, context)

            elif step.action == "extract_player":
                result = execute_extract_player(step, context)

            elif step.action == "compose_report":
                result = execute_compose_report(step, context)

            elif step.action == "update_report":
                result = execute_update_report(step, context)

            elif step.action == "save_player":
                result, should_continue = execute_save_player(step, context, emit_event)
                if not should_continue:
                    step_results.append({"step": idx, "action": step.action, **result})
                    break

            elif step.action == "answer":
                result = execute_answer(step, context)

            else:
                logger.warning(f"[EXECUTOR] Unknown action: {step.action}")
                result = {"success": False, "error": f"Unknown action: {step.action}"}

            step_results.append({"step": idx, "action": step.action, **result})

            # Emit step complete event
            emit_event(
                "plan_step_progress",
                {
                    "step_index": idx,
                    "total_steps": len(plan.steps),
                    "status": "completed",
                    "step_name": step.description,
                    "action": step.action,
                    "result": result,
                },
            )

        except Exception as e:
            logger.error(f"[EXECUTOR] Step {idx} failed: {e}", exc_info=True)
            step_results.append(
                {
                    "step": idx,
                    "action": step.action,
                    "success": False,
                    "error": str(e),
                }
            )

            emit_event(
                "plan_step_progress",
                {
                    "step_index": idx,
                    "total_steps": len(plan.steps),
                    "status": "error",
                    "step_name": step.description,
                    "action": step.action,
                    "error": str(e),
                },
            )

            # Continue to next step on error (could make this configurable)
            continue

    logger.info(f"[EXECUTOR] Plan execution complete. Saved={context.saved}")

    return context, step_results
