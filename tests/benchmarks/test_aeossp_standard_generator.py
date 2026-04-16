"""Focused regressions for the aeossp_standard generator."""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
import json
import random
from pathlib import Path
import sys

import numpy as np
import pytest
import yaml

from benchmarks.aeossp_standard.generator import build as gen_build
from benchmarks.aeossp_standard.generator import cached_tles, sources
from benchmarks.aeossp_standard.generator import geometry as gen_geometry
import benchmarks.aeossp_standard.generator.run as generator_run
from benchmarks.aeossp_standard.generator.geometry import AccessInterval, OrbitSampleGrid
from benchmarks.aeossp_standard.generator.normalize import CityRecord
from benchmarks.aeossp_standard.generator.build import load_generator_config
from benchmarks.aeossp_standard.generator.sources import (
    CELESTRAK_CSV_NAME,
    CELESTRAK_EARTH_RESOURCES_URL,
    CELESTRAK_SNAPSHOT_EPOCH_UTC,
    NATURAL_EARTH_LAND_FILENAME,
    NATURAL_EARTH_LAND_URL,
    WORLD_CITIES_FILENAME,
    WORLD_CITIES_URL,
    SourceFetchResult,
)


def _write_splits_yaml(
    path: Path,
    *,
    snapshot_epoch_utc: str = CELESTRAK_SNAPSHOT_EPOCH_UTC,
) -> None:
    payload = {
        "example_smoke_case": "test/case_0001",
        "source": {
            "celestrak": {
                "kind": "vendored_subset",
                "url": CELESTRAK_EARTH_RESOURCES_URL,
                "snapshot_epoch_utc": snapshot_epoch_utc,
            },
            "world_cities": {
                "kind": "geonames_dump",
                "url": WORLD_CITIES_URL,
            },
            "natural_earth_land": {
                "kind": "natural_earth_geojson",
                "url": NATURAL_EARTH_LAND_URL,
            },
        },
        "splits": {
            "test": {
                "seed": 42,
                "case_count": 1,
                "case_seed_stride": 1009,
                "mission": {
                    "case_start_spacing_hours": 2,
                    "horizon_hours": 12,
                    "action_time_step_s": 5,
                    "geometry_sample_step_s": 5,
                    "resource_sample_step_s": 10,
                    "task_access_sample_step_s": 30,
                },
                "satellite_pool": {
                    "min_altitude_m": 450000.0,
                    "max_altitude_m": 900000.0,
                    "min_retained_count": 1,
                    "include_name_tokens": ["LANDSAT", "SENTINEL-2", "SPOT", "PLEIADES"],
                    "exclude_name_tokens": ["SAR", "ICEYE"],
                },
                "satellites": {
                    "min_per_case": 2,
                    "max_per_case": 2,
                    "template_fractions": {
                        "infrared_balanced": 0.0,
                        "visible_agile": 0.0,
                        "visible_balanced": 1.0,
                    },
                    "templates": {
                        "visible_agile": {
                            "sensor_type": "visible",
                            "max_off_nadir_deg": 30.0,
                            "max_slew_velocity_deg_per_s": 1.8,
                            "max_slew_acceleration_deg_per_s2": 0.4,
                            "settling_time_s": 2.0,
                            "battery_capacity_wh": 1300.0,
                            "initial_battery_wh": 800.0,
                            "idle_power_w": 20.0,
                            "imaging_power_w": 420.0,
                            "slew_power_w": 360.0,
                            "sunlit_charge_power_w": 85.0,
                        },
                        "visible_balanced": {
                            "sensor_type": "visible",
                            "max_off_nadir_deg": 25.0,
                            "max_slew_velocity_deg_per_s": 1.0,
                            "max_slew_acceleration_deg_per_s2": 0.25,
                            "settling_time_s": 3.0,
                            "battery_capacity_wh": 1600.0,
                            "initial_battery_wh": 1000.0,
                            "idle_power_w": 25.0,
                            "imaging_power_w": 480.0,
                            "slew_power_w": 280.0,
                            "sunlit_charge_power_w": 100.0,
                        },
                        "infrared_balanced": {
                            "sensor_type": "infrared",
                            "max_off_nadir_deg": 20.0,
                            "max_slew_velocity_deg_per_s": 0.9,
                            "max_slew_acceleration_deg_per_s2": 0.15,
                            "settling_time_s": 3.5,
                            "battery_capacity_wh": 1800.0,
                            "initial_battery_wh": 1000.0,
                            "idle_power_w": 30.0,
                            "imaging_power_w": 680.0,
                            "slew_power_w": 320.0,
                            "sunlit_charge_power_w": 115.0,
                        },
                    },
                },
                "tasks": {
                    "min_per_case": 4,
                    "max_per_case": 4,
                    "min_target_separation_m": 25000.0,
                    "city_fraction": 1.0,
                    "visible_fraction": 1.0,
                    "city_weight_options": [3.0],
                    "background_weight_options": [1.0],
                    "duration_options_s": [15, 20],
                    "hotspot_probability": 0.7,
                    "hotspot_count": 2,
                    "hotspot_min_spacing_s": 600,
                    "hotspot_window_slack_options_s": [300],
                    "uniform_window_slack_options_s": [900],
                },
            }
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_source_tree(source_dir: Path) -> None:
    celestrak_dir = source_dir / "celestrak"
    celestrak_dir.mkdir(parents=True, exist_ok=True)
    with (celestrak_dir / CELESTRAK_CSV_NAME).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "name",
                "norad_catalog_id",
                "tle_line1",
                "tle_line2",
                "epoch_iso",
                "inclination_deg",
                "eccentricity",
                "mean_motion_rev_per_day",
                "altitude_m",
            ],
        )
        writer.writeheader()
        writer.writerows(cached_tles.CACHED_CELESTRAK_ROWS)
    cities_dir = source_dir / "world_cities"
    cities_dir.mkdir(parents=True, exist_ok=True)
    (cities_dir / WORLD_CITIES_FILENAME).write_text(
        "\n".join(
            [
                "name,country,latitude_deg,longitude_deg,population",
                "Paris,FR,48.8566,2.3522,2161000",
                "Tokyo,JP,35.6762,139.6503,13960000",
                "Sydney,AU,-33.8688,151.2093,5312000",
                "Nairobi,KE,-1.2864,36.8172,4397000",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    natural_earth_dir = source_dir / "natural_earth"
    natural_earth_dir.mkdir(parents=True, exist_ok=True)
    world_polygon = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-180.0, -90.0], [-180.0, 90.0], [180.0, 90.0], [180.0, -90.0], [-180.0, -90.0]]],
                },
            }
        ],
    }
    (natural_earth_dir / NATURAL_EARTH_LAND_FILENAME).write_text(
        json.dumps(world_polygon),
        encoding="utf-8",
    )


