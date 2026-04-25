from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from solvers.regional_coverage.cp_local_search.src.candidates import (
    Candidate,
    generate_candidates,
)
from solvers.regional_coverage.cp_local_search.src.case_io import (
    SolverConfig,
    load_case,
)
from solvers.regional_coverage.cp_local_search.src.coverage import (
    CoverageFootprint,
    CoverageIndex,
)
from solvers.regional_coverage.cp_local_search.src.cp_repair import (
    CPRepairConfig,
    CPMetrics,
)
from solvers.regional_coverage.cp_local_search.src.greedy import (
    GreedyConfig,
    GreedyResult,
    GreedySummary,
    greedy_insertion,
)
from solvers.regional_coverage.cp_local_search.src.local_search import (
    LocalSearchConfig,
    Neighborhood,
    build_neighborhoods,
    covered_sample_ids,
    local_search,
    rebuild_neighborhood,
    schedule_objective,
    state_from_candidates,
)
from solvers.regional_coverage.cp_local_search.src.sequence import (
    SatelliteSequence,
    insert_candidate,
    is_consistent,
    remove_candidate,
)
from solvers.regional_coverage.cp_local_search.src.time_grid import grid_offsets
from solvers.regional_coverage.cp_local_search.src.transition import (
    required_transition_gap_s,
    slew_time_s,
    transition_result,
)


CASE_DIR = REPO_ROOT / "benchmarks" / "regional_coverage" / "dataset" / "cases" / "test" / "case_0001"


def _candidate(
    candidate_id: str,
    *,
    satellite_id: str = "sat_iceye-x2",
    start_offset_s: int = 0,
    end_offset_s: int = 20,
    roll_deg: float = -26.0,
    samples: frozenset[str] = frozenset({"sample_a"}),
    energy_wh: float = 1.0,
) -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
        satellite_id=satellite_id,
        start_offset_s=start_offset_s,
        end_offset_s=end_offset_s,
        duration_s=end_offset_s - start_offset_s,
        roll_deg=roll_deg,
        coverage_sample_ids=samples,
        base_coverage_weight_m2=1.0,
        estimated_energy_wh=energy_wh,
        estimated_slew_in_gap_s=2.0,
        footprint_center_latitude_deg=0.0,
        footprint_center_longitude_deg=0.0,
        footprint_heading_deg=0.0,
        along_half_m=100.0,
        cross_half_m=100.0,
    )


def _coverage_index(weights: dict[str, float]) -> CoverageIndex:
    return CoverageIndex(
        samples=(),
        total_weight_m2=sum(weights.values()),
        sample_weight_by_id=weights,
    )


def test_load_case_reads_public_regional_coverage_files() -> None:
    case = load_case(CASE_DIR)

    assert case.mission.case_id == "case_0001"
    assert case.mission.time_step_s == 10
    assert len(case.satellites) == 10
    assert len(case.regions) == 3
    assert len(case.samples) > 10_000
    assert "sat_iceye-x2" in case.satellites


def test_action_grid_offsets_are_duration_bounded() -> None:
    case = load_case(CASE_DIR)
    mission = case.mission

    offsets = grid_offsets(mission, stride_s=3600, duration_s=20)

    assert offsets[0] == 0
    assert offsets[1] == 3600
    assert offsets[-1] + 20 <= mission.horizon_duration_s
    assert all(offset % mission.time_step_s == 0 for offset in offsets)


def test_candidate_generation_is_deterministic_and_grid_aligned() -> None:
    case = load_case(CASE_DIR)
    config = SolverConfig(
        candidate_stride_s=3600,
        max_candidates_per_satellite=1,
        max_zero_coverage_candidates_per_satellite=1,
    )

    first, first_summary = generate_candidates(case, config)
    second, second_summary = generate_candidates(case, config)

    assert [candidate.candidate_id for candidate in first] == [
        candidate.candidate_id for candidate in second
    ]
    assert first_summary.as_dict() == second_summary.as_dict()
    assert len(first) == len(case.satellites)
    assert all(candidate.duration_s == 20 for candidate in first)
    assert all(candidate.start_offset_s % case.mission.time_step_s == 0 for candidate in first)


