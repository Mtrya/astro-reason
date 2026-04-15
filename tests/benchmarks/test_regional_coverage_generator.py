from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from benchmarks.regional_coverage.generator.build import (
    SUPPORTED_CELESTRAK_SNAPSHOT_EPOCH_UTC,
    load_generator_config,
)
from benchmarks.regional_coverage.generator.run import main


def _write_splits_yaml(path: Path, *, snapshot_epoch_utc: str = SUPPORTED_CELESTRAK_SNAPSHOT_EPOCH_UTC) -> None:
    payload = {
        "example_smoke_case": "test/case_0001",
        "source": {
            "celestrak": {
                "kind": "vendored_subset",
                "url": "https://celestrak.org/NORAD/elements/gp.php?GROUP=resource&FORMAT=tle",
                "snapshot_epoch_utc": snapshot_epoch_utc,
            },
            "region_library": {
                "path": "generator/region_library.geojson",
            },
        },
        "splits": {
            "test": {
                "seed": 20260408,
                "case_count": 1,
                "dataset_attempt_stride": 1000003,
                "case_attempt_stride": 10007,
                "schedule": {
                    "base_horizon_start": "2025-07-17T00:00:00Z",
                    "case_start_spacing_hours": 12,
                    "horizon_hours": 72,
                    "time_step_s": 10,
                    "coverage_sample_step_s": 5,
                },
                "grid": {
                    "sample_spacing_m": 20000.0,
                    "sample_count": {"min": 100, "max": 100000},
                },
                "scoring": {
                    "max_actions_total": 64,
                    "revisit_bonus_alpha": 0.0,
                },
                "regions": {
                    "count": {"values": [2], "weights": [1]},
                    "total_area_m2": {"min": 1.0e10, "max": 1.0e12},
                    "per_region_area_m2": {"min": 1.0e9, "max": 2.0e11},
                    "min_separation_deg": 8.0,
                    "max_region_reuse": 2,
                },
                "satellites": {
                    "count": {"values": [6], "weights": [1]},
                    "min_unique_satellite_ids": 1,
                    "mixed_case_min": 0,
                    "single_class_min": 0,
                    "assignment": {
                        "single_class_probability": 1.0,
                        "wide_fraction": {"min": 0.35, "max": 0.55},
                        "min_per_class": 2,
                    },
                    "classes": {
                        "sar_narrow": {
                            "sensor": {
                                "min_edge_off_nadir_deg": 18.0,
                                "max_edge_off_nadir_deg": 34.0,
                                "cross_track_fov_deg": 2.8,
                                "min_strip_duration_s": 20,
                                "max_strip_duration_s": 120,
                            },
                            "agility": {
                                "max_roll_rate_deg_per_s": 1.2,
                                "max_roll_acceleration_deg_per_s2": 0.4,
                                "settling_time_s": 2.0,
                            },
                            "power": {
                                "battery_capacity_wh": 900,
                                "initial_battery_wh": 540,
                                "idle_power_w": 85,
                                "imaging_power_w": 290,
                                "slew_power_w": 35,
                                "sunlit_charge_power_w": 170,
                                "imaging_duty_limit_s_per_orbit": 900,
                            },
                        },
                        "sar_wide": {
                            "sensor": {
                                "min_edge_off_nadir_deg": 16.0,
                                "max_edge_off_nadir_deg": 40.0,
                                "cross_track_fov_deg": 4.8,
                                "min_strip_duration_s": 20,
                                "max_strip_duration_s": 180,
                            },
                            "agility": {
                                "max_roll_rate_deg_per_s": 1.8,
                                "max_roll_acceleration_deg_per_s2": 0.7,
                                "settling_time_s": 1.5,
                            },
                            "power": {
                                "battery_capacity_wh": 1300,
                                "initial_battery_wh": 780,
                                "idle_power_w": 105,
                                "imaging_power_w": 360,
                                "slew_power_w": 45,
                                "sunlit_charge_power_w": 230,
                                "imaging_duty_limit_s_per_orbit": 1200,
                            },
                        },
                    },
                },
            }
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_main_requires_splits_yaml(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["run.py"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "usage:" in captured.err.lower()


def test_load_generator_config_rejects_unsupported_snapshot_epoch(tmp_path: Path) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path, snapshot_epoch_utc="2025-07-18T00:00:00Z")

    with pytest.raises(ValueError, match="cached CelesTrak snapshot epoch"):
        load_generator_config(splits_path)


def test_main_builds_split_aware_dataset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path)
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            str(splits_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0
    assert (output_dir / "cases" / "test" / "case_0001" / "manifest.json").exists()
    index = json.loads((output_dir / "index.json").read_text(encoding="utf-8"))
    assert index["example_smoke_case"] == "test/case_0001"
    assert index["cases"][0]["split"] == "test"
    assert index["cases"][0]["path"] == "cases/test/case_0001"
