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
from .greedy import GreedyConfig, greedy_insertion
from .local_search import LocalSearchConfig, local_search
from .sequence import is_consistent
from .solution_io import candidates_to_solution, write_json


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
        config_payload = load_solver_config(config_dir)
        config = SolverConfig.from_mapping(config_payload)
        greedy_config = GreedyConfig.from_mapping(config_payload)
        local_search_config = LocalSearchConfig.from_mapping(config_payload)
        case = load_case(case_dir)
        coverage_index = CoverageIndex.from_case(case)
        candidates, candidate_summary = generate_candidates(case, config, coverage_index)
        greedy_result = greedy_insertion(
            case,
            candidates,
            coverage_index=coverage_index,
            config=greedy_config,
        )
        local_search_result = local_search(
            case,
            candidates,
            coverage_index=coverage_index,
            greedy_result=greedy_result,
            greedy_config=greedy_config,
            config=local_search_config,
        )
        selected_candidates = local_search_result.selected_in_solution_order()
        write_json(solution_path, candidates_to_solution(case.mission, selected_candidates))

        debug_dir = solution_dir / "debug"
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
        local_validation = _local_validation_summary(case, local_search_result)
        elapsed = time.perf_counter() - t0
        write_json(
            solution_dir / "status.json",
            {
                "status": "greedy_solution_generated",
                "case_dir": str(case_dir),
                "config_dir": str(config_dir) if config_dir is not None else None,
                "solution": str(solution_path),
                "case_id": case.mission.case_id,
                "satellite_count": len(case.satellites),
                "region_count": len(case.regions),
                "coverage_sample_count": len(case.samples),
                "candidate_config": config.as_dict(),
                "candidate_summary": candidate_summary.as_dict(),
                "greedy_config": greedy_config.as_dict(),
                "greedy_summary": greedy_result.summary.as_dict(),
                "local_search_config": local_search_config.as_dict(),
                "local_search_summary": local_search_result.summary.as_dict(),
                "sequence_model": local_search_result.state.as_dict(),
                "local_validation": local_validation,
                "timing_seconds": {"total": elapsed},
                "reproduction_notes": {
                    "method_reference": "Antuori, Wojtowicz, and Hebrard, CP 2025, Sections 2 and 4.1",
                    "phase": "3_local_search_neighborhoods",
                    "implemented": [
                        "standalone case parser",
                        "deterministic fixed-start strip candidates",
                        "solver-local coverage-grid mapping",
                        "benchmark-compatible roll transition helpers",
                        "satellite-local sequence model",
                        "marginal unique coverage greedy insertion",
                        "bounded deterministic local-search neighborhoods",
                        "greedy neighborhood rebuild",
                    ],
                    "omitted_until_later_phases": [
                        "CP-assisted TSPTW repair",
                        "battery and duty repair",
                    ],
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


if __name__ == "__main__":
    raise SystemExit(main())
