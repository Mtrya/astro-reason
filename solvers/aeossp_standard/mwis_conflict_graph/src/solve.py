"""Phase 1 solver entrypoint: load a case, generate candidates, emit empty solution."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from candidates import CandidateConfig, generate_candidates
from case_io import load_case, load_solver_config
from solution_io import write_empty_solution, write_json


def _build_status(
    *,
    case_dir: Path,
    config_dir: Path | None,
    solution_path: Path,
    case,
    candidate_config: CandidateConfig,
    summary,
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
        **summary.as_dict(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate AEOSSP MWIS candidates and write a Phase 1 empty solution."
    )
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--config-dir", default="")
    parser.add_argument("--solution-dir", required=True)
    args = parser.parse_args(argv)

    case_dir = Path(args.case_dir).resolve()
    config_dir = Path(args.config_dir).resolve() if args.config_dir else None
    solution_dir = Path(args.solution_dir).resolve()

    try:
        config_payload = load_solver_config(config_dir)
        candidate_config = CandidateConfig.from_mapping(config_payload)
        case = load_case(case_dir)
        candidates, summary = generate_candidates(case, candidate_config)
        solution_path = write_empty_solution(solution_dir)
        status = _build_status(
            case_dir=case_dir,
            config_dir=config_dir,
            solution_path=solution_path,
            case=case,
            candidate_config=candidate_config,
            summary=summary,
        )
        write_json(solution_dir / "status.json", status)
        if candidate_config.debug:
            write_json(
                solution_dir / "debug" / "candidate_summary.json",
                {
                    "case_id": case.mission.case_id,
                    "candidate_config": candidate_config.as_status_dict(),
                    "summary": summary.as_dict(),
                },
            )
            write_json(
                solution_dir / "debug" / "candidates.json",
                [candidate.as_dict() for candidate in candidates],
            )
    except Exception as exc:
        solution_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            solution_dir / "status.json",
            {
                "status": "error",
                "phase": 1,
                "case_dir": str(case_dir),
                "config_dir": str(config_dir) if config_dir is not None else None,
                "error": str(exc),
            },
        )
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"phase_1_candidates_generated: {case.mission.case_id} "
        f"candidates={summary.candidate_count} -> {solution_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
