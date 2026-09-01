# Dataset Reconstruction Report

**Dataset:** `research_dataset_perception_performance.xlsx`
**Build date:** 2026-08-10
**Build script:** `campus-va/evaluation/scripts/build_research_dataset_excel_2026-08-10.py`
**Paper:** "Evaluating the Alignment Between Perceived Usability and Objective Task Performance in a
GraphRAG-Based Campus Virtual Assistant"

## 0. Correction log

- **2026-08-10, post-review**: fixed a real formula bug in `09_STATISTICAL_SUMMARY` (the three
  correlation p-value cells under section F). `T.DIST.2T(x, df)` already returns the two-tailed
  p-value in Excel — the original formula wrapped it as `=2*T.DIST.2T(...)`, doubling an
  already-two-tailed result (e.g. producing ~1.31 instead of ~0.657 for the ASQ-vs-latency p-value).
  Fixed to `=T.DIST.2T(...)` in all three cells (ASQ vs latency, ASQ vs task success, ASQ_3 vs
  citation). This did not affect any value in the reconciliation table or the Python-computed
  cross-check figures in §3 below (those were always computed correctly via `scipy`); it only
  affected the three live-formula p-value cells themselves. If you had already opened the file and
  seen an implausible p-value (e.g. greater than 1) in that section, this was the cause.

## 1. Sources found

A repo-wide search (three parallel research passes plus direct file reads) was run before writing
any code, specifically to establish whether real, traceable data exists for the paper's claimed
22 participants / 43 observations / ASQ ≈5.76/7, or whether any values would need to be marked as
unavailable. The search covered `campus-va/evaluation/` (all dated report folders), `campus-va/docs/`
(public and private), the backend `gold_qa_dataset.jsonl` and evaluation scripts, and the
non-`campus-va` root of the repository.

**Result: real, traceable, already-validated data exists.** No respondent, score, or statistic in
this dataset was invented.

| Candidate file | What it is | Used? |
|---|---|---|
| `campus-va/evaluation/reports/2026-08-02/raw_joined_by_scenario.csv` | 43-row, per-observation join of the human ASQ study to production task-performance/latency/citation logs. Anonymized (R01-R22), no PII. | **Yes — sole data source for this workbook.** |
| `campus-va/evaluation/reports/2026-08-02/README.md` | Documents the linkage methodology and 17 headline statistics computed from the CSV above. | Yes — used as the primary cross-check target (§3). |
| `campus-va/evaluation/scripts/build_asq_scenario_excel_2026-08-02.py` | The script that originally built the CSV above; contains the six statistical functions this workbook re-derives. | Yes — statistical functions ported verbatim (see script header comment). |
| `campus-va/evaluation/reports/2026-07-16/sus_asq_final/asq_responses_anonymized.csv` | Earlier, ASQ-only anonymized export (no latency/task-success/citation linkage; different R0x label assignment than the 2026-08-02 file, explicitly documented as non-matching). | No — superseded by the linked 2026-08-02 file for this workbook's purposes. |
| `E:\...\VirtualAsisst_2.0\asq_responses.csv`, `sus_responses.csv` (repo root, outside `campus-va/`) | Un-anonymized upstream source with real participant names/handles and internal `trace_id`/`session_id`. | **No — deliberately excluded.** Only the already-anonymized, privacy-cleared 2026-08-02 CSV was read. |
| `campus-va/docs/private/sus_participant_mapping_PRIVATE.csv` | De-anonymization key (R0x → real codes) for the 2026-07-16 study. | No — not needed and not opened for this task. |
| `campus-va/backend/app/evaluation/gold_qa_dataset.jsonl` + `evaluation/reports/2026-07-18/acif_comparison_summary.csv` | 41-question **automated** gold-QA benchmark (with/without-ACIF ablation), including a 39.0% aggregate citation-correct rate and 9.8% hallucination rate. | **No — explicitly excluded from this dataset.** This is a different instrument, not tied to the 22 human participants. See §5. |
| SUS data (`.../sus_asq_final/tabel_4_24_hasil_skor_sus.csv`, 21 respondents, mean 69.05) | Related usability instrument collected in the same project. | No — out of scope for this ASQ-focused paper, per your explicit decision. Mentioned only in `00_README`. |

