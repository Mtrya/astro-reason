from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess

import brahe
import numpy as np
import pytest

from src import rgt as rgt_module
from src import solution as solution_module
from src.case_io import (
    AttitudeModel,
    ResourceModel,
    RevisitCase,
    SatelliteModel,
    SensorModel,
    Target,
    load_case,
)
from src.coverage import (
    CoarseVisibilityHint,
    CoverageConfig,
    CoverageSummary,
    RaanCandidate,
    VisibilitySample,
    VisibilityWindow,
    build_coverage_summary,
    coarse_hints_from_samples,
    expand_raan_candidates,
    geometry_sample_from_state,
    group_visible_samples,
)
from src.rgt import (
    ClosureScore,
    EARTH_RADIUS_M,
    J2Rates,
    RgtTemplate,
    SIDEREAL_DAY_SEC,
    RgtSearchConfig,
    analytical_brouwer_closure_score,
    brouwer_j2_state_eci,
    circular_state_eci,
    closure_score_from_geocentric,
    enumerate_seeds,
    numerical_closure_score_at_duration,
    search_rgt_templates,
    solve_rgt_semimajor_axis,
)
from src.selection import (
    SelectedCandidate,
    SelectionSummary,
    TargetAssignment,
    satellites_required_for_target,
    select_candidates,
)
from src.solution import (
    ObservationAction,
    SatellitePlan,
    SchedulingConfig,
    build_opportunities,
    build_solution,
    evaluate_phased_candidate_target_quality,
    generate_phased_satellites,
    repair_selection_with_phased_opportunities,
    select_gap_aware_actions,
    validate_solution_locally,
)
from src.time_utils import datetime_to_epoch


REPO_ROOT = Path(__file__).resolve().parents[4]
CASE_DIR = REPO_ROOT / "benchmarks/revisit_constellation/dataset/cases/test/case_0001"
SOLVER_DIR = REPO_ROOT / "solvers/revisit_constellation/j2_rgt_set_cover"


def _synthetic_target(target_id: str, revisit_hours: float = 8.0) -> Target:
    return Target(
        target_id=target_id,
        name=target_id,
        latitude_deg=0.0,
        longitude_deg=0.0,
        altitude_m=0.0,
        expected_revisit_period_hours=revisit_hours,
        min_elevation_deg=10.0,
        max_slant_range_m=1_000_000.0,
        min_duration_sec=30.0,
        ecef_position_m=(0.0, 0.0, 0.0),
    )


def _synthetic_case(
    target_ids: list[str],
    *,
    revisit_hours: float = 8.0,
    max_num_satellites: int = 24,
) -> RevisitCase:
    return RevisitCase(
        case_dir=Path("."),
        horizon_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        horizon_end=datetime(2025, 1, 3, tzinfo=timezone.utc),
        satellite_model=SatelliteModel(
            sensor=SensorModel(
                max_off_nadir_angle_deg=30.0,
                max_range_m=1_000_000.0,
                obs_discharge_rate_w=100.0,
            ),
            resource_model=ResourceModel(
                battery_capacity_wh=2000.0,
                initial_battery_wh=1600.0,
                idle_discharge_rate_w=5.0,
                sunlight_charge_rate_w=100.0,
            ),
            attitude_model=AttitudeModel(
                max_slew_velocity_deg_per_sec=1.0,
                max_slew_acceleration_deg_per_sec2=0.45,
                settling_time_sec=10.0,
                maneuver_discharge_rate_w=90.0,
            ),
            min_altitude_m=500_000.0,
            max_altitude_m=900_000.0,
        ),
        max_num_satellites=max_num_satellites,
        targets={
            target_id: _synthetic_target(target_id, revisit_hours)
            for target_id in target_ids
        },
    )


def _synthetic_candidate(
    candidate_id: str,
    *,
    repeat_hours: float,
    closure_error_m: float = 0.0,
) -> RaanCandidate:
    return RaanCandidate(
        candidate_id=candidate_id,
        template_id=f"{candidate_id}_template",
        repeat_days=max(1, round(repeat_hours / 24.0)),
        revolutions=15,
        inclination_deg=97.8,
        semi_major_axis_m=7_000_000.0,
        altitude_m=621_863.0,
        eccentricity=0.0,
        argument_of_perigee_deg=0.0,
        mean_anomaly_deg=0.0,
        repeat_period_sec=repeat_hours * 3600.0,
        raan_deg=0.0,
        template_closure_error_m=closure_error_m,
    )


def _synthetic_template(
    template_id: str,
    surface_error_m: float,
    *,
    repeat_days: int = 1,
    revolutions: int = 15,
    inclination_deg: float = 97.8,
) -> RgtTemplate:
    return RgtTemplate(
        template_id=template_id,
        repeat_days=repeat_days,
        revolutions=revolutions,
        inclination_deg=inclination_deg,
        semi_major_axis_m=EARTH_RADIUS_M + 600_000.0,
        altitude_m=600_000.0,
        eccentricity=0.0,
        raan_deg=0.0,
        argument_of_perigee_deg=0.0,
        mean_anomaly_deg=0.0,
        repeat_period_sec=repeat_days * SIDEREAL_DAY_SEC,
        state_eci_m_mps=(EARTH_RADIUS_M + 600_000.0, 0.0, 0.0, 0.0, 7_500.0, 0.0),
        rates=J2Rates(0.0, 0.0, 0.0, 0.0),
        closure=ClosureScore(
            longitude_delta_deg=0.0,
            latitude_delta_deg=0.0,
            surface_error_m=surface_error_m,
            start_longitude_deg=0.0,
            start_latitude_deg=0.0,
            end_longitude_deg=0.0,
            end_latitude_deg=0.0,
        ),
        accepted=True,
        rejection_reason=None,
        iterations=1,
        correction_iterations=1,
    )


def _synthetic_coverage(
    *,
    candidates: list[RaanCandidate],
    candidate_to_targets: dict[str, list[str]],
    windows: list[VisibilityWindow] | None = None,
    hints: list[CoarseVisibilityHint] | None = None,
) -> CoverageSummary:
    target_to_candidates: dict[str, list[str]] = {}
    for candidate_id, target_ids in candidate_to_targets.items():
        for target_id in target_ids:
            target_to_candidates.setdefault(target_id, []).append(candidate_id)
    return CoverageSummary(
        candidates=candidates,
        windows=[] if windows is None else windows,
        hints=[] if hints is None else hints,
        target_to_candidates={
            target_id: sorted(candidate_ids)
            for target_id, candidate_ids in sorted(target_to_candidates.items())
        },
        candidate_to_targets={
            candidate.candidate_id: sorted(
                candidate_to_targets.get(candidate.candidate_id, [])
            )
            for candidate in candidates
        },
        uncovered_target_ids=[],
        config=CoverageConfig(),
        sample_offset_count=0,
    )


def _synthetic_window(
    candidate: RaanCandidate,
    target_id: str,
    midpoint_hours: float,
    *,
    duration_sec: float = 120.0,
) -> VisibilityWindow:
    midpoint_sec = midpoint_hours * 3600.0
    start_sec = midpoint_sec - (duration_sec / 2.0)
    end_sec = midpoint_sec + (duration_sec / 2.0)
    sample = VisibilitySample(
        offset_sec=midpoint_sec,
        elevation_deg=45.0,
        slant_range_m=500_000.0,
        off_nadir_deg=5.0,
        visible=True,
    )
    return VisibilityWindow(
        window_id=f"{candidate.candidate_id}__{target_id}__{midpoint_hours:.3f}",
        candidate_id=candidate.candidate_id,
        template_id=candidate.template_id,
        target_id=target_id,
        start_offset_sec=start_sec,
        end_offset_sec=end_sec,
        midpoint_offset_sec=midpoint_sec,
        duration_sec=duration_sec,
        max_elevation_deg=45.0,
        min_slant_range_m=500_000.0,
        min_off_nadir_deg=5.0,
        sample_count=1,
        samples=(sample,),
    )