def test_tuned_candidate_generation_finds_positive_smoke_coverage() -> None:
    case = load_case(CASE_DIR)
    config = SolverConfig(
        candidate_stride_s=600,
        roll_samples_per_side=3,
        include_zero_coverage_candidates=False,
    )

    candidates, summary = generate_candidates(case, config)

    assert candidates
    assert summary.positive_coverage_candidate_count == len(candidates)
    assert summary.max_candidate_weight_m2 > 0.0
    assert all(candidate.coverage_sample_ids for candidate in candidates)


def test_coverage_mapping_selects_samples_inside_oriented_strip() -> None:
    case = load_case(CASE_DIR)
    samples = case.samples[:2]
    index = CoverageIndex(
        samples=samples,
        total_weight_m2=sum(sample.weight_m2 for sample in samples),
        sample_weight_by_id={sample.sample_id: sample.weight_m2 for sample in samples},
    )
    origin = samples[0]
    footprint = CoverageFootprint(
        center_latitude_deg=origin.latitude_deg,
        center_longitude_deg=origin.longitude_deg,
        heading_deg=0.0,
        along_half_m=100.0,
        cross_half_m=100.0,
    )

    hits = index.samples_for_footprint(footprint)

    assert hits == frozenset({origin.sample_id})
    assert index.total_weight(hits) == pytest.approx(origin.weight_m2)


def test_roll_slew_formula_matches_triangular_and_trapezoidal_cases() -> None:
    satellite = load_case(CASE_DIR).satellites["sat_iceye-x2"]

    triangular = slew_time_s(1.0, satellite)
    trapezoidal = slew_time_s(10.0, satellite)

    assert triangular == pytest.approx(2.0 * math.sqrt(1.0 / 0.4))
    assert trapezoidal == pytest.approx(10.0 / 1.2 + 1.2 / 0.4)
    assert required_transition_gap_s(-26.0, 26.0, satellite) == pytest.approx(
        52.0 / 1.2 + 1.2 / 0.4 + 2.0
    )


def test_sequence_insert_remove_and_transition_feasibility() -> None:
    case = load_case(CASE_DIR)
    satellite = case.satellites["sat_iceye-x2"]
    sequence = SatelliteSequence(satellite_id="sat_iceye-x2")
    first = _candidate("c1", start_offset_s=0, end_offset_s=20, roll_deg=-26.0)
    feasible_second = _candidate("c2", start_offset_s=100, end_offset_s=120, roll_deg=26.0)
    infeasible_second = _candidate("c3", start_offset_s=40, end_offset_s=60, roll_deg=26.0)

    assert insert_candidate(case, sequence, first).success is True
    assert transition_result(first, feasible_second, satellite=satellite).feasible is True
    assert insert_candidate(case, sequence, feasible_second).success is True
    ok, reasons = is_consistent(case, sequence)
    assert ok, reasons
    assert sequence.covered_sample_ids() == {"sample_a"}

    removed = remove_candidate(sequence, "c2")
    assert removed.candidate_id == "c2"
    result = insert_candidate(case, sequence, infeasible_second)
    assert result.success is False
    assert "candidate lacks required transition gap from previous" in result.reject_reasons


def test_greedy_updates_marginal_unique_coverage_after_each_insertion() -> None:
    case = load_case(CASE_DIR)
    index = _coverage_index({"a": 1.0, "b": 1.0, "c": 1.0})
    candidates = [
        _candidate("c1", start_offset_s=0, end_offset_s=20, roll_deg=-26.0, samples=frozenset({"a", "b"})),
        _candidate("c2", start_offset_s=100, end_offset_s=120, roll_deg=-26.0, samples=frozenset({"b", "c"})),
    ]

    result = greedy_insertion(
        case,
        candidates,
        coverage_index=index,
        config=GreedyConfig(policy="best_marginal_coverage"),
    )

    assert [candidate.candidate_id for candidate in result.selected_candidates] == ["c1", "c2"]
    assert result.covered_sample_ids == {"a", "b", "c"}
    assert result.summary.selected_weight_m2 == pytest.approx(3.0)
    assert [item.marginal_weight_m2 for item in result.accepted_evaluations] == [2.0, 1.0]


