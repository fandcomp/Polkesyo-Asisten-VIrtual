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
    db_factory, question: dict, run_id, ablation_disable_acif: bool = False
) -> dict[str, Any]:
    """Send one gold-QA question through the real pipeline and score it.

    Uses its own AsyncSession (concurrent questions can't safely share one session), bounded
    by EVALUATION_RUNNER_TIMEOUT_SECONDS so one slow/hung question can't stall the whole run.

    `ablation_disable_acif` is the with/without-ACIF thesis comparison switch (Evaluation Layer
    Phase 5) — forwarded to ChatCoreService.process_message, which only ever honors it under
    evaluation_mode=True (asserted there). A real /chat request is never affected.
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
                    ablation_disable_acif=ablation_disable_acif,
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

        retrieval_rows = (
            await db.execute(select(RetrievalEvaluationLog).where(RetrievalEvaluationLog.trace_id == trace_id))
        ).scalars().all()
        citation_rows = (
            await db.execute(select(CitationEvaluationLog).where(CitationEvaluationLog.trace_id == trace_id))
        ).scalars().all()
        chat_log = (
            await db.execute(select(ChatEvaluationLog).where(ChatEvaluationLog.trace_id == trace_id))
        ).scalar_one_or_none()

        expected_chunk_ids = question.get("expected_chunk_ids") or []
        expected_document_ids = question.get("expected_document_ids") or []
        selected_rows = [r for r in retrieval_rows if r.selected_for_context]

        if expected_chunk_ids:
            retrieved = [r.chunk_id for r in selected_rows]
            precision = metrics.precision_at_k(retrieved, expected_chunk_ids)
            recall = metrics.recall_at_k(retrieved, expected_chunk_ids)
            hit_rate = metrics.hit_rate_at_k(retrieved, expected_chunk_ids)
        elif expected_document_ids:
            retrieved = [r.document_id for r in selected_rows]
            precision = metrics.precision_at_k(retrieved, expected_document_ids)
            recall = metrics.recall_at_k(retrieved, expected_document_ids)
            hit_rate = metrics.hit_rate_at_k(retrieved, expected_document_ids)
        else:
            # No ground truth pinned for this gold item yet — precision/recall/hit_rate are
            # "not applicable", not a failing 0.0 (see metrics.precision_at_k's docstring).
            precision = None
            recall = None
            hit_rate = None

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
        if chat_log and chat_log.answer_status in ("answered", "verified"):
            context_text = "\n\n".join(
                (r.metadata_json or {}).get("content", "")
                for r in selected_rows
                if r.metadata_json
            ).strip()
            judge_result = await llm_judge.judge_answer(
                question=question["question"],
                context=context_text,
                answer=chat_log.final_answer,
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
) -> str:
    """Run the full gold QA dataset once, bounded by EVALUATION_RUNNER_CONCURRENCY, and write
    evaluation_runs + evaluation_results. Returns the created evaluation_run_id (empty string
    if the runner is disabled via EVALUATION_RUNNER_ENABLED=false).

    `config_name` tags the created EvaluationRun row (e.g. "with_acif" / "without_acif") so two
    runs against the same dataset can be paired by question_id for the thesis with/without-ACIF
    comparison (see statistical_comparison.py). `ablation_disable_acif` is forwarded to every
    question — set it True together with config_name="without_acif" to produce that condition.
    """
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
                db_factory, question, run_id, ablation_disable_acif=ablation_disable_acif
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
        help='Tag for this EvaluationRun (e.g. "with_acif" / "without_acif").',
    )
    parser.add_argument(
        "--disable-acif",
        action="store_true",
        help="Run the without-ACIF ablation condition (all 5 gates bypassed; see chat_core.py).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(
        run_evaluation(
            run_name=args.run_name,
            config_name=args.config_name,
            ablation_disable_acif=args.disable_acif,
        )
    )
