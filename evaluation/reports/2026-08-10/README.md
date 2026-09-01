# 2026-08-10 — Master Research Dataset (Perception vs. Performance)

See `dataset_reconstruction_report.md` for the full write-up: sources found, how each field was
reconstructed, statistics reproduced vs. not, and reconciliation against the paper's stated numbers.

## Files in this folder

```
research_dataset_perception_performance.xlsx   the 11-sheet master dataset (start at sheet 00_README)
dataset_reconstruction_report.md                full reconstruction/reconciliation write-up
```

## Reproducibility

```
campus-va/evaluation/scripts/build_research_dataset_excel_2026-08-10.py
    python build_research_dataset_excel_2026-08-10.py --input-csv <path to raw_joined_by_scenario.csv>
```

Sole input: `campus-va/evaluation/reports/2026-08-02/raw_joined_by_scenario.csv` (already
anonymized, no PII, no VPS/database access required to rebuild this workbook).
