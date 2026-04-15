from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from benchmarks.relay_constellation.generator.run import main


def _write_splits_yaml(path: Path) -> None:
    payload = {
        "example_smoke_case": "test/case_0001",
        "splits": {
            "test": {
                "seed": 42,
                "case_count": 1,
                "case_seed_stride": 10007,
                "schedule": {
                    "base_epoch": "2026-01-01T00:00:00Z",
                    "case_start_spacing_hours": 12,
                    "horizon_hours": 96,
                    "routing_step_s": 60,
                    "window_start_grid_min": 5,
                },
                "backbone": {
                    "total_satellites": {"values": [6], "weights": [1]},
                    "num_planes": {"values": [2], "weights": [1]},
                    "altitude_km": {"values": [10000.0], "weights": [1]},
                    "inclination_deg": {"values": [55.0], "weights": [1]},
                    "eccentricity": {"min": 0.001, "max": 0.001},
                },
                "endpoints": {
                    "count": {"values": [4], "weights": [1]},
                    "min_separation_deg": 15.0,
                    "long_pair_min_distance_m": 7000000.0,
                    "medium_pair_distance_m": {
                        "min": 2500000.0,
                        "max": 6500000.0,
                    },
                },
                "demands": {
                    "pair_count": {"values": [2], "weights": [1]},
                    "total_windows": {"values": [5], "weights": [1]},
                    "duration_minutes": {"values": [60], "weights": [1]},
                    "overlap_anchor_minutes": {"start": 360, "stop": 4200, "step": 5},
                    "secondary_pair_offset_steps": {"min": -6, "max": 6},
                    "min_repeat_gap_minutes": 180,
                    "retry_limit": 50,
                    "endpoint_distance_m": {
                        "long_min": 7000000.0,
                        "medium_min": 2500000.0,
                        "medium_max": 6500000.0,
                    },
                },
                "constraints": {
                    "max_added_satellites": {"values": [6], "weights": [1]},
                    "orbit": {
                        "min_altitude_m": 500000.0,
                        "max_altitude_m": 1500000.0,
                        "max_eccentricity": 0.02,
                        "min_inclination_deg": 20.0,
                        "max_inclination_deg": 85.0,
                    },
                    "links": {
                        "max_isl_range_m": 20000000.0,
                        "max_links_per_satellite": 3,
                        "max_links_per_endpoint": 1,
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


def test_main_builds_split_aware_dataset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
