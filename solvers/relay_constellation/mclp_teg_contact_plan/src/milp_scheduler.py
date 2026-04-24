"""Bounded per-sample MILP contact scheduler with deterministic greedy fallback."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .case_io import Case, DemandWindow
from .link_cache import LinkRecord
from .scheduler import (
    _build_ground_adjacency_at_sample,
    _build_demands_by_sample,
    _local_validate,
    _normalize_link_key,
    build_per_sample_links,
    compact_intervals,
    score_ground_link,
    score_isl,
)

if TYPE_CHECKING:
    from typing import Iterable


def milp_scheduler_available() -> bool:
    """Return True if PuLP and CBC are available."""
    try:
        import pulp

        solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=1)
        return solver.available()
    except Exception:
        return False


def milp_select_links(
    sample_index: int,
    feasible_links: list[LinkRecord],
    active_demands: list[DemandWindow],
    max_links_per_satellite: int,
    max_links_per_endpoint: int,
    time_limit_seconds: float = 5.0,
) -> set[tuple[str, str, str]] | None:
    """Select a subset of feasible links at one sample via MILP.

    Returns a set of normalized link keys, or None if the solver fails.
    """
    try:
        import pulp
    except Exception:
        return None

    if not feasible_links:
        return set()

    # Build ground adjacency for ISL scoring
    _, sat_to_eps = _build_ground_adjacency_at_sample(feasible_links, sample_index)

    # Deduplicate by normalized key; keep first record for each key
    unique_links: dict[tuple[str, str, str], LinkRecord] = {}
    for rec in feasible_links:
        key = _normalize_link_key(rec.link_type, rec.node_a, rec.node_b)
        if key not in unique_links:
            unique_links[key] = rec

    # Score each unique link
    scored: dict[tuple[str, str, str], float] = {}
    for key, rec in unique_links.items():
        if rec.link_type == "ground":
            scored[key] = score_ground_link(rec, active_demands)
        else:
            scored[key] = score_isl(rec, active_demands, sat_to_eps)

    # Create MILP
    prob = pulp.LpProblem(f"contact_sched_sample_{sample_index}", pulp.LpMaximize)

    # Binary variable per unique link
    x: dict[tuple[str, str, str], pulp.LpVariable] = {}
    for key in unique_links:
        x[key] = pulp.LpVariable(f"x_{key[0]}_{key[1]}_{key[2]}", cat="Binary")

    # Objective: maximize total utility
    prob += pulp.lpSum(scored[key] * x[key] for key in x)

    # Per-satellite degree cap
    sat_incident: dict[str, list[pulp.LpVariable]] = defaultdict(list)
    for key, rec in unique_links.items():
        if rec.link_type == "ground":
            # endpoint = node_a, satellite = node_b
            sat_incident[rec.node_b].append(x[key])
        else:
            sat_incident[rec.node_a].append(x[key])
            sat_incident[rec.node_b].append(x[key])

    for sat_id, vars_list in sat_incident.items():
        prob += pulp.lpSum(vars_list) <= max_links_per_satellite

    # Per-endpoint degree cap (ground links only)
    ep_incident: dict[str, list[pulp.LpVariable]] = defaultdict(list)
    for key, rec in unique_links.items():
        if rec.link_type == "ground":
            ep_incident[rec.node_a].append(x[key])

    for ep_id, vars_list in ep_incident.items():
        prob += pulp.lpSum(vars_list) <= max_links_per_endpoint

    # Solve with CBC
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit_seconds)
    result_status = prob.solve(solver)

    if pulp.LpStatus[result_status] not in ("Optimal", "Not Solved"):
        return None

    selected: set[tuple[str, str, str]] = set()
    for key, var in x.items():
        if var.value() is not None and var.value() > 0.5:
            selected.add(key)

    return selected


def run_milp_scheduler(
    case: Case,
    sample_times: tuple[datetime, ...],
    link_records: Iterable[LinkRecord],
    selected_satellite_ids: set[str] | None = None,
    milp_time_limit_per_sample: float = 5.0,
    max_total_variables: int = 500,
    max_samples: int = 50,
) -> tuple[list[dict], dict] | None:
    """Run bounded per-sample MILP scheduler; return None if problem exceeds limits or solver fails.

    Returns actions plus a summary dict, or (None, fallback_reason_dict) on failure.
    """
    try:
        import pulp
    except Exception:
        return None

    # Filter links to only involve selected candidates (plus backbone)
    backbone_ids = {s.satellite_id for s in case.network.backbone_satellites}
    allowed_sats = backbone_ids | (selected_satellite_ids or set())
    filtered_records = [
        rec for rec in link_records
        if (rec.link_type == "ground" and rec.node_b in allowed_sats)
        or (rec.link_type == "isl" and rec.node_a in allowed_sats and rec.node_b in allowed_sats)
    ]
    per_sample = build_per_sample_links(filtered_records)
    demands_by_sample = _build_demands_by_sample(case, sample_times)

    sample_indices = sorted(per_sample.keys())

    if len(sample_indices) > max_samples:
        return None

    # Count total unique variables across all samples
    total_vars = 0
    for sidx in sample_indices:
        unique = set()
        for rec in per_sample[sidx]:
            unique.add(_normalize_link_key(rec.link_type, rec.node_a, rec.node_b))
        total_vars += len(unique)
        if total_vars > max_total_variables:
            return None

    max_sat = case.manifest.constraints.max_links_per_satellite
    max_ep = case.manifest.constraints.max_links_per_endpoint

    selected_by_sample: dict[int, set[tuple[str, str, str]]] = {}
    total_selected = 0
    total_utility = 0.0
    per_sample_solve_times: list[float] = []
    total_constraints = 0

    for sidx in sample_indices:
        active_demands = demands_by_sample.get(sidx, [])
        feasible = per_sample[sidx]

        t0 = time.monotonic()
        selected = milp_select_links(
            sidx, feasible, active_demands, max_sat, max_ep, milp_time_limit_per_sample
        )
        t1 = time.monotonic()
        per_sample_solve_times.append(round(t1 - t0, 6))

        if selected is None:
            return None

        selected_by_sample[sidx] = selected
        total_selected += len(selected)

        # Recompute utility for summary
        _, sat_to_eps = _build_ground_adjacency_at_sample(feasible, sidx)
        for key in selected:
            link_type, node_a, node_b = key
            for rec in feasible:
                if rec.link_type == link_type:
                    nkey = _normalize_link_key(rec.link_type, rec.node_a, rec.node_b)
                    if nkey == key:
                        if link_type == "ground":
                            total_utility += score_ground_link(rec, active_demands)
                        else:
                            total_utility += score_isl(rec, active_demands, sat_to_eps)
                        break

        # Count constraints for this sample (approximate: one per satellite + one per endpoint)
        unique_links = {
            _normalize_link_key(rec.link_type, rec.node_a, rec.node_b)
            for rec in feasible
        }
        sats_in_sample: set[str] = set()
        eps_in_sample: set[str] = set()
        for rec in feasible:
            if rec.link_type == "ground":
                sats_in_sample.add(rec.node_b)
                eps_in_sample.add(rec.node_a)
            else:
                sats_in_sample.add(rec.node_a)
                sats_in_sample.add(rec.node_b)
        total_constraints += len(sats_in_sample) + len(eps_in_sample)

    actions = compact_intervals(
        selected_by_sample, sample_times, case.manifest.routing_step_s
    )

    local_violations = _local_validate(actions, case, sample_times)

    num_ground = sum(1 for a in actions if a["action_type"] == "ground_link")
    num_isl = sum(1 for a in actions if a["action_type"] == "inter_satellite_link")

    summary = {
        "scheduler_mode": "milp",
        "milp_attempted": True,
        "milp_fallback_reason": None,
        "milp_model_variables": total_vars,
        "milp_model_constraints": total_constraints,
        "milp_total_solve_time_s": round(sum(per_sample_solve_times), 6),
        "milp_per_sample_solve_times_s": per_sample_solve_times,
        "num_samples_with_links": len(selected_by_sample),
        "total_selected_links": total_selected,
        "total_utility": round(total_utility, 6),
        "num_actions": len(actions),
        "num_ground_actions": num_ground,
        "num_isl_actions": num_isl,
        "local_violations": local_violations,
    }

    return actions, summary
