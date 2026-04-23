"""Conservative solver-local repair for stereo MILP solutions.

Post-processes selected observations to guarantee:
- no duplicate actions
- no overlapping same-satellite observations
- sufficient slew/settle gap between consecutive same-satellite observations
- products whose required observations were removed are dropped

Repair is auditable and deterministic.
"""

from __future__ import annotations

from typing import Any

from geometry import (
    angle_between_deg,
    boresight_unit_vector,
    make_earth_satellite,
    satellite_state_ecef_m,
)
from models import (
    CandidateObservation,
    Mission,
    RepairLog,
    Satellite,
    StereoPair,
    Target,
    TriStereoSet,
)
from milp_model import _min_slew_time_s

_NUMERICAL_EPS = 1e-9
_SLEW_SAFETY_BUFFER_S = 0.5


def _boresight_angle_at_boundary(
    first: CandidateObservation, second: CandidateObservation, sat: Satellite
) -> float:
    """Boresight angle delta at the transition boundary (end of first, start of second).

    Matches the verifier's boundary evaluation for maximum accuracy.
    """
    sf = make_earth_satellite(sat)
    sp0, sv0 = satellite_state_ecef_m(sf, first.end)
    sp1, sv1 = satellite_state_ecef_m(sf, second.start)
    b0 = boresight_unit_vector(
        sp0, sv0, first.off_nadir_along_deg, first.off_nadir_across_deg
    )
    b1 = boresight_unit_vector(
        sp1, sv1, second.off_nadir_along_deg, second.off_nadir_across_deg
    )
    return angle_between_deg(b0, b1)


def _compute_coverage(
    selected_set: set[CandidateObservation],
    pairs: list[StereoPair],
    tris: list[TriStereoSet],
) -> set[str]:
    """Set of target_ids covered by at least one valid selected pair or tri."""
    covered: set[str] = set()
    for p in pairs:
        if p.valid and p.candidate_i in selected_set and p.candidate_j in selected_set:
            covered.add(p.target_id)
    for t in tris:
        if t.valid and all(c in selected_set for c in t.candidates):
            covered.add(t.target_id)
    return covered


def _obs_product_metrics(
    obs: CandidateObservation,
    selected_set: set[CandidateObservation],
    pairs: list[StereoPair],
    tris: list[TriStereoSet],
) -> tuple[int, float]:
    """Return (product_count, quality_sum) for *obs* among selected products."""
    count = 0
    quality = 0.0
    for p in pairs:
        if p.valid and p.candidate_i in selected_set and p.candidate_j in selected_set:
            if obs is p.candidate_i or obs is p.candidate_j:
                count += 1
                quality += p.q_pair
    for t in tris:
        if t.valid and all(c in selected_set for c in t.candidates):
            if obs in t.candidates:
                count += 1
                quality += t.q_tri
    return count, quality


def _choose_removal(
    a: CandidateObservation,
    b: CandidateObservation,
    selected_set: set[CandidateObservation],
    pairs: list[StereoPair],
    tris: list[TriStereoSet],
) -> CandidateObservation:
    """Choose which of *a* or *b* to remove.

    Preference order:
    1. Minimise coverage loss.
    2. Keep the observation involved in more products.
    3. Keep the observation with higher total product quality.
    4. Keep the observation with earlier start time (deterministic tie-break).
    """
    current_coverage = _compute_coverage(selected_set, pairs, tris)
    loss_a = current_coverage - _compute_coverage(selected_set - {a}, pairs, tris)
    loss_b = current_coverage - _compute_coverage(selected_set - {b}, pairs, tris)

    if len(loss_a) < len(loss_b):
        return a
    if len(loss_b) < len(loss_a):
        return b

    count_a, q_a = _obs_product_metrics(a, selected_set, pairs, tris)
    count_b, q_b = _obs_product_metrics(b, selected_set, pairs, tris)

    if count_a > count_b:
        return b
    if count_b > count_a:
        return a
    if q_a > q_b:
        return b
    if q_b > q_a:
        return a
    if a.start > b.start:
        return a
    return b


def _deduplicate(
    candidates: list[CandidateObservation],
) -> tuple[list[CandidateObservation], list[dict[str, Any]]]:
    """Remove observations with identical (sat, target, start, end, along, across)."""
    seen: set[CandidateObservation] = set()
    result: list[CandidateObservation] = []
    removed: list[dict[str, Any]] = []
    for c in candidates:
        if c in seen:
            removed.append(
                {
                    "satellite_id": c.sat_id,
                    "target_id": c.target_id,
                    "start_time": c.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end_time": c.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "off_nadir_along_deg": c.off_nadir_along_deg,
                    "off_nadir_across_deg": c.off_nadir_across_deg,
                    "reason": "duplicate",
                }
            )
        else:
            seen.add(c)
            result.append(c)
    return result, removed


