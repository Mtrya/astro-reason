from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
import time

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from solvers.aeossp_standard.mwis_conflict_graph.src.candidates import (  # noqa: E402
    Candidate,
    CandidateConfig,
    CandidateSummary,
    generate_candidates,
    start_offsets_for_task,
)
from solvers.aeossp_standard.mwis_conflict_graph.src.case_io import (  # noqa: E402
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
from solvers.aeossp_standard.mwis_conflict_graph.src.geometry import (  # noqa: E402
    action_sample_times,
    initial_slew_feasible_from_vectors,
)
from solvers.aeossp_standard.mwis_conflict_graph.src.graph import (  # noqa: E402
    GraphBuildConfig,
    _build_conflict_graph_legacy,
    build_conflict_graph,
    connected_components,
)
from solvers.aeossp_standard.mwis_conflict_graph.src.mwis import (  # noqa: E402
    MwisConfig,
    select_weighted_independent_set,
    solve_exact_component,
    validate_independent_set,
)
from solvers.aeossp_standard.mwis_conflict_graph.src.reduction import (  # noqa: E402
    reduce_component,
)
from solvers.aeossp_standard.mwis_conflict_graph.src.solution_io import (  # noqa: E402
    candidates_to_actions,
)
from solvers.aeossp_standard.mwis_conflict_graph.src.transition import (  # noqa: E402
    TransitionVectorCache,
    transition_gap_conflict,
)
from solvers.aeossp_standard.mwis_conflict_graph.src.validation import (  # noqa: E402
    RepairConfig,
    ValidationIssue,
    ValidationReport,
    battery_issues,
    choose_repair_removal,
    repair_candidates,
    validate_candidates,
)
from solvers.aeossp_standard.mwis_conflict_graph.src.solve import (  # noqa: E402
    BudgetConfig,
    _build_status as build_status_payload,
    _budget_status,
    _timing_with_accounting,
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
        """
mission:
  case_id: overfull_battery
  horizon_start: "2026-04-14T04:00:00Z"
  horizon_end: "2026-04-14T05:00:00Z"
  action_time_step_s: 5
  geometry_sample_step_s: 5
  resource_sample_step_s: 10
""".lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "satellites.yaml").write_text(
        """
satellites:
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
""".lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "tasks.yaml").write_text(
        """
tasks:
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
""".lstrip(),
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

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.candidates.PropagationContext", DummyPropagation)
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.candidates.observation_geometry_valid", lambda **kwargs: True)
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.candidates.initial_slew_feasible", lambda **kwargs: True)

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


def _patch_fast_candidate_generation(monkeypatch) -> None:
    class DummyPropagation:
        def __init__(self, *args, **kwargs):
            pass

    class FakeProcessPoolExecutor:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def map(self, function, *iterables):
            return [function(*args) for args in zip(*iterables)]

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.candidates.PropagationContext", DummyPropagation)
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.candidates.ProcessPoolExecutor", FakeProcessPoolExecutor)
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.candidates.observation_geometry_valid", lambda **kwargs: True)
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.candidates.initial_slew_feasible", lambda **kwargs: True)


def test_parallel_candidate_generation_matches_serial_order_and_summary(monkeypatch) -> None:
    mission = _mission()
    case = AeosspCase(
        case_dir=Path("."),
        mission=mission,
        satellites={
            "sat_b": _satellite("sat_b", "infrared"),
            "sat_a": _satellite("sat_a", "visible"),
        },
        tasks={
            "task_b": _task("task_b", "infrared"),
            "task_a": _task("task_a", "visible"),
        },
    )
    _patch_fast_candidate_generation(monkeypatch)

    serial_candidates, serial_summary = generate_candidates(
        case,
        CandidateConfig(candidate_workers=1),
    )
    parallel_candidates, parallel_summary = generate_candidates(
        case,
        CandidateConfig(candidate_workers=2),
    )

    assert [item.candidate_id for item in parallel_candidates] == [
        item.candidate_id for item in serial_candidates
    ]
    assert parallel_summary.as_dict() == serial_summary.as_dict()


def test_parallel_candidate_generation_preserves_cap_accounting(monkeypatch) -> None:
    mission = _mission()
    case = AeosspCase(
        case_dir=Path("."),
        mission=mission,
        satellites={
            "sat_a": _satellite("sat_a", "visible"),
            "sat_b": _satellite("sat_b", "visible"),
        },
        tasks={
            "task_a": _task("task_a", "visible"),
            "task_b": _task("task_b", "visible"),
        },
    )
    _patch_fast_candidate_generation(monkeypatch)
    config = CandidateConfig(
        max_candidates=5,
        max_candidates_per_task=2,
        candidate_workers=2,
    )

    serial_candidates, serial_summary = generate_candidates(
        case,
        CandidateConfig(
            max_candidates=config.max_candidates,
            max_candidates_per_task=config.max_candidates_per_task,
            candidate_workers=1,
        ),
    )
    parallel_candidates, parallel_summary = generate_candidates(case, config)

    assert [item.candidate_id for item in parallel_candidates] == [
        item.candidate_id for item in serial_candidates
    ]
    assert parallel_summary.as_dict() == serial_summary.as_dict()
    assert parallel_summary.candidate_count == 4
    assert parallel_summary.skipped_cap == 8


def test_candidate_generation_precomputes_offsets_once_per_task(monkeypatch) -> None:
    mission = _mission()
    case = AeosspCase(
        case_dir=Path("."),
        mission=mission,
        satellites={
            "sat_a": _satellite("sat_a", "visible"),
            "sat_b": _satellite("sat_b", "infrared"),
        },
        tasks={
            "task_b": _task("task_b", "infrared"),
            "task_a": _task("task_a", "visible"),
        },
    )
    _patch_fast_candidate_generation(monkeypatch)

    calls: list[str] = []

    def counted_offsets(case_arg, task, *, stride_multiplier=1):
        calls.append(task.task_id)
        return start_offsets_for_task(
            case_arg,
            task,
            stride_multiplier=stride_multiplier,
        )

    monkeypatch.setattr(
        "solvers.aeossp_standard.mwis_conflict_graph.src.candidates.start_offsets_for_task",
        counted_offsets,
    )

    _, serial_summary = generate_candidates(case, CandidateConfig(candidate_workers=1))
    assert calls == ["task_a", "task_b"]
    assert serial_summary.candidate_precompute["total_start_offsets"] == 6
    assert "geometry_cache" in serial_summary.as_dict()

    calls.clear()
    _, parallel_summary = generate_candidates(case, CandidateConfig(candidate_workers=2))
    assert calls == ["task_a", "task_b"]
    assert parallel_summary.candidate_precompute == serial_summary.candidate_precompute


def test_candidate_config_parses_candidate_workers() -> None:
    assert CandidateConfig.from_mapping({}).candidate_workers == 1
    assert CandidateConfig.from_mapping({"candidate_workers": "2"}).candidate_workers == 2

    with pytest.raises(ValueError, match="candidate worker count"):
        CandidateConfig.from_mapping({"candidate_workers": 0})


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

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.graph.PropagationContext", DummyPropagation)
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

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.graph.PropagationContext", DummyPropagation)
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

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.transition.target_vector_eci", fake_target_vector)
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

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.graph.PropagationContext", DummyPropagation)
    graph = build_conflict_graph(_case_for_candidates(candidates), candidates)

    assert not graph.has_edge("sat_a|task_a|10", "sat_a|task_b|250")
    assert graph.stats.transition_edge_count == 0


def _assert_graphs_equal(left, right) -> None:
    assert left.adjacency == right.adjacency
    assert left.reason_edges == right.reason_edges
    assert left.stats.as_dict() == right.stats.as_dict()


def test_graph_build_config_parses_worker_count() -> None:
    assert GraphBuildConfig.from_mapping({}).graph_workers == 1
    assert GraphBuildConfig.from_mapping({"graph_workers": "3"}).graph_workers == 3

    with pytest.raises(ValueError, match="graph worker count"):
        GraphBuildConfig.from_mapping({"graph_workers": 0})


def test_optimized_conflict_graph_matches_legacy_serial_edges(monkeypatch) -> None:
    candidates = [
        _candidate("sat_a|task_a|10", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20),
        _candidate("sat_b|task_a|12", satellite_id="sat_b", task_id="task_a", start_offset_s=12, end_offset_s=22),
        _candidate("sat_a|task_b|18", satellite_id="sat_a", task_id="task_b", start_offset_s=18, end_offset_s=28),
        _candidate("sat_a|task_c|35", satellite_id="sat_a", task_id="task_c", start_offset_s=35, end_offset_s=45),
        _candidate("sat_a|task_d|250", satellite_id="sat_a", task_id="task_d", start_offset_s=250, end_offset_s=260),
        _candidate("sat_b|task_e|20", satellite_id="sat_b", task_id="task_e", start_offset_s=20, end_offset_s=30),
    ]
    case = _case_for_candidates(candidates)

    class DummyPropagation:
        def __init__(self, *args, **kwargs):
            pass

    def fake_transition_gap_conflict(candidate_a, candidate_b, *, case, vector_cache):
        previous, current = sorted(
            (candidate_a, candidate_b),
            key=lambda item: (item.start_offset_s, item.end_offset_s, item.candidate_id),
        )
        return current.start_offset_s - previous.end_offset_s < 20

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.graph.PropagationContext", DummyPropagation)
    monkeypatch.setattr(
        "solvers.aeossp_standard.mwis_conflict_graph.src.graph.transition_gap_conflict",
        fake_transition_gap_conflict,
    )

    legacy = _build_conflict_graph_legacy(case, list(reversed(candidates)))
    optimized = build_conflict_graph(case, list(reversed(candidates)))

    _assert_graphs_equal(optimized, legacy)
    assert optimized.stats.duplicate_task_edge_count == 1
    assert optimized.stats.overlap_edge_count == 2
    assert optimized.stats.transition_edge_count == 2


def test_parallel_conflict_graph_matches_serial_and_merges_deterministically(monkeypatch) -> None:
    candidates = [
        _candidate("sat_a|task_a|10", satellite_id="sat_a", task_id="task_a", start_offset_s=10, end_offset_s=20),
        _candidate("sat_a|task_b|25", satellite_id="sat_a", task_id="task_b", start_offset_s=25, end_offset_s=35),
        _candidate("sat_b|task_a|10", satellite_id="sat_b", task_id="task_a", start_offset_s=10, end_offset_s=20),
        _candidate("sat_b|task_c|18", satellite_id="sat_b", task_id="task_c", start_offset_s=18, end_offset_s=28),
    ]
    case = _case_for_candidates(candidates)

    class DummyPropagation:
        def __init__(self, *args, **kwargs):
            pass

    class FakeProcessPoolExecutor:
        created_max_workers: list[int] = []

        def __init__(self, *, max_workers):
            self.created_max_workers.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def map(self, fn, items):
            return [fn(item) for item in items]

    def fake_transition_gap_conflict(candidate_a, candidate_b, *, case, vector_cache):
        return True

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.graph.PropagationContext", DummyPropagation)
    monkeypatch.setattr(
        "solvers.aeossp_standard.mwis_conflict_graph.src.graph.ProcessPoolExecutor",
        FakeProcessPoolExecutor,
    )
    monkeypatch.setattr(
        "solvers.aeossp_standard.mwis_conflict_graph.src.graph.transition_gap_conflict",
        fake_transition_gap_conflict,
    )

    serial = build_conflict_graph(case, candidates, config=GraphBuildConfig(graph_workers=1))
    parallel = build_conflict_graph(case, candidates, config=GraphBuildConfig(graph_workers=4))

    _assert_graphs_equal(parallel, serial)
    assert FakeProcessPoolExecutor.created_max_workers == [2]


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


def test_exact_component_matches_bruteforce_on_medium_graph() -> None:
    candidates = [
        _candidate(
            f"v{index}",
            task_id=f"task_{index}",
            weight=float((index % 5) + 1),
            end_offset_s=20 + index,
        )
        for index in range(10)
    ]
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    component = [candidate.candidate_id for candidate in candidates]
    edge_pairs = {
        ("v0", "v1"),
        ("v0", "v2"),
        ("v1", "v3"),
        ("v2", "v4"),
        ("v3", "v5"),
        ("v4", "v5"),
        ("v5", "v6"),
        ("v6", "v7"),
        ("v7", "v8"),
        ("v8", "v9"),
    }
    adjacency = {candidate_id: set() for candidate_id in component}
    for left, right in edge_pairs:
        adjacency[left].add(right)
        adjacency[right].add(left)

    best: set[str] = set()
    for mask in range(1 << len(component)):
        selected = {
            candidate_id
            for index, candidate_id in enumerate(component)
            if mask & (1 << index)
        }
        if not validate_independent_set(selected, adjacency):
            continue
        selected_key = (
            round(sum(candidate_by_id[candidate_id].task_weight for candidate_id in selected), 12),
            len(selected),
            -sum(candidate_by_id[candidate_id].end_offset_s for candidate_id in selected),
            tuple(sorted(selected)),
        )
        best_key = (
            round(sum(candidate_by_id[candidate_id].task_weight for candidate_id in best), 12),
            len(best),
            -sum(candidate_by_id[candidate_id].end_offset_s for candidate_id in best),
            tuple(sorted(best)),
        )
        if selected_key > best_key:
            best = selected

    assert solve_exact_component(
        component,
        candidate_by_id,
        adjacency,
        policy="weight_degree_end",
    ) == best


def test_reduction_includes_isolated_nonnegative_vertices() -> None:
    candidates = [
        _candidate("isolated", task_id="task_isolated", weight=0.0),
        _candidate("left", task_id="task_left", weight=3.0),
        _candidate("right", task_id="task_right", weight=3.0),
    ]
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    adjacency = {
        "isolated": set(),
        "left": {"right"},
        "right": {"left"},
    }

    reduction = reduce_component(
        ["isolated", "left", "right"],
        candidate_by_id,
        adjacency,
    )

    assert reduction.active_component == ["left", "right"]
    assert reduction.included_ids == {"isolated"}
    assert reduction.reconstruct({"right"}) == {"isolated", "right"}
    assert reduction.stats.as_dict() == {
        "original_component_size": 3,
        "reduced_component_size": 2,
        "included_by_reduction_count": 1,
        "removed_by_reduction_count": 0,
        "rule_counts": {"isolated_vertex_include": 1},
    }


def test_reduction_removes_strict_weighted_dominated_vertex() -> None:
    candidates = [
        _candidate("heavy", task_id="task_heavy", weight=5.0),
        _candidate("light", task_id="task_light", weight=3.0),
        _candidate("shared", task_id="task_shared", weight=2.0),
        _candidate("outside", task_id="task_outside", weight=1.0),
        _candidate("blocker", task_id="task_blocker", weight=1.0),
    ]
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    adjacency = {
        "heavy": {"light", "shared", "blocker"},
        "light": {"heavy", "shared", "outside", "blocker"},
        "shared": {"heavy", "light"},
        "outside": {"light"},
        "blocker": {"heavy", "light"},
    }

    reduction = reduce_component(
        ["heavy", "light", "shared", "outside", "blocker"],
        candidate_by_id,
        adjacency,
    )

    assert "light" not in reduction.active_component
    assert reduction.removed_ids == {"light"}
    assert reduction.stats.rule_counts == {
        "isolated_vertex_include": 1,
        "strict_weighted_dominated_vertex_remove": 1,
    }


def test_reduction_keeps_equal_weight_dominated_vertex_for_tie_stability() -> None:
    candidates = [
        _candidate("alpha", task_id="task_alpha", weight=5.0),
        _candidate("beta", task_id="task_beta", weight=5.0),
        _candidate("shared", task_id="task_shared", weight=5.0),
    ]
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    adjacency = {
        "alpha": {"beta", "shared"},
        "beta": {"alpha", "shared"},
        "shared": {"alpha", "beta"},
    }

    reduction = reduce_component(
        ["alpha", "beta", "shared"],
        candidate_by_id,
        adjacency,
    )

    assert reduction.active_component == ["alpha", "beta", "shared"]
    assert reduction.removed_ids == set()
    assert reduction.stats.removed_by_reduction_count == 0


def test_reduced_exact_selection_matches_direct_exact_solution() -> None:
    candidates = [
        _candidate("isolated", task_id="task_isolated", weight=1.0, start_offset_s=5),
        _candidate("heavy", task_id="task_heavy", weight=7.0, start_offset_s=10),
        _candidate("light", task_id="task_light", weight=3.0, start_offset_s=15),
        _candidate("shared", task_id="task_shared", weight=4.0, start_offset_s=20),
        _candidate("tail", task_id="task_tail", weight=2.0, start_offset_s=25),
    ]
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    adjacency = {
        "isolated": set(),
        "heavy": {"light", "shared"},
        "light": {"heavy", "shared", "tail"},
        "shared": {"heavy", "light"},
        "tail": {"light"},
    }
    component = ["isolated", "heavy", "light", "shared", "tail"]

    direct = solve_exact_component(
        component,
        candidate_by_id,
        adjacency,
        policy="weight_degree_end",
    )
    reduction = reduce_component(component, candidate_by_id, adjacency)
    reduced = solve_exact_component(
        reduction.active_component,
        candidate_by_id,
        adjacency,
        policy="weight_degree_end",
    )

    assert reduction.reconstruct(reduced) == direct


def test_reduced_exact_matches_direct_exact_on_small_generated_graphs() -> None:
    graph_shapes = [
        set(),
        {("a", "b")},
        {("a", "b"), ("b", "c")},
        {("a", "b"), ("a", "c"), ("b", "c")},
        {("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")},
    ]
    weights = {
        "a": 5.0,
        "b": 3.0,
        "c": 4.0,
        "d": 2.0,
    }
    candidates = [
        _candidate(candidate_id, task_id=f"task_{candidate_id}", weight=weight)
        for candidate_id, weight in weights.items()
    ]
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    component = ["a", "b", "c", "d"]

    for edge_set in graph_shapes:
        adjacency = {candidate_id: set() for candidate_id in component}
        for left, right in edge_set:
            adjacency[left].add(right)
            adjacency[right].add(left)
        direct = solve_exact_component(
            component,
            candidate_by_id,
            adjacency,
            policy="weight_degree_end",
        )
        reduction = reduce_component(component, candidate_by_id, adjacency)
        reduced = solve_exact_component(
            reduction.active_component,
            candidate_by_id,
            adjacency,
            policy="weight_degree_end",
        )

        assert reduction.reconstruct(reduced) == direct


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
    assert stats.included_by_reduction_count == 1
    assert stats.as_dict()["component_search"][0]["reduction_rule_counts"] == {
        "isolated_vertex_include": 1,
    }


def test_mwis_config_allows_non_default_selection_policy() -> None:
    config = MwisConfig.from_mapping(
        {
            "backend": "fallback_python",
            "max_exact_component_size": 0,
            "selection_policy": "weight_degree_end",
        }
    )

    assert config.backend == "fallback_python"
    assert config.max_exact_component_size == 0
    assert config.selection_policy == "weight_degree_end"


def test_mwis_config_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="backend must be one of"):
        MwisConfig.from_mapping({"backend": "native_magic"})


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

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.mwis.solve_greedy_component", fake_greedy)
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
    assert stats.requested_backend == "internal_reduction"
    assert stats.backend == "internal_reduction"
    assert stats.backend_available
    assert stats.backend_fallback_reason is None


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

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.mwis.solve_greedy_component", fake_greedy)

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


def test_explicit_fallback_python_backend_reports_backend_status() -> None:
    candidates = [
        _candidate("early", task_id="task_early", weight=5.0, start_offset_s=10, end_offset_s=20),
        _candidate("late", task_id="task_late", weight=5.0, start_offset_s=20, end_offset_s=30),
    ]
    adjacency = {
        "early": {"late"},
        "late": {"early"},
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
        MwisConfig(backend="fallback_python", max_exact_component_size=0),
    )

    assert [candidate.candidate_id for candidate in selected] == ["early"]
    assert stats.requested_backend == "fallback_python"
    assert stats.backend == "fallback_python"
    assert stats.backend_available
    assert stats.backend_fallback_reason is None
    assert stats.as_dict()["backend"] == "fallback_python"


def test_redumis_backend_request_falls_back_without_native_dependency() -> None:
    candidates = [
        _candidate("early", task_id="task_early", weight=5.0, start_offset_s=10, end_offset_s=20),
        _candidate("late", task_id="task_late", weight=5.0, start_offset_s=20, end_offset_s=30),
    ]
    adjacency = {
        "early": {"late"},
        "late": {"early"},
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
        MwisConfig(backend="redumis", max_exact_component_size=0),
    )

    assert [candidate.candidate_id for candidate in selected] == ["early"]
    assert stats.requested_backend == "redumis"
    assert stats.backend == "fallback_python"
    assert not stats.backend_available
    assert stats.backend_fallback_reason is not None
    assert "not bundled" in stats.backend_fallback_reason


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
    assert stats.effective_time_limit_s == 0.0
    assert stats.deadline_source == "time_limit_s"
    assert stats.selection_started_after_deadline
    assert stats.as_dict()["component_stop_reasons"]["time_limit"] == 1
    assert stats.as_dict()["component_stop_reasons"]["exact"] == 1
    assert stats.as_dict()["component_search"][0]["stop_reason"] == "exact"
    assert stats.as_dict()["component_search"][0]["reduction_rule_counts"] == {
        "isolated_vertex_include": 1,
    }


def test_total_budget_deadline_bounds_mwis_refinement() -> None:
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
            time_limit_s=None,
            max_local_passes=4,
            population_size=2,
            recombination_rounds=2,
        ),
        deadline=time.perf_counter() - 1.0,
    )

    assert [candidate.candidate_id for candidate in selected] == ["early", "free"]
    assert stats.time_limit_hit
    assert stats.search_stop_reason == "time_limit"
    assert stats.time_limit_s is None
    assert stats.effective_time_limit_s == 0.0
    assert stats.deadline_source == "total_time_budget_s"
    assert stats.selection_started_after_deadline


