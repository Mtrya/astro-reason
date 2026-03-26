"""Focused tests for the revisit_constellation verifier."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import math
from pathlib import Path

import brahe
import numpy as np
import pytest

from benchmarks.revisit_constellation.verifier import (
    ObservationRecord,
    load_case,
    load_solution,
    verify,
    verify_solution,
)
from benchmarks.revisit_constellation.verifier.engine import _compute_metrics
from benchmarks.revisit_constellation.verifier.run import main as cli_main


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "revisit_constellation" / "zero_observation"
MU_EARTH_M3_S2 = 3.986004418e14


def _ensure_brahe_ready() -> None:
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )


def _parse_iso8601_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


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


def _base_assets() -> dict:
    return {
        "satellite_model": {
            "model_name": "test_bus",
            "sensor": {
                "field_of_view_half_angle_deg": 180.0,
                "max_range_m": 1.0e9,
                "obs_discharge_rate_w": 5.0,
                "obs_store_rate_mb_per_s": 1.0,
            },
            "terminals": [
                {
                    "downlink_release_rate_mb_per_s": 1.0,
                    "downlink_discharge_rate_w": 5.0,
                }
            ],
            "resource_model": {
                "battery_capacity_wh": 1.0e6,
                "storage_capacity_mb": 1.0e6,
                "initial_battery_wh": 1.0e6,
                "initial_storage_mb": 1.0e3,
                "idle_discharge_rate_w": 1.0,
                "sunlight_charge_rate_w": 0.0,
            },
            "attitude_model": {
                "max_slew_velocity_deg_per_sec": 2.0,
                "max_slew_acceleration_deg_per_sec2": 1.0,
                "settling_time_sec": 1.0,
                "maneuver_discharge_rate_w": 2.0,
            },
            "min_altitude_m": 100000.0,
            "max_altitude_m": 1000000.0,
        },
        "max_num_satellites": 2,
        "ground_stations": [
            {
                "id": "gs1",
                "name": "GS1",
                "latitude_deg": 0.0,
                "longitude_deg": 0.0,
                "altitude_m": 0.0,
                "min_elevation_deg": -90.0,
                "min_duration_sec": 1.0,
            }
        ],
    }


def _base_mission(
    *,
    horizon_start: str = "2025-01-01T00:00:00Z",
    horizon_end: str = "2025-01-01T01:00:00Z",
) -> dict:
    return {
        "horizon_start": horizon_start,
        "horizon_end": horizon_end,
        "targets": [
            {
                "id": "t1",
                "name": "T1",
                "latitude_deg": 0.0,
                "longitude_deg": 0.0,
                "altitude_m": 0.0,
                "expected_revisit_period_hours": 0.5,
                "min_elevation_deg": -90.0,
                "max_slant_range_m": 1.0e9,
                "min_duration_sec": 1.0,
            }
        ],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_case(tmp_path: Path, *, assets: dict | None = None, mission: dict | None = None) -> Path:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    _write_json(case_dir / "assets.json", assets or _base_assets())
    _write_json(case_dir / "mission.json", mission or _base_mission())
    return case_dir


def _write_solution(tmp_path: Path, payload: dict) -> Path:
    solution_path = tmp_path / "solution.json"
    _write_json(solution_path, payload)
    return solution_path


def _circular_speed_m_s(radius_m: float) -> float:
    return math.sqrt(MU_EARTH_M3_S2 / radius_m)


def _satellite_at_radius_with_tangential_speed(
    *,
    satellite_id: str = "sat1",
    radius_m: float,
    speed_m_s: float,
) -> dict:
    return {
        "satellite_id": satellite_id,
        "x_m": radius_m,
        "y_m": 0.0,
        "z_m": 0.0,
        "vx_m_s": 0.0,
        "vy_m_s": speed_m_s,
        "vz_m_s": 0.0,
    }


def _surface_eci_unit_vector(
    timestamp: str,
    *,
    longitude_deg: float = 0.0,
    latitude_deg: float = 0.0,
    altitude_m: float = 0.0,
) -> np.ndarray:
    _ensure_brahe_ready()
    epoch = _datetime_to_epoch(_parse_iso8601_utc(timestamp))
    ecef_position = np.asarray(
        brahe.position_geodetic_to_ecef(
            [longitude_deg, latitude_deg, altitude_m],
            brahe.AngleFormat.DEGREES,
        ),
        dtype=float,
    )
    eci_position = np.asarray(brahe.position_ecef_to_eci(epoch, ecef_position), dtype=float)
    return eci_position / np.linalg.norm(eci_position)


def _orthogonal_unit_vector(vector: np.ndarray) -> np.ndarray:
    z_axis = np.asarray([0.0, 0.0, 1.0], dtype=float)
    tangent = np.cross(z_axis, vector)
    if np.linalg.norm(tangent) < 1e-9:
        tangent = np.cross(np.asarray([0.0, 1.0, 0.0], dtype=float), vector)
    return tangent / np.linalg.norm(tangent)


def _overhead_satellite(
    timestamp: str,
    *,
    satellite_id: str = "sat1",
    longitude_deg: float = 0.0,
    latitude_deg: float = 0.0,
    altitude_m: float = 500000.0,
) -> dict:
    radial_unit = _surface_eci_unit_vector(
        timestamp,
        longitude_deg=longitude_deg,
        latitude_deg=latitude_deg,
    )
    radius_m = brahe.R_EARTH + altitude_m
    position_m = radial_unit * radius_m
    velocity_m_s = _orthogonal_unit_vector(radial_unit) * _circular_speed_m_s(radius_m)
    return {
        "satellite_id": satellite_id,
        "x_m": float(position_m[0]),
        "y_m": float(position_m[1]),
        "z_m": float(position_m[2]),
        "vx_m_s": float(velocity_m_s[0]),
        "vy_m_s": float(velocity_m_s[1]),
        "vz_m_s": float(velocity_m_s[2]),
    }


def _sunlit_satellite(
    timestamp: str,
    *,
    satellite_id: str = "sat1",
    altitude_m: float = 500000.0,
) -> dict:
    _ensure_brahe_ready()
    epoch = _datetime_to_epoch(_parse_iso8601_utc(timestamp))
    sun_hat = np.asarray(brahe.sun_position(epoch), dtype=float)
    sun_hat = sun_hat / np.linalg.norm(sun_hat)
    radius_m = brahe.R_EARTH + altitude_m
    position_m = sun_hat * radius_m
    velocity_m_s = _orthogonal_unit_vector(sun_hat) * _circular_speed_m_s(radius_m)
    return {
        "satellite_id": satellite_id,
        "x_m": float(position_m[0]),
        "y_m": float(position_m[1]),
        "z_m": float(position_m[2]),
        "vx_m_s": float(velocity_m_s[0]),
        "vy_m_s": float(velocity_m_s[1]),
        "vz_m_s": float(velocity_m_s[2]),
    }


def _solution_payload(*, satellites: list[dict], actions: list[dict]) -> dict:
    return {"satellites": satellites, "actions": actions}


def test_zero_observation_fixture_matches_expected_metrics() -> None:
    expected = json.loads((FIXTURE_DIR / "expected.json").read_text(encoding="utf-8"))

    result = verify_solution(FIXTURE_DIR, FIXTURE_DIR / "solution.json")

    assert result.is_valid is expected["is_valid"]
    assert result.metrics["mean_revisit_gap_hours"] == pytest.approx(
        expected["metrics"]["mean_revisit_gap_hours"]
    )
    assert result.metrics["max_revisit_gap_hours"] == pytest.approx(
        expected["metrics"]["max_revisit_gap_hours"]
    )
    assert result.metrics["satellite_count"] == expected["metrics"]["satellite_count"]
    assert result.metrics["threshold_satisfied"] is expected["metrics"]["threshold_satisfied"]
    assert result.metrics["target_gap_summary"]["t1"]["observation_count"] == 0


def test_verify_solution_helper_matches_manual_loading() -> None:
    instance = load_case(FIXTURE_DIR)
    solution = load_solution(FIXTURE_DIR / "solution.json")

    direct = verify(instance, solution)
    via_helper = verify_solution(FIXTURE_DIR, FIXTURE_DIR / "solution.json")

    assert direct.is_valid == via_helper.is_valid
    assert direct.metrics["mean_revisit_gap_hours"] == pytest.approx(
        via_helper.metrics["mean_revisit_gap_hours"]
    )
    assert direct.metrics["max_revisit_gap_hours"] == pytest.approx(
        via_helper.metrics["max_revisit_gap_hours"]
    )


def test_cli_main_uses_case_directory_contract(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main([str(FIXTURE_DIR), str(FIXTURE_DIR / "solution.json")])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"is_valid": true' in captured.out


def test_load_case_rejects_missing_assets_file(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    _write_json(case_dir / "mission.json", _base_mission())

    with pytest.raises(FileNotFoundError, match="Missing case file"):
        load_case(case_dir)


def test_load_case_rejects_duplicate_ground_station_ids(tmp_path: Path) -> None:
    assets = _base_assets()
    duplicate_station = deepcopy(assets["ground_stations"][0])
    assets["ground_stations"].append(duplicate_station)
    case_dir = _write_case(tmp_path, assets=assets)

    with pytest.raises(ValueError, match="Ground station IDs must be unique"):
        load_case(case_dir)


def test_load_case_rejects_duplicate_target_ids(tmp_path: Path) -> None:
    mission = _base_mission()
    duplicate_target = deepcopy(mission["targets"][0])
    mission["targets"].append(duplicate_target)
    case_dir = _write_case(tmp_path, mission=mission)

    with pytest.raises(ValueError, match="Target IDs must be unique"):
        load_case(case_dir)


def test_load_solution_rejects_duplicate_satellite_ids(tmp_path: Path) -> None:
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[
                _overhead_satellite("2025-01-01T00:00:00Z", satellite_id="sat1"),
                _overhead_satellite("2025-01-01T00:00:00Z", satellite_id="sat1"),
            ],
            actions=[],
        ),
    )

    with pytest.raises(ValueError, match="Duplicate satellite_id"):
        load_solution(solution_path)


def test_load_solution_rejects_timezone_free_action_timestamp(tmp_path: Path) -> None:
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_overhead_satellite("2025-01-01T00:00:00Z")],
            actions=[
                {
                    "action_type": "observation",
                    "satellite_id": "sat1",
                    "target_id": "t1",
                    "start": "2025-01-01T00:00:00",
                    "end": "2025-01-01T00:00:10Z",
                }
            ],
        ),
    )

    with pytest.raises(ValueError, match="Timestamp must include timezone information"):
        load_solution(solution_path)


def test_verify_solution_returns_invalid_result_for_malformed_case(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    _write_json(case_dir / "mission.json", _base_mission())
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(satellites=[_overhead_satellite("2025-01-01T00:00:00Z")], actions=[]),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("Failed to load case" in error for error in result.errors)
    assert any("Missing case file" in error for error in result.errors)


def test_verify_solution_returns_invalid_result_for_malformed_solution(tmp_path: Path) -> None:
    case_dir = _write_case(tmp_path)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[
                _overhead_satellite("2025-01-01T00:00:00Z", satellite_id="sat1"),
                _overhead_satellite("2025-01-01T00:00:00Z", satellite_id="sat1"),
            ],
            actions=[],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("Failed to load solution" in error for error in result.errors)
    assert any("Duplicate satellite_id" in error for error in result.errors)


def test_verify_rejects_satellite_below_min_altitude(tmp_path: Path) -> None:
    case_dir = _write_case(tmp_path)
    radius_m = brahe.R_EARTH + 50000.0
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[
                _satellite_at_radius_with_tangential_speed(
                    radius_m=radius_m,
                    speed_m_s=_circular_speed_m_s(radius_m),
                )
            ],
            actions=[],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("below min altitude" in error for error in result.errors)


def test_verify_rejects_suborbital_initial_state_with_allowed_start_altitude(tmp_path: Path) -> None:
    case_dir = _write_case(tmp_path)
    radius_m = brahe.R_EARTH + 500000.0
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[
                _satellite_at_radius_with_tangential_speed(
                    radius_m=radius_m,
                    speed_m_s=7000.0,
                )
            ],
            actions=[],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("perigee below min altitude" in error for error in result.errors)


def test_verify_rejects_escape_initial_state_with_allowed_start_altitude(tmp_path: Path) -> None:
    case_dir = _write_case(tmp_path)
    radius_m = brahe.R_EARTH + 500000.0
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[
                _satellite_at_radius_with_tangential_speed(
                    radius_m=radius_m,
                    speed_m_s=11000.0,
                )
            ],
            actions=[],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("invalid initial orbit" in error for error in result.errors)
    assert any("not a bound Earth orbit" in error for error in result.errors)


@pytest.mark.parametrize(
    ("action", "expected_fragment"),
    [
        (
            {
                "action_type": "observation",
                "satellite_id": "missing_sat",
                "target_id": "t1",
                "start": "2025-01-01T00:00:00Z",
                "end": "2025-01-01T00:00:10Z",
            },
            "unknown satellite_id",
        ),
        (
            {
                "action_type": "observation",
                "satellite_id": "sat1",
                "target_id": "missing_target",
                "start": "2025-01-01T00:00:00Z",
                "end": "2025-01-01T00:00:10Z",
            },
            "unknown target_id",
        ),
        (
            {
                "action_type": "downlink",
                "satellite_id": "sat1",
                "station_id": "missing_station",
                "start": "2025-01-01T00:00:00Z",
                "end": "2025-01-01T00:00:10Z",
            },
            "unknown station_id",
        ),
    ],
)
def test_verify_rejects_unknown_references(
    tmp_path: Path, action: dict, expected_fragment: str
) -> None:
    case_dir = _write_case(tmp_path)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_overhead_satellite("2025-01-01T00:00:00Z")],
            actions=[action],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any(expected_fragment in error for error in result.errors)


def test_verify_rejects_unsupported_action_and_nonpositive_duration(tmp_path: Path) -> None:
    case_dir = _write_case(tmp_path)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_overhead_satellite("2025-01-01T00:00:00Z")],
            actions=[
                {
                    "action_type": "slew",
                    "satellite_id": "sat1",
                    "start": "2025-01-01T00:00:00Z",
                    "end": "2025-01-01T00:00:10Z",
                },
                {
                    "action_type": "observation",
                    "satellite_id": "sat1",
                    "target_id": "t1",
                    "start": "2025-01-01T00:01:00Z",
                    "end": "2025-01-01T00:01:00Z",
                },
            ],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("unsupported action_type" in error for error in result.errors)
    assert any("must satisfy end > start" in error for error in result.errors)


def test_verify_rejects_action_outside_horizon(tmp_path: Path) -> None:
    case_dir = _write_case(tmp_path)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_overhead_satellite("2025-01-01T00:00:00Z")],
            actions=[
                {
                    "action_type": "observation",
                    "satellite_id": "sat1",
                    "target_id": "t1",
                    "start": "2024-12-31T23:59:50Z",
                    "end": "2025-01-01T00:00:10Z",
                }
            ],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("lies outside the mission horizon" in error for error in result.errors)


def test_verify_rejects_observation_shorter_than_target_min_duration(tmp_path: Path) -> None:
    mission = _base_mission()
    mission["targets"][0]["min_duration_sec"] = 30.0
    case_dir = _write_case(tmp_path, mission=mission)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_overhead_satellite("2025-01-01T00:00:00Z")],
            actions=[
                {
                    "action_type": "observation",
                    "satellite_id": "sat1",
                    "target_id": "t1",
                    "start": "2025-01-01T00:00:00Z",
                    "end": "2025-01-01T00:00:10Z",
                }
            ],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("requires at least" in error for error in result.errors)


def test_verify_rejects_observation_when_sensor_range_too_small(tmp_path: Path) -> None:
    assets = _base_assets()
    assets["satellite_model"]["sensor"]["max_range_m"] = 1.0
    case_dir = _write_case(tmp_path, assets=assets)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_overhead_satellite("2025-01-01T00:00:00Z")],
            actions=[
                {
                    "action_type": "observation",
                    "satellite_id": "sat1",
                    "target_id": "t1",
                    "start": "2025-01-01T00:00:00Z",
                    "end": "2025-01-01T00:00:10Z",
                }
            ],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("exceeds sensor max range" in error for error in result.errors)


def test_verify_rejects_downlink_when_station_min_elevation_is_impossible(tmp_path: Path) -> None:
    assets = _base_assets()
    assets["ground_stations"][0]["min_elevation_deg"] = 90.1
    case_dir = _write_case(tmp_path, assets=assets)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_overhead_satellite("2025-01-01T00:00:00Z")],
            actions=[
                {
                    "action_type": "downlink",
                    "satellite_id": "sat1",
                    "station_id": "gs1",
                    "start": "2025-01-01T00:00:00Z",
                    "end": "2025-01-01T00:00:10Z",
                }
            ],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("below station minimum" in error for error in result.errors)


def test_verify_allows_parallel_downlinks_with_two_terminals(tmp_path: Path) -> None:
    assets = _base_assets()
    assets["satellite_model"]["terminals"] = [
        {
            "downlink_release_rate_mb_per_s": 1.0,
            "downlink_discharge_rate_w": 5.0,
        },
        {
            "downlink_release_rate_mb_per_s": 1.0,
            "downlink_discharge_rate_w": 5.0,
        },
    ]
    case_dir = _write_case(tmp_path, assets=assets)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_overhead_satellite("2025-01-01T00:00:00Z")],
            actions=[
                {
                    "action_type": "downlink",
                    "satellite_id": "sat1",
                    "station_id": "gs1",
                    "start": "2025-01-01T00:00:00Z",
                    "end": "2025-01-01T00:00:10Z",
                },
                {
                    "action_type": "downlink",
                    "satellite_id": "sat1",
                    "station_id": "gs1",
                    "start": "2025-01-01T00:00:00Z",
                    "end": "2025-01-01T00:00:10Z",
                },
            ],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert result.is_valid, result.errors


def test_verify_rejects_parallel_downlinks_above_terminal_count(tmp_path: Path) -> None:
    assets = _base_assets()
    assets["satellite_model"]["terminals"][0]["downlink_release_rate_mb_per_s"] = 0.1
    assets["satellite_model"]["resource_model"]["initial_storage_mb"] = 100.0
    case_dir = _write_case(tmp_path, assets=assets)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_overhead_satellite("2025-01-01T00:00:00Z")],
            actions=[
                {
                    "action_type": "downlink",
                    "satellite_id": "sat1",
                    "station_id": "gs1",
                    "start": "2025-01-01T00:00:00Z",
                    "end": "2025-01-01T00:00:10Z",
                },
                {
                    "action_type": "downlink",
                    "satellite_id": "sat1",
                    "station_id": "gs1",
                    "start": "2025-01-01T00:00:00Z",
                    "end": "2025-01-01T00:00:10Z",
                },
            ],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("simultaneous downlinks" in error for error in result.errors)


def test_verify_rejects_insufficient_maneuver_gap(tmp_path: Path) -> None:
    mission = _base_mission()
    mission["targets"].append(
        {
            "id": "t2",
            "name": "T2",
            "latitude_deg": 0.0,
            "longitude_deg": 90.0,
            "altitude_m": 0.0,
            "expected_revisit_period_hours": 0.5,
            "min_elevation_deg": -90.0,
            "max_slant_range_m": 1.0e9,
            "min_duration_sec": 1.0,
        }
    )
    assets = _base_assets()
    assets["satellite_model"]["attitude_model"]["max_slew_velocity_deg_per_sec"] = 0.01
    assets["satellite_model"]["attitude_model"]["max_slew_acceleration_deg_per_sec2"] = 0.01
    assets["satellite_model"]["attitude_model"]["settling_time_sec"] = 30.0
    case_dir = _write_case(tmp_path, assets=assets, mission=mission)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_overhead_satellite("2025-01-01T00:00:00Z")],
            actions=[
                {
                    "action_type": "observation",
                    "satellite_id": "sat1",
                    "target_id": "t1",
                    "start": "2025-01-01T00:00:00Z",
                    "end": "2025-01-01T00:00:10Z",
                },
                {
                    "action_type": "observation",
                    "satellite_id": "sat1",
                    "target_id": "t2",
                    "start": "2025-01-01T00:00:11Z",
                    "end": "2025-01-01T00:00:21Z",
                },
            ],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("needs" in error and "between observations" in error for error in result.errors)


def test_verify_rejects_battery_depletion(tmp_path: Path) -> None:
    assets = _base_assets()
    assets["satellite_model"]["resource_model"]["battery_capacity_wh"] = 10.0
    assets["satellite_model"]["resource_model"]["initial_battery_wh"] = 1.0
    assets["satellite_model"]["resource_model"]["idle_discharge_rate_w"] = 100.0
    case_dir = _write_case(tmp_path, assets=assets)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_sunlit_satellite("2025-01-01T00:00:00Z")],
            actions=[],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("depletes battery below zero" in error for error in result.errors)


def test_verify_accepts_case_when_sunlight_charge_avoids_depletion(tmp_path: Path) -> None:
    assets = _base_assets()
    assets["satellite_model"]["resource_model"]["battery_capacity_wh"] = 10.0
    assets["satellite_model"]["resource_model"]["initial_battery_wh"] = 1.0
    assets["satellite_model"]["resource_model"]["idle_discharge_rate_w"] = 100.0
    assets["satellite_model"]["resource_model"]["sunlight_charge_rate_w"] = 200.0
    mission = _base_mission(
        horizon_start="2025-01-01T00:00:00Z",
        horizon_end="2025-01-01T00:01:00Z",
    )
    case_dir = _write_case(tmp_path, assets=assets, mission=mission)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_sunlit_satellite("2025-01-01T00:00:00Z")],
            actions=[],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert result.is_valid, result.errors


def test_verify_rejects_storage_overflow_during_observation(tmp_path: Path) -> None:
    assets = _base_assets()
    assets["satellite_model"]["resource_model"]["storage_capacity_mb"] = 5.0
    assets["satellite_model"]["resource_model"]["initial_storage_mb"] = 0.0
    assets["satellite_model"]["sensor"]["obs_store_rate_mb_per_s"] = 10.0
    case_dir = _write_case(tmp_path, assets=assets)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_overhead_satellite("2025-01-01T00:00:00Z")],
            actions=[
                {
                    "action_type": "observation",
                    "satellite_id": "sat1",
                    "target_id": "t1",
                    "start": "2025-01-01T00:00:00Z",
                    "end": "2025-01-01T00:00:10Z",
                }
            ],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("exceeds storage capacity" in error for error in result.errors)


def test_verify_rejects_storage_underflow_during_downlink(tmp_path: Path) -> None:
    assets = _base_assets()
    assets["satellite_model"]["resource_model"]["initial_storage_mb"] = 0.0
    assets["satellite_model"]["terminals"][0]["downlink_release_rate_mb_per_s"] = 10.0
    case_dir = _write_case(tmp_path, assets=assets)
    solution_path = _write_solution(
        tmp_path,
        _solution_payload(
            satellites=[_overhead_satellite("2025-01-01T00:00:00Z")],
            actions=[
                {
                    "action_type": "downlink",
                    "satellite_id": "sat1",
                    "station_id": "gs1",
                    "start": "2025-01-01T00:00:00Z",
                    "end": "2025-01-01T00:00:10Z",
                }
            ],
        ),
    )

    result = verify_solution(case_dir, solution_path)

    assert not result.is_valid
    assert any("depletes storage below zero" in error for error in result.errors)


def test_compute_metrics_zero_observations() -> None:
    instance = load_case(FIXTURE_DIR)

    metrics = _compute_metrics(instance, [], satellite_count=1)

    assert metrics["mean_revisit_gap_hours"] == pytest.approx(1.0)
    assert metrics["max_revisit_gap_hours"] == pytest.approx(1.0)
    assert metrics["threshold_satisfied"] is False


def test_compute_metrics_one_observation_uses_midpoint_and_boundaries() -> None:
    instance = load_case(FIXTURE_DIR)
    start = instance.horizon_start + timedelta(minutes=10)
    end = instance.horizon_start + timedelta(minutes=20)
    midpoint = start + ((end - start) / 2)
    observations = [
        ObservationRecord(
            satellite_id="sat1",
            target_id="t1",
            start=start,
            end=end,
            midpoint=midpoint,
        )
    ]

    metrics = _compute_metrics(instance, observations, satellite_count=1)

    assert metrics["mean_revisit_gap_hours"] == pytest.approx(0.5)
    assert metrics["max_revisit_gap_hours"] == pytest.approx(0.75)
    assert metrics["threshold_satisfied"] is False


def test_compute_metrics_multiple_observations_reduce_max_gap() -> None:
    instance = load_case(FIXTURE_DIR)
    observations = [
        ObservationRecord(
            satellite_id="sat1",
            target_id="t1",
            start=instance.horizon_start + timedelta(minutes=10),
            end=instance.horizon_start + timedelta(minutes=20),
            midpoint=instance.horizon_start + timedelta(minutes=15),
        ),
        ObservationRecord(
            satellite_id="sat1",
            target_id="t1",
            start=instance.horizon_start + timedelta(minutes=40),
            end=instance.horizon_start + timedelta(minutes=50),
            midpoint=instance.horizon_start + timedelta(minutes=45),
        ),
    ]

    metrics = _compute_metrics(instance, observations, satellite_count=1)

    assert metrics["mean_revisit_gap_hours"] == pytest.approx(1.0 / 3.0)
    assert metrics["max_revisit_gap_hours"] == pytest.approx(0.5)
    assert metrics["threshold_satisfied"] is True


def test_compute_metrics_threshold_is_per_target_max_gap(tmp_path: Path) -> None:
    mission = _base_mission()
    mission["targets"].append(
        {
            "id": "t2",
            "name": "T2",
            "latitude_deg": 10.0,
            "longitude_deg": 20.0,
            "altitude_m": 0.0,
            "expected_revisit_period_hours": 0.25,
            "min_elevation_deg": -90.0,
            "max_slant_range_m": 1.0e9,
            "min_duration_sec": 1.0,
        }
    )
    case_dir = _write_case(tmp_path, mission=mission)
    instance = load_case(case_dir)
    observations = [
        ObservationRecord(
            satellite_id="sat1",
            target_id="t1",
            start=instance.horizon_start + timedelta(minutes=10),
            end=instance.horizon_start + timedelta(minutes=20),
            midpoint=instance.horizon_start + timedelta(minutes=15),
        )
    ]

    metrics = _compute_metrics(instance, observations, satellite_count=1)

    assert metrics["target_gap_summary"]["t1"]["max_revisit_gap_hours"] == pytest.approx(0.75)
    assert metrics["target_gap_summary"]["t2"]["max_revisit_gap_hours"] == pytest.approx(1.0)
    assert metrics["threshold_satisfied"] is False
