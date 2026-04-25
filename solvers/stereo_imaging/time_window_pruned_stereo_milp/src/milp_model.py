"""Abstract MILP formulation, conflict graph, and deterministic greedy heuristic.

OR-Tools CP-SAT is the exact reproduced-solver backend. The greedy heuristic is
available only when explicitly selected for smoke or diagnostic runs.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from geometry import (
    angle_between_deg,
    boresight_unit_vector,
    make_earth_satellite,
    satellite_state_ecef_m,
)
from models import (
    CandidateObservation,
    Mission,
    Satellite,
    SolveSummary,
    StereoPair,
    Target,
    TriStereoSet,
)

_NUMERICAL_EPS = 1e-9
_SLEW_SAFETY_BUFFER_S = 0.5
_QUALITY_SCALE = 1000


# ---------------------------------------------------------------------------
# Conflict graph
# ---------------------------------------------------------------------------

def _min_slew_time_s(delta_deg: float, sat: Satellite) -> float:
    """Bang-bang (trapezoidal) slew time — same formula as the verifier."""
    d = abs(delta_deg)
    if d < _NUMERICAL_EPS:
        return 0.0
    omega = sat.max_slew_velocity_deg_per_s
    alpha = sat.max_slew_acceleration_deg_per_s2
    if omega < _NUMERICAL_EPS or alpha < _NUMERICAL_EPS:
        return float("inf")
    d_tri = omega * omega / alpha
    if d <= d_tri:
        return 2.0 * math.sqrt(d / alpha)
    else:
        return d / omega + omega / alpha


def _boresight_angle_at_boundaries(
    cand_a: CandidateObservation, cand_b: CandidateObservation, sat: Satellite, sf: Any
) -> float:
    """Angle (deg) between boresight vectors at end of cand_a and start of cand_b."""
    sp_a, sv_a = satellite_state_ecef_m(sf, cand_a.end)
    sp_b, sv_b = satellite_state_ecef_m(sf, cand_b.start)
    b_a = boresight_unit_vector(sp_a, sv_a, cand_a.off_nadir_along_deg, cand_a.off_nadir_across_deg)
    b_b = boresight_unit_vector(sp_b, sv_b, cand_b.off_nadir_along_deg, cand_b.off_nadir_across_deg)
    return angle_between_deg(b_a, b_b)


def _conflict_between(
    cand_a: CandidateObservation, cand_b: CandidateObservation, sat: Satellite, sf: Any
) -> str | None:
    """Return conflict reason or None if the two candidates can coexist."""
    if cand_a.sat_id != cand_b.sat_id:
        return None

    # Temporal overlap
    if cand_a.end > cand_b.start and cand_b.end > cand_a.start:
        return "overlap"

    # Non-overlapping — check slew/settle gap
    if cand_a.end <= cand_b.start:
        gap = (cand_b.start - cand_a.end).total_seconds()
        a_first, a_second = cand_a, cand_b
    elif cand_b.end <= cand_a.start:
        gap = (cand_a.start - cand_b.end).total_seconds()
        a_first, a_second = cand_b, cand_a
    else:
        return "overlap"  # should not reach here

    delta_deg = _boresight_angle_at_boundaries(a_first, a_second, sat, sf)
    need = sat.settling_time_s + _min_slew_time_s(delta_deg, sat) + _SLEW_SAFETY_BUFFER_S
    if gap + 1e-6 < need:
        return "slew"

    return None


def build_conflict_graph(
    candidates: list[CandidateObservation],
    satellites: dict[str, Satellite],
    sat_es_map: dict[str, Any] | None = None,
) -> dict[tuple[int, int], str]:
    """Map from sorted (index_a, index_b) to conflict reason."""
    if sat_es_map is None:
        sat_es_map = {sid: make_earth_satellite(sat) for sid, sat in satellites.items()}

    conflicts: dict[tuple[int, int], str] = {}

    # Group candidates by satellite and sort by start time
    sat_candidates: dict[str, list[tuple[int, CandidateObservation]]] = {}
    for i, c in enumerate(candidates):
        sat_candidates.setdefault(c.sat_id, []).append((i, c))

    for sat_id, sat_cands in sat_candidates.items():
        sat = satellites.get(sat_id)
        if sat is None:
            continue

        sat_cands.sort(key=lambda x: x[1].start)
        max_gap_s = sat.settling_time_s + _min_slew_time_s(180.0, sat) + _SLEW_SAFETY_BUFFER_S
        sf = sat_es_map.get(sat_id)
        if sf is None:
            continue

        n = len(sat_cands)
        for i in range(n):
            idx_i, cand_i = sat_cands[i]
            for j in range(i + 1, n):
                idx_j, cand_j = sat_cands[j]

                gap = (cand_j.start - cand_i.end).total_seconds()
                if gap > max_gap_s:
                    break

                reason = _conflict_between(cand_i, cand_j, sat, sf)
                if reason is not None:
                    a, b = (idx_i, idx_j) if idx_i < idx_j else (idx_j, idx_i)
                    conflicts[(a, b)] = reason

    return conflicts


# ---------------------------------------------------------------------------
# Abstract MILP model
# ---------------------------------------------------------------------------

@dataclass
class AbstractMILP:
    obs_vars: list[dict[str, Any]] = field(default_factory=list)
    pair_vars: list[dict[str, Any]] = field(default_factory=list)
    tri_vars: list[dict[str, Any]] = field(default_factory=list)
    target_coverage_vars: list[dict[str, Any]] = field(default_factory=list)
    pair_link_constraints: list[dict[str, Any]] = field(default_factory=list)
    pair_activation_constraints: list[dict[str, Any]] = field(default_factory=list)
    tri_link_constraints: list[dict[str, Any]] = field(default_factory=list)
    tri_activation_constraints: list[dict[str, Any]] = field(default_factory=list)
    target_coverage_constraints: list[dict[str, Any]] = field(default_factory=list)
    conflict_constraints: list[dict[str, Any]] = field(default_factory=list)
    coverage_bonus: float = 0.0


def _candidate_index_map(candidates: list[CandidateObservation]) -> dict[CandidateObservation, int]:
    return {c: i for i, c in enumerate(candidates)}


def _coverage_bonus(n_targets: int) -> float:
    return float(max(1, n_targets) + 1)


def evaluate_realized_products(
    selected_set: set[CandidateObservation],
    pairs: list[StereoPair],
    tris: list[TriStereoSet],
    target_ids: Iterable[str],
) -> dict[str, Any]:
    """Evaluate realized products with benchmark best-per-target semantics."""
    target_id_set = set(target_ids)
    target_id_set.update(p.target_id for p in pairs if p.valid)
    target_id_set.update(t.target_id for t in tris if t.valid)
    ordered_target_ids = sorted(target_id_set)

    per_target_best_score = {tid: 0.0 for tid in ordered_target_ids}
    selected_pairs = 0
    selected_tris = 0

    for p in pairs:
        if p.valid and p.candidate_i in selected_set and p.candidate_j in selected_set:
            selected_pairs += 1
            if p.q_pair > per_target_best_score[p.target_id]:
                per_target_best_score[p.target_id] = p.q_pair

    for t in tris:
        if t.valid and all(c in selected_set for c in t.candidates):
            selected_tris += 1
            if t.q_tri > per_target_best_score[t.target_id]:
                per_target_best_score[t.target_id] = t.q_tri

    covered_targets = sum(1 for score in per_target_best_score.values() if score > 0.0)
    best_target_quality_sum = sum(per_target_best_score.values())
    n_targets = len(ordered_target_ids)
    normalized_quality = best_target_quality_sum / n_targets if n_targets else 0.0

    return {
        "selected_pairs": selected_pairs,
        "selected_tris": selected_tris,
        "covered_targets": covered_targets,
        "coverage_ratio": covered_targets / n_targets if n_targets else 0.0,
        "best_target_quality_sum": best_target_quality_sum,
        "normalized_quality": normalized_quality,
        "per_target_best_score": per_target_best_score,
    }


def build_milp(
    candidates: list[CandidateObservation],
    pairs: list[StereoPair],
    tris: list[TriStereoSet],
    targets: dict[str, Target],
    satellites: dict[str, Satellite],
    mission: Mission,
    config: dict[str, Any],
    prebuilt_conflicts: dict[tuple[int, int], str] | None = None,
) -> AbstractMILP:
    """Construct the abstract MILP from candidates, products, and conflicts."""
    cand_index = _candidate_index_map(candidates)

    def _find_obs_index(cand: CandidateObservation) -> int:
        return cand_index[cand]

    model = AbstractMILP(coverage_bonus=_coverage_bonus(len(targets)))

    # Observation variables
    for i, c in enumerate(candidates):
        model.obs_vars.append({"idx": i, "cand": c})

    # Conflict constraints
    conflicts = prebuilt_conflicts if prebuilt_conflicts is not None else build_conflict_graph(candidates, satellites)
    for (ia, ib), reason in conflicts.items():
        model.conflict_constraints.append({
            "type": "conflict",
            "obs_indices": [ia, ib],
            "reason": reason,
        })

    # Pair variables and link constraints (only valid pairs)
    valid_pairs = [p for p in pairs if p.valid]
    for j, p in enumerate(valid_pairs):
        i1 = _find_obs_index(p.candidate_i)
        i2 = _find_obs_index(p.candidate_j)
        model.pair_vars.append({"idx": j, "pair": p, "obs_indices": [i1, i2]})
        model.pair_link_constraints.append({"type": "pair_link", "pair_idx": j, "obs_idx": i1})
        model.pair_link_constraints.append({"type": "pair_link", "pair_idx": j, "obs_idx": i2})
        model.pair_activation_constraints.append({"type": "pair_active", "pair_idx": j, "obs_indices": [i1, i2]})

    # Tri variables and link constraints (only valid tris)
    valid_tris = [t for t in tris if t.valid]
    for k, t in enumerate(valid_tris):
        obs_indices = [_find_obs_index(c) for c in t.candidates]
        model.tri_vars.append({"idx": k, "tri": t, "obs_indices": obs_indices})
        for oi in obs_indices:
            model.tri_link_constraints.append({"type": "tri_link", "tri_idx": k, "obs_idx": oi})
        model.tri_activation_constraints.append({"type": "tri_active", "tri_idx": k, "obs_indices": obs_indices})

    # Target coverage variables and constraints
    # Build lookup: target_id -> list of (pair_idx or tri_idx, is_tri)
    target_products: dict[str, list[tuple[int, bool]]] = {}
    for j, pv in enumerate(model.pair_vars):
        tid = pv["pair"].target_id
        target_products.setdefault(tid, []).append((j, False))
    for k, tv in enumerate(model.tri_vars):
        tid = tv["tri"].target_id
        target_products.setdefault(tid, []).append((k, True))

    for m, tid in enumerate(sorted(targets.keys())):
        model.target_coverage_vars.append({"idx": m, "target_id": tid})
        products = target_products.get(tid, [])
        model.target_coverage_constraints.append({
            "type": "target_coverage",
            "target_idx": m,
            "target_id": tid,
            "products": products,
        })

    return model


# ---------------------------------------------------------------------------
# Backend solvers
# ---------------------------------------------------------------------------

class BackendUnavailable(Exception):
    pass


def solve_with_ortools(model: AbstractMILP, time_limit_s: float) -> tuple[list[int], float, dict[str, Any]]:
    """Try to solve with OR-Tools CP-SAT. Raise BackendUnavailable if ortools is not installed."""
    try:
        from ortools.sat.python import cp_model
    except Exception as exc:
        raise BackendUnavailable(f"ortools import failed: {exc}") from exc

    cp = cp_model.CpModel()
    n_obs = len(model.obs_vars)
    n_pair = len(model.pair_vars)
    n_tri = len(model.tri_vars)
    n_tgt = len(model.target_coverage_vars)

    x = [cp.NewBoolVar(f"x_{i}") for i in range(n_obs)]
    y = [cp.NewBoolVar(f"y_{j}") for j in range(n_pair)]
    z = [cp.NewBoolVar(f"z_{k}") for k in range(n_tri)]
    w = [cp.NewBoolVar(f"w_{m}") for m in range(n_tgt)]
    sy = [cp.NewBoolVar(f"sy_{j}") for j in range(n_pair)]
    sz = [cp.NewBoolVar(f"sz_{k}") for k in range(n_tri)]

    # Pair links
    for lc in model.pair_link_constraints:
        j = lc["pair_idx"]
        i = lc["obs_idx"]
        cp.Add(y[j] <= x[i])
    for ac in model.pair_activation_constraints:
        j = ac["pair_idx"]
        obs_indices = ac["obs_indices"]
        cp.Add(y[j] >= cp_model.LinearExpr.Sum([x[i] for i in obs_indices]) - (len(obs_indices) - 1))

    # Tri links
    for lc in model.tri_link_constraints:
        k = lc["tri_idx"]
        i = lc["obs_idx"]
        cp.Add(z[k] <= x[i])
    for ac in model.tri_activation_constraints:
        k = ac["tri_idx"]
        obs_indices = ac["obs_indices"]
        cp.Add(z[k] >= cp_model.LinearExpr.Sum([x[i] for i in obs_indices]) - (len(obs_indices) - 1))

    for j in range(n_pair):
        cp.Add(sy[j] <= y[j])
    for k in range(n_tri):
        cp.Add(sz[k] <= z[k])

    # Coverage and per-target best-product choice
    for tc in model.target_coverage_constraints:
        m = tc["target_idx"]
        score_terms: list[Any] = []
        for prod_idx, is_tri in tc["products"]:
            if is_tri:
                score_terms.append(sz[prod_idx])
            else:
                score_terms.append(sy[prod_idx])
        if score_terms:
            cp.Add(w[m] == cp_model.LinearExpr.Sum(score_terms))
        else:
            cp.Add(w[m] == 0)

    # Conflicts
    for cc in model.conflict_constraints:
        ia, ib = cc["obs_indices"]
        cp.Add(x[ia] + x[ib] <= 1)

    # Objective: lexicographic coverage bonus plus best-per-target product quality.
    coverage_bonus = int(round(model.coverage_bonus * _QUALITY_SCALE))
    obj_terms: list[Any] = []
    for m in range(n_tgt):
        obj_terms.append(coverage_bonus * w[m])
    for j, pv in enumerate(model.pair_vars):
        q = int(round(pv["pair"].q_pair * _QUALITY_SCALE))
        obj_terms.append(q * sy[j])
    for k, tv in enumerate(model.tri_vars):
        q = int(round(tv["tri"].q_tri * _QUALITY_SCALE))
        obj_terms.append(q * sz[k])

    cp.Maximize(cp_model.LinearExpr.Sum(obj_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 1  # deterministic

    start = time.perf_counter()
    status = solver.Solve(cp)
    elapsed = time.perf_counter() - start
    status_name = solver.StatusName(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"OR-Tools solve failed with status {status_name}")

    selected = [i for i in range(n_obs) if solver.Value(x[i]) == 1]
    obj_value = solver.ObjectiveValue() / _QUALITY_SCALE

    stats = {
        "status": status_name,
        "objective_value": obj_value,
        "solve_time_s": elapsed,
        "optimality_gap": 0.0 if status == cp_model.OPTIMAL else None,
        "is_exact_backend": True,
        "is_heuristic": False,
    }
    return selected, obj_value, stats


# ---------------------------------------------------------------------------
# Greedy heuristic
# ---------------------------------------------------------------------------

def solve_greedy_heuristic(
    model: AbstractMILP, config: dict[str, Any]
) -> tuple[list[int], float, dict[str, Any]]:
    """Deterministic greedy selection using coverage gain, then best-target gain."""
    del config

    n_obs = len(model.obs_vars)

    # Build conflict lookup: obs_idx -> set of conflicting obs indices
    conflict_neighbors: dict[int, set[int]] = {i: set() for i in range(n_obs)}
    for cc in model.conflict_constraints:
        ia, ib = cc["obs_indices"]
        conflict_neighbors[ia].add(ib)
        conflict_neighbors[ib].add(ia)

    target_ids = [tv["target_id"] for tv in model.target_coverage_vars]
    pair_products = [pv["pair"] for pv in model.pair_vars]
    tri_products = [tv["tri"] for tv in model.tri_vars]

    # Products with their constituent observation indices
    products: list[dict[str, Any]] = []
    for j, pv in enumerate(model.pair_vars):
        products.append({
            "type": "pair",
            "idx": j,
            "obs_indices": pv["obs_indices"],
            "quality": pv["pair"].q_pair,
            "target_id": pv["pair"].target_id,
            "sat_id": pv["pair"].sat_id,
            "satellite_ids": list(pv["pair"].satellite_ids),
            "interval_id": pv["pair"].access_interval_id,
            "access_interval_ids": list(pv["pair"].access_interval_ids),
            "pair_mode": pv["pair"].pair_mode,
            "time_separation_s": pv["pair"].time_separation_s,
            "start": pv["pair"].candidate_i.start,
        })
    for k, tv in enumerate(model.tri_vars):
        products.append({
            "type": "tri",
            "idx": k,
            "obs_indices": tv["obs_indices"],
            "quality": tv["tri"].q_tri,
            "target_id": tv["tri"].target_id,
            "sat_id": tv["tri"].sat_id,
            "satellite_ids": list(tv["tri"].satellite_ids),
            "interval_id": tv["tri"].access_interval_id,
            "access_interval_ids": list(tv["tri"].access_interval_ids),
            "start": tv["tri"].candidates[0].start,
        })

    # Stable deterministic scan order for ties.
    products.sort(key=lambda p: (
        p["target_id"],
        p["sat_id"],
        p["interval_id"],
        p["start"].isoformat(),
        p["type"],
        p["idx"],
    ))

    selected_obs: set[int] = set()
    selected_prod_indices: list[int] = []

    def _can_add_obs(obs_idx: int) -> bool:
        if obs_idx in selected_obs:
            return True
        for other in selected_obs:
            if obs_idx == other:
                continue
            if obs_idx in conflict_neighbors.get(other, set()):
                return False
        return True

    def _evaluate_obs_indices(obs_indices: set[int]) -> dict[str, Any]:
        return evaluate_realized_products(
            {model.obs_vars[i]["cand"] for i in obs_indices},
            pair_products,
            tri_products,
            target_ids,
        )

    current_eval = _evaluate_obs_indices(selected_obs)
    while True:
        best_choice: tuple[int, dict[str, Any], int, float] | None = None
        for pi, prod in enumerate(products):
            if not all(_can_add_obs(oi) for oi in prod["obs_indices"]):
                continue
            candidate_obs = selected_obs | set(prod["obs_indices"])
            candidate_eval = _evaluate_obs_indices(candidate_obs)
            coverage_gain = candidate_eval["covered_targets"] - current_eval["covered_targets"]
            quality_gain = candidate_eval["best_target_quality_sum"] - current_eval["best_target_quality_sum"]
            if coverage_gain < 0 or quality_gain < -_NUMERICAL_EPS:
                continue
            if coverage_gain == 0 and quality_gain <= _NUMERICAL_EPS:
                continue
            if best_choice is None:
                best_choice = (pi, candidate_eval, coverage_gain, quality_gain)
                continue
            _, _, best_coverage_gain, best_quality_gain = best_choice
            if coverage_gain > best_coverage_gain:
                best_choice = (pi, candidate_eval, coverage_gain, quality_gain)
                continue
            if coverage_gain == best_coverage_gain and quality_gain > best_quality_gain + _NUMERICAL_EPS:
                best_choice = (pi, candidate_eval, coverage_gain, quality_gain)

        if best_choice is None:
            break

        pi, candidate_eval, _, _ = best_choice
        for oi in products[pi]["obs_indices"]:
            selected_obs.add(oi)
        selected_prod_indices.append(pi)
        current_eval = candidate_eval

    selected_indices = sorted(selected_obs)
    objective_value = model.coverage_bonus * current_eval["covered_targets"] + current_eval["best_target_quality_sum"]

    stats = {
        "status": "HEURISTIC",
        "is_exact_backend": False,
        "is_heuristic": True,
        "greedy_pass_products": len(selected_prod_indices),
        "selection_iterations": len(selected_prod_indices),
        "repair_iterations": 0,
    }
    return selected_indices, objective_value, stats


# ---------------------------------------------------------------------------
# Unified solve entrypoint
# ---------------------------------------------------------------------------

def _solve_once(
    model: AbstractMILP,
    backend: str,
    time_limit_s: float,
    config: dict[str, Any],
) -> tuple[list[int] | None, float, dict[str, Any], str, bool, float]:
    """Try one solve without silently falling back to a weaker backend."""
    solve_start = time.perf_counter()

    if backend == "greedy":
        selected_indices, objective_value, solve_stats = solve_greedy_heuristic(model, config)
        backend_used = "greedy"
        solve_time = time.perf_counter() - solve_start
        return selected_indices, objective_value, solve_stats, backend_used, False, solve_time

    if backend != "ortools":
        raise ValueError(f"unknown optimization.backend: {backend!r}")

    try:
        selected_indices, objective_value, solve_stats = solve_with_ortools(model, time_limit_s)
    except BackendUnavailable as exc:
        raise BackendUnavailable(
            f"OR-Tools exact backend unavailable for optimization.backend='ortools': {exc}. "
            "Install solver-local dependencies with ./setup.sh, or set optimization.backend: greedy "
            "explicitly for smoke/diagnostic runs."
        ) from exc

    backend_used = "ortools"
    solve_time = solve_stats.get("solve_time_s", 0.0)
    timeout_reached = solve_stats.get("status") != "OPTIMAL"

    return selected_indices, objective_value, solve_stats, backend_used, timeout_reached, solve_time


def _evaluate_solution(
    model: AbstractMILP,
    selected_indices: list[int],
) -> dict[str, Any]:
    """Evaluate a selected observation set under benchmark ranking semantics."""
    return evaluate_realized_products(
        {model.obs_vars[i]["cand"] for i in selected_indices},
        [pv["pair"] for pv in model.pair_vars],
        [tv["tri"] for tv in model.tri_vars],
        [tv["target_id"] for tv in model.target_coverage_vars],
    )


def solve_milp(
    candidates: list[CandidateObservation],
    pairs: list[StereoPair],
    tris: list[TriStereoSet],
    targets: dict[str, Target],
    satellites: dict[str, Satellite],
    mission: Mission,
    config: dict[str, Any],
) -> tuple[list[int], SolveSummary]:
    """Build the model, solve once, and report benchmark-aligned metrics."""
    opt_cfg = config.get("optimization", {})
    backend = opt_cfg.get("backend", "ortools")
    time_limit_s = float(opt_cfg.get("time_limit_s", 300.0))

    # Build conflict graph once — conflicts depend only on candidates and satellites
    conflict_start = time.perf_counter()
    prebuilt_conflicts = build_conflict_graph(candidates, satellites)
    conflict_time = time.perf_counter() - conflict_start
    model_build_start = time.perf_counter()
    model = build_milp(
        candidates, pairs, tris, targets, satellites, mission, config,
        prebuilt_conflicts=prebuilt_conflicts,
    )
    model_build_time = time.perf_counter() - model_build_start
    selected_indices, objective_value, solve_stats, backend_used, timeout_reached, solve_time = _solve_once(
        model, backend, time_limit_s, config
    )
    evaluation = _evaluate_solution(model, selected_indices)

    summary = SolveSummary(
        backend_used=backend_used,
        n_obs_vars=len(model.obs_vars),
        n_pair_vars=len(model.pair_vars),
        n_tri_vars=len(model.tri_vars),
        n_conflict_constraints=len(model.conflict_constraints),
        n_coverage_constraints=len(model.target_coverage_constraints),
        selected_observations=len(selected_indices),
        selected_pairs=evaluation["selected_pairs"],
        selected_tris=evaluation["selected_tris"],
        covered_targets=evaluation["covered_targets"],
        coverage_ratio=evaluation["coverage_ratio"],
        objective_coverage=evaluation["covered_targets"],
        objective_quality=evaluation["best_target_quality_sum"],
        best_target_quality_sum=evaluation["best_target_quality_sum"],
        normalized_quality=evaluation["normalized_quality"],
        per_target_best_score=evaluation["per_target_best_score"],
        solve_time_s=solve_time,
        timeout_reached=timeout_reached,
        profiling={
            "conflict_graph_s": conflict_time,
            "model_build_s": model_build_time,
            "backend_requested": backend,
            "backend_used": backend_used,
            "backend_stats": dict(solve_stats),
        },
    )

    return selected_indices, summary
