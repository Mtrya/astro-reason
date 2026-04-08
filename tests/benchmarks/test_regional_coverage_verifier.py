"""Focused tests for the regional_coverage verifier."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import math

import brahe
import numpy as np
import pytest
import yaml

from benchmarks.regional_coverage.verifier import (
    Satellite,
    Sensor,
    Agility,
    Power,
    _datetime_to_epoch,
    _ecef_to_lonlat_deg,
    _ground_intercept_ecef_m,
    _ray_ellipsoid_intersection_m,
    _slew_time_s,
    verify_solution,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "benchmarks" / "regional_coverage" / "dataset"
CASE_0001_DIR = DATASET_DIR / "cases" / "case_0001"
EXAMPLE_SOLUTION_PATH = DATASET_DIR / "example_solution.json"

_TLE_LINE1 = "1 63255U 25052AX  25198.17518200  .00001597  00000-0  15702-3 0  9994"
_TLE_LINE2 = "2 63255  97.7253  91.1881 0000724 209.0702 151.0478 14.93504225 18614"
_HORIZON_START = "2025-07-17T04:10:00Z"
_HORIZON_END = "2025-07-17T04:20:00Z"
_VALID_START = "2025-07-17T04:12:20Z"
_VALID_DURATION_S = 20
_VALID_ROLL_DEG = 20.0


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_yaml(path: Path, payload: object) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _default_satellite(
    *,
    power_overrides: dict[str, float | None] | None = None,
    agility_overrides: dict[str, float] | None = None,
    sensor_overrides: dict[str, float] | None = None,
) -> dict:
    sensor = {
        "min_edge_off_nadir_deg": 18.0,
        "max_edge_off_nadir_deg": 34.0,
        "cross_track_fov_deg": 2.8,
        "min_strip_duration_s": 20.0,
        "max_strip_duration_s": 120.0,
    }
    agility = {
        "max_roll_rate_deg_per_s": 1.2,
        "max_roll_acceleration_deg_per_s2": 0.4,
        "settling_time_s": 2.0,
    }
    power = {
        "battery_capacity_wh": 900.0,
        "initial_battery_wh": 540.0,
        "idle_power_w": 85.0,
        "imaging_power_w": 290.0,
        "slew_power_w": 35.0,
        "sunlit_charge_power_w": 170.0,
        "imaging_duty_limit_s_per_orbit": 900.0,
    }
    if sensor_overrides:
        sensor.update(sensor_overrides)
    if agility_overrides:
        agility.update(agility_overrides)
    if power_overrides:
        power.update(power_overrides)
    return {
        "satellite_id": "sat_test",
        "tle_line1": _TLE_LINE1,
        "tle_line2": _TLE_LINE2,
        "tle_epoch": "2025-07-17T04:12:15.724Z",
        "sensor": sensor,
        "agility": agility,
        "power": power,
    }


def _default_manifest() -> dict:
    return {
        "benchmark": "regional_coverage",
        "case_id": "case_test",
        "coverage_sample_step_s": 5,
        "earth_model": {"shape": "wgs84"},
        "grid_parameters": {"sample_spacing_m": 5000.0},
        "horizon_end": _HORIZON_END,
        "horizon_start": _HORIZON_START,
        "scoring": {
            "max_actions_total": 64,
            "primary_metric": "coverage_ratio",
            "revisit_bonus_alpha": 0.0,
        },
        "seed": 20260408,
        "spec_version": "v1",
        "time_step_s": 10,
    }


def _default_action(
    *,
    start_time: str = _VALID_START,
    duration_s: float = _VALID_DURATION_S,
    roll_deg: float = _VALID_ROLL_DEG,
    satellite_id: str = "sat_test",
) -> dict:
    return {
        "type": "strip_observation",
        "satellite_id": satellite_id,
        "start_time": start_time,
        "duration_s": duration_s,
        "roll_deg": roll_deg,
    }


def _intercept_lonlat(start_time: str, duration_s: float, roll_deg: float) -> tuple[float, float]:
    propagator = brahe.SGPPropagator.from_tle(_TLE_LINE1, _TLE_LINE2, 5.0)
    start = _parse_iso(start_time)
    midpoint = start + timedelta(seconds=duration_s / 2.0)
    epoch = _datetime_to_epoch(midpoint)
    state_ecef = np.asarray(propagator.state_ecef(epoch), dtype=float).reshape(6)
    hit = _ground_intercept_ecef_m(state_ecef[:3], state_ecef[3:], roll_deg)
    assert hit is not None
    return _ecef_to_lonlat_deg(hit)


def _square_region(lon_deg: float, lat_deg: float, half_span_deg: float = 0.25) -> list[list[float]]:
    return [
        [lon_deg - half_span_deg, lat_deg - half_span_deg],
        [lon_deg + half_span_deg, lat_deg - half_span_deg],
        [lon_deg + half_span_deg, lat_deg + half_span_deg],
        [lon_deg - half_span_deg, lat_deg + half_span_deg],
        [lon_deg - half_span_deg, lat_deg - half_span_deg],
    ]


def _write_case(
    tmp_path: Path,
    *,
    power_overrides: dict[str, float | None] | None = None,
    agility_overrides: dict[str, float] | None = None,
    sensor_overrides: dict[str, float] | None = None,
    action_for_targeting: dict | None = None,
) -> Path:
    case_dir = tmp_path / "case"
    case_dir.mkdir()

    targeting_action = action_for_targeting or _default_action()
    lon_deg, lat_deg = _intercept_lonlat(
        targeting_action["start_time"],
        float(targeting_action["duration_s"]),
        float(targeting_action["roll_deg"]),
    )
    manifest = _default_manifest()
    satellite = _default_satellite(
        power_overrides=power_overrides,
        agility_overrides=agility_overrides,
        sensor_overrides=sensor_overrides,
    )
    region_polygon = _square_region(lon_deg, lat_deg)
    regions_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "region_id": "region_001",
                    "weight": 1.0,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [region_polygon],
                },
            }
        ],
    }
    coverage_grid = {
        "grid_version": 1,
        "sample_spacing_m": 5000.0,
        "regions": [
            {
                "region_id": "region_001",
                "total_weight_m2": 25_000_000.0,
                "samples": [
                    {
                        "sample_id": "region_001_s000001",
                        "longitude_deg": lon_deg,
                        "latitude_deg": lat_deg,
                        "weight_m2": 25_000_000.0,
                    }
                ],
            }
        ],
    }

    _write_json(case_dir / "manifest.json", manifest)
    _write_yaml(case_dir / "satellites.yaml", [satellite])
    _write_json(case_dir / "regions.geojson", regions_geojson)
    _write_json(case_dir / "coverage_grid.json", coverage_grid)
    return case_dir


def _write_solution(tmp_path: Path, actions: list[dict]) -> Path:
    path = tmp_path / "solution.json"
    _write_json(path, {"actions": actions})
    return path


class TestHelperGeometry:
    def test_ray_ellipsoid_intersection_hits_surface(self):
        origin = np.array([7_000_000.0, 0.0, 0.0])
        direction = np.array([-1.0, 0.0, 0.0])
        distance = _ray_ellipsoid_intersection_m(origin, direction)
        assert distance is not None
        assert distance == pytest.approx(7_000_000.0 - 6_378_137.0, rel=1.0e-6)

    def test_slew_time_matches_trapezoidal_model(self):
        satellite = Satellite(
            satellite_id="sat_test",
            tle_line1=_TLE_LINE1,
            tle_line2=_TLE_LINE2,
            tle_epoch="2025-07-17T04:12:15.724Z",
            sensor=Sensor(18.0, 34.0, 2.8, 20.0, 120.0),
            agility=Agility(1.2, 0.4, 2.0),
            power=Power(900.0, 540.0, 85.0, 290.0, 35.0, 170.0, 900.0),
        )
        triangular = _slew_time_s(1.0, satellite)
        trapezoidal = _slew_time_s(40.0, satellite)
        assert triangular == pytest.approx(2.0 * math.sqrt(1.0 / 0.4), rel=1.0e-6)
        assert trapezoidal == pytest.approx((40.0 / 1.2) + (1.2 / 0.4), rel=1.0e-6)


def test_verify_solution_smoke_on_canonical_example():
    report = verify_solution(CASE_0001_DIR, EXAMPLE_SOLUTION_PATH)
    assert report["valid"] is True
    assert report["metrics"]["coverage_ratio"] == 0.0
    assert report["metrics"]["num_actions"] == 0


def test_start_time_must_align_to_time_grid(tmp_path: Path):
    case_dir = _write_case(tmp_path)
    solution_path = _write_solution(
        tmp_path,
        [_default_action(start_time="2025-07-17T04:12:21Z")],
    )
    report = verify_solution(case_dir, solution_path)
    assert report["valid"] is False
    assert any("start_time must align" in violation for violation in report["violations"])


def test_same_satellite_overlap_rejected(tmp_path: Path):
    case_dir = _write_case(tmp_path)
    solution_path = _write_solution(
        tmp_path,
        [
            _default_action(start_time="2025-07-17T04:12:20Z", duration_s=20),
            _default_action(start_time="2025-07-17T04:12:30Z", duration_s=20),
        ],
    )
    report = verify_solution(case_dir, solution_path)
    assert report["valid"] is False
    assert any("overlapping strip observations" in violation for violation in report["violations"])


def test_slew_gap_rejected(tmp_path: Path):
    case_dir = _write_case(tmp_path)
    solution_path = _write_solution(
        tmp_path,
        [
            _default_action(start_time="2025-07-17T04:12:20Z", duration_s=20, roll_deg=20.0),
            _default_action(start_time="2025-07-17T04:12:50Z", duration_s=20, roll_deg=-20.0),
        ],
    )
    report = verify_solution(case_dir, solution_path)
    assert report["valid"] is False
    assert any("insufficient slew/settle time" in violation for violation in report["violations"])


def test_valid_single_strip_covers_expected_weight(tmp_path: Path):
    action = _default_action()
    case_dir = _write_case(tmp_path, action_for_targeting=action)
    solution_path = _write_solution(tmp_path, [action])
    report = verify_solution(case_dir, solution_path)
    assert report["valid"] is True
    assert report["metrics"]["coverage_ratio"] == pytest.approx(1.0)
    assert report["metrics"]["covered_weight_m2_equivalent"] == pytest.approx(25_000_000.0)
    assert report["metrics"]["region_coverages"]["region_001"]["coverage_ratio"] == pytest.approx(1.0)


def test_battery_depletion_invalid(tmp_path: Path):
    action = _default_action(duration_s=120)
    case_dir = _write_case(
        tmp_path,
        power_overrides={
            "battery_capacity_wh": 2.0,
            "initial_battery_wh": 0.2,
            "idle_power_w": 0.0,
            "imaging_power_w": 720.0,
            "slew_power_w": 0.0,
            "sunlit_charge_power_w": 0.0,
            "imaging_duty_limit_s_per_orbit": None,
        },
        action_for_targeting=action,
    )
    solution_path = _write_solution(tmp_path, [action])
    report = verify_solution(case_dir, solution_path)
    assert report["valid"] is False
    assert any("battery depletes below zero" in violation for violation in report["violations"])
