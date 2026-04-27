"""Phase 4 CLI for the J2 RGT set-cover solver."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sys
import time

from .case_io import load_case, load_solver_config
from .coverage import CoverageConfig, build_coverage_summary
from .rgt import RgtSearchConfig, search_rgt_templates
from .selection import select_candidates
from .solution import (
    SchedulingConfig,
    build_solution,
    repair_selection_with_phased_opportunities,
)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def solve(case_dir: str, config_dir: str | None, solution_dir: str | None) -> int:
    start_time = time.perf_counter()
    output_dir = Path(solution_dir or ".").resolve()
    debug_dir = output_dir / "debug"
    try:
        case = load_case(case_dir)
        config = load_solver_config(config_dir)
        search_config = RgtSearchConfig.from_mapping(config)
        result = search_rgt_templates(case, search_config)
        coverage_config = CoverageConfig.from_mapping(config)
        coverage = build_coverage_summary(
            case,
            result.accepted_templates,
            coverage_config,
        )
        initial_selection = select_candidates(case, coverage)
        scheduling_config = SchedulingConfig.from_mapping(config)
        initial_solution_result = build_solution(
            case=case,
            coverage=coverage,
            selection=initial_selection,
            config=scheduling_config,
        )
        repair = repair_selection_with_phased_opportunities(
            case=case,
            coverage=coverage,
            selection=initial_selection,
            initial_gap_summary=initial_solution_result.target_gap_summary,
            config=scheduling_config,
        )
        selection = repair.selection
        solution_result = build_solution(
            case=case,
            coverage=coverage,
            selection=selection,
            config=scheduling_config,
        )

        solution = solution_result.solution_json()
        write_json(output_dir / "solution.json", solution)
        write_json(debug_dir / "closure_search.json", result.as_debug_dict())
        write_json(debug_dir / "coverage_summary.json", coverage.as_debug_dict())
        write_json(debug_dir / "selection_summary.json", selection.as_debug_dict())
        write_json(
            debug_dir / "initial_selection_summary.json",
            initial_selection.as_debug_dict(),
        )
        write_json(
            debug_dir / "selection_repair_summary.json",
            repair.as_debug_dict(final_gap_summary=solution_result.target_gap_summary),
        )
        write_json(debug_dir / "solution_summary.json", solution_result.as_debug_dict())
        status = {
            "status": "completed",
            "phase": 5,
            "phase_tag": "phased_opportunity_selection_repair",
            "case_dir": str(case.case_dir),
            "timing_seconds": {"total": time.perf_counter() - start_time},
            "closure_search": {
                "accepted_count": len(result.accepted_templates),
                "rejected_count": len(result.rejected_templates),
                "considered_seed_count": result.considered_seed_count,
                "closure_tolerance_m": search_config.closure_tolerance_m,
                "best_surface_error_m": (
                    None
                    if not result.accepted_templates
                    or result.accepted_templates[0].closure is None
                    else result.accepted_templates[0].closure.surface_error_m
                ),
            },
            "coverage": coverage.as_status_dict(),
            "selection": selection.as_status_dict(),
            "selection_repair": repair.as_debug_dict(
                final_gap_summary=solution_result.target_gap_summary
            ),
            "solution": solution_result.as_status_dict(),
        }
        write_json(output_dir / "status.json", status)
        print(
            "phase5 rgt templates/candidates/solution: "
            f"{len(result.accepted_templates)} accepted, "
            f"{len(result.rejected_templates)} rejected, "
            f"{len(coverage.candidates)} candidates, "
            f"{len(coverage.windows)} windows, "
            f"{len(selection.selected_candidates)} selected, "
            f"{len(solution_result.satellites)} satellites, "
            f"{len(solution_result.actions)} actions, "
            f"repair_rounds={len(repair.rounds)}, "
            f"local_valid={solution_result.validation.is_valid}"
        )
        return 0
    except Exception as exc:
        write_json(
            output_dir / "status.json",
            {
                "status": "error",
                "phase": 5,
                "error": f"{type(exc).__name__}: {exc}",
                "timing_seconds": {"total": time.perf_counter() - start_time},
            },
        )
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: solve.py <case_dir> [config_dir] [solution_dir]", file=sys.stderr)
        return 2
    case_dir = args[0]
    config_dir = args[1] if len(args) > 1 else None
    solution_dir = args[2] if len(args) > 2 else None
    return solve(case_dir, config_dir, solution_dir)


if __name__ == "__main__":
    raise SystemExit(main())
