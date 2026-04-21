from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
SOLVER_DIR = REPO_ROOT / "solvers" / "aeossp_standard" / "mwis_conflict_graph" / "src"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SOLVER_DIR))

from candidates import CandidateConfig, CandidateSummary, generate_candidates, start_offsets_for_task  # noqa: E402
from case_io import (  # noqa: E402
    AeosspCase,
    AttitudeModel,
    Mission,
    ResourceModel,
    Satellite,
    Task,
    iso_z,
    parse_iso_z,
)
from geometry import (  # noqa: E402
    action_sample_times,
    initial_slew_feasible_from_vectors,
)
from graph import build_conflict_graph, connected_components  # noqa: E402
from mwis import (  # noqa: E402
    MwisConfig,
    select_weighted_independent_set,
    solve_exact_component,
    validate_independent_set,
)
from solution_io import candidates_to_actions  # noqa: E402
from transition import TransitionVectorCache, transition_gap_conflict  # noqa: E402
from validation import (  # noqa: E402
    RepairConfig,
    ValidationIssue,
    ValidationReport,
    battery_issues,
    choose_repair_removal,
    repair_candidates,
    validate_candidates,
)

from candidates import Candidate  # noqa: E402
from experiments.main_solver.run import _parse_json_verifier  # noqa: E402


def _mission() -> Mission:
    return Mission(
        case_id="unit_case",
        horizon_start=datetime(2026, 4, 14, 4, 0, tzinfo=UTC),
        horizon_end=datetime(2026, 4, 14, 5, 0, tzinfo=UTC),
        action_time_step_s=5,
        geometry_sample_step_s=5,
        resource_sample_step_s=10,
    )


def _satellite(satellite_id: str = "sat_a", sensor_type: str = "visible") -> Satellite:
    return Satellite(
        satellite_id=satellite_id,
        norad_catalog_id=1,
        tle_line1="tle1",
        tle_line2="tle2",
        sensor_type=sensor_type,
        attitude_model=AttitudeModel(
            max_slew_velocity_deg_per_s=1.0,
            max_slew_acceleration_deg_per_s2=1.0,
            settling_time_s=2.0,
            max_off_nadir_deg=30.0,
        ),
        resource_model=ResourceModel(
            battery_capacity_wh=1.0,
            initial_battery_wh=1.0,
            idle_power_w=1.0,
            imaging_power_w=1.0,
            slew_power_w=1.0,
            sunlit_charge_power_w=0.0,
        ),
    )


def _task(task_id: str = "task_a", sensor_type: str = "visible") -> Task:
    mission = _mission()
    return Task(
        task_id=task_id,
        name="task",
        latitude_deg=0.0,
        longitude_deg=0.0,
        altitude_m=0.0,
        release_time=mission.horizon_start + timedelta(seconds=10),
        due_time=mission.horizon_start + timedelta(seconds=30),
        required_duration_s=10,
        required_sensor_type=sensor_type,
        weight=3.0,
        target_ecef_m=(1.0, 0.0, 0.0),
    )


def _candidate(
    candidate_id: str,
    *,
    satellite_id: str = "sat_a",
    task_id: str = "task_a",
    start_offset_s: int = 10,
    end_offset_s: int = 20,
    weight: float = 1.0,
) -> Candidate:
    mission = _mission()
    return Candidate(
        candidate_id=candidate_id,
        satellite_id=satellite_id,
        task_id=task_id,
        start_offset_s=start_offset_s,
        end_offset_s=end_offset_s,
        start_time=iso_z(mission.horizon_start + timedelta(seconds=start_offset_s)),
        end_time=iso_z(mission.horizon_start + timedelta(seconds=end_offset_s)),
        task_weight=weight,
        duration_s=end_offset_s - start_offset_s,
    )


def _case_for_candidates(candidates: list[Candidate]) -> AeosspCase:
    satellites = {
        candidate.satellite_id: _satellite(candidate.satellite_id, "visible")
        for candidate in candidates
    }
    tasks = {
        candidate.task_id: _task(candidate.task_id, "visible")
        for candidate in candidates
    }
    return AeosspCase(
        case_dir=Path("."),
        mission=_mission(),
        satellites=satellites,
        tasks=tasks,
    )


