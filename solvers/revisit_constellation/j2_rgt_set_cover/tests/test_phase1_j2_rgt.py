from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess

import brahe
import numpy as np
import pytest

from src.case_io import RevisitCase, SatelliteModel, SensorModel, Target, load_case
from src.coverage import (
    CoverageConfig,
    CoverageSummary,
    RaanCandidate,
    VisibilitySample,
    build_coverage_summary,
    expand_raan_candidates,
    geometry_sample_from_state,
    group_visible_samples,
)
from src.rgt import (
    EARTH_RADIUS_M,
    SIDEREAL_DAY_SEC,
    RgtSearchConfig,
    analytical_brouwer_closure_score,
    circular_state_eci,
    closure_score_from_geocentric,
    enumerate_seeds,
    numerical_closure_score_at_duration,
    search_rgt_templates,
    solve_rgt_semimajor_axis,
)
from src.selection import satellites_required_for_target, select_candidates
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


def _synthetic_coverage(
    *,
    candidates: list[RaanCandidate],
    candidate_to_targets: dict[str, list[str]],
) -> CoverageSummary:
    target_to_candidates: dict[str, list[str]] = {}
    for candidate_id, target_ids in candidate_to_targets.items():
        for target_id in target_ids:
            target_to_candidates.setdefault(target_id, []).append(candidate_id)
    return CoverageSummary(
        candidates=candidates,
        windows=[],
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


def test_solve_sh_writes_phase3_status_and_debug(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "solution"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "\n".join(
            [
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
                "  worker_count: 1",
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
    assert status["status"] == "completed"
    assert status["phase"] == 3
    assert status["closure_search"]["accepted_count"] == 1
    assert status["coverage"]["candidate_count"] == 2
    assert status["selection"]["selected_candidate_count"] >= 0
    assert solution == {"satellites": [], "actions": []}
    assert debug["accepted_count"] == 1
    assert coverage["candidate_count"] == 2
    assert "target_to_candidates" in coverage
    assert "selected_candidates" in selection
    assert "target_assignments" in selection
