"""Build a fresh, self-contained R01-R22 anonymization of the ASQ raw usability-study data,
recovering trace_id/session_id for internal linkage to objective system logs (latency, task
success, citation correctness) by scenario.

Why this exists: the project's only existing anonymized ASQ export
(evaluation/reports/2026-07-16/sus_asq_final/asq_responses_anonymized.csv) has no trace_id/
session_id column, so it cannot be joined to chat_evaluation_logs/citation_evaluation_logs.
Reverse-matching it back to the un-anonymized root-level `asq_responses.csv` (outside campus-va/,
real participant names) was attempted by content (scenario+3 item scores) and by chronological
order -- both failed to validate cleanly (heavy score ties; the old export's ordering isn't a pure
timestamp sort either). Reverse-matching two independently-anonymized exports is fragile and risks
silently mislabeling respondents, which would corrupt every downstream per-scenario/correlation
metric. So this script defines ITS OWN new R01-R22 labeling directly from the root file (which
already has participant_code, scenario_code, scores, trace_id, session_id together) -- no
cross-file matching needed. Labels are assigned by chronological order of each participant's
earliest scenario submission. This labeling is workbook-internal for the 2026-08-02 report; it
does not need to (and does not) match the R01-R22 codes used in the 2026-07-16 report, since both
ultimately derive from the same 43 raw rows and produce identical aggregate statistics regardless
of which respondent is labeled "R03" vs "R19" (verified: grand mean of average_score reproduces
the known reference value of 5.76/7 from prior reports).

PRIVACY: real participant_code (names/handles) from the root file is used only to group rows
during the chronological sort below and is discarded immediately after -- it is never written to
this script's output. The output DOES contain trace_id/session_id (needed for the next step's VPS
join) and MUST stay out of the campus-va/ repo tree -- write it only to a scratch/temp directory,
never commit it.

Usage:
    python build_r0x_traceid_map_2026-08-02.py --root-csv <path to root asq_responses.csv> --out <scratch output path>
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def load_root(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "participant_code": r["participant_code"],
                "scenario_code": r["scenario_code"],
                "session_id": r["session_id"] or None,
                "trace_id": r["trace_id"] or None,
                "asq_1": int(r["asq_1"]),
                "asq_2": int(r["asq_2"]),
                "asq_3": int(r["asq_3"]),
                "average_score": float(r["average_score"]),
                "created_at": r["created_at"],
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-csv", required=True, type=Path, help="Path to the un-anonymized root asq_responses.csv (outside the repo)")
    parser.add_argument("--out", required=True, type=Path, help="Output CSV path -- MUST be outside campus-va/, never commit this file")
    parser.add_argument("--expected-rows", type=int, default=43)
    parser.add_argument("--expected-participants", type=int, default=22)
    args = parser.parse_args()

    root_rows = load_root(args.root_csv)
    if len(root_rows) != args.expected_rows:
        sys.exit(f"FATAL: expected {args.expected_rows} raw ASQ rows, found {len(root_rows)} -- source data changed, re-verify before proceeding.")

    earliest = {}
    for rr in root_rows:
        pc = rr["participant_code"]
        if pc not in earliest or rr["created_at"] < earliest[pc]:
            earliest[pc] = rr["created_at"]
    participants_in_order = sorted(earliest.keys(), key=lambda pc: earliest[pc])
    if len(participants_in_order) != args.expected_participants:
        sys.exit(f"FATAL: expected {args.expected_participants} distinct participants, found {len(participants_in_order)}")

    r0x_by_participant = {pc: f"R{idx + 1:02d}" for idx, pc in enumerate(participants_in_order)}

    out_rows = []
    for rr in root_rows:
        out_rows.append({
            "r0x": r0x_by_participant[rr["participant_code"]],
            "scenario": rr["scenario_code"],
            "asq_1": rr["asq_1"],
            "asq_2": rr["asq_2"],
            "asq_3": rr["asq_3"],
            "average_score": rr["average_score"],
            "trace_id": rr["trace_id"],
            "session_id": rr["session_id"],
            "asq_created_at": rr["created_at"],
        })
    out_rows.sort(key=lambda r: (r["r0x"], r["scenario"]))

    n_total = len(out_rows)
    grand_mean = sum(r["average_score"] for r in out_rows) / n_total
    no_trace = [r for r in out_rows if not r["trace_id"]]
    scenario_counts: dict[str, int] = {}
    for r in out_rows:
        scenario_counts[r["scenario"]] = scenario_counts.get(r["scenario"], 0) + 1

    print(f"n_rows={n_total} distinct_r0x={len(set(r['r0x'] for r in out_rows))}")
    print(f"grand_mean_average_score={grand_mean:.4f} (sanity-check reference from prior reports: 5.76)")
    print(f"rows with NO trace_id: {len(no_trace)} -> {[(r['r0x'], r['scenario']) for r in no_trace]}")
    print(f"scenario counts: {scenario_counts}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["r0x", "scenario", "asq_1", "asq_2", "asq_3", "average_score", "trace_id", "session_id", "asq_created_at"])
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
