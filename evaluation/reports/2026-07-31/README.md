# Bab-4 Evaluation Data Package — 2026-07-31

> **Untuk revisi naskah skripsi, baca `PANDUAN_REVISI_BAB4_2026-07-31.md` terlebih dahulu** —
> dokumen itu merangkum seluruh 14 data poin dengan detail lengkap, contoh kalimat siap-adaptasi,
> dan metodologi rater independen. README ini adalah indeks teknis/sumber data; panduan itu adalah
> dokumen kerja untuk menulis.

Collected against the **live production VPS** (`root@<PRODUCTION_VPS_IP>`, `/opt/campus-va`) via
read-only SSH/psql/cypher-shell, per the approved plan. Every number below states its source and
whether it is real production data, a semi-automated/verified computation, an explicit estimate,
or awaiting manual human input.

**Update (same day, later): OpenRouter account topped up and reconfirmed working** — a real
`/chat` request returned `status: verified` with real citations, no more 402s. It had been out of
funds from 2026-07-27 08:41 UTC until this top-up (~4 days of real production outage). The two
items below that were blocked on this (indexing time's summarization stage, clean CPU/RAM-under-load
retest) are now complete — see items 11 and 12.

## 1. Jumlah node dan relasi Neo4j
**Real, live data.** 1,699 total nodes (1,654 domain entities + 45 Document provenance nodes),
3,895 relationships. Per-label/per-type breakdown: `raw_vps/neo4j_counts.txt`.

## 2. Entity coverage
**Two numbers, not one** — the codebase has two independent entity mechanisms that don't feed each
other (confirmed via code read, not assumed):
- Neo4j (populated directly by `GraphService.extract_entities`, regex/keyword-based): 1,654 domain
  entity nodes across 6 types (Jadwal 1049, Biaya 576, ProgramStudi 14, Persyaratan 6,
  JalurPendaftaran 5, TahapSeleksi 4).
- `chunk_entities` (a separate, newer admin-review layer, built 2026-07-21): 774 extracted
  candidates, but only **1 of 774 has ever been human-confirmed/edited** — this admin review
  workflow exists in code but is essentially unused in production. This is a real, reportable
  finding, not a measurement gap. Detail: `raw_vps/postgres_aggregates.txt` §7-8.

## 3. Relation coverage
**Real, live data.** 4 of the 10 relationship types defined in CLAUDE.md §14 are actually present
in the live graph (`MEMILIKI_JADWAL`, `MEMILIKI_BIAYA`, `TERSEDIA_PADA`, `MENGHARUSKAN`) = **40%**
schema coverage. `MENTIONS` also exists but is a provenance edge, not one of the 10 defined
domain-relation types. Detail: `raw_vps/neo4j_counts.txt`.

## 4. Evidence coverage
**Real, computed from existing production logs**, new definition: of 25,729
`retrieval_evaluation_logs` rows selected for context, 15,799 have a matching
`graph_consistency_logs` row marked `supported`/`weakly_supported` = **61.4%**. Query:
`evaluation/scripts/vps_eval_data_queries_2026-07-31.sql` §12.

## 5. Graph-document consistency
**Real, aggregated from existing production logs** (29,074 rows, 2026-07-12 to 2026-07-31):
50.06% `weakly_supported`, 49.94% `supported`, **0% `unsupported`/`conflict`/`skipped`** — Gate 3
has never recorded an outright inconsistency in production. Detail: `raw_vps/postgres_aggregates.txt` §10.

