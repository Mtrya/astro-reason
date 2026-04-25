from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import math
import sys

import brahe
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.case_io import (  # noqa: E402
    AttitudeModel,
    ResourceModel,
    RevisitCase,
    SatelliteModel,
    SensorModel,
    SolverConfig,
    Target,
    iso_z,
    load_case,
    parse_iso_z,
)
from solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.binary_scheduler import (  # noqa: E402
    BinaryScheduleResult,
    build_conflict_edges,
    evaluate_schedule,
    schedule_observation_windows,
    selected_windows_to_actions,
)
from solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.design_models import (  # noqa: E402
    DesignProblem,
    DesignResult,
    select_design_slots,
)
from solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.observation_windows import (  # noqa: E402
    ObservationWindow,
    WindowEnumerationResult,
    enumerate_observation_windows,
)
from solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.propagation import (  # noqa: E402
    datetime_to_epoch,
    ensure_brahe_ready,
)
from solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.slot_library import (  # noqa: E402
    OrbitSlot,
    build_slot_library,
)
from solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.solution_io import (  # noqa: E402
    write_empty_solution,
)
from solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.time_grid import (  # noqa: E402
    build_time_grid,
)
from solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.visibility_matrix import (  # noqa: E402
    VisibilityMatrix,
    build_visibility_matrix,
)
from solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.validation import (  # noqa: E402
    validate_and_repair_schedule,
)


CASE_DIR = (
    REPO_ROOT
    / "benchmarks"
    / "revisit_constellation"
    / "dataset"
    / "cases"
    / "test"
    / "case_0001"
)
MU_EARTH_M3_S2 = 3.986004418e14


def _small_config() -> SolverConfig:
    return SolverConfig(
        sample_step_sec=24 * 3600.0,
        altitude_count=1,
        inclination_deg=(50.0,),
        raan_count=2,
        phase_count=2,
        max_slots=3,
        write_visibility_matrix=True,
    )


def _design_config(
    *,
    mode: str,
    satellite_count: int | None = 1,
    max_selected: int = 2,
    exhaustive_max: int = 100,
    max_backend_slots: int = 40,
) -> SolverConfig:
    return SolverConfig(
        design_mode=mode,
        design_backend="auto",
        design_satellite_count=satellite_count,
        design_max_selected_slots=max_selected,
        design_max_backend_slots=max_backend_slots,
        fallback_exhaustive_max_combinations=exhaustive_max,
    )


def _problem(
    *,
    shape: tuple[int, int, int],
    visible: set[tuple[int, int, int]],
    expected_hours: tuple[float, ...] = (8.0,),
    fixed_count: int | None = 1,
    max_selected: int = 2,
) -> DesignProblem:
    return DesignProblem(
        matrix=VisibilityMatrix(shape=shape, visible=frozenset(visible)),
        slot_ids=tuple(f"slot_{index}" for index in range(shape[1])),
        target_ids=tuple(f"target_{index}" for index in range(shape[2])),
        sample_step_sec=3600.0,
        expected_revisit_hours=expected_hours,
        max_selected_slots=max_selected,
        fixed_satellite_count=fixed_count,
    )


def _target_ecef() -> tuple[float, float, float]:
    position = np.asarray(
        brahe.position_geodetic_to_ecef(
            [0.0, 0.0, 0.0],
            brahe.AngleFormat.DEGREES,
        ),
        dtype=float,
    )
    return tuple(float(item) for item in position)


def _surface_eci_unit_vector(timestamp: datetime) -> np.ndarray:
    ensure_brahe_ready()
    epoch = datetime_to_epoch(timestamp)
    eci_position = np.asarray(
        brahe.position_ecef_to_eci(epoch, np.asarray(_target_ecef(), dtype=float)),
        dtype=float,
    )
    return eci_position / np.linalg.norm(eci_position)


def _orthogonal_unit_vector(vector: np.ndarray) -> np.ndarray:
    tangent = np.cross(np.asarray([0.0, 0.0, 1.0]), vector)
    if np.linalg.norm(tangent) < 1e-9:
        tangent = np.cross(np.asarray([0.0, 1.0, 0.0]), vector)
    return tangent / np.linalg.norm(tangent)


