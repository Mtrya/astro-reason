"""Solver entrypoint for RGT/APC candidate, visibility, and gap selection."""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

from .case_io import load_case, load_solver_config
from .orbit_library import OrbitLibraryConfig, generate_orbit_library
from .selection import SelectionConfig, select_satellites_greedy
from .solution_io import write_json, write_solution
from .visibility import VisibilityConfig, build_visibility_library


def _build_status(
    *,
    case_dir: Path,
    config_dir: Path | None,
    solution_path: Path,
    case,
    orbit_config: OrbitLibraryConfig,
    visibility_config: VisibilityConfig,
    selection_config: SelectionConfig,
    orbit_library,
    visibility_library,
    selection_result,
    timing_seconds: dict[str, float],
) -> dict:
    return {
        "status": "phase_2_gap_selection_solution_generated",
        "phase": 2,
        "case_dir": str(case_dir),
        "config_dir": str(config_dir) if config_dir is not None else None,
        "solution": str(solution_path),
        "case_id": case.case_id,
        "target_count": len(case.targets),
        "max_num_satellites": case.max_num_satellites,
        "horizon_duration_sec": case.horizon_duration_sec,
        "satellite_output_count": len(selection_result.selected_candidate_ids),
        "action_output_count": 0,
        "orbit_library_config": orbit_config.as_status_dict(),
        "visibility_config": visibility_config.as_status_dict(),
        "selection_config": selection_config.as_status_dict(),
        "orbit_library": orbit_library.as_status_dict(),
        "visibility": visibility_library.as_status_dict(),
        "selection": selection_result.as_status_dict(),
        "timing_seconds": timing_seconds,
        "reproduction_notes": {
            "method_reference": "Lee et al. 2020 APC / RGT common-ground-track constellation pattern",
            "components_reproduced_this_phase": {
                "public_case_parsing": True,
                "bounded_rgt_apc_candidate_states": True,
                "access_profile_visibility_sampling": True,
                "opportunity_window_grouping": True,
                "benchmark_style_gap_scoring": True,
                "greedy_gap_aware_satellite_selection": True,
            },
            "components_deferred": {
                "constructive_observation_scheduling": "phase 3",
                "slew_battery_repair": "phase 4",
            },
            "action_output_reason": "Phase 2 selects satellites from visibility opportunities; action scheduling is deferred.",
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
        selection_config = SelectionConfig.from_mapping(config_payload)

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

        selection_start = time.perf_counter()
        selection_result = select_satellites_greedy(
            case=case,
            candidates=orbit_library.candidates,
            windows=visibility_library.windows,
            config=selection_config,
        )
        selection_end = time.perf_counter()

        solution_path = write_solution(
            solution_dir,
            satellites=[
                candidate.as_solution_satellite()
                for candidate in selection_result.selected_candidates
            ],
        )
        total_end = time.perf_counter()
        timing_seconds = {
            "orbit_library": orbit_end - orbit_start,
            "visibility": visibility_end - visibility_start,
            "selection": selection_end - selection_start,
            "total": total_end - total_start,
        }
        status = _build_status(
            case_dir=case_dir,
            config_dir=config_dir,
            solution_path=solution_path,
            case=case,
            orbit_config=orbit_config,
            visibility_config=visibility_config,
            selection_config=selection_config,
            orbit_library=orbit_library,
            visibility_library=visibility_library,
            selection_result=selection_result,
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
        write_json(
            solution_dir / "debug" / "selection_rounds.json",
            [round_info.as_dict() for round_info in selection_result.rounds],
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
