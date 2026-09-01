"""Unit tests for routes_evaluation_admin.py — covers the trace-detail 404 path, latency
filter query construction, the safe-summary serializer never leaking gate internals, and the
with/without-ACIF comparison endpoint (Evaluation Layer Phase 5)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from app.api import routes_evaluation_admin as r
from app.db.models import AcifTraceLog, ChatEvaluationLog, EvaluationResult, EvaluationRun


class TestCsvExportFormatting:
    """2026-07-22: CSV exports opened garbled in Excel (no BOM) and list-typed fields
    (rewritten_queries, detected_terms, risk_flags, ...) rendered as Python repr instead of
    readable text — both fixed in _csv_stream/_clean_csv_cell."""

    def test_clean_csv_cell_joins_lists_readably(self):
        assert r._clean_csv_cell(["a", "b", "c"]) == "a; b; c"

    def test_clean_csv_cell_none_becomes_empty_string(self):
        assert r._clean_csv_cell(None) == ""

    def test_clean_csv_cell_passes_through_scalars(self):
        assert r._clean_csv_cell("hello") == "hello"
        assert r._clean_csv_cell(42) == 42
        assert r._clean_csv_cell(True) is True

    def test_csv_stream_starts_with_utf8_bom(self):
        chunks = list(r._csv_stream(["a"], [{"a": "1"}]))
        body = "".join(chunks).encode("utf-8")
        assert body.startswith(b"\xef\xbb\xbf")

    def test_csv_stream_cleans_list_fields_in_rows(self):
        rows = [{"terms": ["biaya", "pendaftaran"], "note": None}]
        chunks = list(r._csv_stream(["terms", "note"], rows))
        body = "".join(chunks)
        assert "biaya; pendaftaran" in body
        assert "['biaya'" not in body  # no Python repr leaking into the CSV


@pytest.mark.asyncio
class TestChatLogDetail:
    async def test_404_when_trace_not_found(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        with pytest.raises(HTTPException) as exc_info:
            await r.get_chat_log_detail("nonexistent-trace", db=db)

        assert exc_info.value.status_code == 404


class TestChatLogConditions:
    def test_invalid_session_id_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            r._chat_log_conditions(
                None, None, "not-a-uuid", None, None, None, None, None, None
            )
        assert exc_info.value.status_code == 400

    def test_builds_one_condition_per_provided_filter(self):
        conditions = r._chat_log_conditions(
            date_from=None,
            date_to=None,
            session_id=None,
            participant_code="P001",
            scenario_code="S1",
            fallback_triggered=True,
            model_used=None,
            latency_min_ms=100,
            latency_max_ms=None,
        )
        # participant_code, scenario_code, fallback_triggered, latency_min_ms -> 4 conditions
        assert len(conditions) == 4

    def test_no_filters_yields_no_conditions(self):
        conditions = r._chat_log_conditions(None, None, None, None, None, None, None, None, None)
        assert conditions == []


class TestGateSerializerNeverLeaksInternals:
    def test_serialized_gate_only_has_safe_fields(self):
        gate = AcifTraceLog(
            trace_id="t1",
            gate_number=1,
            gate_name="Gate 1 - Input Intent Integrity Check",
            gate_status="pass",
            risk_score=0.1,
            risk_level="low",
            action_taken="Allowed",
            risk_flags={"matched_signal_count": 0},
            public_summary="Input Anda telah diperiksa dan aman untuk diproses.",
            admin_summary="Input passes integrity checks",
            latency_ms=5,
        )
        serialized = r._serialize_gate(gate)

        # Structurally impossible to leak a raw prompt/formula: no such key exists at all.
        forbidden_keys = {"final_prompt", "system_policy", "vector_context", "raw_signals", "scoring_dimensions"}
        assert forbidden_keys.isdisjoint(serialized.keys())
        assert serialized["gate_status"] == "pass"
        assert serialized["admin_summary"] == "Input passes integrity checks"


class TestTriggerRunRequestAblationFields:
    def test_defaults_to_with_acif_and_no_ablation(self):
        request = r.TriggerRunRequest()
        assert request.config_name == "with_acif"
        assert request.ablation_disable_acif is False
        assert request.disabled_gates is None

    def test_accepts_without_acif_ablation_override(self):
        request = r.TriggerRunRequest(
            run_name="ablation_run", config_name="without_acif", ablation_disable_acif=True
        )
        assert request.config_name == "without_acif"
        assert request.ablation_disable_acif is True

    def test_accepts_disabled_gates_for_n_gate_ablation(self):
        request = r.TriggerRunRequest(
            run_name="ablation_run", config_name="gates_all_minus_3", disabled_gates=[3]
        )
        assert request.config_name == "gates_all_minus_3"
        assert request.disabled_gates == [3]


@pytest.mark.asyncio
class TestTriggerEvaluationRunForwardsDisabledGates:
    async def test_forwards_disabled_gates_as_frozenset(self, monkeypatch):
        from fastapi import BackgroundTasks

        captured: dict = {}

        def fake_add_task(func, *args, **kwargs):
            captured["func"] = func
            captured["args"] = args
            captured["kwargs"] = kwargs

        monkeypatch.setattr(r.settings, "evaluation_runner_enabled", True)
        background_tasks = BackgroundTasks()
        background_tasks.add_task = fake_add_task
        request = r.TriggerRunRequest(
            run_name="ablation_run", config_name="gates_1_2", disabled_gates=[3, 4, 5]
        )

        await r.trigger_evaluation_run(request, background_tasks)

        assert captured["kwargs"]["disabled_gates"] == frozenset({3, 4, 5})
        assert captured["kwargs"]["config_name"] == "gates_1_2"

    async def test_disabled_gates_none_when_not_provided(self, monkeypatch):
        from fastapi import BackgroundTasks

        captured: dict = {}

        def fake_add_task(func, *args, **kwargs):
            captured["kwargs"] = kwargs

        monkeypatch.setattr(r.settings, "evaluation_runner_enabled", True)
        background_tasks = BackgroundTasks()
        background_tasks.add_task = fake_add_task
        request = r.TriggerRunRequest(run_name="ablation_run", config_name="with_acif")

        await r.trigger_evaluation_run(request, background_tasks)

        assert captured["kwargs"]["disabled_gates"] is None


@pytest.mark.asyncio
class TestFetchRunAndResults:
    async def test_404_when_run_not_found(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        with pytest.raises(HTTPException) as exc_info:
            await r._fetch_run_and_results(db, "nonexistent-run")
        assert exc_info.value.status_code == 404

    async def test_returns_run_and_its_results(self):
        run = EvaluationRun(run_name="with_acif_run", config_name="with_acif")
        result_row = EvaluationResult(question_id="Q001", precision_at_3=0.8)

        run_lookup = MagicMock()
        run_lookup.scalar_one_or_none.return_value = run
        results_lookup = MagicMock()
        results_lookup.scalars.return_value.all.return_value = [result_row]

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[run_lookup, results_lookup])

        fetched_run, results = await r._fetch_run_and_results(db, "run-a")
        assert fetched_run is run
        assert results == [result_row]


@pytest.mark.asyncio
class TestCompareEvaluationRuns:
    async def test_compares_two_runs_and_returns_report(self):
        run_a = EvaluationRun(id="run-a", run_name="without_acif_run", config_name="without_acif")
        run_b = EvaluationRun(id="run-b", run_name="with_acif_run", config_name="with_acif")
        results_a = [
            EvaluationResult(question_id="Q001", precision_at_3=0.3),
            EvaluationResult(question_id="Q002", precision_at_3=0.3),
        ]
        results_b = [
            EvaluationResult(question_id="Q001", precision_at_3=0.9),
            EvaluationResult(question_id="Q002", precision_at_3=0.9),
        ]

        run_a_lookup, results_a_lookup = MagicMock(), MagicMock()
        run_a_lookup.scalar_one_or_none.return_value = run_a
        results_a_lookup.scalars.return_value.all.return_value = results_a

        run_b_lookup, results_b_lookup = MagicMock(), MagicMock()
        run_b_lookup.scalar_one_or_none.return_value = run_b
        results_b_lookup.scalars.return_value.all.return_value = results_b

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[run_a_lookup, results_a_lookup, run_b_lookup, results_b_lookup]
        )

        payload = await r.compare_evaluation_runs("run-a", "run-b", db=db)

        assert payload["config_name_a"] == "without_acif"
        assert payload["config_name_b"] == "with_acif"
        assert payload["n_paired_questions"] == 2
        precision_metric = next(m for m in payload["metrics"] if m["metric"] == "precision_at_3")
        assert precision_metric["mean_delta"] == pytest.approx(0.6)


@pytest.mark.asyncio
class TestExportCombinedReportCsv:
    """2026-07-23: combined-report.csv previously joined chat/retrieval/citation/ACIF-gate data
    only — it never included the answer text or the gold-QA evaluation-harness scores
    (precision/recall/faithfulness/citation_correct/etc from evaluation_results), so a reviewer
    couldn't see quality evidence and the underlying chat log in one place."""

    async def _run_export(self, chat_log, eval_result):
        chat_lookup = MagicMock()
        chat_lookup.scalars.return_value.all.return_value = [chat_log]
        retrieval_counts_lookup = MagicMock()
        retrieval_counts_lookup.all.return_value = [(chat_log.trace_id, 5)]
        selected_counts_lookup = MagicMock()
        selected_counts_lookup.all.return_value = [(chat_log.trace_id, 3)]
        citation_counts_lookup = MagicMock()
        citation_counts_lookup.all.return_value = [(chat_log.trace_id, 1)]
        gate_rows_lookup = MagicMock()
        gate_rows_lookup.all.return_value = [(chat_log.trace_id, 1, "pass")]
        eval_lookup = MagicMock()
        eval_lookup.scalars.return_value.all.return_value = [eval_result] if eval_result else []

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                chat_lookup,
                retrieval_counts_lookup,
                selected_counts_lookup,
                citation_counts_lookup,
                gate_rows_lookup,
                eval_lookup,
            ]
        )
        response = await r.export_combined_report_csv(db=db)
        body = b"".join([c.encode("utf-8") if isinstance(c, str) else c async for c in response.body_iterator])
        return body.decode("utf-8")

    async def test_includes_answer_text_and_eval_scores_for_gold_qa_trace(self):
        chat_log = ChatEvaluationLog(
            trace_id="trace-1",
            user_question="Apa syarat pendaftaran?",
            final_answer="Syaratnya adalah ...",
            answer_status="verified",
        )
        eval_result = EvaluationResult(
            evaluation_run_id="11111111-1111-1111-1111-111111111111",
            question_id="Q001",
            trace_id="trace-1",
            category="SPMB",
            expected_behavior="answer",
            precision_at_3=0.333,
            recall_at_3=1.0,
            hit_rate_at_3=1.0,
            citation_correct=True,
            faithfulness_score=0.9,
        )

        body = await self._run_export(chat_log, eval_result)

        assert "Syaratnya adalah" in body
        assert "0.333" in body
        assert "SPMB" in body

    async def test_organic_chat_without_eval_result_leaves_eval_fields_empty(self):
        chat_log = ChatEvaluationLog(
            trace_id="trace-2",
            user_question="Halo",
            final_answer="Halo juga",
            answer_status="answered",
        )

        body = await self._run_export(chat_log, eval_result=None)

        rows = body.split("\n")
        header = rows[0].lstrip("﻿").split(",")
        data_row = rows[1].split(",")
        eval_precision_idx = header.index("eval_precision_at_3")
        assert data_row[eval_precision_idx] == ""