def test_iso_z_timestamp_round_trip() -> None:
    parsed = parse_iso_z("2026-04-14T04:00:05Z")

    assert parsed.tzinfo is UTC
    assert iso_z(parsed) == "2026-04-14T04:00:05Z"


def test_action_grid_iteration_respects_window_and_duration() -> None:
    case = AeosspCase(
        case_dir=Path("."),
        mission=_mission(),
        satellites={},
        tasks={"task_a": _task()},
    )

    assert start_offsets_for_task(case, _task()) == [10, 15, 20]
    assert start_offsets_for_task(case, _task(), stride_multiplier=2) == [10, 20]


def test_geometry_sample_times_include_boundaries_and_interior_grid() -> None:
    mission = _mission()
    start = mission.horizon_start + timedelta(seconds=7)
    end = mission.horizon_start + timedelta(seconds=22)

    assert [int((item - mission.horizon_start).total_seconds()) for item in action_sample_times(mission, start, end)] == [
        7,
        10,
        15,
        20,
        22,
    ]


def test_initial_slew_feasibility_from_nadir_vectors() -> None:
    satellite = _satellite()

    assert initial_slew_feasible_from_vectors(
        nadir_vector_eci=np.array([1.0, 0.0, 0.0]),
        target_vector_eci=np.array([1.0, 0.0, 0.0]),
        available_gap_s=2.0,
        satellite=satellite,
    )
    assert not initial_slew_feasible_from_vectors(
        nadir_vector_eci=np.array([1.0, 0.0, 0.0]),
        target_vector_eci=np.array([0.0, 1.0, 0.0]),
        available_gap_s=2.0,
        satellite=satellite,
    )


def test_generate_candidates_filters_sensor_and_keeps_stable_ids(monkeypatch) -> None:
    mission = _mission()
    case = AeosspCase(
        case_dir=Path("."),
        mission=mission,
        satellites={
            "sat_a": _satellite("sat_a", "visible"),
            "sat_b": _satellite("sat_b", "infrared"),
        },
        tasks={
            "task_a": _task("task_a", "visible"),
            "task_b": _task("task_b", "infrared"),
        },
    )

    class DummyPropagation:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("candidates.PropagationContext", DummyPropagation)
    monkeypatch.setattr("candidates.observation_geometry_valid", lambda **kwargs: True)
    monkeypatch.setattr("candidates.initial_slew_feasible", lambda **kwargs: True)

    candidates, summary = generate_candidates(case, CandidateConfig())
    candidate_ids = [item.candidate_id for item in candidates]

    assert candidate_ids == [
        "sat_a|task_a|10",
        "sat_a|task_a|15",
        "sat_a|task_a|20",
        "sat_b|task_b|10",
        "sat_b|task_b|15",
        "sat_b|task_b|20",
    ]
    assert len(candidate_ids) == len(set(candidate_ids))
    assert summary.candidate_count == 6
    assert summary.skipped_sensor_mismatch == 6


def test_candidate_summary_debug_dict_reports_zero_candidate_tasks() -> None:
    case = AeosspCase(
        case_dir=Path("."),
        mission=_mission(),
        satellites={"sat_a": _satellite("sat_a", "visible")},
        tasks={
            "task_a": _task("task_a", "visible"),
            "task_b": _task("task_b", "infrared"),
        },
    )
    summary = CandidateSummary(
        candidate_count=2,
        per_satellite_candidate_counts={"sat_a": 2},
        per_task_candidate_counts={"task_a": 2, "task_b": 0},
    )

    debug_summary = summary.as_debug_dict(case)

    assert debug_summary["zero_candidate_task_count"] == 1
    assert debug_summary["zero_candidate_task_counts_by_sensor"] == {"infrared": 1}
    assert debug_summary["zero_candidate_task_ids"] == ["task_b"]