def test_load_case_rejects_bool_integer(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "assets.json").write_text(
        json.dumps(
            {
                "max_num_satellites": True,
                "satellite_model": {
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
                    "max_altitude_m": 900000.0,
                },
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "mission.json").write_text(
        json.dumps(
            {
                "horizon_start": "2025-07-17T12:00:00Z",
                "horizon_end": "2025-07-19T12:00:00Z",
                "targets": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="max_num_satellites"):
        load_case(case_dir)


def test_load_case_rejects_inverted_horizon(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    assets = json.loads((CASE_DIR / "assets.json").read_text(encoding="utf-8"))
    mission = json.loads((CASE_DIR / "mission.json").read_text(encoding="utf-8"))
    mission["horizon_end"] = mission["horizon_start"]
    (case_dir / "assets.json").write_text(json.dumps(assets), encoding="utf-8")
    (case_dir / "mission.json").write_text(json.dumps(mission), encoding="utf-8")

    with pytest.raises(ValueError, match="horizon_end must be after horizon_start"):
        load_case(case_dir)


def test_datetime_to_epoch_rejects_non_utc_datetime() -> None:
    non_utc = datetime(2025, 1, 1, tzinfo=timezone(timedelta(hours=8)))

    with pytest.raises(ValueError, match="datetime must be UTC"):
        datetime_to_epoch(non_utc)


def test_circular_state_respects_altitude_bounds() -> None:
    case = load_case(CASE_DIR)
    semi_major_axis, iterations, rejection = solve_rgt_semimajor_axis(
        repeat_days=1,
        revolutions=14,
        inclination_deg=53.0,
        min_altitude_m=case.satellite_model.min_altitude_m,
        max_altitude_m=case.satellite_model.max_altitude_m,
    )

    assert rejection is None
    assert iterations > 0
    assert semi_major_axis is not None
    altitude_m = semi_major_axis - EARTH_RADIUS_M
    assert case.satellite_model.min_altitude_m <= altitude_m <= case.satellite_model.max_altitude_m
    assert len(circular_state_eci(semi_major_axis, 53.0)) == 6


def test_closure_score_wraps_longitude() -> None:
    score = closure_score_from_geocentric(179.0, 0.0, -179.0, 0.0)

    assert score.longitude_delta_deg == pytest.approx(2.0)
    assert score.surface_error_m < 250_000.0


def test_seed_enumeration_is_deterministic_for_shuffled_inclinations() -> None:
    left = RgtSearchConfig(
        max_repeat_days=1,
        min_revolutions_per_day=14,
        max_revolutions_per_day=15,
        inclinations_deg=(97.8, 53.0, 63.4),
    )
    right = RgtSearchConfig(
        max_repeat_days=1,
        min_revolutions_per_day=14,
        max_revolutions_per_day=15,
        inclinations_deg=(63.4, 97.8, 53.0),
    )

    assert enumerate_seeds(left) == enumerate_seeds(right)


def test_brouwer_j2_closure_agrees_with_numerical_j2_for_seed() -> None:
    case = load_case(CASE_DIR)
    semi_major_axis, _, rejection = solve_rgt_semimajor_axis(
        repeat_days=1,
        revolutions=15,
        inclination_deg=97.8,
        min_altitude_m=case.satellite_model.min_altitude_m,
        max_altitude_m=case.satellite_model.max_altitude_m,
    )
    assert rejection is None
    assert semi_major_axis is not None

    analytical_closure, analytical_state = analytical_brouwer_closure_score(
        case,
        semi_major_axis_m=semi_major_axis,
        inclination_deg=97.8,
        eccentricity=0.0,
        mean_anomaly_deg=0.0,
        duration_sec=SIDEREAL_DAY_SEC,
    )
    numerical_closure = numerical_closure_score_at_duration(
        case,
        analytical_state,
        duration_sec=SIDEREAL_DAY_SEC,
    )

    assert abs(
        analytical_closure.surface_error_m - numerical_closure.surface_error_m
    ) < 5_000.0


def test_j2_search_accepts_analytically_closed_template() -> None:
    case = load_case(CASE_DIR)
    config = RgtSearchConfig(
        max_repeat_days=1,
        min_revolutions_per_day=15,
        max_revolutions_per_day=15,
        inclinations_deg=(97.8,),
        max_templates=1,
        closure_tolerance_m=5_000.0,
        refinement_iterations=8,
    )

    result = search_rgt_templates(case, config)

    assert len(result.accepted_templates) == 1
    template = result.accepted_templates[0]
    assert template.closure is not None
    assert template.closure.surface_error_m <= config.closure_tolerance_m
    assert template.rejection_reason is None


def test_j2_search_selects_best_templates_after_all_seeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = load_case(CASE_DIR)
    config = RgtSearchConfig(
        max_repeat_days=1,
        min_revolutions_per_day=11,
        max_revolutions_per_day=13,
        inclinations_deg=(30.0, 40.0),
        max_templates=2,
        closure_tolerance_m=5_000.0,
        refinement_iterations=1,
    )
    errors_by_seed = {
        (1, 11, 30.0): 4000.0,
        (1, 11, 40.0): 3000.0,
        (1, 12, 30.0): 20.0,
        (1, 12, 40.0): 10.0,
        (1, 13, 30.0): 2000.0,
        (1, 13, 40.0): 1000.0,
    }
    calls: list[tuple[int, int, float]] = []

    def fake_construct_template(
        _case: RevisitCase,
        _config: RgtSearchConfig,
        *,
        repeat_days: int,
        revolutions: int,
        inclination_deg: float,
    ) -> RgtTemplate:
        key = (repeat_days, revolutions, inclination_deg)
        calls.append(key)
        return _synthetic_template(
            f"tpl_{repeat_days}_{revolutions}_{inclination_deg:g}",
            errors_by_seed[key],
            repeat_days=repeat_days,
            revolutions=revolutions,
            inclination_deg=inclination_deg,
        )

    monkeypatch.setattr(rgt_module, "construct_template", fake_construct_template)

    result = search_rgt_templates(case, config)

    assert calls == enumerate_seeds(config)
    assert result.considered_seed_count == len(calls)
    assert [item.closure.surface_error_m for item in result.accepted_templates] == [
        10.0,
        20.0,
    ]


def test_geometry_visibility_accepts_overhead_and_rejects_range() -> None:
    case = load_case(CASE_DIR)
    target = case.targets["target_002"]
    start_epoch = datetime_to_epoch(case.horizon_start)
    target_ecef = np.asarray(target.ecef_position_m, dtype=float)
    radial = target_ecef / np.linalg.norm(target_ecef)

    overhead_ecef = target_ecef + radial * 600_000.0
    overhead_eci = np.asarray(
        brahe.position_ecef_to_eci(start_epoch, overhead_ecef),
        dtype=float,
    )
    overhead_sample = geometry_sample_from_state(
        case=case,
        target=target,
        state_eci_m_mps=tuple(float(value) for value in (*overhead_eci, 0.0, 0.0, 0.0)),
        instant=case.horizon_start,
        offset_sec=0.0,
    )

    assert overhead_sample.visible
    assert overhead_sample.elevation_deg > 89.0
    assert overhead_sample.off_nadir_deg < 1.0

    far_ecef = target_ecef + radial * 2_000_000.0
    far_eci = np.asarray(brahe.position_ecef_to_eci(start_epoch, far_ecef), dtype=float)
    far_sample = geometry_sample_from_state(
        case=case,
        target=target,
        state_eci_m_mps=tuple(float(value) for value in (*far_eci, 0.0, 0.0, 0.0)),
        instant=case.horizon_start,
        offset_sec=0.0,
    )

    assert not far_sample.visible
    assert far_sample.slant_range_m > case.satellite_model.sensor.max_range_m


def test_group_visible_samples_respects_min_duration() -> None:
    samples = [
        VisibilitySample(
            offset_sec=float(index * 10),
            elevation_deg=40.0,
            slant_range_m=500_000.0,
            off_nadir_deg=5.0,
            visible=visible,
        )
        for index, visible in enumerate([True, True, False, True, True, True])
    ]

    windows = group_visible_samples(
        candidate_id="candidate",
        template_id="template",
        target_id="target",
        repeat_period_sec=60.0,
        sample_step_sec=10.0,
        min_duration_sec=25.0,
        samples=samples,
        keep_samples_per_window=2,
    )

    assert [window.window_id for window in windows] == ["candidate__target__win0000"]
    assert windows[0].start_offset_sec == pytest.approx(30.0)
    assert windows[0].end_offset_sec == pytest.approx(60.0)
    assert windows[0].duration_sec == pytest.approx(30.0)
    assert windows[0].sample_count == 3
    assert [sample.offset_sec for sample in windows[0].samples] == [30.0, 50.0]


def test_template_to_raan_candidate_expansion_is_deterministic() -> None:
    case = load_case(CASE_DIR)
    config = RgtSearchConfig(
        max_repeat_days=1,
        min_revolutions_per_day=15,
        max_revolutions_per_day=15,
        inclinations_deg=(97.8,),
        max_templates=1,
        closure_tolerance_m=5_000.0,
        refinement_iterations=8,
    )
    result = search_rgt_templates(case, config)

    candidates = expand_raan_candidates(
        result.accepted_templates,
        CoverageConfig(raan_count=4, raan_start_deg=15.0),
    )

    assert [candidate.raan_deg for candidate in candidates] == [
        15.0,
        105.0,
        195.0,
        285.0,
    ]
    assert [candidate.candidate_id for candidate in candidates] == sorted(
        candidate.candidate_id for candidate in candidates
    )
    assert {candidate.template_id for candidate in candidates} == {
        result.accepted_templates[0].template_id
    }


def test_serial_and_parallel_coverage_summaries_match() -> None:
    case = load_case(CASE_DIR)
    search_config = RgtSearchConfig(
        max_repeat_days=1,
        min_revolutions_per_day=15,
        max_revolutions_per_day=15,
        inclinations_deg=(97.8,),
        max_templates=1,
        closure_tolerance_m=5_000.0,
        refinement_iterations=8,
    )
    result = search_rgt_templates(case, search_config)
    base_config = CoverageConfig(
        raan_count=3,
        sample_step_sec=3600.0,
        keep_samples_per_window=2,
        worker_count=1,
    )

    serial = build_coverage_summary(case, result.accepted_templates, base_config)
    parallel = build_coverage_summary(
        case,
        result.accepted_templates,
        CoverageConfig(
            raan_count=base_config.raan_count,
            sample_step_sec=base_config.sample_step_sec,
            keep_samples_per_window=base_config.keep_samples_per_window,
            worker_count=2,
        ),
    )

    assert serial.target_to_candidates == parallel.target_to_candidates
    assert serial.candidate_to_targets == parallel.candidate_to_targets
    assert serial.uncovered_target_ids == parallel.uncovered_target_ids
    assert [window.as_dict() for window in serial.windows] == [
        window.as_dict() for window in parallel.windows
    ]


def test_coverage_indexes_and_uncovered_summary_are_stable() -> None:
    case = load_case(CASE_DIR)
    search_config = RgtSearchConfig(
        max_repeat_days=1,
        min_revolutions_per_day=15,
        max_revolutions_per_day=15,
        inclinations_deg=(97.8,),
        max_templates=1,
        closure_tolerance_m=5_000.0,
        refinement_iterations=8,
    )
    result = search_rgt_templates(case, search_config)

    summary = build_coverage_summary(
        case,
        result.accepted_templates,
        CoverageConfig(raan_count=2, sample_step_sec=7200.0, worker_count=1),
    )

    assert [candidate.candidate_id for candidate in summary.candidates] == sorted(
        candidate.candidate_id for candidate in summary.candidates
    )
    assert summary.uncovered_target_ids == sorted(summary.uncovered_target_ids)
    for candidate_ids in summary.target_to_candidates.values():
        assert candidate_ids == sorted(candidate_ids)
    for target_ids in summary.candidate_to_targets.values():
        assert target_ids == sorted(target_ids)
    assert summary.as_status_dict()["candidate_count"] == 2


def test_satellite_cost_formula_handles_repeat_period_and_thresholds() -> None:
    one_day = _synthetic_candidate("one_day", repeat_hours=24.0)
    two_day = _synthetic_candidate("two_day", repeat_hours=48.0)

    assert satellites_required_for_target(one_day, _synthetic_target("t1", 8.0)) == 3
    assert satellites_required_for_target(two_day, _synthetic_target("t1", 8.0)) == 6
    assert satellites_required_for_target(one_day, _synthetic_target("t1", 6.0)) == 4
    assert satellites_required_for_target(two_day, _synthetic_target("t1", 6.0)) == 8


def test_greedy_set_cover_prefers_lower_cost_full_cover() -> None:
    case = _synthetic_case(["t1", "t2"], revisit_hours=8.0, max_num_satellites=8)
    low_cost = _synthetic_candidate("a_low_cost", repeat_hours=24.0)
    high_cost = _synthetic_candidate("b_high_cost", repeat_hours=48.0)
    summary = _synthetic_coverage(
        candidates=[high_cost, low_cost],
        candidate_to_targets={
            high_cost.candidate_id: ["t1", "t2"],
            low_cost.candidate_id: ["t1", "t2"],
        },
    )

    selection = select_candidates(case, summary)

    assert selection.all_targets_covered
    assert selection.total_required_satellites == 3
    assert [item.candidate.candidate_id for item in selection.selected_candidates] == [
        low_cost.candidate_id
    ]
    assert set(selection.target_assignments) == {"t1", "t2"}


def test_set_cover_ties_are_stable_under_shuffled_candidates() -> None:
    case = _synthetic_case(["t1", "t2"], revisit_hours=8.0, max_num_satellites=8)
    first = _synthetic_candidate("a_first", repeat_hours=24.0, closure_error_m=10.0)
    second = _synthetic_candidate("b_second", repeat_hours=24.0, closure_error_m=10.0)
    candidate_to_targets = {
        first.candidate_id: ["t1", "t2"],
        second.candidate_id: ["t1", "t2"],
    }

    left = select_candidates(
        case,
        _synthetic_coverage(
            candidates=[second, first],
            candidate_to_targets=candidate_to_targets,
        ),
    )
    right = select_candidates(
        case,
        _synthetic_coverage(
            candidates=[first, second],
            candidate_to_targets=candidate_to_targets,
        ),
    )

    assert [item.candidate.candidate_id for item in left.selected_candidates] == [
        first.candidate_id
    ]
    assert [item.candidate.candidate_id for item in right.selected_candidates] == [
        first.candidate_id
    ]


def test_budget_failure_reports_uncovered_targets_and_near_miss() -> None:
    case = _synthetic_case(["t1"], revisit_hours=8.0, max_num_satellites=2)
    candidate = _synthetic_candidate("candidate", repeat_hours=24.0)
    summary = _synthetic_coverage(
        candidates=[candidate],
        candidate_to_targets={candidate.candidate_id: ["t1"]},
    )

    selection = select_candidates(case, summary)

    assert not selection.all_targets_covered
    assert selection.uncovered_target_ids == ["t1"]
    assert selection.total_required_satellites == 0
    assert selection.budget_near_misses[0].candidate_id == candidate.candidate_id
    assert selection.budget_near_misses[0].satellite_over_budget == 1


def test_local_improvement_removes_redundant_selected_candidates() -> None:
    case = _synthetic_case(["t1", "t2", "t3"], revisit_hours=8.0, max_num_satellites=10)
    fast_partial = _synthetic_candidate("a_fast_partial", repeat_hours=8.0)
    full_cover = _synthetic_candidate("b_full_cover", repeat_hours=24.0)
    summary = _synthetic_coverage(
        candidates=[full_cover, fast_partial],
        candidate_to_targets={
            fast_partial.candidate_id: ["t1", "t2"],
            full_cover.candidate_id: ["t1", "t2", "t3"],
        },
    )

    selection = select_candidates(case, summary)

    assert selection.all_targets_covered
    assert selection.total_required_satellites == 3
    assert [item.candidate.candidate_id for item in selection.selected_candidates] == [
        full_cover.candidate_id
    ]
    assert set(selection.target_assignments) == {"t1", "t2", "t3"}


def test_coarse_hints_store_offsets_and_margins_without_certifying_windows() -> None:
    case = _synthetic_case(["t1"], revisit_hours=8.0, max_num_satellites=6)
    target = case.targets["t1"]
    samples = [
        VisibilitySample(
            offset_sec=120.0,
            elevation_deg=30.0,
            slant_range_m=800_000.0,
            off_nadir_deg=12.0,
            visible=True,
        ),
        VisibilitySample(
            offset_sec=240.0,
            elevation_deg=0.0,
            slant_range_m=900_000.0,
            off_nadir_deg=40.0,
            visible=False,
        ),
    ]

    hints = coarse_hints_from_samples(
        case=case,
        candidate_id="candidate",
        template_id="template",
        target=target,
        repeat_period_sec=86_400.0,
        sample_step_sec=300.0,
        samples=samples,
    )

    assert len(hints) == 1
    assert hints[0].offset_sec == pytest.approx(120.0)
    assert hints[0].source == "coarse_visible_sample"
    assert hints[0].elevation_margin_deg == pytest.approx(20.0)
    assert hints[0].range_margin_m == pytest.approx(200_000.0)
    assert hints[0].min_margin == pytest.approx(18.0)


def test_phased_opportunity_quality_refines_coarse_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        solution_module,
        "_action_geometry_valid",
        lambda **_: True,
    )
    case = _synthetic_case(["t1"], revisit_hours=8.0, max_num_satellites=6)
    candidate = _synthetic_candidate("candidate", repeat_hours=24.0)
    coverage = _synthetic_coverage(
        candidates=[candidate],
        candidate_to_targets={candidate.candidate_id: ["t1"]},
        windows=[
            _synthetic_window(candidate, "t1", 1.0),
            _synthetic_window(candidate, "t1", 25.0),
        ],
    )

    quality = evaluate_phased_candidate_target_quality(
        case=case,
        coverage=coverage,
        candidate_id=candidate.candidate_id,
        target_id="t1",
    )

    assert quality.required_satellites == 3
    assert quality.opportunity_count >= 6
    assert quality.max_gap_hours <= 8.0
    assert quality.coarse_hint_count == 2
    assert quality.refined_opportunity_count == quality.opportunity_count


def test_refinement_rejects_coarse_hint_when_final_geometry_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        solution_module,
        "_action_geometry_valid",
        lambda **_: False,
    )
    case = _synthetic_case(["t1"], revisit_hours=8.0, max_num_satellites=6)
    candidate = _synthetic_candidate("candidate", repeat_hours=24.0)
    coverage = _synthetic_coverage(
        candidates=[candidate],
        candidate_to_targets={candidate.candidate_id: ["t1"]},
        windows=[_synthetic_window(candidate, "t1", 1.0)],
    )

    quality = evaluate_phased_candidate_target_quality(
        case=case,
        coverage=coverage,
        candidate_id=candidate.candidate_id,
        target_id="t1",
    )

    assert quality.coarse_hint_count == 1
    assert quality.opportunity_count == 0
    assert quality.rejection_reasons == {"no_valid_interval": 6}


def test_selection_repair_uses_remaining_budget_for_high_gap_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        solution_module,
        "_action_geometry_valid",
        lambda **_: True,
    )
    case = _synthetic_case(["t1", "t2"], revisit_hours=8.0, max_num_satellites=6)
    bad = _synthetic_candidate("a_bad_full_cover", repeat_hours=24.0)
    good = _synthetic_candidate("b_good_t1", repeat_hours=24.0)
    coverage = _synthetic_coverage(
        candidates=[bad, good],
        candidate_to_targets={
            bad.candidate_id: ["t1", "t2"],
            good.candidate_id: ["t1"],
        },
        windows=[
            _synthetic_window(bad, "t2", 1.0),
            _synthetic_window(bad, "t2", 25.0),
            _synthetic_window(good, "t1", 1.0),
            _synthetic_window(good, "t1", 25.0),
        ],
    )
    selection = select_candidates(case, coverage)
    initial_gaps = {
        "t1": {
            "max_revisit_gap_hours": 24.0,
            "expected_revisit_period_hours": 8.0,
        },
        "t2": {
            "max_revisit_gap_hours": 8.0,
            "expected_revisit_period_hours": 8.0,
        },
    }

    repair = repair_selection_with_phased_opportunities(
        case=case,
        coverage=coverage,
        selection=selection,
        initial_gap_summary=initial_gaps,
        config=SchedulingConfig(min_gap_improvement_sec=60.0),
    )

    assert repair.changed
    assert repair.selection.total_required_satellites == 6
    assert repair.selection.target_assignments["t1"].candidate_id == good.candidate_id
    assert repair.selection.target_assignments["t2"].candidate_id == bad.candidate_id
    assert repair.rounds[0].improved_target_ids == ("t1",)
    assert repair.as_debug_dict()["target_diagnostics"]["t1"]["chosen_candidate_id"] == (
        good.candidate_id
    )


def test_selection_repair_replaces_failed_candidate_instead_of_adding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        solution_module,
        "_action_geometry_valid",
        lambda **_: True,
    )
    case = _synthetic_case(["t1", "t2"], revisit_hours=8.0, max_num_satellites=6)
    bad = _synthetic_candidate("a_bad_initial", repeat_hours=24.0, closure_error_m=0.0)
    good = _synthetic_candidate("b_good_replacement", repeat_hours=24.0, closure_error_m=10.0)
    coverage = _synthetic_coverage(
        candidates=[bad, good],
        candidate_to_targets={
            bad.candidate_id: ["t1", "t2"],
            good.candidate_id: ["t1", "t2"],
        },
        windows=[
            _synthetic_window(bad, "t1", 1.0),
            _synthetic_window(bad, "t1", 25.0),
            _synthetic_window(good, "t1", 1.0),
            _synthetic_window(good, "t1", 25.0),
            _synthetic_window(good, "t2", 2.0),
            _synthetic_window(good, "t2", 26.0),
        ],
    )
    selection = select_candidates(case, coverage)
    initial_gaps = {
        "t1": {
            "max_revisit_gap_hours": 8.0,
            "expected_revisit_period_hours": 8.0,
        },
        "t2": {
            "max_revisit_gap_hours": 24.0,
            "expected_revisit_period_hours": 8.0,
        },
    }

    assert [item.candidate.candidate_id for item in selection.selected_candidates] == [
        bad.candidate_id
    ]

    repair = repair_selection_with_phased_opportunities(
        case=case,
        coverage=coverage,
        selection=selection,
        initial_gap_summary=initial_gaps,
        config=SchedulingConfig(),
    )

    assert [item.candidate.candidate_id for item in repair.selection.selected_candidates] == [
        good.candidate_id
    ]
    assert repair.selection.total_required_satellites == 3
    assert repair.rounds[0].added_satellites == 0
    assert repair.as_debug_dict()["refined_repacking_summary"]["selected_candidate_ids"] == [
        good.candidate_id
    ]


def test_selection_repair_keeps_original_when_repack_drops_assignments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        solution_module,
        "_action_geometry_valid",
        lambda **_: True,
    )
    case = _synthetic_case(["t1", "t2"], revisit_hours=8.0, max_num_satellites=3)
    original = _synthetic_candidate("b_original_t2_only", repeat_hours=24.0, closure_error_m=10.0)
    replacement = _synthetic_candidate("a_replacement_t1_only", repeat_hours=24.0)
    coverage = _synthetic_coverage(
        candidates=[original, replacement],
        candidate_to_targets={
            original.candidate_id: ["t1", "t2"],
            replacement.candidate_id: ["t1"],
        },
        windows=[
            _synthetic_window(original, "t2", 1.0),
            _synthetic_window(original, "t2", 25.0),
            _synthetic_window(replacement, "t1", 1.0),
            _synthetic_window(replacement, "t1", 25.0),
        ],
    )
    selection = select_candidates(case, coverage)
    initial_gaps = {
        "t1": {
            "max_revisit_gap_hours": 24.0,
            "expected_revisit_period_hours": 8.0,
        },
        "t2": {
            "max_revisit_gap_hours": 8.0,
            "expected_revisit_period_hours": 8.0,
        },
    }

    repair = repair_selection_with_phased_opportunities(
        case=case,
        coverage=coverage,
        selection=selection,
        initial_gap_summary=initial_gaps,
        config=SchedulingConfig(),
    )

    assert not repair.changed
    assert repair.selection.as_debug_dict() == selection.as_debug_dict()
    assert repair.blocker == "refined_repack_would_reduce_assignment_coverage"
    assert repair.as_debug_dict()["refined_repacking_summary"]["accepted"] is False


