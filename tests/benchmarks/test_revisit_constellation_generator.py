from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

import benchmarks.revisit_constellation.generator.run as generator_run


def _write_world_cities_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name,country,lat,lng,population",
                "Alpha,Aland,0.0,0.0,1000000",
                "Bravo,Bland,0.0,60.0,900000",
                "Charlie,Cland,30.0,120.0,800000",
                "Delta,Dland,-30.0,-120.0,700000",
                "Echo,Eland,45.0,45.0,600000",
                "Foxtrot,Fland,-45.0,135.0,500000",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_splits_yaml(path: Path) -> None:
    payload = {
        "example_smoke_case": "test/case_0001",
        "source": {
            "world_cities": {
                "kind": "kaggle_dataset",
                "dataset": "juanmah/world-cities",
                "page_url": "https://www.kaggle.com/datasets/juanmah/world-cities",
            }
        },
        "splits": {
            "test": {
                "seed": 42,
                "case_count": 2,
                "case_spec_seed_stride": 10007,
                "target_selection_seed_stride": 10000,
                "target_selection_seed_offset": 1,
                "case_spec": {
                    "target_count": {"min": 3, "max": 3},
                    "max_num_satellites": {"min": 6, "max": 6},
                    "revisit_threshold_hours_options": [6.0],
                },
                "mission": {
                    "horizon_start": "2025-07-17T12:00:00Z",
                    "horizon_end": "2025-07-19T12:00:00Z",
                    "min_target_separation_m": 1000.0,
                    "target_defaults": {
                        "min_elevation_deg": 20.0,
                        "max_slant_range_m": 1800000.0,
                        "min_duration_sec": 30.0,
                    },
                },
                "target_selection": {
                    "initial_pool": {"min_size": 3, "multiplier": 1}
                },
                "satellite_model": {
                    "model_name": "balanced_leo_eo_bus_v1",
                    "sensor": {
                        "max_off_nadir_angle_deg": 25.0,
                        "max_range_m": 1000000.0,
                        "obs_discharge_rate_w": 120.0,
                    },
                    "resource_model": {
                        "battery_capacity_wh": 2000.0,
                        "initial_battery_wh": 1600.0,
                        "idle_discharge_rate_w": 5.0,
                        "sunlight_charge_rate_w": 100.0,
                    },
                    "attitude_model": {
                        "max_slew_velocity_deg_per_sec": 1.0,
                        "max_slew_acceleration_deg_per_sec2": 0.45,
                        "settling_time_sec": 10.0,
                        "maneuver_discharge_rate_w": 90.0,
                    },
                    "min_altitude_m": 500000.0,
                    "max_altitude_m": 850000.0,
                },
            }
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_main_requires_splits_yaml(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["run.py"])

    with pytest.raises(SystemExit) as exc_info:
        generator_run.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "usage:" in captured.err.lower()


def test_main_builds_dataset_from_yaml_and_keeps_download_controls_operational(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "world_cities.csv"
    _write_world_cities_csv(csv_path)
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path)
    output_dir = tmp_path / "output"
    download_dir = tmp_path / "downloads"
    captured: dict[str, object] = {}

    def fake_download_sources(destination_dir: Path, *, force_download: bool = False) -> Path:
        captured["destination_dir"] = destination_dir
        captured["force_download"] = force_download
        return csv_path

    monkeypatch.setattr(generator_run, "download_sources", fake_download_sources)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            str(splits_path),
            "--output-dir",
            str(output_dir),
            "--download-dir",
            str(download_dir),
            "--force-download",
        ],
    )

    assert generator_run.main() == 0
    assert captured["destination_dir"] == download_dir
    assert captured["force_download"] is True
    assert (output_dir / "cases" / "test" / "case_0001" / "assets.json").exists()
    index = json.loads((output_dir / "index.json").read_text(encoding="utf-8"))
    assert index["example_smoke_case"] == "test/case_0001"
    assert len(index["cases"]) == 2
    assert all(case["split"] == "test" for case in index["cases"])
    assert all(case["path"].startswith("cases/test/") for case in index["cases"])
