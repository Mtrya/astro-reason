from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.case_io import (  # noqa: E402
    SolverConfig,
    iso_z,
    load_case,
    parse_iso_z,
)
from solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.design_models import (  # noqa: E402
    DesignProblem,
    select_design_slots,
)
from solvers.revisit_constellation.rogers_mmrt_mart_binary_scheduler.src.slot_library import (  # noqa: E402
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


CASE_DIR = (
    REPO_ROOT
    / "benchmarks"
    / "revisit_constellation"
    / "dataset"
    / "cases"
    / "test"
    / "case_0001"
)


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
