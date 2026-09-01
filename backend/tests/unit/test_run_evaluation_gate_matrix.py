"""Unit tests for run_evaluation.py's N-gate ablation matrix (2026-07-24) — pure, no DB/async.

Covers ABLATION_GATE_MATRIX's structural invariants and _resolve_disabled_gates's 3-way
precedence (disabled_gates param > ablation_disable_acif bool > config_name lookup), including
the hard-fail-on-unknown-config_name behavior (each run is real, billed OpenRouter traffic, so
a typo'd config name must error rather than silently defaulting to "all gates enabled")."""
import pytest

from app.evaluation.run_evaluation import ABLATION_GATE_MATRIX, _resolve_disabled_gates

_ALL_GATES = frozenset({1, 2, 3, 4, 5})


class TestAblationGateMatrixStructure:
    def test_has_13_keys_mapping_to_10_distinct_gate_subsets(self):
        # 13 keys: with_acif/without_acif (legacy names) + gates_none/gates_all (new-naming
        # aliases of the same 2 conditions) + gates_1/_1_2/_1_2_3/_1_2_3_4 (4 cumulative
        # intermediates) + gates_all_minus_1..5 (5 leave-one-out) = 13 keys, but only 10
        # distinct gate-subsets: with_acif==gates_all and without_acif==gates_none by design,
        # AND gates_1_2_3_4 (disable only gate 5) is mathematically identical to
        # gates_all_minus_5 (leave out only gate 5) — both mean "gates 1-4 active, gate 5
        # disabled". This is an inherent overlap where the cumulative and leave-one-out framings
        # meet at their shared endpoint, not a matrix design error — it means only 8 distinct
        # NEW evaluation runs are needed for the 9 "new" config names, not 9.
        assert len(ABLATION_GATE_MATRIX) == 13
        distinct_subsets = {frozenset(v) for v in ABLATION_GATE_MATRIX.values()}
        assert len(distinct_subsets) == 10
        assert ABLATION_GATE_MATRIX["gates_1_2_3_4"] == ABLATION_GATE_MATRIX["gates_all_minus_5"]

    def test_gates_all_and_with_acif_are_aliases(self):
        assert ABLATION_GATE_MATRIX["gates_all"] == ABLATION_GATE_MATRIX["with_acif"] == frozenset()

    def test_gates_none_and_without_acif_are_aliases(self):
        assert ABLATION_GATE_MATRIX["gates_none"] == ABLATION_GATE_MATRIX["without_acif"] == _ALL_GATES

    def test_cumulative_sets_are_strictly_nested(self):
        cumulative_keys = ["gates_1", "gates_1_2", "gates_1_2_3", "gates_1_2_3_4", "gates_all"]
        sets = [ABLATION_GATE_MATRIX[k] for k in cumulative_keys]
        for larger, smaller in zip(sets, sets[1:]):
            assert smaller < larger  # strictly nested: each step disables one fewer gate

    def test_leave_one_out_sets_are_all_singletons(self):
        for gate_num in range(1, 6):
            key = f"gates_all_minus_{gate_num}"
            assert ABLATION_GATE_MATRIX[key] == frozenset({gate_num})

    def test_all_values_are_subsets_of_1_to_5(self):
        for disabled in ABLATION_GATE_MATRIX.values():
            assert disabled.issubset(_ALL_GATES)


class TestResolveDisabledGates:
    def test_explicit_disabled_gates_wins_over_everything(self):
        result = _resolve_disabled_gates(
            config_name="gates_all", ablation_disable_acif=True, disabled_gates=frozenset({2})
        )
        assert result == frozenset({2})

    def test_ablation_disable_acif_wins_over_config_name(self):
        result = _resolve_disabled_gates(
            config_name="gates_1", ablation_disable_acif=True, disabled_gates=None
        )
        assert result == _ALL_GATES

    def test_config_name_lookup_used_when_no_explicit_override(self):
        result = _resolve_disabled_gates(
            config_name="gates_all_minus_3", ablation_disable_acif=False, disabled_gates=None
        )
        assert result == frozenset({3})

    def test_unknown_config_name_raises_instead_of_silently_defaulting(self):
        with pytest.raises(ValueError):
            _resolve_disabled_gates(
                config_name="gates_1_23", ablation_disable_acif=False, disabled_gates=None
            )

    def test_empty_disabled_gates_set_is_explicit_and_valid(self):
        # frozenset() is falsy but not None — must be honored, not treated as "not provided".
        result = _resolve_disabled_gates(
            config_name="gates_none", ablation_disable_acif=False, disabled_gates=frozenset()
        )
        assert result == frozenset()