def test_greedy_can_insert_between_predecessor_and_successor() -> None:
    case = load_case(CASE_DIR)
    index = _coverage_index({"a": 5.0, "b": 1.0, "c": 4.0})
    candidates = [
        _candidate("c1", start_offset_s=0, end_offset_s=20, roll_deg=-26.0, samples=frozenset({"a"})),
        _candidate("c2", start_offset_s=100, end_offset_s=120, roll_deg=-26.0, samples=frozenset({"b"})),
        _candidate("c3", start_offset_s=200, end_offset_s=220, roll_deg=-26.0, samples=frozenset({"c"})),
    ]

    result = greedy_insertion(
        case,
        candidates,
        coverage_index=index,
        config=GreedyConfig(policy="best_marginal_coverage"),
    )

    sequence = result.state.sequences["sat_iceye-x2"]
    assert [candidate.candidate_id for candidate in sequence.candidates] == ["c1", "c2", "c3"]
    assert result.accepted_evaluations[-1].position == 1


def test_greedy_rejects_infeasible_overlap_and_slew() -> None:
    case = load_case(CASE_DIR)
    index = _coverage_index({"a": 5.0, "b": 4.0})
    candidates = [
        _candidate("c1", start_offset_s=0, end_offset_s=20, roll_deg=-26.0, samples=frozenset({"a"})),
        _candidate("c2", start_offset_s=40, end_offset_s=60, roll_deg=26.0, samples=frozenset({"b"})),
    ]

    result = greedy_insertion(
        case,
        candidates,
        coverage_index=index,
        config=GreedyConfig(policy="best_marginal_coverage"),
    )

    assert [candidate.candidate_id for candidate in result.selected_candidates] == ["c1"]
    assert result.summary.stop_reason == "no_positive_feasible_insertion"
    assert result.summary.reject_reasons["candidate lacks required transition gap from previous"] >= 1


def test_greedy_stops_at_action_cap() -> None:
    case = load_case(CASE_DIR)
    capped_case = replace(case, mission=replace(case.mission, max_actions_total=1))
    index = _coverage_index({"a": 5.0, "b": 4.0})
    candidates = [
        _candidate("c1", start_offset_s=0, end_offset_s=20, samples=frozenset({"a"})),
        _candidate("c2", start_offset_s=100, end_offset_s=120, samples=frozenset({"b"})),
    ]

    result = greedy_insertion(
        capped_case,
        candidates,
        coverage_index=index,
        config=GreedyConfig(policy="best_marginal_coverage"),
    )

    assert [candidate.candidate_id for candidate in result.selected_candidates] == ["c1"]
    assert result.summary.stop_reason == "action_cap_reached"


def test_greedy_tie_breaks_by_lower_energy_then_stable_candidate_id() -> None:
    case = load_case(CASE_DIR)
    index = _coverage_index({"a": 1.0, "b": 1.0, "c": 1.0})
    candidates = [
        _candidate("c_energy_high", start_offset_s=0, end_offset_s=20, samples=frozenset({"a"}), energy_wh=3.0),
        _candidate("z_energy_low", start_offset_s=0, end_offset_s=20, samples=frozenset({"b"}), energy_wh=1.0),
        _candidate("a_stable_id", start_offset_s=0, end_offset_s=20, samples=frozenset({"c"}), energy_wh=1.0),
    ]

    first = greedy_insertion(
        case,
        candidates,
        coverage_index=index,
        config=GreedyConfig(policy="best_marginal_coverage", max_iterations=1),
    )
    second = greedy_insertion(
        case,
        list(reversed(candidates)),
        coverage_index=index,
        config=GreedyConfig(policy="best_marginal_coverage", max_iterations=1),
    )

    assert first.selected_candidates[0].candidate_id == "a_stable_id"
    assert second.selected_candidates[0].candidate_id == "a_stable_id"


def test_local_search_extracts_satellite_time_component_neighborhoods() -> None:
    selected = [
        _candidate("c1", start_offset_s=0, end_offset_s=20),
        _candidate("c2", start_offset_s=500, end_offset_s=520),
        _candidate("c3", start_offset_s=5000, end_offset_s=5020),
    ]
    candidates = selected + [
        _candidate("u1", start_offset_s=200, end_offset_s=220),
        _candidate("u2", start_offset_s=5050, end_offset_s=5070),
    ]

    neighborhoods = build_neighborhoods(
        candidates,
        selected,
        config=LocalSearchConfig(
            component_gap_s=1000,
            time_padding_s=100,
            max_neighborhoods_per_iteration=10,
        ),
    )

    time_components = [
        item for item in neighborhoods if item.kind == "satellite_time_component"
    ]
    assert len(time_components) == 2
    assert time_components[0].remove_candidate_ids == ("c1", "c2")
    assert "u1" in time_components[0].candidate_ids
    assert time_components[1].remove_candidate_ids == ("c3",)
    assert "u2" in time_components[1].candidate_ids


