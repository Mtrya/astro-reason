"""Test BSK verifier against ground truth fixtures.

Validates that the BSK-based verifier produces metrics matching
the fixtures generated with the original constellation/ implementation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from verifier_bsk import AEOSVerifierBSK

FIXTURES_DIR = Path("fixtures")


def load_fixture(case_id: int):
    """Load fixture files for a case."""
    case_dir = FIXTURES_DIR / "cases" / f"{case_id:05d}"
    solution_path = FIXTURES_DIR / "solutions" / f"{case_id:05d}.json"
    metrics_path = FIXTURES_DIR / "metrics" / f"{case_id:05d}.json"

    with open(case_dir / "constellation.json") as f:
        constellation = json.load(f)
    with open(case_dir / "taskset.json") as f:
        taskset = json.load(f)
    with open(solution_path) as f:
        solution = json.load(f)
    with open(metrics_path) as f:
        expected_metrics = json.load(f)

    return constellation, taskset, solution, expected_metrics


def test_case_157_metrics():
    """Test against case 157 fixture (single case for initial validation)."""
    if not FIXTURES_DIR.exists():
        pytest.skip("Fixtures directory not found")

    case_id = 157
    try:
        constellation, taskset, solution, expected = load_fixture(case_id)
    except FileNotFoundError:
        pytest.skip(f"Case {case_id} fixture not found")

    # Run verifier
    verifier = AEOSVerifierBSK(constellation, taskset)
    result = verifier.verify(solution["assignments"])

    # Check valid flag
    assert result["valid"], "Verifier returned invalid result"

    # Compare metrics with tolerance
    # Tolerances account for float32 storage precision in fixtures
    expected_metrics = expected["metrics"]
    tolerances = {
        "CR": 1e-7,    # Ratio - floating-point accumulation
        "WCR": 1e-7,   # Weighted ratio - floating-point accumulation
        "PCR": 1e-7,   # Partial completion ratio - floating-point accumulation
        "WPCR": 1e-7,  # Weighted partial completion ratio
        "TAT": 1e-4,   # Time accumulation - float32 vs float64
        "PC": 1e-2,    # Power in watt-seconds - float32 precision
    }

    metrics_to_check = ["CR", "WCR", "PCR", "WPCR", "TAT", "PC"]
    for key in metrics_to_check:
        actual = result[key]
        exp = expected_metrics[key]
        diff = abs(actual - exp)
        tol = tolerances[key]
        assert diff < tol, (
            f"{key} mismatch for case {case_id}: "
            f"got {actual:.10f}, expected {exp:.10f}, diff={diff:.10e} (tol={tol:.2e})"
        )


@pytest.mark.slow
@pytest.mark.parametrize("case_id", [
    157,  # Test case from memory - known working
    # Add more case IDs as they become available
])
def test_specific_case(case_id: int):
    """Test against specific fixture cases."""
    if not FIXTURES_DIR.exists():
        pytest.skip("Fixtures directory not found")

    try:
        constellation, taskset, solution, expected = load_fixture(case_id)
    except FileNotFoundError:
        pytest.skip(f"Case {case_id} fixture not found")

    # Run verifier
    verifier = AEOSVerifierBSK(constellation, taskset)
    result = verifier.verify(solution["assignments"])

    # Check valid flag
    assert result["valid"], "Verifier returned invalid result"

    # Compare metrics with tolerance
    # Tolerances account for float32 storage precision in fixtures
    expected_metrics = expected["metrics"]
    tolerances = {
        "CR": 1e-7,    # Ratio - floating-point accumulation
        "WCR": 1e-7,   # Weighted ratio - floating-point accumulation
        "PCR": 1e-7,   # Partial completion ratio - floating-point accumulation
        "WPCR": 1e-7,  # Weighted partial completion ratio
        "TAT": 1e-4,   # Time accumulation - float32 vs float64
        "PC": 1e-2,    # Power in watt-seconds - float32 precision
    }

    metrics_to_check = ["CR", "WCR", "PCR", "WPCR", "TAT", "PC"]
    for key in metrics_to_check:
        actual = result[key]
        exp = expected_metrics[key]
        diff = abs(actual - exp)
        tol = tolerances[key]
        assert diff < tol, (
            f"{key} mismatch for case {case_id}: "
            f"got {actual:.10f}, expected {exp:.10f}, diff={diff:.10e} (tol={tol:.2e})"
        )


@pytest.mark.slow
def test_all_fixtures(all_fixtures):
    """Test against all available fixtures."""
    if not all_fixtures:
        pytest.skip("No fixtures available")

    failures = []

    for case_id, (constellation, taskset, solution, expected) in all_fixtures:
        try:
            verifier = AEOSVerifierBSK(constellation, taskset)
            result = verifier.verify(solution["assignments"])

            if not result["valid"]:
                failures.append(f"Case {case_id}: invalid result")
                continue

            expected_metrics = expected["metrics"]
            tolerances = {
                "CR": 1e-7, "WCR": 1e-7, "PCR": 1e-7, "WPCR": 1e-7,
                "TAT": 1e-4, "PC": 1e-2,
            }

            for key in ["CR", "WCR", "PCR", "WPCR", "TAT", "PC"]:
                actual = result[key]
                exp = expected_metrics[key]
                diff = abs(actual - exp)
                tol = tolerances[key]
                if diff >= tol:
                    failures.append(
                        f"Case {case_id}: {key} mismatch: "
                        f"got {actual:.10f}, expected {exp:.10f}, diff={diff:.2e}, tol={tol:.2e}"
                    )

        except Exception as e:
            failures.append(f"Case {case_id}: exception: {e}")

    if failures:
        pytest.fail("\n".join(failures))
