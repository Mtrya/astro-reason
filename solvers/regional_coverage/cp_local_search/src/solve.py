"""Phase-1 solver entrypoint: parse, enumerate candidates, write empty solution."""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

from .candidates import generate_candidates
from .case_io import SolverConfig, load_case, load_solver_config
from .coverage import CoverageIndex
from .sequence import create_empty_state
from .solution_io import write_empty_solution, write_json


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
        case = load_case(case_dir)
        coverage_index = CoverageIndex.from_case(case)
        candidates, candidate_summary = generate_candidates(case, config, coverage_index)
        sequence_state = create_empty_state(case)
        write_empty_solution(solution_path)

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
        elapsed = time.perf_counter() - t0
        write_json(
            solution_dir / "status.json",
            {
                "status": "empty_solution_with_phase_1_scaffold",
                "case_dir": str(case_dir),
                "config_dir": str(config_dir) if config_dir is not None else None,
                "solution": str(solution_path),
                "case_id": case.mission.case_id,
                "satellite_count": len(case.satellites),
                "region_count": len(case.regions),
                "coverage_sample_count": len(case.samples),
                "candidate_config": config.as_dict(),
                "candidate_summary": candidate_summary.as_dict(),
                "sequence_model": sequence_state.as_dict(),
                "timing_seconds": {"total": elapsed},
                "reproduction_notes": {
                    "method_reference": "Antuori, Wojtowicz, and Hebrard, CP 2025, Sections 2 and 4.1",
                    "phase": "1_contract_candidates_and_sequence_model",
                    "implemented": [
                        "standalone case parser",
                        "deterministic fixed-start strip candidates",
                        "solver-local coverage-grid mapping",
                        "benchmark-compatible roll transition helpers",
                        "satellite-local sequence model",
                    ],
                    "omitted_until_later_phases": [
                        "greedy insertion schedule construction",
                        "local-search neighborhoods",
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


if __name__ == "__main__":
    raise SystemExit(main())