def test_conflict_graph_adds_duplicate_task_edges_across_satellites(monkeypatch) -> None:
    candidates = [
        _candidate("sat_a|task_a|10", satellite_id="sat_a", task_id="task_a"),
        _candidate("sat_b|task_a|15", satellite_id="sat_b", task_id="task_a", start_offset_s=15, end_offset_s=25),
    ]

    class DummyPropagation:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("graph.PropagationContext", DummyPropagation)
    graph = build_conflict_graph(_case_for_candidates(candidates), candidates)

    assert graph.has_edge("sat_a|task_a|10", "sat_b|task_a|15")
    assert graph.stats.duplicate_task_edge_count == 1


def test_conflict_graph_adds_same_satellite_overlap_edges(monkeypatch) -> None:
    candidates = [
        _candidate("sat_a|task_a|10", task_id="task_a", start_offset_s=10, end_offset_s=25),
        _candidate("sat_a|task_b|20", task_id="task_b", start_offset_s=20, end_offset_s=30),
    ]

    class DummyPropagation:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("graph.PropagationContext", DummyPropagation)
    graph = build_conflict_graph(_case_for_candidates(candidates), candidates)

    assert graph.has_edge("sat_a|task_a|10", "sat_a|task_b|20")
    assert graph.stats.overlap_edge_count == 1


def test_transition_gap_conflict_is_order_independent(monkeypatch) -> None:
    candidate_a = _candidate("sat_a|task_a|10", task_id="task_a", start_offset_s=10, end_offset_s=20)
    candidate_b = _candidate("sat_a|task_b|21", task_id="task_b", start_offset_s=21, end_offset_s=30)
    case = _case_for_candidates([candidate_a, candidate_b])

    def fake_target_vector(task, propagation, satellite_id, instant):
        if task.task_id == "task_a":
            return np.array([1.0, 0.0, 0.0])
        return np.array([0.0, 1.0, 0.0])

    monkeypatch.setattr("transition.target_vector_eci", fake_target_vector)
    vector_cache = TransitionVectorCache(case, propagation=object())

    assert transition_gap_conflict(candidate_a, candidate_b, case=case, vector_cache=vector_cache)
    assert transition_gap_conflict(candidate_b, candidate_a, case=case, vector_cache=vector_cache)


def test_conflict_graph_omits_transition_edge_with_sufficient_gap(monkeypatch) -> None:
    candidates = [
        _candidate("sat_a|task_a|10", task_id="task_a", start_offset_s=10, end_offset_s=20),
        _candidate("sat_a|task_b|250", task_id="task_b", start_offset_s=250, end_offset_s=260),
    ]

    class DummyPropagation:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("graph.PropagationContext", DummyPropagation)
    graph = build_conflict_graph(_case_for_candidates(candidates), candidates)

    assert not graph.has_edge("sat_a|task_a|10", "sat_a|task_b|250")
    assert graph.stats.transition_edge_count == 0


def test_connected_components_are_stable() -> None:
    adjacency = {
        "a": {"b"},
        "b": {"a"},
        "c": set(),
    }

    assert connected_components(adjacency) == [["c"], ["a", "b"]]


def test_exact_tiny_component_prefers_higher_total_weight() -> None:
    candidates = [
        _candidate("a", task_id="task_a", weight=6.0),
        _candidate("b", task_id="task_b", weight=4.0),
        _candidate("c", task_id="task_c", weight=4.0),
    ]
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    adjacency = {
        "a": {"b", "c"},
        "b": {"a"},
        "c": {"a"},
    }

    assert solve_exact_component(
        ["a", "b", "c"],
        candidate_by_id,
        adjacency,
        policy="weight_end_degree",
    ) == {"b", "c"}


def test_greedy_selection_is_deterministic_when_exact_disabled() -> None:
    candidates = [
        _candidate("late", task_id="task_late", start_offset_s=20, end_offset_s=30, weight=5.0),
        _candidate("early", task_id="task_early", start_offset_s=10, end_offset_s=20, weight=5.0),
        _candidate("low", task_id="task_low", start_offset_s=5, end_offset_s=10, weight=1.0),
    ]
    adjacency = {
        "late": {"early"},
        "early": {"late"},
        "low": set(),
    }
    graph = type(
        "ManualGraph",
        (),
        {
            "adjacency": adjacency,
            "stats": None,
        },
    )()

    selected, stats = select_weighted_independent_set(
        candidates,
        graph,
        MwisConfig(max_exact_component_size=0),
    )

    assert [candidate.candidate_id for candidate in selected] == ["low", "early"]
    assert stats.independent_set_valid


