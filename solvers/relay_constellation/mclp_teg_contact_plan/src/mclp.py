"""MCLP candidate selection using demand-window service-potential rewards."""

from __future__ import annotations

import time
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
        start_idx = max(0, sample_index(horizon_start, demand.start_time, routing_step_s))
        end_idx = min(
            max(0, len(sample_times_list) - 1),
            sample_index(horizon_start, demand.end_time, routing_step_s),
        )
        for idx in range(start_idx, end_idx):
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


def _compute_marginal_gain_fast(
    cid: str,
    base_set: set[str],
    demand_samples: dict[str, list[int]],
    demands_by_id: dict[str, DemandWindow],
    ground_map: dict[int, dict[str, set[str]]],
    isl_map: dict[int, dict[str, set[str]]],
    base_cc_cache: dict[int, dict[str, int]],
    sample_to_demands: dict[int, list[str]],
) -> set[DemandSample]:
    """Return demand-samples newly covered by adding candidate cid to base_set.

    Avoids recomputing connected components from scratch by using the precomputed
    base_cc_cache and incrementally checking connectivity through the candidate.
    """
    new_covered: set[DemandSample] = set()
    trial_set = base_set | {cid}

    for sidx, d_ids in sample_to_demands.items():
        gm = ground_map.get(sidx, {})
        if not gm:
            continue

        im = isl_map.get(sidx, {})
        base_cc = base_cc_cache.get(sidx, {})
        cand_peers = im.get(cid, set()) & trial_set if im else set()

        for d_id in d_ids:
            demand = demands_by_id[d_id]

            # Was it already covered by base?
            src_base = gm.get(demand.source_endpoint_id, set()) & base_set
            dst_base = gm.get(demand.destination_endpoint_id, set()) & base_set
            base_covered = False
            if src_base and dst_base:
                for s in src_base:
                    for d in dst_base:
                        if s == d or (s in base_cc and d in base_cc and base_cc[s] == base_cc[d]):
                            base_covered = True
                            break
                    if base_covered:
                        break

            if base_covered:
                continue

            # Check trial coverage
            src_trial = gm.get(demand.source_endpoint_id, set()) & trial_set
            dst_trial = gm.get(demand.destination_endpoint_id, set()) & trial_set
            if not src_trial or not dst_trial:
                continue

            # Direct relay (same satellite sees both endpoints)
            if src_trial & dst_trial:
                new_covered.add(DemandSample(d_id, sidx))
                continue

            # Need ISL connectivity
            if not im:
                continue

            connected = False
            for s in src_trial:
                for d in dst_trial:
                    if s == d:
                        connected = True
                        break
                    # Both in base and same CC
                    if s in base_cc and d in base_cc and base_cc[s] == base_cc[d]:
                        connected = True
                        break
                    # Candidate bridges them directly
                    if s == cid and d in cand_peers:
                        connected = True
                        break
                    if d == cid and s in cand_peers:
                        connected = True
                        break
                    if s in cand_peers and d in cand_peers:
                        connected = True
                        break
                    # One in base CC, other is candidate or peer, and they're in same merged component
                    if s in base_cc and (d == cid or d in cand_peers):
                        for p in cand_peers:
                            if p in base_cc and base_cc[p] == base_cc[s]:
                                connected = True
                                break
                        if connected:
                            break
                    if d in base_cc and (s == cid or s in cand_peers):
                        for p in cand_peers:
                            if p in base_cc and base_cc[p] == base_cc[d]:
                                connected = True
                                break
                        if connected:
                            break
                if connected:
                    break

            if connected:
                new_covered.add(DemandSample(d_id, sidx))

    return new_covered


