"""Focused helper regressions for the aeossp_standard visualizer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from benchmarks.aeossp_standard.verifier.engine import _action_sample_times
from benchmarks.aeossp_standard.verifier.models import Mission
from benchmarks.aeossp_standard.visualizer import geometry as viz_geometry
from benchmarks.aeossp_standard.visualizer.geometry import OrbitSampleGrid


def _utc_datetime(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int,
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def test_action_sample_times_uses_public_geometry_grid() -> None:
    mission = Mission(
        case_id="case_test",
        horizon_start=_utc_datetime(2025, 1, 1, 0, 0, 0),
        horizon_end=_utc_datetime(2025, 1, 1, 1, 0, 0),
        action_time_step_s=10,
        geometry_sample_step_s=15,
        resource_sample_step_s=30,
    )

    sample_times = _action_sample_times(
        mission,
        mission.horizon_start + timedelta(seconds=10),
        mission.horizon_start + timedelta(seconds=40),
    )

    assert sample_times == [
        mission.horizon_start + timedelta(seconds=10),
        mission.horizon_start + timedelta(seconds=15),
        mission.horizon_start + timedelta(seconds=30),
        mission.horizon_start + timedelta(seconds=40),
    ]


def test_visualizer_access_intervals_stop_at_last_checked_sample(monkeypatch) -> None:
    orbit_grid = OrbitSampleGrid(
        start_time=_utc_datetime(2025, 1, 1, 0, 0, 0),
        end_time=_utc_datetime(2025, 1, 1, 0, 2, 0),
        step_s=60,
        sample_times=(
            _utc_datetime(2025, 1, 1, 0, 0, 0),
            _utc_datetime(2025, 1, 1, 0, 1, 0),
            _utc_datetime(2025, 1, 1, 0, 2, 0),
        ),
        positions_ecef_m={"sat_001": np.zeros((3, 3), dtype=float)},
        longitudes_deg={},
        latitudes_deg={},
    )

    def _fake_access_mask_for_satellite(*args, **kwargs):
        return np.array([True, True, False], dtype=bool), np.array([5.0, 7.5, 90.0], dtype=float)

    monkeypatch.setattr(
        viz_geometry,
        "access_mask_for_satellite",
        _fake_access_mask_for_satellite,
    )

    intervals = viz_geometry.derive_task_access_intervals(
        {
            "task_id": "task_001",
            "required_duration_s": 60,
            "required_sensor_type": "visible",
        },
        [
            {
                "satellite_id": "sat_001",
                "sensor": {"sensor_type": "visible"},
                "attitude_model": {"max_off_nadir_deg": 30.0},
            }
        ],
        orbit_grid,
    )

    assert len(intervals) == 1
    assert intervals[0].start_time == _utc_datetime(2025, 1, 1, 0, 0, 0)
    assert intervals[0].end_time == _utc_datetime(2025, 1, 1, 0, 1, 0)
    assert intervals[0].duration_s == 60


def test_visualizer_access_mask_uses_nan_for_inaccessible_off_nadir() -> None:
    mask, off_nadir_deg = viz_geometry.access_mask_for_satellite(
        {
            "required_sensor_type": "infrared",
            "latitude_deg": 0.0,
            "longitude_deg": 0.0,
            "altitude_m": 0.0,
        },
        {
            "satellite_id": "sat_001",
            "sensor": {"sensor_type": "visible"},
            "attitude_model": {"max_off_nadir_deg": 30.0},
        },
        np.zeros((3, 3), dtype=float),
    )

    assert not np.any(mask)
    assert np.all(np.isnan(off_nadir_deg))