def test_mwis_config_allows_non_default_selection_policy() -> None:
    config = MwisConfig.from_mapping(
        {
            "max_exact_component_size": 0,
            "selection_policy": "weight_degree_end",
        }
    )

    assert config.max_exact_component_size == 0
    assert config.selection_policy == "weight_degree_end"


def test_mwis_config_parses_phase_5_search_knobs() -> None:
    config = MwisConfig.from_mapping(
        {
            "time_limit_s": 1.5,
            "max_local_passes": 3,
            "population_size": 2,
            "recombination_rounds": 5,
        }
    )

    assert config.time_limit_s == 1.5
    assert config.max_local_passes == 3
    assert config.population_size == 2
    assert config.recombination_rounds == 5


def test_independent_set_validation_rejects_adjacent_selected_candidates() -> None:
    adjacency = {
        "a": {"b"},
        "b": {"a"},
        "c": set(),
    }

    assert not validate_independent_set({"a", "b"}, adjacency)
    assert validate_independent_set({"a", "c"}, adjacency)


def test_candidates_decode_to_sorted_observation_actions() -> None:
    candidates = [
        _candidate("sat_b|task_b|30", satellite_id="sat_b", task_id="task_b", start_offset_s=30, end_offset_s=40),
        _candidate("sat_a|task_a|10", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20),
    ]

    assert candidates_to_actions(candidates) == [
        {
            "type": "observation",
            "satellite_id": "sat_a",
            "task_id": "task_a",
            "start_time": "2026-04-14T04:00:10Z",
            "end_time": "2026-04-14T04:00:20Z",
        },
        {
            "type": "observation",
            "satellite_id": "sat_b",
            "task_id": "task_b",
            "start_time": "2026-04-14T04:00:30Z",
            "end_time": "2026-04-14T04:00:40Z",
        },
    ]


def test_local_improvement_applies_weighted_two_swap(monkeypatch) -> None:
    candidates = [
        _candidate("blocker", task_id="task_blocker", weight=5.0, start_offset_s=5, end_offset_s=15),
        _candidate("left", task_id="task_left", weight=4.0, start_offset_s=20, end_offset_s=30),
        _candidate("right", task_id="task_right", weight=4.0, start_offset_s=35, end_offset_s=45),
    ]
    adjacency = {
        "blocker": {"left", "right"},
        "left": {"blocker"},
        "right": {"blocker"},
    }
    graph = type(
        "ManualGraph",
        (),
        {
            "adjacency": adjacency,
            "stats": None,
        },
    )()

    def fake_greedy(component, candidate_by_id, adjacency_map, *, policy, reverse=False):
        return {"blocker"}

    monkeypatch.setattr("mwis.solve_greedy_component", fake_greedy)
    selected, stats = select_weighted_independent_set(
        candidates,
        graph,
        MwisConfig(
            max_exact_component_size=0,
            max_local_passes=4,
            population_size=1,
            recombination_rounds=0,
        ),
    )

    assert [candidate.candidate_id for candidate in selected] == ["left", "right"]
    assert stats.local_improvement_count >= 1
    assert stats.successful_two_swap_count == 1
    assert stats.independent_set_valid


