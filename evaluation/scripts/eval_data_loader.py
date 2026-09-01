"""Shared data loaders for the 2026-07-24 N-gate ablation evidence workbook.

Must be run where the `app` package + a live DB connection are available (i.e. inside the
campus-va-backend container via `docker exec`, or a host venv with DATABASE_URL pointed at the
same Postgres). Not part of the backend package itself -- one-shot thesis tooling, mirroring
generate_charts.py's existing "standalone tooling that only reads/writes evaluation artifacts"
convention.

Fixes the one known gap in `app.evaluation.ablation_matrix_report`: `build_gate_impact_ranking`
looks up the literal key "gates_all_minus_5", but that run was never executed separately (it is
mathematically identical to "gates_1_2_3_4", already run, per the 2026-07-24 ablation session
notes) -- so without the alias below, gate 5's row is silently missing from the ranking. This
file does the aliasing in new code only; `ablation_matrix_report.py`'s already-tested functions
are reused unmodified.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models import EvaluationResult
    from app.evaluation.ablation_matrix_report import AblationMatrixReport

# NOTE: `app.*`/`sqlalchemy` imports are deferred into the functions below (not module-level)
# so this file can also be imported standalone by build_lampiran_excel.py/build_chatlog_excel.py
# for the pandas-only helpers further down, without requiring the backend package or a DB
# connection -- only load_results_by_config/build_gap_fixed_matrix/main need them, and those are
# meant to run inside the campus-va-backend container via `docker exec`.

ABLATION_CONFIG_NAMES = [
    "gates_all",
    "gates_none",
    "gates_1",
    "gates_1_2",
    "gates_1_2_3",
    "gates_1_2_3_4",
    "gates_all_minus_1",
    "gates_all_minus_2",
    "gates_all_minus_3",
    "gates_all_minus_4",
]


async def load_results_by_config(db: "AsyncSession", config_names: list[str]) -> dict[str, list["EvaluationResult"]]:
    """Most-recent EvaluationRun per config_name -- same convention as
    ablation_matrix_report._load_latest_results_by_config (not imported directly since it's a
    module-private helper), reproduced here so this file has no private-API dependency."""
    from sqlalchemy import select

    from app.db.models import EvaluationResult, EvaluationRun

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
            continue
        rows = (
            await db.execute(select(EvaluationResult).where(EvaluationResult.evaluation_run_id == run.id))
        ).scalars().all()
        results_by_config[config_name] = list(rows)
    return results_by_config


def build_gap_fixed_matrix(results_by_config: dict[str, list["EvaluationResult"]]) -> "AblationMatrixReport":
    """Apply the gates_all_minus_5 <-> gates_1_2_3_4 alias (identical gate-subset, saves a run)
    before building the matrix, so build_gate_impact_ranking's gate-5 lookup resolves."""
    from app.evaluation.ablation_matrix_report import build_ablation_matrix

    aliased = dict(results_by_config)
    if "gates_1_2_3_4" in aliased and "gates_all_minus_5" not in aliased:
        aliased["gates_all_minus_5"] = aliased["gates_1_2_3_4"]
    return build_ablation_matrix(aliased)


async def main() -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app.evaluation.ablation_matrix_report import build_gate_impact_ranking

    engine = create_async_engine(settings.database_url)
    db_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with db_factory() as db:
        results_by_config = await load_results_by_config(db, ABLATION_CONFIG_NAMES)
    await engine.dispose()

    matrix = build_gap_fixed_matrix(results_by_config)
    ranking = build_gate_impact_ranking(matrix)

    out_dir = Path("data/evaluation_reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = out_dir / "ablation_matrix_summary_fixed.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        metric_names = list(matrix.rows[0].aggregate_metrics.keys())
        writer = csv.DictWriter(f, fieldnames=["config_name", "gate_count", "disabled_gates", "n_questions", *metric_names])
        writer.writeheader()
        for row in matrix.rows:
            writer.writerow({
                "config_name": row.config_name,
                "gate_count": row.gate_count,
                "disabled_gates": ",".join(str(g) for g in row.disabled_gates),
                "n_questions": row.n_questions,
                **row.aggregate_metrics,
            })

    ranking_path = out_dir / "gate_impact_ranking_fixed.csv"
    with open(ranking_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "gate_number", "metric", "gates_all_value", "gates_all_minus_n_value",
            "delta", "percent_change", "significant",
        ])
        writer.writeheader()
        for row in ranking:
            writer.writerow({
                "gate_number": row.gate_number,
                "metric": row.metric,
                "gates_all_value": row.gates_all_value,
                "gates_all_minus_n_value": row.gates_all_minus_n_value,
                "delta": row.delta,
                "percent_change": row.percent_change,
                "significant": row.significant,
            })

    print(f"Wrote {summary_path} ({len(matrix.rows)} configs)")
    print(f"Wrote {ranking_path} ({len(ranking)} gate/metric rows)")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())


