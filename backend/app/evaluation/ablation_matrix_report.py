"""Cross-config N-gate ablation analysis — Evaluation Layer Phase 5 extension (2026-07-24).

Aggregates EvaluationResult rows across the 11-condition ABLATION_GATE_MATRIX
(run_evaluation.py) into one wide summary table plus a gate-by-gate impact ranking derived
from the 5 "gates_all_minus_N" leave-one-out configs. Extends (does not replace) the original
2-condition with/without-ACIF comparison in statistical_comparison.py — every significance
figure here is produced by calling that module's `compare_runs`, not by re-deriving Wilcoxon/
McNemar logic.

`build_ablation_matrix`/`build_gate_impact_ranking` are pure and DB-free (unit-testable with
plain in-memory EvaluationResult lists). The `if __name__ == "__main__":` block at the bottom
does the DB lookups and CSV writing.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence

from app.db.models import EvaluationResult
from app.evaluation import metrics
from app.evaluation.statistical_comparison import ComparisonReport, compare_runs

logger = logging.getLogger(__name__)

REPORTS_DIR = Path("data/evaluation_reports")

# The two canonical reference conditions every other config is compared against.
_GATES_ALL_ALIASES = ("gates_all", "with_acif")
_GATES_NONE_ALIASES = ("gates_none", "without_acif")


def _first_present(results_by_config: dict[str, Sequence[EvaluationResult]], aliases: tuple[str, ...]):
    for alias in aliases:
        if alias in results_by_config:
            return alias, results_by_config[alias]
    return None, None


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _config_aggregate_metrics(results: Sequence[EvaluationResult]) -> dict[str, float | None]:
    """Descriptive per-config means, reusing metrics.py's existing pure functions — no new
    metric math invented. `None`-valued fields (e.g. no Security items, judge disabled) are
    skipped rather than coerced to 0.0, matching metrics.py's established convention."""
    as_dicts = [
        {
            "citation_present": r.citation_present,
            "citation_correct": r.citation_correct,
            "attack_success": r.attack_success,
        }
        for r in results
    ]
    fallback_scored = [r.fallback_correct for r in results if r.fallback_correct is not None]
    return {
        "precision_at_3": _mean([r.precision_at_3 for r in results]),
        "recall_at_3": _mean([r.recall_at_3 for r in results]),
        "hit_rate_at_3": _mean([r.hit_rate_at_3 for r in results]),
        "citation_coverage": metrics.citation_coverage(as_dicts),
        "citation_correctness": metrics.citation_correctness(as_dicts),
        "fallback_correctness": _mean([1.0 if v else 0.0 for v in fallback_scored]),
        "attack_success_rate": metrics.attack_success_rate(as_dicts),
        "faithfulness_score": _mean([r.faithfulness_score for r in results]),
        "answer_relevance_score": _mean([r.answer_relevance_score for r in results]),
        "average_latency_ms": metrics.average_latency([r.total_latency_ms for r in results]),
        "p95_latency_ms": metrics.p95_latency([r.total_latency_ms for r in results]),
    }


@dataclass
class AblationConfigRow:
    config_name: str
    gate_count: int
    disabled_gates: tuple[int, ...]
    n_questions: int
    aggregate_metrics: dict[str, float | None]
    # comparison_vs_gates_all/_none: a=reference condition, b=this config, so mean_delta =
    # this_config - reference (positive means this config scored higher than the reference).
    comparison_vs_gates_all: ComparisonReport | None = None
    comparison_vs_gates_none: ComparisonReport | None = None


@dataclass
class AblationMatrixReport:
    rows: list[AblationConfigRow] = field(default_factory=list)


@dataclass
class GateImpactRow:
    gate_number: int
    metric: str
    gates_all_value: float | None
    gates_all_minus_n_value: float | None
    delta: float | None  # gates_all_minus_N - gates_all (negative = removing this gate hurt)
    percent_change: float | None
    significant: bool | None


def build_ablation_matrix(results_by_config: dict[str, Sequence[EvaluationResult]]) -> AblationMatrixReport:
    """Build the wide per-config summary. `results_by_config` maps config_name (any key from
    run_evaluation.ABLATION_GATE_MATRIX, e.g. "gates_all", "gates_all_minus_3") to that config's
    full evaluation_results rows from a same-corpus, same-day run."""
    from app.evaluation.run_evaluation import ABLATION_GATE_MATRIX

    gates_all_name, gates_all_results = _first_present(results_by_config, _GATES_ALL_ALIASES)
    gates_none_name, gates_none_results = _first_present(results_by_config, _GATES_NONE_ALIASES)

    rows: list[AblationConfigRow] = []
    for config_name, results in results_by_config.items():
        disabled = ABLATION_GATE_MATRIX.get(config_name, frozenset())
        comparison_vs_gates_all = None
        if gates_all_results is not None and config_name != gates_all_name:
            comparison_vs_gates_all = compare_runs(
                gates_all_results, results, config_name_a=gates_all_name, config_name_b=config_name
            )
        comparison_vs_gates_none = None
        if gates_none_results is not None and config_name != gates_none_name:
            comparison_vs_gates_none = compare_runs(
                gates_none_results, results, config_name_a=gates_none_name, config_name_b=config_name
            )
        rows.append(AblationConfigRow(
            config_name=config_name,
            gate_count=5 - len(disabled),
            disabled_gates=tuple(sorted(disabled)),
            n_questions=len(results),
            aggregate_metrics=_config_aggregate_metrics(results),
            comparison_vs_gates_all=comparison_vs_gates_all,
            comparison_vs_gates_none=comparison_vs_gates_none,
        ))
    return AblationMatrixReport(rows=rows)


