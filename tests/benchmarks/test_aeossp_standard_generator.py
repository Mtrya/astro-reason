"""Focused regressions for the aeossp_standard generator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import random

import numpy as np

from benchmarks.aeossp_standard.generator import build as gen_build
from benchmarks.aeossp_standard.generator import cached_tles, sources
from benchmarks.aeossp_standard.generator import geometry as gen_geometry
from benchmarks.aeossp_standard.generator.geometry import AccessInterval, OrbitSampleGrid
from benchmarks.aeossp_standard.generator.normalize import CityRecord


def _utc_datetime(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int,
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def _test_orbit_grid() -> OrbitSampleGrid:
    return OrbitSampleGrid(
        start_time=_utc_datetime(2025, 1, 1, 0, 0, 0),
        end_time=_utc_datetime(2025, 1, 1, 0, 2, 0),
        step_s=60,
        sample_times=(
            _utc_datetime(2025, 1, 1, 0, 0, 0),
            _utc_datetime(2025, 1, 1, 0, 1, 0),
            _utc_datetime(2025, 1, 1, 0, 2, 0),
        ),
        positions_ecef_m={"sat_001": np.zeros((3, 3), dtype=float)},
    )


def test_generator_access_intervals_require_nonzero_duration(monkeypatch) -> None:
    def _fake_access_mask_for_satellite(*args, **kwargs):
        return np.array([True, False, False], dtype=bool), np.array([5.0, 90.0, 90.0], dtype=float)

    monkeypatch.setattr(
        gen_geometry,
        "access_mask_for_satellite",
        _fake_access_mask_for_satellite,
    )

    intervals = gen_geometry.derive_task_access_intervals(
        {
            "task_id": "task_001",
            "required_duration_s": 1,
            "required_sensor_type": "visible",
        },
        [
            {
                "satellite_id": "sat_001",
                "sensor": {"sensor_type": "visible"},
                "attitude_model": {"max_off_nadir_deg": 30.0},
            }
        ],
        _test_orbit_grid(),
    )

    assert intervals == []


def test_generator_access_intervals_handle_trailing_runs(monkeypatch) -> None:
    def _fake_access_mask_for_satellite(*args, **kwargs):
        return np.array([False, True, True], dtype=bool), np.array([90.0, 7.5, 5.0], dtype=float)

    monkeypatch.setattr(
        gen_geometry,
        "access_mask_for_satellite",
        _fake_access_mask_for_satellite,
    )

    intervals = gen_geometry.derive_task_access_intervals(
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
        _test_orbit_grid(),
    )

    assert len(intervals) == 1
    assert intervals[0].start_time == _utc_datetime(2025, 1, 1, 0, 1, 0)
    assert intervals[0].end_time == _utc_datetime(2025, 1, 1, 0, 2, 0)
    assert intervals[0].duration_s == 60


def test_reachable_city_candidates_filter_unreachable_rows(monkeypatch) -> None:
    cities = [
        CityRecord("north", "AA", 10.0, 20.0, 1_000_000),
        CityRecord("south", "BB", -10.0, 30.0, 500_000),
    ]

    def _fake_derive(task_like, *args, **kwargs):
        if task_like["latitude_deg"] > 0:
            return [object()]
        return []

    monkeypatch.setattr(gen_build, "derive_task_access_intervals", _fake_derive)

    reachable = gen_build._reachable_city_candidates(
        cities,
        satellites=[],
        orbit_grid=object(),
        sensor_type="infrared",
        compatible_satellite_ids={"sat_001"},
    )

    assert reachable == [cities[0]]


def test_build_task_entries_uses_adaptive_retry_budget(monkeypatch) -> None:
    rng = random.Random(0)
    city = CityRecord("reachable", "AA", 10.0, 20.0, 1_000_000)
    horizon_start = _utc_datetime(2025, 1, 1, 0, 0, 0)
    horizon_end = horizon_start + timedelta(hours=12)
    interval = AccessInterval(
        satellite_id="sat_ir_1",
        start_index=0,
        end_index=1,
        start_time=horizon_start,
        end_time=horizon_start + timedelta(seconds=30),
        duration_s=30,
        midpoint_time=horizon_start + timedelta(seconds=15),
        min_off_nadir_deg=5.0,
        max_off_nadir_deg=7.5,
    )
    sample_round = {"count": 0}
    access_calls = {"count": 0}

    monkeypatch.setattr(gen_build, "_sample_hotspot_offsets", lambda rng, horizon_s: [0, 3600, 7200, 10800])
    monkeypatch.setattr(gen_build, "sample_orbit_grid", lambda *args, **kwargs: object())
    monkeypatch.setattr(gen_build, "_group_task_counts", lambda task_count: {("city", "infrared"): 1})
    monkeypatch.setattr(gen_build, "_reachable_city_candidates", lambda *args, **kwargs: [city])

    def _fake_sample_candidate_seeds(*args, **kwargs):
        sample_round["count"] += 1
        return [
            gen_build.TaskSeed(
                name=f"candidate_{sample_round['count']}",
                latitude_deg=city.latitude_deg,
                longitude_deg=city.longitude_deg + sample_round["count"],
                altitude_m=0.0,
                source_kind="city",
            )
        ]

    def _fake_derive(*args, **kwargs):
        access_calls["count"] += 1
        if access_calls["count"] <= 12:
            return []
        return [interval]

    monkeypatch.setattr(gen_build, "_sample_candidate_seeds", _fake_sample_candidate_seeds)
    monkeypatch.setattr(gen_build, "derive_task_access_intervals", _fake_derive)
    monkeypatch.setattr(gen_build, "_choose_access_interval", lambda *args, **kwargs: (interval, False))
    monkeypatch.setattr(
        gen_build,
        "_window_around_access",
        lambda *args, **kwargs: (horizon_start, horizon_start + timedelta(seconds=30)),
    )

    tasks = gen_build._build_task_entries(
        rng,
        cities=[city],
        land_geometry=None,
        satellites=[
            {
                "satellite_id": "sat_ir_1",
                "sensor": {"sensor_type": "infrared"},
                "attitude_model": {"max_off_nadir_deg": 20.0},
            }
        ],
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        task_count=1,
    )

    assert len(tasks) == 1
    assert access_calls["count"] == 13
    assert sample_round["count"] == 13


def test_download_celestrak_uses_vendored_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        sources.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network should not be used")),
    )

    result = sources.download_celestrak(tmp_path, force_download=True)
    csv_path = tmp_path / "celestrak" / "earth_resources.csv"
    raw_path = tmp_path / "celestrak" / "earth_resources_raw.tle"

    assert result.extra["vendored_snapshot"] is True
    assert result.extra["record_count"] == len(cached_tles.CACHED_CELESTRAK_ROWS)
    assert csv_path.is_file()
    assert raw_path.is_file()
    assert csv_path.read_text(encoding="utf-8").startswith(
        "name,norad_catalog_id,tle_line1,tle_line2,epoch_iso,inclination_deg,"
    )
