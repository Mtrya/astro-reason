from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from solvers.aeossp_standard.greedy_lns.src.candidates import (  # noqa: E402
    Candidate,
    CandidateConfig,
    CandidateSummary,
    generate_candidates,
    start_offsets_for_task,
)
from solvers.aeossp_standard.greedy_lns.src.case_io import (  # noqa: E402
    AeosspCase,
    AttitudeModel,
    Mission,
    ResourceModel,
    Satellite,
    Task,
    iso_z,
    load_case,
    load_solver_config,
    parse_iso_z,
)
from solvers.aeossp_standard.greedy_lns.src.components import (  # noqa: E402
    Component,
    build_component_index,
)
from solvers.aeossp_standard.greedy_lns.src.geometry import (  # noqa: E402
    action_sample_times,
    angle_between_deg,
    initial_slew_feasible_from_vectors,
    slew_time_s,
)
from solvers.aeossp_standard.greedy_lns.src.insertion import (  # noqa: E402
    InsertionConfig,
    InsertionResult,
    greedy_insertion,
)
from solvers.aeossp_standard.greedy_lns.src.local_search import (  # noqa: E402
    LocalSearchConfig,
    LocalSearchResult,
    _marginal_profit,
    _recompute_component,
    _by_satellite,
    local_search,
)
from solvers.aeossp_standard.greedy_lns.src.solution_io import (  # noqa: E402
    candidates_to_actions,
    write_empty_solution,
)
from solvers.aeossp_standard.greedy_lns.src.transition import (  # noqa: E402
    TransitionVectorCache,
    transition_gap_conflict,
    transition_result,
)
from solvers.aeossp_standard.greedy_lns.src.validation import (  # noqa: E402
    RepairConfig,
    ValidationIssue,
    candidate_shape_issues,
    repair_schedule,
)


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
        utility=weight / max(1, end_offset_s - start_offset_s),
        utility_tie_break=(-weight, 30, 0.0, candidate_id),
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


