"""Unit tests for app/evaluation/statistical_comparison.py — the paired with/without-ACIF
comparison used by GET /api/admin/evaluation/compare."""
import pytest

from app.db.models import EvaluationResult
from app.evaluation.statistical_comparison import compare_runs, compare_runs_pooled


def _result(question_id: str, **kwargs) -> EvaluationResult:
    return EvaluationResult(question_id=question_id, **kwargs)


class TestWilcoxonContinuousMetrics:
    def test_consistent_improvement_is_significant(self):
        # "without_acif" (a) scores lower precision on every paired question than
        # "with_acif" (b) — a clear, consistent gap should reach significance.
        results_a = [
            _result(f"Q{i}", precision_at_3=0.3) for i in range(10)
        ]
        results_b = [
            _result(f"Q{i}", precision_at_3=0.9) for i in range(10)
        ]

        report = compare_runs(results_a, results_b, config_name_a="without_acif", config_name_b="with_acif")
        precision_metric = next(m for m in report.metrics if m.metric == "precision_at_3")

        assert report.n_paired_questions == 10
        assert precision_metric.n_pairs == 10
        assert precision_metric.mean_a == pytest.approx(0.3)
        assert precision_metric.mean_b == pytest.approx(0.9)
        assert precision_metric.mean_delta == pytest.approx(0.6)
        assert precision_metric.percent_change == pytest.approx(200.0)
        assert precision_metric.significant is True
        assert precision_metric.p_value is not None and precision_metric.p_value < 0.05

    def test_no_difference_is_not_significant(self):
        results_a = [_result(f"Q{i}", precision_at_3=0.7) for i in range(8)]
        results_b = [_result(f"Q{i}", precision_at_3=0.7) for i in range(8)]

        report = compare_runs(results_a, results_b)
        precision_metric = next(m for m in report.metrics if m.metric == "precision_at_3")

        assert precision_metric.mean_delta == 0.0
        assert precision_metric.significant is False
        assert precision_metric.p_value == 1.0

    def test_fewer_than_two_pairs_is_not_applicable(self):
        results_a = [_result("Q1", precision_at_3=0.5)]
        results_b = [_result("Q1", precision_at_3=0.9)]

        report = compare_runs(results_a, results_b)
        precision_metric = next(m for m in report.metrics if m.metric == "precision_at_3")

        assert precision_metric.p_value is None
        assert precision_metric.significant is None
        assert "not applicable" in precision_metric.note

    def test_null_values_are_excluded_from_pairing(self):
        results_a = [
            _result("Q1", precision_at_3=0.5),
            _result("Q2", precision_at_3=None),  # not applicable gold item — excluded
        ]
        results_b = [
            _result("Q1", precision_at_3=0.9),
            _result("Q2", precision_at_3=0.9),
        ]

        report = compare_runs(results_a, results_b)
        precision_metric = next(m for m in report.metrics if m.metric == "precision_at_3")

        assert precision_metric.n_pairs == 1


class TestQuestionPairing:
    def test_pairs_only_matching_question_ids(self):
        results_a = [_result("Q1", precision_at_3=0.5), _result("Q2", precision_at_3=0.5)]
        results_b = [_result("Q1", precision_at_3=0.9)]  # Q2 missing (e.g. timed out)

        report = compare_runs(results_a, results_b)

        assert report.n_paired_questions == 1

    def test_pairing_is_order_independent(self):
        results_a = [_result("Q2", precision_at_3=0.4), _result("Q1", precision_at_3=0.5)]
        results_b = [_result("Q1", precision_at_3=0.9), _result("Q2", precision_at_3=0.9)]

        report = compare_runs(results_a, results_b)

        assert report.n_paired_questions == 2


class TestMcNemarBinaryMetrics:
    def test_discordant_pairs_favor_b_is_significant(self):
        # 9 discordant pairs: 8 where A is wrong/B is right, 1 the reverse. Concordant pairs
        # (both right or both wrong) don't affect the test at all.
        results_a = (
            [_result(f"D{i}", citation_correct=False) for i in range(8)]
            + [_result("D8", citation_correct=True)]
            + [_result("C1", citation_correct=True), _result("C2", citation_correct=False)]
        )
        results_b = (
            [_result(f"D{i}", citation_correct=True) for i in range(8)]
            + [_result("D8", citation_correct=False)]
            + [_result("C1", citation_correct=True), _result("C2", citation_correct=False)]
        )

        report = compare_runs(results_a, results_b)
        citation_metric = next(m for m in report.metrics if m.metric == "citation_correct")

        assert citation_metric.test_name == "mcnemar_exact"
        assert citation_metric.statistic == 9  # discordant pair count
        assert citation_metric.p_value == pytest.approx(0.0390625)
        assert citation_metric.significant is True

    def test_no_discordant_pairs_is_not_significant(self):
        results_a = [_result(f"Q{i}", fallback_correct=True) for i in range(5)]
        results_b = [_result(f"Q{i}", fallback_correct=True) for i in range(5)]

        report = compare_runs(results_a, results_b)
        fallback_metric = next(m for m in report.metrics if m.metric == "fallback_correct")

        assert fallback_metric.p_value == 1.0
        assert fallback_metric.significant is False
        assert "agree" in fallback_metric.note

    def test_no_paired_observations_is_not_applicable(self):
        results_a = [_result("Q1", fallback_correct=None)]
        results_b = [_result("Q1", fallback_correct=None)]

        report = compare_runs(results_a, results_b)
        fallback_metric = next(m for m in report.metrics if m.metric == "fallback_correct")

        assert fallback_metric.n_pairs == 0
        assert fallback_metric.p_value is None


