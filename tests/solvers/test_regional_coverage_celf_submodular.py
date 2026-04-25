from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SOLVER_SRC = REPO_ROOT / "solvers" / "regional_coverage" / "celf_submodular" / "src"
sys.path.insert(0, str(SOLVER_SRC))

from candidates import CandidateConfig, generate_candidates  # noqa: E402
from case_io import CoverageSample, iso_z, load_case, parse_iso_z  # noqa: E402
from coverage import sample_indices_near_centerline  # noqa: E402
from solve import run  # noqa: E402


TLE_LINE1 = "1 44389U 19038C   25198.19039474  .00015630  00000-0  49052-3 0  9999"
TLE_LINE2 = "2 44389  97.9126 220.0010 0009728  22.5714 337.5952 15.33088716331302"


def _write_case(case_dir: Path) -> None:
    case_dir.mkdir(exist_ok=True)
    (case_dir / "manifest.json").write_text(
        json.dumps(
            {
                "benchmark": "regional_coverage",
                "case_id": "unit_regional",
                "coverage_sample_step_s": 5,
                "earth_model": {"shape": "wgs84"},
                "grid_parameters": {"sample_spacing_m": 5000.0},
                "horizon_end": "2025-07-17T00:00:40Z",
                "horizon_start": "2025-07-17T00:00:00Z",
                "scoring": {
                    "max_actions_total": 4,
                    "primary_metric": "coverage_ratio",
                    "revisit_bonus_alpha": 0.0,
                },
                "seed": 1,
                "spec_version": "v1",
                "time_step_s": 10,
            }
        ),
        encoding="utf-8",
    )
    satellite_row = {
        "tle_line1": TLE_LINE1,
        "tle_line2": TLE_LINE2,
        "tle_epoch": "2025-07-17T00:00:00Z",
        "sensor": {
            "min_edge_off_nadir_deg": 10.0,
            "max_edge_off_nadir_deg": 20.0,
            "cross_track_fov_deg": 4.0,
            "min_strip_duration_s": 10,
            "max_strip_duration_s": 20,
        },
        "agility": {
            "max_roll_rate_deg_per_s": 1.0,
            "max_roll_acceleration_deg_per_s2": 0.5,
            "settling_time_s": 2.0,
        },
        "power": {
            "battery_capacity_wh": 10.0,
            "initial_battery_wh": 8.0,
            "idle_power_w": 1.0,
            "imaging_power_w": 2.0,
            "slew_power_w": 1.0,
            "sunlit_charge_power_w": 0.0,
            "imaging_duty_limit_s_per_orbit": None,
        },
    }
    rows = [
        {"satellite_id": "sat_b", **satellite_row},
        {"satellite_id": "sat_a", **satellite_row},
    ]
    (case_dir / "satellites.yaml").write_text(yaml.safe_dump(rows), encoding="utf-8")
    (case_dir / "regions.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"region_id": "region_a", "weight": 2.0},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "coverage_grid.json").write_text(
        json.dumps(
            {
                "grid_version": 1,
                "sample_spacing_m": 5000.0,
                "regions": [
                    {
                        "region_id": "region_a",
                        "total_weight_m2": 3.0,
                        "samples": [
                            {
                                "sample_id": "region_a_s1",
                                "longitude_deg": 0.0,
                                "latitude_deg": 0.0,
                                "weight_m2": 1.0,
                            },
                            {
                                "sample_id": "region_a_s2",
                                "longitude_deg": 10.0,
                                "latitude_deg": 10.0,
                                "weight_m2": 2.0,
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_iso_z_timestamp_round_trip() -> None:
    parsed = parse_iso_z("2025-07-17T00:00:05Z")
    assert iso_z(parsed) == "2025-07-17T00:00:05Z"


def test_candidate_generation_is_grid_aligned_filtered_and_stable(tmp_path: Path) -> None:
    _write_case(tmp_path)
    case = load_case(tmp_path)
    config = CandidateConfig(
        time_stride_s=10,
        duration_values_s=(25, 20, 10),
        roll_values_deg=(19.0, -18.0, 0.0, 12.0),
        max_candidates_total=None,
    )

    candidates, summary = generate_candidates(case, config)

    assert summary.candidate_count == 28
    assert summary.truncated_by_cap is False
    assert all(candidate.start_offset_s % 10 == 0 for candidate in candidates)
    assert {candidate.duration_s for candidate in candidates} == {10, 20}
    assert {candidate.roll_deg for candidate in candidates} == {-18.0, 12.0}
    assert candidates[0].candidate_id == "sat_a|dur=0010|roll=-018.000|start=0000000"
    assert candidates[1].candidate_id == "sat_a|dur=0010|roll=-018.000|start=0000010"
    assert candidates[-1].candidate_id == "sat_b|dur=0020|roll=+012.000|start=0000020"


def test_coverage_sample_indexing_is_duplicate_free() -> None:
    samples = (
        CoverageSample(0, "near", "region_a", 0.0, 0.0, 1.0),
        CoverageSample(1, "also_near", "region_a", 0.01, 0.0, 1.0),
        CoverageSample(2, "far", "region_a", 5.0, 5.0, 1.0),
    )

    covered = sample_indices_near_centerline(((0.0, 0.0), (0.0, 0.0)), samples, 2_000.0)

    assert covered == (0, 1)


def test_phase1_solver_writes_empty_solution_and_status(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    config_dir = tmp_path / "config"
    solution_dir = tmp_path / "solution"
    _write_case(case_dir)
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "candidate_generation": {
                    "time_stride_s": 20,
                    "duration_values_s": [10],
                    "roll_values_deg": [12.0],
                    "max_candidates_total": 3,
                    "debug_candidate_limit": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    assert run(case_dir, config_dir, solution_dir) == 0

    solution = json.loads((solution_dir / "solution.json").read_text(encoding="utf-8"))
    status = json.loads((solution_dir / "status.json").read_text(encoding="utf-8"))
    debug = json.loads((solution_dir / "candidate_debug.json").read_text(encoding="utf-8"))
    assert solution == {"actions": []}
    assert status["parsed_counts"] == {
        "satellite_count": 2,
        "region_count": 1,
        "sample_count": 2,
    }
    assert status["candidate_summary"]["candidate_count"] == 3
    assert status["output_policy"]["empty_solution_only"] is True
    assert len(debug) == 2
