"""Main entrypoint for the MCLP+TEG relay solver."""

from __future__ import annotations

import argparse
import json
import os
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .case_io import load_case
from .link_cache import build_link_cache
from .mclp import greedy_select, mclp_milp_eligibility, milp_select
from .orbit_library import generate_candidates
from .propagation import propagate_satellite
from .scheduler import run_scheduler
from .solution_io import write_debug_summary, write_reproduction_summary, write_solution, write_status
from .time_grid import build_time_grid


DEFAULT_CONFIG: dict[str, Any] = {
    "profile": "smoke",
    "profile_version": "1",
    "profile_envelope": "contract_smoke",
    "profile_description": "Lightweight verifier-compatible settings for local contract checks.",
    "budget_policy": "informational",
    "mclp_mode": "auto",
    "scheduler_mode": "route_aware",
    "parallel_mode": "auto",
    "max_parallel_workers": 8,
    "time_budget_s": 300,
    "orbit_grid": {
        "altitude_step_m": None,
        "inclination_step_deg": None,
        "num_raan_planes": 3,
        "num_phase_slots": 2,
    },
    "mclp_milp_config": {
        "max_candidates_for_milp": 20,
        "max_added_for_milp": 5,
        "time_limit_seconds": 30.0,
    },
    "milp_config": {
        "max_total_variables": 500,
        "max_samples": 50,
        "milp_time_limit_per_sample": 5.0,
    },
}