def test_load_case_rejects_initial_battery_above_capacity(tmp_path: Path) -> None:
    (tmp_path / "mission.yaml").write_text(
        """mission:
  case_id: overfull_battery
  horizon_start: "2026-04-14T04:00:00Z"
  horizon_end: "2026-04-14T05:00:00Z"
  action_time_step_s: 5
  geometry_sample_step_s: 5
  resource_sample_step_s: 10
""",
        encoding="utf-8",
    )
    (tmp_path / "satellites.yaml").write_text(
        """satellites:
- satellite_id: sat_001
  norad_catalog_id: 28051
  tle_line1: 1 28051U 03046A   26103.92936350  .00000126  00000+0  55914-4 0  9994
  tle_line2: 2 28051  98.1985 143.5711 0064246 173.9227 286.4737 14.36137850171300
  sensor:
    sensor_type: visible
  attitude_model:
    max_slew_velocity_deg_per_s: 1.8
    max_slew_acceleration_deg_per_s2: 0.4
    settling_time_s: 2.0
    max_off_nadir_deg: 30.0
  resource_model:
    battery_capacity_wh: 1300.0
    initial_battery_wh: 1300.1
    idle_power_w: 20.0
    imaging_power_w: 420.0
    slew_power_w: 360.0
    sunlit_charge_power_w: 85.0
""",
        encoding="utf-8",
    )
    (tmp_path / "tasks.yaml").write_text(
        """tasks:
- task_id: task_0001
  name: task
  latitude_deg: 0.0
  longitude_deg: 0.0
  altitude_m: 0.0
  release_time: "2026-04-14T04:10:00Z"
  due_time: "2026-04-14T04:20:00Z"
  required_duration_s: 10
  required_sensor_type: visible
  weight: 1.0
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="initial_battery_wh"):
        load_case(tmp_path)


def test_load_solver_config_rejects_explicit_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="config path does not exist"):
        load_solver_config(tmp_path / "missing")


def test_load_solver_config_rejects_empty_explicit_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no supported config file found"):
        load_solver_config(tmp_path)


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
    offsets = [
        int((item - mission.horizon_start).total_seconds())
        for item in action_sample_times(mission, start, end)
    ]
    assert offsets == [7, 10, 15, 20, 22]


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

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.candidates.PropagationContext", DummyPropagation)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.candidates.observation_geometry_valid", lambda **kwargs: True)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.candidates.initial_slew_feasible", lambda **kwargs: True)

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
    assert summary.per_satellite_candidate_counts["sat_a"] == 3
    assert summary.per_satellite_candidate_counts["sat_b"] == 3
    assert summary.per_task_candidate_counts["task_a"] == 3
    assert summary.per_task_candidate_counts["task_b"] == 3


def test_angle_between_deg_edge_cases() -> None:
    assert angle_between_deg(np.array([1.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0])) == pytest.approx(0.0)
    assert angle_between_deg(np.array([1.0, 0.0, 0.0]), np.array([-1.0, 0.0, 0.0])) == pytest.approx(180.0)
    assert angle_between_deg(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0])) == pytest.approx(0.0)


def test_slew_time_triangular_vs_trapezoidal() -> None:
    # Triangular profile: small angle
    t_tri = slew_time_s(1.0, 2.0, 2.0)
    assert t_tri == pytest.approx(2.0 * (1.0 / 2.0) ** 0.5)
    # Trapezoidal profile: large angle
    t_trap = slew_time_s(10.0, 2.0, 2.0)
    ramp_time = 2.0 / 2.0
    threshold = 2.0 * 2.0 / 2.0
    cruise = 10.0 - threshold
    expected = (2.0 * ramp_time) + (cruise / 2.0)
    assert t_trap == pytest.approx(expected)
    # Zero angle
    assert slew_time_s(0.0, 2.0, 2.0) == pytest.approx(0.0)


def test_transition_result_cross_satellite_is_always_feasible() -> None:
    case = _case_for_candidates([])
    a = _candidate("a", satellite_id="sat_a", start_offset_s=10, end_offset_s=20)
    b = _candidate("b", satellite_id="sat_b", start_offset_s=30, end_offset_s=40)

    class DummyCache:
        pass

    result = transition_result(a, b, case=case, vector_cache=DummyCache())  # type: ignore[arg-type]
    assert result.feasible
    assert result.required_gap_s == 0.0
    assert result.available_gap_s == float("inf")


def test_transition_gap_conflict_same_satellite_overlap() -> None:
    case = _case_for_candidates([])
    a = _candidate("a", satellite_id="sat_a", start_offset_s=10, end_offset_s=25)
    b = _candidate("b", satellite_id="sat_a", start_offset_s=20, end_offset_s=30)

    class DummyCache:
        pass

    assert transition_gap_conflict(a, b, case=case, vector_cache=DummyCache())  # type: ignore[arg-type]


def test_candidates_to_actions_sorts_and_formats() -> None:
    c1 = _candidate("c1", satellite_id="sat_a", task_id="task_a", start_offset_s=20, end_offset_s=30)
    c2 = _candidate("c2", satellite_id="sat_a", task_id="task_b", start_offset_s=10, end_offset_s=20)
    actions = candidates_to_actions([c1, c2])
    assert actions[0]["task_id"] == "task_b"
    assert actions[1]["task_id"] == "task_a"
    for action in actions:
        assert action["type"] == "observation"
        assert "satellite_id" in action
        assert "start_time" in action
        assert "end_time" in action


def test_write_empty_solution_creates_valid_json(tmp_path: Path) -> None:
    path = write_empty_solution(tmp_path)
    assert path.exists()
    import json
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {"actions": []}


def test_candidate_config_from_mapping_defaults() -> None:
    cfg = CandidateConfig.from_mapping(None)
    assert cfg.candidate_stride_multiplier == 1
    assert cfg.max_candidates is None
    assert cfg.max_candidates_per_task is None
    assert not cfg.debug


def test_candidate_config_caps_reject_non_positive() -> None:
    with pytest.raises(ValueError, match="positive integers"):
        CandidateConfig.from_mapping({"max_candidates": 0})


def test_candidate_summary_zero_task_tracking() -> None:
    mission = _mission()
    case = AeosspCase(
        case_dir=Path("."),
        mission=mission,
        satellites={"sat_a": _satellite("sat_a", "visible")},
        tasks={
            "task_a": _task("task_a", "visible"),
            "task_b": _task("task_b", "infrared"),
        },
    )
    summary = CandidateSummary()
    summary.per_task_candidate_counts["task_a"] = 2
    debug = summary.as_debug_dict(case)
    assert debug["zero_candidate_task_count"] == 1
    assert debug["zero_candidate_task_ids"] == ["task_b"]
    assert debug["zero_candidate_task_counts_by_sensor"] == {"infrared": 1}



def test_greedy_insertion_selects_higher_utility_first(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20, weight=5.0)
    b = _candidate("b", satellite_id="sat_a", task_id="task_a", start_offset_s=30, end_offset_s=40, weight=1.0)
    case = _case_for_candidates([a, b])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.initial_slew_feasible", lambda **kwargs: True)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.transition_result", lambda *args, **kwargs: type("R", (), {"feasible": True})())

    result = greedy_insertion(case, [a, b])
    assert len(result.selected) == 1
    assert result.selected[0].candidate_id == "a"
    assert result.stats.candidates_skipped_duplicate_task == 1


def test_greedy_insertion_rejects_overlap(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=25, weight=5.0)
    b = _candidate("b", satellite_id="sat_a", task_id="task_b", start_offset_s=20, end_offset_s=30, weight=1.0)
    case = _case_for_candidates([a, b])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.initial_slew_feasible", lambda **kwargs: True)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.transition_result", lambda *args, **kwargs: type("R", (), {"feasible": True})())

    result = greedy_insertion(case, [a, b])
    assert len(result.selected) == 1
    assert result.selected[0].candidate_id == "a"
    assert result.stats.candidates_rejected_overlap == 1


def test_greedy_insertion_rejects_insufficient_transition(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20, weight=5.0)
    b = _candidate("b", satellite_id="sat_a", task_id="task_b", start_offset_s=22, end_offset_s=32, weight=1.0)
    case = _case_for_candidates([a, b])

    class FakeResult:
        feasible = False

    def fake_transition(previous, current, **kwargs):
        if previous.candidate_id == "a" and current.candidate_id == "b":
            return FakeResult()
        return type("R", (), {"feasible": True})()

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.initial_slew_feasible", lambda **kwargs: True)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.transition_result", fake_transition)

    result = greedy_insertion(case, [a, b])
    assert len(result.selected) == 1
    assert result.selected[0].candidate_id == "a"
    assert result.stats.candidates_rejected_transition == 1


def test_greedy_insertion_respects_initial_slew(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20, weight=5.0)
    case = _case_for_candidates([a])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.initial_slew_feasible", lambda **kwargs: False)

    result = greedy_insertion(case, [a])
    assert len(result.selected) == 0
    assert result.stats.candidates_rejected_initial_slew == 1


def test_greedy_insertion_insert_between_feasible(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20, weight=1.0)
    c = _candidate("c", satellite_id="sat_a", task_id="task_c", start_offset_s=30, end_offset_s=40, weight=1.0)
    b = _candidate("b", satellite_id="sat_a", task_id="task_b", start_offset_s=22, end_offset_s=28, weight=1.0)
    case = _case_for_candidates([a, b, c])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.initial_slew_feasible", lambda **kwargs: True)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.transition_result", lambda *args, **kwargs: type("R", (), {"feasible": True})())

    result = greedy_insertion(case, [a, b, c])
    ids = [item.candidate_id for item in result.selected]
    assert ids == ["a", "b", "c"]
    assert result.stats.candidates_inserted == 3


def test_greedy_insertion_cross_satellite_same_task_rejected(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_x", start_offset_s=10, end_offset_s=20, weight=5.0)
    b = _candidate("b", satellite_id="sat_b", task_id="task_x", start_offset_s=30, end_offset_s=40, weight=1.0)
    case = _case_for_candidates([a, b])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.initial_slew_feasible", lambda **kwargs: True)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.transition_result", lambda *args, **kwargs: type("R", (), {"feasible": True})())

    result = greedy_insertion(case, [a, b])
    assert len(result.selected) == 1
    assert result.selected[0].candidate_id == "a"
    assert result.stats.candidates_skipped_duplicate_task == 1


def test_repair_removes_battery_violation(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20, weight=5.0)
    b = _candidate("b", satellite_id="sat_a", task_id="task_b", start_offset_s=30, end_offset_s=40, weight=1.0)
    case = _case_for_candidates([a, b])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.validation.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.validation.schedule_issues", lambda case, candidates, **kwargs: [])

    def fake_battery_issues(case, candidates, **kwargs):
        if any(c.candidate_id == "b" for c in candidates):
            return (
                [ValidationIssue(reason="battery_depletion", message="battery depleted", satellite_id="sat_a", offset_s=35.0)],
                {},
            )
        return ([], {})

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.validation.battery_issues", fake_battery_issues)

    result = repair_schedule(case, [a, b], config=RepairConfig(max_repair_iterations=10))
    assert len(result.candidates) == 1
    assert result.candidates[0].candidate_id == "a"
    assert result.terminated_reason == "valid"
    assert len(result.removals) == 1
    assert result.removals[0].candidate_id == "b"


def test_repair_passes_when_valid(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20, weight=5.0)
    case = _case_for_candidates([a])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.validation.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.validation.schedule_issues", lambda case, candidates, **kwargs: [])
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.validation.battery_issues", lambda case, candidates, **kwargs: ([], {}))

    result = repair_schedule(case, [a], config=RepairConfig(max_repair_iterations=10))
    assert len(result.candidates) == 1
    assert result.terminated_reason == "valid"
    assert len(result.removals) == 0


def test_component_graph_overlap_edge(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=25)
    b = _candidate("b", satellite_id="sat_a", task_id="task_b", start_offset_s=20, end_offset_s=30)
    case = _case_for_candidates([a, b])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.components.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.components.transition_gap_conflict", lambda *args, **kwargs: False)

    index = build_component_index(case, [a, b])
    assert index.stats.component_count == 1
    assert index.components[0].size == 2


def test_component_graph_no_edge_for_temporal_separation(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20)
    b = _candidate("b", satellite_id="sat_a", task_id="task_b", start_offset_s=100, end_offset_s=110)
    case = _case_for_candidates([a, b])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.components.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.components.transition_gap_conflict", lambda *args, **kwargs: False)

    index = build_component_index(case, [a, b])
    assert index.stats.component_count == 2
    assert index.stats.singleton_count == 2


def test_component_graph_edge_for_insufficient_transition(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20)
    b = _candidate("b", satellite_id="sat_a", task_id="task_b", start_offset_s=22, end_offset_s=32)
    case = _case_for_candidates([a, b])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.components.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.components.transition_gap_conflict", lambda *args, **kwargs: True)

    index = build_component_index(case, [a, b])
    assert index.stats.component_count == 1
    assert index.components[0].size == 2


def test_component_extraction_is_deterministic(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20)
    b = _candidate("b", satellite_id="sat_a", task_id="task_b", start_offset_s=22, end_offset_s=32)
    c = _candidate("c", satellite_id="sat_a", task_id="task_c", start_offset_s=40, end_offset_s=50)
    case = _case_for_candidates([a, b, c])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.components.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.components.transition_gap_conflict", lambda *args, **kwargs: True)

    index1 = build_component_index(case, [a, b, c])
    index2 = build_component_index(case, [a, b, c])
    assert [c.component_id for c in index1.components] == [c.component_id for c in index2.components]


def test_marginal_profit_free_task() -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", weight=5.0)
    scheduled = {a.task_id: a}
    free = _candidate("b", satellite_id="sat_a", task_id="task_b", weight=3.0)
    assert _marginal_profit(free, scheduled) == 3.0


def test_marginal_profit_external_alternative() -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_x", weight=5.0)
    b = _candidate("b", satellite_id="sat_b", task_id="task_x", weight=3.0)
    scheduled = {a.task_id: a}
    assert _marginal_profit(b, scheduled) == 3.0 - 5.0


def test_marginal_profit_internal_alternative() -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_x", weight=5.0)
    b = _candidate("b", satellite_id="sat_a", task_id="task_x", weight=3.0)
    scheduled = {}
    assert _marginal_profit(b, scheduled) == 3.0


def test_local_search_accepted_improving_move(monkeypatch) -> None:
    low = _candidate("low", satellite_id="sat_a", task_id="task_x", start_offset_s=10, end_offset_s=20, weight=1.0)
    high = _candidate("high", satellite_id="sat_a", task_id="task_x", start_offset_s=10, end_offset_s=20, weight=5.0)
    case = _case_for_candidates([low, high])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.local_search.build_component_index", lambda case, candidates: type("Idx", (), {
        "components": [
            type("Comp", (), {
                "satellite_id": "sat_a",
                "component_id": "sat_a::root",
                "candidates": (low, high),
                "size": 2,
            })()
        ],
        "stats": type("Stats", (), {"component_count": 1, "largest_component_size": 2})(),
    })())
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.local_search.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.local_search.TransitionVectorCache", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.local_search.transition_result", lambda *args, **kwargs: type("R", (), {"feasible": True})())
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.local_search.initial_slew_feasible", lambda **kwargs: True)

    greedy_solution = [low]
    result = local_search(case, [low, high], greedy_solution, config=LocalSearchConfig(max_local_search_iterations=10))
    assert result.stats.moves_accepted >= 1
    assert result.stats.final_objective == 5.0


def test_local_search_rejected_non_improving_move(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20, weight=5.0)
    case = _case_for_candidates([a])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.local_search.build_component_index", lambda case, candidates: type("Idx", (), {
        "components": [
            type("Comp", (), {
                "satellite_id": "sat_a",
                "component_id": "sat_a::root",
                "candidates": (a,),
                "size": 1,
            })()
        ],
        "stats": type("Stats", (), {"component_count": 1, "largest_component_size": 1})(),
    })())
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.local_search.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.local_search.TransitionVectorCache", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.local_search.transition_result", lambda *args, **kwargs: type("R", (), {"feasible": True})())
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.local_search.initial_slew_feasible", lambda **kwargs: True)

    greedy_solution = [a]
    result = local_search(case, [a], greedy_solution, config=LocalSearchConfig(max_local_search_iterations=10))
    assert result.stats.moves_accepted == 0
    assert result.stats.final_objective == 5.0


def test_local_search_restart_determinism(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20, weight=5.0)
    case = _case_for_candidates([a])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.local_search.build_component_index", lambda case, candidates: type("Idx", (), {
        "components": [],
        "stats": type("Stats", (), {"component_count": 0, "largest_component_size": 0})(),
    })())
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.local_search.PropagationContext", lambda *args, **kwargs: None)

    greedy_solution = [a]
    result1 = local_search(case, [a], greedy_solution, config=LocalSearchConfig(restart_count=2, random_seed=42))
    result2 = local_search(case, [a], greedy_solution, config=LocalSearchConfig(restart_count=2, random_seed=42))
    assert result1.stats.stop_reason == result2.stats.stop_reason
    assert result1.stats.final_objective == result2.stats.final_objective


def test_candidate_shape_issues_catch_duration_mismatch(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20, weight=5.0)
    case = _case_for_candidates([a])
    # Create a new task with a different required_duration_s
    task = case.tasks["task_a"]
    new_task = task.__class__(
        task_id=task.task_id,
        name=task.name,
        latitude_deg=task.latitude_deg,
        longitude_deg=task.longitude_deg,
        altitude_m=task.altitude_m,
        release_time=task.release_time,
        due_time=task.due_time,
        required_duration_s=15,
        required_sensor_type=task.required_sensor_type,
        weight=task.weight,
        target_ecef_m=task.target_ecef_m,
    )
    new_case = AeosspCase(
        case_dir=case.case_dir,
        mission=case.mission,
        satellites=case.satellites,
        tasks={**case.tasks, "task_a": new_task},
    )
    issues = candidate_shape_issues(new_case, [a])
    assert any(i.reason == "duration_mismatch" for i in issues)


def test_candidate_shape_issues_catch_grid_misalignment(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20, weight=5.0)
    case = _case_for_candidates([a])
    # Create a new case with a larger action_time_step_s
    mission = case.mission
    new_mission = mission.__class__(
        case_id=mission.case_id,
        horizon_start=mission.horizon_start,
        horizon_end=mission.horizon_end,
        action_time_step_s=7,
        geometry_sample_step_s=mission.geometry_sample_step_s,
        resource_sample_step_s=mission.resource_sample_step_s,
    )
    new_case = AeosspCase(
        case_dir=case.case_dir,
        mission=new_mission,
        satellites=case.satellites,
        tasks=case.tasks,
    )
    issues = candidate_shape_issues(new_case, [a])
    assert any(i.reason == "grid_misalignment" for i in issues)


def test_greedy_insertion_with_minimize_transition_increment(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20, weight=5.0)
    b = _candidate("b", satellite_id="sat_a", task_id="task_b", start_offset_s=30, end_offset_s=40, weight=3.0)
    c = _candidate("c", satellite_id="sat_a", task_id="task_c", start_offset_s=22, end_offset_s=28, weight=1.0)
    case = _case_for_candidates([a, b, c])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.initial_slew_feasible", lambda **kwargs: True)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.transition_result", lambda *args, **kwargs: type("R", (), {"feasible": True, "required_gap_s": 1.0})())

    result = greedy_insertion(case, [a, b, c], config=InsertionConfig(minimize_transition_increment=True))
    ids = [item.candidate_id for item in result.selected]
    assert ids == ["a", "c", "b"]
    assert result.stats.candidates_inserted == 3


def test_greedy_insertion_minimize_rejects_infeasible(monkeypatch) -> None:
    a = _candidate("a", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=25, weight=5.0)
    b = _candidate("b", satellite_id="sat_a", task_id="task_b", start_offset_s=20, end_offset_s=30, weight=1.0)
    case = _case_for_candidates([a, b])

    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.PropagationContext", lambda *args, **kwargs: None)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.initial_slew_feasible", lambda **kwargs: True)
    monkeypatch.setattr("solvers.aeossp_standard.greedy_lns.src.insertion.transition_result", lambda *args, **kwargs: type("R", (), {"feasible": True, "required_gap_s": 1.0})())

    result = greedy_insertion(case, [a, b], config=InsertionConfig(minimize_transition_increment=True))
    assert len(result.selected) == 1
    assert result.selected[0].candidate_id == "a"
    assert result.stats.candidates_rejected_overlap == 1