def test_recombination_can_improve_incumbent_without_local_search(monkeypatch) -> None:
    candidates = [
        _candidate("l1", task_id="task_l1", weight=2.0, start_offset_s=10, end_offset_s=20),
        _candidate("l2", task_id="task_l2", weight=2.0, start_offset_s=15, end_offset_s=25),
        _candidate("r1", task_id="task_r1", weight=2.0, start_offset_s=30, end_offset_s=40),
        _candidate("r2", task_id="task_r2", weight=2.0, start_offset_s=35, end_offset_s=45),
    ]
    adjacency = {
        "l1": {"l2"},
        "l2": {"l1", "r2"},
        "r1": {"r2"},
        "r2": {"l2", "r1"},
    }
    graph = type(
        "ManualGraph",
        (),
        {
            "adjacency": adjacency,
            "stats": None,
        },
    )()

    def fake_greedy(component, candidate_by_id, adjacency_map, *, policy, reverse=False):
        if reverse:
            return {"l2"}
        if policy == "weight_end_degree":
            return {"l1", "r2"}
        return {"l2", "r1"}

    monkeypatch.setattr("mwis.solve_greedy_component", fake_greedy)

    selected, stats = select_weighted_independent_set(
        candidates,
        graph,
        MwisConfig(
            max_exact_component_size=0,
            max_local_passes=0,
            population_size=3,
            recombination_rounds=2,
        ),
    )

    assert [candidate.candidate_id for candidate in selected] == ["l1", "r1"]
    assert stats.recombination_attempt_count >= 1
    assert stats.recombination_win_count >= 1
    assert stats.incumbent_source == "recombination"


def test_time_budget_returns_valid_baseline_incumbent() -> None:
    candidates = [
        _candidate("early", task_id="task_early", weight=5.0, start_offset_s=10, end_offset_s=20),
        _candidate("late", task_id="task_late", weight=5.0, start_offset_s=20, end_offset_s=30),
        _candidate("free", task_id="task_free", weight=1.0, start_offset_s=35, end_offset_s=45),
    ]
    adjacency = {
        "early": {"late"},
        "late": {"early"},
        "free": set(),
    }
    graph = type(
        "ManualGraph",
        (),
        {
            "adjacency": adjacency,
            "stats": None,
        },
    )()

    selected, stats = select_weighted_independent_set(
        candidates,
        graph,
        MwisConfig(
            max_exact_component_size=0,
            time_limit_s=0.0,
            max_local_passes=4,
            population_size=2,
            recombination_rounds=2,
        ),
    )

    assert [candidate.candidate_id for candidate in selected] == ["early", "free"]
    assert stats.time_limit_hit
    assert stats.search_stop_reason == "time_limit"
    assert stats.independent_set_valid


