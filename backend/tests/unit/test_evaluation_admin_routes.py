"""Unit tests for routes_evaluation_admin.py — covers the trace-detail 404 path, latency
filter query construction, the safe-summary serializer never leaking gate internals, and the
with/without-ACIF comparison endpoint (Evaluation Layer Phase 5)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from app.api import routes_evaluation_admin as r
from app.db.models import AcifTraceLog, EvaluationResult, EvaluationRun


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

    def test_accepts_without_acif_ablation_override(self):
        request = r.TriggerRunRequest(
            run_name="ablation_run", config_name="without_acif", ablation_disable_acif=True
        )
        assert request.config_name == "without_acif"
        assert request.ablation_disable_acif is True


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