def test_selection_repair_ties_are_deterministic_under_shuffled_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        solution_module,
        "_action_geometry_valid",
        lambda **_: True,
    )
    case = _synthetic_case(["t1", "t2"], revisit_hours=8.0, max_num_satellites=6)
    bad = _synthetic_candidate("z_bad_full_cover", repeat_hours=24.0)
    first = _synthetic_candidate("a_good_t1", repeat_hours=24.0)
    second = _synthetic_candidate("b_good_t1", repeat_hours=24.0)
    candidate_to_targets = {
        bad.candidate_id: ["t1", "t2"],
        first.candidate_id: ["t1"],
        second.candidate_id: ["t1"],
    }
    windows = [
        _synthetic_window(bad, "t2", 1.0),
        _synthetic_window(bad, "t2", 25.0),
        _synthetic_window(first, "t1", 1.0),
        _synthetic_window(first, "t1", 25.0),
        _synthetic_window(second, "t1", 1.0),
        _synthetic_window(second, "t1", 25.0),
    ]
    initial_gaps = {
        "t1": {
            "max_revisit_gap_hours": 24.0,
            "expected_revisit_period_hours": 8.0,
        },
        "t2": {
            "max_revisit_gap_hours": 8.0,
            "expected_revisit_period_hours": 8.0,
        },
    }

    left_selection = select_candidates(
        case,
        _synthetic_coverage(
            candidates=[bad, second, first],
            candidate_to_targets=candidate_to_targets,
            windows=windows,
        ),
    )
    right_selection = select_candidates(
        case,
        _synthetic_coverage(
            candidates=[first, bad, second],
            candidate_to_targets=candidate_to_targets,
            windows=windows,
        ),
    )
    left = repair_selection_with_phased_opportunities(
        case=case,
        coverage=_synthetic_coverage(
            candidates=[bad, second, first],
            candidate_to_targets=candidate_to_targets,
            windows=windows,
        ),
        selection=left_selection,
        initial_gap_summary=initial_gaps,
        config=SchedulingConfig(),
    )
    right = repair_selection_with_phased_opportunities(
        case=case,
        coverage=_synthetic_coverage(
            candidates=[first, bad, second],
            candidate_to_targets=candidate_to_targets,
            windows=windows,
        ),
        selection=right_selection,
        initial_gap_summary=initial_gaps,
        config=SchedulingConfig(),
    )

    assert left.selection.target_assignments["t1"].candidate_id == first.candidate_id
    assert right.selection.target_assignments["t1"].candidate_id == first.candidate_id


