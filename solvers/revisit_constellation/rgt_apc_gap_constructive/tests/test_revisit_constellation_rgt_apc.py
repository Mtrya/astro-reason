from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


SOLVER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SOLVER_DIR))

from src.baseline import (  # noqa: E402
    OFFICIAL_VERIFICATION_BOUNDARY,
    build_baseline_evidence,
)
from src.case_io import (  # noqa: E402
    load_case,
    load_solver_config,
)
from src.gaps import (  # noqa: E402
    gap_improvement,
    score_observation_timelines,
)
from src.orbit_library import (  # noqa: E402
    OrbitCandidate,
    OrbitLibraryConfig,
    generate_orbit_library,
    initial_orbit_bounds,
)
from src.propagation import PropagationCache  # noqa: E402
from src.scheduling import (  # noqa: E402
    SchedulingConfig,
    ScheduledObservation,
    build_observation_options,
    repair_schedule_deterministic,
    schedule_observations,
    validate_schedule_local,
)
from src.selection import (  # noqa: E402
    SelectionConfig,
    select_satellites_greedy,
)
from src.solution_io import (  # noqa: E402
    write_empty_solution,
)
from src.time_grid import (  # noqa: E402
    horizon_sample_times,
    iso_z,
    parse_iso_z,
)
from src.visibility import (  # noqa: E402
    VisibilityConfig,
    VisibilitySample,
    VisibilityWindow,
    build_visibility_library,
    group_visible_samples,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _assets_payload(
    *,
    min_altitude_m: float = 500000.0,
    max_altitude_m: float = 850000.0,
    initial_battery_wh: float = 1600.0,
) -> dict:
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
                "initial_battery_wh": initial_battery_wh,
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


def _mission_payload(*, expected_revisit_period_hours: float = 8.0) -> dict:
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
                "expected_revisit_period_hours": expected_revisit_period_hours,
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


def _gap_case_dir(tmp_path: Path, *, expected_revisit_period_hours: float = 0.4) -> Path:
    case_dir = tmp_path / "gap_case"
    _write_json(case_dir / "assets.json", _assets_payload())
    _write_json(
        case_dir / "mission.json",
        _mission_payload(expected_revisit_period_hours=expected_revisit_period_hours),
    )
    return case_dir


def _scheduler_case_dir(tmp_path: Path) -> Path:
    case_dir = tmp_path / "scheduler_case"
    mission = _mission_payload(expected_revisit_period_hours=0.4)
    mission["targets"].append(
        {
            "id": "target_002",
            "name": "Second Target",
            "latitude_deg": 1.0,
            "longitude_deg": 1.0,
            "altitude_m": 0.0,
            "expected_revisit_period_hours": 0.4,
            "min_elevation_deg": 10.0,
            "max_slant_range_m": 1800000.0,
            "min_duration_sec": 30.0,
        }
    )
    _write_json(case_dir / "assets.json", _assets_payload())
    _write_json(case_dir / "mission.json", mission)
    return case_dir


def _wide_visibility_case_dir(tmp_path: Path) -> Path:
    case_dir = tmp_path / "wide_visibility_case"
    assets = _assets_payload()
    assets["satellite_model"]["sensor"]["max_off_nadir_angle_deg"] = 180.0
    assets["satellite_model"]["sensor"]["max_range_m"] = 50000000.0
    mission = _mission_payload(expected_revisit_period_hours=0.4)
    mission["targets"][0]["min_elevation_deg"] = -90.0
    mission["targets"][0]["max_slant_range_m"] = 50000000.0
    mission["targets"][0]["min_duration_sec"] = 60.0
    mission["targets"].append(
        {
            "id": "target_002",
            "name": "Wide Second Target",
            "latitude_deg": 20.0,
            "longitude_deg": 15.0,
            "altitude_m": 0.0,
            "expected_revisit_period_hours": 0.4,
            "min_elevation_deg": -90.0,
            "max_slant_range_m": 50000000.0,
            "min_duration_sec": 60.0,
        }
    )
    _write_json(case_dir / "assets.json", assets)
    _write_json(case_dir / "mission.json", mission)
    return case_dir


def _low_battery_case_dir(tmp_path: Path) -> Path:
    case_dir = tmp_path / "low_battery_case"
    _write_json(case_dir / "assets.json", _assets_payload(initial_battery_wh=1.0))
    _write_json(case_dir / "mission.json", _mission_payload())
    return case_dir


def _candidate(candidate_id: str) -> OrbitCandidate:
    return OrbitCandidate(
        candidate_id=candidate_id,
        source="unit",
        semi_major_axis_m=7000000.0,
        eccentricity=0.0,
        inclination_deg=53.0,
        raan_deg=0.0,
        argument_of_perigee_deg=0.0,
        mean_anomaly_deg=0.0,
        altitude_m=600000.0,
        period_ratio_np=None,
        period_ratio_nd=None,
        phase_slot_index=0,
        phase_slot_count=1,
        state_eci_m_mps=(7000000.0, 0.0, 0.0, 0.0, 7500.0, 0.0),
    )


def _window(
    candidate_id: str,
    target_id: str,
    start: datetime,
    minutes: int,
    *,
    off_nadir_deg: float = 2.0,
) -> VisibilityWindow:
    window_start = start + timedelta(minutes=minutes)
    window_end = window_start + timedelta(seconds=60)
    return VisibilityWindow(
        window_id=f"{candidate_id}_{target_id}_{minutes}",
        candidate_id=candidate_id,
        target_id=target_id,
        start=window_start,
        end=window_end,
        midpoint=window_start + timedelta(seconds=30),
        duration_sec=60.0,
        max_elevation_deg=50.0,
        min_slant_range_m=700000.0,
        min_off_nadir_deg=off_nadir_deg,
        sample_count=1,
        samples=(),
    )


def _scheduled(
    option_id: str,
    satellite_id: str,
    target_id: str,
    start: datetime,
    seconds: int = 30,
) -> ScheduledObservation:
    end = start + timedelta(seconds=seconds)
    return ScheduledObservation(
        option_id=option_id,
        window_id=option_id,
        satellite_id=satellite_id,
        target_id=target_id,
        start=start,
        end=end,
        midpoint=start + ((end - start) / 2),
        quality_score=1.0,
    )


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


def test_config_example_loads_all_solver_component_configs(tmp_path: Path) -> None:
    case = load_case(_case_dir(tmp_path))
    config_dir = tmp_path / "example_config"
    config_dir.mkdir()
    config_text = (
        REPO_ROOT / "solvers/revisit_constellation/rgt_apc_gap_constructive/config.example.yaml"
    ).read_text(encoding="utf-8")
    (config_dir / "config.yaml").write_text(config_text, encoding="utf-8")

    payload = load_solver_config(config_dir)
    orbit_config = OrbitLibraryConfig.from_mapping(payload, case)
    visibility_config = VisibilityConfig.from_mapping(payload)
    selection_config = SelectionConfig.from_mapping(payload)
    scheduling_config = SchedulingConfig.from_mapping(payload)

    assert orbit_config.max_candidates == 18
    assert visibility_config.sample_step_sec == 120.0
    assert visibility_config.worker_count is None
    assert selection_config.require_positive_improvement is True
    assert scheduling_config.enable_repair is True
    assert scheduling_config.repair_max_iterations == 3


def test_propagation_cache_state_grid_matches_scalar_states(tmp_path: Path) -> None:
    case = load_case(_case_dir(tmp_path))
    candidate = _candidate("sat_a")
    cache = PropagationCache([candidate], case.horizon_start, case.horizon_end)
    sample_times = horizon_sample_times(case.horizon_start, case.horizon_end, 600.0)

    grid = cache.candidate_state_grid(candidate.candidate_id, sample_times)
    same_grid = cache.candidate_state_grid(candidate.candidate_id, sample_times)

    assert same_grid is grid
    assert grid.candidate_id == "sat_a"
    assert grid.sample_times == tuple(sample_times)
    assert grid.eci_states.shape == (len(sample_times), 6)
    assert grid.ecef_states.shape == (len(sample_times), 6)
    for index, instant in enumerate(sample_times):
        assert grid.eci_states[index] == pytest.approx(
            cache.state_eci(candidate.candidate_id, instant)
        )
        assert grid.ecef_states[index] == pytest.approx(
            cache.state_ecef(candidate.candidate_id, instant)
        )


def test_parallel_visibility_matches_serial_state_grid_output(tmp_path: Path) -> None:
    case = load_case(_wide_visibility_case_dir(tmp_path))
    candidates = [_candidate("sat_b"), _candidate("sat_a")]
    serial = build_visibility_library(
        case,
        candidates,
        VisibilityConfig(
            sample_step_sec=600.0,
            keep_samples_per_window=3,
            worker_count=1,
        ),
    )
    parallel = build_visibility_library(
        case,
        candidates,
        VisibilityConfig(
            sample_step_sec=600.0,
            keep_samples_per_window=3,
            worker_count=2,
        ),
    )

    assert serial.sample_count == parallel.sample_count
    assert serial.pair_count == parallel.pair_count
    assert [window.as_dict() for window in serial.windows] == [
        window.as_dict() for window in parallel.windows
    ]
    assert serial.caps["worker_count_used"] == 1
    assert parallel.caps["worker_count_used"] == 2
    assert serial.caps["state_cache"]["cached_candidate_count"] == 2
    assert [window.window_id for window in parallel.windows] == sorted(
        [window.window_id for window in parallel.windows]
    )


def test_visibility_window_cap_applies_after_deterministic_sort(tmp_path: Path) -> None:
    case = load_case(_wide_visibility_case_dir(tmp_path))
    candidates = [_candidate("sat_b"), _candidate("sat_a")]
    uncapped = build_visibility_library(
        case,
        candidates,
        VisibilityConfig(sample_step_sec=600.0, worker_count=1),
    )
    capped_serial = build_visibility_library(
        case,
        candidates,
        VisibilityConfig(sample_step_sec=600.0, max_windows=2, worker_count=1),
    )
    capped_parallel = build_visibility_library(
        case,
        candidates,
        VisibilityConfig(sample_step_sec=600.0, max_windows=2, worker_count=2),
    )

    expected = [window.as_dict() for window in uncapped.windows[:2]]
    assert [window.as_dict() for window in capped_serial.windows] == expected
    assert [window.as_dict() for window in capped_parallel.windows] == expected
    assert capped_parallel.caps["window_count_capped"] is True
    assert capped_parallel.caps["uncapped_visibility_window_count"] == len(
        uncapped.windows
    )


def test_gap_score_matches_boundary_inclusive_benchmark_metrics(tmp_path: Path) -> None:
    case = load_case(_gap_case_dir(tmp_path, expected_revisit_period_hours=0.4))
    midpoint = case.horizon_start + timedelta(minutes=30)

    score = score_observation_timelines(
        case,
        {"target_001": [midpoint, midpoint]},
    )

    target_score = score.target_gap_summary["target_001"]
    assert target_score.observation_count == 1
    assert target_score.max_revisit_gap_hours == pytest.approx(0.5)
    assert target_score.mean_revisit_gap_hours == pytest.approx(0.5)
    assert score.threshold_violation_count == 1
    assert score.capped_max_revisit_gap_hours == pytest.approx(0.5)


def test_gap_improvement_uses_benchmark_style_caps_and_mean(tmp_path: Path) -> None:
    case = load_case(_gap_case_dir(tmp_path, expected_revisit_period_hours=0.6))
    before = score_observation_timelines(case, {})
    after = score_observation_timelines(
        case,
        {
            "target_001": [
                case.horizon_start + timedelta(minutes=20),
                case.horizon_start + timedelta(minutes=40),
            ]
        },
    )

    improvement = gap_improvement(before, after)

    assert before.threshold_violation_count == 1
    assert after.threshold_violation_count == 0
    assert improvement.threshold_violation_reduction == 1
    assert improvement.capped_max_revisit_gap_reduction_hours == pytest.approx(0.4)
    assert improvement.max_revisit_gap_reduction_hours == pytest.approx(2.0 / 3.0)
    assert improvement.mean_revisit_gap_reduction_hours == pytest.approx(2.0 / 3.0)


def test_greedy_selection_respects_case_and_config_caps(tmp_path: Path) -> None:
    case = load_case(_gap_case_dir(tmp_path))
    candidates = [
        _candidate("sat_a"),
        _candidate("sat_b"),
        _candidate("sat_c"),
        _candidate("sat_d"),
        _candidate("sat_e"),
    ]
    windows = [
        _window("sat_a", "target_001", case.horizon_start, 15),
        _window("sat_b", "target_001", case.horizon_start, 30),
        _window("sat_c", "target_001", case.horizon_start, 45),
        _window("sat_d", "target_001", case.horizon_start, 5),
        _window("sat_e", "target_001", case.horizon_start, 55),
    ]

    config_capped = select_satellites_greedy(
        case=case,
        candidates=candidates,
        windows=windows,
        config=SelectionConfig(max_selected_satellites=2),
    )
    case_capped = select_satellites_greedy(
        case=case,
        candidates=candidates,
        windows=windows,
        config=SelectionConfig(max_selected_satellites=99),
    )

    assert len(config_capped.selected_candidate_ids) == 2
    assert config_capped.caps["selected_satellite_limit"] == 2
    assert config_capped.caps["stopped_by_limit"] is True
    assert len(case_capped.selected_candidate_ids) == case.max_num_satellites
    assert case_capped.caps["selected_satellite_limit"] == case.max_num_satellites


def test_greedy_selection_uses_deterministic_candidate_id_ties(tmp_path: Path) -> None:
    case = load_case(_gap_case_dir(tmp_path))
    candidates = [_candidate("sat_b"), _candidate("sat_a")]
    windows = [
        _window("sat_b", "target_001", case.horizon_start, 30),
        _window("sat_a", "target_001", case.horizon_start, 30),
    ]

    result = select_satellites_greedy(
        case=case,
        candidates=candidates,
        windows=windows,
        config=SelectionConfig(max_selected_satellites=1),
    )

    assert result.selected_candidate_ids == ["sat_a"]


def test_scheduler_prioritizes_lower_flexibility_when_freshness_ties(tmp_path: Path) -> None:
    case = load_case(_scheduler_case_dir(tmp_path))
    windows = [
        _window("sat_a", "target_001", case.horizon_start, 10),
        _window("sat_a", "target_001", case.horizon_start, 40),
        _window("sat_b", "target_002", case.horizon_start, 30),
    ]

    result = schedule_observations(
        case=case,
        selected_candidate_ids=["sat_a", "sat_b"],
        windows=windows,
        config=SchedulingConfig(
            max_actions=1,
            transition_gap_sec=0.0,
            enforce_simple_energy_budget=False,
            enable_repair=False,
        ),
    )

    assert result.scheduled_observations[0].target_id == "target_002"
    assert result.decisions[0].target_flexibility == 1
    assert result.actions[0]["action_type"] == "observation"


def test_scheduler_prioritizes_staler_target_after_freshness_update(tmp_path: Path) -> None:
    case = load_case(_scheduler_case_dir(tmp_path))
    windows = [
        _window("sat_a", "target_001", case.horizon_start, 10),
        _window("sat_b", "target_001", case.horizon_start, 50),
        _window("sat_c", "target_002", case.horizon_start, 20),
        _window("sat_d", "target_002", case.horizon_start, 40),
    ]

    result = schedule_observations(
        case=case,
        selected_candidate_ids=["sat_a", "sat_b", "sat_c", "sat_d"],
        windows=windows,
        config=SchedulingConfig(
            max_actions=2,
            transition_gap_sec=0.0,
            enforce_simple_energy_budget=False,
            enable_repair=False,
        ),
    )

    assert [decision.selected_option.target_id for decision in result.decisions] == [
        "target_001",
        "target_002",
    ]
    second_score = result.decisions[1].score_before.target_gap_summary
    assert second_score["target_002"].max_revisit_gap_hours > second_score[
        "target_001"
    ].max_revisit_gap_hours


def test_scheduler_uses_lower_opportunity_cost_within_target(tmp_path: Path) -> None:
    case = load_case(_scheduler_case_dir(tmp_path))
    windows = [
        _window("sat_a", "target_001", case.horizon_start, 10),
        _window("sat_a", "target_001", case.horizon_start, 40),
        _window("sat_a", "target_002", case.horizon_start, 10, off_nadir_deg=0.1),
        _window("sat_b", "target_002", case.horizon_start, 20),
        _window("sat_c", "target_002", case.horizon_start, 30),
        _window("sat_d", "target_002", case.horizon_start, 50),
    ]

    result = schedule_observations(
        case=case,
        selected_candidate_ids=["sat_a", "sat_b", "sat_c", "sat_d"],
        windows=windows,
        config=SchedulingConfig(
            max_actions=1,
            transition_gap_sec=0.0,
            enforce_simple_energy_budget=False,
            enable_repair=False,
        ),
    )

    first = result.scheduled_observations[0]
    assert first.target_id == "target_001"
    assert first.window_id == "sat_a_target_001_40"
    assert result.decisions[0].opportunity_cost == pytest.approx(0.0)


def test_scheduler_uses_deterministic_window_ties(tmp_path: Path) -> None:
    case = load_case(_gap_case_dir(tmp_path))
    windows = [
        _window("sat_b", "target_001", case.horizon_start, 30),
        _window("sat_a", "target_001", case.horizon_start, 30),
    ]

    result = schedule_observations(
        case=case,
        selected_candidate_ids=["sat_a", "sat_b"],
        windows=windows,
        config=SchedulingConfig(
            max_actions=1,
            transition_gap_sec=0.0,
            enforce_simple_energy_budget=False,
            enable_repair=False,
        ),
    )

    assert result.scheduled_observations[0].satellite_id == "sat_a"
    assert result.final_score.target_gap_summary["target_001"].observation_count == 1


def test_scheduler_records_reproduction_fidelity_mode_comparison(tmp_path: Path) -> None:
    case = load_case(_scheduler_case_dir(tmp_path))
    windows = [
        _window("sat_a", "target_001", case.horizon_start, 10),
        _window("sat_a", "target_001", case.horizon_start, 40),
        _window("sat_b", "target_002", case.horizon_start, 30),
    ]

    result = schedule_observations(
        case=case,
        selected_candidate_ids=["sat_a", "sat_b"],
        windows=windows,
        config=SchedulingConfig(
            max_actions=1,
            transition_gap_sec=0.0,
            enforce_simple_energy_budget=False,
            enable_repair=True,
            repair_max_iterations=1,
        ),
    )

    entries = {entry["mode"]: entry for entry in result.mode_comparison["entries"]}
    assert result.mode_comparison["mode_order"] == [
        "no_op",
        "fifo",
        "constructive",
        "repaired",
    ]
    assert entries["no_op"]["action_count"] == 0
    assert entries["fifo"]["scheduled_option_ids"] == ["sat_a_target_001_10"]
    assert entries["constructive"]["scheduled_option_ids"] == ["sat_b_target_002_30"]
    assert entries["repaired"]["action_count"] == len(result.scheduled_observations)
    assert result.debug_summary["mode_comparison_compact"][0]["mode"] == "no_op"
    assert result.debug_summary["high_gap_target_count"] == len(
        result.validation_report.high_gap_target_ids
    )
    assert result.debug_summary["option_count_by_target"] == {
        "target_001": 2,
        "target_002": 1,
    }
    assert result.debug_summary["scheduled_action_count_by_target"] == {
        "target_002": 1
    }


def test_baseline_evidence_records_target_reasons_and_timing(tmp_path: Path) -> None:
    case = load_case(_scheduler_case_dir(tmp_path))
    candidates = [_candidate("sat_a"), _candidate("sat_b")]
    windows = [
        _window("sat_a", "target_001", case.horizon_start, 10),
        _window("sat_a", "target_001", case.horizon_start, 40),
        _window("sat_b", "target_002", case.horizon_start, 30),
    ]
    orbit_library = generate_orbit_library(
        case,
        OrbitLibraryConfig(
            max_candidates=2,
            max_rgt_days=1,
            min_revolutions_per_day=10,
            max_revolutions_per_day=18,
            phase_slot_count=2,
        ),
    )
    visibility_library = type(
        "VisibilityLibraryStub",
        (),
        {
            "windows": windows,
            "sample_count": 8,
            "pair_count": 4,
        },
    )()
    selection_result = select_satellites_greedy(
        case=case,
        candidates=candidates,
        windows=windows,
        config=SelectionConfig(max_selected_satellites=2),
    )
    scheduling_result = schedule_observations(
        case=case,
        selected_candidate_ids=["sat_a", "sat_b"],
        windows=windows,
        config=SchedulingConfig(
            max_actions=1,
            transition_gap_sec=0.0,
            enforce_simple_energy_budget=False,
            enable_repair=False,
        ),
    )

    evidence = build_baseline_evidence(
        case=case,
        orbit_library=orbit_library,
        visibility_library=visibility_library,
        selection_result=selection_result,
        scheduling_result=scheduling_result,
        timing_seconds={
            "orbit_library": 1.0,
            "visibility": 3.0,
            "selection": 0.5,
            "scheduling": 5.5,
            "total": 10.0,
        },
    )

    assert evidence["version"] == 1
    assert evidence["official_verification_boundary"] == OFFICIAL_VERIFICATION_BOUNDARY
    assert evidence["timing_profile"]["dominant_stage_order"] == [
        "scheduling",
        "visibility",
        "orbit_library",
        "selection",
    ]
    assert evidence["counts"]["candidate_count"] == 2
    assert evidence["counts"]["option_count"] == 3
    assert [row["target_id"] for row in evidence["target_evidence"]] == [
        "target_001",
        "target_002",
    ]
    by_target = {row["target_id"]: row for row in evidence["target_evidence"]}
    assert by_target["target_001"]["unobserved_reason"] == "options_available_not_scheduled"
    assert by_target["target_002"]["unobserved_reason"] is None
    assert by_target["target_001"]["visibility_window_count"] == 2
    assert by_target["target_002"]["scheduled_action_count"] == 1
    assert [entry["mode"] for entry in evidence["mode_comparison_compact"]] == [
        "no_op",
        "fifo",
        "constructive",
        "repaired",
    ]


def test_local_validation_reports_overlap_high_gap_and_battery_risk(tmp_path: Path) -> None:
    overlap_case = load_case(_gap_case_dir(tmp_path))
    overlapping = [
        _scheduled("obs_a", "sat_a", "target_001", overlap_case.horizon_start + timedelta(minutes=10)),
        _scheduled(
            "obs_b",
            "sat_a",
            "target_001",
            overlap_case.horizon_start + timedelta(minutes=10, seconds=10),
        ),
    ]
    overlap_report = validate_schedule_local(
        case=overlap_case,
        scheduled=overlapping,
        selected_candidate_ids=["sat_a"],
        transition_gap_sec=0.0,
        propagation=None,
    )

    assert "overlap" in {issue.reason for issue in overlap_report.issues}
    assert overlap_report.high_gap_target_ids == ["target_001"]

    battery_case = load_case(_low_battery_case_dir(tmp_path))
    battery_report = validate_schedule_local(
        case=battery_case,
        scheduled=[],
        selected_candidate_ids=["sat_a"],
        transition_gap_sec=0.0,
        propagation=None,
    )

    assert "battery_risk" in {issue.reason for issue in battery_report.issues}
    assert battery_report.battery_risk_by_satellite["sat_a"] < 0.0


def test_repair_removes_overlapping_observation_deterministically(tmp_path: Path) -> None:
    case = load_case(_gap_case_dir(tmp_path))
    scheduled = [
        _scheduled("obs_b", "sat_a", "target_001", case.horizon_start + timedelta(minutes=10)),
        _scheduled(
            "obs_a",
            "sat_a",
            "target_001",
            case.horizon_start + timedelta(minutes=10, seconds=10),
        ),
    ]

    repaired, steps, report = repair_schedule_deterministic(
        case=case,
        scheduled=scheduled,
        options=[],
        selected_candidate_ids=["sat_a"],
        config=SchedulingConfig(
            transition_gap_sec=0.0,
            enforce_simple_energy_budget=False,
            repair_max_iterations=2,
        ),
        transition_gap_sec=0.0,
        propagation=None,
    )

    assert [step.action for step in steps] == ["remove"]
    assert steps[0].reason == "overlap"
    assert len(repaired) == 1
    assert repaired[0].option_id == "obs_a"
    assert report.is_valid


def test_repair_inserts_high_gap_target_option_deterministically(tmp_path: Path) -> None:
    case = load_case(_scheduler_case_dir(tmp_path))
    windows = [
        _window("sat_a", "target_001", case.horizon_start, 10),
        _window("sat_b", "target_002", case.horizon_start, 30),
    ]
    options, _ = build_observation_options(
        case=case,
        selected_candidate_ids={"sat_a", "sat_b"},
        selected_candidates=None,
        windows=windows,
        config=SchedulingConfig(enforce_simple_energy_budget=False),
    )
    scheduled = [
        _scheduled("sat_a_target_001_10", "sat_a", "target_001", case.horizon_start + timedelta(minutes=10, seconds=15))
    ]

    repaired, steps, report = repair_schedule_deterministic(
        case=case,
        scheduled=scheduled,
        options=options,
        selected_candidate_ids=["sat_a", "sat_b"],
        config=SchedulingConfig(
            transition_gap_sec=0.0,
            enforce_simple_energy_budget=False,
            repair_max_iterations=1,
        ),
        transition_gap_sec=0.0,
        propagation=None,
    )

    assert [step.action for step in steps] == ["insert"]
    assert steps[0].inserted_observation is not None
    assert steps[0].inserted_observation.target_id == "target_002"
    assert len(repaired) == 2
    assert report.score.target_gap_summary["target_002"].observation_count == 1


def test_solve_sh_smoke_writes_selected_solution_status_and_debug(tmp_path: Path) -> None:
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
                "scheduling": {
                    "transition_gap_sec": 0.0,
                    "enforce_simple_energy_budget": False,
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
    solution = json.loads((solution_dir / "solution.json").read_text(encoding="utf-8"))
    assert isinstance(solution["actions"], list)
    assert isinstance(solution["satellites"], list)
    status = json.loads((solution_dir / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "phase_6_reproduction_fidelity_validated"
    assert status["target_count"] == 1
    assert status["orbit_library"]["candidate_count"] == 1
    assert status["visibility"]["candidate_target_pair_count"] == 1
    assert status["selection"]["selected_candidate_count"] == len(solution["satellites"])
    assert status["scheduling"]["action_count"] == len(solution["actions"])
    assert status["baseline_evidence"]["version"] == 1
    assert status["baseline_evidence"]["counts"]["target_count"] == 1
    assert status["baseline_evidence"]["counts"]["candidate_count"] == 1
    assert status["baseline_evidence"]["counts"]["action_count"] == len(solution["actions"])
    boundary = status["baseline_evidence"]["official_verification_boundary"]
    assert boundary.startswith("Solver output records local metrics only")
    assert "experiments/main_solver" in boundary
    assert status["reproduction_fidelity"]["mode_comparison"]["mode_order"] == [
        "no_op",
        "fifo",
        "constructive",
        "repaired",
    ]
    assert status["reproduction_fidelity"]["paper_adaptation_notes"]["issue"].endswith(
        "/issues/87"
    )
    assert status["selection"]["final_score"]["target_gap_summary"]["target_001"]
    assert (solution_dir / "debug" / "orbit_candidates.json").exists()
    assert (solution_dir / "debug" / "visibility_windows.json").exists()
    assert (solution_dir / "debug" / "selection_rounds.json").exists()
    assert (solution_dir / "debug" / "scheduling_decisions.json").exists()
    assert (solution_dir / "debug" / "scheduling_rejections.json").exists()
    assert (solution_dir / "debug" / "local_validation.json").exists()
    assert (solution_dir / "debug" / "repair_steps.json").exists()
    assert (solution_dir / "debug" / "scheduling_summary.json").exists()
    assert (solution_dir / "debug" / "baseline_summary.json").exists()
    assert (solution_dir / "debug" / "mode_comparison.json").exists()
    assert (solution_dir / "debug" / "adaptation_notes.json").exists()
    baseline = json.loads(
        (solution_dir / "debug" / "baseline_summary.json").read_text(encoding="utf-8")
    )
    assert baseline == status["baseline_evidence"]


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