def _overhead_slot(start: datetime) -> OrbitSlot:
    radial_unit = _surface_eci_unit_vector(start)
    radius_m = brahe.R_EARTH + 500000.0
    position = radial_unit * radius_m
    velocity = _orthogonal_unit_vector(radial_unit) * math.sqrt(MU_EARTH_M3_S2 / radius_m)
    return OrbitSlot(
        slot_id="slot_test",
        altitude_m=500000.0,
        inclination_deg=0.0,
        raan_deg=0.0,
        phase_deg=0.0,
        state_eci_m_mps=tuple(float(item) for item in np.concatenate((position, velocity))),
    )


def _window_case(*, max_range_m: float = 1.0e9, min_duration_sec: float = 20.0) -> RevisitCase:
    start = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    end = start + timedelta(seconds=60)
    return RevisitCase(
        case_dir=Path("."),
        assets_path=Path("assets.json"),
        mission_path=Path("mission.json"),
        horizon_start=start,
        horizon_end=end,
        satellite_model=SatelliteModel(
            model_name="test_bus",
            sensor=SensorModel(
                max_off_nadir_angle_deg=180.0,
                max_range_m=max_range_m,
                obs_discharge_rate_w=1.0,
            ),
            resource_model=ResourceModel(
                battery_capacity_wh=1000.0,
                initial_battery_wh=1000.0,
                idle_discharge_rate_w=1.0,
                sunlight_charge_rate_w=0.0,
            ),
            attitude_model=AttitudeModel(
                max_slew_velocity_deg_per_sec=1.0,
                max_slew_acceleration_deg_per_sec2=1.0,
                settling_time_sec=1.0,
                maneuver_discharge_rate_w=1.0,
            ),
            min_altitude_m=100000.0,
            max_altitude_m=1000000.0,
        ),
        max_num_satellites=1,
        targets=(
            Target(
                target_id="target_001",
                name="Target",
                latitude_deg=0.0,
                longitude_deg=0.0,
                altitude_m=0.0,
                expected_revisit_period_hours=1.0,
                min_elevation_deg=-90.0,
                max_slant_range_m=max_range_m,
                min_duration_sec=min_duration_sec,
                ecef_position_m=_target_ecef(),
            ),
        ),
    )


def _window_config(*, stride_sec: float = 20.0, sample_step_sec: float = 10.0) -> SolverConfig:
    return SolverConfig(
        window_stride_sec=stride_sec,
        window_geometry_sample_step_sec=sample_step_sec,
        max_observation_windows=20,
        max_windows_per_satellite_target=20,
    )


def _scheduler_config(
    *,
    backend: str = "fallback",
    max_selected: int = 10,
    max_exact_combinations: int = 1000,
    transition_gap_sec: float = 0.0,
) -> SolverConfig:
    return SolverConfig(
        scheduler_backend=backend,
        scheduler_max_selected_windows=max_selected,
        scheduler_max_exact_combinations=max_exact_combinations,
        scheduler_min_transition_gap_sec=transition_gap_sec,
    )


def _design_result() -> DesignResult:
    return DesignResult(
        mode="hybrid",
        backend="fallback",
        fallback_reason=None,
        selected_slot_indices=(0,),
        selected_slot_ids=("slot_test",),
        objective={},
        target_stats=(),
        model_size={},
    )


def _manual_window(
    window_id: str,
    *,
    start_offset_sec: int,
    end_offset_sec: int,
    target_id: str = "target_001",
    satellite_id: str = "sat_001",
    conflict_ids: tuple[str, ...] = (),
    max_reduction: float = 0.0,
    mean_reduction: float = 0.0,
) -> ObservationWindow:
    start = datetime(2025, 1, 1, 0, 0, tzinfo=UTC) + timedelta(seconds=start_offset_sec)
    end = datetime(2025, 1, 1, 0, 0, tzinfo=UTC) + timedelta(seconds=end_offset_sec)
    return ObservationWindow(
        window_id=window_id,
        satellite_id=satellite_id,
        slot_id="slot_test",
        slot_index=0,
        target_id=target_id,
        target_index=0,
        start=start,
        end=end,
        midpoint=start + ((end - start) / 2),
        duration_sec=(end - start).total_seconds(),
        estimated_max_gap_reduction_hours=max_reduction,
        estimated_mean_gap_reduction_hours=mean_reduction,
        conflict_ids=conflict_ids,
    )