def test_selection_repair_rankings_match_across_worker_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        solution_module,
        "_action_geometry_valid",
        lambda **_: True,
    )
    case = _synthetic_case(["t1", "t2"], revisit_hours=8.0, max_num_satellites=6)
    bad = _synthetic_candidate("a_bad_full_cover", repeat_hours=24.0)
    good = _synthetic_candidate("b_good_t1", repeat_hours=24.0)
    coverage = _synthetic_coverage(
        candidates=[bad, good],
        candidate_to_targets={
            bad.candidate_id: ["t1", "t2"],
            good.candidate_id: ["t1"],
        },
        windows=[
            _synthetic_window(good, "t1", 1.0),
            _synthetic_window(good, "t1", 25.0),
        ],
    )
    selection = select_candidates(case, coverage)
    initial_gaps = {
        "t1": {
            "max_revisit_gap_hours": 24.0,
            "expected_revisit_period_hours": 8.0,
        },
        "t2": {
            "max_revisit_gap_hours": 8.0,
            "expected_revisit_period_hours": 8.0,
        },
    }

    serial = repair_selection_with_phased_opportunities(
        case=case,
        coverage=coverage,
        selection=selection,
        initial_gap_summary=initial_gaps,
        config=SchedulingConfig(repair_worker_count=1),
    )
    parallel = repair_selection_with_phased_opportunities(
        case=case,
        coverage=coverage,
        selection=selection,
        initial_gap_summary=initial_gaps,
        config=SchedulingConfig(repair_worker_count=2),
    )

    assert serial.selection.as_debug_dict() == parallel.selection.as_debug_dict()
    assert [item.as_dict() for item in serial.rounds] == [
        item.as_dict() for item in parallel.rounds
    ]


