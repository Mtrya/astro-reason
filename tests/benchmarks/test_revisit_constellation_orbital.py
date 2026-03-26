"""Orbital regression tests for the revisit_constellation verifier."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import brahe
import numpy as np
import pytest
import yaml

from benchmarks.revisit_constellation.verifier import load_case, load_solution
from benchmarks.revisit_constellation.verifier.engine import (
    _build_propagators,
    _datetime_to_epoch,
    _ensure_brahe_ready,
    _is_sunlit,
    _observation_geometry_ok,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SGP4_SKYFIELD_DIR = REPO_ROOT / "tests" / "fixtures" / "sgp4_skyfield"
NO_SLANT_RANGE_LIMIT_M = 1.0e12


def _parse_iso8601_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError(f"{path} must contain a top-level YAML list")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _fixture_case_dir(case_id: str) -> Path:
    return SGP4_SKYFIELD_DIR / case_id


def _build_assets_payload(satellite_count: int) -> dict[str, Any]:
    return {
        "satellite_model": {
            "model_name": "sgp4_fixture_adapter",
            "sensor": {
                "field_of_view_half_angle_deg": 180.0,
                "max_range_m": NO_SLANT_RANGE_LIMIT_M,
                "obs_discharge_rate_w": 1.0,
                "obs_store_rate_mb_per_s": 0.0,
            },
            "terminals": [
                {
                    "downlink_release_rate_mb_per_s": 1.0,
                    "downlink_discharge_rate_w": 1.0,
                }
            ],
            "resource_model": {
                "battery_capacity_wh": 1.0e9,
                "storage_capacity_mb": 1.0e9,
                "initial_battery_wh": 1.0e9,
                "initial_storage_mb": 0.0,
                "idle_discharge_rate_w": 0.0,
                "sunlight_charge_rate_w": 0.0,
            },
            "attitude_model": {
                "max_slew_velocity_deg_per_sec": 180.0,
                "max_slew_acceleration_deg_per_sec2": 180.0,
                "settling_time_sec": 0.0,
                "maneuver_discharge_rate_w": 0.0,
            },
            "min_altitude_m": 100000.0,
            "max_altitude_m": 50000000.0,
        },
        "max_num_satellites": satellite_count,
        "ground_stations": [],
    }


def _build_mission_payload(
    metadata: dict[str, Any],
    target_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "horizon_start": metadata["horizon_start_utc"],
        "horizon_end": metadata["horizon_end_utc"],
        "targets": [
            {
                "id": target["id"],
                "name": target["id"],
                "latitude_deg": float(target["latitude_deg"]),
                "longitude_deg": float(target["longitude_deg"]),
                "altitude_m": float(target["altitude_m"]),
                "expected_revisit_period_hours": 24.0,
                "min_elevation_deg": float(target["min_elevation_deg"]),
                "max_slant_range_m": (
                    NO_SLANT_RANGE_LIMIT_M
                    if target["max_slant_range_m"] is None
                    else float(target["max_slant_range_m"])
                ),
                "min_duration_sec": 1.0,
            }
            for target in target_payloads
        ],
    }


def _build_solution_payload(orbital_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "satellites": [
            {
                "satellite_id": satellite["id"],
                "x_m": float(satellite["position_gcrs_m"][0][0]),
                "y_m": float(satellite["position_gcrs_m"][0][1]),
                "z_m": float(satellite["position_gcrs_m"][0][2]),
                "vx_m_s": float(satellite["velocity_gcrs_m_per_s"][0][0]),
                "vy_m_s": float(satellite["velocity_gcrs_m_per_s"][0][1]),
                "vz_m_s": float(satellite["velocity_gcrs_m_per_s"][0][2]),
            }
            for satellite in orbital_payload["satellites"]
        ],
        "actions": [],
    }


def _load_fixture_case(
    tmp_path: Path, case_id: str
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    fixture_dir = _fixture_case_dir(case_id)
    orbital_payload = _read_json(fixture_dir / "orbital_states.json")
    visibility_payload = _read_json(fixture_dir / "visibility_windows.json")
    illumination_payload = _read_json(fixture_dir / "illumination_windows.json")
    target_payloads = _read_yaml(fixture_dir / "targets.yaml")

    case_dir = tmp_path / case_id
    case_dir.mkdir()
    _write_json(
        case_dir / "assets.json",
        _build_assets_payload(len(orbital_payload["satellites"])),
    )
    _write_json(
        case_dir / "mission.json",
        _build_mission_payload(orbital_payload["metadata"], target_payloads),
    )
    _write_json(
        case_dir / "solution.json",
        _build_solution_payload(orbital_payload),
    )

    return case_dir, orbital_payload, visibility_payload, illumination_payload


def _load_runtime_case(
    tmp_path: Path, case_id: str
) -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    case_dir, orbital_payload, visibility_payload, illumination_payload = _load_fixture_case(
        tmp_path, case_id
    )
    _ensure_brahe_ready()
    instance = load_case(case_dir)
    solution = load_solution(case_dir / "solution.json")
    propagators = _build_propagators(instance, solution)
    return instance, propagators, orbital_payload, visibility_payload, illumination_payload


def _parse_windows(windows: list[dict[str, Any]]) -> list[tuple[datetime, datetime]]:
    return [
        (_parse_iso8601_utc(window["start_utc"]), _parse_iso8601_utc(window["end_utc"]))
        for window in windows
    ]


def _satellite_orbital_payload(
    orbital_payload: dict[str, Any], satellite_id: str
) -> dict[str, Any]:
    return next(
        satellite
        for satellite in orbital_payload["satellites"]
        if satellite["id"] == satellite_id
    )


def _sample_state_eci(
    orbital_payload: dict[str, Any],
    satellite_id: str,
    sample_index: int,
) -> np.ndarray:
    satellite = _satellite_orbital_payload(orbital_payload, satellite_id)
    return np.asarray(
        satellite["position_gcrs_m"][sample_index]
        + satellite["velocity_gcrs_m_per_s"][sample_index],
        dtype=float,
    )


def _timestamp_in_windows(instant: datetime, windows: list[tuple[datetime, datetime]]) -> bool:
    return any(start <= instant < end for start, end in windows)


@pytest.mark.parametrize(
    ("case_id", "satellite_id", "max_position_error_m", "max_velocity_error_m_per_s"),
    [
        ("case_0001", "sat_yaogan-16_01a", 24000.0, 24.0),
        ("case_0002", "sat_spot_1", 35000.0, 35.0),
        ("case_0002", "sat_skysat-a", 9000.0, 9.0),
        ("case_0002", "sat_qianfan-1", 2000.0, 1.0),
    ],
)
def test_build_propagators_match_sgp4_fixture_within_j2_drift_bounds(
    tmp_path: Path,
    case_id: str,
    satellite_id: str,
    max_position_error_m: float,
    max_velocity_error_m_per_s: float,
) -> None:
    instance, propagators, orbital_payload, _, _ = _load_runtime_case(tmp_path, case_id)
    assert orbital_payload["metadata"]["state_frame"] == "GCRS"
    assert instance.horizon_start == _parse_iso8601_utc(orbital_payload["metadata"]["horizon_start_utc"])
    assert instance.horizon_end == _parse_iso8601_utc(orbital_payload["metadata"]["horizon_end_utc"])

    timestamps = [_parse_iso8601_utc(value) for value in orbital_payload["timestamps_utc"]]
    satellite = _satellite_orbital_payload(orbital_payload, satellite_id)

    position_errors_m: list[float] = []
    velocity_errors_m_per_s: list[float] = []
    for timestamp, reference_position_m, reference_velocity_m_per_s in zip(
        timestamps,
        satellite["position_gcrs_m"],
        satellite["velocity_gcrs_m_per_s"],
    ):
        epoch = _datetime_to_epoch(timestamp)
        propagated_state = np.asarray(
            propagators[satellite_id].state_eci(epoch),
            dtype=float,
        )
        position_errors_m.append(
            float(
                np.linalg.norm(
                    propagated_state[:3] - np.asarray(reference_position_m, dtype=float)
                )
            )
        )
        velocity_errors_m_per_s.append(
            float(
                np.linalg.norm(
                    propagated_state[3:] - np.asarray(reference_velocity_m_per_s, dtype=float)
                )
            )
        )

    assert position_errors_m[0] == pytest.approx(0.0, abs=1e-6)
    assert velocity_errors_m_per_s[0] == pytest.approx(0.0, abs=1e-9)
    assert max(position_errors_m) <= max_position_error_m
    assert max(velocity_errors_m_per_s) <= max_velocity_error_m_per_s


def test_observation_geometry_matches_visibility_fixture_midpoints(tmp_path: Path) -> None:
    case_dir, orbital_payload, visibility_payload, _ = _load_fixture_case(tmp_path, "case_0002")
    _ensure_brahe_ready()
    instance = load_case(case_dir)
    timestamps = [_parse_iso8601_utc(value) for value in orbital_payload["timestamps_utc"]]

    for row in visibility_payload["satellite_to_target"]:
        satellite_id = row["satellite_id"]
        target = instance.targets[row["target_id"]]
        windows = _parse_windows(row["windows"])

        for sample_index, timestamp in enumerate(timestamps):
            expected_visible = _timestamp_in_windows(timestamp, windows)
            epoch = _datetime_to_epoch(timestamp)
            state_eci = _sample_state_eci(orbital_payload, satellite_id, sample_index)
            state_ecef = np.asarray(
                brahe.state_eci_to_ecef(epoch, state_eci),
                dtype=float,
            )
            ok, _ = _observation_geometry_ok(
                instance, target, state_eci, state_ecef, epoch
            )
            assert ok is expected_visible, (
                f"Visibility classification mismatch at {timestamp.isoformat()} for "
                f"{satellite_id}/{target.target_id}: expected {expected_visible}, got {ok}"
            )


def test_sunlight_classification_matches_illumination_fixture_midpoints(
    tmp_path: Path,
) -> None:
    _, orbital_payload, _, illumination_payload = _load_fixture_case(tmp_path, "case_0002")
    _ensure_brahe_ready()
    timestamps = [_parse_iso8601_utc(value) for value in orbital_payload["timestamps_utc"]]

    for satellite_payload in illumination_payload["satellites"]:
        satellite_id = satellite_payload["satellite_id"]
        sunlit_windows = _parse_windows(satellite_payload["sunlit_windows"])

        for sample_index, timestamp in enumerate(timestamps):
            expected_sunlit = (
                satellite_payload["final_state"] == "sunlit"
                if timestamp == timestamps[-1]
                else _timestamp_in_windows(timestamp, sunlit_windows)
            )
            epoch = _datetime_to_epoch(timestamp)
            state_eci = _sample_state_eci(orbital_payload, satellite_id, sample_index)
            assert _is_sunlit(state_eci[:3], epoch) is expected_sunlit, (
                f"Illumination classification mismatch at {timestamp.isoformat()} for "
                f"{satellite_id}: expected {expected_sunlit}"
            )
