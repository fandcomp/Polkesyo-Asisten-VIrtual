"""Unit tests for ablation_matrix_report.py's pure functions — no DB, small in-memory
EvaluationResult lists (same construction pattern as test_evaluation_admin_routes.py)."""
from app.db.models import EvaluationResult
from app.evaluation.ablation_matrix_report import build_ablation_matrix, build_gate_impact_ranking


def _results(*, precision, fallback_correct, attack_success=None, category="SPMB", n=4):
    return [
        EvaluationResult(
            question_id=f"Q{i}",
            category=category,
            expected_behavior="answer",
            precision_at_3=precision,
            fallback_correct=fallback_correct,
            attack_success=attack_success,
        )
        for i in range(n)
    ]


class TestBuildAblationMatrix:
    def test_produces_one_row_per_config(self):
        results_by_config = {
            "gates_all": _results(precision=0.9, fallback_correct=True),
            "gates_none": _results(precision=0.5, fallback_correct=False),
            "gates_all_minus_2": _results(precision=0.7, fallback_correct=True),
        }
        matrix = build_ablation_matrix(results_by_config)
        assert len(matrix.rows) == 3
        assert {r.config_name for r in matrix.rows} == set(results_by_config.keys())

    def test_gate_count_and_disabled_gates_derived_from_matrix(self):
        results_by_config = {
            "gates_all": _results(precision=0.9, fallback_correct=True),
            "gates_all_minus_3": _results(precision=0.7, fallback_correct=True),
        }
        matrix = build_ablation_matrix(results_by_config)
        row = next(r for r in matrix.rows if r.config_name == "gates_all_minus_3")
        assert row.gate_count == 4
        assert row.disabled_gates == (3,)
        all_row = next(r for r in matrix.rows if r.config_name == "gates_all")
        assert all_row.gate_count == 5
        assert all_row.disabled_gates == ()

    def test_none_valued_metrics_do_not_crash_aggregation(self):
        # No pinned ground truth (precision_at_3=None for every row) — must aggregate to
        # None, not crash or silently become 0.0 (metrics.py's "not applicable" convention).
        results_by_config = {
            "gates_all": [
                EvaluationResult(question_id="Q1", category="Security", expected_behavior="block_or_fallback")
            ],
        }
        matrix = build_ablation_matrix(results_by_config)
        assert matrix.rows[0].aggregate_metrics["precision_at_3"] is None

    def test_comparison_vs_gates_all_populated_for_other_configs(self):
        results_by_config = {
            "gates_all": _results(precision=0.9, fallback_correct=True),
            "gates_all_minus_1": _results(precision=0.5, fallback_correct=False),
        }
        matrix = build_ablation_matrix(results_by_config)
        minus_row = next(r for r in matrix.rows if r.config_name == "gates_all_minus_1")
        assert minus_row.comparison_vs_gates_all is not None
        gates_all_row = next(r for r in matrix.rows if r.config_name == "gates_all")
        assert gates_all_row.comparison_vs_gates_all is None  # no self-comparison


class TestBuildGateImpactRanking:
    def test_ranks_by_absolute_delta_descending(self):
        results_by_config = {
            "gates_all": _results(precision=0.9, fallback_correct=True),
            # Removing gate 1 barely changes precision (small delta).
            "gates_all_minus_1": _results(precision=0.88, fallback_correct=True),
            # Removing gate 5 crashes precision (large delta) — should rank first.
            "gates_all_minus_5": _results(precision=0.2, fallback_correct=False),
        }
        matrix = build_ablation_matrix(results_by_config)
        ranking = build_gate_impact_ranking(matrix)

        precision_rows = [r for r in ranking if r.metric == "precision_at_3"]
        assert precision_rows[0].gate_number == 5
        gate5_row = next(r for r in precision_rows if r.gate_number == 5)
        gate1_row = next(r for r in precision_rows if r.gate_number == 1)
        assert abs(gate5_row.delta) > abs(gate1_row.delta)

    def test_delta_is_minus_config_value_minus_gates_all_value(self):
        results_by_config = {
            "gates_all": _results(precision=0.9, fallback_correct=True),
            "gates_all_minus_2": _results(precision=0.6, fallback_correct=True),
        }
        matrix = build_ablation_matrix(results_by_config)
        ranking = build_gate_impact_ranking(matrix)
        row = next(r for r in ranking if r.gate_number == 2 and r.metric == "precision_at_3")
        assert row.gates_all_value == 0.9
        assert row.gates_all_minus_n_value == 0.6
        assert row.delta is not None
        assert row.delta < 0  # removing gate 2 hurt precision

    def test_missing_gates_all_minus_n_config_is_skipped_not_crashed(self):
        # Only gate 1's leave-one-out run exists — gates 2-5 not run yet; must not raise.
        results_by_config = {
            "gates_all": _results(precision=0.9, fallback_correct=True),
            "gates_all_minus_1": _results(precision=0.85, fallback_correct=True),
        }
        matrix = build_ablation_matrix(results_by_config)
        ranking = build_gate_impact_ranking(matrix)
        assert all(r.gate_number == 1 for r in ranking)

    def test_empty_matrix_returns_empty_ranking(self):
        matrix = build_ablation_matrix({})
        assert build_gate_impact_ranking(matrix) == []
