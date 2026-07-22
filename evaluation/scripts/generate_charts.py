"""Standalone chart generator for Bab 4.4 figures 4.39/4.40/4.43/4.46/4.48/4.49/4.52.

Not part of the backend package — this is one-shot thesis tooling, run locally with
`pip install matplotlib pandas` in a scratch environment. It never touches production; it
only reads the CSVs already exported into evaluation/templates/charts/ and writes PNGs next
to them under evaluation/reports/<date>/figures/.

Usage:
    python evaluation/scripts/generate_charts.py [--out-dir evaluation/reports/2026-07-16/figures]

Each figure function skips gracefully (prints a warning, does not crash the whole run) when
its source CSV still has empty cells for that series — matching the "Belum ada" markers in
evaluation/templates/charts/README_charts.md.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

CHARTS_DIR = Path(__file__).parent.parent / "templates" / "charts"

plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.bbox": "tight",
    "font.size": 10,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.axisbelow": True,
})


def _save(fig, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    fig.savefig(path)
    plt.close(fig)
    print(f"wrote {path}")


def fig_4_39_precision_recall(out_dir: Path) -> None:
    df = pd.read_csv(CHARTS_DIR / "chart_4_39_precision_recall.csv")
    df = df.dropna(subset=["Precision_at_3"])
    if df.empty:
        print("skip 4.39: no rows with Precision_at_3 filled in")
        return
    x = range(len(df))
    width = 0.25
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = {"Precision_at_3": "Precision@3", "Recall_at_3": "Recall@3", "Hit_Rate_at_3": "Hit Rate@3"}
    cols = [c for c in labels if c in df.columns]
    for i, col in enumerate(cols):
        offset = (i - (len(cols) - 1) / 2) * width
        ax.bar([xi + offset for xi in x], df[col], width, label=labels[col])
    ax.set_xticks(list(x))
    ax.set_xticklabels(df["Kategori"], rotation=20, ha="right")
    ax.set_ylabel("Nilai (0-1)")
    ax.set_ylim(0, 1.05)
    ax.set_title("Precision@3, Recall@3, dan Hit Rate@3 per Kategori")
    ax.legend()
    _save(fig, out_dir, "fig_4_39_precision_recall")


def fig_4_40_answer_quality(out_dir: Path) -> None:
    df = pd.read_csv(CHARTS_DIR / "chart_4_40_answer_quality.csv")
    df = df.dropna(subset=["Nilai"])
    if df.empty:
        print("skip 4.40: no rows with Nilai filled in")
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(df["Metrik"], df["Nilai"], color="#4C72B0")
    for i, (val, n) in enumerate(zip(df["Nilai"], df["N"])):
        n_label = "" if pd.isna(n) else f" (n={int(n)})"
        ax.text(i, val, f"{val:g}{n_label}", ha="center", va="bottom", fontsize=8)
    ax.set_ylabel("Nilai")
    ax.set_title("Hasil Evaluasi Kualitas Jawaban")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    _save(fig, out_dir, "fig_4_40_answer_quality")


def fig_4_43_citation(out_dir: Path) -> None:
    df = pd.read_csv(CHARTS_DIR / "chart_4_43_citation.csv")
    x = range(len(df))
    width = 0.35
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar([xi - width / 2 for xi in x], df["Citation_Coverage_pct"], width, label="Citation Coverage (%)")
    ax.bar([xi + width / 2 for xi in x], df["Citation_Correctness_pct"], width, label="Citation Correctness (%)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(df["Kategori"], rotation=20, ha="right")
    ax.set_ylabel("Persentase (%)")
    ax.set_title("Citation Coverage dan Citation Correctness per Kategori")
    ax.legend()
    _save(fig, out_dir, "fig_4_43_citation")


def fig_4_46_acif_gate_distribution(out_dir: Path) -> None:
    df = pd.read_csv(CHARTS_DIR / "chart_4_46_acif_gate_distribution.csv")
    status_cols = ["Pass", "Warn", "Block", "Fallback", "Error"]
    df_data = df.dropna(subset=status_cols, how="all")
    if df_data.empty:
        print("skip 4.46: gate distribution CSV is still empty (see README_charts.md #1)")
        return
    fig, ax = plt.subplots(figsize=(9, 5))
    bottom = [0] * len(df_data)
    for col in status_cols:
        vals = df_data[col].fillna(0)
        ax.bar(df_data["Gate"], vals, bottom=bottom, label=col)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_ylabel("Jumlah")
    ax.set_title("Distribusi Status Gate ACIF")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    ax.legend()
    _save(fig, out_dir, "fig_4_46_acif_gate_distribution")


def _latency_bar(csv_name: str, value_col: str, ylabel: str, title: str, out_name: str, out_dir: Path) -> None:
    df = pd.read_csv(CHARTS_DIR / csv_name)
    df = df.dropna(subset=[value_col])
    if df.empty:
        print(f"skip {out_name}: no rows with {value_col} filled in")
        return
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(df["Komponen"], df[value_col], color="#55A868")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    _save(fig, out_dir, out_name)


def fig_4_48_latency_per_component(out_dir: Path) -> None:
    _latency_bar(
        "chart_4_48_latency_per_component.csv", "Rata_rata_ms", "Milidetik (ms)",
        "Rata-rata Latency per Komponen", "fig_4_48_latency_per_component", out_dir,
    )


def fig_4_49_p95_latency(out_dir: Path) -> None:
    _latency_bar(
        "chart_4_49_p95_latency.csv", "P95_ms", "Milidetik (ms)",
        "P95 Latency per Komponen", "fig_4_49_p95_latency", out_dir,
    )


def fig_4_52_sus_items(out_dir: Path) -> None:
    df = pd.read_csv(CHARTS_DIR / "chart_4_52_sus_items.csv")
    df_items = df[df["Item"] != "Skor SUS Rata-rata Keseluruhan"]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(df_items["Item"], df_items["Rata_rata_Skor"], color="#C44E52")
    ax.axhline(3, color="grey", linestyle="--", linewidth=1)
    ax.set_ylabel("Rata-rata Skor (skala 1-5)")
    ax.set_title("Rata-rata Skor per Item SUS (n=21)")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    _save(fig, out_dir, "fig_4_52_sus_items")


FIGURES = [
    fig_4_39_precision_recall,
    fig_4_40_answer_quality,
    fig_4_43_citation,
    fig_4_46_acif_gate_distribution,
    fig_4_48_latency_per_component,
    fig_4_49_p95_latency,
    fig_4_52_sus_items,
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).parent.parent / "reports" / "figures"),
        help="Directory to write PNGs into.",
    )
    args = parser.parse_args()
    out_dir = Path(args.out_dir)

    for fn in FIGURES:
        fn(out_dir)


if __name__ == "__main__":
    main()
