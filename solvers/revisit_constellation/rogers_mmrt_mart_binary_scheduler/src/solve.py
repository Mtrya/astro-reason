"""Phase 2 entrypoint for Rogers MMRT/MART solver preprocessing."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import time
from typing import Iterator

from .binary_scheduler import compare_scheduler_modes, schedule_observation_windows
from .case_io import load_case, load_solver_config
from .design_models import build_design_problem, compare_design_modes, select_design_slots
from .observation_windows import enumerate_observation_windows
from .slot_library import build_slot_library
from .solution_io import write_preprocessing_artifacts, write_slot_solution
from .time_grid import build_time_grid
from .validation import validate_and_repair_schedule
from .visibility_matrix import build_visibility_matrix


ISSUE_88_URL = "https://github.com/Mtrya/astro-reason/issues/88"


class RunProfiler:
    def __init__(self) -> None:
        self.started_at = time.perf_counter()
        self.stage_durations_sec: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started_at = time.perf_counter()
        try:
            yield
        finally:
            self.stage_durations_sec[name] = round(time.perf_counter() - started_at, 6)

    def to_accounting(self, config) -> dict[str, object]:
        return {
            "timing": {
                "clock": "time.perf_counter",
                "total_elapsed_sec": round(time.perf_counter() - self.started_at, 6),
                "stage_durations_sec": dict(self.stage_durations_sec),
            },
            "run_policy": {
                "policy_name": "ci_smoke_defaults",
                "bounded": True,
                "sample_step_sec": config.sample_step_sec,
                "window_stride_sec": config.window_stride_sec,
                "window_geometry_sample_step_sec": config.window_geometry_sample_step_sec,
                "geometry_worker_count": config.geometry_worker_count,
                "max_slots": config.max_slots,
                "max_observation_windows": config.max_observation_windows,
                "scheduler_max_selected_windows": config.scheduler_max_selected_windows,
                "design_time_limit_sec": config.design_time_limit_sec,
                "scheduler_time_limit_sec": config.scheduler_time_limit_sec,
                "design_backend": config.design_backend,
                "scheduler_backend": config.scheduler_backend,
                "write_visibility_matrix": config.write_visibility_matrix,
                "write_observation_windows": config.write_observation_windows,
            },
        }


def solve(case_dir: Path, config_dir: str | None, solution_dir: Path) -> None:
    profiler = RunProfiler()
    with profiler.stage("case_config_loading"):
        case = load_case(case_dir)
        config = load_solver_config(config_dir)
    with profiler.stage("slot_library_generation"):
        slots = build_slot_library(case, config)
    with profiler.stage("time_grid_generation"):
        samples = build_time_grid(case.horizon_start, case.horizon_end, config.sample_step_sec)
    with profiler.stage("visibility_matrix_generation"):
        matrix = build_visibility_matrix(
            case,
            slots,
            samples,
            worker_count=config.geometry_worker_count,
        )
    with profiler.stage("design_solve"):
        design_problem = build_design_problem(case, config, slots, matrix)
        design_result = select_design_slots(design_problem, config)
    with profiler.stage("observation_window_enumeration"):
        window_result = enumerate_observation_windows(case, config, slots, design_result)
    with profiler.stage("scheduler_solve"):
        schedule_result = schedule_observation_windows(case, config, window_result)
    with profiler.stage("local_validation_repair"):
        validation_result = validate_and_repair_schedule(case, config, slots, schedule_result)
    with profiler.stage("debug_comparisons"):
        design_mode_comparison = compare_design_modes(design_problem, config)
        scheduler_mode_comparison = compare_scheduler_modes(
            case, config, window_result, schedule_result
        )

    solution_dir.mkdir(parents=True, exist_ok=True)
    run_accounting = profiler.to_accounting(config)
    artifact_write_started_at = time.perf_counter()
    write_slot_solution(
        solution_dir,
        slots,
        design_result.selected_slot_indices,
        schedule_result,
        validation_result.repaired_windows,
    )
    write_preprocessing_artifacts(
        solution_dir,
        case,
        config,
        slots,
        samples,
        matrix,
        design_result,
        window_result,
        schedule_result,
        validation_result,
        design_mode_comparison,
        scheduler_mode_comparison,
        issue_88_url=ISSUE_88_URL,
        run_accounting=run_accounting,
        artifact_write_started_at=artifact_write_started_at,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", required=True, type=Path)
    parser.add_argument("--config-dir", default="")
    parser.add_argument("--solution-dir", required=True, type=Path)
    args = parser.parse_args()
    solve(args.case_dir, args.config_dir or None, args.solution_dir)


if __name__ == "__main__":
    main()