def test_equal_phasing_produces_expected_spacing_for_repeat_periods() -> None:
    one_day_case = _synthetic_case(["t1"], revisit_hours=8.0, max_num_satellites=12)
    one_day_candidate = _synthetic_candidate("one_day", repeat_hours=24.0)
    one_day_selection = select_candidates(
        one_day_case,
        _synthetic_coverage(
            candidates=[one_day_candidate],
            candidate_to_targets={one_day_candidate.candidate_id: ["t1"]},
        ),
    )
    one_day_satellites = generate_phased_satellites(one_day_case, one_day_selection)

    assert [satellite.phase_offset_sec for satellite in one_day_satellites] == [
        0.0,
        pytest.approx(8.0 * 3600.0),
        pytest.approx(16.0 * 3600.0),
    ]

    two_day_case = _synthetic_case(["t1"], revisit_hours=8.0, max_num_satellites=12)
    two_day_candidate = _synthetic_candidate("two_day", repeat_hours=48.0)
    two_day_selection = select_candidates(
        two_day_case,
        _synthetic_coverage(
            candidates=[two_day_candidate],
            candidate_to_targets={two_day_candidate.candidate_id: ["t1"]},
        ),
    )
    two_day_satellites = generate_phased_satellites(two_day_case, two_day_selection)

    assert len(two_day_satellites) == 6
    assert two_day_satellites[1].phase_offset_sec == pytest.approx(8.0 * 3600.0)
    assert two_day_satellites[-1].phase_offset_sec == pytest.approx(40.0 * 3600.0)


