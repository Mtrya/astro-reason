"""Main entrypoint for the MCLP+TEG relay solver."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from .case_io import load_case
from .link_cache import build_link_cache
from .mclp import greedy_select, milp_select
from .orbit_library import generate_candidates
from .propagation import propagate_satellite
from .scheduler import run_scheduler
from .solution_io import write_debug_summary, write_solution, write_status
from .time_grid import build_time_grid


def _load_config(config_dir: Path) -> dict[str, Any]:
    """Load optional solver config from config_dir/config.json."""
    config_path = config_dir / "config.json"
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="MCLP+TEG relay solver")
    parser.add_argument("--case-dir", required=True, help="Path to benchmark case directory")
    parser.add_argument("--config-dir", default="", help="Optional config directory")
    parser.add_argument("--solution-dir", default="solution", help="Output directory for solution artifacts")
    args = parser.parse_args()

    config = _load_config(Path(args.config_dir)) if args.config_dir else {}
    mclp_mode = config.get("mclp_mode", "auto")  # "auto", "greedy", or "milp"
    scheduler_mode = config.get("scheduler_mode", "auto")  # "auto", "greedy", or "milp"
    milp_config = config.get("milp_config", {})

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

    # Generate candidate orbit library (conservative grid for speed)
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

    # MCLP candidate selection
    selected: list[Any] = []
    mclp_summary: dict[str, Any] = {"policy": "none", "selected_count": 0}

    if candidates:
        if mclp_mode == "milp":
            milp_result = milp_select(candidates, case, sample_times, link_records)
            if milp_result is not None:
                selected, mclp_summary = milp_result
            else:
                selected, mclp_summary = greedy_select(candidates, case, sample_times, link_records)
                mclp_summary["policy"] = "greedy (milp fallback)"
        elif mclp_mode == "greedy":
            selected, mclp_summary = greedy_select(candidates, case, sample_times, link_records)
        else:  # auto
            milp_result = milp_select(candidates, case, sample_times, link_records)
            if milp_result is not None:
                selected, mclp_summary = milp_result
            else:
                selected, mclp_summary = greedy_select(candidates, case, sample_times, link_records)
    t7 = time.monotonic()

    # Build added_satellites output
    added_satellites: list[dict[str, Any]] = []
    for cand in selected:
        x, y, z, vx, vy, vz = cand.state_eci_m_mps
        added_satellites.append(
            {
                "satellite_id": cand.satellite_id,
                "x_m": x,
                "y_m": y,
                "z_m": z,
                "vx_m_s": vx,
                "vy_m_s": vy,
                "vz_m_s": vz,
            }
        )

    # Contact scheduling (MILP or greedy)
    selected_ids = {c.satellite_id for c in selected}
    actions, sched_summary = run_scheduler(
        case, sample_times, link_records, selected_ids,
        scheduler_mode=scheduler_mode,
        milp_config=milp_config,
    )
    t8 = time.monotonic()

    # Write solution
    solution_dir = Path(args.solution_dir)
    write_solution(
        solution_dir,
        added_satellites=added_satellites,
        actions=actions,
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
        "mclp_policy": mclp_summary.get("policy", "none"),
        "mclp_baseline_score": mclp_summary.get("baseline_score", 0.0),
        "mclp_selected_score": mclp_summary.get("selected_score", 0.0),
        "mclp_selected_count": mclp_summary.get("selected_count", 0),
        "mclp_selected_candidate_ids": mclp_summary.get("selected_candidate_ids", []),
        "link_cache_summary": link_summary,
        "timings_s": {
            "load_case": round(t1 - t0, 3),
            "build_time_grid": round(t2 - t1, 3),
            "generate_candidates": round(t3 - t2, 3),
            "propagate_backbone": round(t4 - t3, 3),
            "propagate_candidates": round(t5 - t4, 3),
            "build_link_cache": round(t6 - t5, 3),
            "mclp_selection": round(t7 - t6, 3),
            "scheduler": round(t8 - t7, 3),
            "total": round(t8 - t0, 3),
        },
        "scheduler_mode": sched_summary.get("scheduler_mode", "greedy"),
        "scheduler_milp_attempted": sched_summary.get("milp_attempted", False),
        "scheduler_milp_fallback_reason": sched_summary.get("milp_fallback_reason", None),
        "scheduler_milp_model_variables": sched_summary.get("milp_model_variables", None),
        "scheduler_milp_model_constraints": sched_summary.get("milp_model_constraints", None),
        "scheduler_milp_total_solve_time_s": sched_summary.get("milp_total_solve_time_s", None),
        "scheduler_num_actions": sched_summary.get("num_actions", 0),
        "scheduler_num_ground_actions": sched_summary.get("num_ground_actions", 0),
        "scheduler_num_isl_actions": sched_summary.get("num_isl_actions", 0),
        "scheduler_local_violations": sched_summary.get("local_violations", []),
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
    write_debug_summary(solution_dir, "mclp_reward_summary", mclp_summary)
    write_debug_summary(solution_dir, "teg_summary", sched_summary)
    if sched_summary.get("milp_attempted"):
        write_debug_summary(solution_dir, "milp_summary", {
            "milp_attempted": sched_summary.get("milp_attempted"),
            "milp_fallback_reason": sched_summary.get("milp_fallback_reason"),
            "milp_model_variables": sched_summary.get("milp_model_variables"),
            "milp_model_constraints": sched_summary.get("milp_model_constraints"),
            "milp_total_solve_time_s": sched_summary.get("milp_total_solve_time_s"),
            "milp_per_sample_solve_times_s": sched_summary.get("milp_per_sample_solve_times_s"),
        })
    write_debug_summary(
        solution_dir,
        "selected_orbits",
        {
            "count": len(selected),
            "selected": [
                {
                    "satellite_id": c.satellite_id,
                    "altitude_m": c.altitude_m,
                    "inclination_deg": c.inclination_deg,
                    "raan_deg": c.raan_deg,
                    "mean_anomaly_deg": c.mean_anomaly_deg,
                    "eccentricity": c.eccentricity,
                }
                for c in selected
            ],
        },
    )

    print(f"MCLP+TEG scheduling complete for {case.manifest.case_id}")
    print(f"  Policy: {mclp_summary.get('policy', 'none')}")
    print(f"  Candidates: {len(candidates)}")
    print(f"  Selected: {len(selected)}")
    print(f"  Baseline score: {mclp_summary.get('baseline_score', 0.0)}")
    print(f"  Selected score: {mclp_summary.get('selected_score', 0.0)}")
    print(f"  Scheduler mode: {sched_summary.get('scheduler_mode', 'greedy')}")
    if sched_summary.get("milp_attempted"):
        print(f"  MILP attempted: {sched_summary['milp_attempted']}")
        if sched_summary.get("milp_fallback_reason"):
            print(f"  MILP fallback reason: {sched_summary['milp_fallback_reason']}")
    print(f"  Actions: {len(actions)} ({sched_summary.get('num_ground_actions', 0)} ground, {sched_summary.get('num_isl_actions', 0)} ISL)")
    print(f"  Local violations: {len(sched_summary.get('local_violations', []))}")
    print(f"  Solution written to: {solution_dir.resolve()}")


if __name__ == "__main__":
    main()