def test_total_budget_deadline_bounds_exact_component() -> None:
    candidates = [
        _candidate("early", task_id="task_early", weight=5.0, start_offset_s=10, end_offset_s=20),
        _candidate("late", task_id="task_late", weight=5.0, start_offset_s=20, end_offset_s=30),
    ]
    adjacency = {
        "early": {"late"},
        "late": {"early"},
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
        MwisConfig(max_exact_component_size=2),
        deadline=time.perf_counter() - 1.0,
    )

    assert [candidate.candidate_id for candidate in selected] == ["early"]
    assert stats.time_limit_hit
    assert stats.search_stop_reason == "time_limit"
    assert stats.as_dict()["component_stop_reasons"]["time_limit"] == 1
    assert stats.as_dict()["component_search"][0]["mode"] == "baseline_only"


def test_local_validation_rejects_duplicate_tasks(monkeypatch) -> None:
    candidates = [
        _candidate("sat_a|task_a|10", satellite_id="sat_a", task_id="task_a"),
        _candidate("sat_b|task_a|15", satellite_id="sat_b", task_id="task_a", start_offset_s=15, end_offset_s=25),
    ]

    class DummyPropagation:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation.PropagationContext", DummyPropagation)
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation.schedule_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation.battery_issues", lambda *args, **kwargs: ([], {}))

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

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation.PropagationContext", DummyPropagation)
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation._initial_slew_required_s", lambda *args, **kwargs: 0.0)
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation.battery_issues", lambda *args, **kwargs: ([], {}))

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

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation.PropagationContext", DummyPropagation)
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation._initial_slew_required_s", lambda *args, **kwargs: 0.0)
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation.transition_result", lambda *args, **kwargs: FakeTransition())
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation.battery_issues", lambda *args, **kwargs: ([], {}))

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

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation._initial_slew_required_s", lambda *args, **kwargs: 0.0)
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation.is_sunlit", lambda *args, **kwargs: False)

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


