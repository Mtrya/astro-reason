"""Solver entrypoint: generate candidates and emit actions for Phase 1."""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

from candidates import CandidateConfig, generate_candidates
from case_io import load_case, load_solver_config
from solution_io import write_json, write_empty_solution


def _build_status(
    *,
    case_dir: Path,
    config_dir: Path | None,
    solution_path: Path,
    case,
    candidate_config: CandidateConfig,
    candidate_summary,
    timing_seconds: dict[str, float],
) -> dict:
    return {
        "status": "phase_1_candidates_generated",
        "phase": 1,
        "case_dir": str(case_dir),
        "config_dir": str(config_dir) if config_dir is not None else None,
        "solution": str(solution_path),
        "case_id": case.mission.case_id,
        "satellite_count": len(case.satellites),
        "task_count": len(case.tasks),
        "candidate_config": candidate_config.as_status_dict(),
        "utility_policy": "weight_over_duration",
        **candidate_summary.as_debug_dict(case),
        "timing_seconds": timing_seconds,
    }


def _write_debug_artifacts(
    *,
    solution_dir: Path,
    case,
    candidate_config: CandidateConfig,
    candidate_summary,
    candidates,
    timing_seconds: dict[str, float],
) -> None:
    write_json(
        solution_dir / "debug" / "candidate_summary.json",
        {
            "case_id": case.mission.case_id,
            "candidate_config": candidate_config.as_status_dict(),
            "summary": candidate_summary.as_debug_dict(case),
        },
    )
    write_json(
        solution_dir / "debug" / "candidates.json",
        [candidate.as_dict() for candidate in candidates],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate AEOSSP greedy-LNS candidates and write a Phase-1 scaffold solution."
    )
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--config-dir", default="")
    parser.add_argument("--solution-dir", required=True)
    args = parser.parse_args(argv)

    case_dir = Path(args.case_dir).resolve()
    config_dir = Path(args.config_dir).resolve() if args.config_dir else None
    solution_dir = Path(args.solution_dir).resolve()

    try:
        total_start = time.perf_counter()
        config_payload = load_solver_config(config_dir)
        candidate_config = CandidateConfig.from_mapping(config_payload)
        case = load_case(case_dir)
        candidate_start = time.perf_counter()
        candidates, candidate_summary = generate_candidates(case, candidate_config)
        candidate_end = time.perf_counter()
        # Phase 1 writes an empty solution; schedule construction comes in Phase 2.
        solution_path = write_empty_solution(solution_dir)
        total_end = time.perf_counter()
        timing_seconds = {
            "candidate_generation": candidate_end - candidate_start,
            "total": total_end - total_start,
        }
        status = _build_status(
            case_dir=case_dir,
            config_dir=config_dir,
            solution_path=solution_path,
            case=case,
            candidate_config=candidate_config,
            candidate_summary=candidate_summary,
            timing_seconds=timing_seconds,
        )
        write_json(solution_dir / "status.json", status)
        if candidate_config.debug:
            _write_debug_artifacts(
                solution_dir=solution_dir,
                case=case,
                candidate_config=candidate_config,
                candidate_summary=candidate_summary,
                candidates=candidates,
                timing_seconds=timing_seconds,
            )
    except Exception as exc:
        traceback_text = traceback.format_exc()
        solution_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            solution_dir / "status.json",
            {
                "status": "error",
                "phase": 1,
                "case_dir": str(case_dir),
                "config_dir": str(config_dir) if config_dir is not None else None,
                "error": str(exc),
                "traceback": traceback_text,
            },
        )
        print(traceback_text, file=sys.stderr, end="")
        return 2

    print(
        f"phase_1_candidates_generated: {case.mission.case_id} "
        f"candidates={candidate_summary.candidate_count} "
        f"satellites={len(case.satellites)} "
        f"tasks={len(case.tasks)} -> {solution_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
