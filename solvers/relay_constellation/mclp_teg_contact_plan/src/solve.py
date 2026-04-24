"""Main entrypoint for the MCLP+TEG relay solver (Phase 1 scaffold)."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from .case_io import load_case
from .link_cache import build_link_cache
from .orbit_library import generate_candidates
from .propagation import propagate_satellite
from .solution_io import write_debug_summary, write_solution, write_status
from .time_grid import build_time_grid


def main() -> None:
    parser = argparse.ArgumentParser(description="MCLP+TEG relay solver (Phase 1)")
    parser.add_argument("--case-dir", required=True, help="Path to benchmark case directory")
    parser.add_argument("--config-dir", default="", help="Optional config directory")
    parser.add_argument("--solution-dir", default="solution", help="Output directory for solution artifacts")
    args = parser.parse_args()

    t0 = time.monotonic()
    case = load_case(Path(args.case_dir))
    t1 = time.monotonic()

    # Build time grid
    sample_times = build_time_grid(
        case.manifest.horizon_start,
        case.manifest.horizon_end,
        case.manifest.routing_step_s,
    )
    t2 = time.monotonic()

    # Generate candidate orbit library (conservative grid for Phase 1)
    candidates = generate_candidates(
        case.manifest.constraints,
        altitude_step_m=case.manifest.constraints.max_altitude_m - case.manifest.constraints.min_altitude_m,
        inclination_step_deg=(
            (case.manifest.constraints.max_inclination_deg or 180.0)
            - (case.manifest.constraints.min_inclination_deg or 0.0)
        ),
        num_raan_planes=1,
        num_phase_slots=1,
    )
    t3 = time.monotonic()

    # Propagate backbone satellites
    backbone_positions: dict[str, dict[int, Any]] = {}
    for sat in case.network.backbone_satellites:
        backbone_positions[sat.satellite_id] = propagate_satellite(
            sat.state_eci_m_mps,
            case.manifest.epoch,
            sample_times,
        )
    t4 = time.monotonic()

    # Propagate candidate satellites
    candidate_positions: dict[str, dict[int, Any]] = {}
    for cand in candidates:
        candidate_positions[cand.satellite_id] = propagate_satellite(
            cand.state_eci_m_mps,
            case.manifest.epoch,
            sample_times,
        )
    t5 = time.monotonic()

    # Build link-feasibility cache
    link_records, link_summary = build_link_cache(case, backbone_positions, candidate_positions)
    t6 = time.monotonic()

    # Write empty solution (Phase 1)
    solution_dir = Path(args.solution_dir)
    write_solution(
        solution_dir,
        added_satellites=[],
        actions=[],
    )

    # Write status
    status = {
        "benchmark": case.manifest.benchmark,
        "case_id": case.manifest.case_id,
        "case_path": str(Path(args.case_dir).resolve()),
        "horizon_start": case.manifest.horizon_start.isoformat().replace("+00:00", "Z"),
        "horizon_end": case.manifest.horizon_end.isoformat().replace("+00:00", "Z"),
        "routing_step_s": case.manifest.routing_step_s,
        "num_samples": len(sample_times),
        "num_backbone_satellites": len(case.network.backbone_satellites),
        "num_ground_endpoints": len(case.network.ground_endpoints),
        "num_demanded_windows": len(case.demands.demanded_windows),
        "num_candidate_satellites": len(candidates),
        "link_cache_summary": link_summary,
        "timings_s": {
            "load_case": round(t1 - t0, 3),
            "build_time_grid": round(t2 - t1, 3),
            "generate_candidates": round(t3 - t2, 3),
            "propagate_backbone": round(t4 - t3, 3),
            "propagate_candidates": round(t5 - t4, 3),
            "build_link_cache": round(t6 - t5, 3),
            "total": round(t6 - t0, 3),
        },
    }
    write_status(solution_dir, status)

    # Write debug summaries
    write_debug_summary(
        solution_dir,
        "orbit_candidates",
        {
            "count": len(candidates),
            "candidates": [
                {
                    "satellite_id": c.satellite_id,
                    "altitude_m": c.altitude_m,
                    "inclination_deg": c.inclination_deg,
                    "raan_deg": c.raan_deg,
                    "mean_anomaly_deg": c.mean_anomaly_deg,
                    "eccentricity": c.eccentricity,
                }
                for c in candidates
            ],
        },
    )
    write_debug_summary(solution_dir, "link_cache_summary", link_summary)

    print(f"Phase 1 scaffold complete for {case.manifest.case_id}")
    print(f"  Candidates: {len(candidates)}")
    print(f"  Samples: {len(sample_times)}")
    print(f"  Links: {link_summary.get('total_records', 0)}")
    print(f"  Solution written to: {solution_dir.resolve()}")


if __name__ == "__main__":
    main()