def _compute_marginal_gain_indexed(
    cid: str,
    base_set: set[str],
    current_covered: set[int],
    ground_map: dict[int, dict[str, set[str]]],
    isl_map: dict[int, dict[str, set[str]]],
    base_cc_cache: dict[int, dict[str, int]],
    sample_to_demand_entries: dict[int, list[tuple[int, DemandWindow]]],
) -> set[int]:
    """Return newly covered demand-sample indices after adding candidate cid.

    This is the same reward test as ``_compute_marginal_gain_fast``, but it
    avoids rebuilding ``DemandSample`` objects and avoids re-checking whether
    the current base constellation already covers each sample. The greedy loop
    maintains ``current_covered`` exactly, so candidate evaluation only needs to
    test uncovered demand-samples against the trial active set.
    """
    new_covered: set[int] = set()
    trial_set = base_set | {cid}

    for sidx, entries in sample_to_demand_entries.items():
        gm = ground_map.get(sidx, {})
        if not gm:
            continue

        im = isl_map.get(sidx, {})
        base_cc = base_cc_cache.get(sidx, {})
        cand_peers = im.get(cid, set()) & trial_set if im else set()

        for ds_idx, demand in entries:
            if ds_idx in current_covered:
                continue

            src_trial = gm.get(demand.source_endpoint_id, set()) & trial_set
            dst_trial = gm.get(demand.destination_endpoint_id, set()) & trial_set
            if not src_trial or not dst_trial:
                continue

            if src_trial & dst_trial:
                new_covered.add(ds_idx)
                continue

            if not im:
                continue

            connected = False
            for src_sat in src_trial:
                for dst_sat in dst_trial:
                    if src_sat == dst_sat:
                        connected = True
                        break
                    if (
                        src_sat in base_cc
                        and dst_sat in base_cc
                        and base_cc[src_sat] == base_cc[dst_sat]
                    ):
                        connected = True
                        break
                    if src_sat == cid and dst_sat in cand_peers:
                        connected = True
                        break
                    if dst_sat == cid and src_sat in cand_peers:
                        connected = True
                        break
                    if src_sat in cand_peers and dst_sat in cand_peers:
                        connected = True
                        break
                    if src_sat in base_cc and (dst_sat == cid or dst_sat in cand_peers):
                        for peer in cand_peers:
                            if peer in base_cc and base_cc[peer] == base_cc[src_sat]:
                                connected = True
                                break
                        if connected:
                            break
                    if dst_sat in base_cc and (src_sat == cid or src_sat in cand_peers):
                        for peer in cand_peers:
                            if peer in base_cc and base_cc[peer] == base_cc[dst_sat]:
                                connected = True
                                break
                        if connected:
                            break
                if connected:
                    break

            if connected:
                new_covered.add(ds_idx)

    return new_covered


def _weighted_score(
    covered: set[DemandSample],
    demands_by_id: dict[str, DemandWindow],
) -> float:
    """Sum of weights for covered demand-samples."""
    score = 0.0
    for ds in covered:
        score += demands_by_id[ds.demand_id].weight
    return score