def test_equal_phasing_uses_rotating_frame_time_shift() -> None:
    case = _synthetic_case(["t1"], revisit_hours=8.0, max_num_satellites=12)
    candidate = _synthetic_candidate("candidate", repeat_hours=24.0)
    selection = select_candidates(
        case,
        _synthetic_coverage(
            candidates=[candidate],
            candidate_to_targets={candidate.candidate_id: ["t1"]},
        ),
    )
    satellite = generate_phased_satellites(case, selection)[1]
    future_epoch = datetime_to_epoch(
        case.horizon_start + timedelta(seconds=satellite.phase_offset_sec)
    )
    start_epoch = datetime_to_epoch(case.horizon_start)
    future_base_state = np.asarray(
        brouwer_j2_state_eci(
            candidate.semi_major_axis_m,
            candidate.inclination_deg,
            eccentricity=candidate.eccentricity,
            raan_deg=candidate.raan_deg,
            argument_of_perigee_deg=candidate.argument_of_perigee_deg,
            mean_anomaly_deg=candidate.mean_anomaly_deg,
            duration_sec=satellite.phase_offset_sec,
        ),
        dtype=float,
    )

    expected_ecef = np.asarray(
        brahe.state_eci_to_ecef(future_epoch, future_base_state),
        dtype=float,
    )
    actual_ecef = np.asarray(
        brahe.state_eci_to_ecef(
            start_epoch,
            np.asarray(satellite.state_eci_m_mps, dtype=float),
        ),
        dtype=float,
    )

    assert np.allclose(actual_ecef[:3], expected_ecef[:3], atol=1e-6)
    assert np.allclose(actual_ecef[3:], expected_ecef[3:], atol=1e-6)


def test_generated_satellite_states_are_unique_and_within_bounds() -> None:
    case = _synthetic_case(["t1"], revisit_hours=8.0, max_num_satellites=12)
    candidate = _synthetic_candidate("candidate", repeat_hours=24.0)
    selection = select_candidates(
        case,
        _synthetic_coverage(
            candidates=[candidate],
            candidate_to_targets={candidate.candidate_id: ["t1"]},
        ),
    )

    satellites = generate_phased_satellites(case, selection)

    positions = {
        tuple(round(value, 3) for value in satellite.state_eci_m_mps[:3])
        for satellite in satellites
    }
    assert len(positions) == len(satellites)
    for satellite in satellites:
        altitude_m = np.linalg.norm(satellite.state_eci_m_mps[:3]) - EARTH_RADIUS_M
        assert case.satellite_model.min_altitude_m <= altitude_m
        assert altitude_m <= case.satellite_model.max_altitude_m


def test_serial_and_parallel_opportunity_generation_match() -> None:
    case = load_case(CASE_DIR)
    search_config = RgtSearchConfig(
        max_repeat_days=1,
        min_revolutions_per_day=15,
        max_revolutions_per_day=15,
        inclinations_deg=(97.8,),
        max_templates=1,
        closure_tolerance_m=5_000.0,
        refinement_iterations=8,
    )
    result = search_rgt_templates(case, search_config)
    coverage = build_coverage_summary(
        case,
        result.accepted_templates,
        CoverageConfig(
            raan_count=2,
            sample_step_sec=7200.0,
            keep_samples_per_window=2,
            worker_count=1,
        ),
    )
    selection = select_candidates(case, coverage)
    satellites = generate_phased_satellites(case, selection)
    base_config = SchedulingConfig(
        opportunity_sample_step_sec=1800.0,
        validation_sample_step_sec=10.0,
        opportunity_worker_count=1,
    )

    serial, serial_considered, serial_refinement = build_opportunities(
        case=case,
        coverage=coverage,
        selection=selection,
        satellites=satellites,
        config=base_config,
    )
    parallel, parallel_considered, parallel_refinement = build_opportunities(
        case=case,
        coverage=coverage,
        selection=selection,
        satellites=satellites,
        config=SchedulingConfig(
            opportunity_sample_step_sec=base_config.opportunity_sample_step_sec,
            validation_sample_step_sec=base_config.validation_sample_step_sec,
            opportunity_worker_count=2,
        ),
    )

    assert serial_considered == parallel_considered
    assert serial_refinement == parallel_refinement
    assert [action.as_debug_dict() for action in serial] == [
        action.as_debug_dict() for action in parallel
    ]


def test_opportunity_generation_includes_redundant_visible_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _synthetic_case(
        ["assigned", "uncovered"],
        revisit_hours=8.0,
        max_num_satellites=3,
    )
    candidate = _synthetic_candidate("candidate", repeat_hours=24.0)
    coverage = _synthetic_coverage(
        candidates=[candidate],
        candidate_to_targets={candidate.candidate_id: ["assigned", "uncovered"]},
    )
    selection = SelectionSummary(
        selected_candidates=[
            SelectedCandidate(
                candidate=candidate,
                assigned_target_ids=("assigned",),
                required_satellites=3,
                covered_target_ids=("assigned", "uncovered"),
                redundant_target_ids=("uncovered",),
            )
        ],
        target_assignments={
            "assigned": TargetAssignment(
                target_id="assigned",
                candidate_id=candidate.candidate_id,
                required_satellites=3,
                repeat_period_hours=24.0,
                coverage_margin_score=0.0,
            )
        },
        uncovered_target_ids=["uncovered"],
        total_required_satellites=3,
        max_num_satellites=3,
        rounds=[],
        budget_near_misses=[],
        all_targets_covered=False,
        within_satellite_budget=True,
    )
    satellites = [
        SatellitePlan(
            satellite_id=f"satellite_{index:02d}",
            candidate_id=candidate.candidate_id,
            template_id=candidate.template_id,
            phase_index=index,
            phase_count=3,
            phase_offset_sec=float(index * 8 * 3600),
            mean_anomaly_deg=float(index * 120.0),
            state_eci_m_mps=(7_000_000.0, 0.0, 0.0, 0.0, 7_500.0, 0.0),
        )
        for index in range(3)
    ]

    def fake_refined_opportunities(**kwargs):
        satellite = kwargs["satellite"]
        target_id = kwargs["target_id"]
        action = ObservationAction(
            action_type="observation",
            satellite_id=satellite.satellite_id,
            target_id=target_id,
            start=case.horizon_start + timedelta(hours=1),
            end=case.horizon_start + timedelta(hours=1, seconds=30),
            candidate_id=satellite.candidate_id,
            opportunity_midpoint_offset_sec=3615.0,
        )
        return [action], 1, {}, {}

    monkeypatch.setattr(
        solution_module,
        "_refined_opportunities_for_satellite_target",
        fake_refined_opportunities,
    )

    opportunities, considered, refinement = build_opportunities(
        case=case,
        coverage=coverage,
        selection=selection,
        satellites=satellites,
        config=SchedulingConfig(opportunity_worker_count=1),
    )

    assert considered == 6
    assert {action.target_id for action in opportunities} == {
        "assigned",
        "uncovered",
    }
    assert refinement["opportunity_target_summary"]["assigned_pair_count"] == 1
    assert refinement["opportunity_target_summary"]["opportunistic_pair_count"] == 1
    assert refinement["opportunity_target_summary"]["opportunistic_target_ids"] == [
        "uncovered"
    ]


