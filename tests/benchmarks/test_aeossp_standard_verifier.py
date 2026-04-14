"""Focused tests for the aeossp_standard verifier."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import brahe
import pytest
import yaml

from benchmarks.aeossp_standard.verifier import verify_solution


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "benchmarks" / "aeossp_standard" / "dataset"
INDEX_PATH = DATASET_DIR / "index.json"
EXAMPLE_SOLUTION_PATH = DATASET_DIR / "example_solution.json"

_TLE_LINE1 = "1 63255U 25052AX  25198.17518200  .00001597  00000-0  15702-3 0  9994"
_TLE_LINE2 = "2 63255  97.7253  91.1881 0000724 209.0702 151.0478 14.93504225 18614"


def _write_yaml(path: Path, payload: object) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _ensure_brahe_ready() -> None:
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )


def _datetime_to_epoch(value: datetime) -> brahe.Epoch:
    value = value.astimezone(UTC)
    second = float(value.second) + (value.microsecond / 1_000_000.0)
    return brahe.Epoch.from_datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        second,
        0.0,
        brahe.TimeSystem.UTC,
    )


def _subpoint_lon_lat(start_time: datetime) -> tuple[float, float]:
    _ensure_brahe_ready()
    propagator = brahe.SGPPropagator.from_tle(_TLE_LINE1, _TLE_LINE2, 5.0)
    state_ecef = propagator.state_ecef(_datetime_to_epoch(start_time))
    longitude_deg, latitude_deg, _altitude_m = brahe.position_ecef_to_geodetic(
        state_ecef[:3], brahe.AngleFormat.DEGREES
    )
    return float(longitude_deg), float(latitude_deg)


def _write_case(
    tmp_path: Path,
    *,
    horizon_start: datetime,
    horizon_end: datetime,
    tasks: list[dict],
    resource_overrides: dict[str, float] | None = None,
) -> Path:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    mission = {
        "mission": {
            "case_id": "case_test",
            "horizon_start": _iso_z(horizon_start),
            "horizon_end": _iso_z(horizon_end),
            "action_time_step_s": 5,
            "geometry_sample_step_s": 5,
            "resource_sample_step_s": 10,
            "propagation": {
                "model": "sgp4",
                "frame_inertial": "gcrf",
                "frame_fixed": "itrf",
                "earth_shape": "wgs84",
            },
            "scoring": {
                "ranking_order": ["valid", "WCR", "CR", "TAT", "PC"],
                "reported_metrics": ["CR", "WCR", "TAT", "PC"],
            },
        }
    }
    resource_model = {
        "battery_capacity_wh": 20.0,
        "initial_battery_wh": 20.0,
        "idle_power_w": 60.0,
        "imaging_power_w": 50.0,
        "slew_power_w": 40.0,
        "sunlit_charge_power_w": 0.0,
    }
    if resource_overrides:
        resource_model.update(resource_overrides)
    satellites = {
        "satellites": [
            {
                "satellite_id": "sat_001",
                "norad_catalog_id": 63255,
                "tle_line1": _TLE_LINE1,
                "tle_line2": _TLE_LINE2,
                "sensor": {"sensor_type": "visible"},
                "attitude_model": {
                    "max_slew_velocity_deg_per_s": 2.0,
                    "max_slew_acceleration_deg_per_s2": 1.0,
                    "settling_time_s": 2.0,
                    "max_off_nadir_deg": 5.0,
                },
                "resource_model": resource_model,
            }
        ]
    }
    _write_yaml(case_dir / "mission.yaml", mission)
    _write_yaml(case_dir / "satellites.yaml", satellites)
    _write_yaml(case_dir / "tasks.yaml", {"tasks": tasks})
    return case_dir


def test_verify_solution_rejects_malformed_solution(tmp_path: Path) -> None:
    horizon_start = datetime(2025, 7, 17, 4, 10, tzinfo=UTC)
    horizon_end = horizon_start + timedelta(minutes=10)
    lon_deg, lat_deg = _subpoint_lon_lat(horizon_start + timedelta(minutes=2))
    case_dir = _write_case(
        tmp_path,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        tasks=[
            {
                "task_id": "task_001",
                "name": "target",
                "latitude_deg": lat_deg,
                "longitude_deg": lon_deg,
                "altitude_m": 0.0,
                "release_time": _iso_z(horizon_start + timedelta(minutes=2)),
                "due_time": _iso_z(horizon_start + timedelta(minutes=3)),
                "required_duration_s": 5,
                "required_sensor_type": "visible",
                "weight": 2.0,
            }
        ],
    )
    malformed_solution_path = tmp_path / "malformed_solution.json"
    malformed_solution_path.write_text("[]\n", encoding="utf-8")

    result = verify_solution(case_dir, malformed_solution_path)

    assert result.valid is False
    assert result.violations == ["solution.json must be a JSON object"]


def test_verify_solution_valid_case_reports_exact_metrics(tmp_path: Path) -> None:
    horizon_start = datetime(2025, 7, 17, 4, 10, tzinfo=UTC)
    horizon_end = horizon_start + timedelta(minutes=10)
    action_start = horizon_start + timedelta(minutes=2)
    action_end = action_start + timedelta(seconds=5)
    lon_deg, lat_deg = _subpoint_lon_lat(action_start)
    case_dir = _write_case(
        tmp_path,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        tasks=[
            {
                "task_id": "task_001",
                "name": "target",
                "latitude_deg": lat_deg,
                "longitude_deg": lon_deg,
                "altitude_m": 0.0,
                "release_time": _iso_z(action_start),
                "due_time": _iso_z(action_start + timedelta(seconds=30)),
                "required_duration_s": 5,
                "required_sensor_type": "visible",
                "weight": 2.0,
            }
        ],
    )
    solution_path = tmp_path / "solution.json"
    _write_json(
        solution_path,
        {
            "actions": [
                {
                    "type": "observation",
                    "satellite_id": "sat_001",
                    "task_id": "task_001",
                    "start_time": _iso_z(action_start),
                    "end_time": _iso_z(action_end),
                }
            ]
        },
    )

    result = verify_solution(case_dir, solution_path)

    assert result.valid is True
    assert result.metrics["CR"] == pytest.approx(1.0)
    assert result.metrics["WCR"] == pytest.approx(1.0)
    assert result.metrics["TAT"] == pytest.approx(5.0)
    slew_time_s = result.diagnostics["per_satellite_resource_summary"]["sat_001"]["total_slew_time_s"]
    expected_pc = (60.0 * 600.0 + 50.0 * 5.0 + 40.0 * slew_time_s) / 3600.0
    assert result.metrics["PC"] == pytest.approx(expected_pc)


def test_verify_solution_rejects_battery_depletion(tmp_path: Path) -> None:
    horizon_start = datetime(2025, 7, 17, 4, 10, tzinfo=UTC)
    horizon_end = horizon_start + timedelta(minutes=10)
    lon_deg, lat_deg = _subpoint_lon_lat(horizon_start + timedelta(minutes=2))
    case_dir = _write_case(
        tmp_path,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        tasks=[
            {
                "task_id": "task_001",
                "name": "target",
                "latitude_deg": lat_deg,
                "longitude_deg": lon_deg,
                "altitude_m": 0.0,
                "release_time": _iso_z(horizon_start + timedelta(minutes=2)),
                "due_time": _iso_z(horizon_start + timedelta(minutes=3)),
                "required_duration_s": 5,
                "required_sensor_type": "visible",
                "weight": 2.0,
            }
        ],
        resource_overrides={
            "battery_capacity_wh": 5.0,
            "initial_battery_wh": 1.0,
            "idle_power_w": 1000.0,
            "imaging_power_w": 0.0,
            "slew_power_w": 0.0,
        },
    )
    solution_path = tmp_path / "solution.json"
    _write_json(solution_path, {"actions": []})

    result = verify_solution(case_dir, solution_path)

    assert result.valid is False
    assert any("battery depletes below zero" in violation for violation in result.violations)


def test_verify_solution_rejects_insufficient_slew_gap(tmp_path: Path) -> None:
    horizon_start = datetime(2025, 7, 17, 4, 10, tzinfo=UTC)
    horizon_end = horizon_start + timedelta(minutes=10)
    action_start = horizon_start + timedelta(minutes=2)
    first_lon_deg, first_lat_deg = _subpoint_lon_lat(action_start)
    second_lon_deg, second_lat_deg = _subpoint_lon_lat(action_start + timedelta(seconds=5))
    case_dir = _write_case(
        tmp_path,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        tasks=[
            {
                "task_id": "task_001",
                "name": "target_a",
                "latitude_deg": first_lat_deg,
                "longitude_deg": first_lon_deg,
                "altitude_m": 0.0,
                "release_time": _iso_z(action_start - timedelta(seconds=30)),
                "due_time": _iso_z(action_start + timedelta(seconds=30)),
                "required_duration_s": 5,
                "required_sensor_type": "visible",
                "weight": 1.0,
            },
            {
                "task_id": "task_002",
                "name": "target_b",
                "latitude_deg": second_lat_deg,
                "longitude_deg": second_lon_deg,
                "altitude_m": 0.0,
                "release_time": _iso_z(action_start - timedelta(seconds=30)),
                "due_time": _iso_z(action_start + timedelta(seconds=30)),
                "required_duration_s": 5,
                "required_sensor_type": "visible",
                "weight": 1.0,
            },
        ],
    )
    solution_path = tmp_path / "solution.json"
    _write_json(
        solution_path,
        {
            "actions": [
                {
                    "type": "observation",
                    "satellite_id": "sat_001",
                    "task_id": "task_001",
                    "start_time": _iso_z(action_start),
                    "end_time": _iso_z(action_start + timedelta(seconds=5)),
                },
                {
                    "type": "observation",
                    "satellite_id": "sat_001",
                    "task_id": "task_002",
                    "start_time": _iso_z(action_start + timedelta(seconds=5)),
                    "end_time": _iso_z(action_start + timedelta(seconds=10)),
                },
            ]
        },
    )

    result = verify_solution(case_dir, solution_path)

    assert result.valid is False
    assert any("insufficient slew/settle time" in violation for violation in result.violations)


def test_verify_solution_example_smoke_case_reports_nonzero_completion() -> None:
    index_payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    case_dir = DATASET_DIR / "cases" / index_payload["example_smoke_case_id"]

    result = verify_solution(case_dir, EXAMPLE_SOLUTION_PATH)

    assert result.valid is True
    assert result.metrics["CR"] > 0.0
    assert result.metrics["WCR"] > 0.0
    assert result.metrics["TAT"] is not None
