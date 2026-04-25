"""Solution and preprocessing artifact writers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .case_io import RevisitCase, SolverConfig, iso_z
from .slot_library import OrbitSlot, slots_to_records
from .time_grid import TimeSample, time_grid_to_records
from .visibility_matrix import VisibilityMatrix, target_visibility_counts, visibility_to_sparse_records


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_empty_solution(solution_dir: Path) -> Path:
    path = solution_dir / "solution.json"
    write_json(path, {"satellites": [], "actions": []})
    return path


def write_preprocessing_artifacts(
    solution_dir: Path,
    case: RevisitCase,
    config: SolverConfig,
    slots: tuple[OrbitSlot, ...],
    samples: tuple[TimeSample, ...],
    matrix: VisibilityMatrix,
    *,
    issue_88_url: str | None,
) -> None:
    prep_dir = solution_dir / "model_prep"
    write_json(prep_dir / "slots.json", {"slots": slots_to_records(slots)})
    write_json(prep_dir / "time_grid.json", {"samples": time_grid_to_records(samples)})
    if config.write_visibility_matrix:
        write_json(prep_dir / "visibility_matrix.json", visibility_to_sparse_records(matrix))

    capacity = matrix.shape[0] * matrix.shape[1] * matrix.shape[2]
    status = {
        "solver": "rogers_mmrt_mart_binary_scheduler",
        "phase": "phase_1_contract_slot_library_and_visibility_matrix",
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
        "target_visibility_counts": target_visibility_counts(matrix, case.targets),
        "issue_88_exists": issue_88_url is not None,
        "issue_88_url": issue_88_url,
        "solution_note": "Phase 1 emits an empty schedule; design and scheduling are out of scope.",
    }
    write_json(solution_dir / "status.json", status)