def test_opportunity_refinement_uses_numerical_j2_state_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _synthetic_case(["assigned"], revisit_hours=8.0, max_num_satellites=3)
    candidate = _synthetic_candidate("candidate", repeat_hours=24.0)
    coverage = _synthetic_coverage(
        candidates=[candidate],
        candidate_to_targets={candidate.candidate_id: ["assigned"]},
        windows=[_synthetic_window(candidate, "assigned", 1.0)],
    )
    selection = select_candidates(case, coverage)
    satellites = generate_phased_satellites(case, selection)
    seen_provider: list[bool] = []

    def fake_refined_opportunities(**kwargs):
        seen_provider.append(kwargs["state_provider"] is not None)
        return [], 1, {"no_valid_interval": 1}, {}

    monkeypatch.setattr(
        solution_module,
        "_refined_opportunities_for_satellite_target",
        fake_refined_opportunities,
    )

    build_opportunities(
        case=case,
        coverage=coverage,
        selection=selection,
        satellites=satellites,
        config=SchedulingConfig(
            opportunity_worker_count=1,
            refinement_propagation="numerical_j2",
        ),
    )

    assert seen_provider
    assert all(seen_provider)


def test_gap_aware_action_selection_improves_with_phased_opportunities() -> None:
    case = _synthetic_case(["t1"], revisit_hours=8.0, max_num_satellites=3)
    candidate = _synthetic_candidate("candidate", repeat_hours=24.0)
    selection = select_candidates(
        case,
        _synthetic_coverage(
            candidates=[candidate],
            candidate_to_targets={candidate.candidate_id: ["t1"]},
        ),
    )
    satellites = generate_phased_satellites(case, selection)
    opportunities = [
        ObservationAction(
            action_type="observation",
            satellite_id=satellite.satellite_id,
            target_id="t1",
            start=case.horizon_start + timedelta(hours=8 * index),
            end=case.horizon_start + timedelta(hours=8 * index, seconds=60),
            candidate_id=candidate.candidate_id,
            opportunity_midpoint_offset_sec=8.0 * index * 3600.0 + 30.0,
        )
        for index, satellite in enumerate(satellites, start=1)
    ]

    selected = select_gap_aware_actions(
        case=case,
        selection=selection,
        satellites=satellites,
        opportunities=opportunities,
        config=SchedulingConfig(min_gap_improvement_sec=1.0),
    )

    assert len(selected) >= 2


def test_assigned_first_scheduler_commits_assigned_revisit_before_opportunistic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        solution_module,
        "_compatible_with_selected",
        lambda **_: True,
    )
    case = _synthetic_case(["assigned", "uncovered"], revisit_hours=8.0, max_num_satellites=3)
    candidate = _synthetic_candidate("candidate", repeat_hours=24.0)
    selection = SelectionSummary(
        selected_candidates=[
            SelectedCandidate(
                candidate=candidate,
                assigned_target_ids=("assigned",),
                required_satellites=3,
                covered_target_ids=("assigned", "uncovered"),
                redundant_target_ids=("uncovered",),
            )
        ],
        target_assignments={
            "assigned": TargetAssignment(
                target_id="assigned",
                candidate_id=candidate.candidate_id,
                required_satellites=3,
                repeat_period_hours=24.0,
                coverage_margin_score=0.0,
            )
        },
        uncovered_target_ids=["uncovered"],
        total_required_satellites=3,
        max_num_satellites=3,
        rounds=[],
        budget_near_misses=[],
        all_targets_covered=False,
        within_satellite_budget=True,
    )
    satellites = generate_phased_satellites(case, selection)
    opportunities: list[ObservationAction] = []
    for index, hour in enumerate([8, 16, 24, 32, 40]):
        satellite = satellites[index % len(satellites)]
        midpoint = case.horizon_start + timedelta(hours=hour)
        opportunities.append(
            ObservationAction(
                action_type="observation",
                satellite_id=satellite.satellite_id,
                target_id="assigned",
                start=midpoint - timedelta(seconds=15),
                end=midpoint + timedelta(seconds=15),
                candidate_id=candidate.candidate_id,
                opportunity_midpoint_offset_sec=hour * 3600.0,
            )
        )
    midpoint = case.horizon_start + timedelta(hours=12)
    opportunities.append(
        ObservationAction(
            action_type="observation",
            satellite_id=satellites[0].satellite_id,
            target_id="uncovered",
            start=midpoint - timedelta(seconds=15),
            end=midpoint + timedelta(seconds=15),
            candidate_id=candidate.candidate_id,
            opportunity_midpoint_offset_sec=12 * 3600.0,
        )
    )

    selected, summary = solution_module.select_assigned_first_actions(
        case=case,
        selection=selection,
        satellites=satellites,
        opportunities=opportunities,
        config=SchedulingConfig(min_gap_improvement_sec=1.0),
    )

    assigned_actions = [action for action in selected if action.target_id == "assigned"]
    assert len(assigned_actions) == 5
    assert summary["failed_assigned_target_ids"] == []
    assert summary["assigned_action_count_before_opportunistic"] == 5


def test_action_builder_avoids_same_satellite_overlap() -> None:
    case = _synthetic_case(["t1", "t2"], revisit_hours=8.0, max_num_satellites=3)
    candidate = _synthetic_candidate("candidate", repeat_hours=24.0)
    selection = select_candidates(
        case,
        _synthetic_coverage(
            candidates=[candidate],
            candidate_to_targets={candidate.candidate_id: ["t1", "t2"]},
        ),
    )
    satellite = generate_phased_satellites(case, selection)[0]
    opportunities = [
        ObservationAction(
            action_type="observation",
            satellite_id=satellite.satellite_id,
            target_id="t1",
            start=case.horizon_start + timedelta(hours=12),
            end=case.horizon_start + timedelta(hours=12, seconds=120),
            candidate_id=candidate.candidate_id,
            opportunity_midpoint_offset_sec=12.0 * 3600.0,
        ),
        ObservationAction(
            action_type="observation",
            satellite_id=satellite.satellite_id,
            target_id="t2",
            start=case.horizon_start + timedelta(hours=12, seconds=30),
            end=case.horizon_start + timedelta(hours=12, seconds=150),
            candidate_id=candidate.candidate_id,
            opportunity_midpoint_offset_sec=12.0 * 3600.0 + 30.0,
        ),
    ]

    selected = select_gap_aware_actions(
        case=case,
        selection=selection,
        satellites=[satellite],
        opportunities=opportunities,
        config=SchedulingConfig(min_gap_improvement_sec=1.0),
    )

    assert len(selected) == 1