class TestAttackSuccessReporting:
    def test_security_category_only(self):
        results_a = [
            _result("S1", category="Security", attack_success=True),
            _result("S2", category="Security", attack_success=True),
            _result("Q1", category="SPMB", attack_success=None),
        ]
        results_b = [
            _result("S1", category="Security", attack_success=False),
            _result("S2", category="Security", attack_success=False),
            _result("Q1", category="SPMB", attack_success=None),
        ]

        report = compare_runs(results_a, results_b)

        assert report.attack_success is not None
        assert report.attack_success.n_pairs == 2
        assert report.attack_success.mean_a == pytest.approx(1.0)  # without-ACIF: both attacks succeed
        assert report.attack_success.mean_b == pytest.approx(0.0)  # with-ACIF: both blocked

    def test_no_security_rows_yields_none(self):
        results_a = [_result("Q1", category="SPMB", attack_success=None)]
        results_b = [_result("Q1", category="SPMB", attack_success=None)]

        report = compare_runs(results_a, results_b)

        assert report.attack_success is None


class TestCompareRunsPooled:
    """compare_runs_pooled combines N repeated trial pairs for more statistical power than a
    single run affords (2026-07-22 remediation of the 2026-07-18 report's Tier 3 finding)."""

    def test_pools_observations_across_trials_not_just_within_one(self):
        # 3 trials of the same 5 questions, identical values each trial — pooling should see
        # n_paired_questions == 15 (5 questions x 3 trials), not 5.
        trial_pairs = [
            (
                [_result(f"Q{i}", precision_at_3=0.2) for i in range(5)],
                [_result(f"Q{i}", precision_at_3=0.8) for i in range(5)],
            )
            for _ in range(3)
        ]

        report = compare_runs_pooled(trial_pairs, config_name_a="without_acif", config_name_b="with_acif")
        precision_metric = next(m for m in report.metrics if m.metric == "precision_at_3")

        assert report.n_paired_questions == 15
        assert precision_metric.n_pairs == 15
        assert precision_metric.mean_a == pytest.approx(0.2)
        assert precision_metric.mean_b == pytest.approx(0.8)

    def test_more_trials_can_reach_significance_where_one_run_could_not(self):
        # A small, consistent per-trial gap that a single n=3 run wouldn't reach significance
        # with with can become significant once pooled across enough repeated trials.
        single_trial = (
            [_result(f"Q{i}", faithfulness_score=v) for i, v in enumerate([0.9, 0.85, 0.8])],
            [_result(f"Q{i}", faithfulness_score=v) for i, v in enumerate([0.8, 0.75, 0.7])],
        )
        single_report = compare_runs(*single_trial)
        single_metric = next(m for m in single_report.metrics if m.metric == "faithfulness_score")

        pooled_report = compare_runs_pooled([single_trial] * 5)
        pooled_metric = next(m for m in pooled_report.metrics if m.metric == "faithfulness_score")

        assert pooled_metric.n_pairs == single_metric.n_pairs * 5
        assert pooled_metric.p_value is not None
        assert pooled_metric.p_value <= single_metric.p_value

    def test_run_ids_are_joined_for_traceability(self):
        trial_pairs = [
            ([_result("Q1", precision_at_3=0.5)], [_result("Q1", precision_at_3=0.5)]),
            ([_result("Q1", precision_at_3=0.5)], [_result("Q1", precision_at_3=0.5)]),
        ]

        report = compare_runs_pooled(trial_pairs, run_ids_a=["run-a1", "run-a2"], run_ids_b=["run-b1", "run-b2"])

        assert report.run_id_a == "run-a1,run-a2"
        assert report.run_id_b == "run-b1,run-b2"

    def test_attack_success_pools_across_trials(self):
        trial_pairs = [
            (
                [_result("S1", category="Security", attack_success=True)],
                [_result("S1", category="Security", attack_success=False)],
            )
            for _ in range(3)
        ]

        report = compare_runs_pooled(trial_pairs)

        assert report.attack_success is not None
        assert report.attack_success.n_pairs == 3
        assert report.attack_success.mean_a == pytest.approx(1.0)
        assert report.attack_success.mean_b == pytest.approx(0.0)
