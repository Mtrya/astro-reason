"""
Tests for the SPOT-5 Satellite Photography Scheduling Benchmark Verifier.

Tests include:
1. Validation of all reference solutions from tests/fixtures/spot5_val_sol/
2. Invalid solution examples (domain violations, constraint violations, etc.)
"""

import pytest
from pathlib import Path

from benchmarks.spot5.verifier import (
    Instance,
    Solution,
    Variable,
    Constraint,
    VerificationResult,
    parse_instance,
    parse_solution,
    verify,
    verify_files,
    MULTI_ORBIT_INSTANCES,
    FIXED_CAPACITY,
)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATASET_DIR = PROJECT_ROOT / "benchmarks" / "spot5" / "dataset"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "spot5_val_sol"

# All instance names from the fixtures
ALL_INSTANCES = [
    "8",
    "54",
    "5",
    "11",
    "28",
    "29",
    "42",
    "404",
    "408",
    "412",
    "503",
    "505",
    "507",
    "509",
    "1021",
    "1401",
    "1403",
    "1405",
    "1502",
    "1504",
    "1506",
]


class TestParseInstance:
    """Tests for instance file parsing."""

    def test_parse_small_instance(self):
        """Test parsing the smallest instance (8.spot)."""
        instance = parse_instance(DATASET_DIR / "8.spot")

        assert instance.n_variables == 8
        assert len(instance.constraints) == 7
        assert instance.capacity == 0  # single-orbit
        assert not instance.is_multi_orbit

        # Check first variable (mono, domain {1,2,3})
        var0 = instance.variables[0]
        assert var0.var_id == 0
        assert var0.profit == 1
        assert set(var0.domain.keys()) == {1, 2, 3}

        # Check stereo variable (domain {13})
        var4 = instance.variables[4]
        assert var4.var_id == 4
        assert var4.profit == 2
        assert set(var4.domain.keys()) == {13}

    def test_parse_multi_orbit_instance(self):
        """Test parsing a multi-orbit instance with memory constraints."""
        instance = parse_instance(DATASET_DIR / "1502.spot")

        assert instance.is_multi_orbit
        assert instance.capacity == FIXED_CAPACITY

        # Check that consumption values are non-zero
        var0 = instance.variables[0]
        for val, consumption in var0.domain.items():
            assert consumption > 0

    def test_parse_constraint_binary(self):
        """Test parsing binary constraints."""
        instance = parse_instance(DATASET_DIR / "8.spot")

        # First constraint: "2 1 0 3 3 2 2 1 1"
        # Binary constraint between vars 1 and 0 with forbidden pairs
        constraint = instance.constraints[0]
        assert constraint.arity == 2
        assert constraint.variables == [1, 0]
        assert (3, 3) in constraint.forbidden
        assert (2, 2) in constraint.forbidden
        assert (1, 1) in constraint.forbidden

    def test_parse_constraint_ternary(self):
        """Test parsing ternary constraints."""
        # Instance 11 has ternary constraints
        instance = parse_instance(DATASET_DIR / "11.spot")

        # Find a ternary constraint
        ternary = [c for c in instance.constraints if c.arity == 3]
        assert len(ternary) > 0

        tc = ternary[0]
        assert tc.arity == 3
        assert len(tc.variables) == 3
        assert all(len(t) == 3 for t in tc.forbidden)


class TestParseSolution:
    """Tests for solution file parsing."""

    def test_parse_small_solution(self):
        """Test parsing the smallest solution (8.spot_sol.txt)."""
        solution = parse_solution(FIXTURES_DIR / "8.spot_sol.txt")

        assert solution.claimed_profit == 10
        assert solution.claimed_weight == 0
        assert solution.n_candidates == 8
        assert solution.n_selected == 7
        assert len(solution.assignments) == 8

        # Check specific assignments from the file
        assert solution.assignments[0] == 1   # var 0 = camera 1
        assert solution.assignments[1] == 3   # var 1 = camera 3
        assert solution.assignments[4] == 13  # var 4 = stereo
        assert solution.assignments[5] == 0   # var 5 = not selected

    def test_parse_multi_orbit_solution(self):
        """Test parsing a multi-orbit solution with weight."""
        solution = parse_solution(FIXTURES_DIR / "1502.spot_sol.txt")

        assert solution.claimed_weight > 0 or solution.claimed_weight == 0
        assert solution.n_candidates > 0
        assert len(solution.assignments) == solution.n_candidates