def test_local_validation_catches_overlap_and_visibility_failures() -> None:
    case = _synthetic_case(["t1"], revisit_hours=8.0, max_num_satellites=3)
    candidate = _synthetic_candidate("candidate", repeat_hours=24.0)
    selection = select_candidates(
        case,
        _synthetic_coverage(
            candidates=[candidate],
            candidate_to_targets={candidate.candidate_id: ["t1"]},
        ),
    )
    satellite = generate_phased_satellites(case, selection)[0]
    first = ObservationAction(
        action_type="observation",
        satellite_id=satellite.satellite_id,
        target_id="t1",
        start=case.horizon_start + timedelta(hours=1),
        end=case.horizon_start + timedelta(hours=1, seconds=120),
        candidate_id=candidate.candidate_id,
        opportunity_midpoint_offset_sec=3600.0,
    )
    second = ObservationAction(
        action_type="observation",
        satellite_id=satellite.satellite_id,
        target_id="t1",
        start=case.horizon_start + timedelta(hours=1, seconds=30),
        end=case.horizon_start + timedelta(hours=1, seconds=150),
        candidate_id=candidate.candidate_id,
        opportunity_midpoint_offset_sec=3630.0,
    )

    validation = validate_solution_locally(
        case=case,
        selection=selection,
        satellites=[satellite],
        actions=[first, second],
        config=SchedulingConfig(),
    )

    assert not validation.is_valid
    assert any("overlapping" in error for error in validation.errors)
    assert any("visibility" in error for error in validation.errors)


def test_solution_writer_emits_benchmark_shaped_json() -> None:
    case = _synthetic_case(["t1"], revisit_hours=8.0, max_num_satellites=3)
    candidate = _synthetic_candidate("candidate", repeat_hours=24.0)
    coverage = _synthetic_coverage(
        candidates=[candidate],
        candidate_to_targets={candidate.candidate_id: ["t1"]},
    )
    selection = select_candidates(case, coverage)

    result = build_solution(
        case=case,
        coverage=coverage,
        selection=selection,
        config=SchedulingConfig(),
    )
    payload = result.solution_json()

    assert set(payload) == {"satellites", "actions"}
    assert len(payload["satellites"]) == 3
    assert isinstance(payload["actions"], list)
    assert {"satellite_id", "x_m", "y_m", "z_m", "vx_m_s", "vy_m_s", "vz_m_s"} <= set(
        payload["satellites"][0]
    )


def test_full_profile_analytical_rgt_matches_numerical_j2_oracle() -> None:
    case = load_case(CASE_DIR)
    config = RgtSearchConfig(
        max_repeat_days=2,
        min_revolutions_per_day=12,
        max_revolutions_per_day=16,
        inclinations_deg=(30.0, 45.0, 53.0, 63.4, 75.0, 97.8),
        max_templates=12,
        closure_tolerance_m=5_000.0,
        refinement_iterations=8,
    )

    result = search_rgt_templates(case, config)

    assert len(result.accepted_templates) == config.max_templates
    for template in result.accepted_templates:
        assert template.closure is not None
        numerical_closure = numerical_closure_score_at_duration(
            case,
            template.state_eci_m_mps,
            duration_sec=template.repeat_period_sec,
        )
        assert numerical_closure.surface_error_m <= config.closure_tolerance_m
        assert abs(
            numerical_closure.surface_error_m - template.closure.surface_error_m
        ) < config.closure_tolerance_m


def test_solve_sh_writes_status_solution_and_debug(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "solution"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "\n".join(
            [
                "active_profile: test_public",
                "compute_envelope:",
                "  name: test_public",
                "  deterministic: true",
                "rgt_search:",
                "  max_repeat_days: 1",
                "  min_revolutions_per_day: 15",
                "  max_revolutions_per_day: 15",
                "  inclinations_deg: [97.8]",
                "  max_templates: 1",
                "  closure_tolerance_m: 5000.0",
                "  refinement_iterations: 8",
                "coverage:",
                "  raan_count: 2",
                "  sample_step_sec: 7200.0",
                "  keep_samples_per_window: 2",
                "  worker_count: 2",
                "scheduling:",
                "  observation_duration_sec: 60.0",
                "  opportunity_sample_step_sec: 300.0",
                "  min_gap_improvement_sec: 60.0",
                "  validation_sample_step_sec: 10.0",
                "  max_actions: 100",
                "  max_selection_repair_rounds: 2",
                "  max_repair_alternates_per_target: 4",
                "  opportunity_worker_count: 2",
                "  repair_worker_count: 2",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "bash",
            str(SOLVER_DIR / "solve.sh"),
            str(CASE_DIR),
            str(config_dir),
            str(output_dir),
        ],
        check=False,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    status = json.loads((output_dir / "status.json").read_text(encoding="utf-8"))
    solution = json.loads((output_dir / "solution.json").read_text(encoding="utf-8"))
    debug = json.loads(
        (output_dir / "debug/closure_search.json").read_text(encoding="utf-8")
    )
    coverage = json.loads(
        (output_dir / "debug/coverage_summary.json").read_text(encoding="utf-8")
    )
    selection = json.loads(
        (output_dir / "debug/selection_summary.json").read_text(encoding="utf-8")
    )
    repair = json.loads(
        (output_dir / "debug/selection_repair_summary.json").read_text(
            encoding="utf-8"
        )
    )
    solution_debug = json.loads(
        (output_dir / "debug/solution_summary.json").read_text(encoding="utf-8")
    )
    assert status["status"] == "completed"
    assert status["solver"] == "j2_rgt_set_cover"
    assert status["method_status"] == "experiment_ready"
    assert status["closure_search"]["accepted_count"] == 1
    assert status["coverage"]["candidate_count"] == 2
    assert "coarse_hint_count" in status["coverage"]
    assert status["compute_profile"]["active_profile"] == "test_public"
    assert status["compute_profile"]["compute_envelope"]["name"] == "test_public"
    assert status["compute_profile"]["available_profiles"] == []
    assert status["compute_profile"]["coverage_worker_count"] == 2
    assert status["compute_profile"]["opportunity_worker_count"] == 2
    assert status["compute_profile"]["repair_worker_count"] == 2
    assert "coverage" in status["timing_seconds"]
    assert "final_solution_timing_seconds" in status["compute_profile"]
    assert status["selection"]["selected_candidate_count"] >= 0
    assert set(solution) == {"satellites", "actions"}
    assert debug["accepted_count"] == 1
    assert coverage["candidate_count"] == 2
    assert "target_to_candidates" in coverage
    assert "coarse_hints" in coverage
    assert "selected_candidates" in selection
    assert "target_assignments" in selection
    assert "target_diagnostics" in repair
    assert "validation" in solution_debug
    assert "timing_seconds" in solution_debug
    assert "opportunity_refinement_summary" in solution_debug
    assert "opportunity_refinement_summary" in status["solution"]
    assert status["solution"]["satellite_count"] == len(solution["satellites"])
