"""Same aggregation as eval_data_loader.py, but looked up by explicit run_name rather than
"most recent run per config_name" -- needed because the 2026-07-25b refresh has 4 different
runs sharing config_name="gates_all" (the gate-ablation gates_all run plus 3 GraphRAG-condition
runs also pinned at gates_all), so the config_name-based lookup is ambiguous. Run inside the
campus-va-backend container via docker exec.
"""
from __future__ import annotations

import asyncio
import csv
from pathlib import Path

RUN_NAME_BY_CONFIG = {
    "gates_none": "refresh_20260727b_gates_none",
    "gates_1": "refresh_20260727b_gates_1",
    "gates_1_2": "refresh_20260727b_gates_1_2",
    "gates_1_2_3": "refresh_20260727b_gates_1_2_3",
    "gates_1_2_3_4": "refresh_20260727b_gates_1_2_3_4",
    "gates_all_minus_1": "refresh_20260727b_gates_all_minus_1",
    "gates_all_minus_2": "refresh_20260727b_gates_all_minus_2",
    "gates_all_minus_3": "refresh_20260727b_gates_all_minus_3",
    "gates_all_minus_4": "refresh_20260727b_gates_all_minus_4",
    "gates_all": "refresh_20260727b_gates_all",  # the gate-ablation run, NOT any GraphRAG-condition run
}


async def main() -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app.db.models import EvaluationResult, EvaluationRun
    from app.evaluation.ablation_matrix_report import build_ablation_matrix, build_gate_impact_ranking

    engine = create_async_engine(settings.database_url)
    db_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    results_by_config: dict[str, list] = {}
    async with db_factory() as db:
        for config_name, run_name in RUN_NAME_BY_CONFIG.items():
            run = (
                await db.execute(select(EvaluationRun).where(EvaluationRun.run_name == run_name))
            ).scalar_one_or_none()
            if run is None:
                print(f"WARNING: run_name={run_name!r} not found, skipping {config_name}")
                continue
            rows = (
                await db.execute(select(EvaluationResult).where(EvaluationResult.evaluation_run_id == run.id))
            ).scalars().all()
            results_by_config[config_name] = list(rows)
            print(f"{config_name} -> {run_name}: {len(rows)} rows")
    await engine.dispose()

    aliased = dict(results_by_config)
    aliased["gates_all_minus_5"] = aliased["gates_1_2_3_4"]
    matrix = build_ablation_matrix(aliased)
    ranking = build_gate_impact_ranking(matrix)

    out_dir = Path("data/evaluation_reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = out_dir / "ablation_matrix_summary_v3.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        metric_names = list(matrix.rows[0].aggregate_metrics.keys())
        writer = csv.DictWriter(f, fieldnames=["config_name", "gate_count", "disabled_gates", "n_questions", *metric_names])
        writer.writeheader()
        for row in matrix.rows:
            writer.writerow({
                "config_name": row.config_name, "gate_count": row.gate_count,
                "disabled_gates": ",".join(str(g) for g in row.disabled_gates),
                "n_questions": row.n_questions, **row.aggregate_metrics,
            })

    ranking_path = out_dir / "gate_impact_ranking_v3.csv"
    with open(ranking_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "gate_number", "metric", "gates_all_value", "gates_all_minus_n_value",
            "delta", "percent_change", "significant",
        ])
        writer.writeheader()
        for row in ranking:
            writer.writerow({
                "gate_number": row.gate_number, "metric": row.metric,
                "gates_all_value": row.gates_all_value, "gates_all_minus_n_value": row.gates_all_minus_n_value,
                "delta": row.delta, "percent_change": row.percent_change, "significant": row.significant,
            })

    print(f"Wrote {summary_path} ({len(matrix.rows)} configs)")
    print(f"Wrote {ranking_path} ({len(ranking)} rows)")


if __name__ == "__main__":
    asyncio.run(main())
