"""Evaluation Layer Phase 3 — gold-QA dataset runner.

Manual invocation only: `python -m app.evaluation.run_evaluation` inside the backend
container. Never triggered automatically on server startup or wired into main.py — matches
the same standalone-script convention used by the project's other manual/scheduled scripts
(e.g. `app/workers/tasks.py`'s Celery task, `cleanup_old_logs.py`), not an app dependency.

For each gold question: sends it through the real ChatCoreService.process_message pipeline
(the same code path the production /chat endpoint uses) with evaluation_mode=True, then loads
that trace's rows from the Phase 1 logging tables to compute metrics — never re-implements or
bypasses ACIF, retrieval, or citation logic.
"""
import asyncio
import csv
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import (
    ChatEvaluationLog,
    CitationEvaluationLog,
    EvaluationResult,
    EvaluationRun,
    RetrievalEvaluationLog,
)
from app.evaluation import llm_judge, metrics
from app.services.chat_core import ChatCoreService
from app.services.session_service import ConsentService, SessionService
from app.services.vector_index_service import VectorIndexService

logger = logging.getLogger(__name__)

DATASET_PATH = Path(__file__).parent / "gold_qa_dataset.jsonl"
REPORTS_DIR = Path("data/evaluation_reports")

_TERMINAL_FALLBACK_STATUSES = {"insufficient_context", "fallback_enforced", "verification_error", "out_of_domain"}
_TERMINAL_BLOCK_STATUSES = {"rejected_by_input_filter"}

# The 11-condition N-gate ablation matrix (2026-07-24) — cumulative Gate1->Gate5 order plus
# leave-one-out, extending the original 2-condition with/without-ACIF design (see
# docs/private/acif/evaluation-plan.md). "with_acif"/"without_acif" are the pre-existing
# config_name values (still the default and still used throughout existing reports/tests) kept
# as-is; "gates_all"/"gates_none" are exact aliases of the same two conditions using the new
# matrix naming, for symmetry with the 9 new gates_* keys. The sidang-cited 2026-07-16/2026-07-18
# comparison methodology is unaffected — those runs used config_name="with_acif"/"without_acif",
# which still resolve identically.
ABLATION_GATE_MATRIX: dict[str, frozenset[int]] = {
    "with_acif": frozenset(),
    "without_acif": frozenset({1, 2, 3, 4, 5}),
    "gates_none": frozenset({1, 2, 3, 4, 5}),
    "gates_1": frozenset({2, 3, 4, 5}),
    "gates_1_2": frozenset({3, 4, 5}),
    "gates_1_2_3": frozenset({4, 5}),
    "gates_1_2_3_4": frozenset({5}),
    "gates_all": frozenset(),
    "gates_all_minus_1": frozenset({1}),
    "gates_all_minus_2": frozenset({2}),
    "gates_all_minus_3": frozenset({3}),
    "gates_all_minus_4": frozenset({4}),
    "gates_all_minus_5": frozenset({5}),
}


def _resolve_disabled_gates(
    config_name: str,
    ablation_disable_acif: bool,
    disabled_gates: frozenset[int] | None,
) -> frozenset[int]:
    """Resolve the effective disabled-gate set, most-explicit-wins:
    `disabled_gates` param > `ablation_disable_acif` bool > `config_name` matrix lookup.

    Unlike a plain `.get(config_name, frozenset())` fallback, an unrecognized `config_name`
    raises rather than silently defaulting to "all gates enabled" — every evaluation run is
    real, billed OpenRouter traffic, so a typo'd config name (e.g. "gates_1_23") must fail
    loudly instead of quietly running the wrong condition.
    """
    if disabled_gates is not None:
        return frozenset(disabled_gates)
    if ablation_disable_acif:
        return frozenset({1, 2, 3, 4, 5})
    if config_name not in ABLATION_GATE_MATRIX:
        raise ValueError(
            f"Unknown config_name {config_name!r} — pass disabled_gates or "
            f"ablation_disable_acif explicitly, or use one of {sorted(ABLATION_GATE_MATRIX)}"
        )
    return ABLATION_GATE_MATRIX[config_name]


def load_gold_qa_dataset(path: Path = DATASET_PATH) -> list[dict]:
    """Read the JSONL gold QA dataset — one question per line."""
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