def _load_config(config_dir: Path) -> dict[str, Any]:
    """Load optional solver config from config_dir/config.yaml or config.json."""
    yaml_path = config_dir / "config.yaml"
    if yaml_path.exists():
        payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    json_path = config_dir / "config.json"
    if json_path.exists():
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    return {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a recursive merge of override onto base."""
    merged = deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _resolve_config(
    *,
    config_dir: Path | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve experiment-owned config plus built-in smoke fallback."""
    config_override = _load_config(config_dir) if config_dir else {}
    resolved = _deep_merge(DEFAULT_CONFIG, config_override)
    profile_name = str(resolved.get("profile", "custom"))

    metadata = {
        "profile": profile_name,
        "profile_version": resolved.get("profile_version", "unknown"),
        "profile_description": resolved.get("profile_description", ""),
        "profile_envelope": resolved.get("profile_envelope", ""),
        "profile_source": None,
        "config_dir": str(config_dir.resolve()) if config_dir else None,
        "config_override_keys": sorted(config_override.keys()),
    }
    return resolved, metadata


def _candidate_library_summary(
    *,
    candidates: list[Any] | tuple[Any, ...],
    orbit_grid: dict[str, Any],
    profile_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Summarize the generated candidate library for status/debug artifacts."""
    altitudes = sorted({round(float(c.altitude_m), 6) for c in candidates})
    inclinations = sorted({round(float(c.inclination_deg), 6) for c in candidates})
    raans = sorted({round(float(c.raan_deg), 6) for c in candidates})
    phases = sorted({round(float(c.mean_anomaly_deg), 6) for c in candidates})
    return {
        "profile": profile_metadata["profile"],
        "profile_envelope": profile_metadata["profile_envelope"],
        "candidate_count": len(candidates),
        "orbit_grid": orbit_grid,
        "altitude_shell_count": len(altitudes),
        "inclination_band_count": len(inclinations),
        "raan_plane_count": len(raans),
        "phase_slot_count": len(phases),
        "altitude_min_m": altitudes[0] if altitudes else None,
        "altitude_max_m": altitudes[-1] if altitudes else None,
        "inclination_min_deg": inclinations[0] if inclinations else None,
        "inclination_max_deg": inclinations[-1] if inclinations else None,
    }


def _propagate_with_timings(
    satellites: list[tuple[str, tuple[float, ...]]],
    epoch: Any,
    sample_times: tuple[Any, ...],
    use_parallel: bool,
    worker_count: int | None = None,
) -> tuple[dict[str, Any], list[float], bool, str | None]:
    """Propagate satellites and return (positions, per-satellite ms, fallback_happened)."""
    if not satellites:
        return {}, [], False, None

    fallback_reason: str | None = None
    if use_parallel:
        try:
            from .parallel import ParallelExecutionError, propagate_satellites_parallel

            positions, timings = propagate_satellites_parallel(
                satellites, epoch, sample_times, max_workers=worker_count
            )
            return positions, timings, False, None
        except ParallelExecutionError as exc:
            fallback_reason = str(exc)

    # Sequential fallback (also the primary path when parallel is disabled)
    positions: dict[str, Any] = {}
    timings: list[float] = []
    for sid, state in satellites:
        t0 = time.monotonic()
        positions[sid] = propagate_satellite(state, epoch, sample_times)
        timings.append((time.monotonic() - t0) * 1000.0)
    return positions, timings, use_parallel, fallback_reason if use_parallel else None


def _build_link_cache_with_mode(
    case: Any,
    backbone_positions: dict[str, Any],
    candidate_positions: dict[str, Any],
    use_parallel: bool,
    worker_count: int | None = None,
    *,
    include_candidate_candidate_isl: bool = True,
    cache_stage: str = "full",
) -> tuple[tuple[Any, ...], dict[str, object], bool, str | None]:
    """Build link cache and return (records, summary, fallback_happened)."""
    fallback_reason: str | None = None
    if use_parallel:
        try:
            from .parallel import ParallelExecutionError, build_link_cache_parallel

            records, summary = build_link_cache_parallel(
                case,
                backbone_positions,
                candidate_positions,
                max_workers=worker_count,
                include_candidate_candidate_isl=include_candidate_candidate_isl,
                cache_stage=cache_stage,
            )
            return records, summary, False, None
        except ParallelExecutionError as exc:
            fallback_reason = str(exc)

    records, summary = build_link_cache(
        case,
        backbone_positions,
        candidate_positions,
        include_candidate_candidate_isl=include_candidate_candidate_isl,
        cache_stage=cache_stage,
    )
    return records, summary, use_parallel, fallback_reason if use_parallel else None


def _skipped_link_cache_summary(
    *,
    cache_stage: str,
    reason: str,
    num_samples: int,
    backbone_count: int,
    candidate_count: int,
) -> dict[str, object]:
    return {
        "cache_stage": cache_stage,
        "cache_exact": False,
        "include_candidate_candidate_isl": False,
        "skipped": True,
        "skip_reason": reason,
        "num_samples": num_samples,
        "backbone_satellite_count": backbone_count,
        "candidate_satellite_count": candidate_count,
        "ground_link_records": 0,
        "isl_link_records": 0,
        "total_records": 0,
        "candidate_candidate_pairs_skipped": 0,
        "candidate_pair_sample_checks_avoided": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="MCLP+TEG relay solver")
    parser.add_argument("--case-dir", required=True, help="Path to benchmark case directory")
    parser.add_argument("--config-dir", default="", help="Optional config directory")
    parser.add_argument("--solution-dir", default="solution", help="Output directory for solution artifacts")
    args = parser.parse_args()

    config_dir = Path(args.config_dir) if args.config_dir else None
    config, profile_metadata = _resolve_config(
        config_dir=config_dir,
    )
    mclp_mode = config.get("mclp_mode", "auto")  # "auto", "greedy", "milp", or "none"
    scheduler_mode = config.get("scheduler_mode", "auto")  # "auto", "greedy", or "milp"
    milp_config = config.get("milp_config", {})
    mclp_milp_config = config.get("mclp_milp_config", {})
    parallel_mode = config.get("parallel_mode", "auto")  # "auto", "parallel", or "sequential"
    time_budget_s = config.get("time_budget_s", 300)
    budget_policy = config.get("budget_policy", "informational")
    orbit_grid = config.get("orbit_grid", {})
    max_parallel_workers = config.get("max_parallel_workers")
    mclp_milp_bounds = {
        "max_candidates_for_milp": mclp_milp_config.get("max_candidates_for_milp", 20),
        "max_added_for_milp": mclp_milp_config.get("max_added_for_milp", 5),
        "time_limit_seconds": mclp_milp_config.get("time_limit_seconds", 30.0),
    }

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

    # Generate candidate orbit library (configurable grid)
    # Skip generation entirely when no candidates will be selected
    if mclp_mode == "none":
        candidates = []
        t3 = time.monotonic()
    else:
        og = orbit_grid
        alt_step = og.get("altitude_step_m")
        inc_step = og.get("inclination_step_deg")
        num_raan = og.get("num_raan_planes", 3)
        num_phase = og.get("num_phase_slots", 2)
        candidates = generate_candidates(
            case.manifest.constraints,
            altitude_step_m=alt_step,
            inclination_step_deg=inc_step,
            num_raan_planes=num_raan,
            num_phase_slots=num_phase,
        )
        t3 = time.monotonic()
    candidate_summary = _candidate_library_summary(
        candidates=candidates,
        orbit_grid=orbit_grid,
        profile_metadata=profile_metadata,
    )

    # Decide whether to use parallel execution
    n_satellites = len(case.network.backbone_satellites) + len(candidates)
    auto_parallel = n_satellites > 1 or len(sample_times) > 1000
    use_parallel = parallel_mode == "parallel" or (parallel_mode == "auto" and auto_parallel)
    worker_cap = int(max_parallel_workers) if max_parallel_workers else (os.cpu_count() or 1)
    worker_count = min(os.cpu_count() or 1, n_satellites, worker_cap) if use_parallel else 1

    # Propagate backbone satellites
    backbone_tasks = [
        (sat.satellite_id, sat.state_eci_m_mps)
        for sat in case.network.backbone_satellites
    ]
    backbone_positions, backbone_timings_ms, bb_fallback, bb_fallback_reason = _propagate_with_timings(
        backbone_tasks, case.manifest.epoch, sample_times, use_parallel, worker_count
    )
    t4 = time.monotonic()

    # Propagate candidate satellites
    candidate_tasks = [
        (cand.satellite_id, cand.state_eci_m_mps)
        for cand in candidates
    ]
    candidate_positions, candidate_timings_ms, cand_fallback, cand_fallback_reason = _propagate_with_timings(
        candidate_tasks, case.manifest.epoch, sample_times, use_parallel, worker_count
    )
    t5 = time.monotonic()

    # Build lightweight selection-stage link cache for MCLP. This intentionally
    # avoids candidate-candidate ISL checks; the scheduler gets an exact cache
    # after MCLP selects the active added satellites.
    if candidates and mclp_mode != "none":
        selection_link_records, selection_link_summary, selection_lc_fallback, selection_lc_fallback_reason = (
            _build_link_cache_with_mode(
                case,
                backbone_positions,
                candidate_positions,
                use_parallel,
                worker_count,
                include_candidate_candidate_isl=False,
                cache_stage="selection",
            )
        )
    else:
        selection_link_records = ()
        selection_link_summary = _skipped_link_cache_summary(
            cache_stage="selection",
            reason="mclp_disabled_or_no_candidates",
            num_samples=len(sample_times),
            backbone_count=len(backbone_positions),
            candidate_count=len(candidate_positions),
        )
        selection_lc_fallback = False
        selection_lc_fallback_reason = None
    t6 = time.monotonic()

    # MCLP candidate selection
    selected: list[Any] = []
    mclp_summary: dict[str, Any] = {
        "policy": "none",
        "selected_count": 0,
        "candidate_count": len(candidates),
        "candidate_library": candidate_summary,
        "mclp_milp_bounds": mclp_milp_bounds,
        "mclp_milp_eligible": False,
        "mclp_milp_attempted": False,
        "mclp_milp_fallback_reason": "mclp_mode_none" if mclp_mode == "none" else None,
    }

    if candidates and mclp_mode != "none":
        if mclp_mode in ("auto", "milp"):
            mclp_milp_eligible, mclp_milp_ineligible_reason = mclp_milp_eligibility(
                candidates,
                case,
                max_candidates_for_milp=mclp_milp_bounds["max_candidates_for_milp"],
                max_added_for_milp=mclp_milp_bounds["max_added_for_milp"],
            )
        else:
            mclp_milp_eligible = False
            mclp_milp_ineligible_reason = "mclp_mode_greedy"
        if mclp_mode == "milp":
            milp_result = milp_select(
                candidates,
                case,
                sample_times,
                selection_link_records,
                max_candidates_for_milp=mclp_milp_bounds["max_candidates_for_milp"],
                max_added_for_milp=mclp_milp_bounds["max_added_for_milp"],
                time_limit_seconds=mclp_milp_bounds["time_limit_seconds"],
            )
            if milp_result is not None:
                selected, mclp_summary = milp_result
            else:
                selected, mclp_summary = greedy_select(candidates, case, sample_times, selection_link_records)
                mclp_summary["policy"] = "greedy (milp fallback)"
                mclp_summary["mclp_milp_fallback_reason"] = (
                    mclp_milp_ineligible_reason or "mclp_milp_solver_failed_or_not_optimal"
                )
        elif mclp_mode == "greedy":
            selected, mclp_summary = greedy_select(candidates, case, sample_times, selection_link_records)
            mclp_summary["mclp_milp_fallback_reason"] = "mclp_mode_greedy"
        else:  # auto
            milp_result = milp_select(
                candidates,
                case,
                sample_times,
                selection_link_records,
                max_candidates_for_milp=mclp_milp_bounds["max_candidates_for_milp"],
                max_added_for_milp=mclp_milp_bounds["max_added_for_milp"],
                time_limit_seconds=mclp_milp_bounds["time_limit_seconds"],
            )
            if milp_result is not None:
                selected, mclp_summary = milp_result
            else:
                selected, mclp_summary = greedy_select(candidates, case, sample_times, selection_link_records)
                mclp_summary["mclp_milp_fallback_reason"] = (
                    mclp_milp_ineligible_reason or "mclp_milp_solver_failed_or_not_optimal"
                )
        mclp_summary["candidate_count"] = len(candidates)
        mclp_summary["candidate_library"] = candidate_summary
        mclp_summary["selection_cache_mode"] = "ground_all_plus_backbone_touching_isl"
        mclp_summary["selection_cache_exact"] = False
        mclp_summary["mclp_milp_bounds"] = mclp_milp_bounds
        mclp_summary["mclp_milp_eligible"] = mclp_milp_eligible
        mclp_summary["mclp_milp_attempted"] = (
            mclp_mode in ("auto", "milp") and mclp_milp_eligible
        )
        if mclp_summary.get("policy") == "milp":
            mclp_summary["mclp_milp_fallback_reason"] = None
    t7 = time.monotonic()

    # Build exact scheduler-stage cache for backbone plus selected candidates.
    selected_candidate_positions = {
        c.satellite_id: candidate_positions[c.satellite_id]
        for c in selected
        if c.satellite_id in candidate_positions
    }
    scheduler_link_records, scheduler_link_summary, scheduler_lc_fallback, scheduler_lc_fallback_reason = (
        _build_link_cache_with_mode(
            case,
            backbone_positions,
            selected_candidate_positions,
            use_parallel,
            worker_count,
            include_candidate_candidate_isl=True,
            cache_stage="scheduler",
        )
    )
    t8 = time.monotonic()

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
        case, sample_times, scheduler_link_records, selected_ids,
        scheduler_mode=scheduler_mode,
        milp_config=milp_config,
    )
    t9 = time.monotonic()

    total_time = t9 - t0
    any_fallback = (
        bb_fallback or cand_fallback or selection_lc_fallback or scheduler_lc_fallback
    )
    link_cache_strategy = {
        "strategy": "two_stage",
        "selection_cache_mode": selection_link_summary.get("cache_stage", "selection"),
        "selection_cache_exact": selection_link_summary.get("cache_exact", False),
        "selection_total_records": selection_link_summary.get("total_records", 0),
        "scheduler_cache_mode": scheduler_link_summary.get("cache_stage", "scheduler"),
        "scheduler_cache_exact": scheduler_link_summary.get("cache_exact", False),
        "scheduler_total_records": scheduler_link_summary.get("total_records", 0),
        "candidate_pair_sample_checks_avoided": selection_link_summary.get(
            "candidate_pair_sample_checks_avoided", 0
        ),
        "scheduler_exact_after_selection": scheduler_link_summary.get("cache_exact", False),
    }

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
        "profile": profile_metadata["profile"],
        "profile_version": profile_metadata["profile_version"],
        "profile_description": profile_metadata["profile_description"],
        "profile_envelope": profile_metadata["profile_envelope"],
        "profile_source": profile_metadata["profile_source"],
        "config_dir": profile_metadata["config_dir"],
        "config_override_keys": profile_metadata["config_override_keys"],
        "horizon_start": case.manifest.horizon_start.isoformat().replace("+00:00", "Z"),
        "horizon_end": case.manifest.horizon_end.isoformat().replace("+00:00", "Z"),
        "routing_step_s": case.manifest.routing_step_s,
        "num_samples": len(sample_times),
        "num_backbone_satellites": len(case.network.backbone_satellites),
        "num_ground_endpoints": len(case.network.ground_endpoints),
        "num_demanded_windows": len(case.demands.demanded_windows),
        "num_candidate_satellites": len(candidates),
        "candidate_library": candidate_summary,
        "compute_budget_s": time_budget_s,
        "budget_policy": budget_policy,
        "compute_envelope": {
            "profile": profile_metadata["profile"],
            "profile_version": profile_metadata["profile_version"],
            "profile_envelope": profile_metadata["profile_envelope"],
            "budget_policy": budget_policy,
            "time_budget_s": time_budget_s,
            "mclp_mode": mclp_mode,
            "scheduler_mode": scheduler_mode,
            "parallel_mode": parallel_mode,
            "max_parallel_workers": max_parallel_workers,
            "orbit_grid": orbit_grid,
            "mclp_milp_config": mclp_milp_config,
            "scheduler_milp_config": milp_config,
        },
        "budget_warning": (
            f"Total time {total_time:.1f}s exceeds 90% of budget {time_budget_s}s"
            if total_time > time_budget_s * 0.9 else None
        ),
        "execution_model": {
            "parallel_mode": parallel_mode,
            "parallel_enabled": use_parallel,
            "max_parallel_workers": max_parallel_workers,
            "worker_count": worker_count,
            "propagation_mode": "parallel" if (use_parallel and not bb_fallback) else "sequential",
            "selection_link_cache_mode": "parallel" if (use_parallel and not selection_lc_fallback) else "sequential",
            "scheduler_link_cache_mode": "parallel" if (use_parallel and not scheduler_lc_fallback) else "sequential",
            "parallel_fallback": any_fallback,
            "parallel_fallback_reasons": {
                "backbone_propagation": bb_fallback_reason,
                "candidate_propagation": cand_fallback_reason,
                "selection_link_cache": selection_lc_fallback_reason,
                "scheduler_link_cache": scheduler_lc_fallback_reason,
            },
        },
        "mclp_policy": mclp_summary.get("policy", "none"),
        "mclp_milp_bounds": mclp_summary.get("mclp_milp_bounds", mclp_milp_bounds),
        "mclp_milp_eligible": mclp_summary.get("mclp_milp_eligible", False),
        "mclp_milp_attempted": mclp_summary.get("mclp_milp_attempted", False),
        "mclp_milp_fallback_reason": mclp_summary.get("mclp_milp_fallback_reason"),
        "mclp_baseline_score": mclp_summary.get("baseline_score", 0.0),
        "mclp_selected_score": mclp_summary.get("selected_score", 0.0),
        "mclp_selected_count": mclp_summary.get("selected_count", 0),
        "mclp_selected_candidate_ids": mclp_summary.get("selected_candidate_ids", []),
        "mclp_scoring_engine": mclp_summary.get("scoring_engine"),
        "mclp_demand_sample_count": mclp_summary.get("demand_sample_count"),
        "mclp_candidate_evaluations": mclp_summary.get("candidate_evaluations"),
        "mclp_candidate_evaluations_per_selected": mclp_summary.get("candidate_evaluations_per_selected"),
        "mclp_index_build_time_s": mclp_summary.get("index_build_time_s"),
        "mclp_baseline_eval_time_s": mclp_summary.get("baseline_eval_time_s"),
        "mclp_selection_loop_time_s": mclp_summary.get("selection_loop_time_s"),
        "mclp_base_cc_total_time_s": mclp_summary.get("base_cc_total_time_s"),
        "mclp_marginal_eval_total_time_s": mclp_summary.get("marginal_eval_total_time_s"),
        "link_cache_summary": scheduler_link_summary,
        "selection_link_cache_summary": selection_link_summary,
        "scheduler_link_cache_summary": scheduler_link_summary,
        "link_cache_strategy": link_cache_strategy,
        "timings_s": {
            "load_case": round(t1 - t0, 3),
            "build_time_grid": round(t2 - t1, 3),
            "generate_candidates": round(t3 - t2, 3),
            "propagate_backbone": round(t4 - t3, 3),
            "propagate_backbone_total": round(t4 - t3, 3),
            "propagate_backbone_per_satellite_ms": [round(v, 3) for v in backbone_timings_ms],
            "propagate_candidates": round(t5 - t4, 3),
            "propagate_candidates_total": round(t5 - t4, 3),
            "propagate_candidates_per_satellite_ms": [round(v, 3) for v in candidate_timings_ms],
            "build_selection_link_cache": round(t6 - t5, 3),
            "mclp_selection": round(t7 - t6, 3),
            "build_scheduler_link_cache": round(t8 - t7, 3),
            "build_link_cache": round((t6 - t5) + (t8 - t7), 3),
            "build_link_cache_total": round((t6 - t5) + (t8 - t7), 3),
            "scheduler": round(t9 - t8, 3),
            "total": round(total_time, 3),
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
        "scheduler_route_aware_demands_considered": sched_summary.get("route_aware_demands_considered"),
        "scheduler_route_aware_demands_routed": sched_summary.get("route_aware_demands_routed"),
        "scheduler_route_aware_demands_unrouted": sched_summary.get("route_aware_demands_unrouted"),
        "scheduler_route_aware_capacity_rejects": sched_summary.get("route_aware_capacity_rejects"),
    }
    write_status(solution_dir, status)

    # Write debug summaries
    write_debug_summary(
        solution_dir,
        "orbit_candidates",
        {
            "summary": candidate_summary,
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
    write_debug_summary(solution_dir, "link_cache_summary", link_cache_strategy)
    write_debug_summary(solution_dir, "selection_link_cache_summary", selection_link_summary)
    write_debug_summary(solution_dir, "scheduler_link_cache_summary", scheduler_link_summary)
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
    write_reproduction_summary(
        solution_dir,
        mclp_mode=mclp_mode,
        scheduler_mode=sched_summary.get("scheduler_mode", "greedy"),
        parallel_mode=parallel_mode,
        worker_count=worker_count,
        time_budget_s=time_budget_s,
    )

    print(f"MCLP+TEG scheduling complete for {case.manifest.case_id}")
    print(f"  Policy: {mclp_summary.get('policy', 'none')}")
    print(f"  Candidates: {len(candidates)}")
    print(f"  Selected: {len(selected)}")
    print(f"  Baseline score: {mclp_summary.get('baseline_score', 0.0)}")
    print(f"  Selected score: {mclp_summary.get('selected_score', 0.0)}")
    if mclp_summary.get("candidate_evaluations") is not None:
        print(f"  MCLP candidate evaluations: {mclp_summary.get('candidate_evaluations')}")
        print(f"  MCLP marginal eval time: {mclp_summary.get('marginal_eval_total_time_s')}s")
    print(f"  Scheduler mode: {sched_summary.get('scheduler_mode', 'greedy')}")
    print(f"  Selection cache records: {selection_link_summary.get('total_records', 0)}")
    print(f"  Scheduler cache records: {scheduler_link_summary.get('total_records', 0)}")
    print(f"  Candidate-pair sample checks avoided: {selection_link_summary.get('candidate_pair_sample_checks_avoided', 0)}")
    if sched_summary.get("milp_attempted"):
        print(f"  MILP attempted: {sched_summary['milp_attempted']}")
        if sched_summary.get("milp_fallback_reason"):
            print(f"  MILP fallback reason: {sched_summary['milp_fallback_reason']}")
    print(f"  Parallel mode: {parallel_mode}")
    print(f"  Parallel enabled: {use_parallel}")
    if any_fallback:
        print("  Parallel fallback: yes (sequential used)")
    print(f"  Actions: {len(actions)} ({sched_summary.get('num_ground_actions', 0)} ground, {sched_summary.get('num_isl_actions', 0)} ISL)")
    print(f"  Local violations: {len(sched_summary.get('local_violations', []))}")
    print(f"  Solution written to: {solution_dir.resolve()}")


if __name__ == "__main__":
    main()