def _window_result(windows: tuple[ObservationWindow, ...]) -> WindowEnumerationResult:
    return WindowEnumerationResult(
        windows=windows,
        candidate_count_by_satellite={"sat_001": len(windows)},
        candidate_count_by_target={"target_001": len(windows)},
        candidate_count_by_satellite_target={"sat_001|target_001": len(windows)},
        zero_window_targets=(),
        zero_window_satellites=(),
        conflict_edge_count=sum(len(window.conflict_ids) for window in windows) // 2,
        capped=False,
        caps={},
    )


def test_iso_z_timestamp_round_trip() -> None:
    parsed = parse_iso_z("2025-07-17T12:00:00Z")

    assert parsed.tzinfo is UTC
    assert iso_z(parsed) == "2025-07-17T12:00:00Z"


def test_load_case_parses_public_files() -> None:
    case = load_case(CASE_DIR)

    assert case.max_num_satellites == 18
    assert case.satellite_model.sensor.max_off_nadir_angle_deg == 25.0
    assert len(case.targets) == 23
    assert case.targets[0].target_id == "target_001"
    assert case.horizon_duration_sec == 48 * 3600.0


def test_time_grid_includes_horizon_end() -> None:
    start = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    end = start + timedelta(seconds=100)

    samples = build_time_grid(start, end, 30)

    assert [sample.offset_sec for sample in samples] == [0.0, 30.0, 60.0, 90.0, 100.0]
    assert samples[-1].instant == end


def test_slot_library_filters_to_cap_and_stable_ids() -> None:
    case = load_case(CASE_DIR)
    slots = build_slot_library(case, _small_config())

    assert len(slots) == 3
    assert [slot.slot_id for slot in slots] == sorted(slot.slot_id for slot in slots)
    assert [slot.slot_id for slot in slots] == [
        "slot_a0675000_i0500_r00_u00",
        "slot_a0675000_i0500_r00_u01",
        "slot_a0675000_i0500_r01_u00",
    ]
    for slot in slots:
        assert case.satellite_model.min_altitude_m <= slot.altitude_m <= case.satellite_model.max_altitude_m
        assert len(slot.state_eci_m_mps) == 6


def test_visibility_matrix_has_expected_dimensions() -> None:
    case = load_case(CASE_DIR)
    config = _small_config()
    slots = build_slot_library(case, config)
    samples = build_time_grid(case.horizon_start, case.horizon_end, config.sample_step_sec)

    matrix = build_visibility_matrix(case, slots, samples)

    assert matrix.shape == (3, 3, 23)
    assert 0 <= matrix.visible_count <= 3 * 3 * 23
    assert 0.0 <= matrix.density <= 1.0
    assert matrix.visible == build_visibility_matrix(case, slots, samples).visible


def test_empty_solution_output_schema(tmp_path: Path) -> None:
    solution_path = write_empty_solution(tmp_path)
    payload = json.loads(solution_path.read_text(encoding="utf-8"))

    assert payload == {"satellites": [], "actions": []}


def test_mmrt_design_selects_slot_with_smallest_worst_gap() -> None:
    problem = _problem(
        shape=(6, 2, 1),
        visible={
            (2, 0, 0),
            (1, 1, 0),
            (4, 1, 0),
        },
    )

    result = select_design_slots(problem, _design_config(mode="mmrt"))

    assert result.selected_slot_ids == ("slot_1",)
    assert result.objective["max_gap_samples"] == 2


def test_mart_design_selects_slot_with_smallest_average_gap() -> None:
    problem = _problem(
        shape=(8, 2, 1),
        visible={
            (3, 0, 0),
            (1, 1, 0),
            (3, 1, 0),
            (5, 1, 0),
        },
    )

    result = select_design_slots(problem, _design_config(mode="mart"))

    assert result.selected_slot_ids == ("slot_1",)
    assert result.objective["sum_mean_gap_samples"] == 1.25


