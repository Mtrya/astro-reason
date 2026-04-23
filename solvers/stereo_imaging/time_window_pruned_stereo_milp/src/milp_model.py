"""Abstract MILP formulation, conflict graph, and deterministic greedy fallback.

Backend-specific solvers (OR-Tools, PuLP) are pluggable via auto-discovery.
When no backend is available, the deterministic greedy fallback runs.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
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
    Satellite,
    SolveSummary,
    StereoPair,
    Target,
    TriStereoSet,
)

_NUMERICAL_EPS = 1e-9
_SLEW_SAFETY_BUFFER_S = 0.5


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


def _boresight_angle_between(cand_a: CandidateObservation, cand_b: CandidateObservation, sat: Satellite) -> float:
    """Angle (deg) between boresight vectors at candidate midpoints."""
    sf = make_earth_satellite(sat)
    mid_a = cand_a.start + (cand_a.end - cand_a.start) / 2
    mid_b = cand_b.start + (cand_b.end - cand_b.start) / 2
    sp_a, sv_a = satellite_state_ecef_m(sf, mid_a)
    sp_b, sv_b = satellite_state_ecef_m(sf, mid_b)
    b_a = boresight_unit_vector(sp_a, sv_a, cand_a.off_nadir_along_deg, cand_a.off_nadir_across_deg)
    b_b = boresight_unit_vector(sp_b, sv_b, cand_b.off_nadir_along_deg, cand_b.off_nadir_across_deg)
    return angle_between_deg(b_a, b_b)


def _conflict_between(cand_a: CandidateObservation, cand_b: CandidateObservation, sat: Satellite) -> str | None:
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

    delta_deg = _boresight_angle_between(a_first, a_second, sat)
    need = sat.settling_time_s + _min_slew_time_s(delta_deg, sat) + _SLEW_SAFETY_BUFFER_S
    if gap + 1e-6 < need:
        return "slew"

    return None


def build_conflict_graph(
    candidates: list[CandidateObservation], satellites: dict[str, Satellite]
) -> dict[tuple[int, int], str]:
    """Map from sorted (index_a, index_b) to conflict reason."""
    conflicts: dict[tuple[int, int], str] = {}
    n = len(candidates)
    for i in range(n):
        ci = candidates[i]
        sat = satellites.get(ci.sat_id)
        if sat is None:
            continue
        for j in range(i + 1, n):
            cj = candidates[j]
            if cj.sat_id != ci.sat_id:
                continue
            reason = _conflict_between(ci, cj, sat)
            if reason is not None:
                conflicts[(i, j)] = reason
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
    tri_link_constraints: list[dict[str, Any]] = field(default_factory=list)
    target_coverage_constraints: list[dict[str, Any]] = field(default_factory=list)
    conflict_constraints: list[dict[str, Any]] = field(default_factory=list)
    coverage_weight: float = 1000.0
    objective_quality_terms: list[tuple[float, int, str]] = field(default_factory=list)


def _candidate_index_map(candidates: list[CandidateObservation]) -> dict[tuple, int]:
    return {
        (c.sat_id, c.target_id, c.access_interval_id, c.start, c.end, c.off_nadir_along_deg, c.off_nadir_across_deg): i
        for i, c in enumerate(candidates)
    }


def build_milp(
    candidates: list[CandidateObservation],
    pairs: list[StereoPair],
    tris: list[TriStereoSet],
    targets: dict[str, Target],
    satellites: dict[str, Satellite],
    mission: Mission,
    config: dict[str, Any],
) -> AbstractMILP:
    """Construct the abstract MILP from candidates, products, and conflicts."""
    opt_cfg = config.get("optimization", {})
    coverage_weight = float(opt_cfg.get("coverage_weight", 1000.0))

    cand_index = _candidate_index_map(candidates)

    def _find_obs_index(cand: CandidateObservation) -> int:
        key = (cand.sat_id, cand.target_id, cand.access_interval_id, cand.start, cand.end, cand.off_nadir_along_deg, cand.off_nadir_across_deg)
        return cand_index[key]

    model = AbstractMILP(coverage_weight=coverage_weight)

    # Observation variables
    for i, c in enumerate(candidates):
        model.obs_vars.append({"idx": i, "cand": c})

    # Conflict constraints
    conflicts = build_conflict_graph(candidates, satellites)
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
        model.objective_quality_terms.append((p.q_pair, j, "pair"))

    # Tri variables and link constraints (only valid tris)
    valid_tris = [t for t in tris if t.valid]
    for k, t in enumerate(valid_tris):
        obs_indices = [_find_obs_index(c) for c in t.candidates]
        model.tri_vars.append({"idx": k, "tri": t, "obs_indices": obs_indices})
        for oi in obs_indices:
            model.tri_link_constraints.append({"type": "tri_link", "tri_idx": k, "obs_idx": oi})
        model.objective_quality_terms.append((t.q_tri, k, "tri"))

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

    # Scale quality to integers (CP-SAT requires integer coefficients)
    scale = 1000

    x = [cp.NewBoolVar(f"x_{i}") for i in range(n_obs)]
    y = [cp.NewBoolVar(f"y_{j}") for j in range(n_pair)]
    z = [cp.NewBoolVar(f"z_{k}") for k in range(n_tri)]
    w = [cp.NewBoolVar(f"w_{m}") for m in range(n_tgt)]

    # Pair links
    for lc in model.pair_link_constraints:
        j = lc["pair_idx"]
        i = lc["obs_idx"]
        cp.Add(y[j] <= x[i])

    # Tri links
    for lc in model.tri_link_constraints:
        k = lc["tri_idx"]
        i = lc["obs_idx"]
        cp.Add(z[k] <= x[i])

    # Target coverage
    for tc in model.target_coverage_constraints:
        m = tc["target_idx"]
        terms: list[Any] = []
        for prod_idx, is_tri in tc["products"]:
            if is_tri:
                terms.append(z[prod_idx])
            else:
                terms.append(y[prod_idx])
        if terms:
            cp.Add(w[m] <= cp_model.LinearExpr.Sum(terms))
        else:
            cp.Add(w[m] == 0)

    # Conflicts
    for cc in model.conflict_constraints:
        ia, ib = cc["obs_indices"]
        cp.Add(x[ia] + x[ib] <= 1)

    # Objective: coverage_weight * sum(w) + scale * (sum(q_pair * y) + sum(q_tri * z))
    coverage_weight = int(model.coverage_weight * scale)
    obj_terms: list[Any] = []
    for m in range(n_tgt):
        obj_terms.append(coverage_weight * w[m])
    for j, pv in enumerate(model.pair_vars):
        q = int(round(pv["pair"].q_pair * scale))
        obj_terms.append(q * y[j])
    for k, tv in enumerate(model.tri_vars):
        q = int(round(tv["tri"].q_tri * scale))
        obj_terms.append(q * z[k])

    cp.Maximize(cp_model.LinearExpr.Sum(obj_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 1  # deterministic

    start = time.perf_counter()
    status = solver.Solve(cp)
    elapsed = time.perf_counter() - start

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"OR-Tools solve failed with status {status}")

    selected = [i for i in range(n_obs) if solver.Value(x[i]) == 1]
    obj_value = solver.ObjectiveValue() / scale

    stats = {
        "status": str(status),
        "objective_value": obj_value,
        "solve_time_s": elapsed,
        "optimality_gap": 0.0 if status == cp_model.OPTIMAL else None,
    }
    return selected, obj_value, stats


def solve_with_pulp(model: AbstractMILP, time_limit_s: float) -> tuple[list[int], float, dict[str, Any]]:
    """Try to solve with PuLP + CBC. Raise BackendUnavailable if pulp is not installed."""
    try:
        import pulp
    except Exception as exc:
        raise BackendUnavailable(f"pulp import failed: {exc}") from exc

    prob = pulp.LpProblem("stereo_milp", pulp.LpMaximize)
    n_obs = len(model.obs_vars)
    n_pair = len(model.pair_vars)
    n_tri = len(model.tri_vars)
    n_tgt = len(model.target_coverage_vars)

    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(n_obs)]
    y = [pulp.LpVariable(f"y_{j}", cat="Binary") for j in range(n_pair)]
    z = [pulp.LpVariable(f"z_{k}", cat="Binary") for k in range(n_tri)]
    w = [pulp.LpVariable(f"w_{m}", cat="Binary") for m in range(n_tgt)]

    for lc in model.pair_link_constraints:
        prob += y[lc["pair_idx"]] <= x[lc["obs_idx"]]

    for lc in model.tri_link_constraints:
        prob += z[lc["tri_idx"]] <= x[lc["obs_idx"]]

    for tc in model.target_coverage_constraints:
        m = tc["target_idx"]
        terms = []
        for prod_idx, is_tri in tc["products"]:
            terms.append(z[prod_idx] if is_tri else y[prod_idx])
        if terms:
            prob += w[m] <= pulp.lpSum(terms)
        else:
            prob += w[m] == 0

    for cc in model.conflict_constraints:
        ia, ib = cc["obs_indices"]
        prob += x[ia] + x[ib] <= 1

    # Objective
    obj = model.coverage_weight * pulp.lpSum(w)
    for j, pv in enumerate(model.pair_vars):
        obj += pv["pair"].q_pair * y[j]
    for k, tv in enumerate(model.tri_vars):
        obj += tv["tri"].q_tri * z[k]
    prob += obj

    start = time.perf_counter()
    prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit_s))
    elapsed = time.perf_counter() - start

    if pulp.LpStatus[prob.status] not in ("Optimal", "Feasible"):
        raise RuntimeError(f"PuLP solve failed with status {pulp.LpStatus[prob.status]}")

    selected = [i for i in range(n_obs) if pulp.value(x[i]) == 1]
    obj_value = pulp.value(prob.objective)

    stats = {
        "status": pulp.LpStatus[prob.status],
        "objective_value": obj_value,
        "solve_time_s": elapsed,
        "optimality_gap": None,
    }
    return selected, obj_value, stats


# ---------------------------------------------------------------------------
# Greedy fallback
# ---------------------------------------------------------------------------

def solve_greedy_fallback(
    model: AbstractMILP, config: dict[str, Any]
) -> tuple[list[int], float, dict[str, Any]]:
    """Deterministic greedy product selection with conflict repair.

    1. Sort valid products by quality (desc) with deterministic tie-breakers.
    2. Greedily select products whose observations don't conflict.
    3. Repair any remaining conflicts per satellite.
    4. Optional coverage-augmenting pass.
    """
    opt_cfg = config.get("optimization", {})
    coverage_augment = bool(opt_cfg.get("greedy_coverage_augment", True))
    max_repair_iter = int(opt_cfg.get("greedy_max_repair_iterations", 10))

    n_obs = len(model.obs_vars)

    # Build conflict lookup: obs_idx -> set of conflicting obs indices
    conflict_neighbors: dict[int, set[int]] = {i: set() for i in range(n_obs)}
    for cc in model.conflict_constraints:
        ia, ib = cc["obs_indices"]
        conflict_neighbors[ia].add(ib)
        conflict_neighbors[ib].add(ia)

    # Build per-observation satellite lookup
    obs_sat = [model.obs_vars[i]["cand"].sat_id for i in range(n_obs)]

    # Build target coverage lookup from model constraints
    target_coverage_map: dict[str, list[tuple[int, bool]]] = {}
    for tc in model.target_coverage_constraints:
        tid = tc["target_id"]
        target_coverage_map[tid] = tc["products"]

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
            "interval_id": pv["pair"].access_interval_id,
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
            "interval_id": tv["tri"].access_interval_id,
            "start": tv["tri"].candidates[0].start,
        })

    # Sort by quality desc, then deterministic tie-breakers
    products.sort(key=lambda p: (
        -p["quality"],
        p["target_id"],
        p["sat_id"],
        p["interval_id"],
        p["start"].isoformat(),
        p["type"],
        p["idx"],
    ))

    selected_obs: set[int] = set()
    selected_products: list[dict[str, Any]] = []

    def _can_add_obs(obs_idx: int) -> bool:
        for other in selected_obs:
            if obs_idx == other:
                continue
            if obs_idx in conflict_neighbors.get(other, set()):
                return False
        return True

    # Greedy pass
    for prod in products:
        obs_idxs = prod["obs_indices"]
        if all(_can_add_obs(oi) for oi in obs_idxs):
            for oi in obs_idxs:
                selected_obs.add(oi)
            selected_products.append(prod)

    # Conflict repair pass
    for _ in range(max_repair_iter):
        removed = False
        # Per satellite, sort by start time and scan adjacent conflicts
        sat_obs: dict[str, list[int]] = {}
        for oi in selected_obs:
            sid = obs_sat[oi]
            sat_obs.setdefault(sid, []).append(oi)

        for sid, ois in sat_obs.items():
            ois_sorted = sorted(ois, key=lambda i: model.obs_vars[i]["cand"].start)
            for a in range(len(ois_sorted) - 1):
                ia = ois_sorted[a]
                ib = ois_sorted[a + 1]
                if ib in conflict_neighbors.get(ia, set()):
                    # Remove the one that participates in fewer products
                    # Count how many selected products each observation participates in
                    def _obs_value(oi: int) -> float:
                        count = 0
                        q_sum = 0.0
                        for sp in selected_products:
                            if oi in sp["obs_indices"]:
                                count += 1
                                q_sum += sp["quality"]
                        return (count, q_sum)

                    va = _obs_value(ia)
                    vb = _obs_value(ib)
                    if va < vb or (va == vb and ia > ib):
                        to_remove = ia
                    else:
                        to_remove = ib

                    selected_obs.discard(to_remove)
                    # Also remove any products that now have missing observations
                    selected_products = [
                        sp for sp in selected_products
                        if all(oi in selected_obs for oi in sp["obs_indices"])
                    ]
                    removed = True
                    break
            if removed:
                break
        if not removed:
            break

    # Coverage-augmenting pass
    if coverage_augment:
        covered_targets = set()
        for sp in selected_products:
            covered_targets.add(sp["target_id"])

        for tid in sorted(target_coverage_map.keys()):
            if tid in covered_targets:
                continue
            # Try to add the best valid product for this target
            target_prods = [p for p in products if p["target_id"] == tid]
            target_prods.sort(key=lambda p: (-p["quality"], p["start"].isoformat(), p["idx"]))
            for tp in target_prods:
                if all(_can_add_obs(oi) for oi in tp["obs_indices"]):
                    for oi in tp["obs_indices"]:
                        selected_obs.add(oi)
                    selected_products.append(tp)
                    covered_targets.add(tid)
                    break

    selected_indices = sorted(selected_obs)

    # Approximate objective value
    covered_targets = set(sp["target_id"] for sp in selected_products)
    obj_coverage = len(covered_targets)
    obj_quality = sum(sp["quality"] for sp in selected_products)
    objective_value = model.coverage_weight * obj_coverage + obj_quality

    stats = {
        "greedy_pass_products": len(selected_products),
        "coverage_augment": coverage_augment,
        "repair_iterations": max_repair_iter,
    }
    return selected_indices, objective_value, stats


# ---------------------------------------------------------------------------
# Unified solve entrypoint
# ---------------------------------------------------------------------------

def solve_milp(
    candidates: list[CandidateObservation],
    pairs: list[StereoPair],
    tris: list[TriStereoSet],
    targets: dict[str, Target],
    satellites: dict[str, Satellite],
    mission: Mission,
    config: dict[str, Any],
) -> tuple[list[int], SolveSummary]:
    """Build model, try backends, fall back to greedy. Return selected obs indices and summary."""
    opt_cfg = config.get("optimization", {})
    backend = opt_cfg.get("backend", "auto")
    time_limit_s = float(opt_cfg.get("time_limit_s", 300.0))

    model = build_milp(candidates, pairs, tris, targets, satellites, mission, config)

    tried: list[str] = []
    selected_indices: list[int] | None = None
    objective_value = 0.0
    solve_stats: dict[str, Any] = {}
    fallback_reason: str | None = None
    backend_used = "unknown"
    timeout_reached = False
    solve_time = 0.0

    solve_start = time.perf_counter()

    if backend in ("auto", "ortools"):
        try:
            selected_indices, objective_value, solve_stats = solve_with_ortools(model, time_limit_s)
            backend_used = "ortools"
            solve_time = solve_stats.get("solve_time_s", 0.0)
            timeout_reached = solve_stats.get("status") != "OPTIMAL"
        except Exception as exc:
            tried.append(f"ortools: {exc}")

    if selected_indices is None and backend in ("auto", "pulp"):
        try:
            selected_indices, objective_value, solve_stats = solve_with_pulp(model, time_limit_s)
            backend_used = "pulp"
            solve_time = solve_stats.get("solve_time_s", 0.0)
            timeout_reached = solve_stats.get("status") not in ("Optimal",)
        except Exception as exc:
            tried.append(f"pulp: {exc}")

    if selected_indices is None:
        if backend == "greedy":
            fallback_reason = None
        else:
            fallback_reason = "; ".join(tried) if tried else "no_backend_available"
        selected_indices, objective_value, solve_stats = solve_greedy_fallback(model, config)
        backend_used = "greedy_fallback"
        solve_time = time.perf_counter() - solve_start
        timeout_reached = False

    # Count selected products and covered targets
    selected_obs_set = set(selected_indices)
    selected_pairs = 0
    selected_tris = 0
    covered_targets: set[str] = set()
    obj_quality = 0.0

    for pv in model.pair_vars:
        if all(oi in selected_obs_set for oi in pv["obs_indices"]):
            selected_pairs += 1
            covered_targets.add(pv["pair"].target_id)
            obj_quality += pv["pair"].q_pair

    for tv in model.tri_vars:
        if all(oi in selected_obs_set for oi in tv["obs_indices"]):
            selected_tris += 1
            covered_targets.add(tv["tri"].target_id)
            obj_quality += tv["tri"].q_tri

    summary = SolveSummary(
        backend_used=backend_used,
        fallback_reason=fallback_reason,
        n_obs_vars=len(model.obs_vars),
        n_pair_vars=len(model.pair_vars),
        n_tri_vars=len(model.tri_vars),
        n_conflict_constraints=len(model.conflict_constraints),
        n_coverage_constraints=len(model.target_coverage_constraints),
        selected_observations=len(selected_indices),
        selected_pairs=selected_pairs,
        selected_tris=selected_tris,
        covered_targets=len(covered_targets),
        objective_coverage=len(covered_targets),
        objective_quality=obj_quality,
        solve_time_s=solve_time,
        timeout_reached=timeout_reached,
    )

    return selected_indices, summary
