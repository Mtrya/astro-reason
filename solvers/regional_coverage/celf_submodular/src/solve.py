"""Phase 1 regional-coverage CELF scaffold entrypoint."""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from candidates import generate_candidates, load_candidate_config
from case_io import load_case
from coverage import build_candidate_coverage
from solution_io import write_candidate_debug, write_empty_solution, write_json


def _config_dir(value: str) -> Path | None:
    if not value:
        return None
    return Path(value)


def _round_seconds(value: float) -> float:
    return round(value, 6)


def _build_status(
    *,
    case,
    config_dir: Path | None,
    solution_path: Path,
    candidate_config,
    candidate_summary,
    coverage_summary,
    timing_seconds: dict[str, float],
) -> dict[str, Any]:
    return {
        "status": "ok",
        "phase": "phase_1_contract_candidates_and_coverage",
        "case_dir": str(case.case_dir),
        "config_dir": str(config_dir) if config_dir is not None else None,
        "solution": str(solution_path),
        "case": {
            "case_id": case.manifest.case_id,
            "benchmark": case.manifest.benchmark,
            "spec_version": case.manifest.spec_version,
            "horizon_start": case.manifest.horizon_start.isoformat(),
            "horizon_end": case.manifest.horizon_end.isoformat(),
            "horizon_seconds": case.manifest.horizon_seconds,
            "time_step_s": case.manifest.time_step_s,
            "coverage_sample_step_s": case.manifest.coverage_sample_step_s,
            "max_actions_total": case.manifest.max_actions_total,
        },
        "parsed_counts": {
            "satellite_count": len(case.satellites),
            "region_count": len(case.regions),
            "sample_count": len(case.coverage_grid.samples),
        },
        "candidate_config": candidate_config.as_status_dict(),
        "candidate_summary": candidate_summary.as_dict(),
        "coverage_summary": coverage_summary.as_dict(),
        "output_policy": {
            "solution_actions": 0,
            "empty_solution_only": True,
            "selection_deferred_to_phase": 2,
            "sequence_feasibility_deferred_to_phase": 3,
            "coverage_geometry": "solver-local circular-orbit approximation",
        },
        "timing_seconds": timing_seconds,
    }


def run(case_dir: Path, config_dir: Path | None, solution_dir: Path) -> int:
    total_start = time.perf_counter()
    solution_dir.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}

    start = time.perf_counter()
    case = load_case(case_dir)
    candidate_config = load_candidate_config(config_dir)
    timings["case_loading"] = _round_seconds(time.perf_counter() - start)

    start = time.perf_counter()
    candidates, candidate_summary = generate_candidates(case, candidate_config)
    timings["candidate_generation"] = _round_seconds(time.perf_counter() - start)

    start = time.perf_counter()
    coverage_by_candidate, coverage_summary = build_candidate_coverage(case, candidates)
    timings["coverage_mapping"] = _round_seconds(time.perf_counter() - start)

    start = time.perf_counter()
    solution_path = write_empty_solution(solution_dir)
    write_candidate_debug(
        solution_dir,
        candidates,
        coverage_by_candidate,
        limit=candidate_config.debug_candidate_limit,
    )
    timings["output"] = _round_seconds(time.perf_counter() - start)
    timings["total"] = _round_seconds(time.perf_counter() - total_start)

    status = _build_status(
        case=case,
        config_dir=config_dir,
        solution_path=solution_path,
        candidate_config=candidate_config,
        candidate_summary=candidate_summary,
        coverage_summary=coverage_summary,
        timing_seconds=timings,
    )
    write_json(solution_dir / "status.json", status)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", required=True, type=Path)
    parser.add_argument("--config-dir", default="", type=str)
    parser.add_argument("--solution-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        return run(args.case_dir, _config_dir(args.config_dir), args.solution_dir)
    except Exception as exc:
        args.solution_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            args.solution_dir / "status.json",
            {
                "status": "error",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        print(f"regional coverage CELF scaffold failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