def test_threshold_first_finds_fewest_slots_satisfying_expected_gap() -> None:
    problem = _problem(
        shape=(6, 3, 1),
        visible={
            (2, 0, 0),
            (4, 1, 0),
            (0, 2, 0),
        },
        expected_hours=(2.0,),
        fixed_count=None,
        max_selected=3,
    )
    config = _design_config(
        mode="threshold_first",
        satellite_count=None,
        max_selected=3,
    )

    result = select_design_slots(problem, config)

    assert result.selected_slot_ids == ("slot_0", "slot_1")
    assert result.objective["threshold_satisfied"] is True
    assert result.objective["selected_count"] == 2


def test_design_fallback_trigger_is_deterministic() -> None:
    problem = _problem(
        shape=(5, 3, 1),
        visible={
            (1, 0, 0),
            (3, 1, 0),
            (2, 2, 0),
        },
        fixed_count=1,
        max_selected=1,
    )
    config = _design_config(
        mode="mmrt",
        satellite_count=1,
        max_selected=1,
        max_backend_slots=1,
    )

    first = select_design_slots(problem, config)
    second = select_design_slots(problem, config)

    assert first.backend == "fallback"
    assert first.fallback_reason is not None
    assert "slot_bound_exceeded" in first.fallback_reason
    assert first.selected_slot_ids == second.selected_slot_ids


def test_observation_windows_with_gap_metadata_and_conflicts() -> None:
    case = _window_case()
    slots = (_overhead_slot(case.horizon_start),)

    result = enumerate_observation_windows(case, _window_config(), slots, _design_result())

    assert [window.window_id for window in result.windows] == [
        "win_sat_001_target_001_20250101T000000Z",
        "win_sat_001_target_001_20250101T000020Z",
        "win_sat_001_target_001_20250101T000040Z",
    ]
    assert all(case.horizon_start <= window.start < window.end <= case.horizon_end for window in result.windows)
    assert result.windows[0].midpoint == case.horizon_start + timedelta(seconds=10)
    assert result.windows[0].estimated_max_gap_reduction_hours > 0.0
    assert result.windows[0].estimated_mean_gap_reduction_hours == 0.5 / 60.0
    assert result.conflict_edge_count == 0
    assert result.candidate_count_by_satellite == {"sat_001": 3}
    assert result.candidate_count_by_target == {"target_001": 3}


def test_observation_window_conflicts_for_overlapping_same_satellite_windows() -> None:
    case = _window_case()
    slots = (_overhead_slot(case.horizon_start),)

    result = enumerate_observation_windows(
        case,
        _window_config(stride_sec=10.0),
        slots,
        _design_result(),
    )

    first = result.windows[0]
    assert result.conflict_edge_count > 0
    assert "win_sat_001_target_001_20250101T000010Z" in first.conflict_ids


def test_observation_window_geometry_filter_rejects_range_violation() -> None:
    case = _window_case(max_range_m=1.0)
    slots = (_overhead_slot(case.horizon_start),)

    result = enumerate_observation_windows(case, _window_config(), slots, _design_result())

    assert result.windows == ()
    assert result.zero_window_targets == ("target_001",)
    assert result.zero_window_satellites == ("sat_001",)


def test_scheduler_excludes_conflicting_windows() -> None:
    case = _window_case()
    early = _manual_window(
        "win_early",
        start_offset_sec=0,
        end_offset_sec=10,
        conflict_ids=("win_late",),
    )
    late = _manual_window(
        "win_late",
        start_offset_sec=30,
        end_offset_sec=40,
        conflict_ids=("win_early",),
    )

    result = schedule_observation_windows(
        case,
        _scheduler_config(max_selected=2),
        _window_result((early, late)),
    )

    assert len(result.selected_window_ids) == 1
    assert set(result.selected_window_ids) <= {"win_early", "win_late"}
    assert result.conflict_edge_count == 1


