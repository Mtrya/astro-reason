"""Deterministic time-window cluster pruning adapted from Kim et al. 2020."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from models import (
    CandidateObservation,
    Mission,
    PruningSummary,
    Satellite,
    StereoPair,
    Target,
    TriStereoSet,
)
from products import enumerate_products


def compute_cluster_gap_s(sat: Satellite) -> float:
    """Kim-style max-slew-time gap: (2*max_roll + 2*max_pitch) / slew_rate + settling_time.

    Since the benchmark uses a single max_off_nadir_deg for both axes,
    we approximate as (4 * max_off_nadir_deg) / max_slew_velocity + settling_time.
    """
    return (4.0 * sat.max_off_nadir_deg) / sat.max_slew_velocity_deg_per_s + sat.settling_time_s


def compute_lambda_lb(candidates: list[CandidateObservation], satellites: dict[str, Satellite]) -> int:
    """Lower-bound cluster capacity inspired by Kim's lambda_LB.

    lambda_LB = avg_window_length / (avg_obs_time + avg_stabilization_time)
    We approximate avg_window_length as average candidate duration,
    and avg_stabilization_time as mean satellite settling_time_s.
    """
    if not candidates or not satellites:
        return 1
    avg_obs_dur = sum((c.end - c.start).total_seconds() for c in candidates) / len(candidates)
    avg_settle = sum(s.settling_time_s for s in satellites.values()) / len(satellites)
    denom = avg_obs_dur + avg_settle
    if denom <= 0.0:
        return 1
    lb = int(avg_obs_dur / denom)
    return max(1, lb)


def cluster_candidates_by_gap(
    candidates: list[CandidateObservation], gap_s: float
) -> list[list[CandidateObservation]]:
    """Cluster candidates per satellite by temporal gap.

    Within each satellite, candidates are sorted by (start, target_id,
    access_interval_id, off_nadir_along_deg, off_nadir_across_deg).
    A new cluster starts when the gap between a candidate's start and the
    previous candidate's end exceeds gap_s.
    """
    by_sat: dict[str, list[CandidateObservation]] = {}
    for c in candidates:
        by_sat.setdefault(c.sat_id, []).append(c)

    clusters: list[list[CandidateObservation]] = []
    for sat_id in sorted(by_sat.keys()):
        sat_cands = sorted(
            by_sat[sat_id],
            key=lambda c: (c.start, c.target_id, c.access_interval_id, c.off_nadir_along_deg, c.off_nadir_across_deg),
        )
        current: list[CandidateObservation] = []
        prev_end: datetime | None = None
        for c in sat_cands:
            if prev_end is None:
                current = [c]
                prev_end = c.end
            else:
                gap = (c.start - prev_end).total_seconds()
                if gap <= gap_s:
                    current.append(c)
                    if c.end > prev_end:
                        prev_end = c.end
                else:
                    clusters.append(current)
                    current = [c]
                    prev_end = c.end
        if current:
            clusters.append(current)
    return clusters


@dataclass
class _CandidateScore:
    cand: CandidateObservation
    has_valid_product: bool
    scarcity: float
    max_q: float
    is_anchor: bool
    valid_pair_count: int
    valid_tri_count: int


def _score_candidates(
    cluster: list[CandidateObservation],
    pairs: list[StereoPair],
    tris: list[TriStereoSet],
    target_total_candidates: dict[str, int],
    near_nadir_anchor_max_off_nadir_deg: float,
) -> list[_CandidateScore]:
    """Precompute per-candidate metrics for ranking."""
    # Build lookup sets for fast membership tests
    cand_key = lambda c: (c.sat_id, c.target_id, c.access_interval_id, c.start, c.end, c.off_nadir_along_deg, c.off_nadir_across_deg)
    # Use id() for hashability since CandidateObservation is frozen dataclass

    pair_counts: dict[int, int] = {}
    tri_counts: dict[int, int] = {}
    max_q: dict[int, float] = {}

    for p in pairs:
        if p.valid:
            for c in (p.candidate_i, p.candidate_j):
                cid = id(c)
                pair_counts[cid] = pair_counts.get(cid, 0) + 1
                max_q[cid] = max(max_q.get(cid, 0.0), p.q_pair)

    for t in tris:
        if t.valid:
            for c in t.candidates:
                cid = id(c)
                tri_counts[cid] = tri_counts.get(cid, 0) + 1
                max_q[cid] = max(max_q.get(cid, 0.0), t.q_tri)

    cluster_mean_on = 0.0
    if cluster:
        cluster_mean_on = sum(c.combined_off_nadir_deg for c in cluster) / len(cluster)

    scores: list[_CandidateScore] = []
    for c in cluster:
        cid = id(c)
        vpc = pair_counts.get(cid, 0)
        vtc = tri_counts.get(cid, 0)
        has_product = vpc > 0 or vtc > 0
        scarcity = 1.0 / (1.0 + target_total_candidates.get(c.target_id, 0))
        q = max_q.get(cid, 0.0)
        is_anchor = c.combined_off_nadir_deg <= near_nadir_anchor_max_off_nadir_deg + 1e-9
        scores.append(_CandidateScore(c, has_product, scarcity, q, is_anchor, vpc, vtc))

    return scores


def _rank_key(score: _CandidateScore, cluster_mean_on: float) -> tuple:
    """Lexicographic rank tuple: lower is better."""
    c = score.cand
    return (
        -int(score.has_valid_product),          # product participants first
        -score.scarcity,                         # scarcer targets first
        -score.max_q,                            # higher quality first
        abs(c.combined_off_nadir_deg - cluster_mean_on),  # steering similarity
        c.target_id,                             # deterministic tie-break
        c.start.isoformat(),
        c.off_nadir_along_deg,
        c.off_nadir_across_deg,
    )


def prune_candidates(
    candidates: list[CandidateObservation],
    pairs: list[StereoPair],
    tris: list[TriStereoSet],
    satellites: dict[str, Satellite],
    targets: dict[str, Target],
    mission: Mission,
    config: dict[str, Any],
) -> tuple[list[CandidateObservation], list[StereoPair], list[TriStereoSet], PruningSummary]:
    """Apply Kim-style cluster pruning with benchmark-native adaptations.

    Returns the pruned candidate list, recomputed pairs/tris, and a summary.
    """
    pruning_cfg = config.get("pruning", {})
    if not pruning_cfg.get("enabled", False):
        summary = PruningSummary(
            enabled=False,
            cluster_gap_s=0.0,
            lambda_cap=0,
            pre_candidates=len(candidates),
            post_candidates=len(candidates),
            pre_pairs=len(pairs),
            post_pairs=len(pairs),
            pre_tris=len(tris),
            post_tris=len(tris),
        )
        return candidates, pairs, tris, summary

    # Resolve gap_s
    gap_cfg = pruning_cfg.get("cluster_gap_s", "auto")
    if gap_cfg == "auto" or gap_cfg is None:
        # Use the most restrictive (smallest) gap across satellites for conservatism
        gap_s = min(compute_cluster_gap_s(s) for s in satellites.values()) if satellites else 60.0
    else:
        gap_s = float(gap_cfg)

    # Resolve lambda_cap
    lambda_cfg = pruning_cfg.get("max_candidates_per_cluster", "auto")
    if lambda_cfg == "auto" or lambda_cfg is None:
        lambda_cap = compute_lambda_lb(candidates, satellites)
    else:
        lambda_cap = int(lambda_cfg)
    min_lambda = int(pruning_cfg.get("min_candidates_per_cluster", 2))
    lambda_cap = max(lambda_cap, min_lambda)

    # Global cap
    max_total = int(pruning_cfg.get("max_total_candidates", 10000))
    preserve_anchors = bool(pruning_cfg.get("preserve_anchors", True))
    preserve_products = bool(pruning_cfg.get("preserve_products", True))

    pre_candidates = len(candidates)
    pre_pairs = len(pairs)
    pre_tris = len(tris)

    # Target-level candidate counts for scarcity
    target_total_candidates: dict[str, int] = {}
    for c in candidates:
        target_total_candidates[c.target_id] = target_total_candidates.get(c.target_id, 0) + 1

    clusters = cluster_candidates_by_gap(candidates, gap_s)

    retained: list[CandidateObservation] = []
    preservation_forced = 0
    rejected_by_capacity = 0
    by_cluster_info: list[dict[str, Any]] = []
    by_target_info: dict[str, dict[str, Any]] = {}

    for cluster_idx, cluster in enumerate(clusters):
        cluster_mean_on = sum(c.combined_off_nadir_deg for c in cluster) / len(cluster) if cluster else 0.0
        scores = _score_candidates(
            cluster, pairs, tris, target_total_candidates,
            mission.validity_thresholds.near_nadir_anchor_max_off_nadir_deg,
        )
        scores_sorted = sorted(scores, key=lambda s: _rank_key(s, cluster_mean_on))

        # Track per-target counts within this cluster
        retained_in_cluster: list[CandidateObservation] = []
        cluster_retained_per_target: dict[str, int] = {}
        force_retained_ids: set[int] = set()

        # Hard preservation pass
        if preserve_anchors or preserve_products:
            # Per-target anchor tracking
            target_anchors: dict[str, list[_CandidateScore]] = {}
            target_product_participants: dict[str, list[_CandidateScore]] = {}
            for s in scores_sorted:
                tid = s.cand.target_id
                if s.is_anchor:
                    target_anchors.setdefault(tid, []).append(s)
                if s.has_valid_product:
                    target_product_participants.setdefault(tid, []).append(s)

            for s in scores_sorted:
                tid = s.cand.target_id
                force = False
                if preserve_anchors:
                    # If this is the ONLY anchor for this target in this cluster, force retain
                    anchors_for_target = target_anchors.get(tid, [])
                    if len(anchors_for_target) == 1 and anchors_for_target[0] is s:
                        force = True
                if preserve_products and not force:
                    # If this is the ONLY product participant for this target in this cluster, force retain
                    participants = target_product_participants.get(tid, [])
                    if len(participants) == 1 and participants[0] is s:
                        force = True

                if force:
                    cid = id(s.cand)
                    if cid not in force_retained_ids:
                        force_retained_ids.add(cid)
                        retained_in_cluster.append(s.cand)
                        cluster_retained_per_target[tid] = cluster_retained_per_target.get(tid, 0) + 1
                        preservation_forced += 1

        # Capacity pass: fill remaining slots by rank
        for s in scores_sorted:
            cid = id(s.cand)
            if cid in force_retained_ids:
                continue
            tid = s.cand.target_id
            current_for_target = cluster_retained_per_target.get(tid, 0)
            if current_for_target < lambda_cap:
                retained_in_cluster.append(s.cand)
                cluster_retained_per_target[tid] = current_for_target + 1
            else:
                rejected_by_capacity += 1

        retained.extend(retained_in_cluster)

        # Cluster info for debug
        cluster_info = {
            "cluster_index": cluster_idx,
            "sat_id": cluster[0].sat_id if cluster else None,
            "pre_count": len(cluster),
            "post_count": len(retained_in_cluster),
            "force_retained": len(force_retained_ids),
            "start": cluster[0].start.isoformat() if cluster else None,
            "end": cluster[-1].end.isoformat() if cluster else None,
        }
        by_cluster_info.append(cluster_info)

        # Target info aggregation
        for c in cluster:
            tid = c.target_id
            entry = by_target_info.setdefault(tid, {"pre": 0, "post": 0, "forced": 0, "rejected": 0})
            entry["pre"] += 1
        for c in retained_in_cluster:
            tid = c.target_id
            by_target_info[tid]["post"] += 1
        for s in scores_sorted:
            cid = id(s.cand)
            if cid in force_retained_ids:
                by_target_info[s.cand.target_id]["forced"] += 1
            elif s.cand not in retained_in_cluster:
                by_target_info[s.cand.target_id]["rejected"] += 1

    # Global cap enforcement: if total retained exceeds max_total, prune by global rank
    if len(retained) > max_total:
        # Recompute global scores for retained candidates
        global_scores = _score_candidates(
            retained, pairs, tris, target_total_candidates,
            mission.validity_thresholds.near_nadir_anchor_max_off_nadir_deg,
        )
        global_mean_on = sum(s.cand.combined_off_nadir_deg for s in global_scores) / len(global_scores) if global_scores else 0.0
        global_scores_sorted = sorted(global_scores, key=lambda s: _rank_key(s, global_mean_on))
        # Force-retain anchors and product participants even under global cap
        global_force_ids: set[int] = set()
        if preserve_anchors or preserve_products:
            target_anchors_g: dict[str, list[_CandidateScore]] = {}
            target_prod_g: dict[str, list[_CandidateScore]] = {}
            for s in global_scores_sorted:
                tid = s.cand.target_id
                if s.is_anchor:
                    target_anchors_g.setdefault(tid, []).append(s)
                if s.has_valid_product:
                    target_prod_g.setdefault(tid, []).append(s)
            for s in global_scores_sorted:
                tid = s.cand.target_id
                force = False
                if preserve_anchors:
                    anchors = target_anchors_g.get(tid, [])
                    if len(anchors) == 1 and anchors[0] is s:
                        force = True
                if preserve_products and not force:
                    prods = target_prod_g.get(tid, [])
                    if len(prods) == 1 and prods[0] is s:
                        force = True
                if force:
                    global_force_ids.add(id(s.cand))

        kept: list[CandidateObservation] = []
        for s in global_scores_sorted:
            cid = id(s.cand)
            if cid in global_force_ids:
                kept.append(s.cand)
            elif len(kept) < max_total:
                kept.append(s.cand)
            else:
                rejected_by_capacity += 1
        retained = kept

    # Recompute products on pruned candidates
    post_pairs, post_tris, post_summary = enumerate_products(
        retained, satellites, targets, mission, config
    )

    summary = PruningSummary(
        enabled=True,
        cluster_gap_s=gap_s,
        lambda_cap=lambda_cap,
        pre_candidates=pre_candidates,
        post_candidates=len(retained),
        pre_pairs=pre_pairs,
        post_pairs=len(post_pairs),
        pre_tris=pre_tris,
        post_tris=len(post_tris),
        by_target=by_target_info,
        by_cluster=by_cluster_info,
        preservation_forced=preservation_forced,
        rejected_by_capacity=rejected_by_capacity,
    )

    return retained, post_pairs, post_tris, summary