def test_repair_config_parses_incremental_flag() -> None:
    assert RepairConfig.from_mapping({}).enable_incremental_repair
    assert RepairConfig.from_mapping({"enable_incremental_repair": False}).enable_incremental_repair is False
    assert RepairConfig.from_mapping({"enable_incremental_repair": "false"}).enable_incremental_repair is False
    assert RepairConfig.from_mapping({"enable_incremental_repair": "true"}).enable_incremental_repair is True


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

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation.validate_candidates", lambda *args, **kwargs: invalid_report)

    result = repair_candidates(
        _case_for_candidates(candidates),
        candidates,
        config=RepairConfig(max_repair_iterations=1, enable_incremental_repair=False),
    )

    assert len(result.reports) == 2
    assert len(result.removals) == 1
    assert result.terminated_reason == "max_iterations"


def test_incremental_repair_matches_full_repair_and_reports_impact(monkeypatch) -> None:
    low = _candidate("sat_a|task_shared|10", satellite_id="sat_a", task_id="task_shared", weight=1.0)
    high = _candidate(
        "sat_b|task_shared|15",
        satellite_id="sat_b",
        task_id="task_shared",
        start_offset_s=15,
        end_offset_s=25,
        weight=5.0,
    )
    candidates = [high, low]
    case = _case_for_candidates(candidates)
    for satellite_id, satellite in list(case.satellites.items()):
        case.satellites[satellite_id] = Satellite(
            satellite_id=satellite.satellite_id,
            norad_catalog_id=satellite.norad_catalog_id,
            tle_line1=satellite.tle_line1,
            tle_line2=satellite.tle_line2,
            sensor_type=satellite.sensor_type,
            attitude_model=satellite.attitude_model,
            resource_model=ResourceModel(
                battery_capacity_wh=100.0,
                initial_battery_wh=100.0,
                idle_power_w=0.0,
                imaging_power_w=0.0,
                slew_power_w=0.0,
                sunlit_charge_power_w=0.0,
            ),
        )

    class DummyPropagation:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation.PropagationContext", DummyPropagation)
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation._initial_slew_required_s", lambda *args, **kwargs: 0.0)
    monkeypatch.setattr("solvers.aeossp_standard.mwis_conflict_graph.src.validation.is_sunlit", lambda *args, **kwargs: False)

    full = repair_candidates(
        case,
        candidates,
        config=RepairConfig(max_repair_iterations=4, enable_incremental_repair=False),
    )
    incremental = repair_candidates(
        case,
        candidates,
        config=RepairConfig(max_repair_iterations=4, enable_incremental_repair=True),
    )

    assert [candidate.candidate_id for candidate in incremental.candidates] == [
        candidate.candidate_id for candidate in full.candidates
    ]
    assert [removal.as_dict() for removal in incremental.removals] == [
        removal.as_dict() for removal in full.removals
    ]
    assert incremental.final_report.as_dict() == full.final_report.as_dict()

    status = incremental.as_status_dict()
    assert status["actions_before_repair"] == 2
    assert status["actions_after_repair"] == 1
    assert status["objective_before_repair"] == 6.0
    assert status["objective_after_repair"] == 5.0
    assert status["objective_removed_by_repair"] == 1.0
    assert status["removed_action_count_by_reason"] == {"duplicate_task": 1}
    assert status["battery_failure_count_before_repair"] == 0
    assert status["battery_failure_count_after_repair"] == 0
    assert status["full_validation_count"] == 1
    assert status["incremental_validation_count"] == 1
    assert status["fallback_count"] == 0
    assert status["affected_satellites_by_iteration"] == [[], ["sat_a"]]
    assert len(status["validation_time_s_by_iteration"]) == 2


