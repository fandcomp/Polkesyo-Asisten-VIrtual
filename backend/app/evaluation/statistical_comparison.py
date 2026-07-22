"""Statistical comparison between two evaluation runs — Evaluation Layer Phase 5.

Built for the thesis with/without-ACIF rumusan masalah: two EvaluationRuns produced from the
same gold_qa_dataset.jsonl (e.g. config_name="with_acif" vs "without_acif", see
run_evaluation.py) are naturally paired by question_id, so this uses paired tests rather than
independent-sample tests:

- Wilcoxon signed-rank (scipy.stats.wilcoxon) for continuous/ordinal metrics (precision@3,
  recall@3, faithfulness_score, answer_relevance_score, total_latency_ms).
- The exact McNemar test for paired binary metrics (citation_correct, fallback_correct,
  attack_success). scipy has no built-in McNemar implementation; the exact McNemar test is
  mathematically equivalent to a two-sided exact binomial test on the discordant-pair counts
  (scipy.stats.binomtest), which avoids adding statsmodels as a dependency for one function.

Every comparison also reports descriptive deltas (mean/median difference, % change) alongside
the test result, since n=41 is a small sample and a non-significant p-value with a clear
descriptive gap is still worth reporting honestly (see docs/private/acif/evaluation-plan.md).
"""
from dataclasses import dataclass, field
from typing import Sequence

from scipy import stats

from app.db.models import EvaluationResult

_CONTINUOUS_METRICS = [
    "precision_at_3",
    "recall_at_3",
    "hit_rate_at_3",
    "faithfulness_score",
    "answer_relevance_score",
    "total_latency_ms",
]
_BINARY_METRICS = ["citation_correct", "fallback_correct"]

ALPHA = 0.05


@dataclass
class MetricComparison:
    metric: str
    n_pairs: int
    mean_a: float | None
    mean_b: float | None
    mean_delta: float | None  # b - a
    median_delta: float | None
    percent_change: float | None
    test_name: str
    statistic: float | None
    p_value: float | None
    significant: bool | None
    note: str | None = None


@dataclass
class ComparisonReport:
    run_id_a: str
    run_id_b: str
    config_name_a: str | None
    config_name_b: str | None
    n_paired_questions: int
    metrics: list[MetricComparison] = field(default_factory=list)
    attack_success: MetricComparison | None = None


def _pair_by_question(
    results_a: Sequence[EvaluationResult], results_b: Sequence[EvaluationResult]
) -> list[tuple[EvaluationResult, EvaluationResult]]:
    """Pair rows by question_id — both runs replay the same gold-QA dataset, so order and
    per-run completeness (e.g. a timed-out question) need not match between the two lists."""
    by_question_b = {r.question_id: r for r in results_b}
    return [
        (r_a, by_question_b[r_a.question_id])
        for r_a in results_a
        if r_a.question_id in by_question_b
    ]


def _median(values: list[float]) -> float:
    n = len(values)
    ordered = sorted(values)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _wilcoxon_metric(metric: str, pairs: list[tuple[EvaluationResult, EvaluationResult]]) -> MetricComparison:
    paired = [
        (getattr(a, metric), getattr(b, metric))
        for a, b in pairs
        if getattr(a, metric) is not None and getattr(b, metric) is not None
    ]
    n = len(paired)
    if n < 2:
        return MetricComparison(
            metric=metric, n_pairs=n, mean_a=None, mean_b=None, mean_delta=None,
            median_delta=None, percent_change=None, test_name="wilcoxon_signed_rank",
            statistic=None, p_value=None, significant=None,
            note="Fewer than 2 paired non-null observations — test not applicable.",
        )

    a_vals = [float(p[0]) for p in paired]
    b_vals = [float(p[1]) for p in paired]
    deltas = [b - a for a, b in zip(a_vals, b_vals)]
    mean_a = sum(a_vals) / n
    mean_b = sum(b_vals) / n
    mean_delta = sum(deltas) / n
    median_delta = _median(deltas)
    percent_change = (mean_delta / mean_a * 100) if mean_a else None

    if all(d == 0 for d in deltas):
        return MetricComparison(
            metric=metric, n_pairs=n, mean_a=mean_a, mean_b=mean_b, mean_delta=mean_delta,
            median_delta=median_delta, percent_change=percent_change,
            test_name="wilcoxon_signed_rank", statistic=None, p_value=1.0, significant=False,
            note="No difference between conditions for any paired question.",
        )

    try:
        statistic, p_value = stats.wilcoxon(a_vals, b_vals)
    except ValueError as e:
        return MetricComparison(
            metric=metric, n_pairs=n, mean_a=mean_a, mean_b=mean_b, mean_delta=mean_delta,
            median_delta=median_delta, percent_change=percent_change,
            test_name="wilcoxon_signed_rank", statistic=None, p_value=None, significant=None,
            note=str(e),
        )

    return MetricComparison(
        metric=metric, n_pairs=n, mean_a=mean_a, mean_b=mean_b, mean_delta=mean_delta,
        median_delta=median_delta, percent_change=percent_change,
        test_name="wilcoxon_signed_rank", statistic=float(statistic), p_value=float(p_value),
        significant=bool(p_value < ALPHA),
    )