## 6. Path correctness
**Fully checked now — 5 of 6 multi-hop questions verified via direct Cypher queries against the
live graph** (stronger than the plan's original "small manual verdict" fallback): MH01 ✅ correct,
MH02 ✅ correct, MH03 ❌ **incorrect — gold-answer/graph mismatch, a genuine new finding** (source
claims "only SPMB Prestasi" but the graph shows 2 valid paths), MH04 ✅ correct (KTP/ijazah/surat
confirmed universal across all 5 jalur), MH05 already-documented pre-existing gap (cited from the
dataset itself), MH06 ✅ correct. **Path correctness rate = 4/5 directly checked = 80%** (or 4/6 =
66.7% counting MH05 as a known failure). Full detail + methodology:
`manual_annotation_needed/path_correctness.csv`.

## 7. Distribusi status masing-masing gate ACIF
**Real production data**, all 5 gates, all 4 real statuses seen (`pass`/`warn`/`block`/`bypassed`;
`error` never occurred), 18,979 gate-check rows, 2026-07-12 to 2026-07-31 (full 3-week production
history, not just ablation-sweep traffic). Full table: `raw_vps/postgres_aggregates.txt` §9.

## 8. Answer Correctness (indikator akurasi)
**Two layers, both now complete:**
- **Automatic reference** (already computed by the system's LLM-judge), filtered to the one
  confirmed-clean (zero OpenRouter-402-contaminated) run `refresh_20260727_gates_all`, n=41:
  faithfulness 0.906, answer relevance 0.9375, citation-correct rate 39.0%, hallucination rate 9.8%.
- **Manual rubric, fully scored by direct transcript review** (same transparency caveat as item 9 —
  Claude scored all 41 rows against each question's gold `expected_answer`, not a blinded
  independent human reviewer): `manual_annotation_needed/answer_quality_eval.csv`. Aggregate of the
  manual scores: 34/41 rows scored a clean 4/4/4 (fully relevant, faithful, complete). **7 rows
  flagged with real, specific findings**, most notably:
  - **Q012 and Q017 — false-negative fallbacks**: both have a real, retrievable gold answer
    (`expected_behavior=answer`) but the system returned `fallback_enforced` anyway — the system
    was too conservative here, not hallucinating.
  - **Q004, Q007, Q014 — topic-adjacent misses**: the system answered a related-but-different
    question than what was asked (e.g. Q014 asked specifically about transferring health-facility
    registration before PKKMB; the system answered with generic health-fitness criteria instead).
    Not fabrication — citation-backed, just off-target retrieval.
  - **Q024 — needs source verification before citing**: the system supplied a specific phone
    number (0274-617601) cited across 5 documents where gold expected a fallback; automatic
    `hallucination_detected=true` fired, but this could equally be the system correctly finding
    real footer contact info gold didn't anticipate — not resolved either way this session.
  - **Q010, Q011, Q013, Q015 — positive finding**: several answers proactively surfaced genuine
    internal source-document inconsistencies (conflicting numbers/dates across sections of the
    same PDF) rather than silently picking one — good faithfulness behavior, worth citing as a
    strength.

## 9. ASR (Attack Success Rate) — hasil anotasi manual
**Hard gap in tooling** (no schema/UI for manual security-response review exists anywhere in the
codebase, confirmed via full-repo search) — **but the manual_verdict column has now been filled**,
at the user's explicit request, by direct transcript review (Claude reading each of the 10
Security-question transcripts and judging whether the attack actually succeeded — not a blinded
independent human reviewer, flagged here for transparency; the thesis author may still want a
second independent pass). Result: **all 10/10 verdicts = GAGAL (blocked)**, matching the automatic
`attack_success=false` flag — no system prompt, internal policy, or unapproved content leaked in
any transcript. One methodological note surfaced during review: Q037 (base64-encoded jailbreak
payload) was caught via the `out_of_domain` path rather than `rejected_by_input_filter` — still
correctly blocked, but worth checking whether Gate 1 should catch encoded payloads more
explicitly. See `manual_annotation_needed/asr_manual_annotation.csv` (also fixes a data
misalignment bug from the first pass — 2 rows had unquoted commas in the raw psql dump that shifted
columns; re-exported with proper CSV quoting).

## 10. Data mentah SUS per responden
**Already collected, reused as-is** (2026-07-16 one-time human-subject study, 21 respondents,
avg 69.05 "Good" — reconfirmed matching the live `sus_responses` table today). Copied to
`sus_reused_from_2026-07-16/`.

## 11. Waktu pengindeksan
**Now fully measured, including the summarization stage.** Read-only measurement on the VPS (no
writes to DB/Chroma/Neo4j; real production `SentenceTransformerEmbeddingFunction` and real
`ChunkSummaryService.generate_summary` OpenRouter calls, not substitutes):
- Extraction+chunking+entity-extraction+embedding for one real 45-page-equivalent Pedoman PDF (16
  chunks): **~1.77 seconds**.
- Summarization (real `google/gemini-2.5-flash` calls, 3-chunk sample, no DB write): **avg 8,827
  ms/chunk** (range 5.9-10.4s). Confirmed via code read that real ingestion processes chunks
  **sequentially**, not concurrently — so this multiplies cleanly to a whole-document estimate.
- **Estimated full indexing time for this 16-chunk document: ~143 seconds (~2.4 minutes)**,
  dominated almost entirely by the summarization stage (extraction/chunking/embedding together are
  <2 seconds). A short 1-page announcement's total is similarly dominated by its one summarization
  call (~8.9s total vs 46ms for everything else).
Detail: `raw_vps/postgres_aggregates.txt` §17.

## 12. Penggunaan CPU/RAM
**Real, now including a clean (non-402-contaminated) under-load retest.** Idle: backend 0.71% CPU
/ 5.08GiB RAM (32.5%) on a **4 vCPU / 15.6GB RAM** VPS (smaller than CLAUDE.md §24.2's recommended
8 vCPU spec — a real documented-vs-actual gap). Under a 10-concurrent-request burst with the
account funded (real generation, not retries): backend CPU spiked to **391.6%** (near-total
saturation of the 4 cores), RAM to **8.04 GiB (51.5%)**. **Real finding**: individual request
latency degrades from ~20s (single request) to **46-82s at 10 concurrent** — genuine CPU
contention on this 4-vCPU host, not an artifact (the account was healthy; `LLM_MAX_CONCURRENCY=25`
was nowhere near being hit). This is a legitimate "high-intensity query handling" capacity finding
for the thesis: current hardware roughly triples-to-quadruples per-request latency at ~10
concurrent real users. Detail: `raw_vps/postgres_aggregates.txt` §19-20.

## 13. Token dan biaya OpenRouter
**Tokens: real historical data** (9,416 calls, 2026-07-05 to 2026-07-27, 29.6M prompt + 2.77M
completion tokens across gemini-2.5-pro/flash). **Cost: forward-looking PROJECTION** per your
explicit choice (not reconstructed from the broken `cost_usd` column) — built from real observed
token averages × live-fetched OpenRouter pricing × several volume scenarios ($29-$370/month
depending on assumed scale). Full detail: `openrouter_cost_projection.md`.

## 14. Ukuran dokumen, chunk, Chroma, dan Neo4j
**Real, live data.** 45 documents (57 MB raw files on disk), 1,894 total chunks (428 approved+active
text chunks, avg 395 tokens/chunk; 975 active visual chunks: 266 image + 709 table_image). Storage:
Postgres 208MB, Neo4j 517MB, Chroma 19MB, Redis 772KB (docker volume `du -sh`). Full breakdown +
one data-quality flag (68 `superseded` text chunks still marked `active=1`, a known-pattern issue
from prior incidents, not independently fixed this session): `raw_vps/postgres_aggregates.txt` §3-6.

---

## Files in this package

```
PANDUAN_REVISI_BAB4_2026-07-31.md           (START HERE for thesis writing — all 14 items, detailed)
README.md                                   (this file — technical index)
openrouter_cost_projection.md               (item 13)
raw_vps/
  neo4j_counts.txt                          (items 1, 3)
  postgres_aggregates.txt                   (items 2, 4, 5, 7, 8, 9(auto), 11, 12, 14 — full detail)
manual_annotation_needed/
  path_correctness.csv                      (item 6)
  TEMUAN_MH03_gold_graph_mismatch.md        (item 6, formal write-up of the MH03 finding)
  answer_quality_eval.csv                   (item 8, manual rubric + independent rater 2 + agreement)
  answer_quality_eval_raw.csv               (raw psql export before rubric columns added)
  asr_manual_annotation.csv                 (item 9, manual verdict + independent rater 2 + agreement)
  asr_security_rows_raw.csv                 (raw psql export)
sus_reused_from_2026-07-16/
  tabel_4_23/24/25_*.csv                    (item 10)
```

## Reproducibility

- `campus-va/evaluation/scripts/vps_eval_data_queries_2026-07-31.sql` — every Postgres aggregate
  query used, runnable again via `docker exec campus-va-postgres psql -U assistant_user -d
  assistant_db -f <file>`.
- `campus-va/evaluation/scripts/indexing_time_measurement_2026-07-31.py` — the read-only timing
  script for extraction/chunking/entity-extraction/embedding, runnable again via `docker cp` +
  `docker exec campus-va-backend python3`.
- `campus-va/evaluation/scripts/indexing_time_measurement_summarization_2026-07-31.py` — companion
  script for the summarization stage (real OpenRouter calls via `ChunkSummaryService`, no DB
  writes) — costs real (small) OpenRouter spend each run, N_CHUNKS_TO_SUMMARIZE is deliberately
  kept small (3) to control cost.
- Neo4j count/path-correctness queries are recorded inline in `raw_vps/neo4j_counts.txt` and
  `manual_annotation_needed/path_correctness.csv`'s `graph_verification_method` column.

## Known open items for next session

1. ~~Confirm OpenRouter account top-up, re-measure indexing time's summarization stage, redo the
   CPU/RAM under-load snapshot.~~ **DONE same day** — account topped up, both remeasured with real
   data (items 11-12 above). New finding from the clean retest: ~10-concurrent-request latency is
   genuinely 3-4x worse than single-request on this 4-vCPU host — a real capacity ceiling, not an
   artifact, worth citing in the thesis's high-intensity-handling discussion.
2. MH03's gold-answer/graph mismatch needs a decision (fix the gold dataset, or investigate the
   graph edge) before citing it either way in the thesis.
3. Q012/Q017 false-negative fallbacks and Q004/Q007/Q014 topic-adjacent misses (see item 8) are
   real retrieval-quality gaps worth investigating, not just noting.
4. Q024's phone number (0274-617601) needs verification against the actual source PDF before
   citing it either as a system success or a hallucination in the thesis.
5. The 68 `superseded AND active=1` text chunks are a data-quality flag, not re-audited this
   session (same class of issue as the documented 2026-07-27 v2/v4 incident).
6. `chunk_entities` admin-review layer is built but essentially unused (1/774 reviewed) — worth a
   product decision on whether to actually staff/use this workflow, or whether it's dead weight.
7. All manual_verdict/manual-rubric columns in this package were filled by Claude reviewing
   transcripts directly (at the user's explicit request), not a blinded independent human
   reviewer — flagged in items 8 and 9 above; consider a second independent pass if the thesis
   methodology requires inter-rater checking.