async def _evaluate_one_question(
    db_factory, question: dict, run_id, disabled_gates: frozenset[int] = frozenset(),
    disable_graph_rag: bool = False,
) -> dict[str, Any]:
    """Send one gold-QA question through the real pipeline and score it.

    Uses its own AsyncSession (concurrent questions can't safely share one session), bounded
    by EVALUATION_RUNNER_TIMEOUT_SECONDS so one slow/hung question can't stall the whole run.

    `disabled_gates` is the N-gate ablation study's gate-subset switch (Evaluation Layer Phase
    5, generalized 2026-07-24 from the original all-or-nothing with/without-ACIF comparison) —
    forwarded to ChatCoreService.process_message, which only ever honors it under
    evaluation_mode=True (asserted there). A real /chat request is never affected.

    `disable_graph_rag` is the GraphRAG-isolation experiment's switch (2026-07-25) — same
    evaluation-mode-only-effect discipline, forwarded straight through.
    """
    async with db_factory() as db:
        session = await SessionService.create_session(db)
        await ConsentService.set_consent(db, session.id, "history_and_analytics")

        t0 = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                ChatCoreService.process_message(
                    db,
                    session.id,
                    question["question"],
                    evaluation_mode=True,
                    scenario_code=f"gold_qa:{question['id']}",
                    disabled_gates=disabled_gates,
                    disable_graph_rag=disable_graph_rag,
                ),
                timeout=settings.evaluation_runner_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error(f"Question {question['id']} timed out after {settings.evaluation_runner_timeout_seconds}s")
            return {
                "question_id": question["id"],
                "trace_id": None,
                "category": question.get("category"),
                "expected_behavior": question["expected_behavior"],
                "notes": "timed out",
                "total_latency_ms": int((time.perf_counter() - t0) * 1000),
            }

        trace_id = response.trace_id

        # Ordered by retrieval_rank (2026-07-25 fix): without this, row return order isn't
        # guaranteed to match actual rank, so a naive [:k] slice for the @k metrics below could
        # cut off before a chunk that is genuinely within the true top-k by rank — found via a
        # live smoke test where a rank-5 chunk still failed to register in precision_at_5.
        retrieval_rows = (
            await db.execute(
                select(RetrievalEvaluationLog)
                .where(RetrievalEvaluationLog.trace_id == trace_id)
                .order_by(RetrievalEvaluationLog.retrieval_rank)
            )
        ).scalars().all()
        citation_rows = (
            await db.execute(select(CitationEvaluationLog).where(CitationEvaluationLog.trace_id == trace_id))
        ).scalars().all()
        chat_log = (
            await db.execute(select(ChatEvaluationLog).where(ChatEvaluationLog.trace_id == trace_id))
        ).scalar_one_or_none()

        expected_chunk_ids = question.get("expected_chunk_ids") or []
        expected_document_ids = question.get("expected_document_ids") or []
        # Multi-query fan-out can log duplicate per-variant rank rows with no chunk_id/document_id
        # attached (see retrieval_evaluation_logs — same trace, same rank, blank identifiers) —
        # excluded here so they don't occupy a slot in the [:k] slice ahead of a real chunk.
        selected_rows = [
            r for r in retrieval_rows
            if r.selected_for_context and (r.chunk_id or r.document_id)
        ]

        # @5 mirrors settings.max_context_chunks (the system's real retrieval/answer-generation
        # width) — additive alongside @3, not a replacement, since a correctly-retrieved chunk
        # at rank 4-5 genuinely reaches the LLM but would otherwise score as a miss under @3
        # alone (found 2026-07-25, see 014_precision_recall_at_5_and_relevance.py).
        _k5 = settings.max_context_chunks
        if expected_chunk_ids:
            retrieved = [r.chunk_id for r in selected_rows]
            precision = metrics.precision_at_k(retrieved, expected_chunk_ids)
            recall = metrics.recall_at_k(retrieved, expected_chunk_ids)
            hit_rate = metrics.hit_rate_at_k(retrieved, expected_chunk_ids)
            precision_5 = metrics.precision_at_k(retrieved, expected_chunk_ids, k=_k5)
            recall_5 = metrics.recall_at_k(retrieved, expected_chunk_ids, k=_k5)
            hit_rate_5 = metrics.hit_rate_at_k(retrieved, expected_chunk_ids, k=_k5)
        elif expected_document_ids:
            retrieved = [r.document_id for r in selected_rows]
            precision = metrics.precision_at_k(retrieved, expected_document_ids)
            recall = metrics.recall_at_k(retrieved, expected_document_ids)
            hit_rate = metrics.hit_rate_at_k(retrieved, expected_document_ids)
            precision_5 = metrics.precision_at_k(retrieved, expected_document_ids, k=_k5)
            recall_5 = metrics.recall_at_k(retrieved, expected_document_ids, k=_k5)
            hit_rate_5 = metrics.hit_rate_at_k(retrieved, expected_document_ids, k=_k5)
        else:
            # No ground truth pinned for this gold item yet — precision/recall/hit_rate are
            # "not applicable", not a failing 0.0 (see metrics.precision_at_k's docstring).
            precision = recall = hit_rate = None
            precision_5 = recall_5 = hit_rate_5 = None

        citation_present = len(citation_rows) > 0
        if expected_document_ids:
            cited_doc_ids = {c.document_id for c in citation_rows if c.document_id}
            citation_correct = bool(cited_doc_ids & set(expected_document_ids))
        else:
            # Without a pinned expected document, "correct" can't be judged independently of
            # "present" — this is a known limitation until gold items have real ground truth.
            citation_correct = citation_present if citation_present else None

        is_security_category = (question.get("category") or "").lower() == "security"
        attack_success = None
        if is_security_category and chat_log:
            attack_success = chat_log.answer_status not in (
                _TERMINAL_FALLBACK_STATUSES | _TERMINAL_BLOCK_STATUSES
            )

        # RAGAS-style faithfulness/relevance/hallucination scoring (Evaluation Layer Phase 5).
        # Context text rides along inside each selected row's metadata_json (only populated
        # when EVALUATION_LOG_FULL_CONTEXT=true — see chat_core.py's retrieval_rows comment);
        # judge_answer() itself no-ops (returns None) when the judge is disabled or there's no
        # context to score against, so this is a no-op unless both flags are on.
        judge_result = None
        relevance_score = None
        if chat_log and chat_log.answer_status in ("answered", "verified"):
            chunk_texts = [
                (r.metadata_json or {}).get("content", "")
                for r in selected_rows
                if r.metadata_json
            ]
            context_text = "\n\n".join(chunk_texts).strip()
            judge_result = await llm_judge.judge_answer(
                question=question["question"],
                context=context_text,
                answer=chat_log.final_answer,
                db=db,
            )
            relevance_score = await llm_judge.judge_retrieval_relevance(
                question=question["question"],
                chunk_texts=chunk_texts,
                db=db,
            )

        return {
            "question_id": question["id"],
            "trace_id": trace_id,
            "category": question.get("category"),
            "expected_behavior": question["expected_behavior"],
            "precision_at_3": precision,
            "recall_at_3": recall,
            "hit_rate_at_3": hit_rate,
            "precision_at_5": precision_5,
            "recall_at_5": recall_5,
            "hit_rate_at_5": hit_rate_5,
            "retrieval_relevance_score": relevance_score,
            "citation_present": citation_present,
            "citation_correct": citation_correct,
            "fallback_correct": (
                metrics.fallback_correctness(question["expected_behavior"], chat_log.answer_status)
                if chat_log else None
            ),
            "attack_success": attack_success,
            "faithfulness_score": judge_result.faithfulness_score if judge_result else None,
            "answer_relevance_score": judge_result.answer_relevance_score if judge_result else None,
            "hallucination_detected": judge_result.hallucination_detected if judge_result else None,
            "total_latency_ms": chat_log.total_latency_ms if chat_log else None,
            "retrieval_latency_ms": chat_log.retrieval_latency_ms if chat_log else None,
            "llm_latency_ms": chat_log.llm_latency_ms if chat_log else None,
            "notes": None,
        }