def _mcnemar_metric(metric: str, pairs: list[tuple[EvaluationResult, EvaluationResult]]) -> MetricComparison:
    paired = [
        (getattr(a, metric), getattr(b, metric))
        for a, b in pairs
        if getattr(a, metric) is not None and getattr(b, metric) is not None
    ]
    n = len(paired)
    if n == 0:
        return MetricComparison(
            metric=metric, n_pairs=0, mean_a=None, mean_b=None, mean_delta=None,
            median_delta=None, percent_change=None, test_name="mcnemar_exact",
            statistic=None, p_value=None, significant=None,
            note="No paired non-null observations — test not applicable.",
        )

    a_vals = [bool(a) for a, _ in paired]
    b_vals = [bool(b) for _, b in paired]
    mean_a = sum(a_vals) / n
    mean_b = sum(b_vals) / n
    mean_delta = mean_b - mean_a
    percent_change = (mean_delta / mean_a * 100) if mean_a else None

    # Discordant pairs: b_disc = condition A false / B true; c_disc = A true / B false.
    b_disc = sum(1 for a, b in zip(a_vals, b_vals) if (not a) and b)
    c_disc = sum(1 for a, b in zip(a_vals, b_vals) if a and (not b))
    discordant_total = b_disc + c_disc

    if discordant_total == 0:
        return MetricComparison(
            metric=metric, n_pairs=n, mean_a=mean_a, mean_b=mean_b, mean_delta=mean_delta,
            median_delta=None, percent_change=percent_change, test_name="mcnemar_exact",
            statistic=None, p_value=1.0, significant=False,
            note="No discordant pairs — conditions agree on every paired question.",
        )

    # Exact McNemar test == two-sided exact binomial test on the discordant-pair counts.
    binom_result = stats.binomtest(min(b_disc, c_disc), discordant_total, p=0.5, alternative="two-sided")

    return MetricComparison(
        metric=metric, n_pairs=n, mean_a=mean_a, mean_b=mean_b, mean_delta=mean_delta,
        median_delta=None, percent_change=percent_change, test_name="mcnemar_exact",
        statistic=float(discordant_total), p_value=float(binom_result.pvalue),
        significant=bool(binom_result.pvalue < ALPHA),
        note=f"discordant pairs: {discordant_total} (b={b_disc}, c={c_disc})",
    )


def compare_runs(
    results_a: Sequence[EvaluationResult],
    results_b: Sequence[EvaluationResult],
    run_id_a: str = "",
    run_id_b: str = "",
    config_name_a: str | None = None,
    config_name_b: str | None = None,
) -> ComparisonReport:
    """Compare two evaluation runs question-by-question.

    `results_a`/`results_b` should be the full evaluation_results rows for two EvaluationRuns
    produced from the SAME gold-QA dataset — pairing is by question_id, so list order and
    per-run completeness need not match.
    """
    pairs = _pair_by_question(results_a, results_b)

    metric_comparisons = [_wilcoxon_metric(m, pairs) for m in _CONTINUOUS_METRICS]
    metric_comparisons += [_mcnemar_metric(m, pairs) for m in _BINARY_METRICS]

    # attack_success is Security-category-only and lower-is-better (unlike the metrics above),
    # so it's reported separately rather than folded into the general binary-metric list.
    attack_pairs = [(a, b) for a, b in pairs if (a.category or "").lower() == "security"]
    attack_success = _mcnemar_metric("attack_success", attack_pairs) if attack_pairs else None

    return ComparisonReport(
        run_id_a=run_id_a,
        run_id_b=run_id_b,
        config_name_a=config_name_a,
        config_name_b=config_name_b,
        n_paired_questions=len(pairs),
        metrics=metric_comparisons,
        attack_success=attack_success,
    )
