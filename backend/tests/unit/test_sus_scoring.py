"""Unit tests for SUS scoring (routes_evaluation_public.py's calculate_sus_score) —
standard System Usability Scale: odd items contribute (score-1), even items contribute
(5-score), sum * 2.5 gives the 0-100 scale score."""
import pytest

from app.api.routes_evaluation_public import calculate_sus_score


class TestCalculateSusScore:
    def test_all_neutral_threes_score_50(self):
        # Every item contributes (3-1)=2 or (5-3)=2 regardless of odd/even -> sum=20 -> *2.5=50.
        assert calculate_sus_score([3] * 10) == 50.0

    def test_best_possible_answers_score_100(self):
        # Odd items answered 5 (best), even items answered 1 (best) -> every item contributes 4.
        scores = [5, 1, 5, 1, 5, 1, 5, 1, 5, 1]
        assert calculate_sus_score(scores) == 100.0

    def test_worst_possible_answers_score_0(self):
        # Odd items answered 1 (worst), even items answered 5 (worst) -> every item contributes 0.
        scores = [1, 5, 1, 5, 1, 5, 1, 5, 1, 5]
        assert calculate_sus_score(scores) == 0.0

    def test_known_mixed_example(self):
        # Matches the live end-to-end verification done during Phase 4:
        # odd (4,5,4,5,4) -> contributions (3,4,3,4,3)=17; even (2,1,2,1,2) -> (3,4,3,4,3)=17
        # total=34 * 2.5 = 85.0
        scores = [4, 2, 5, 1, 4, 2, 5, 1, 4, 2]
        assert calculate_sus_score(scores) == 85.0

    def test_above_average_usability_threshold(self):
        # 68 is the commonly-cited "above average" SUS benchmark; confirm our calc agrees a
        # slightly-better-than-neutral response set clears it.
        scores = [4, 2, 4, 2, 4, 2, 4, 2, 4, 2]
        assert calculate_sus_score(scores) > 68