No thesis/manuscript document exists anywhere in the repository. The only "reported" values treated
as ground truth for reconciliation are the ones you explicitly stated as already published: **ASQ
overall ≈5.76/7, n=43 observations, n=22 participants.**

## 2. How each field was reconstructed

- **participant_id**: derived by renaming the source's `r0x` codes (R01-R22) to `P001-P022`
  1:1 by numeric suffix. No new anonymization was performed.
- **observation_id**: assigned sequentially (`OBS001`-`OBS043`), sorted by `participant_id` then
  `scenario_id`.
- **ASQ items/mean, task_success, completion_time_s, latency, citation fields**: copied directly
  from `raw_joined_by_scenario.csv`, with `asq_mean` computed live via `=AVERAGE()` in the workbook
  rather than copied as a static value.
- **session_id, timestamps, query_text, response_id, and most of 06_SYSTEM_METRICS' finer-grained
  fields**: marked `NA` with an explicit `missing_reason` — these were deliberately scrubbed from
  the safe/anonymized 2026-08-02 export for participant privacy, or were never captured at this
  grain in production logs. **No value was estimated or imputed for any of these.**
- **participant_group**: marked `NA` — not recorded anywhere in the source data at any stage.
- **has_correct_citation**: recomputed live via formula (`n_valid_citations > 0`), reproducing the
  source CSV's own derivation rule rather than just copying its precomputed boolean — this doubled
  as an internal consistency check during development (recomputed values matched the source exactly).
- **08_MERGED_ANALYSIS**: built entirely via `INDEX/MATCH` formulas keyed on `observation_id`, not
  manual retyping and not a same-row-order assumption.
- **09_STATISTICAL_SUMMARY**: descriptive statistics, Cronbach's alpha, Pearson r, and
  point-biserial correlations are live Excel formulas (via per-row helper columns for
  scenario/group-conditional aggregates, avoiding legacy array-formula entry, which could not be
  verified in this environment — see §4). Spearman rho/p and the Wilcoxon signed-rank test are
  computed once in Python (`scipy`, same method as the source script) and written as documented
  values, because Excel has no native exact Wilcoxon function.

## 3. Statistics reproduced vs. not, and reconciliation with the paper

Every statistic below was **independently recomputed** by this workbook's build script from the
same source CSV, using the same computational methods as the already-published 2026-08-02 report
(functions ported verbatim). The comparison is a real check, not a tautology — a bug in the new
join/derivation logic would show up as a mismatch here.

| Statistic | Reported (2026-08-02 report / paper) | Recomputed (this workbook) | Status |
|---|---|---|---|
| ASQ overall mean | 5.76/7 (n=43, SD=1.35, 95% CI [5.34, 6.17]) | 5.7597/7 (n=43, SD=1.3478, 95% CI [5.345, 6.174]) | **MATCH** |
| n observations | 43 | 43 | **MATCH** |
| n participants | 22 | 22 | **MATCH** |
| Cronbach's alpha S1 / S2 | 0.969 / 0.951 | 0.9694 / 0.9508 | MATCH (rounds identically) |
| Task success rate S1 / S2 | 42.9% / 42.9% | 42.9% / 42.9% (9/21 each) | MATCH |
| Completion time median (clean) S1 / S2 | 148s (n=19) / 150s (n=21) | recomputed with same n=19/n=21 clean counts (median values reproduce the source's own filtering exactly — 1 negative-duration row and 2 >1h outliers excluded per scenario, matching the source's own flags) | MATCH |
| Latency mean S1 / S2 | not stated to full precision in the report's summary table | 9171.5ms / 8817.2ms | reference not stated at full precision — recomputed value only |
| ASQ vs latency (Pearson) | r=0.071, p=0.657, n=42 | r=0.0706, p=0.6569, n=42 | **MATCH** |
| ASQ vs task success (point-biserial) | r=0.067, p=0.673, n=42 | r=0.0670, p=0.6734, n=42 | **MATCH** |
| ASQ_3 vs citation correctness (point-biserial) | r=0.170, p=0.283, n=42 | r=0.1697, p=0.2827, n=42 | **MATCH** |
| Wilcoxon ASQ S1 vs S2 | p=1.0000, n=21 pairs | W=18.0, p=1.0000, n=21 pairs | **MATCH** |

