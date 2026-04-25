"""Solution and preprocessing artifact writers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import time

from .binary_scheduler import BinaryScheduleResult, selected_windows_to_actions
from .case_io import RevisitCase, SolverConfig, iso_z
from .design_models import DesignResult
from .observation_windows import ObservationWindow, WindowEnumerationResult
from .slot_library import OrbitSlot, slot_library_summary, slots_to_records
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


def _backend_accounting(
    backend_report: dict[str, object],
    model_size: dict[str, int],
    configured_time_limit_sec: float,
) -> dict[str, object]:
    fallback_reason = backend_report.get("fallback_reason") or backend_report.get("failure_reason")
    return {
        "backend_name": backend_report.get("backend_name"),
        "active_backend": backend_report.get("active_backend"),
        "backend_requested": backend_report.get("requested_backend"),
        "backend_available": backend_report.get("available"),
        "backend_attempted": backend_report.get("attempted"),
        "backend_solved": backend_report.get("solved"),
        "solver_status": backend_report.get("solver_status"),
        "fallback_reason": fallback_reason,
        "model_size": model_size,
        "configured_time_limit_sec": configured_time_limit_sec,
        "exact_required": backend_report.get("exact_required"),
        "solved_with_milp_backend": backend_report.get("solved_with_milp_backend"),
        "solved_with_binary_milp": backend_report.get("solved_with_binary_milp"),
    }


def _with_backend_accounting(
    summary: dict[str, object],
    configured_time_limit_sec: float,
) -> dict[str, object]:
    backend_report = dict(summary.get("backend_report", {}))
    model_size = dict(summary.get("model_size", {}))
    return summary | {
        "backend_accounting": _backend_accounting(
            backend_report,
            model_size,
            configured_time_limit_sec,
        )
    }


def _complete_run_accounting(
    run_accounting: dict[str, object] | None,
    artifact_write_started_at: float | None,
) -> dict[str, object]:
    accounting = dict(run_accounting or {})
    timing = dict(accounting.get("timing", {}))
    stages = dict(timing.get("stage_durations_sec", {}))
    if artifact_write_started_at is not None:
        stages["artifact_writing"] = round(time.perf_counter() - artifact_write_started_at, 6)
    timing["stage_durations_sec"] = stages
    timing.setdefault("clock", "time.perf_counter")
    if "total_elapsed_sec" in timing and artifact_write_started_at is not None:
        prior_total = float(timing["total_elapsed_sec"])
        timing["total_elapsed_sec"] = round(
            prior_total + float(stages["artifact_writing"]),
            6,
        )
    accounting["timing"] = timing
    accounting.setdefault("run_policy", {})
    return accounting


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
    design_mode_comparison: tuple[dict[str, object], ...],
    scheduler_mode_comparison: tuple[dict[str, object], ...],
    *,
    issue_88_url: str | None,
    run_accounting: dict[str, object] | None = None,
    artifact_write_started_at: float | None = None,
) -> None:
    prep_dir = solution_dir / "model_prep"
    debug_dir = solution_dir / "debug"
    design_summary = _with_backend_accounting(
        design_result.to_summary(),
        config.design_time_limit_sec,
    )
    scheduler_summary = _with_backend_accounting(
        schedule_result.to_summary(),
        config.scheduler_time_limit_sec,
    )
    design_backend_accounting = design_summary["backend_accounting"]
    scheduler_backend_accounting = scheduler_summary["backend_accounting"]
    slot_summary = slot_library_summary(config, slots)
    write_json(
        prep_dir / "slots.json",
        {
            "slot_library": slot_summary,
            "slots": slots_to_records(slots),
        },
    )
    write_json(prep_dir / "time_grid.json", {"samples": time_grid_to_records(samples)})
    if config.write_visibility_matrix:
        write_json(prep_dir / "visibility_matrix.json", visibility_to_sparse_records(matrix))
    write_json(debug_dir / "design_model_summary.json", design_summary)
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
    write_json(debug_dir / "scheduler_model_summary.json", scheduler_summary)
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
    completed_run_accounting = _complete_run_accounting(
        run_accounting,
        artifact_write_started_at,
    )
    reproduction_summary = {
        "source_mapping": {
            "rogers_slot_visibility_model": "reproduced as finite candidate slots and sampled V[t,j,p] visibility",
            "rogers_mmrt_design": "implemented for bounded cases with PuLP backend when available and deterministic fallback otherwise",
            "rogers_mart_design": "implemented for bounded cases with PuLP backend when available and deterministic fallback otherwise",
            "rogers_constrained_variants": "adapted as threshold_first and hybrid modes over expected revisit thresholds",
            "cho_window_generation": "adapted as feasible observation-window enumeration for selected slots",
            "cho_binary_scheduler": "adapted as binary conflict selection with marginal revisit-gap profit",
            "benchmark_resource_adaptation": "local validation and conservative repair cover overlap, sampled geometry, slew gaps, and battery margin",
        },
        "issue_88": {
            "exists": issue_88_url is not None,
            "url": issue_88_url,
        },
        "active_configuration": {
            "run_policy": config.run_policy,
            "slot_library_mode": config.slot_library_mode,
            "design_mode": design_result.mode,
            "design_backend": design_result.backend,
            "design_fallback_reason": design_result.fallback_reason,
            "scheduler_backend": schedule_result.backend,
            "scheduler_fallback_reason": schedule_result.fallback_reason,
            "local_repair_enabled": validation_result.repair_enabled,
            "scheduler_enable_slew_constraints": config.scheduler_enable_slew_constraints,
            "scheduler_enable_resource_constraints": config.scheduler_enable_resource_constraints,
        },
        "design_backend_report": design_result.to_summary()["backend_report"],
        "scheduler_backend_report": schedule_result.to_summary()["backend_report"],
        "slot_library": slot_summary,
        "design_backend_accounting": design_backend_accounting,
        "scheduler_backend_accounting": scheduler_backend_accounting,
        "scheduler_constraint_summary": schedule_result.constraint_summary,
        "visibility_execution": matrix.execution,
        "window_execution": window_result.execution,
        "run_accounting": completed_run_accounting,
        "design_mode_comparison": list(design_mode_comparison),
        "scheduler_mode_comparison": list(scheduler_mode_comparison),
        "validation": validation_result.to_summary(),
        "metric_drift": {
            "design_proxy": design_result.objective,
            "scheduled_estimate_before_repair": schedule_result.evaluation.to_dict(),
            "scheduled_estimate_after_repair": validation_result.estimated_metrics,
        },
    }
    write_json(debug_dir / "reproduction_summary.json", reproduction_summary)

    capacity = matrix.shape[0] * matrix.shape[1] * matrix.shape[2]
    status = {
        "solver": "rogers_mmrt_mart_binary_scheduler",
        "phase": "phase_6_validation_tuning_and_reproduction_fidelity",
        "case_dir": str(case.case_dir),
        "horizon_start": iso_z(case.horizon_start),
        "horizon_end": iso_z(case.horizon_end),
        "sample_step_sec": config.sample_step_sec,
        "slot_count": len(slots),
        "run_policy_name": config.run_policy,
        "slot_library_mode": config.slot_library_mode,
        "slot_library": slot_summary,
        "target_count": len(case.targets),
        "time_sample_count": len(samples),
        "visibility_shape": list(matrix.shape),
        "visibility_capacity": capacity,
        "visible_count": matrix.visible_count,
        "visibility_density": matrix.density,
        "visibility_execution": matrix.execution,
        "max_num_satellites": case.max_num_satellites,
        "slot_cap": config.max_slots,
        "altitude_count": config.altitude_count,
        "raan_count": config.raan_count,
        "phase_count": config.phase_count,
        "inclination_deg": list(config.inclination_deg),
        "design_mode": design_result.mode,
        "design_backend": design_result.backend,
        "design_fallback_reason": design_result.fallback_reason,
        "design_backend_report": design_result.to_summary()["backend_report"],
        "design_backend_accounting": design_backend_accounting,
        "design_objective": design_result.objective,
        "design_model_size": design_result.model_size,
        "design_mode_comparison": list(design_mode_comparison),
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
        "window_execution": window_result.execution,
        "scheduler_backend": schedule_result.backend,
        "scheduler_fallback_reason": schedule_result.fallback_reason,
        "scheduler_backend_report": schedule_result.to_summary()["backend_report"],
        "scheduler_backend_accounting": scheduler_backend_accounting,
        "scheduler_model_size": schedule_result.model_size,
        "scheduler_constraint_summary": schedule_result.constraint_summary,
        "scheduler_selected_window_count": len(schedule_result.selected_windows),
        "scheduler_selected_window_ids": list(schedule_result.selected_window_ids),
        "scheduler_conflict_edge_count": schedule_result.conflict_edge_count,
        "scheduler_transition_conflict_edge_count": schedule_result.transition_conflict_edge_count,
        "scheduler_estimated_metrics": schedule_result.evaluation.to_dict(),
        "scheduler_mode_comparison": list(scheduler_mode_comparison),
        "local_validation_issue_count": len(validation_result.issues),
        "local_repaired_window_count": len(validation_result.repaired_windows),
        "local_dropped_window_ids": list(validation_result.dropped_window_ids),
        "local_validation_metrics": validation_result.estimated_metrics,
        "target_visibility_counts": target_visibility_counts(matrix, case.targets),
        "run_accounting": completed_run_accounting,
        "timing": completed_run_accounting.get("timing", {}),
        "run_policy": completed_run_accounting.get("run_policy", {}),
        "issue_88_exists": issue_88_url is not None,
        "issue_88_url": issue_88_url,
        "solution_note": (
            "Phase 6 emits selected design satellites and scheduled observation actions. "
            "Debug artifacts record Rogers design mode comparisons, scheduler fallback "
            "behavior, and local validation/repair as benchmark adaptations."
        ),
    }
    write_json(solution_dir / "status.json", status)
