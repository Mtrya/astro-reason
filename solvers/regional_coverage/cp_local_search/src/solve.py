"""Solver entrypoint: parse, enumerate candidates, build a greedy schedule."""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from .candidates import generate_candidates
from .case_io import SolverConfig, load_case, load_solver_config
from .coverage import CoverageIndex
from .cp_repair import CPRepairConfig
from .greedy import GreedyConfig
from .local_search import LocalSearchConfig
from .search import SearchConfig, run_search
from .sequence import is_consistent
from .solution_io import candidates_to_solution, write_json
from .timing import PhaseTimer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build regional_coverage CP/local-search phase-1 candidates and emit an empty solution."
    )
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--config-dir", default="")
    parser.add_argument("--solution-dir", required=True)
    args = parser.parse_args(argv)

    case_dir = Path(args.case_dir).resolve()
    config_dir = Path(args.config_dir).resolve() if args.config_dir else None
    solution_dir = Path(args.solution_dir).resolve()
    solution_path = solution_dir / "solution.json"

    try:
        t0 = time.perf_counter()
        phase_timer = PhaseTimer()
        with phase_timer.phase("config_loading"):
            config_payload = load_solver_config(config_dir)
        config = SolverConfig.from_mapping(config_payload)
        search_config = SearchConfig.from_mapping(config_payload)
        greedy_config = GreedyConfig.from_mapping(config_payload)
        local_search_config = LocalSearchConfig.from_mapping(config_payload)
        cp_config = CPRepairConfig.from_mapping(config_payload)
        with phase_timer.phase("case_parsing"):
            case = load_case(case_dir)
        with phase_timer.phase("coverage_index"):
            coverage_index = CoverageIndex.from_case(case)
        with phase_timer.phase("candidate_generation"):
            candidates, candidate_summary = generate_candidates(case, config, coverage_index)
        with phase_timer.phase("search"):
            search_result = run_search(
                case,
                candidates,
                coverage_index=coverage_index,
                search_config=search_config,
                greedy_config=greedy_config,
                local_search_config=local_search_config,
                cp_config=cp_config,
            )
        greedy_result = search_result.greedy_result
        local_search_result = search_result.local_search_result
        selected_candidates = local_search_result.selected_in_solution_order()
        with phase_timer.phase("solution_writing"):
            write_json(solution_path, candidates_to_solution(case.mission, selected_candidates))

        debug_dir = solution_dir / "debug"
        with phase_timer.phase("debug_writing"):
            write_json(
                debug_dir / "candidate_summary.json",
                {
                    "case_id": case.mission.case_id,
                    "config": config.as_dict(),
                    "summary": candidate_summary.as_dict(),
                },
            )
            write_json(
                debug_dir / "candidates.json",
                [candidate.as_dict() for candidate in candidates[: config.candidate_debug_limit]],
            )
            write_json(
                debug_dir / "greedy_summary.json",
                {
                    "case_id": case.mission.case_id,
                    "config": greedy_config.as_dict(),
                    "summary": greedy_result.summary.as_dict(),
                },
            )
            write_json(
                debug_dir / "selected_candidates.json",
                [candidate.as_dict() for candidate in selected_candidates],
            )
            write_json(
                debug_dir / "local_search_summary.json",
                {
                    "case_id": case.mission.case_id,
                    "config": local_search_config.as_dict(),
                    "summary": local_search_result.summary.as_dict(),
                },
            )
            write_json(
                debug_dir / "search_summary.json",
                {
                    "case_id": case.mission.case_id,
                    "config": search_config.as_dict(),
                    "summary": search_result.summary.as_dict(),
                },
            )
            if greedy_config.write_insertion_attempts:
                attempts_path = debug_dir / "insertion_attempts.jsonl"
                attempts_path.parent.mkdir(parents=True, exist_ok=True)
                attempts_path.write_text(
                    "".join(
                        json.dumps(item, sort_keys=True) + "\n"
                        for item in greedy_result.attempt_debug
                    ),
                    encoding="utf-8",
                )
            if local_search_config.write_move_log:
                moves_path = debug_dir / "moves.jsonl"
                moves_path.parent.mkdir(parents=True, exist_ok=True)
                moves_path.write_text(
                    "".join(
                        json.dumps(move.as_dict(), sort_keys=True) + "\n"
                        for move in local_search_result.moves
                    ),
                    encoding="utf-8",
                )
        with phase_timer.phase("local_validation"):
            local_validation = _local_validation_summary(case, local_search_result)
        elapsed = time.perf_counter() - t0
        timing_seconds = _timing_summary(
            total_elapsed_s=elapsed,
            phase_timer=phase_timer,
            cp_summary=local_search_result.summary.cp_metrics,
        )
        write_json(
            solution_dir / "status.json",
            {
                "status": "solution_generated",
                "case_dir": str(case_dir),
                "config_dir": str(config_dir) if config_dir is not None else None,
                "solution": str(solution_path),
                "case_id": case.mission.case_id,
                "execution_mode": _execution_mode(local_search_config, cp_config),
                "satellite_count": len(case.satellites),
                "region_count": len(case.regions),
                "coverage_sample_count": len(case.samples),
                "candidate_config": config.as_dict(),
                "candidate_summary": candidate_summary.as_dict(),
                "search_config": search_config.as_dict(),
                "search_summary": search_result.summary.as_dict(),
                "greedy_config": greedy_config.as_dict(),
                "greedy_summary": greedy_result.summary.as_dict(),
                "local_search_config": local_search_config.as_dict(),
                "local_search_summary": local_search_result.summary.as_dict(),
                "cp_config": cp_config.as_dict(),
                "cp_summary": local_search_result.summary.cp_metrics,
                "sequence_model": local_search_result.state.as_dict(),
                "local_validation": local_validation,
                "timing_seconds": timing_seconds,
                "reproduction_notes": {
                    "method_reference": "Antuori, Wojtowicz, and Hebrard, CP 2025, Sections 2 and 4.1",
                    "phase": "6_tuning_and_reproduction_fidelity",
                    "implemented": [
                        "standalone case parser",
                        "deterministic fixed-start strip candidates",
                        "solver-local coverage-grid mapping",
                        "benchmark-compatible roll transition helpers",
                        "satellite-local sequence model",
                        "marginal unique coverage greedy insertion",
                        "bounded deterministic local-search neighborhoods",
                        "greedy neighborhood rebuild",
                        "bounded OR-Tools CP-SAT sequence repair in local neighborhoods",
                        "verifier-shaped solver-local strip coverage scoring",
                        "CP call success and improvement-rate reporting",
                        "seeded restart and multi-start search orchestration",
                    ],
                    "omitted_until_later_phases": [
                        "battery and duty repair",
                    ],
                    "backend_note": (
                        "OR-Tools is installed in the solver-local environment by setup.sh; "
                        "CP assistance is implemented as bounded CP-SAT repair over fixed-start "
                        "TSPTW-style neighborhood subproblems."
                    ),
                },
            },
        )
        return 0
    except Exception as exc:  # pragma: no cover - exercised by CLI failures
        solution_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            solution_dir / "status.json",
            {
                "status": "error",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        print(f"regional_coverage cp_local_search failed: {exc}", file=sys.stderr)
        return 2


def _timing_summary(
    *,
    total_elapsed_s: float,
    phase_timer: PhaseTimer,
    cp_summary: dict,
) -> dict:
    model_build_s = float(cp_summary.get("model_build_time_s", 0.0))
    solve_s = float(cp_summary.get("solve_time_s", 0.0))
    return {
        "total": total_elapsed_s,
        "wall_phases": phase_timer.as_dict(),
        "reported_subphases": {
            "cp_repair": {
                "source": "cp_metrics",
                "model_build": model_build_s,
                "solve": solve_s,
                "total": model_build_s + solve_s,
            },
        },
    }


def _local_validation_summary(case, greedy_result) -> dict:
    per_satellite: dict[str, dict] = {}
    valid = True
    for satellite_id, sequence in sorted(greedy_result.state.sequences.items()):
        sequence_valid, reasons = is_consistent(case, sequence)
        valid = valid and sequence_valid
        per_satellite[satellite_id] = {
            "valid": sequence_valid,
            "issues": reasons,
            "candidate_count": len(sequence.candidates),
        }
    return {
        "valid": valid,
        "selected_count": len(greedy_result.selected_candidates),
        "covered_sample_count": len(greedy_result.covered_sample_ids),
        "per_satellite": per_satellite,
    }


def _execution_mode(local_search_config: LocalSearchConfig, cp_config: CPRepairConfig) -> str:
    if not local_search_config.enabled:
        return "greedy_only"
    if not cp_config.enabled:
        return "local_search_greedy_rebuild"
    return "cp_enabled_local_search"


if __name__ == "__main__":
    raise SystemExit(main())