class TestVerifyValidSolutions:
    """Tests that all reference solutions are valid."""

    @pytest.mark.parametrize("instance_name", ALL_INSTANCES)
    def test_reference_solution_valid(self, instance_name: str):
        """Test that each reference solution passes verification."""
        instance_path = DATASET_DIR / f"{instance_name}.spot"
        solution_path = FIXTURES_DIR / f"{instance_name}.spot_sol.txt"

        if not instance_path.exists():
            pytest.skip(f"Instance file {instance_path} not found")
        if not solution_path.exists():
            pytest.skip(f"Solution file {solution_path} not found")

        result = verify_files(instance_path, solution_path)

        assert result.is_valid, f"Solution for {instance_name} should be valid: {result.errors}"
        assert result.computed_profit > 0
        assert result.computed_selected > 0

    def test_8_spot_detailed(self):
        """Detailed test for 8.spot - verify exact values."""
        result = verify_files(
            DATASET_DIR / "8.spot",
            FIXTURES_DIR / "8.spot_sol.txt"
        )

        assert result.is_valid
        assert result.computed_profit == 10
        assert result.computed_weight == 0
        assert result.computed_selected == 7

    def test_multi_orbit_capacity_respected(self):
        """Test that multi-orbit solutions respect capacity constraint."""
        for name in MULTI_ORBIT_INSTANCES:
            instance_path = DATASET_DIR / f"{name}.spot"
            solution_path = FIXTURES_DIR / f"{name}.spot_sol.txt"

            if not instance_path.exists() or not solution_path.exists():
                continue

            result = verify_files(instance_path, solution_path)

            assert result.is_valid
            assert result.computed_weight <= FIXED_CAPACITY, \
                f"{name}: weight {result.computed_weight} exceeds capacity {FIXED_CAPACITY}"