def _repair_overlaps(
    candidates: list[CandidateObservation],
    pairs: list[StereoPair],
    tris: list[TriStereoSet],
) -> tuple[list[CandidateObservation], list[dict[str, Any]]]:
    """Iteratively remove overlapping same-satellite observations."""
    removed: list[dict[str, Any]] = []
    current = list(candidates)

    while True:
        by_sat: dict[str, list[CandidateObservation]] = {}
        for c in current:
            by_sat.setdefault(c.sat_id, []).append(c)

        found = False
        for sid, obs_list in by_sat.items():
            obs_list.sort(key=lambda c: (c.start, c.end, c.target_id, c.access_interval_id))
            for i in range(len(obs_list) - 1):
                a = obs_list[i]
                b = obs_list[i + 1]
                if b.start < a.end:
                    selected_set = set(current)
                    to_remove = _choose_removal(a, b, selected_set, pairs, tris)
                    current.remove(to_remove)
                    removed.append(
                        {
                            "satellite_id": to_remove.sat_id,
                            "target_id": to_remove.target_id,
                            "start_time": to_remove.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "end_time": to_remove.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "off_nadir_along_deg": to_remove.off_nadir_along_deg,
                            "off_nadir_across_deg": to_remove.off_nadir_across_deg,
                            "reason": "overlap",
                        }
                    )
                    found = True
                    break
            if found:
                break
        if not found:
            break

    return current, removed


def _repair_slew(
    candidates: list[CandidateObservation],
    pairs: list[StereoPair],
    tris: list[TriStereoSet],
    satellites: dict[str, Satellite],
) -> tuple[list[CandidateObservation], list[dict[str, Any]]]:
    """Iteratively remove same-satellite observations with insufficient slew/settle gap."""
    removed: list[dict[str, Any]] = []
    current = list(candidates)

    while True:
        by_sat: dict[str, list[CandidateObservation]] = {}
        for c in current:
            by_sat.setdefault(c.sat_id, []).append(c)

        found = False
        for sid, obs_list in by_sat.items():
            obs_list.sort(key=lambda c: (c.start, c.end, c.target_id, c.access_interval_id))
            sat = satellites.get(sid)
            if sat is None:
                continue
            for i in range(len(obs_list) - 1):
                a = obs_list[i]
                b = obs_list[i + 1]
                gap = (b.start - a.end).total_seconds()
                if gap < -_NUMERICAL_EPS:
                    continue  # overlap already handled above
                delta_deg = _boresight_angle_at_boundary(a, b, sat)
                need = sat.settling_time_s + _min_slew_time_s(delta_deg, sat) + _SLEW_SAFETY_BUFFER_S
                if gap + 1e-6 < need:
                    selected_set = set(current)
                    to_remove = _choose_removal(a, b, selected_set, pairs, tris)
                    current.remove(to_remove)
                    removed.append(
                        {
                            "satellite_id": to_remove.sat_id,
                            "target_id": to_remove.target_id,
                            "start_time": to_remove.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "end_time": to_remove.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "off_nadir_along_deg": to_remove.off_nadir_along_deg,
                            "off_nadir_across_deg": to_remove.off_nadir_across_deg,
                            "reason": "slew",
                            "detail": f"need={need:.3f}s gap={gap:.3f}s delta={delta_deg:.4f}deg",
                        }
                    )
                    found = True
                    break
            if found:
                break
        if not found:
            break

    return current, removed


def repair_solution(
    selected_candidates: list[CandidateObservation],
    pairs: list[StereoPair],
    tris: list[TriStereoSet],
    satellites: dict[str, Satellite],
    targets: dict[str, Target],
    mission: Mission,
    config: dict[str, Any],
) -> tuple[list[CandidateObservation], RepairLog]:
    """Apply conservative deterministic repair to selected observations.

    Returns the repaired candidate list and an auditable repair log.
    """
    del targets, mission  # reserved for future target-priority rules

    # Pre-repair metrics
    pre_set = set(selected_candidates)
    pre_pairs = sum(
        1 for p in pairs if p.valid and p.candidate_i in pre_set and p.candidate_j in pre_set
    )
    pre_tris = sum(
        1 for t in tris if t.valid and all(c in pre_set for c in t.candidates)
    )
    pre_coverage = len(_compute_coverage(pre_set, pairs, tris))

    # Step 1: deduplicate
    candidates, removed_dedup = _deduplicate(selected_candidates)

    # Step 2: overlap removal
    candidates, removed_overlap = _repair_overlaps(candidates, pairs, tris)

    # Step 3: slew/settle removal
    candidates, removed_slew = _repair_slew(candidates, pairs, tris, satellites)

    # Post-repair metrics
    post_set = set(candidates)
    post_pairs = sum(
        1 for p in pairs if p.valid and p.candidate_i in post_set and p.candidate_j in post_set
    )
    post_tris = sum(
        1 for t in tris if t.valid and all(c in post_set for c in t.candidates)
    )
    post_coverage = len(_compute_coverage(post_set, pairs, tris))

    log = RepairLog(
        removed_observations=removed_dedup + removed_overlap + removed_slew,
        pre_repair_obs_count=len(selected_candidates),
        post_repair_obs_count=len(candidates),
        pre_repair_pairs=pre_pairs,
        post_repair_pairs=post_pairs,
        pre_repair_tris=pre_tris,
        post_repair_tris=post_tris,
        pre_repair_covered_targets=pre_coverage,
        post_repair_covered_targets=post_coverage,
    )
    return candidates, log