def test_neighborhood_rebuild_recomputes_marginal_after_removal_and_accepts_improvement() -> None:
    case = load_case(CASE_DIR)
    incumbent = [
        _candidate("c1", start_offset_s=0, end_offset_s=20, samples=frozenset({"a"})),
        _candidate("c2", start_offset_s=200, end_offset_s=220, samples=frozenset({"b"})),
    ]
    replacement = _candidate(
        "c3",
        start_offset_s=100,
        end_offset_s=120,
        samples=frozenset({"a", "c"}),
    )
    candidate_by_id = {candidate.candidate_id: candidate for candidate in incumbent + [replacement]}
    index = _coverage_index({"a": 1.0, "b": 1.0, "c": 1.0})
    neighborhood = Neighborhood(
        neighborhood_id="n_test",
        kind="satellite_time_component",
        satellite_id="sat_iceye-x2",
        start_offset_s=0,
        end_offset_s=220,
        remove_candidate_ids=("c1",),
        candidate_ids=("c1", "c3"),
        reason="unit test replacement",
    )

    move = rebuild_neighborhood(
        case,
        incumbent,
        neighborhood,
        candidate_by_id=candidate_by_id,
        coverage_index=index,
        greedy_config=GreedyConfig(),
    )

    assert move.accepted is True
    assert move.before.coverage_weight_m2 == pytest.approx(2.0)
    assert move.after.coverage_weight_m2 == pytest.approx(3.0)
    assert move.inserted_candidate_ids == ("c3",)


def test_local_search_accepts_strictly_improving_rebuild() -> None:
    case = load_case(CASE_DIR)
    incumbent = [
        _candidate("c1", start_offset_s=0, end_offset_s=20, samples=frozenset({"a"})),
        _candidate("c2", start_offset_s=200, end_offset_s=220, samples=frozenset({"b"})),
    ]
    replacement = _candidate(
        "c3",
        start_offset_s=100,
        end_offset_s=120,
        samples=frozenset({"a", "b", "c"}),
    )
    all_candidates = incumbent + [replacement]
    index = _coverage_index({"a": 1.0, "b": 1.0, "c": 1.0})
    greedy_result = GreedyResult(
        state=state_from_candidates(case, incumbent),
        selected_candidates=list(incumbent),
        covered_sample_ids=covered_sample_ids(incumbent),
        summary=GreedySummary(policy="best_marginal_coverage"),
        accepted_evaluations=[],
        attempt_debug=[],
    )

    result = local_search(
        case,
        all_candidates,
        coverage_index=index,
        greedy_result=greedy_result,
        greedy_config=GreedyConfig(),
        config=LocalSearchConfig(
            max_iterations=2,
            component_gap_s=1000,
            time_padding_s=100,
            max_neighborhoods_per_iteration=4,
        ),
    )

    assert result.summary.accepted_moves == 1
    assert result.summary.final_objective.coverage_weight_m2 == pytest.approx(3.0)
    assert [candidate.candidate_id for candidate in result.selected_candidates] == ["c3"]
    assert result.summary.incumbent_progression[0]["objective"]["coverage_weight_m2"] == pytest.approx(3.0)


def test_local_search_rejects_non_improving_move_and_keeps_incumbent() -> None:
    case = load_case(CASE_DIR)
    incumbent = [
        _candidate("c1", start_offset_s=0, end_offset_s=20, samples=frozenset({"a"})),
        _candidate("c2", start_offset_s=200, end_offset_s=220, samples=frozenset({"b"})),
    ]
    duplicate = _candidate(
        "c3",
        start_offset_s=100,
        end_offset_s=120,
        samples=frozenset({"a"}),
    )
    all_candidates = incumbent + [duplicate]
    index = _coverage_index({"a": 1.0, "b": 1.0})
    greedy_result = GreedyResult(
        state=state_from_candidates(case, incumbent),
        selected_candidates=list(incumbent),
        covered_sample_ids=covered_sample_ids(incumbent),
        summary=GreedySummary(policy="best_marginal_coverage"),
        accepted_evaluations=[],
        attempt_debug=[],
    )

    result = local_search(
        case,
        all_candidates,
        coverage_index=index,
        greedy_result=greedy_result,
        greedy_config=GreedyConfig(),
        config=LocalSearchConfig(
            max_iterations=1,
            component_gap_s=1000,
            time_padding_s=100,
            max_neighborhoods_per_iteration=4,
        ),
    )

    assert result.summary.accepted_moves == 0
    assert [candidate.candidate_id for candidate in result.selected_candidates] == ["c1", "c2"]
    assert result.summary.final_objective == schedule_objective(case, incumbent, index)
    assert result.summary.objective_delta["coverage_weight_m2"] == pytest.approx(0.0)


