\echo '=== 1. document counts by status ==='
SELECT status, count(*) FROM documents GROUP BY status ORDER BY count(*) DESC;

\echo '=== 2. document counts by type (active only) ==='
SELECT document_type, count(*) FROM documents WHERE status = 'active' GROUP BY document_type ORDER BY count(*) DESC;

\echo '=== 3. chunk counts by status/type ==='
SELECT chunk_type, status, active, count(*) FROM document_chunks GROUP BY chunk_type, status, active ORDER BY count(*) DESC;

\echo '=== 4. chunk token_count stats (approved+active text chunks) ==='
SELECT count(*), avg(token_count), sum(token_count), avg(length(original_text)), sum(length(original_text))
FROM document_chunks WHERE chunk_type='text' AND status='approved' AND active > 0;

\echo '=== 5. table sizes (pretty) ==='
SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC LIMIT 15;

\echo '=== 6. chunk_entities status counts ==='
SELECT entity_type, status, count(*) FROM chunk_entities GROUP BY entity_type, status ORDER BY entity_type, status;

\echo '=== 7. chunk_entities distinct confirmed/detected entity text count ==='
SELECT count(DISTINCT coalesce(corrected_text, detected_text)) AS distinct_entities_confirmed
FROM chunk_entities WHERE status IN ('confirmed','edited');
SELECT count(DISTINCT coalesce(corrected_text, detected_text)) AS distinct_entities_all_nonrejected
FROM chunk_entities WHERE status != 'rejected';

\echo '=== 8. acif_trace_logs gate x status distribution ==='
SELECT gate_number, gate_name, gate_status, count(*)
FROM acif_trace_logs GROUP BY gate_number, gate_name, gate_status ORDER BY gate_number, gate_status;

\echo '=== 9. acif_trace_logs total row count + date range ==='
SELECT count(*), min(created_at), max(created_at) FROM acif_trace_logs;

\echo '=== 10. graph_consistency_logs status distribution ==='
SELECT consistency_status, count(*) FROM graph_consistency_logs GROUP BY consistency_status ORDER BY count(*) DESC;

\echo '=== 11. graph_consistency_logs total + date range ==='
SELECT count(*), min(created_at), max(created_at) FROM graph_consistency_logs;

\echo '=== 12. evidence coverage: selected_for_context retrieval rows with/without graph support ==='
SELECT
  count(*) FILTER (WHERE r.selected_for_context = true) AS selected_total,
  count(*) FILTER (
    WHERE r.selected_for_context = true
    AND EXISTS (
      SELECT 1 FROM graph_consistency_logs g
      WHERE g.trace_id = r.trace_id
      AND g.consistency_status IN ('supported','weakly_supported')
    )
  ) AS selected_with_graph_support
FROM retrieval_evaluation_logs r;

\echo '=== 13. openrouter_usage_logs token totals by model ==='
SELECT model, count(*) AS calls, sum(prompt_tokens) AS total_prompt_tokens, sum(completion_tokens) AS total_completion_tokens,
  avg(prompt_tokens) AS avg_prompt_tokens, avg(completion_tokens) AS avg_completion_tokens
FROM openrouter_usage_logs GROUP BY model ORDER BY calls DESC;

\echo '=== 14. openrouter_usage_logs date range + total calls ==='
SELECT count(*), min(created_at), max(created_at) FROM openrouter_usage_logs;

\echo '=== 15. chat_evaluation_logs token totals (fallback source, non-null) ==='
SELECT model_used, count(*), sum(input_tokens), sum(output_tokens), avg(input_tokens), avg(output_tokens)
FROM chat_evaluation_logs WHERE input_tokens IS NOT NULL GROUP BY model_used;

\echo '=== 16. chat_evaluation_logs answer_status distribution (all time) ==='
SELECT answer_status, count(*) FROM chat_evaluation_logs GROUP BY answer_status ORDER BY count(*) DESC;

\echo '=== 17. sus_responses count + score summary ==='
SELECT count(*), avg(sus_score), min(sus_score), max(sus_score) FROM sus_responses;

\echo '=== 18. asq_responses count ==='
SELECT count(*), avg(average_score) FROM asq_responses;

\echo '=== 19. evaluation_results answer correctness composite (latest run per config, avg) ==='
SELECT
  count(*) AS n,
  avg(faithfulness_score) AS avg_faithfulness,
  avg(answer_relevance_score) AS avg_answer_relevance,
  avg(CASE WHEN citation_correct THEN 1.0 ELSE 0.0 END) AS citation_correct_rate,
  avg(CASE WHEN hallucination_detected THEN 1.0 ELSE 0.0 END) AS hallucination_rate
FROM evaluation_results
WHERE faithfulness_score IS NOT NULL OR answer_relevance_score IS NOT NULL;

\echo '=== 20. evaluation_runs list (recent) ==='
SELECT run_name, created_at FROM evaluation_runs ORDER BY created_at DESC LIMIT 20;

\echo '=== 21. security-category chat logs for ASR manual annotation ==='
SELECT count(*) FROM evaluation_results WHERE category = 'Security';

\echo '=== 22. total document count + total corpus token_count all statuses ==='
SELECT count(*) FROM documents;
SELECT count(*) FROM document_chunks;
