"""Phase 2 entrypoint for Rogers MMRT/MART solver preprocessing."""

from __future__ import annotations

import argparse
from pathlib import Path

from .binary_scheduler import schedule_observation_windows
from .case_io import load_case, load_solver_config
from .design_models import build_design_problem, select_design_slots
from .observation_windows import enumerate_observation_windows
from .slot_library import build_slot_library
from .solution_io import write_preprocessing_artifacts, write_slot_solution
from .time_grid import build_time_grid
from .validation import validate_and_repair_schedule
from .visibility_matrix import build_visibility_matrix


ISSUE_88_URL = "https://github.com/Mtrya/astro-reason/issues/88"


def solve(case_dir: Path, config_dir: str | None, solution_dir: Path) -> None:
    case = load_case(case_dir)
    config = load_solver_config(config_dir)
    slots = build_slot_library(case, config)
    samples = build_time_grid(case.horizon_start, case.horizon_end, config.sample_step_sec)
    matrix = build_visibility_matrix(case, slots, samples)
    design_problem = build_design_problem(case, config, slots, matrix)
    design_result = select_design_slots(design_problem, config)
    window_result = enumerate_observation_windows(case, config, slots, design_result)
    schedule_result = schedule_observation_windows(case, config, window_result)
    validation_result = validate_and_repair_schedule(case, config, slots, schedule_result)

    solution_dir.mkdir(parents=True, exist_ok=True)
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
        issue_88_url=ISSUE_88_URL,
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
