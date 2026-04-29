"""CLI for the J2 RGT set-cover solver."""

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


def _profile_status(config: dict[str, Any]) -> dict[str, Any]:
    profiles = config.get("profiles")
    profile_keys = sorted(profiles) if isinstance(profiles, dict) else []
    compute_envelope = config.get("compute_envelope")
    return {
        "active_profile": str(config.get("active_profile", "custom")),
        "compute_envelope": (
            compute_envelope if isinstance(compute_envelope, dict) else {}
        ),
        "available_profiles": profile_keys,
    }


def solve(case_dir: str, config_dir: str | None, solution_dir: str | None) -> int:
    start_time = time.perf_counter()
    output_dir = Path(solution_dir or ".").resolve()
    debug_dir = output_dir / "debug"
    timing_seconds: dict[str, float] = {}
    try:
        stage_start = time.perf_counter()
        case = load_case(case_dir)
        config = load_solver_config(config_dir)
        timing_seconds["case_and_config_load"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        search_config = RgtSearchConfig.from_mapping(config)
        result = search_rgt_templates(case, search_config)
        timing_seconds["closure_search"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        coverage_config = CoverageConfig.from_mapping(config)
        coverage = build_coverage_summary(
            case,
            result.accepted_templates,
            coverage_config,
        )
        timing_seconds["coverage"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        initial_selection = select_candidates(case, coverage)
        timing_seconds["initial_selection"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        scheduling_config = SchedulingConfig.from_mapping(config)
        initial_solution_result = build_solution(
            case=case,
            coverage=coverage,
            selection=initial_selection,
            config=scheduling_config,
        )
        timing_seconds["initial_solution_build"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        repair = repair_selection_with_phased_opportunities(
            case=case,
            coverage=coverage,
            selection=initial_selection,
            initial_gap_summary=initial_solution_result.target_gap_summary,
            config=scheduling_config,
        )
        timing_seconds["selection_repair"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        selection = repair.selection
        solution_result = build_solution(
            case=case,
            coverage=coverage,
            selection=selection,
            config=scheduling_config,
        )
        timing_seconds["final_solution_build"] = time.perf_counter() - stage_start
        timing_seconds["total_before_writes"] = time.perf_counter() - start_time

        solution = solution_result.solution_json()
        stage_start = time.perf_counter()
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
        timing_seconds["debug_writes"] = time.perf_counter() - stage_start
        timing_seconds["total"] = time.perf_counter() - start_time
        profile_status = _profile_status(config)
        compute_profile = {
            **profile_status,
            "coverage_worker_count": coverage.config.worker_count,
            "opportunity_worker_count": scheduling_config.opportunity_worker_count,
            "repair_worker_count": scheduling_config.repair_worker_count,
            "initial_solution_timing_seconds": initial_solution_result.timing_seconds,
            "final_solution_timing_seconds": solution_result.timing_seconds,
        }
        status = {
            "status": "completed",
            "solver": "j2_rgt_set_cover",
            "method_status": "experiment_ready",
            "case_dir": str(case.case_dir),
            "timing_seconds": timing_seconds,
            "compute_profile": compute_profile,
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
            "j2_rgt_set_cover templates/candidates/solution: "
            f"{len(result.accepted_templates)} accepted, "
            f"{len(result.rejected_templates)} rejected, "
            f"{len(coverage.candidates)} candidates, "
            f"{len(coverage.windows)} windows, "
            f"{len(selection.selected_candidates)} selected, "
            f"{len(solution_result.satellites)} satellites, "
            f"{len(solution_result.actions)} actions, "
            f"repair_rounds={len(repair.rounds)}, "
            f"workers={coverage.config.worker_count}/"
            f"{scheduling_config.opportunity_worker_count}/"
            f"{scheduling_config.repair_worker_count}, "
            f"profile={profile_status['active_profile']}, "
            f"local_valid={solution_result.validation.is_valid}"
        )
        return 0
    except (ValueError, FileNotFoundError, PermissionError, OSError, json.JSONDecodeError) as exc:
        write_json(
            output_dir / "status.json",
            {
                "status": "error",
                "solver": "j2_rgt_set_cover",
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
