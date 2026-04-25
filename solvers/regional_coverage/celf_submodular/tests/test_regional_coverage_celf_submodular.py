from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import yaml


SOLVER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
SOLVER_SRC = SOLVER_ROOT / "src"
sys.path.insert(0, str(SOLVER_SRC))

from candidates import CandidateConfig, generate_candidates, load_candidate_config  # noqa: E402
from candidates import StripCandidate  # noqa: E402
from case_io import CoverageSample, iso_z, load_case, parse_iso_z  # noqa: E402
from celf import (  # noqa: E402
    SelectionConfig,
    lazy_forward_selection,
    marginal_gain,
    naive_recomputation_bound,
    naive_forward_selection,
    run_celf_selection,
)
from coverage import (  # noqa: E402
    build_candidate_coverage,
    build_coverage_diagnostics,
    sample_indices_near_centerline,
)
from geometry import strip_centerline_and_half_width_m  # noqa: E402
from schedule import (  # noqa: E402
    repair_schedule,
    required_gap_s,
    slew_time_s,
    validate_schedule,
)
from solve import run  # noqa: E402
from solution_io import write_solution_from_candidates  # noqa: E402


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


def _candidate(
    candidate_id: str,
    *,
    start_offset_s: int = 0,
    duration_s: int = 10,
    roll_deg: float = 12.0,
) -> StripCandidate:
    return StripCandidate(
        candidate_id=candidate_id,
        satellite_id="sat_a",
        start_offset_s=start_offset_s,
        start_time=f"2025-07-17T00:00:{start_offset_s:02d}Z",
        duration_s=duration_s,
        roll_deg=roll_deg,
        theta_inner_deg=10.0,
        theta_outer_deg=14.0,
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


def test_balanced_candidate_cap_spans_eligible_satellites(tmp_path: Path) -> None:
    _write_case(tmp_path)
    case = load_case(tmp_path)
    config = CandidateConfig(
        time_stride_s=10,
        duration_values_s=(10, 20),
        roll_values_deg=(-18.0, 12.0),
        max_candidates_total=4,
    )

    candidates, summary = generate_candidates(case, config)

    assert summary.truncated_by_cap is True
    assert summary.full_candidate_count == 28
    assert summary.removed_by_cap_count == 24
    assert summary.active_caps["cap_strategy"] == "balanced_stride"
    assert summary.candidate_count == 4
    assert set(summary.per_satellite) == {"sat_a", "sat_b"}
    assert summary.per_satellite == {"sat_a": 2, "sat_b": 2}
    assert {candidate.satellite_id for candidate in candidates} == {"sat_a", "sat_b"}


def test_balanced_candidate_cap_is_deterministic(tmp_path: Path) -> None:
    _write_case(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["horizon_end"] = "2025-07-17T02:00:00Z"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    case = load_case(tmp_path)
    config = CandidateConfig(
        time_stride_s=600,
        duration_values_s=(10, 20),
        roll_values_deg=(-18.0, 12.0),
        max_candidates_total=16,
    )

    first, first_summary = generate_candidates(case, config)
    second, second_summary = generate_candidates(case, config)

    assert [candidate.candidate_id for candidate in first] == [
        candidate.candidate_id for candidate in second
    ]
    assert first_summary.as_dict() == second_summary.as_dict()
    assert len(first_summary.per_duration) > 1
    assert len(first_summary.per_roll) > 1
    assert len(first_summary.per_time_bucket) > 1


def test_empty_experiment_config_uses_candidate_defaults(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("{}\n", encoding="utf-8")

    config = load_candidate_config(tmp_path)

    assert config.max_candidates_total == 512
    assert config.time_stride_s == 600
    assert config.cap_strategy == "balanced_stride"


def test_coverage_sample_indexing_is_duplicate_free() -> None:
    samples = (
        CoverageSample(0, "near", "region_a", 0.0, 0.0, 1.0),
        CoverageSample(1, "also_near", "region_a", 0.01, 0.0, 1.0),
        CoverageSample(2, "far", "region_a", 5.0, 5.0, 1.0),
    )

    covered = sample_indices_near_centerline(((0.0, 0.0), (0.0, 0.0)), samples, 2_000.0)

    assert covered == (0, 1)


def test_solver_local_geometry_can_produce_nonzero_candidate_coverage(tmp_path: Path) -> None:
    _write_case(tmp_path)
    initial_case = load_case(tmp_path)
    candidates, _ = generate_candidates(
        initial_case,
        CandidateConfig(
            time_stride_s=10,
            duration_values_s=(20,),
            roll_values_deg=(12.0,),
            max_candidates_total=1,
        ),
    )
    candidate = candidates[0]
    centerline, half_width_m = strip_centerline_and_half_width_m(
        initial_case.manifest,
        initial_case.satellites[candidate.satellite_id],
        candidate,
    )
    assert centerline
    assert half_width_m > 0.0
    lon_deg, lat_deg = centerline[len(centerline) // 2]
    (tmp_path / "coverage_grid.json").write_text(
        json.dumps(
            {
                "grid_version": 1,
                "sample_spacing_m": 5000.0,
                "regions": [
                    {
                        "region_id": "region_a",
                        "total_weight_m2": 7.0,
                        "samples": [
                            {
                                "sample_id": "on_strip",
                                "longitude_deg": lon_deg,
                                "latitude_deg": lat_deg,
                                "weight_m2": 7.0,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    case = load_case(tmp_path)

    coverage_by_candidate, summary = build_candidate_coverage(case, candidates)

    assert summary.zero_coverage_count == 0
    assert summary.unique_sample_count == 1
    assert coverage_by_candidate[candidate.candidate_id] == (0,)

    selected = lazy_forward_selection(
        candidates,
        coverage_by_candidate,
        {0: 7.0},
        budget=1.0,
        policy="unit_cost",
    )
    assert selected.selected_candidate_ids == (candidate.candidate_id,)
    assert selected.objective_value == 7.0


def test_coverage_diagnostics_report_bounds_and_zero_signal(tmp_path: Path) -> None:
    _write_case(tmp_path)
    case = load_case(tmp_path)
    candidates = [
        _candidate("zero", start_offset_s=0, roll_deg=12.0),
        _candidate("nonzero", start_offset_s=10, roll_deg=-12.0),
    ]
    coverage_by_candidate = {"zero": (), "nonzero": (0,)}

    diagnostics = build_coverage_diagnostics(
        case,
        candidates,
        coverage_by_candidate,
        limit=1,
    )

    region_bounds = diagnostics["sample_bounds_by_region"]["region_a"]
    assert region_bounds["sample_count"] == 2
    assert region_bounds["min_longitude_deg"] == 0.0
    assert region_bounds["max_longitude_deg"] == 10.0
    assert region_bounds["min_latitude_deg"] == 0.0
    assert region_bounds["max_latitude_deg"] == 10.0
    assert region_bounds["sample_weight_sum_m2"] == 3.0
    assert region_bounds["total_weight_m2"] == 3.0
    assert diagnostics["all_candidates_zero_coverage"] is False
    assert diagnostics["zero_coverage_count"] == 1
    assert diagnostics["nonzero_coverage_count"] == 1

    buckets = diagnostics["coverage_buckets"]
    assert buckets["time_bucket_width_s"] == 3600
    assert buckets["by_satellite"]["sat_a"]["candidate_count"] == 2
    assert buckets["by_satellite"]["sat_a"]["zero_coverage_count"] == 1
    assert buckets["by_satellite"]["sat_a"]["unique_sample_count"] == 1
    assert buckets["by_duration"]["10"]["candidate_count"] == 2
    assert buckets["by_roll"]["12.000000"]["zero_coverage_count"] == 1
    assert buckets["by_roll"]["-12.000000"]["unique_sample_count"] == 1
    assert buckets["by_time_bucket"]["0000000-0003599"]["candidate_count"] == 2

    rows = diagnostics["candidate_diagnostics"]
    assert len(rows) == 1
    assert rows[0]["candidate_id"] == "zero"
    assert rows[0]["covered_sample_count"] == 0
    assert rows[0]["centerline_bbox"] is not None
    assert rows[0]["coverage_bbox"] is not None
    assert rows[0]["half_width_m"] > 0.0
    assert rows[0]["nearest_sample"]["sample_id"] in {"region_a_s1", "region_a_s2"}
    assert rows[0]["nearest_sample_margin_m"] is not None


def test_coverage_diagnostics_flag_all_zero_coverage(tmp_path: Path) -> None:
    _write_case(tmp_path)
    case = load_case(tmp_path)
    candidates = [
        _candidate("zero_a", start_offset_s=0, roll_deg=12.0),
        _candidate("zero_b", start_offset_s=10, roll_deg=-12.0),
    ]

    diagnostics = build_coverage_diagnostics(
        case,
        candidates,
        {"zero_a": (), "zero_b": ()},
        limit=0,
    )

    assert diagnostics["all_candidates_zero_coverage"] is True
    assert diagnostics["zero_coverage_count"] == 2
    assert diagnostics["nonzero_coverage_count"] == 0
    assert diagnostics["candidate_diagnostics"] == []


def test_marginal_gain_counts_only_fresh_weighted_samples() -> None:
    coverage_by_candidate = {"c1": (0, 1, 2), "c2": (1, 2)}
    sample_weights = {0: 1.5, 1: 2.0, 2: 3.0}

    gain = marginal_gain("c1", coverage_by_candidate, {1}, sample_weights)
    repeated_gain = marginal_gain("c2", coverage_by_candidate, {1, 2}, sample_weights)

    assert gain == 4.5
    assert repeated_gain == 0.0


def test_lazy_and_naive_unit_cost_greedy_agree_on_fixed_candidates() -> None:
    candidates = [
        _candidate("a", start_offset_s=0),
        _candidate("b", start_offset_s=10),
        _candidate("c", start_offset_s=20),
    ]
    coverage_by_candidate = {
        "a": (0, 1),
        "b": (1, 2),
        "c": (3,),
    }
    sample_weights = {0: 3.0, 1: 2.0, 2: 4.0, 3: 1.0}

    lazy = lazy_forward_selection(
        candidates,
        coverage_by_candidate,
        sample_weights,
        budget=2.0,
        policy="unit_cost",
    )
    naive = naive_forward_selection(
        candidates,
        coverage_by_candidate,
        sample_weights,
        budget=2.0,
        policy="unit_cost",
    )

    assert lazy.selected_candidate_ids == naive.selected_candidate_ids == ("b", "a")
    assert lazy.objective_value == naive.objective_value == 9.0
    assert lazy.marginal_recomputations < naive.marginal_recomputations
    assert lazy.as_dict()["estimated_naive_recomputations"] == naive.marginal_recomputations
    assert lazy.as_dict()["estimated_lazy_recomputations_saved"] > 0
    assert lazy.as_dict()["lazy_recomputation_ratio"] < 1.0


def test_lazy_and_naive_cost_benefit_greedy_agree_on_fixed_candidates() -> None:
    candidates = [
        _candidate("large_slow", start_offset_s=0, duration_s=40),
        _candidate("small_fast", start_offset_s=10, duration_s=10),
        _candidate("medium", start_offset_s=20, duration_s=20),
    ]
    coverage_by_candidate = {
        "large_slow": (0, 1, 2, 3),
        "small_fast": (0, 4),
        "medium": (2, 5),
    }
    sample_weights = {0: 4.0, 1: 1.0, 2: 2.0, 3: 1.0, 4: 4.0, 5: 2.0}

    lazy = lazy_forward_selection(
        candidates,
        coverage_by_candidate,
        sample_weights,
        budget=50.0,
        policy="cost_benefit",
        cost_mode="imaging_time",
    )
    naive = naive_forward_selection(
        candidates,
        coverage_by_candidate,
        sample_weights,
        budget=50.0,
        policy="cost_benefit",
        cost_mode="imaging_time",
    )

    assert lazy.selected_candidate_ids == naive.selected_candidate_ids
    assert lazy.objective_value == naive.objective_value
    assert lazy.marginal_recomputations <= naive.marginal_recomputations


def test_naive_recomputation_bound_matches_simple_greedy_rounds() -> None:
    assert naive_recomputation_bound(5, 3, stop_reason="budget_exhausted") == 12
    assert naive_recomputation_bound(5, 3, stop_reason="no_positive_gain") == 14


def test_cost_benefit_can_differ_from_unit_cost_when_costs_differ() -> None:
    candidates = [
        _candidate("long", start_offset_s=0, duration_s=90),
        _candidate("short", start_offset_s=10, duration_s=10),
    ]
    coverage_by_candidate = {
        "long": (0, 1, 2),
        "short": (0,),
    }
    sample_weights = {0: 5.0, 1: 1.0, 2: 1.0}

    unit = lazy_forward_selection(
        candidates,
        coverage_by_candidate,
        sample_weights,
        budget=100.0,
        policy="unit_cost",
        cost_mode="action_count",
    )
    cost_benefit = lazy_forward_selection(
        candidates,
        coverage_by_candidate,
        sample_weights,
        budget=100.0,
        policy="cost_benefit",
        cost_mode="imaging_time",
    )

    assert unit.selected_candidate_ids[0] == "long"
    assert cost_benefit.selected_candidate_ids[0] == "short"


def test_tie_breaking_is_deterministic() -> None:
    candidates = [
        _candidate("later", start_offset_s=20, roll_deg=12.0),
        _candidate("earlier_high_roll", start_offset_s=10, roll_deg=16.0),
        _candidate("earlier_low_roll_z", start_offset_s=10, roll_deg=12.0),
        _candidate("earlier_low_roll_a", start_offset_s=10, roll_deg=-12.0),
    ]
    coverage_by_candidate = {candidate.candidate_id: (0,) for candidate in candidates}
    sample_weights = {0: 3.0}

    result = lazy_forward_selection(
        candidates,
        coverage_by_candidate,
        sample_weights,
        budget=1.0,
        policy="unit_cost",
    )

    assert result.selected_candidate_ids == ("earlier_low_roll_a",)


def test_run_celf_selection_keeps_higher_reward_variant() -> None:
    candidates = [
        _candidate("expensive", start_offset_s=0, duration_s=90),
        _candidate("cheap", start_offset_s=10, duration_s=10),
    ]
    coverage_by_candidate = {
        "expensive": (0, 1, 2),
        "cheap": (0,),
    }
    sample_weights = {0: 5.0, 1: 1.0, 2: 1.0}

    result = run_celf_selection(
        candidates,
        coverage_by_candidate,
        sample_weights,
        max_actions_total=100,
        config=SelectionConfig(cost_mode="imaging_time", budget=90.0),
    )

    assert result.unit_cost is not None
    assert result.cost_benefit is not None
    assert result.as_dict()["algorithm"]["paper"] == (
        "Leskovec et al. CELF / CEF lazy forward selection"
    )
    assert result.as_dict()["algorithm"]["fixed_ground_set"] is True
    assert result.best_policy == "unit_cost"
    assert result.best.selected_candidate_ids == ("expensive",)


def test_roll_slew_time_matches_public_trapezoidal_formula(tmp_path: Path) -> None:
    _write_case(tmp_path)
    case = load_case(tmp_path)
    satellite = case.satellites["sat_a"]

    triangular = slew_time_s(1.0, satellite)
    trapezoidal = slew_time_s(40.0, satellite)

    assert triangular == 2.0 * (1.0 / 0.5) ** 0.5
    assert trapezoidal == (40.0 / 1.0) + (1.0 / 0.5)


def test_overlap_detection_is_half_open_per_satellite(tmp_path: Path) -> None:
    _write_case(tmp_path)
    case = load_case(tmp_path)
    overlap = _candidate("overlap", start_offset_s=5, duration_s=10)
    previous = _candidate("previous", start_offset_s=0, duration_s=10)
    other_satellite = _candidate("other", start_offset_s=5, duration_s=10)
    other_satellite = StripCandidate(
        **{**other_satellite.as_dict(), "satellite_id": "sat_b"}
    )
    candidates_by_id = {
        candidate.candidate_id: candidate
        for candidate in (previous, overlap, other_satellite)
    }

    report = validate_schedule(
        case, candidates_by_id, ("previous", "overlap", "other")
    )

    assert report.valid is False
    assert any(issue.issue_type == "overlap" for issue in report.issues)
    assert not any(
        issue.issue_type == "overlap" and "other" in issue.candidate_ids
        for issue in report.issues
    )


def test_slew_gap_validation_accepts_exact_boundary(tmp_path: Path) -> None:
    _write_case(tmp_path)
    case = load_case(tmp_path)
    first = _candidate("first", start_offset_s=0, duration_s=10, roll_deg=12.0)
    satellite = case.satellites["sat_a"]
    gap = required_gap_s(
        first,
        _candidate("probe", start_offset_s=0, duration_s=10, roll_deg=-12.0),
        satellite,
    )
    second_start = first.start_offset_s + first.duration_s + math.ceil(gap)
    second = _candidate("second", start_offset_s=second_start, duration_s=10, roll_deg=-12.0)
    candidates_by_id = {"first": first, "second": second}

    report = validate_schedule(case, candidates_by_id, ("first", "second"))

    assert not any(issue.issue_type == "slew_gap" for issue in report.issues)


def test_deterministic_repair_removes_lower_loss_conflicting_candidate(tmp_path: Path) -> None:
    _write_case(tmp_path)
    case = load_case(tmp_path)
    keep = _candidate("keep", start_offset_s=0, duration_s=20, roll_deg=12.0)
    drop = _candidate("drop", start_offset_s=10, duration_s=10, roll_deg=12.0)
    candidates_by_id = {"keep": keep, "drop": drop}
    coverage_by_candidate = {"keep": (0, 1), "drop": (1,)}
    sample_weights = {0: 10.0, 1: 1.0}

    result = repair_schedule(
        case,
        candidates_by_id,
        ("keep", "drop"),
        coverage_by_candidate,
        sample_weights,
    )

    assert result.before.valid is False
    assert result.after.valid is True
    assert result.repaired_candidate_ids == ("keep",)
    assert result.removed_candidate_ids == ("drop",)
    assert result.repair_log[0].reason == "overlap"


def test_repair_enforces_action_cap_deterministically(tmp_path: Path) -> None:
    _write_case(tmp_path)
    case = load_case(tmp_path)
    object.__setattr__(case.manifest, "max_actions_total", 1)
    first = _candidate("first", start_offset_s=0, duration_s=10)
    second = _candidate("second", start_offset_s=30, duration_s=10)
    candidates_by_id = {"first": first, "second": second}
    coverage_by_candidate = {"first": (0,), "second": (1,)}
    sample_weights = {0: 5.0, 1: 1.0}

    result = repair_schedule(
        case,
        candidates_by_id,
        ("first", "second"),
        coverage_by_candidate,
        sample_weights,
    )

    assert result.after.valid is True
    assert result.repaired_candidate_ids == ("first",)
    assert result.removed_candidate_ids == ("second",)


def test_solution_output_schema_has_only_public_action_fields(tmp_path: Path) -> None:
    candidate = _candidate("public", start_offset_s=0, duration_s=10, roll_deg=12.0)

    write_solution_from_candidates(tmp_path, {"public": candidate}, ("public",))

    solution = json.loads((tmp_path / "solution.json").read_text(encoding="utf-8"))
    assert list(solution) == ["actions"]
    assert set(solution["actions"][0]) == {
        "type",
        "satellite_id",
        "start_time",
        "duration_s",
        "roll_deg",
    }
    assert solution["actions"][0]["type"] == "strip_observation"


def test_solver_writes_solution_status_and_repair_debug(tmp_path: Path) -> None:
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
    assert status["coverage_diagnostics"]["candidate_count"] == 3
    assert "sample_bounds_by_region" in status["coverage_diagnostics"]
    assert "coverage_buckets" in status["coverage_diagnostics"]
    assert len(status["coverage_diagnostics"]["candidate_diagnostics"]) == 2
    assert "celf_summary" in status
    assert status["phase"] == "phase_5_validation_tuning_and_reproduction_fidelity"
    assert "feasibility_summary" in status
    assert status["reproduction_summary"]["paper_faithful_elements"]["celf_lazy_updates"]
    assert status["reproduction_summary"]["benchmark_adaptations"]["official_validation"]
    assert status["output_policy"]["satellite_repair_enabled"] is True
    assert status["output_policy"]["experiment_registration_enabled"] is True
    assert len(debug) == 2
    assert (solution_dir / "debug" / "celf_summary.json").is_file()
    assert (solution_dir / "debug" / "coverage_diagnostics.json").is_file()
    assert (solution_dir / "debug" / "feasibility_summary.json").is_file()
    assert (solution_dir / "debug" / "repair_log.json").is_file()
    assert (solution_dir / "debug" / "repaired_candidates.json").is_file()
    assert (solution_dir / "debug" / "reproduction_summary.json").is_file()