def mclp_milp_eligibility(
    candidates: tuple[CandidateSatellite, ...],
    case: Case,
    *,
    max_candidates_for_milp: int = 20,
    max_added_for_milp: int = 5,
) -> tuple[bool, str | None]:
    """Return whether the exact MCLP MILP path is eligible under current bounds."""
    if len(candidates) > max_candidates_for_milp:
        return False, "candidate_count_exceeds_mclp_milp_bound"
    if case.manifest.constraints.max_added_satellites > max_added_for_milp:
        return False, "max_added_satellites_exceeds_mclp_milp_bound"

    import pulp  # noqa: F401

    return True, None


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
    t_start = time.monotonic()
    demand_samples = build_demand_sample_indices(case, sample_times)
    ground_map, isl_map = build_ground_and_isl_maps(link_records)
    demands_by_id = {d.demand_id: d for d in case.demands.demanded_windows}
    index_built_at = time.monotonic()

    backbone_ids = {s.satellite_id for s in case.network.backbone_satellites}
    candidate_ids = [c.satellite_id for c in candidates]
    candidate_by_id = {c.satellite_id: c for c in candidates}
    max_added = case.manifest.constraints.max_added_satellites

    # Baseline: backbone only
    baseline_covered = _compute_covered_samples(
        backbone_ids, demand_samples, demands_by_id, ground_map, isl_map
    )
    baseline_score = _weighted_score(baseline_covered, demands_by_id)
    baseline_eval_at = time.monotonic()

    selected: list[CandidateSatellite] = []
    selected_ids: set[str] = set()
    demand_sample_to_index: dict[DemandSample, int] = {}
    demand_sample_weights: list[float] = []
    sample_to_demand_entries: dict[int, list[tuple[int, DemandWindow]]] = defaultdict(list)
    for demand_id in sorted(demand_samples):
        demand = demands_by_id[demand_id]
        for sidx in demand_samples[demand_id]:
            ds = DemandSample(demand_id, sidx)
            ds_idx = len(demand_sample_weights)
            demand_sample_to_index[ds] = ds_idx
            demand_sample_weights.append(demand.weight)
            sample_to_demand_entries[sidx].append((ds_idx, demand))

    current_covered = {
        demand_sample_to_index[ds]
        for ds in baseline_covered
        if ds in demand_sample_to_index
    }
    current_score = baseline_score

    iteration_log: list[dict[str, object]] = []
    total_candidate_evaluations = 0
    total_marginal_eval_time_s = 0.0
    total_base_cc_time_s = 0.0
    selection_loop_started_at = time.monotonic()

    while len(selected) < max_added:
        iteration_started_at = time.monotonic()
        best_cand_id: str | None = None
        best_marginal = -1.0
        best_new_covered: set[int] = set()

        base_set = backbone_ids | selected_ids

        # Precompute base CC for each sample once per greedy iteration
        base_cc_started_at = time.monotonic()
        base_cc_cache: dict[int, dict[str, int]] = {}
        for sidx in sample_to_demand_entries:
            im = isl_map.get(sidx, {})
            if im:
                base_cc_cache[sidx] = _connected_components(base_set, im)
        base_cc_time_s = time.monotonic() - base_cc_started_at
        total_base_cc_time_s += base_cc_time_s

        iteration_candidate_evaluations = 0
        marginal_eval_started_at = time.monotonic()
        for cid in candidate_ids:
            if cid in selected_ids:
                continue
            new_covered = _compute_marginal_gain_indexed(
                cid,
                base_set,
                current_covered,
                ground_map,
                isl_map,
                base_cc_cache,
                sample_to_demand_entries,
            )
            marginal = sum(demand_sample_weights[idx] for idx in new_covered)
            iteration_candidate_evaluations += 1

            if marginal > best_marginal or (
                marginal == best_marginal and (best_cand_id is None or cid < best_cand_id)
            ):
                best_marginal = marginal
                best_cand_id = cid
                best_new_covered = new_covered
        marginal_eval_time_s = time.monotonic() - marginal_eval_started_at
        total_marginal_eval_time_s += marginal_eval_time_s
        total_candidate_evaluations += iteration_candidate_evaluations

        if best_cand_id is None or best_marginal <= 0.0:
            iteration_log.append(
                {
                    "iteration": len(selected) + 1,
                    "selected_candidate_id": None,
                    "marginal_score": round(max(best_marginal, 0.0), 6),
                    "cumulative_score": round(current_score, 6),
                    "candidate_evaluations": iteration_candidate_evaluations,
                    "skipped_selected_candidates": len(selected_ids),
                    "newly_covered_samples": 0,
                    "base_cc_time_s": round(base_cc_time_s, 6),
                    "marginal_eval_time_s": round(marginal_eval_time_s, 6),
                    "iteration_time_s": round(time.monotonic() - iteration_started_at, 6),
                    "stop_reason": "no_positive_marginal_gain",
                }
            )
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
                "candidate_evaluations": iteration_candidate_evaluations,
                "skipped_selected_candidates": len(selected_ids) - 1,
                "newly_covered_samples": len(best_new_covered),
                "base_cc_time_s": round(base_cc_time_s, 6),
                "marginal_eval_time_s": round(marginal_eval_time_s, 6),
                "iteration_time_s": round(time.monotonic() - iteration_started_at, 6),
                "stop_reason": None,
            }
        )

    selection_done_at = time.monotonic()
    summary = {
        "policy": "greedy",
        "scoring_engine": "indexed_exact",
        "max_added_satellites": max_added,
        "baseline_score": round(baseline_score, 6),
        "selected_score": round(current_score, 6),
        "selected_count": len(selected),
        "selected_candidate_ids": [c.satellite_id for c in selected],
        "iteration_log": iteration_log,
        "demand_sample_count": len(demand_sample_weights),
        "baseline_covered_sample_count": len(baseline_covered),
        "selected_covered_sample_count": len(current_covered),
        "candidate_evaluations": total_candidate_evaluations,
        "candidate_evaluations_per_selected": (
            round(total_candidate_evaluations / len(selected), 3) if selected else 0.0
        ),
        "skipped_selected_candidate_evaluations": sum(range(len(selected))),
        "index_build_time_s": round(index_built_at - t_start, 6),
        "baseline_eval_time_s": round(baseline_eval_at - index_built_at, 6),
        "selection_loop_time_s": round(selection_done_at - selection_loop_started_at, 6),
        "base_cc_total_time_s": round(total_base_cc_time_s, 6),
        "marginal_eval_total_time_s": round(total_marginal_eval_time_s, 6),
        "total_time_s": round(selection_done_at - t_start, 6),
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
    eligible, _reason = mclp_milp_eligibility(
        candidates,
        case,
        max_candidates_for_milp=max_candidates_for_milp,
        max_added_for_milp=max_added_for_milp,
    )
    if not eligible:
        return None

    import pulp

    # Materialize iterables to allow multiple iterations
    sample_times_tuple = tuple(sample_times)
    link_records_tuple = tuple(link_records)

    all_ds, cover_sets, backbone_covered = _build_simplified_cover_matrix(
        candidates, case, sample_times_tuple, link_records_tuple
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

    if pulp.LpStatus[result_status] != "Optimal":
        # Timed out, infeasible, or unsolved; fall back to greedy.
        return None

    selected = [
        candidate_by_id[cid]
        for cid, var in x.items()
        if var.value() is not None and var.value() > 0.5
    ]

    # Compute score for selected set using the same service-potential function
    demand_samples = build_demand_sample_indices(case, sample_times_tuple)
    ground_map, isl_map = build_ground_and_isl_maps(link_records_tuple)
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