def build_gate_impact_ranking(matrix: AblationMatrixReport) -> list[GateImpactRow]:
    """Rank each gate's individual contribution using the 5 gates_all_minus_N configs' own
    comparison_vs_gates_all (already-computed Wilcoxon/McNemar results — nothing re-derived
    here), sorted by |delta| descending across all (gate, metric) pairs. Kept per-metric
    (no single composite score) so the ranking stays auditable per CLAUDE.md's evaluation
    honesty principle."""
    rows_by_config = {r.config_name: r for r in matrix.rows}
    impact_rows: list[GateImpactRow] = []

    for gate_num in range(1, 6):
        minus_row = rows_by_config.get(f"gates_all_minus_{gate_num}")
        if minus_row is None or minus_row.comparison_vs_gates_all is None:
            continue
        cmp = minus_row.comparison_vs_gates_all
        comparisons = list(cmp.metrics)
        if cmp.attack_success is not None:
            comparisons.append(cmp.attack_success)
        for mc in comparisons:
            impact_rows.append(GateImpactRow(
                gate_number=gate_num,
                metric=mc.metric,
                gates_all_value=mc.mean_a,
                gates_all_minus_n_value=mc.mean_b,
                delta=mc.mean_delta,
                percent_change=mc.percent_change,
                significant=mc.significant,
            ))

    impact_rows.sort(key=lambda r: abs(r.delta) if r.delta is not None else -1.0, reverse=True)
    return impact_rows


def _write_summary_csv(matrix: AblationMatrixReport, path: Path) -> None:
    if not matrix.rows:
        return
    metric_names = list(matrix.rows[0].aggregate_metrics.keys())
    fieldnames = ["config_name", "gate_count", "disabled_gates", "n_questions", *metric_names]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in matrix.rows:
            writer.writerow({
                "config_name": row.config_name,
                "gate_count": row.gate_count,
                "disabled_gates": ",".join(str(g) for g in row.disabled_gates),
                "n_questions": row.n_questions,
                **row.aggregate_metrics,
            })


def _write_ranking_csv(impact_rows: list[GateImpactRow], path: Path) -> None:
    if not impact_rows:
        return
    fieldnames = [
        "gate_number", "metric", "gates_all_value", "gates_all_minus_n_value",
        "delta", "percent_change", "significant",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in impact_rows:
            writer.writerow({
                "gate_number": row.gate_number,
                "metric": row.metric,
                "gates_all_value": row.gates_all_value,
                "gates_all_minus_n_value": row.gates_all_minus_n_value,
                "delta": row.delta,
                "percent_change": row.percent_change,
                "significant": row.significant,
            })


async def _load_latest_results_by_config(db, config_names: list[str]) -> dict[str, list[EvaluationResult]]:
    """Look up the most-recent EvaluationRun per config_name (config_name has no unique
    constraint — db/models.py's EvaluationRun.config_name — so "most recent wins", the same
    convention already used by routes_evaluation_admin.py's combined-report export)."""
    from sqlalchemy import select

    from app.db.models import EvaluationRun

    results_by_config: dict[str, list[EvaluationResult]] = {}
    for config_name in config_names:
        run = (
            await db.execute(
                select(EvaluationRun)
                .where(EvaluationRun.config_name == config_name)
                .order_by(EvaluationRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None:
            logger.warning(f"No EvaluationRun found for config_name={config_name!r} — skipping")
            continue
        rows = (
            await db.execute(select(EvaluationResult).where(EvaluationResult.evaluation_run_id == run.id))
        ).scalars().all()
        results_by_config[config_name] = list(rows)
    return results_by_config


if __name__ == "__main__":
    import argparse
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app.evaluation.run_evaluation import ABLATION_GATE_MATRIX

    parser = argparse.ArgumentParser(
        description="Build the cross-config N-gate ablation summary + gate impact ranking."
    )
    parser.add_argument(
        "--config-names",
        default=",".join(ABLATION_GATE_MATRIX.keys()),
        help="Comma-separated config_names to include (default: the full 11-config matrix, "
        "using the most recent EvaluationRun for each).",
    )
    args = parser.parse_args()
    config_names = [c.strip() for c in args.config_names.split(",") if c.strip()]

    logging.basicConfig(level=logging.INFO)

    async def _main() -> None:
        engine = create_async_engine(settings.database_url)
        db_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with db_factory() as db:
            results_by_config = await _load_latest_results_by_config(db, config_names)
        await engine.dispose()

        if not results_by_config:
            logger.error("No evaluation results found for any requested config_name — nothing to report.")
            return

        matrix = build_ablation_matrix(results_by_config)
        impact_ranking = build_gate_impact_ranking(matrix)

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        summary_path = REPORTS_DIR / f"ablation_matrix_summary_{timestamp}.csv"
        ranking_path = REPORTS_DIR / f"gate_impact_ranking_{timestamp}.csv"
        _write_summary_csv(matrix, summary_path)
        _write_ranking_csv(impact_ranking, ranking_path)
        logger.info(f"Wrote {summary_path} ({len(matrix.rows)} configs)")
        logger.info(f"Wrote {ranking_path} ({len(impact_ranking)} gate/metric rows)")

    asyncio.run(_main())