def test_cp_repair_does_not_accept_float_noise_tie() -> None:
    case = load_case(CASE_DIR)
    incumbent = [
        _candidate(
            "c_old",
            start_offset_s=0,
            end_offset_s=20,
            samples=frozenset({"a"}),
        )
    ]
    equivalent = _candidate(
        "c_equivalent",
        start_offset_s=100,
        end_offset_s=120,
        samples=frozenset({"a"}),
    )
    candidate_by_id = {
        candidate.candidate_id: candidate
        for candidate in incumbent + [equivalent]
    }
    index = _coverage_index({"a": 1.0})
    neighborhood = Neighborhood(
        neighborhood_id="n_cp_tie",
        kind="satellite_time_component",
        satellite_id="sat_iceye-x2",
        start_offset_s=0,
        end_offset_s=120,
        remove_candidate_ids=("c_old",),
        candidate_ids=("c_old", "c_equivalent"),
        reason="unit test equivalent cp fallback",
    )
    metrics = CPMetrics()

    move = rebuild_neighborhood(
        case,
        incumbent,
        neighborhood,
        candidate_by_id=candidate_by_id,
        coverage_index=index,
        greedy_config=GreedyConfig(),
        cp_config=CPRepairConfig(max_candidates=4, max_calls=4, max_subsets=16),
        cp_metrics=metrics,
    )

    assert move.accepted is False
    assert move.cp_repair is not None
    assert move.cp_repair.improving is False
    assert metrics.calls == 1
    assert metrics.feasible_solutions == 1
    assert metrics.improving_solutions == 0


def test_local_search_is_deterministic_for_same_inputs() -> None:
    case = load_case(CASE_DIR)
    incumbent = [
        _candidate("c1", start_offset_s=0, end_offset_s=20, samples=frozenset({"a"})),
        _candidate("c2", start_offset_s=200, end_offset_s=220, samples=frozenset({"b"})),
    ]
    replacements = [
        _candidate("c3", start_offset_s=100, end_offset_s=120, samples=frozenset({"a", "b", "c"})),
        _candidate("c4", start_offset_s=120, end_offset_s=140, samples=frozenset({"a", "b", "c"}), energy_wh=2.0),
    ]
    index = _coverage_index({"a": 1.0, "b": 1.0, "c": 1.0})

    def run_once(order):
        greedy_result = GreedyResult(
            state=state_from_candidates(case, incumbent),
            selected_candidates=list(incumbent),
            covered_sample_ids=covered_sample_ids(incumbent),
            summary=GreedySummary(policy="best_marginal_coverage"),
            accepted_evaluations=[],
            attempt_debug=[],
        )
        return local_search(
            case,
            order,
            coverage_index=index,
            greedy_result=greedy_result,
            greedy_config=GreedyConfig(),
            config=LocalSearchConfig(
                max_iterations=2,
                component_gap_s=1000,
                time_padding_s=150,
                max_neighborhoods_per_iteration=4,
            ),
        )

    first = run_once(incumbent + replacements)
    second = run_once(list(reversed(incumbent + replacements)))

    assert [candidate.candidate_id for candidate in first.selected_candidates] == [
        candidate.candidate_id for candidate in second.selected_candidates
    ]
    assert first.summary.as_dict() == second.summary.as_dict()


