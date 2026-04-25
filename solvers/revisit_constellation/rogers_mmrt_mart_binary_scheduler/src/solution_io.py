"""Solution and preprocessing artifact writers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .binary_scheduler import BinaryScheduleResult, selected_windows_to_actions
from .case_io import RevisitCase, SolverConfig, iso_z
from .design_models import DesignResult
from .observation_windows import ObservationWindow, WindowEnumerationResult
from .slot_library import OrbitSlot, slots_to_records
from .time_grid import TimeSample, time_grid_to_records
from .validation import LocalValidationResult
from .visibility_matrix import VisibilityMatrix, target_visibility_counts, visibility_to_sparse_records


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")


def write_empty_solution(solution_dir: Path) -> Path:
    path = solution_dir / "solution.json"
    write_json(path, {"satellites": [], "actions": []})
    return path


def write_slot_solution(
    solution_dir: Path,
    slots: tuple[OrbitSlot, ...],
    selected_slot_indices: tuple[int, ...],
    schedule_result: BinaryScheduleResult | None = None,
    repaired_windows: tuple[ObservationWindow, ...] | None = None,
) -> Path:
    satellites = []
    for satellite_number, slot_index in enumerate(selected_slot_indices, start=1):
        slot = slots[slot_index]
        state = slot.state_eci_m_mps
        satellites.append(
            {
                "satellite_id": f"sat_{satellite_number:03d}",
                "x_m": state[0],
                "y_m": state[1],
                "z_m": state[2],
                "vx_m_s": state[3],
                "vy_m_s": state[4],
                "vz_m_s": state[5],
            }
        )
    path = solution_dir / "solution.json"
    scheduled_windows = (
        repaired_windows
        if repaired_windows is not None
        else (schedule_result.selected_windows if schedule_result is not None else ())
    )
    actions = selected_windows_to_actions(tuple(scheduled_windows))
    write_json(path, {"satellites": satellites, "actions": actions})
    return path


def write_preprocessing_artifacts(
    solution_dir: Path,
    case: RevisitCase,
    config: SolverConfig,
    slots: tuple[OrbitSlot, ...],
    samples: tuple[TimeSample, ...],
    matrix: VisibilityMatrix,
    design_result: DesignResult,
    window_result: WindowEnumerationResult,
    schedule_result: BinaryScheduleResult,
    validation_result: LocalValidationResult,
    *,
    issue_88_url: str | None,
) -> None:
    prep_dir = solution_dir / "model_prep"
    debug_dir = solution_dir / "debug"
    write_json(prep_dir / "slots.json", {"slots": slots_to_records(slots)})
    write_json(prep_dir / "time_grid.json", {"samples": time_grid_to_records(samples)})
    if config.write_visibility_matrix:
        write_json(prep_dir / "visibility_matrix.json", visibility_to_sparse_records(matrix))
    write_json(debug_dir / "design_model_summary.json", design_result.to_summary())
    write_json(
        debug_dir / "selected_slots.json",
        {
            "selected_slots": [
                slots_to_records((slots[index],))[0]
                for index in design_result.selected_slot_indices
            ]
        },
    )
    write_json(debug_dir / "window_summary.json", window_result.to_summary())
    if config.write_observation_windows:
        write_jsonl(
            debug_dir / "observation_windows.jsonl",
            [window.to_record() for window in window_result.windows],
        )
    write_json(debug_dir / "scheduler_model_summary.json", schedule_result.to_summary())
    write_json(
        debug_dir / "selected_windows.json",
        {"selected_windows": [window.to_record() for window in schedule_result.selected_windows]},
    )
    write_json(
        debug_dir / "rounding_or_fallback_summary.json",
        schedule_result.rounding_summary
        | {
            "backend": schedule_result.backend,
            "fallback_reason": schedule_result.fallback_reason,
        },
    )
    write_json(debug_dir / "validation_summary.json", validation_result.to_summary())

    capacity = matrix.shape[0] * matrix.shape[1] * matrix.shape[2]
    status = {
        "solver": "rogers_mmrt_mart_binary_scheduler",
        "phase": "phase_4_binary_scheduler_and_relaxed_fallback",
        "case_dir": str(case.case_dir),
        "horizon_start": iso_z(case.horizon_start),
        "horizon_end": iso_z(case.horizon_end),
        "sample_step_sec": config.sample_step_sec,
        "slot_count": len(slots),
        "target_count": len(case.targets),
        "time_sample_count": len(samples),
        "visibility_shape": list(matrix.shape),
        "visibility_capacity": capacity,
        "visible_count": matrix.visible_count,
        "visibility_density": matrix.density,
        "max_num_satellites": case.max_num_satellites,
        "slot_cap": config.max_slots,
        "altitude_count": config.altitude_count,
        "raan_count": config.raan_count,
        "phase_count": config.phase_count,
        "inclination_deg": list(config.inclination_deg),
        "design_mode": design_result.mode,
        "design_backend": design_result.backend,
        "design_fallback_reason": design_result.fallback_reason,
        "design_objective": design_result.objective,
        "design_model_size": design_result.model_size,
        "selected_slot_count": len(design_result.selected_slot_indices),
        "selected_slot_ids": list(design_result.selected_slot_ids),
        "observation_window_count": len(window_result.windows),
        "candidate_count_by_satellite": window_result.candidate_count_by_satellite,
        "candidate_count_by_target": window_result.candidate_count_by_target,
        "zero_window_targets": list(window_result.zero_window_targets),
        "zero_window_satellites": list(window_result.zero_window_satellites),
        "window_conflict_edge_count": window_result.conflict_edge_count,
        "window_caps": window_result.caps,
        "window_capped": window_result.capped,
        "scheduler_backend": schedule_result.backend,
        "scheduler_fallback_reason": schedule_result.fallback_reason,
        "scheduler_model_size": schedule_result.model_size,
        "scheduler_selected_window_count": len(schedule_result.selected_windows),
        "scheduler_selected_window_ids": list(schedule_result.selected_window_ids),
        "scheduler_conflict_edge_count": schedule_result.conflict_edge_count,
        "scheduler_transition_conflict_edge_count": schedule_result.transition_conflict_edge_count,
        "scheduler_estimated_metrics": schedule_result.evaluation.to_dict(),
        "local_validation_issue_count": len(validation_result.issues),
        "local_repaired_window_count": len(validation_result.repaired_windows),
        "local_dropped_window_ids": list(validation_result.dropped_window_ids),
        "local_validation_metrics": validation_result.estimated_metrics,
        "target_visibility_counts": target_visibility_counts(matrix, case.targets),
        "issue_88_exists": issue_88_url is not None,
        "issue_88_url": issue_88_url,
        "solution_note": (
            "Phase 4 emits selected design satellites and scheduled observation actions. "
            "Battery and full slew repair remain out of scope until Phase 5."
        ),
    }
    write_json(solution_dir / "status.json", status)
