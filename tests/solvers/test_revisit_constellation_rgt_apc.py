from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from solvers.revisit_constellation.rgt_apc_gap_constructive.src.case_io import (  # noqa: E402
    load_case,
)
from solvers.revisit_constellation.rgt_apc_gap_constructive.src.orbit_library import (  # noqa: E402
    OrbitLibraryConfig,
    generate_orbit_library,
    initial_orbit_bounds,
)
from solvers.revisit_constellation.rgt_apc_gap_constructive.src.solution_io import (  # noqa: E402
    write_empty_solution,
)
from solvers.revisit_constellation.rgt_apc_gap_constructive.src.time_grid import (  # noqa: E402
    horizon_sample_times,
    iso_z,
    parse_iso_z,
)
from solvers.revisit_constellation.rgt_apc_gap_constructive.src.visibility import (  # noqa: E402
    VisibilitySample,
    group_visible_samples,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _assets_payload(*, min_altitude_m: float = 500000.0, max_altitude_m: float = 850000.0) -> dict:
    return {
        "max_num_satellites": 4,
        "satellite_model": {
            "model_name": "unit_revisit_bus",
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
            "min_altitude_m": min_altitude_m,
            "max_altitude_m": max_altitude_m,
        },
    }


def _mission_payload() -> dict:
    return {
        "horizon_start": "2025-07-17T12:00:00Z",
        "horizon_end": "2025-07-17T13:00:00Z",
        "targets": [
            {
                "id": "target_001",
                "name": "Unit Target",
                "latitude_deg": 0.0,
                "longitude_deg": 0.0,
                "altitude_m": 0.0,
                "expected_revisit_period_hours": 8.0,
                "min_elevation_deg": 10.0,
                "max_slant_range_m": 1800000.0,
                "min_duration_sec": 30.0,
            }
        ],
    }


def _case_dir(tmp_path: Path) -> Path:
    case_dir = tmp_path / "case_0001"
    _write_json(case_dir / "assets.json", _assets_payload())
    _write_json(case_dir / "mission.json", _mission_payload())
    return case_dir


def test_iso_z_parsing_formatting_and_horizon_grid() -> None:
    start = parse_iso_z("2025-07-17T12:00:00Z", field_name="start")
    end = parse_iso_z("2025-07-17T12:10:00Z", field_name="end")

    assert start == datetime(2025, 7, 17, 12, 0, tzinfo=UTC)
    assert iso_z(start) == "2025-07-17T12:00:00Z"
    assert horizon_sample_times(start, end, 120.0) == [
        start,
        start + timedelta(seconds=120),
        start + timedelta(seconds=240),
        start + timedelta(seconds=360),
        start + timedelta(seconds=480),
    ]

    with pytest.raises(ValueError, match="timezone"):
        parse_iso_z("2025-07-17T12:00:00", field_name="start")


def test_load_case_parses_public_files_without_benchmark_imports(tmp_path: Path) -> None:
    case = load_case(_case_dir(tmp_path))

    assert case.case_id == "case_0001"
    assert case.max_num_satellites == 4
    assert case.horizon_duration_sec == 3600
    assert case.satellite_model.sensor.max_off_nadir_angle_deg == 25.0
    assert list(case.targets) == ["target_001"]
    assert case.targets["target_001"].ecef_position_m[0] > 6.0e6


def test_generate_orbit_library_filters_altitude_bounds_and_stable_ids(tmp_path: Path) -> None:
    case = load_case(_case_dir(tmp_path))
    config = OrbitLibraryConfig(
        max_candidates=4,
        max_rgt_days=1,
        min_revolutions_per_day=10,
        max_revolutions_per_day=18,
        phase_slot_count=4,
    )

    library = generate_orbit_library(case, config)
    candidate_ids = [candidate.candidate_id for candidate in library.candidates]

    assert len(candidate_ids) == 4
    assert len(candidate_ids) == len(set(candidate_ids))
    assert all(candidate.source in {"rgt_apc", "circular_fallback"} for candidate in library.candidates)
    for candidate in library.candidates:
        perigee_m, apogee_m = initial_orbit_bounds(candidate)
        assert case.satellite_model.min_altitude_m <= perigee_m <= case.satellite_model.max_altitude_m
        assert case.satellite_model.min_altitude_m <= apogee_m <= case.satellite_model.max_altitude_m


def test_group_visible_samples_into_min_duration_windows() -> None:
    start = datetime(2025, 7, 17, 12, 0, tzinfo=UTC)
    samples = [
        VisibilitySample(0.0, 5.0, 900000.0, 15.0, False),
        VisibilitySample(60.0, 20.0, 800000.0, 10.0, True),
        VisibilitySample(120.0, 25.0, 700000.0, 8.0, True),
        VisibilitySample(180.0, 5.0, 900000.0, 15.0, False),
        VisibilitySample(240.0, 22.0, 750000.0, 11.0, True),
    ]

    windows = group_visible_samples(
        candidate_id="sat_a",
        target_id="target_001",
        horizon_start=start,
        horizon_end=start + timedelta(seconds=300),
        sample_step_sec=60.0,
        min_duration_sec=120.0,
        samples=samples,
        keep_samples_per_window=2,
    )

    assert len(windows) == 1
    assert windows[0].window_id == "sat_a__target_001__win0000"
    assert windows[0].duration_sec == 120.0
    assert windows[0].sample_count == 2
    assert windows[0].max_elevation_deg == 25.0
    assert len(windows[0].samples) == 2


def test_empty_solution_schema(tmp_path: Path) -> None:
    solution_path = write_empty_solution(tmp_path)

    assert json.loads(solution_path.read_text(encoding="utf-8")) == {
        "actions": [],
        "satellites": [],
    }


def test_solve_sh_smoke_writes_empty_solution_status_and_debug(tmp_path: Path) -> None:
    case_dir = _case_dir(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "orbit_library": {
                    "max_candidates": 1,
                    "max_rgt_days": 1,
                    "min_revolutions_per_day": 10,
                    "max_revolutions_per_day": 18,
                    "phase_slot_count": 1,
                },
                "visibility": {
                    "sample_step_sec": 600.0,
                    "max_windows": 5,
                    "keep_samples_per_window": 2,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    solution_dir = tmp_path / "solution"

    result = subprocess.run(
        [
            str(REPO_ROOT / "solvers/revisit_constellation/rgt_apc_gap_constructive/solve.sh"),
            str(case_dir),
            str(config_dir),
            str(solution_dir),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads((solution_dir / "solution.json").read_text(encoding="utf-8")) == {
        "actions": [],
        "satellites": [],
    }
    status = json.loads((solution_dir / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "phase_1_scaffold_solution_generated"
    assert status["target_count"] == 1
    assert status["orbit_library"]["candidate_count"] == 1
    assert status["visibility"]["candidate_target_pair_count"] == 1
    assert (solution_dir / "debug" / "orbit_candidates.json").exists()
    assert (solution_dir / "debug" / "visibility_windows.json").exists()


def test_solver_source_does_not_import_benchmark_or_experiment_internals() -> None:
    solver_src = REPO_ROOT / "solvers/revisit_constellation/rgt_apc_gap_constructive/src"
    forbidden_fragments = (
        "import benchmarks",
        "from benchmarks",
        "import experiments",
        "from experiments",
        "import runtimes",
        "from runtimes",
    )

    for path in solver_src.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not any(fragment in text for fragment in forbidden_fragments), path