class TestInvalidSolutions:
    """Tests for invalid solution detection."""

    def test_invalid_domain_violation(self):
        """Test detection of assignment outside variable domain."""
        instance = Instance(
            variables=[
                Variable(var_id=0, profit=10, domain={1: 0, 2: 0, 3: 0}),
                Variable(var_id=1, profit=20, domain={13: 0}),  # stereo only
            ],
            constraints=[],
            capacity=0,
        )

        # Invalid: assign value 2 to a stereo-only variable
        solution = Solution(
            claimed_profit=30,
            claimed_weight=0,
            n_candidates=2,
            n_selected=2,
            assignments=[1, 2],  # var 1 can only be 0 or 13
        )

        result = verify(instance, solution)

        assert not result.is_valid
        assert any("domain" in e.lower() for e in result.errors)

    def test_invalid_binary_constraint_violation(self):
        """Test detection of binary constraint violation."""
        instance = Instance(
            variables=[
                Variable(var_id=0, profit=10, domain={1: 0, 2: 0, 3: 0}),
                Variable(var_id=1, profit=20, domain={1: 0, 2: 0, 3: 0}),
            ],
            constraints=[
                Constraint(
                    arity=2,
                    variables=[0, 1],
                    forbidden={(1, 1), (2, 2), (3, 3)},  # can't use same camera
                )
            ],
            capacity=0,
        )

        # Invalid: both use camera 1
        solution = Solution(
            claimed_profit=30,
            claimed_weight=0,
            n_candidates=2,
            n_selected=2,
            assignments=[1, 1],
        )

        result = verify(instance, solution)

        assert not result.is_valid
        assert any("binary constraint" in e.lower() for e in result.errors)

    def test_invalid_ternary_constraint_violation(self):
        """Test detection of ternary constraint violation."""
        instance = Instance(
            variables=[
                Variable(var_id=0, profit=10, domain={1: 0, 2: 0, 3: 0, 13: 0}),
                Variable(var_id=1, profit=20, domain={1: 0, 2: 0, 3: 0}),
                Variable(var_id=2, profit=30, domain={1: 0, 2: 0, 3: 0, 13: 0}),
            ],
            constraints=[
                Constraint(
                    arity=3,
                    variables=[0, 1, 2],
                    forbidden={(13, 2, 13)},  # specific forbidden combination
                )
            ],
            capacity=0,
        )

        # Invalid: matches forbidden tuple
        solution = Solution(
            claimed_profit=60,
            claimed_weight=0,
            n_candidates=3,
            n_selected=3,
            assignments=[13, 2, 13],
        )

        result = verify(instance, solution)

        assert not result.is_valid
        assert any("ternary constraint" in e.lower() for e in result.errors)

    def test_invalid_capacity_exceeded(self):
        """Test detection of capacity constraint violation."""
        instance = Instance(
            variables=[
                Variable(var_id=0, profit=1000, domain={2: 451.15}),
                Variable(var_id=1, profit=1000, domain={2: 451.15}),
                Variable(var_id=2, profit=1000, domain={2: 451.15}),
            ],
            constraints=[],
            capacity=200,  # multi-orbit
        )

        # Create solution that exceeds capacity
        # Each var contributes round(451.15/451) = 1 weight
        # To exceed 200, we need more than 200 selected variables
        # For this test, let's modify to have higher consumption
        instance.variables[0].domain = {2: 45115.0}  # contributes 100
        instance.variables[1].domain = {2: 45115.0}  # contributes 100
        instance.variables[2].domain = {2: 45115.0}  # contributes 100
        # Total = 300 > 200

        solution = Solution(
            claimed_profit=3000,
            claimed_weight=300,
            n_candidates=3,
            n_selected=3,
            assignments=[2, 2, 2],
        )

        result = verify(instance, solution)

        assert not result.is_valid
        assert any("capacity" in e.lower() for e in result.errors)

    def test_valid_constraint_when_var_not_selected(self):
        """Test that constraints are satisfied when variables are not selected."""
        instance = Instance(
            variables=[
                Variable(var_id=0, profit=10, domain={1: 0, 2: 0, 3: 0}),
                Variable(var_id=1, profit=20, domain={1: 0, 2: 0, 3: 0}),
            ],
            constraints=[
                Constraint(
                    arity=2,
                    variables=[0, 1],
                    forbidden={(1, 1), (2, 2), (3, 3)},
                )
            ],
            capacity=0,
        )

        # Valid: one variable not selected, constraint satisfied
        solution = Solution(
            claimed_profit=10,
            claimed_weight=0,
            n_candidates=2,
            n_selected=1,
            assignments=[1, 0],  # var 1 not selected
        )

        result = verify(instance, solution)

        assert result.is_valid
        assert result.computed_profit == 10
        assert result.computed_selected == 1

    def test_invalid_assignment_count_mismatch(self):
        """Test detection of assignment count mismatch."""
        instance = Instance(
            variables=[
                Variable(var_id=0, profit=10, domain={1: 0}),
                Variable(var_id=1, profit=20, domain={1: 0}),
            ],
            constraints=[],
            capacity=0,
        )

        # Wrong number of assignments
        solution = Solution(
            claimed_profit=10,
            claimed_weight=0,
            n_candidates=3,  # claims 3 but only 1 assignment
            n_selected=1,
            assignments=[1],  # missing assignments
        )

        result = verify(instance, solution)

        assert not result.is_valid
        assert any("mismatch" in e.lower() for e in result.errors)


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_empty_solution(self):
        """Test solution with no photos selected."""
        instance = Instance(
            variables=[
                Variable(var_id=0, profit=10, domain={1: 0}),
                Variable(var_id=1, profit=20, domain={1: 0}),
            ],
            constraints=[],
            capacity=0,
        )

        solution = Solution(
            claimed_profit=0,
            claimed_weight=0,
            n_candidates=2,
            n_selected=0,
            assignments=[0, 0],
        )

        result = verify(instance, solution)

        assert result.is_valid
        assert result.computed_profit == 0
        assert result.computed_selected == 0

    def test_stereo_assignment_value_13(self):
        """Test that value 13 (stereo) is handled correctly."""
        instance = Instance(
            variables=[
                Variable(var_id=0, profit=100, domain={13: 0}),  # stereo only
            ],
            constraints=[],
            capacity=0,
        )

        solution = Solution(
            claimed_profit=100,
            claimed_weight=0,
            n_candidates=1,
            n_selected=1,
            assignments=[13],
        )

        result = verify(instance, solution)

        assert result.is_valid
        assert result.computed_profit == 100

    def test_weight_calculation_normalization(self):
        """Test weight normalization for multi-orbit instances."""
        instance = Instance(
            variables=[
                Variable(var_id=0, profit=1000, domain={2: 451.15}),   # weight = 1
                Variable(var_id=1, profit=1000, domain={2: 902.3}),    # weight = 2
                Variable(var_id=2, profit=2000, domain={13: 1804.6}),  # weight = 4
            ],
            constraints=[],
            capacity=200,
        )

        solution = Solution(
            claimed_profit=4000,
            claimed_weight=7,
            n_candidates=3,
            n_selected=3,
            assignments=[2, 2, 13],
        )

        result = verify(instance, solution)

        assert result.is_valid
        assert result.computed_weight == 7  # 1 + 2 + 4

    def test_profit_mismatch_warning(self):
        """Test that profit mismatch generates warning but solution is valid."""
        instance = Instance(
            variables=[
                Variable(var_id=0, profit=10, domain={1: 0}),
            ],
            constraints=[],
            capacity=0,
        )

        solution = Solution(
            claimed_profit=999,  # wrong claimed profit
            claimed_weight=0,
            n_candidates=1,
            n_selected=1,
            assignments=[1],
        )

        result = verify(instance, solution)

        assert result.is_valid  # Still valid, just with warning
        assert result.computed_profit == 10
        assert len(result.warnings) > 0
        assert any("profit" in w.lower() for w in result.warnings)