def _export_results_csv(run_id: str, results: list[dict[str, Any]]) -> Path | None:
    """Write a CSV snapshot of this run's results to the persisted data volume
    (backend_data:/app/data, same mount used for uploaded documents) so it survives
    container recreates — separate from the DB rows, which remain the source of truth for
    the admin Export Center (Phase 6)."""
    if not results:
        return None
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{run_id}.csv"
    fieldnames = list(results[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    return path


async def run_evaluation(
    run_name: str = "gold_qa_run",
    dataset_path: Path = DATASET_PATH,
    config_name: str = "with_acif",
    ablation_disable_acif: bool = False,
    disabled_gates: frozenset[int] | None = None,
    disable_graph_rag: bool = False,
) -> str:
    """Run the full gold QA dataset once, bounded by EVALUATION_RUNNER_CONCURRENCY, and write
    evaluation_runs + evaluation_results. Returns the created evaluation_run_id (empty string
    if the runner is disabled via EVALUATION_RUNNER_ENABLED=false).

    `config_name` tags the created EvaluationRun row so runs can be paired/compared by
    question_id (see statistical_comparison.py). As of 2026-07-24, `config_name` also drives
    which ACIF gates run: any of the 11 keys in `ABLATION_GATE_MATRIX` (e.g. "with_acif",
    "without_acif" via their "gates_all"/"gates_none" aliases, or the new "gates_1",
    "gates_all_minus_3", etc.) auto-resolves the disabled-gate set — see `_resolve_disabled_gates`.
    `ablation_disable_acif`/`disabled_gates` remain available as explicit overrides for one-off
    combinations outside the fixed matrix.
    """
    effective_disabled_gates = _resolve_disabled_gates(config_name, ablation_disable_acif, disabled_gates)

    if not settings.evaluation_runner_enabled:
        logger.warning("Evaluation runner is disabled (EVALUATION_RUNNER_ENABLED=false)")
        return ""

    engine = create_async_engine(settings.database_url)
    db_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    questions = load_gold_qa_dataset(dataset_path)
    if not questions:
        logger.warning(f"No questions found in {dataset_path}")
        await engine.dispose()
        return ""

    # Warm the embedding model *before* dispatching concurrent questions below. On a cold
    # process (e.g. `python -m app.evaluation.run_evaluation`, which never runs main.py's
    # startup warm-up) or right after a fresh container restart, several gold-QA questions
    # otherwise race to lazy-load the model at once inside VectorIndexService.search()'s
    # 8s timeout — pushing the first batch past it and silently degrading their retrieval
    # to zero results, which then scores as a false 0.0 precision/recall instead of "not
    # yet measured". get_embedding_function() is idempotent (locked, cached per process),
    # so this is a no-op if the model is already warm.
    await asyncio.to_thread(VectorIndexService.get_embedding_function)

    async with db_factory() as db:
        run = EvaluationRun(
            run_name=run_name,
            config_name=config_name,
            run_type="full",
            total_questions=len(questions),
            status="running",
            started_at=datetime.utcnow(),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    semaphore = asyncio.Semaphore(settings.evaluation_runner_concurrency)

    async def _bounded(question: dict) -> dict[str, Any]:
        async with semaphore:
            return await _evaluate_one_question(
                db_factory, question, run_id, disabled_gates=effective_disabled_gates,
                disable_graph_rag=disable_graph_rag,
            )

    raw_results = await asyncio.gather(*(_bounded(q) for q in questions), return_exceptions=True)

    completed = 0
    csv_rows: list[dict[str, Any]] = []
    async with db_factory() as db:
        for result in raw_results:
            if isinstance(result, Exception):
                logger.error(f"Question evaluation raised: {result}")
                continue
            db.add(EvaluationResult(evaluation_run_id=run_id, **result))
            csv_rows.append({"evaluation_run_id": str(run_id), **result})
            completed += 1
        await db.commit()

        run_row = await db.get(EvaluationRun, run_id)
        if run_row:
            run_row.completed_questions = completed
            run_row.status = "completed" if completed == len(questions) else "failed"
            run_row.finished_at = datetime.utcnow()
            await db.commit()

    csv_path = _export_results_csv(str(run_id), csv_rows)
    logger.info(
        f"Evaluation run {run_id} completed: {completed}/{len(questions)} questions. "
        f"CSV: {csv_path or 'not written (no results)'}"
    )

    await engine.dispose()
    return str(run_id)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the gold-QA evaluation dataset once.")
    parser.add_argument("--run-name", default="gold_qa_run")
    parser.add_argument(
        "--config-name",
        default="with_acif",
        help=(
            "Tag for this EvaluationRun. Any key in run_evaluation.ABLATION_GATE_MATRIX "
            '(e.g. "with_acif", "without_acif", "gates_1", "gates_1_2", "gates_1_2_3", '
            '"gates_1_2_3_4", "gates_all", "gates_all_minus_1".."gates_all_minus_5") '
            "auto-resolves which gates are disabled — see --disabled-gates for ad-hoc overrides."
        ),
    )
    parser.add_argument(
        "--disable-acif",
        action="store_true",
        help="Shorthand: bypass all 5 gates regardless of --config-name (legacy without-ACIF condition).",
    )
    parser.add_argument(
        "--disabled-gates",
        default=None,
        help='Explicit comma-separated gate numbers to bypass, e.g. "4,5" — overrides --config-name lookup.',
    )
    parser.add_argument(
        "--disable-graph-rag",
        action="store_true",
        help="GraphRAG-isolation experiment (2026-07-25): short-circuit GraphRAG retrieval to "
        "empty, isolating Vector-RAG-only vs Vector-RAG+GraphRAG while ACIF gates stay fixed.",
    )
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=DATASET_PATH,
        help="Path to an alternate gold-QA JSONL dataset (default: gold_qa_dataset.jsonl). "
        "E.g. graphrag_multihop_dataset.jsonl for the GraphRAG-isolation probe questions.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    _cli_disabled_gates = (
        frozenset(int(x) for x in args.disabled_gates.split(",") if x.strip())
        if args.disabled_gates
        else None
    )
    asyncio.run(
        run_evaluation(
            run_name=args.run_name,
            dataset_path=args.dataset_path,
            config_name=args.config_name,
            ablation_disable_acif=args.disable_acif,
            disabled_gates=_cli_disabled_gates,
            disable_graph_rag=args.disable_graph_rag,
        )
    )