# ---------------------------------------------------------------------------
# Pandas-based helpers for the Excel-workbook build scripts (build_lampiran_excel.py,
# build_chatlog_excel.py). These run against the local `raw_exports/*.csv` files pulled from
# the VPS -- no DB/app-package dependency, unlike the async loaders above.
# ---------------------------------------------------------------------------

NA = "N/A"


def na(reason: str) -> str:
    return f"{NA} - {reason}"


def fmt_bool(v, true_txt="t", false_txt="f", na_reason: str | None = None):
    import pandas as pd

    if v is None or (isinstance(v, float) and pd.isna(v)):
        return na(na_reason) if na_reason else NA
    return true_txt if bool(v) else false_txt


def fmt_score(v, na_reason: str = "LLM-judge tidak menilai (jawaban ditolak/fallback atau tidak ada konteks)"):
    import pandas as pd

    if v is None or (isinstance(v, float) and pd.isna(v)):
        return na(na_reason)
    return round(float(v), 4)


def format_gate_block(gate_row) -> str:
    """One GATE N - Aksi cell, mirroring the 2026-07-23 workbook's
    'Status: X (Yms)\\nAksi: ...\\nRisk level: ...\\nDetail: ...' shape."""
    if gate_row is None:
        return na("gate tidak dijalankan pada trace ini")
    status = str(gate_row.get("gate_status", "")).upper()
    latency = gate_row.get("latency_ms")
    latency_txt = f"{int(latency)}ms" if latency == latency and latency is not None else "?ms"
    action = gate_row.get("action_taken") or ""
    risk = gate_row.get("risk_level") or ""
    detail = gate_row.get("public_summary") or gate_row.get("admin_summary") or ""
    return f"Status: {status} ({latency_txt})\nAksi: {action}\nRisk level: {risk}\nDetail: {detail}"


def format_retrieval_block(retrieval_rows: list[dict]) -> str:
    if not retrieval_rows:
        return na("tidak ada chunk yang diambil (mis. rejected_by_input_filter/out_of_domain)")
    lines = []
    for i, r in enumerate(sorted(retrieval_rows, key=lambda x: (x.get("retrieval_rank") or 999)), start=1):
        title = r.get("document_title") or "(dokumen tidak diketahui)"
        source = r.get("retrieval_source") or "?"
        ctype = r.get("chunk_type") or "text"
        score = r.get("retrieval_score")
        score_txt = f"{float(score):.3f}" if score == score and score is not None else "-"
        used = "-> DIPAKAI" if r.get("selected_for_context") in (True, "t", "True") else (
            f"-> ditolak - alasan: {r.get('rejected_reason')}" if r.get("rejected_reason") else "-> ditolak"
        )
        lines.append(f"[{i}] {title} (sumber={source}, tipe={ctype}, skor={score_txt}) {used}")
    return "\n".join(lines)


def format_citation_block(citation_rows: list[dict]) -> str:
    if not citation_rows:
        return na("tidak ada sitasi (jawaban fallback/tanpa sumber)")
    lines = []
    for r in citation_rows:
        title = r.get("document_title") or "(dokumen tidak diketahui)"
        page = r.get("page_number")
        page_txt = f", hal. {int(page)}" if page == page and page is not None else ""
        valid = "valid" if r.get("is_valid") in (True, "t", "True") else "tidak valid"
        lines.append(f"{title}{page_txt} [{valid}]")
    return "\n".join(lines)


def format_score_block(result_row: dict) -> str:
    parts = []
    for label, key in [
        ("Precision@3", "precision_at_3"), ("Recall@3", "recall_at_3"), ("Hit Rate@3", "hit_rate_at_3"),
        ("Faithfulness", "faithfulness_score"), ("Relevansi", "answer_relevance_score"),
    ]:
        v = result_row.get(key)
        if v is not None and v == v:
            parts.append(f"{label}={round(float(v), 3)}")
    return "; ".join(parts) if parts else na("belum ada skor evaluasi terstruktur untuk baris ini")


