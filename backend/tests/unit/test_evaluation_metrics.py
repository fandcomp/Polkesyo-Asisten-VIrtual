"""Unit tests for app/evaluation/metrics.py — pure functions used by the gold-QA runner and
the admin Overview page's aggregate cards."""
import pytest

from app.evaluation import metrics


class TestPrecisionAtK:
    def test_all_retrieved_match_expected(self):
        assert metrics.precision_at_k(["a", "b", "c"], ["a", "b", "c"], k=3) == 1.0

    def test_partial_match(self):
        assert metrics.precision_at_k(["a", "b", "c"], ["a", "x"], k=3) == pytest.approx(1 / 3)

    def test_no_match(self):
        assert metrics.precision_at_k(["a", "b"], ["x", "y"], k=3) == 0.0

    def test_only_considers_top_k(self):
        # "c" is expected but sits outside the top-2 window, so it shouldn't count.
        assert metrics.precision_at_k(["a", "b", "c"], ["c"], k=2) == 0.0

    def test_empty_expected_is_not_applicable(self):
        assert metrics.precision_at_k(["a", "b"], [], k=3) is None

    def test_empty_retrieved_with_expected_scores_zero(self):
        assert metrics.precision_at_k([], ["a"], k=3) == 0.0


class TestRecallAtK:
    def test_all_expected_found(self):
        assert metrics.recall_at_k(["a", "b", "c"], ["a", "b"], k=3) == 1.0

    def test_partial_recall(self):
        assert metrics.recall_at_k(["a", "b", "c"], ["a", "x"], k=3) == 0.5

    def test_nothing_found(self):
        assert metrics.recall_at_k(["a", "b"], ["x", "y"], k=3) == 0.0

    def test_empty_expected_is_not_applicable(self):
        assert metrics.recall_at_k(["a"], [], k=3) is None

    def test_respects_k_window(self):
        assert metrics.recall_at_k(["a", "b", "c"], ["c"], k=2) == 0.0


class TestHitRateAtK:
    def test_hit_when_expected_id_in_top_k(self):
        assert metrics.hit_rate_at_k(["a", "b", "c"], ["c"], k=3) == 1.0

    def test_miss_when_expected_id_outside_top_k(self):
        assert metrics.hit_rate_at_k(["a", "b", "c"], ["c"], k=2) == 0.0

    def test_no_match(self):
        assert metrics.hit_rate_at_k(["a", "b"], ["x", "y"], k=3) == 0.0

    def test_hit_with_multiple_expected_ids_needs_only_one(self):
        assert metrics.hit_rate_at_k(["a", "b", "c"], ["x", "c"], k=3) == 1.0

    def test_empty_expected_is_not_applicable(self):
        assert metrics.hit_rate_at_k(["a", "b"], [], k=3) is None

    def test_empty_retrieved_with_expected_scores_zero(self):
        assert metrics.hit_rate_at_k([], ["a"], k=3) == 0.0


class TestCitationCoverage:
    def test_mixed_coverage(self):
        results = [{"citation_present": True}, {"citation_present": False}, {"citation_present": True}]
        assert metrics.citation_coverage(results) == pytest.approx(2 / 3)

    def test_empty_results_scores_zero(self):
        assert metrics.citation_coverage([]) == 0.0

    def test_full_coverage(self):
        assert metrics.citation_coverage([{"citation_present": True}] * 3) == 1.0


class TestCitationCorrectness:
    def test_correct_among_cited(self):
        results = [
            {"citation_present": True, "citation_correct": True},
            {"citation_present": True, "citation_correct": False},
            {"citation_present": False, "citation_correct": None},
        ]
        assert metrics.citation_correctness(results) == 0.5

    def test_no_citations_present_scores_zero(self):
        results = [{"citation_present": False, "citation_correct": None}]
        assert metrics.citation_correctness(results) == 0.0


class TestFallbackCorrectness:
    def test_answer_expected_and_verified_is_correct(self):
        assert metrics.fallback_correctness("answer", "verified") is True

    def test_answer_expected_but_fallback_is_incorrect(self):
        assert metrics.fallback_correctness("answer", "insufficient_context") is False

    def test_fallback_expected_and_fallback_returned_is_correct(self):
        assert metrics.fallback_correctness("fallback", "insufficient_context") is True
        assert metrics.fallback_correctness("fallback", "fallback_enforced") is True

    def test_fallback_expected_and_llm_out_of_domain_refusal_is_correct(self):
        # The LLM's own domain-boundary refusal (status out_of_domain, emitted by
        # chat_core._detect_llm_refusal_status) is a correct safe non-answer — found via
        # gold-QA run where Q004's correct refusal was scored as a failure.
        assert metrics.fallback_correctness("fallback", "out_of_domain") is True
        assert metrics.fallback_correctness("block_or_fallback", "out_of_domain") is True

    def test_block_or_fallback_accepts_either(self):
        assert metrics.fallback_correctness("block_or_fallback", "rejected_by_input_filter") is True
        assert metrics.fallback_correctness("block_or_fallback", "insufficient_context") is True

    def test_block_or_fallback_rejects_a_real_answer(self):
        assert metrics.fallback_correctness("block_or_fallback", "verified") is False

    def test_unknown_expected_behavior_is_false(self):
        assert metrics.fallback_correctness("unexpected_value", "verified") is False


class TestAttackSuccessRate:
    def test_mixed_outcomes(self):
        results = [{"attack_success": True}, {"attack_success": False}, {"attack_success": False}]
        assert metrics.attack_success_rate(results) == pytest.approx(1 / 3)

    def test_ignores_non_security_rows(self):
        results = [{"attack_success": None}, {"attack_success": None}]
        assert metrics.attack_success_rate(results) == 0.0

    def test_empty_scores_zero(self):
        assert metrics.attack_success_rate([]) == 0.0


class TestLatencyAggregates:
    def test_average_latency(self):
        assert metrics.average_latency([100, 200, 300]) == 200.0

    def test_average_ignores_none(self):
        assert metrics.average_latency([100, None, 300]) == 200.0

    def test_average_empty_is_none(self):
        assert metrics.average_latency([]) is None

    def test_p95_single_value(self):
        assert metrics.p95_latency([500]) == 500.0

    def test_p95_of_ordered_set(self):
        # nearest-rank 95th percentile of 20 evenly spaced values lands on the 19th value.
        values = list(range(1, 21))  # 1..20
        assert metrics.p95_latency(values) == 19.0

    def test_p95_empty_is_none(self):
        assert metrics.p95_latency([]) is None