def test_local_validation_rejects_duplicate_tasks(monkeypatch) -> None:
    candidates = [
        _candidate("sat_a|task_a|10", satellite_id="sat_a", task_id="task_a"),
        _candidate("sat_b|task_a|15", satellite_id="sat_b", task_id="task_a", start_offset_s=15, end_offset_s=25),
    ]

    class DummyPropagation:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("validation.PropagationContext", DummyPropagation)
    monkeypatch.setattr("validation.schedule_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr("validation.battery_issues", lambda *args, **kwargs: ([], {}))

    report = validate_candidates(_case_for_candidates(candidates), candidates)

    assert not report.valid
    assert [issue.reason for issue in report.issues] == ["duplicate_task"]


def test_local_validation_rejects_overlap(monkeypatch) -> None:
    candidates = [
        _candidate("sat_a|task_a|10", task_id="task_a", start_offset_s=10, end_offset_s=25),
        _candidate("sat_a|task_b|20", task_id="task_b", start_offset_s=20, end_offset_s=30),
    ]

    class DummyPropagation:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("validation.PropagationContext", DummyPropagation)
    monkeypatch.setattr("validation._initial_slew_required_s", lambda *args, **kwargs: 0.0)
    monkeypatch.setattr("validation.battery_issues", lambda *args, **kwargs: ([], {}))

    report = validate_candidates(_case_for_candidates(candidates), candidates)

    assert not report.valid
    assert "overlap" in {issue.reason for issue in report.issues}


def test_local_validation_rejects_transition_gap(monkeypatch) -> None:
    candidates = [
        _candidate("sat_a|task_a|10", task_id="task_a", start_offset_s=10, end_offset_s=20),
        _candidate("sat_a|task_b|21", task_id="task_b", start_offset_s=21, end_offset_s=30),
    ]

    class DummyPropagation:
        def __init__(self, *args, **kwargs):
            pass

    class FakeTransition:
        feasible = False
        available_gap_s = 1.0
        required_gap_s = 9.0

    monkeypatch.setattr("validation.PropagationContext", DummyPropagation)
    monkeypatch.setattr("validation._initial_slew_required_s", lambda *args, **kwargs: 0.0)
    monkeypatch.setattr("validation.transition_result", lambda *args, **kwargs: FakeTransition())
    monkeypatch.setattr("validation.battery_issues", lambda *args, **kwargs: ([], {}))

    report = validate_candidates(_case_for_candidates(candidates), candidates)

    assert not report.valid
    assert "transition_gap" in {issue.reason for issue in report.issues}


def test_local_battery_approximation_reports_depletion(monkeypatch) -> None:
    candidate = _candidate("sat_a|task_a|10", task_id="task_a", start_offset_s=10, end_offset_s=20)
    case = _case_for_candidates([candidate])
    satellite = case.satellites["sat_a"]
    case.satellites["sat_a"] = Satellite(
        satellite_id=satellite.satellite_id,
        norad_catalog_id=satellite.norad_catalog_id,
        tle_line1=satellite.tle_line1,
        tle_line2=satellite.tle_line2,
        sensor_type=satellite.sensor_type,
        attitude_model=satellite.attitude_model,
        resource_model=ResourceModel(
            battery_capacity_wh=1.0,
            initial_battery_wh=0.01,
            idle_power_w=100.0,
            imaging_power_w=0.0,
            slew_power_w=0.0,
            sunlit_charge_power_w=0.0,
        ),
    )

    monkeypatch.setattr("validation._initial_slew_required_s", lambda *args, **kwargs: 0.0)
    monkeypatch.setattr("validation.is_sunlit", lambda *args, **kwargs: False)

    issues, traces = battery_issues(case, [candidate], propagation=object())

    assert "battery_depletion" in {issue.reason for issue in issues}
    assert traces["sat_a"].min_battery_wh < 0.0


def test_repair_selection_removes_lowest_priority_implicated_candidate() -> None:
    low = _candidate("low", task_id="task_low", weight=1.0)
    high = _candidate("high", task_id="task_high", weight=5.0)
    report = ValidationReport(
        valid=False,
        issue_count=1,
        issues=[
            ValidationIssue(
                reason="transition_gap",
                message="bad transition",
                candidate_ids=("high", "low"),
            )
        ],
    )

    removal, reason = choose_repair_removal(report, [high, low])

    assert removal == low
    assert reason == "transition_gap"


def test_bounded_repair_terminates(monkeypatch) -> None:
    candidates = [
        _candidate("a", task_id="task_a", weight=1.0),
        _candidate("b", task_id="task_b", weight=1.0),
    ]
    invalid_report = ValidationReport(
        valid=False,
        issue_count=1,
        issues=[
            ValidationIssue(
                reason="transition_gap",
                message="bad transition",
                candidate_ids=("a", "b"),
            )
        ],
    )

    monkeypatch.setattr("validation.validate_candidates", lambda *args, **kwargs: invalid_report)

    result = repair_candidates(
        _case_for_candidates(candidates),
        candidates,
        config=RepairConfig(max_repair_iterations=1),
    )

    assert len(result.reports) == 2
    assert len(result.removals) == 1
    assert result.terminated_reason == "max_iterations"


def test_parse_json_verifier_records_aeossp_report() -> None:
    payload = {
        "valid": True,
        "metrics": {"CR": 0.5},
        "violations": [],
        "diagnostics": {"note": "ok"},
    }

    parsed = _parse_json_verifier(json_dumps(payload), 0)

    assert parsed["status"] == "valid"
    assert parsed["valid"] is True
    assert parsed["metrics"] == {"CR": 0.5}
    assert parsed["diagnostics"] == {"note": "ok"}


def test_parse_json_verifier_rejects_missing_valid() -> None:
    parsed = _parse_json_verifier("{}", 1)

    assert parsed["status"] == "error"
    assert parsed["valid"] is None


def json_dumps(payload: dict) -> str:
    import json

    return json.dumps(payload)