def _test_split_config() -> dict[str, object]:
    return {
        "seed": 42,
        "case_count": 1,
        "case_seed_stride": 1009,
        "mission": {
            "case_start_spacing_hours": 2,
            "horizon_hours": 12,
            "action_time_step_s": 5,
            "geometry_sample_step_s": 5,
            "resource_sample_step_s": 10,
            "task_access_sample_step_s": 30,
        },
        "satellite_pool": {
            "min_altitude_m": 450000.0,
            "max_altitude_m": 900000.0,
            "min_retained_count": 1,
            "include_name_tokens": ["LANDSAT", "SENTINEL-2", "SPOT", "PLEIADES"],
            "exclude_name_tokens": ["SAR", "ICEYE"],
        },
        "satellites": {
            "min_per_case": 2,
            "max_per_case": 2,
            "template_fractions": {
                "infrared_balanced": 0.0,
                "visible_agile": 0.0,
                "visible_balanced": 1.0,
            },
            "templates": {
                "visible_agile": {
                    "sensor_type": "visible",
                    "max_off_nadir_deg": 30.0,
                    "max_slew_velocity_deg_per_s": 1.8,
                    "max_slew_acceleration_deg_per_s2": 0.4,
                    "settling_time_s": 2.0,
                    "battery_capacity_wh": 1300.0,
                    "initial_battery_wh": 800.0,
                    "idle_power_w": 20.0,
                    "imaging_power_w": 420.0,
                    "slew_power_w": 360.0,
                    "sunlit_charge_power_w": 85.0,
                },
                "visible_balanced": {
                    "sensor_type": "visible",
                    "max_off_nadir_deg": 25.0,
                    "max_slew_velocity_deg_per_s": 1.0,
                    "max_slew_acceleration_deg_per_s2": 0.25,
                    "settling_time_s": 3.0,
                    "battery_capacity_wh": 1600.0,
                    "initial_battery_wh": 1000.0,
                    "idle_power_w": 25.0,
                    "imaging_power_w": 480.0,
                    "slew_power_w": 280.0,
                    "sunlit_charge_power_w": 100.0,
                },
                "infrared_balanced": {
                    "sensor_type": "infrared",
                    "max_off_nadir_deg": 20.0,
                    "max_slew_velocity_deg_per_s": 0.9,
                    "max_slew_acceleration_deg_per_s2": 0.15,
                    "settling_time_s": 3.5,
                    "battery_capacity_wh": 1800.0,
                    "initial_battery_wh": 1000.0,
                    "idle_power_w": 30.0,
                    "imaging_power_w": 680.0,
                    "slew_power_w": 320.0,
                    "sunlit_charge_power_w": 115.0,
                },
            },
        },
        "tasks": {
            "min_per_case": 4,
            "max_per_case": 4,
            "min_target_separation_m": 25000.0,
            "city_fraction": 1.0,
            "visible_fraction": 1.0,
            "city_weight_options": [3.0],
            "background_weight_options": [1.0],
            "duration_options_s": [15, 20],
            "hotspot_probability": 0.7,
            "hotspot_count": 2,
            "hotspot_min_spacing_s": 600,
            "hotspot_window_slack_options_s": [300],
            "uniform_window_slack_options_s": [900],
        },
    }