def test_budget_config_parses_total_time_budget() -> None:
    assert BudgetConfig.from_mapping({}).total_time_budget_s is None
    assert BudgetConfig.from_mapping({"total_time_budget_s": ""}).total_time_budget_s is None
    assert BudgetConfig.from_mapping({"total_time_budget_s": 0}).total_time_budget_s == 0.0
    assert BudgetConfig.from_mapping({"total_time_budget_s": "3.5"}).total_time_budget_s == 3.5

    with pytest.raises(ValueError, match="total_time_budget_s"):
        BudgetConfig.from_mapping({"total_time_budget_s": -1})


def test_budget_status_reports_total_and_refinement_budgets() -> None:
    no_budget = _budget_status(
        budget_config=BudgetConfig(),
        timing_seconds={"total": 2.0, "candidate_generation": 1.0},
        stage_order=("candidate_generation",),
        search_stage_budget_s=None,
        search_stage_budget_hit=False,
        selection_started_with_remaining_budget_s=None,
        selection_deadline_source="none",
        selection_started_after_deadline=False,
        refinement_only_budget_s=4.0,
        refinement_only_budget_hit=False,
    )
    assert no_budget["configured"]["total_time_budget_s"] is None
    assert not no_budget["budget_hit"]
    assert no_budget["refinement_only_time_limit_s"] == 4.0
    assert not no_budget["refinement_only_time_limit_hit"]

    pressured = _budget_status(
        budget_config=BudgetConfig(total_time_budget_s=1.5),
        timing_seconds={
            "total": 3.0,
            "candidate_generation": 1.0,
            "graph_build": 0.7,
            "selection": 0.5,
        },
        stage_order=("candidate_generation", "graph_build", "selection"),
        search_stage_budget_s=0.0,
        search_stage_budget_hit=True,
        selection_started_with_remaining_budget_s=0.0,
        selection_deadline_source="total_time_budget_s",
        selection_started_after_deadline=True,
        refinement_only_budget_s=None,
        refinement_only_budget_hit=True,
    )
    assert pressured["budget_hit"]
    assert pressured["stage_observed"] == "graph_build"
    assert pressured["output_status"] == "best_effort"
    assert pressured["remaining_time_s"] == 0.0
    assert pressured["search_stage_budget_s"] == 0.0
    assert pressured["search_stage_budget_hit"]
    assert pressured["selection_started_with_remaining_budget_s"] == 0.0
    assert pressured["selection_deadline_source"] == "total_time_budget_s"
    assert pressured["selection_started_after_deadline"]
    assert not pressured["refinement_only_time_limit_hit"]