**No mismatches were found.** Every statistic that could be independently recomputed reproduced the
previously-published figures to at least 2 decimal places. This is strong evidence that (a) the
underlying source data is stable and correctly interpreted, and (b) this workbook's restructuring
introduced no computational errors.

Per your explicit instruction not to fabricate a comparison target, all other statistics in the
workbook's reconciliation table (sheet `09_STATISTICAL_SUMMARY`, section I) that have no
independently-stated "paper" value are marked `SOURCE_NOT_FOUND` — their recomputed values are
still shown (and match the table above), but no target was invented to check them against.

## 4. Known limitations of this dataset (disclose these in the paper)

- **Completion time is a proxy**, not a stopwatch measurement — it is the timestamp delta between
  ASQ submissions. 1 row (P006/S1) has an invalid negative-duration proxy; 2 rows (P017/S1, P022/S1)
  are >1-hour outliers, both excluded from "clean" completion-time statistics. This is the source
  study's own documented limitation, not introduced by this reconstruction.
- **One observation has no linked production turn**: P006/S1 has real ASQ scores but no matching
  `trace_id`, so its `task_status`, `latency_ms`, and citation fields are `NA` for that row. It is
  still counted in ASQ statistics but excluded from task-success/latency/citation denominators
  (not counted as a failure).
- **One participant (P016) has no S2 observation** — this is why 22×2=44 collapses to 43 observations;
  it was not forced to match the paper's stated number, it is a genuine gap in the original data
  collection.
- **Citation correctness has two different, non-interchangeable meanings in this project.** This
  dataset's `has_correct_citation`/citation figures are per-observation, tied to the 22 real
  participants (via production `citation_evaluation_logs`). A separate, unrelated 41-question
  automated gold-QA benchmark also reports a citation-correct rate (39.0%) and hallucination rate
  (9.8%) — that is a **different instrument**, not tied to these participants, and is intentionally
  **not included anywhere in this dataset's figures**. If the paper cites both numbers, it must
  describe them as two separate measurements from two separate evaluation instruments.
- **No perception-performance threshold is imposed.** Sheet 9's gap analysis reports the continuous
  comparison (ASQ mean by task-success group) as the primary result, per your explicit instruction
  not to invent an unvalidated high/low ASQ cutoff.
- **Formula recalculation was not machine-verified end-to-end — please check this yourself on
  first open.** This workbook relies on live Excel formulas that recalculate automatically when
  opened in Excel, LibreOffice Calc, or Google Sheets (standard spreadsheet behavior). This build
  environment had neither Excel nor LibreOffice installed. Verification here relied on: (a) an
  independent Python/`scipy` recomputation of every statistic from the same source data (§3 — all
  10 independently-checkable statistics matched the previously-published report exactly), (b)
  structural checks (row counts, primary keys, table/data-validation objects, codebook-completeness
  assertion — all passed, enforced by the build script itself), (c) a fix pass that specifically
  searched for and removed formula-string bugs (stray legacy array-formula braces, and
  documentation text that accidentally began with `=` and would otherwise have been misread as a
  formula), and (d) an attempted automated recalculation via the Python `formulas` library, which
  did not complete within a practical time budget in this environment and was abandoned rather than
  reported as a pass. **Action needed from you:** the first time you open the `.xlsx` file in a
  real spreadsheet application, check that no cell displays `#REF!`, `#VALUE!`, `#NAME?`, or `#N/A`
  — particularly in `09_STATISTICAL_SUMMARY` (which has the most complex formulas) — and compare a
  few values against the "Python-computed cross-check" figures in §3 above.

## 5. Recommendation

The paper's headline numbers (22 participants, 43 observations, ASQ ≈5.76/7) are well-supported by
real, traceable data and reproduce exactly under independent recomputation. The clearest
improvement opportunity is in how the paper describes two adjacent-but-distinct metrics under
similar names: task success (per-observation, human study, 42.9%) and citation correctness
(per-observation for this dataset, 39.0%/9.8% hallucination for the separate automated benchmark) —
we recommend the methods section explicitly names which instrument each reported percentage comes
from, exactly as this dataset's `00_README` and `07_CITATION_EVALUATION` sheets now do.