ABLATION_LABELS = {
    "gates_none": "Semua Gate Nonaktif (0 Gate)",
    "gates_1": "Hanya Gate 1 Aktif",
    "gates_1_2": "Gate 1-2 Aktif",
    "gates_1_2_3": "Gate 1-3 Aktif",
    "gates_1_2_3_4": "Gate 1-4 Aktif",
    "gates_all_minus_1": "Semua Gate kecuali Gate 1",
    "gates_all_minus_2": "Semua Gate kecuali Gate 2",
    "gates_all_minus_3": "Semua Gate kecuali Gate 3",
    "gates_all_minus_4": "Semua Gate kecuali Gate 4",
    "gates_all": "Semua Gate Aktif (5 Gate)",
}


def load_raw_exports(raw_dir):
    """Load all 2026-07-24 raw_exports CSVs into a dict of DataFrames, keyed by short name."""
    import pandas as pd
    from pathlib import Path

    raw_dir = Path(raw_dir)
    names = [
        "evaluation_runs", "evaluation_results", "chat_evaluation_logs",
        "acif_trace_logs", "retrieval_evaluation_logs", "citation_evaluation_logs",
    ]
    return {name: pd.read_csv(raw_dir / f"export_{name}.csv") for name in names}


def load_gold_qa(path) -> dict:
    import json

    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out[row["id"]] = row
    return out


def build_sheet2_rows(dfs: dict, gold_qa: dict, config_names: list[str]) -> list[dict]:
    """Build the 21-column 'Hasil Evaluasi per Soal' rows for the 10 x 41 = 410 new ablation
    results, matching the existing 2026-07-23 workbook's exact column schema."""
    import pandas as pd

    runs = dfs["evaluation_runs"].set_index("id")
    results = dfs["evaluation_results"]
    rows = []
    for _, r in results.iterrows():
        run = runs.loc[r["evaluation_run_id"]]
        config_name = run["config_name"]
        gq = gold_qa.get(r["question_id"], {})
        category = r.get("category") or gq.get("category")
        is_security = category == "Security"
        citation_present = r.get("citation_present")
        rows.append({
            "Kode Soal": r["question_id"],
            "Kategori": category,
            "Kondisi ACIF": f"ABLATION 2026-07-24: {ABLATION_LABELS.get(config_name, config_name)}",
            "Nama Run Evaluasi": run["run_name"],
            "Tanggal Run": str(run["created_at"])[:19],
            "Expected Behavior": r.get("expected_behavior") or gq.get("expected_behavior"),
            "Precision@3": r.get("precision_at_3"),
            "Recall@3": r.get("recall_at_3"),
            "Hit Rate@3": r.get("hit_rate_at_3") if pd.notna(r.get("hit_rate_at_3")) else na(
                "ground truth (expected_chunk_ids) belum dipin untuk soal ini"),
            "Sitasi Ada?": fmt_bool(citation_present),
            "Sitasi Benar?": fmt_bool(r.get("citation_correct"), na_reason="tidak ada sitasi untuk dinilai")
                if citation_present in (True, "t") else na("tidak ada sitasi untuk dinilai"),
            "Fallback Tepat?": fmt_bool(r.get("fallback_correct"), na_reason="jawaban bukan fallback/reject, penilaian fallback tidak berlaku"),
            "Skor Relevansi Jawaban": fmt_score(r.get("answer_relevance_score")),
            "Skor Faithfulness": fmt_score(r.get("faithfulness_score")),
            "Terdeteksi Halusinasi?": fmt_bool(r.get("hallucination_detected"), na_reason="LLM-judge tidak menilai (jawaban ditolak/fallback atau tidak ada konteks)"),
            "Serangan Berhasil?": fmt_bool(r.get("attack_success"), na_reason="tidak dapat dinilai") if is_security
                else na("kategori soal bukan Security, uji serangan tidak berlaku"),
            "Latency Total (ms)": r.get("total_latency_ms"),
            "Latency Retrieval (ms)": r.get("retrieval_latency_ms"),
            "Latency LLM (ms)": r.get("llm_latency_ms"),
            "Trace ID": r.get("trace_id"),
            "Catatan": None,
        })
    return rows


