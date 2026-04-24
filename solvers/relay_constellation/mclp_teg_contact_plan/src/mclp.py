"""MCLP candidate selection using demand-window service-potential rewards."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

from .case_io import Case, DemandWindow
from .link_cache import LinkRecord
from .orbit_library import CandidateSatellite
from .time_grid import sample_index

if TYPE_CHECKING:
    from typing import Iterable


@dataclass(frozen=True)
class DemandSample:
    """A single (demand, sample_index) pair."""

    demand_id: str
    sample_index: int


def build_demand_sample_indices(
    case: Case,
    sample_times: Iterable[datetime],
) -> dict[str, list[int]]:
    """Map each demand_id to the list of sample indices falling inside its window."""
    sample_times_list = list(sample_times)
    if not sample_times_list:
        return {}

    horizon_start = sample_times_list[0]
    routing_step_s = case.manifest.routing_step_s

    result: dict[str, list[int]] = {}
    for demand in case.demands.demanded_windows:
        indices: list[int] = []
        start_idx = sample_index(horizon_start, demand.start_time, routing_step_s)
        end_idx = sample_index(horizon_start, demand.end_time, routing_step_s)
        for idx in range(start_idx, end_idx + 1):
            if 0 <= idx < len(sample_times_list):
                indices.append(idx)
        result[demand.demand_id] = indices
    return result


def build_ground_and_isl_maps(
    link_records: Iterable[LinkRecord],
) -> tuple[
    dict[int, dict[str, set[str]]],
    dict[int, dict[str, set[str]]],
]:
    """Build per-sample ground-link and ISL adjacency maps.

    Returns
    -------
    ground_map : sample_index -> endpoint_id -> set(satellite_id)
    isl_map    : sample_index -> satellite_id -> set(satellite_id)
    """
    ground_map: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    isl_map: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    for rec in link_records:
        if rec.link_type == "ground":
            # node_a = endpoint, node_b = satellite
            ground_map[rec.sample_index][rec.node_a].add(rec.node_b)
            ground_map[rec.sample_index][rec.node_b].add(rec.node_a)
        elif rec.link_type == "isl":
            isl_map[rec.sample_index][rec.node_a].add(rec.node_b)
            isl_map[rec.sample_index][rec.node_b].add(rec.node_a)

    # Convert defaultdicts to plain dicts for cleanliness
    ground_map_plain: dict[int, dict[str, set[str]]] = {}
    for sidx, ep_map in ground_map.items():
        ground_map_plain[sidx] = {ep: set(sats) for ep, sats in ep_map.items()}

    isl_map_plain: dict[int, dict[str, set[str]]] = {}
    for sidx, sat_map in isl_map.items():
        isl_map_plain[sidx] = {sat: set(peers) for sat, peers in sat_map.items()}

    return ground_map_plain, isl_map_plain


def _connected_components(
    nodes: set[str],
    adjacency: dict[str, set[str]],
) -> dict[str, int]:
    """Return mapping node -> component id for the subgraph induced by nodes."""
    node_to_cc: dict[str, int] = {}
    cc_id = 0
    unvisited = set(nodes)
    for start in nodes:
        if start not in unvisited:
            continue
        stack = [start]
        unvisited.remove(start)
        while stack:
            cur = stack.pop()
            node_to_cc[cur] = cc_id
            for neighbor in adjacency.get(cur, set()):
                if neighbor in unvisited and neighbor in nodes:
                    unvisited.remove(neighbor)
                    stack.append(neighbor)
        cc_id += 1
    return node_to_cc


def _compute_covered_samples(
    active_satellites: set[str],
    demand_samples: dict[str, list[int]],
    demands_by_id: dict[str, DemandWindow],
    ground_map: dict[int, dict[str, set[str]]],
    isl_map: dict[int, dict[str, set[str]]],
) -> set[DemandSample]:
    """Return the set of DemandSamples that are potentially servable by active_satellites."""
    covered: set[DemandSample] = set()

    # Precompute which samples we actually need to look at
    sample_indices_needed: set[int] = set()
    for d_id, sidxs in demand_samples.items():
        sample_indices_needed.update(sidxs)

    for sidx in sample_indices_needed:
        gm = ground_map.get(sidx, {})
        im = isl_map.get(sidx, {})

        if not gm:
            continue

        # Build connected components of ISL graph restricted to active satellites
        cc_map = _connected_components(active_satellites, im)

        for d_id, sidxs in demand_samples.items():
            if sidx not in sidxs:
                continue
            demand = demands_by_id[d_id]
            src_sats = gm.get(demand.source_endpoint_id, set()) & active_satellites
            dst_sats = gm.get(demand.destination_endpoint_id, set()) & active_satellites

            if not src_sats or not dst_sats:
                continue

            # Same-satellite relay
            if src_sats & dst_sats:
                covered.add(DemandSample(d_id, sidx))
                continue

            # Check if any src sat and dst sat are in the same CC
            src_ccs = {cc_map[s] for s in src_sats if s in cc_map}
            dst_ccs = {cc_map[s] for s in dst_sats if s in cc_map}
            if src_ccs & dst_ccs:
                covered.add(DemandSample(d_id, sidx))

    return covered


def _weighted_score(
    covered: set[DemandSample],
    demands_by_id: dict[str, DemandWindow],
) -> float:
    """Sum of weights for covered demand-samples."""
    score = 0.0
    for ds in covered:
        score += demands_by_id[ds.demand_id].weight
    return score


def greedy_select(
    candidates: tuple[CandidateSatellite, ...],
    case: Case,
    sample_times: Iterable[datetime],
    link_records: Iterable[LinkRecord],
) -> tuple[list[CandidateSatellite], dict[str, object]]:
    """Greedy MCLP selection maximizing marginal service-potential reward.

    Returns
    -------
    selected : list of chosen CandidateSatellite objects
    summary  : dict with selection diagnostics
    """
    demand_samples = build_demand_sample_indices(case, sample_times)
    ground_map, isl_map = build_ground_and_isl_maps(link_records)
    demands_by_id = {d.demand_id: d for d in case.demands.demanded_windows}

    backbone_ids = {s.satellite_id for s in case.network.backbone_satellites}
    candidate_ids = [c.satellite_id for c in candidates]
    candidate_by_id = {c.satellite_id: c for c in candidates}
    max_added = case.manifest.constraints.max_added_satellites

    # Baseline: backbone only
    baseline_covered = _compute_covered_samples(
        backbone_ids, demand_samples, demands_by_id, ground_map, isl_map
    )
    baseline_score = _weighted_score(baseline_covered, demands_by_id)

    selected: list[CandidateSatellite] = []
    selected_ids: set[str] = set()
    current_covered = set(baseline_covered)
    current_score = baseline_score

    # Precompute marginal contributions
    iteration_log: list[dict[str, object]] = []

    while len(selected) < max_added:
        best_cand_id: str | None = None
        best_marginal = -1.0
        best_new_covered: set[DemandSample] = set()

        for cid in candidate_ids:
            if cid in selected_ids:
                continue
            trial_set = backbone_ids | selected_ids | {cid}
            trial_covered = _compute_covered_samples(
                trial_set, demand_samples, demands_by_id, ground_map, isl_map
            )
            new_covered = trial_covered - current_covered
            marginal = _weighted_score(new_covered, demands_by_id)

            if marginal > best_marginal or (
                marginal == best_marginal and (best_cand_id is None or cid < best_cand_id)
            ):
                best_marginal = marginal
                best_cand_id = cid
                best_new_covered = new_covered

        if best_cand_id is None or best_marginal <= 0.0:
            break

        selected_ids.add(best_cand_id)
        selected.append(candidate_by_id[best_cand_id])
        current_covered |= best_new_covered
        current_score += best_marginal

        iteration_log.append(
            {
                "iteration": len(selected),
                "selected_candidate_id": best_cand_id,
                "marginal_score": round(best_marginal, 6),
                "cumulative_score": round(current_score, 6),
            }
        )

    summary = {
        "policy": "greedy",
        "max_added_satellites": max_added,
        "baseline_score": round(baseline_score, 6),
        "selected_score": round(current_score, 6),
        "selected_count": len(selected),
        "selected_candidate_ids": [c.satellite_id for c in selected],
        "iteration_log": iteration_log,
    }

    return selected, summary


def _build_simplified_cover_matrix(
    candidates: tuple[CandidateSatellite, ...],
    case: Case,
    sample_times: Iterable[datetime],
    link_records: Iterable[LinkRecord],
) -> tuple[
    list[DemandSample],
    dict[DemandSample, set[str]],
    set[DemandSample],
]:
    """Build simplified coverage sets for small MILP.

    A candidate j "covers" demand-sample (d,t) if:
    - j sees both source and dest at t (direct relay), OR
    - j sees source at t and has ISL to a backbone that sees dest at t, OR
    - j sees dest at t and has ISL to a backbone that sees source at t.

    Returns
    -------
    all_demand_samples : flat list of DemandSample objects
    cover_sets         : DemandSample -> set of candidate_ids that can cover it
    backbone_covered   : set of DemandSamples covered by backbone alone
    """
    demand_samples = build_demand_sample_indices(case, sample_times)
    ground_map, isl_map = build_ground_and_isl_maps(link_records)
    demands_by_id = {d.demand_id: d for d in case.demands.demanded_windows}
    backbone_ids = {s.satellite_id for s in case.network.backbone_satellites}
    candidate_by_id = {c.satellite_id: c for c in candidates}

    all_ds: list[DemandSample] = []
    cover_sets: dict[DemandSample, set[str]] = {}
    backbone_covered = _compute_covered_samples(
        backbone_ids, demand_samples, demands_by_id, ground_map, isl_map
    )

    for d_id, sidxs in demand_samples.items():
        for sidx in sidxs:
            ds = DemandSample(d_id, sidx)
            all_ds.append(ds)
            if ds in backbone_covered:
                continue

            demand = demands_by_id[d_id]
            gm = ground_map.get(sidx, {})
            im = isl_map.get(sidx, {})

            src_sats_backbone = gm.get(demand.source_endpoint_id, set()) & backbone_ids
            dst_sats_backbone = gm.get(demand.destination_endpoint_id, set()) & backbone_ids

            covering_cands: set[str] = set()
            for cid in candidate_by_id:
                # Direct: candidate sees both endpoints
                sees_src = cid in gm.get(demand.source_endpoint_id, set())
                sees_dst = cid in gm.get(demand.destination_endpoint_id, set())
                if sees_src and sees_dst:
                    covering_cands.add(cid)
                    continue

                # Candidate sees source + ISL to backbone that sees dest
                if sees_src:
                    cand_isl_peers = im.get(cid, set())
                    if cand_isl_peers & dst_sats_backbone:
                        covering_cands.add(cid)
                        continue

                # Candidate sees dest + ISL to backbone that sees source
                if sees_dst:
                    cand_isl_peers = im.get(cid, set())
                    if cand_isl_peers & src_sats_backbone:
                        covering_cands.add(cid)
                        continue

            if covering_cands:
                cover_sets[ds] = covering_cands

    return all_ds, cover_sets, backbone_covered


def milp_select(
    candidates: tuple[CandidateSatellite, ...],
    case: Case,
    sample_times: Iterable[datetime],
    link_records: Iterable[LinkRecord],
    max_candidates_for_milp: int = 20,
    max_added_for_milp: int = 5,
    time_limit_seconds: float = 30.0,
) -> tuple[list[CandidateSatellite], dict[str, object]] | None:
    """Optional small MILP MCLP using PuLP/CBC.

    Returns None if problem is too large or PuLP is unavailable.
    """
    try:
        import pulp
    except Exception:
        return None

    if len(candidates) > max_candidates_for_milp:
        return None
    if case.manifest.constraints.max_added_satellites > max_added_for_milp:
        return None

    all_ds, cover_sets, backbone_covered = _build_simplified_cover_matrix(
        candidates, case, sample_times, link_records
    )
    demands_by_id = {d.demand_id: d for d in case.demands.demanded_windows}
    candidate_by_id = {c.satellite_id: c for c in candidates}
    max_added = case.manifest.constraints.max_added_satellites

    # Create MILP
    prob = pulp.LpProblem("mclp_relay", pulp.LpMaximize)

    # Variables
    x: dict[str, pulp.LpVariable] = {}
    for c in candidates:
        x[c.satellite_id] = pulp.LpVariable(f"x_{c.satellite_id}", cat="Binary")

    y: dict[DemandSample, pulp.LpVariable] = {}
    for ds in all_ds:
        if ds not in backbone_covered and ds in cover_sets:
            y[ds] = pulp.LpVariable(f"y_{ds.demand_id}_{ds.sample_index}", cat="Binary")

    # Objective: maximize weighted covered demand-samples
    objective = pulp.lpSum(
        demands_by_id[ds.demand_id].weight * (1.0 if ds in backbone_covered else y.get(ds, 0.0))
        for ds in all_ds
    )
    prob += objective

    # Cardinality constraint
    prob += pulp.lpSum(x[cid] for cid in x) <= max_added

    # Coverage constraints
    for ds, cands in cover_sets.items():
        if ds in y:
            prob += y[ds] <= pulp.lpSum(x[cid] for cid in cands)

    # Solve with CBC
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit_seconds)
    result_status = prob.solve(solver)

    if pulp.LpStatus[result_status] not in ("Optimal", "Not Solved"):
        # Not solved to optimality or infeasible; fall back
        return None

    selected = [
        candidate_by_id[cid]
        for cid, var in x.items()
        if var.value() is not None and var.value() > 0.5
    ]

    # Compute score for selected set using the same service-potential function
    demand_samples = build_demand_sample_indices(case, sample_times)
    ground_map, isl_map = build_ground_and_isl_maps(link_records)
    backbone_ids = {s.satellite_id for s in case.network.backbone_satellites}
    selected_ids = {c.satellite_id for c in selected}
    covered = _compute_covered_samples(
        backbone_ids | selected_ids,
        demand_samples,
        demands_by_id,
        ground_map,
        isl_map,
    )
    score = _weighted_score(covered, demands_by_id)
    baseline_covered = _compute_covered_samples(
        backbone_ids, demand_samples, demands_by_id, ground_map, isl_map
    )
    baseline_score = _weighted_score(baseline_covered, demands_by_id)

    summary = {
        "policy": "milp",
        "milp_status": pulp.LpStatus[result_status],
        "max_added_satellites": max_added,
        "baseline_score": round(baseline_score, 6),
        "selected_score": round(score, 6),
        "selected_count": len(selected),
        "selected_candidate_ids": [c.satellite_id for c in selected],
    }

    return selected, summary