def test_main_requires_splits_yaml(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["run.py"])

    with pytest.raises(SystemExit) as exc_info:
        generator_run.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "usage:" in captured.err.lower()


def test_load_generator_config_rejects_unsupported_snapshot_epoch(tmp_path: Path) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path, snapshot_epoch_utc="2026-04-15T00:00:00Z")

    with pytest.raises(ValueError, match="cached CelesTrak snapshot epoch"):
        load_generator_config(splits_path)


def test_main_builds_split_aware_dataset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path)
    output_dir = tmp_path / "output"
    download_dir = tmp_path / "source_data"

    def fake_fetch_all_sources(dest_dir: Path, *, force_download: bool = False):
        _write_source_tree(dest_dir)
        return {
            "celestrak": SourceFetchResult(
                "celestrak",
                [dest_dir / "celestrak" / CELESTRAK_CSV_NAME],
                {
                    "url": CELESTRAK_EARTH_RESOURCES_URL,
                    "snapshot_epoch_utc": CELESTRAK_SNAPSHOT_EPOCH_UTC,
                    "record_count": len(cached_tles.CACHED_CELESTRAK_ROWS),
                    "sha256": "fake",
                    "vendored_snapshot": True,
                },
            ),
            "world_cities": SourceFetchResult(
                "world_cities",
                [dest_dir / "world_cities" / WORLD_CITIES_FILENAME],
                {"url": WORLD_CITIES_URL, "sha256": "fake"},
            ),
            "natural_earth_land": SourceFetchResult(
                "natural_earth_land",
                [dest_dir / "natural_earth" / NATURAL_EARTH_LAND_FILENAME],
                {"url": NATURAL_EARTH_LAND_URL, "sha256": "fake"},
            ),
        }

    def fake_sample_orbit_grid(*args, **kwargs):
        return object()

    def fake_derive_task_access_intervals(task_like, satellites, orbit_grid, **kwargs):
        del orbit_grid, kwargs
        first_satellite = next(
            (
                sat
                for sat in satellites
                if sat["sensor"]["sensor_type"] == task_like["required_sensor_type"]
            ),
            satellites[0],
        )
        start_time = _utc_datetime(2026, 4, 14, 4, 0, 0)
        end_time = start_time + timedelta(seconds=task_like["required_duration_s"])
        return [
            AccessInterval(
                satellite_id=first_satellite["satellite_id"],
                start_index=0,
                end_index=1,
                start_time=start_time,
                end_time=end_time,
                duration_s=task_like["required_duration_s"],
                midpoint_time=start_time + timedelta(seconds=task_like["required_duration_s"] / 2),
                min_off_nadir_deg=1.0,
                max_off_nadir_deg=5.0,
            )
        ]

    monkeypatch.setattr(generator_run, "fetch_all_sources", fake_fetch_all_sources)
    monkeypatch.setattr(gen_build, "sample_orbit_grid", fake_sample_orbit_grid)
    monkeypatch.setattr(gen_build, "derive_task_access_intervals", fake_derive_task_access_intervals)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            str(splits_path),
            "--download-dir",
            str(download_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert generator_run.main() == 0
    index = json.loads((output_dir / "index.json").read_text(encoding="utf-8"))
    assert index["example_smoke_case"] == "test/case_0001"
    assert index["source"]["celestrak"]["snapshot_epoch_utc"] == CELESTRAK_SNAPSHOT_EPOCH_UTC
    assert index["cases"][0]["split"] == "test"
    assert index["cases"][0]["path"] == "cases/test/case_0001"
    assert (output_dir / "cases" / "test" / "case_0001" / "mission.yaml").is_file()
    assert (output_dir / "cases" / "test" / "case_0001" / "satellites.yaml").is_file()
    assert (output_dir / "cases" / "test" / "case_0001" / "tasks.yaml").is_file()


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
        task_config=_test_split_config()["tasks"],
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

    monkeypatch.setattr(
        gen_build,
        "_sample_hotspot_offsets",
        lambda rng, horizon_s, *, task_config: [0, 3600, 7200, 10800],
    )
    monkeypatch.setattr(gen_build, "sample_orbit_grid", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        gen_build,
        "_group_task_counts",
        lambda task_count, *, task_config: {("city", "infrared"): 1},
    )
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
        split_config=_test_split_config(),
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
    legacy_raw_path = tmp_path / "celestrak" / "earth_resources_raw.tle"
    legacy_raw_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_raw_path.write_text("legacy", encoding="utf-8")

    result = sources.download_celestrak(tmp_path, force_download=True)
    csv_path = tmp_path / "celestrak" / "earth_resources.csv"

    assert result.extra["vendored_snapshot"] is True
    assert result.extra["snapshot_epoch_utc"] == CELESTRAK_SNAPSHOT_EPOCH_UTC
    assert result.extra["record_count"] == len(cached_tles.CACHED_CELESTRAK_ROWS)
    assert csv_path.is_file()
    assert not legacy_raw_path.exists()
    assert csv_path.read_text(encoding="utf-8").startswith(
        "name,norad_catalog_id,tle_line1,tle_line2,epoch_iso,inclination_deg,"
    )


def test_download_world_cities_uses_vendored_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        sources.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network should not be used")),
    )

    result = sources.download_world_cities(tmp_path, force_download=True)
    csv_path = tmp_path / "world_cities" / WORLD_CITIES_FILENAME

    assert result.extra["vendored_snapshot"] is True
    assert csv_path.is_file()
    assert csv_path.read_text(encoding="utf-8").startswith("name,country,latitude_deg,longitude_deg,population\n")
