"""Focused tests for the aeossp_standard verifier."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.aeossp_standard.verifier import verify_solution


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "benchmarks" / "aeossp_standard" / "dataset"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "aeossp_standard"
INDEX_PATH = DATASET_DIR / "index.json"
EXAMPLE_SOLUTION_PATH = DATASET_DIR / "example_solution.json"
FIXTURE_NAMES = (
    "full_completion_valid",
    "zero_completion_valid",
    "duplicate_observation_no_bonus_valid",
    "sensor_type_mismatch_invalid",
    "visibility_invalid",
    "observation_overlap_invalid",
    "slew_gap_invalid",
    "battery_depletion_invalid",
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _assert_expected_value(actual: object, expected: object) -> None:
    if isinstance(expected, float):
        assert actual == pytest.approx(expected)
        return
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        for key, value in expected.items():
            assert key in actual
            _assert_expected_value(actual[key], value)
        return
    if isinstance(expected, list):
        assert isinstance(actual, list)
        assert len(actual) == len(expected)
        for actual_item, expected_item in zip(actual, expected):
            _assert_expected_value(actual_item, expected_item)
        return
    assert actual == expected


def _load_fixture(name: str) -> tuple[Path, Path, dict[str, object]]:
    fixture_dir = FIXTURES_DIR / name
    expected = json.loads((fixture_dir / "expected.json").read_text(encoding="utf-8"))
    return fixture_dir, fixture_dir / "solution.json", expected


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_verify_solution_fixture_regressions(fixture_name: str) -> None:
    case_dir, solution_path, expected = _load_fixture(fixture_name)

    result = verify_solution(case_dir, solution_path)

    assert result.valid is expected["valid"]
    _assert_expected_value(result.metrics, expected["metrics"])

    diagnostics = expected.get("diagnostics")
    if diagnostics is not None:
        _assert_expected_value(result.diagnostics, diagnostics)

    for substring in expected.get("violation_substrings", []):
        assert any(substring in violation for violation in result.violations)

    action_failures = result.diagnostics.get("action_failures", [])
    assert len(action_failures) == expected.get("action_failures_len", 0)

    first_action_failure = expected.get("first_action_failure")
    if first_action_failure is not None:
        assert action_failures
        actual = action_failures[0]
        for key, value in first_action_failure.items():
            if key == "reason_substring":
                assert value in actual["reason"]
            else:
                assert actual[key] == value


def test_verify_solution_rejects_malformed_solution(tmp_path: Path) -> None:
    case_dir = FIXTURES_DIR / "full_completion_valid"
    malformed_solution_path = tmp_path / "malformed_solution.json"
    malformed_solution_path.write_text("[]\n", encoding="utf-8")

    result = verify_solution(case_dir, malformed_solution_path)

    assert result.valid is False
    assert result.violations == ["solution.json must be a JSON object"]


@pytest.mark.parametrize(
    ("payload", "expected_violation"),
    (
        (
            {
                "actions": [
                    {
                        "type": "observation",
                        "satellite_id": "sat_missing",
                        "task_id": "task_001",
                        "start_time": "2025-07-17T04:12:00Z",
                        "end_time": "2025-07-17T04:12:05Z",
                    }
                ]
            },
            "unknown satellite_id",
        ),
        (
            {
                "actions": [
                    {
                        "type": "observation",
                        "satellite_id": "sat_001",
                        "task_id": "task_missing",
                        "start_time": "2025-07-17T04:12:00Z",
                        "end_time": "2025-07-17T04:12:05Z",
                    }
                ]
            },
            "unknown task_id",
        ),
    ),
)
def test_verify_solution_rejects_unknown_references(
    tmp_path: Path,
    payload: dict[str, object],
    expected_violation: str,
) -> None:
    solution_path = tmp_path / "solution.json"
    _write_json(solution_path, payload)

    result = verify_solution(FIXTURES_DIR / "full_completion_valid", solution_path)

    assert result.valid is False
    assert any(expected_violation in violation for violation in result.violations)


@pytest.mark.parametrize(
    ("payload", "expected_violation"),
    (
        (
            {
                "actions": [
                    {
                        "type": "observation",
                        "satellite_id": "sat_001",
                        "task_id": "task_001",
                        "start_time": "2025-07-17T04:12:01Z",
                        "end_time": "2025-07-17T04:12:06Z",
                    }
                ]
            },
            "must align to the 5s action grid",
        ),
        (
            {
                "actions": [
                    {
                        "type": "observation",
                        "satellite_id": "sat_001",
                        "task_id": "task_001",
                        "start_time": "2025-07-17T04:20:00Z",
                        "end_time": "2025-07-17T04:20:05Z",
                    }
                ]
            },
            "outside the mission horizon",
        ),
    ),
)
def test_verify_solution_rejects_bad_action_timing(
    tmp_path: Path,
    payload: dict[str, object],
    expected_violation: str,
) -> None:
    solution_path = tmp_path / "solution.json"
    _write_json(solution_path, payload)

    result = verify_solution(FIXTURES_DIR / "full_completion_valid", solution_path)

    assert result.valid is False
    assert any(expected_violation in violation for violation in result.violations)


def test_verify_solution_example_smoke_case_reports_nonzero_completion() -> None:
    index_payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    case_dir = DATASET_DIR / "cases" / index_payload["example_smoke_case_id"]

    result = verify_solution(case_dir, EXAMPLE_SOLUTION_PATH)

    assert result.valid is True
    assert result.metrics["CR"] > 0.0
    assert result.metrics["WCR"] > 0.0
    assert result.metrics["TAT"] is not None