def test_scheduler_chooses_window_with_better_gap_reduction() -> None:
    case = _window_case()
    edge = _manual_window("win_edge", start_offset_sec=0, end_offset_sec=10)
    center = _manual_window("win_center", start_offset_sec=25, end_offset_sec=35)

    result = schedule_observation_windows(
        case,
        _scheduler_config(max_selected=1),
        _window_result((edge, center)),
    )

    assert result.selected_window_ids == ("win_center",)
    assert result.evaluation.max_revisit_gap_hours == 0.5 / 60.0


def test_scheduler_greedy_fallback_is_deterministic() -> None:
    case = _window_case()
    windows = (
        _manual_window("win_00", start_offset_sec=0, end_offset_sec=10),
        _manual_window("win_01", start_offset_sec=20, end_offset_sec=30),
        _manual_window("win_02", start_offset_sec=40, end_offset_sec=50),
    )
    config = _scheduler_config(max_selected=2, max_exact_combinations=1)

    first = schedule_observation_windows(case, config, _window_result(windows))
    second = schedule_observation_windows(case, config, _window_result(windows))

    assert first.backend == "greedy_fallback"
    assert first.selected_window_ids == second.selected_window_ids
    assert "greedy_fallback" in (first.fallback_reason or "")


def test_scheduler_adds_transition_gap_conflicts() -> None:
    first = _manual_window("win_first", start_offset_sec=0, end_offset_sec=10)
    second = _manual_window("win_second", start_offset_sec=15, end_offset_sec=25)

    edges, transition_count = build_conflict_edges((first, second), 10.0)

    assert edges == frozenset({(0, 1)})
    assert transition_count == 1


def test_selected_windows_decode_to_action_schema() -> None:
    window = _manual_window("win_action", start_offset_sec=0, end_offset_sec=10)

    actions = selected_windows_to_actions((window,))

    assert actions == [
        {
            "action_type": "observation",
            "satellite_id": "sat_001",
            "target_id": "target_001",
            "start": "2025-01-01T00:00:00Z",
            "end": "2025-01-01T00:00:10Z",
        }
    ]


def test_local_validation_repair_drops_overlapping_low_value_window() -> None:
    case = _window_case()
    slots = (_overhead_slot(case.horizon_start),)
    low = _manual_window(
        "win_low",
        start_offset_sec=0,
        end_offset_sec=20,
        max_reduction=0.1,
        mean_reduction=0.1,
    )
    high = _manual_window(
        "win_high",
        start_offset_sec=10,
        end_offset_sec=30,
        max_reduction=0.5,
        mean_reduction=0.5,
    )
    schedule = BinaryScheduleResult(
        backend="test",
        fallback_reason=None,
        selected_window_ids=("win_low", "win_high"),
        selected_window_indices=(0, 1),
        selected_windows=(low, high),
        evaluation=evaluate_schedule(case, (low, high), (0, 1)),
        conflict_edge_count=1,
        transition_conflict_edge_count=0,
        model_size={},
        rounding_summary={},
    )

    result = validate_and_repair_schedule(case, SolverConfig(), slots, schedule)

    assert result.dropped_window_ids == ("win_low",)
    assert [window.window_id for window in result.repaired_windows] == ["win_high"]
    assert any(issue.issue_type == "overlap" for issue in result.issues)


def test_local_validation_can_report_without_repair() -> None:
    case = _window_case(max_range_m=1.0)
    slots = (_overhead_slot(case.horizon_start),)
    invalid = _manual_window("win_invalid", start_offset_sec=0, end_offset_sec=20)
    schedule = BinaryScheduleResult(
        backend="test",
        fallback_reason=None,
        selected_window_ids=("win_invalid",),
        selected_window_indices=(0,),
        selected_windows=(invalid,),
        evaluation=evaluate_schedule(case, (invalid,), (0,)),
        conflict_edge_count=0,
        transition_conflict_edge_count=0,
        model_size={},
        rounding_summary={},
    )
    config = SolverConfig(local_repair_enabled=False)

    result = validate_and_repair_schedule(case, config, slots, schedule)

    assert result.repaired_windows == (invalid,)
    assert result.dropped_window_ids == ()
    assert result.repair_enabled is False
    assert any(issue.issue_type == "geometry" for issue in result.issues)
