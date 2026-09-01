-- Read-only queries backing the 2026-08-02 ASQ-per-scenario workbook (evaluation/reports/2026-08-02/).
-- Extends the pattern in vps_eval_data_queries_2026-07-31.sql. Run via:
--   docker exec -i campus-va-postgres psql -U assistant_user -d assistant_db --csv -c "<query>"
--
-- The :TRACE_ID_LIST placeholder must be substituted at run time with the trace_id list produced
-- by build_r0x_traceid_map_2026-08-02.py's output CSV (scratch-only, never committed -- trace_ids
-- are not written into this file since a specific run's ID list is scratch-run output, not a
-- reusable query definition).

-- A. Per-turn latency + answer status for every ASQ-linked trace_id
SELECT trace_id, scenario_code, total_latency_ms, answer_status, created_at
FROM chat_evaluation_logs
WHERE trace_id IN (:TRACE_ID_LIST)
ORDER BY trace_id;

-- B. Citation validity rolled up per trace_id (0 rows for a trace = no citations were logged,
-- e.g. fallback/out_of_domain turns -- treat as citation_correct=false downstream, not missing)
SELECT trace_id, count(*) AS n_citations, count(*) FILTER (WHERE is_valid = true) AS n_valid_citations
FROM citation_evaluation_logs
WHERE trace_id IN (:TRACE_ID_LIST)
GROUP BY trace_id
ORDER BY trace_id;

-- C. Earliest logged chat turn per session_id (anchor for the completion-time proxy: for scenario
-- S1, completion_time = asq_S1.created_at - this value; for S2, completion_time =
-- asq_S2.created_at - asq_S1.created_at, computed in Python since it only needs the ASQ table).
SELECT session_id::text AS session_id, min(created_at) AS first_turn_at
FROM chat_evaluation_logs
WHERE session_id::text IN (SELECT DISTINCT session_id FROM asq_responses WHERE session_id IS NOT NULL)
GROUP BY session_id;

-- D. Sanity check: confirm the reference clean gold-QA run is still present (should return 41 for
-- refresh_20260727_gates_all -- NOT the refresh_20260727b_* family, which is a contaminated sweep
-- run during the 2026-07-27 OpenRouter outage per project memory).
SELECT run_name, created_at FROM evaluation_runs ORDER BY created_at DESC LIMIT 10;

-- E. Per-question detail for the clean run -- category/expected_behavior/fallback_correct back
-- citation-correct rate, hallucination rate, and false-positive rate (of ACIF filtering); grouped
-- aggregation is done in Python for flexibility in slicing by category.
SELECT er.category, er.expected_behavior, er.fallback_correct, er.citation_correct, er.hallucination_detected
FROM evaluation_results er
JOIN evaluation_runs run ON run.id = er.evaluation_run_id
WHERE run.run_name = 'refresh_20260727_gates_all';
