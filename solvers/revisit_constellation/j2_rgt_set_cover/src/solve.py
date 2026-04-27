"""Phase 1 CLI for the J2 RGT set-cover solver."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sys
import time

from .case_io import load_case, load_solver_config
from .rgt import RgtSearchConfig, search_rgt_templates


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

        solution = {"satellites": [], "actions": []}
        write_json(output_dir / "solution.json", solution)
        write_json(debug_dir / "closure_search.json", result.as_debug_dict())
        status = {
            "status": "completed",
            "phase": 1,
            "phase_tag": "j2_rgt_orbit_construction",
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
        }
        write_json(output_dir / "status.json", status)
        print(
            "phase1 rgt templates: "
            f"{len(result.accepted_templates)} accepted, "
            f"{len(result.rejected_templates)} rejected"
        )
        return 0
    except Exception as exc:
        write_json(
            output_dir / "status.json",
            {
                "status": "error",
                "phase": 1,
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
