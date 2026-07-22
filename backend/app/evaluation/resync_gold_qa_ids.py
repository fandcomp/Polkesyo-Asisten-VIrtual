"""Propose refreshed `expected_chunk_ids` for `gold_qa_dataset.jsonl` — READ-ONLY, human-reviewed.

Root cause: `document_chunks.id` used to be a random UUID assigned on every ingestion run (see
`app/services/id_generation.py` for the fix going forward), so any `expected_chunk_ids` pinned
before this fix — or before a document is ever re-ingested/re-indexed — silently go stale, and
`precision_at_k`/`recall_at_k` (`app/evaluation/metrics.py`) score a real 0.0 for something that
should have been "not applicable".

This script does NOT rewrite `gold_qa_dataset.jsonl`. For each gold question with a non-empty
`expected_document_ids`, it looks at that document's *current* approved chunks, scores each one
by keyword overlap against `expected_answer`, and writes a diff-report CSV for a human to review
and apply by hand. Auto-writing pinned ground truth without review would undermine the very
evaluation integrity this script exists to protect (CLAUDE.md §29).

Usage (run against whatever Postgres `settings.database_url` currently points at — local dev by
default; never targets the VPS):
    python -m app.evaluation.resync_gold_qa_ids [--output PATH]
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import ChunkSummary, DocumentChunk
from app.evaluation.run_evaluation import DATASET_PATH, load_gold_qa_dataset

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("data/evaluation_reports") / "gold_qa_resync"
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_TOP_N_CANDIDATES = 3


def _tokenize(text: str) -> set[str]:
    return {tok for tok in _WORD_RE.findall(text.lower()) if len(tok) > 2}


def _score_chunk(expected_answer_tokens: set[str], chunk_text: str) -> float:
    """Fraction of expected-answer tokens found in the chunk's own text/summary."""
    if not expected_answer_tokens:
        return 0.0
    chunk_tokens = _tokenize(chunk_text)
    if not chunk_tokens:
        return 0.0
    hits = len(expected_answer_tokens & chunk_tokens)
    return hits / len(expected_answer_tokens)


async def _candidates_for_document(db: AsyncSession, document_id: str) -> list[dict[str, Any]]:
    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.chunk_index,
            DocumentChunk.original_text,
            ChunkSummary.approved_summary,
        )
        .outerjoin(ChunkSummary, ChunkSummary.chunk_id == DocumentChunk.id)
        .where(DocumentChunk.document_id == document_id)
        .where(DocumentChunk.status == "approved")
        .order_by(DocumentChunk.chunk_index)
    )
    result = await db.execute(stmt)
    return [
        {
            "id": str(row.id),
            "chunk_index": row.chunk_index,
            "text": f"{row.original_text or ''} {row.approved_summary or ''}",
            "snippet": (row.approved_summary or row.original_text or "")[:200].replace("\n", " "),
        }
        for row in result.all()
    ]


async def build_resync_proposal(db_factory) -> list[dict[str, Any]]:
    questions = load_gold_qa_dataset(DATASET_PATH)
    rows: list[dict[str, Any]] = []

    async with db_factory() as db:
        for question in questions:
            expected_document_ids = question.get("expected_document_ids") or []
            old_expected_chunk_ids = question.get("expected_chunk_ids") or []
            if not expected_document_ids:
                continue

            answer_tokens = _tokenize(question.get("expected_answer") or "")

            all_candidates: list[dict[str, Any]] = []
            for document_id in expected_document_ids:
                all_candidates.extend(await _candidates_for_document(db, document_id))

            if not all_candidates:
                rows.append({
                    "question_id": question.get("id"),
                    "category": question.get("category"),
                    "old_expected_chunk_ids": ";".join(old_expected_chunk_ids),
                    "proposed_chunk_id": "",
                    "match_score": 0.0,
                    "matched_snippet": "NO APPROVED CHUNKS FOUND FOR expected_document_ids",
                })
                continue

            scored = sorted(
                (
                    {**c, "score": _score_chunk(answer_tokens, c["text"])}
                    for c in all_candidates
                ),
                key=lambda c: c["score"],
                reverse=True,
            )[:_TOP_N_CANDIDATES]

            for rank, candidate in enumerate(scored):
                rows.append({
                    "question_id": question.get("id"),
                    "category": question.get("category"),
                    "old_expected_chunk_ids": ";".join(old_expected_chunk_ids) if rank == 0 else "",
                    "proposed_chunk_id": candidate["id"],
                    "match_score": round(candidate["score"], 3),
                    "matched_snippet": candidate["snippet"],
                })

    return rows


def _write_csv(rows: list[dict[str, Any]], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["question_id", "category", "old_expected_chunk_ids", "proposed_chunk_id", "match_score", "matched_snippet"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


async def main(output: Path | None = None) -> Path:
    engine = create_async_engine(settings.database_url)
    db_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        rows = await build_resync_proposal(db_factory)
    finally:
        await engine.dispose()

    output_path = output or (DEFAULT_OUTPUT_DIR / f"gold_qa_resync_proposal_{date.today().isoformat()}.csv")
    written = _write_csv(rows, output_path)
    logger.info(f"Wrote {len(rows)} candidate rows to {written}")
    logger.info("This is a PROPOSAL only — review match_score/matched_snippet by hand before "
                "editing gold_qa_dataset.jsonl's expected_chunk_ids. Nothing was auto-applied.")
    return written


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None, help="CSV output path (default: data/evaluation_reports/gold_qa_resync/)")
    args = parser.parse_args()
    asyncio.run(main(args.output))