def build_sheet3_rows(dfs: dict) -> list[dict]:
    """Build the 27-column 'Log Chat Lengkap' narrative rows for the same 410 traces."""
    import pandas as pd

    runs = dfs["evaluation_runs"].set_index("id")
    results = dfs["evaluation_results"].set_index("trace_id")
    chats = dfs["chat_evaluation_logs"]
    gates = dfs["acif_trace_logs"]
    retrievals = dfs["retrieval_evaluation_logs"]
    citations = dfs["citation_evaluation_logs"]

    gates_by_trace = {tid: g.sort_values("gate_number") for tid, g in gates.groupby("trace_id")}
    retrieval_by_trace = {tid: g.to_dict("records") for tid, g in retrievals.groupby("trace_id")}
    citation_by_trace = {tid: g.to_dict("records") for tid, g in citations.groupby("trace_id")}

    rows = []
    for _, chat in chats.iterrows():
        tid = chat["trace_id"]
        er = results.loc[tid] if tid in results.index else None
        run_name = runs.loc[er["evaluation_run_id"]]["run_name"] if er is not None else None
        g = gates_by_trace.get(tid)
        gate_lookup = {int(row["gate_number"]): row for _, row in g.iterrows()} if g is not None else {}

        def gate_cell(n):
            row = gate_lookup.get(n)
            return format_gate_block(row.to_dict() if row is not None else None)

        rows.append({
            "Trace ID": tid,
            "Waktu (UTC)": str(chat["created_at"])[:26],
            "Mode Chat": "EVALUASI ABLASI 2026-07-24 (Gold QA)",
            "Kode Soal Terkait": er.name if False else (er["question_id"] if er is not None else None),
            "Nama Run Evaluasi": run_name,
            "Pertanyaan Pengguna": chat.get("user_question"),
            "Pertanyaan Ternormalisasi": chat.get("normalized_question"),
            "Intent Terdeteksi": f"{chat.get('intent')} (confidence={chat.get('intent_confidence')})" if pd.notna(chat.get("intent")) else None,
            "Jawaban Akhir": chat.get("final_answer"),
            "Status Jawaban": chat.get("answer_status"),
            "Fallback Terpicu?": fmt_bool(chat.get("fallback_triggered")),
            "Alasan Fallback": chat.get("fallback_reason") if pd.notna(chat.get("fallback_reason")) else na("tidak ada fallback"),
            "GATE 1 - Aksi (Input Intent Integrity Check)": gate_cell(1),
            "GATE 2 - Aksi (Retrieval Context Integrity Scoring)": gate_cell(2),
            "GATE 3 - Aksi (Graph-Document Consistency Check)": gate_cell(3),
            "GATE 4 - Aksi (Prompt Boundary Construction)": gate_cell(4),
            "GATE 5 - Aksi (Output Claim Verification)": gate_cell(5),
            "RETRIEVAL - Dokumen & Chunk yang Diambil": format_retrieval_block(retrieval_by_trace.get(tid, [])),
            "GRAPH - Entitas & Relasi yang Diambil": na("graph_consistency_logs tidak diekspor terpisah pada sesi ini - lihat GATE 3 di atas untuk ringkasan konsistensi graph"),
            "SITASI - Sumber yang Dikutip di Jawaban": format_citation_block(citation_by_trace.get(tid, [])),
            "SKOR EVALUASI": format_score_block(er.to_dict()) if er is not None else na("bukan bagian dari evaluation_results"),
            "Model LLM": chat.get("model_used"),
            "Token In/Out": f"{chat.get('input_tokens')}/{chat.get('output_tokens')}",
            "Estimasi Biaya (USD)": chat.get("estimated_cost"),
            "Latency Total (ms)": chat.get("total_latency_ms"),
            "Latency Retrieval/Graph/ACIF/LLM/Verifikasi (ms)": (
                f"{chat.get('retrieval_latency_ms')}/{chat.get('graph_latency_ms')}/{chat.get('acif_latency_ms')}/"
                f"{chat.get('llm_latency_ms')}/{chat.get('output_verification_latency_ms')}"
            ),
            "Session ID": chat.get("session_id"),
            "Error": chat.get("error_message") if pd.notna(chat.get("error_message")) else None,
        })
    return rows
