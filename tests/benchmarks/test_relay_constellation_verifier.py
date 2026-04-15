"""Focused tests for the relay_constellation verifier."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import brahe
import numpy as np
import pytest

from benchmarks.relay_constellation.verifier import verify_solution


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "benchmarks" / "relay_constellation" / "dataset"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "relay_constellation"
FIXTURE_NAMES = (
    "full_service_valid",
    "served_time_only_latency_valid",
    "ground_visibility_invalid",
    "isl_occultation_invalid",
    "concurrency_cap_invalid",
    "contention_deterministic_valid",
    "ground_transit_forbidden_valid",
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    case_dir = FIXTURES_DIR / "full_service_valid"
    malformed_solution_path = tmp_path / "malformed_solution.json"
    malformed_solution_path.write_text("[]\n", encoding="utf-8")

    result = verify_solution(case_dir, malformed_solution_path)

    assert result.valid is False
    assert result.violations == ["solution.json must be a JSON object"]


def test_verify_solution_rejects_duplicate_demand_ids(tmp_path: Path) -> None:
    case_dir = tmp_path / "case_duplicate_demands"
    fixture_dir = FIXTURES_DIR / "full_service_valid"
    for filename in ("manifest.json", "network.json"):
        (case_dir / filename).parent.mkdir(parents=True, exist_ok=True)
        (case_dir / filename).write_text((fixture_dir / filename).read_text(encoding="utf-8"), encoding="utf-8")
    _write_json(
        case_dir / "demands.json",
        {
            "demanded_windows": [
                {
                    "demand_id": "demand_001",
                    "source_endpoint_id": "ground_001",
                    "destination_endpoint_id": "ground_002",
                    "start_time": "2026-01-01T00:00:00Z",
                    "end_time": "2026-01-01T00:01:00Z",
                    "weight": 1.0,
                },
                {
                    "demand_id": "demand_001",
                    "source_endpoint_id": "ground_001",
                    "destination_endpoint_id": "ground_002",
                    "start_time": "2026-01-01T00:01:00Z",
                    "end_time": "2026-01-01T00:02:00Z",
                    "weight": 1.0,
                },
            ]
        },
    )

    result = verify_solution(case_dir, FIXTURES_DIR / "full_service_valid" / "solution.json")

    assert result.valid is False
    assert result.violations == ["Duplicate demand_id: demand_001"]


def test_verify_solution_rejects_invalid_added_orbit(tmp_path: Path) -> None:
    low_orbit_state = np.asarray(
        brahe.state_koe_to_eci(
            np.asarray(
                [float(brahe.R_EARTH) + 100_000.0, 0.0, 45.0, 0.0, 0.0, 0.0],
                dtype=float,
            ),
            brahe.AngleFormat.DEGREES,
        ),
        dtype=float,
    )
    solution_path = tmp_path / "invalid_orbit_solution.json"
    _write_json(
        solution_path,
        {
            "added_satellites": [
                {
                    "satellite_id": "added_001",
                    "x_m": float(low_orbit_state[0]),
                    "y_m": float(low_orbit_state[1]),
                    "z_m": float(low_orbit_state[2]),
                    "vx_m_s": float(low_orbit_state[3]),
                    "vy_m_s": float(low_orbit_state[4]),
                    "vz_m_s": float(low_orbit_state[5]),
                }
            ],
            "actions": [],
        },
    )

    result = verify_solution(FIXTURES_DIR / "full_service_valid", solution_path)

    assert result.valid is False
    assert any("below min_altitude_m" in violation for violation in result.violations)


def test_verify_solution_rejects_off_grid_action(tmp_path: Path) -> None:
    solution_path = tmp_path / "off_grid_solution.json"
    _write_json(
        solution_path,
        {
            "added_satellites": [],
            "actions": [
                {
                    "action_type": "ground_link",
                    "endpoint_id": "ground_001",
                    "satellite_id": "backbone_001",
                    "start_time": "2026-01-01T00:00:30Z",
                    "end_time": "2026-01-01T00:01:00Z",
                }
            ],
        },
    )

    result = verify_solution(FIXTURES_DIR / "full_service_valid", solution_path)

    assert result.valid is False
    assert any("routing_step_s grid" in violation for violation in result.violations)


def test_verify_solution_returns_invalid_result_for_bad_case_demand_grid(tmp_path: Path) -> None:
    case_dir = tmp_path / "case_bad_demand_grid"
    fixture_dir = FIXTURES_DIR / "full_service_valid"
    for filename in ("manifest.json", "network.json"):
        (case_dir / filename).parent.mkdir(parents=True, exist_ok=True)
        (case_dir / filename).write_text((fixture_dir / filename).read_text(encoding="utf-8"), encoding="utf-8")
    _write_json(
        case_dir / "demands.json",
        {
            "demanded_windows": [
                {
                    "demand_id": "demand_001",
                    "source_endpoint_id": "ground_001",
                    "destination_endpoint_id": "ground_002",
                    "start_time": "2026-01-01T00:00:30Z",
                    "end_time": "2026-01-01T00:01:00Z",
                    "weight": 1.0,
                }
            ]
        },
    )

    result = verify_solution(case_dir, FIXTURES_DIR / "full_service_valid" / "solution.json")

    assert result.valid is False
    assert any("routing_step_s grid" in violation for violation in result.violations)


def test_verify_solution_rejects_non_integral_horizon_length(tmp_path: Path) -> None:
    case_dir = tmp_path / "case_bad_horizon"
    fixture_dir = FIXTURES_DIR / "full_service_valid"
    (case_dir / "network.json").parent.mkdir(parents=True, exist_ok=True)
    (case_dir / "network.json").write_text(
        (fixture_dir / "network.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (case_dir / "demands.json").write_text(
        (fixture_dir / "demands.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["horizon_end"] = "2026-01-01T00:05:30Z"
    _write_json(case_dir / "manifest.json", manifest)

    result = verify_solution(case_dir, FIXTURES_DIR / "full_service_valid" / "solution.json")

    assert result.valid is False
    assert result.violations == [
        "manifest.json horizon must be exactly divisible by routing_step_s"
    ]


def test_verify_solution_normalizes_optional_float_parse_errors(tmp_path: Path) -> None:
    case_dir = tmp_path / "case_bad_optional_float"
    fixture_dir = FIXTURES_DIR / "full_service_valid"
    for filename in ("network.json", "demands.json"):
        (case_dir / filename).parent.mkdir(parents=True, exist_ok=True)
        (case_dir / filename).write_text(
            (fixture_dir / filename).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["constraints"]["max_eccentricity"] = None
    _write_json(case_dir / "manifest.json", manifest)

    result = verify_solution(case_dir, FIXTURES_DIR / "full_service_valid" / "solution.json")

    assert result.valid is False
    assert result.violations == ["manifest.json.constraints.max_eccentricity must be numeric"]


def test_verify_solution_example_smoke_case_reports_nonzero_service() -> None:
    index_payload = json.loads((DATASET_DIR / "index.json").read_text(encoding="utf-8"))
    case_dir = DATASET_DIR / "cases" / Path(index_payload["example_smoke_case"])
    solution_path = DATASET_DIR / "example_solution.json"

    result = verify_solution(case_dir, solution_path)

    assert result.valid is True
    assert result.metrics["service_fraction"] > 0.0
    assert result.metrics["worst_demand_service_fraction"] == 0.0
    assert result.metrics["num_demanded_windows"] > 0
    assert result.metrics["mean_latency_ms"] is not None