def test_cp_exact_fallback_improves_when_greedy_rebuild_is_blocked() -> None:
    case = load_case(CASE_DIR)
    incumbent = [
        _candidate(
            "c_old",
            start_offset_s=10,
            end_offset_s=110,
            samples=frozenset({"a", "b", "c", "d", "e"}),
        )
    ]
    left = _candidate(
        "c_left",
        start_offset_s=0,
        end_offset_s=40,
        samples=frozenset({"f", "g", "h"}),
    )
    right = _candidate(
        "c_right",
        start_offset_s=80,
        end_offset_s=120,
        samples=frozenset({"i", "j", "k"}),
    )
    candidate_by_id = {
        candidate.candidate_id: candidate
        for candidate in incumbent + [left, right]
    }
    index = _coverage_index({key: 1.0 for key in "abcdefghijk"})
    neighborhood = Neighborhood(
        neighborhood_id="n_cp",
        kind="satellite_time_component",
        satellite_id="sat_iceye-x2",
        start_offset_s=0,
        end_offset_s=120,
        remove_candidate_ids=("c_old",),
        candidate_ids=("c_old", "c_left", "c_right"),
        reason="unit test cp fallback",
    )
    metrics = CPMetrics()

    move = rebuild_neighborhood(
        case,
        incumbent,
        neighborhood,
        candidate_by_id=candidate_by_id,
        coverage_index=index,
        greedy_config=GreedyConfig(),
        cp_config=CPRepairConfig(max_candidates=4, max_calls=4, max_subsets=16),
        cp_metrics=metrics,
    )

    assert move.accepted is True
    assert move.stop_reason == "cp_strict_improvement"
    assert move.before.coverage_weight_m2 == pytest.approx(5.0)
    assert move.after.coverage_weight_m2 == pytest.approx(6.0)
    assert move.inserted_candidate_ids == ("c_left", "c_right")
    assert move.cp_repair is not None
    assert move.cp_repair.improving is True
    assert metrics.calls == 1
    assert metrics.feasible_solutions == 1
    assert metrics.improving_solutions == 1


def test_local_search_reports_cp_metrics() -> None:
    case = load_case(CASE_DIR)
    incumbent = [
        _candidate(
            "c_old",
            start_offset_s=10,
            end_offset_s=110,
            samples=frozenset({"a", "b", "c", "d", "e"}),
        )
    ]
    all_candidates = incumbent + [
        _candidate("c_left", start_offset_s=0, end_offset_s=40, samples=frozenset({"f", "g", "h"})),
        _candidate("c_right", start_offset_s=80, end_offset_s=120, samples=frozenset({"i", "j", "k"})),
    ]
    index = _coverage_index({key: 1.0 for key in "abcdefghijk"})
    greedy_result = GreedyResult(
        state=state_from_candidates(case, incumbent),
        selected_candidates=list(incumbent),
        covered_sample_ids=covered_sample_ids(incumbent),
        summary=GreedySummary(policy="best_marginal_coverage"),
        accepted_evaluations=[],
        attempt_debug=[],
    )

    result = local_search(
        case,
        all_candidates,
        coverage_index=index,
        greedy_result=greedy_result,
        greedy_config=GreedyConfig(),
        config=LocalSearchConfig(
            max_iterations=1,
            component_gap_s=1000,
            time_padding_s=20,
            max_neighborhoods_per_iteration=1,
            max_neighborhood_candidates=4,
        ),
        cp_config=CPRepairConfig(max_candidates=4, max_calls=4, max_subsets=16),
    )

    assert result.summary.accepted_moves == 1
    assert result.summary.cp_metrics["calls"] == 1
    assert result.summary.cp_metrics["successful_calls"] == 1
    assert result.summary.cp_metrics["call_success_rate"] == pytest.approx(1.0)
    assert result.summary.cp_metrics["improving_solutions"] == 1
    assert result.summary.cp_metrics["improving_success_rate"] == pytest.approx(1.0)
    assert [candidate.candidate_id for candidate in result.selected_candidates] == ["c_left", "c_right"]


def test_cp_metrics_reports_success_rates_and_skips() -> None:
    metrics = CPMetrics(
        calls=4,
        feasible_solutions=3,
        improving_solutions=1,
        skipped_disabled=1,
        skipped_size_limit=2,
    )

    payload = metrics.as_dict()

    assert payload["successful_calls"] == 3
    assert payload["call_success_rate"] == pytest.approx(0.75)
    assert payload["improving_success_rate"] == pytest.approx(0.25)
    assert payload["skipped_calls"] == 3
