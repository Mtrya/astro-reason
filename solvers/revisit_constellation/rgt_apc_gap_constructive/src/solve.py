"""Phase-1 solver entrypoint for RGT/APC candidate and visibility construction."""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

from .case_io import load_case, load_solver_config
from .orbit_library import OrbitLibraryConfig, generate_orbit_library
from .solution_io import write_empty_solution, write_json
from .visibility import VisibilityConfig, build_visibility_library


def _build_status(
    *,
    case_dir: Path,
    config_dir: Path | None,
    solution_path: Path,
    case,
    orbit_config: OrbitLibraryConfig,
    visibility_config: VisibilityConfig,
    orbit_library,
    visibility_library,
    timing_seconds: dict[str, float],
) -> dict:
    return {
        "status": "phase_1_scaffold_solution_generated",
        "phase": 1,
        "case_dir": str(case_dir),
        "config_dir": str(config_dir) if config_dir is not None else None,
        "solution": str(solution_path),
        "case_id": case.case_id,
        "target_count": len(case.targets),
        "max_num_satellites": case.max_num_satellites,
        "horizon_duration_sec": case.horizon_duration_sec,
        "satellite_output_count": 0,
        "action_output_count": 0,
        "orbit_library_config": orbit_config.as_status_dict(),
        "visibility_config": visibility_config.as_status_dict(),
        "orbit_library": orbit_library.as_status_dict(),
        "visibility": visibility_library.as_status_dict(),
        "timing_seconds": timing_seconds,
        "reproduction_notes": {
            "method_reference": "Lee et al. 2020 APC / RGT common-ground-track constellation pattern",
            "components_reproduced_this_phase": {
                "public_case_parsing": True,
                "bounded_rgt_apc_candidate_states": True,
                "access_profile_visibility_sampling": True,
                "opportunity_window_grouping": True,
            },
            "components_deferred": {
                "gap_aware_satellite_selection": "phase 2",
                "constructive_observation_scheduling": "phase 3",
                "slew_battery_repair": "phase 4",
            },
            "empty_output_reason": "Phase 1 intentionally emits no selected satellites or actions.",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build RGT/APC-style candidate and visibility artifacts and emit an empty revisit solution."
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
        case = load_case(case_dir)

        orbit_config = OrbitLibraryConfig.from_mapping(config_payload, case)
        visibility_config = VisibilityConfig.from_mapping(config_payload)

        orbit_start = time.perf_counter()
        orbit_library = generate_orbit_library(case, orbit_config)
        orbit_end = time.perf_counter()

        visibility_start = time.perf_counter()
        visibility_library = build_visibility_library(
            case,
            orbit_library.candidates,
            visibility_config,
        )
        visibility_end = time.perf_counter()

        solution_path = write_empty_solution(solution_dir)
        total_end = time.perf_counter()
        timing_seconds = {
            "orbit_library": orbit_end - orbit_start,
            "visibility": visibility_end - visibility_start,
            "total": total_end - total_start,
        }
        status = _build_status(
            case_dir=case_dir,
            config_dir=config_dir,
            solution_path=solution_path,
            case=case,
            orbit_config=orbit_config,
            visibility_config=visibility_config,
            orbit_library=orbit_library,
            visibility_library=visibility_library,
            timing_seconds=timing_seconds,
        )
        write_json(solution_dir / "status.json", status)
        write_json(
            solution_dir / "debug" / "orbit_candidates.json",
            [candidate.as_dict() for candidate in orbit_library.candidates],
        )
        write_json(
            solution_dir / "debug" / "visibility_windows.json",
            [window.as_dict() for window in visibility_library.windows],
        )
    except Exception as exc:
        traceback_text = traceback.format_exc()
        solution_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            solution_dir / "status.json",
            {
                "status": "failed",
                "error": str(exc),
                "traceback": traceback_text,
            },
        )
        print(traceback_text, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