def test_status_payload_reports_execution_model_and_timing_schema(tmp_path: Path) -> None:
    class DictPayload:
        def __init__(self, payload: dict):
            self.payload = payload

        def as_dict(self) -> dict:
            return self.payload

        def as_status_dict(self) -> dict:
            return self.payload

    class MwisStatsPayload:
        selection_policy = "weight_degree_end"
        selected_candidate_count = 0
        incumbent_source = "exact"
        local_improvement_count = 0
        successful_two_swap_count = 0
        recombination_attempt_count = 0
        recombination_win_count = 0
        search_stop_reason = "exact_only"
        time_limit_hit = False

        def as_dict(self) -> dict:
            return {
                "selected_candidate_count": self.selected_candidate_count,
                "search_stop_reason": self.search_stop_reason,
                "time_limit_hit": self.time_limit_hit,
                "component_stop_reasons": {"exact": 1},
                "component_search": [],
            }

    class RepairPayload:
        final_report = type("FinalReport", (), {"valid": True})()
        candidates: list[Candidate] = []
        removals: list[object] = []

        def as_status_dict(self) -> dict:
            return {"final_local_valid": True}

    case = AeosspCase(
        case_dir=Path("."),
        mission=_mission(),
        satellites={
            "sat_a": _satellite("sat_a", "visible"),
            "sat_b": _satellite("sat_b", "visible"),
        },
        tasks={},
    )
    timing = _timing_with_accounting(
        {
            "config_load": 0.1,
            "case_load": 0.2,
            "candidate_generation": 1.0,
            "graph_build": 0.4,
            "selection": 0.3,
            "repair": 0.5,
            "solution_write": 0.1,
        },
        total_seconds=2.8,
        aliases={"search": 0.3},
    )
    status = build_status_payload(
        case_dir=tmp_path,
        config_dir=None,
        solution_path=tmp_path / "solution.json",
        case=case,
        candidate_config=CandidateConfig(candidate_workers=2),
        graph_config=GraphBuildConfig(graph_workers=2),
        candidate_summary=CandidateSummary(),
        graph=type("Graph", (), {"stats": DictPayload({"vertex_count": 0})})(),
        mwis_config=MwisConfig(),
        mwis_stats=MwisStatsPayload(),
        repair_config=RepairConfig(),
        repair_result=RepairPayload(),
        timing_seconds=timing,
        budget_status=_budget_status(
            budget_config=BudgetConfig(),
            timing_seconds=timing,
            stage_order=("candidate_generation",),
            search_stage_budget_s=None,
            search_stage_budget_hit=False,
            selection_started_with_remaining_budget_s=None,
            selection_deadline_source="none",
            selection_started_after_deadline=False,
            refinement_only_budget_s=None,
            refinement_only_budget_hit=False,
        ),
    )

    assert set(status["execution_model"]) == {
        "case_load",
        "candidate_generation",
        "graph_build",
        "search",
        "validation",
        "repair",
        "solution_write",
    }
    assert status["execution_model"]["candidate_generation"]["model"] == "process_pool_python"
    assert status["execution_model"]["candidate_generation"]["parallelism_scope"] == "satellite"
    assert status["execution_model"]["candidate_generation"]["configured_workers"] == 2
    assert status["execution_model"]["candidate_generation"]["effective_workers"] == 2
    assert status["graph_config"] == {"graph_workers": 2}
    assert status["execution_model"]["graph_build"]["model"] == "process_pool_python"
    assert status["execution_model"]["graph_build"]["parallelism_scope"] == "satellite_temporal_edges"
    assert status["execution_model"]["graph_build"]["configured_workers"] == 2
    assert status["execution_model"]["graph_build"]["effective_workers"] == 2
    assert "candidate_precompute" in status
    assert "geometry_cache" in status
    assert status["execution_model"]["search"]["budget_field"] == "effective_time_limit_s"
    assert status["execution_model"]["search"]["configured_budget_fields"] == [
        "total_time_budget_s",
        "time_limit_s",
    ]
    assert status["budget"]["configured"]["total_time_budget_s"] is None
    assert not status["budget"]["budget_hit"]
    assert status["budget"]["selection_deadline_source"] == "none"
    assert status["budget"]["refinement_only_time_limit_s"] is None
    assert status["timing_seconds"]["accounted_total"] == pytest.approx(2.6)
    assert status["timing_seconds"]["unaccounted_overhead"] == pytest.approx(0.2)
    for key in (
        "config_load",
        "case_load",
        "candidate_generation",
        "graph_build",
        "selection",
        "search",
        "repair",
        "solution_write",
        "total",
    ):
        assert key in status["timing_seconds"]
