"""Solver entrypoint: generate candidates and emit empty valid solution."""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from candidates import generate_candidates
from case_io import load_case, load_solver_config
from models import CandidateObservation


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)


def _candidate_to_action(cand: CandidateObservation) -> dict:
    return {
        "type": "observation",
        "satellite_id": cand.sat_id,
        "target_id": cand.target_id,
        "start_time": cand.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time": cand.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "off_nadir_along_deg": cand.off_nadir_along_deg,
        "off_nadir_across_deg": cand.off_nadir_across_deg,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase-1 stereo MILP scaffold: candidate generation + empty solution."
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
        mission, satellites, targets = load_case(case_dir)

        candidate_start = time.perf_counter()
        candidates, rejections, summary = generate_candidates(
            mission, satellites, targets, config_payload
        )
        candidate_end = time.perf_counter()

        # Phase 1 emits empty valid solution; candidates are debug-only.
        solution = {"actions": []}
        solution_path = solution_dir / "solution.json"
        _write_json(solution_path, solution)

        status = {
            "status": "phase_1_candidate_library_generated",
            "phase": 1,
            "case_dir": str(case_dir),
            "config_dir": str(config_dir) if config_dir is not None else None,
            "solution": str(solution_path),
            "satellite_count": len(satellites),
            "target_count": len(targets),
            "candidate_counts": summary.as_dict(),
            "timing_seconds": {
                "candidate_generation": candidate_end - candidate_start,
                "total": time.perf_counter() - total_start,
            },
            "approximation_flags": {
                "access_intervals": "coarse_time_step_approximate",
                "solar_elevation": "sampled_at_midpoint",
                "los": "checked_at_midpoint",
                "note": "Exact SGP4/access reproduction deferred to Phase 6; drift expected.",
            },
        }
        _write_json(solution_dir / "status.json", status)

        if config_payload.get("debug", False):
            debug_dir = solution_dir / "debug"
            _write_json(
                debug_dir / "candidate_summary.json",
                {
                    "case_dir": str(case_dir),
                    "candidate_counts": summary.as_dict(),
                    "sample_candidates": [_candidate_to_action(c) for c in candidates[:50]],
                    "sample_rejections": [
                        {
                            "sat_id": r.sat_id,
                            "target_id": r.target_id,
                            "interval_id": r.interval_id,
                            "reason": r.reason,
                            "start": r.start.strftime("%Y-%m-%dT%H:%M:%SZ") if r.start else None,
                            "end": r.end.strftime("%Y-%m-%dT%H:%M:%SZ") if r.end else None,
                        }
                        for r in rejections[:50]
                    ],
                },
            )

    except Exception as exc:
        traceback_text = traceback.format_exc()
        solution_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
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
        f"phase_1_candidate_library_generated: case={case_dir.name} "
        f"candidates={summary.total_accepted} rejected={summary.total_rejected} "
        f"-> {solution_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