class TestAllowedCombinations:
    """Test that valid constraint combinations pass."""

    def test_binary_constraint_different_cameras(self):
        """Test that different camera assignments pass binary constraints."""
        instance = Instance(
            variables=[
                Variable(var_id=0, profit=10, domain={1: 0, 2: 0, 3: 0}),
                Variable(var_id=1, profit=20, domain={1: 0, 2: 0, 3: 0}),
            ],
            constraints=[
                Constraint(
                    arity=2,
                    variables=[0, 1],
                    forbidden={(1, 1), (2, 2), (3, 3)},  # same camera forbidden
                )
            ],
            capacity=0,
        )

        # Valid: different cameras
        solution = Solution(
            claimed_profit=30,
            claimed_weight=0,
            n_candidates=2,
            n_selected=2,
            assignments=[1, 2],  # different cameras
        )

        result = verify(instance, solution)

        assert result.is_valid

    def test_ternary_constraint_allowed_combination(self):
        """Test that allowed ternary combinations pass."""
        instance = Instance(
            variables=[
                Variable(var_id=0, profit=10, domain={1: 0, 13: 0}),
                Variable(var_id=1, profit=20, domain={2: 0}),
                Variable(var_id=2, profit=30, domain={1: 0, 13: 0}),
            ],
            constraints=[
                Constraint(
                    arity=3,
                    variables=[0, 1, 2],
                    forbidden={(13, 2, 13)},  # only this specific combo forbidden
                )
            ],
            capacity=0,
        )

        # Valid: different combination
        solution = Solution(
            claimed_profit=60,
            claimed_weight=0,
            n_candidates=3,
            n_selected=3,
            assignments=[1, 2, 13],  # not (13, 2, 13)
        )

        result = verify(instance, solution)

        assert result.is_valid


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
