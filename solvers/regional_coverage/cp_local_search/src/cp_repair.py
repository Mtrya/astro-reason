"""Bounded OR-Tools CP-SAT repair for local sequence neighborhoods.

The repair is deliberately local: each call receives the incumbent candidates
kept outside one local-search neighborhood plus the candidate pool for that
neighborhood. The CP model chooses a feasible fixed-start subset that maximizes
unique benchmark-grid coverage not already supplied by the kept schedule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Iterable

from .candidates import Candidate
from .case_io import RegionalCoverageCase
from .coverage import CoverageIndex
from .sequence import create_empty_state, insert_candidate, is_consistent
from .transition import transition_result


@dataclass(frozen=True, slots=True)
class CPRepairConfig:
    enabled: bool = True
    backend: str = "ortools_cp_sat"
    max_calls: int = 32
    max_candidates: int = 10
    max_conflicts: int = 2048
    time_limit_s: float = 0.25
    min_improvement_weight_m2: float = 1.0e-6

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "CPRepairConfig":
        payload = payload or {}
        backend = str(payload.get("cp_backend", "ortools_cp_sat"))
        if backend != "ortools_cp_sat":
            raise ValueError(
                "cp_backend must be 'ortools_cp_sat'; run solver-local setup.sh to install OR-Tools"
            )
        return cls(
            enabled=bool(payload.get("cp_enabled", True)),
            backend=backend,
            max_calls=_non_negative_int(payload.get("cp_max_calls", 32), "cp_max_calls"),
            max_candidates=_positive_int(payload.get("cp_max_candidates", 10), "cp_max_candidates"),
            max_conflicts=_positive_int(
                payload.get("cp_max_conflicts", 2048),
                "cp_max_conflicts",
            ),
            time_limit_s=_positive_float(payload.get("cp_time_limit_s", 0.25), "cp_time_limit_s"),
            min_improvement_weight_m2=_non_negative_float(
                payload.get("cp_min_improvement_weight_m2", 1.0e-6),
                "cp_min_improvement_weight_m2",
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "backend": self.backend,
            "max_calls": self.max_calls,
            "max_candidates": self.max_candidates,
            "max_conflicts": self.max_conflicts,
            "time_limit_s": self.time_limit_s,
            "min_improvement_weight_m2": self.min_improvement_weight_m2,
        }


@dataclass(slots=True)
class CPMetrics:
    backend: str = "ortools_cp_sat"
    calls: int = 0
    feasible_solutions: int = 0
    improving_solutions: int = 0
    optimal_solutions: int = 0
    skipped_disabled: int = 0
    skipped_call_limit: int = 0
    skipped_size_limit: int = 0
    timeout_stops: int = 0
    conflict_limit_stops: int = 0
    infeasible_stops: int = 0
    unknown_stops: int = 0
    model_build_time_s: float = 0.0
    solve_time_s: float = 0.0
    cp_sat_version: str | None = None
    status_counts: dict[str, int] = field(default_factory=dict)
    model_bool_variables: int = 0
    model_constraints: int = 0
    candidate_variables: int = 0
    sample_coverage_variables: int = 0
    transition_conflict_constraints: int = 0
    anchor_conflict_constraints: int = 0
    coverage_link_constraints: int = 0
    branches: int = 0
    conflicts: int = 0

    def as_dict(self) -> dict[str, Any]:
        skipped_calls = self.skipped_disabled + self.skipped_call_limit + self.skipped_size_limit
        call_success_rate = 0.0 if self.calls == 0 else self.feasible_solutions / self.calls
        improving_success_rate = 0.0 if self.calls == 0 else self.improving_solutions / self.calls
        return {
            "backend": self.backend,
            "backend_note": "solver-local OR-Tools CP-SAT repair over bounded fixed-start TSPTW-style neighborhoods",
            "cp_sat_version": self.cp_sat_version,
            "calls": self.calls,
            "successful_calls": self.feasible_solutions,
            "call_success_rate": call_success_rate,
            "feasible_solutions": self.feasible_solutions,
            "optimal_solutions": self.optimal_solutions,
            "improving_solutions": self.improving_solutions,
            "improving_success_rate": improving_success_rate,
            "skipped_calls": skipped_calls,
            "skipped_disabled": self.skipped_disabled,
            "skipped_call_limit": self.skipped_call_limit,
            "skipped_size_limit": self.skipped_size_limit,
            "timeout_stops": self.timeout_stops,
            "conflict_limit_stops": self.conflict_limit_stops,
            "infeasible_stops": self.infeasible_stops,
            "unknown_stops": self.unknown_stops,
            "model_build_time_s": self.model_build_time_s,
            "solve_time_s": self.solve_time_s,
            "status_counts": dict(sorted(self.status_counts.items())),
            "model_bool_variables": self.model_bool_variables,
            "model_constraints": self.model_constraints,
            "candidate_variables": self.candidate_variables,
            "sample_coverage_variables": self.sample_coverage_variables,
            "transition_conflict_constraints": self.transition_conflict_constraints,
            "anchor_conflict_constraints": self.anchor_conflict_constraints,
            "coverage_link_constraints": self.coverage_link_constraints,
            "branches": self.branches,
            "conflicts": self.conflicts,
        }


@dataclass(frozen=True, slots=True)
class CPRepairResult:
    attempted: bool
    backend: str
    selected_candidate_ids: tuple[str, ...]
    feasible: bool
    improving: bool
    stop_reason: str
    solver_status: str | None
    objective_key: tuple[Any, ...] | None
    coverage_objective_m2: float
    objective_bound_m2: float | None
    model_bool_variables: int
    model_constraints: int
    candidate_variables: int
    sample_coverage_variables: int
    transition_conflict_constraints: int
    anchor_conflict_constraints: int
    coverage_link_constraints: int
    branches: int
    conflicts: int
    model_build_time_s: float
    solve_time_s: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "backend": self.backend,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "feasible": self.feasible,
            "improving": self.improving,
            "stop_reason": self.stop_reason,
            "solver_status": self.solver_status,
            "objective_key": list(self.objective_key) if self.objective_key is not None else None,
            "coverage_objective_m2": self.coverage_objective_m2,
            "objective_bound_m2": self.objective_bound_m2,
            "model_bool_variables": self.model_bool_variables,
            "model_constraints": self.model_constraints,
            "candidate_variables": self.candidate_variables,
            "sample_coverage_variables": self.sample_coverage_variables,
            "transition_conflict_constraints": self.transition_conflict_constraints,
            "anchor_conflict_constraints": self.anchor_conflict_constraints,
            "coverage_link_constraints": self.coverage_link_constraints,
            "branches": self.branches,
            "conflicts": self.conflicts,
            "model_build_time_s": self.model_build_time_s,
            "solve_time_s": self.solve_time_s,
        }


@dataclass(frozen=True, slots=True)
class _ModelStats:
    model_bool_variables: int
    model_constraints: int
    candidate_variables: int
    sample_coverage_variables: int
    transition_conflict_constraints: int
    anchor_conflict_constraints: int
    coverage_link_constraints: int


def cp_sat_repair(
    case: RegionalCoverageCase,
    *,
    kept_candidates: list[Candidate],
    neighborhood_candidates: list[Candidate],
    coverage_index: CoverageIndex,
    before_key: tuple[Any, ...],
    config: CPRepairConfig,
    metrics: CPMetrics,
) -> CPRepairResult:
    if not config.enabled:
        metrics.skipped_disabled += 1
        return _not_attempted(config, "disabled")
    if metrics.calls >= config.max_calls:
        metrics.skipped_call_limit += 1
        return _not_attempted(config, "call_limit")
    if len(neighborhood_candidates) > config.max_candidates:
        metrics.skipped_size_limit += 1
        return _not_attempted(config, "size_limit")

    cp_model, ortools_version = _load_cp_sat_backend()
    metrics.cp_sat_version = ortools_version

    build_start = perf_counter()
    pool = sorted(
        {candidate.candidate_id: candidate for candidate in neighborhood_candidates}.values(),
        key=_candidate_key,
    )
    kept = sorted(kept_candidates, key=_candidate_key)
    model = cp_model.CpModel()
    selected_vars = {
        candidate.candidate_id: model.NewBoolVar(_safe_var_name(f"sel_{candidate.candidate_id}"))
        for candidate in pool
    }

    transition_conflict_constraints = _add_pool_transition_constraints(
        case,
        model,
        pool,
        selected_vars,
    )
    anchor_conflict_constraints = _add_anchor_constraints(
        case,
        model,
        kept,
        pool,
        selected_vars,
    )
    model.Add(sum(selected_vars.values()) + len(kept) <= case.mission.max_actions_total)
    anchor_conflict_constraints += 1

    coverage_expr, sample_vars, coverage_link_constraints = _add_coverage_objective(
        model,
        kept,
        pool,
        selected_vars,
        coverage_index,
    )
    model.Maximize(coverage_expr)
    build_elapsed = perf_counter() - build_start
    stats = _model_stats(
        model,
        candidate_variables=len(selected_vars),
        sample_coverage_variables=len(sample_vars),
        transition_conflict_constraints=transition_conflict_constraints,
        anchor_conflict_constraints=anchor_conflict_constraints,
        coverage_link_constraints=coverage_link_constraints,
    )
    _add_model_stats(metrics, stats)
    metrics.model_build_time_s += build_elapsed
    metrics.calls += 1

    solve_start = perf_counter()
    branches_before = metrics.branches
    conflicts_before = metrics.conflicts
    first_solver = _new_solver(cp_model, config, config.time_limit_s)
    first_status = first_solver.Solve(model)
    first_status_name = first_solver.StatusName(first_status)
    _record_solver_stats(metrics, first_status_name, first_solver)
    solve_elapsed = perf_counter() - solve_start
    if first_status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        metrics.solve_time_s += solve_elapsed
        _record_stop(metrics, first_status_name, first_solver, config)
        return _finish_result(
            config,
            metrics,
            (),
            None,
            before_key,
            stats,
            build_elapsed,
            solve_elapsed,
            branches=metrics.branches - branches_before,
            conflicts=metrics.conflicts - conflicts_before,
            stop_reason=_stop_reason(first_status_name, first_solver, config),
            solver_status=first_status_name,
            objective_bound_m2=None,
        )

    best_coverage = int(round(first_solver.ObjectiveValue()))
    selected_ids = _selected_ids(pool, selected_vars, first_solver)
    best_status_name = first_status_name
    best_stop_reason = _stop_reason(first_status_name, first_solver, config)
    objective_bound_m2 = float(first_solver.BestObjectiveBound())

    remaining_s = config.time_limit_s - solve_elapsed
    if remaining_s > 1.0e-6:
        model.Add(coverage_expr == best_coverage)
        model.Maximize(_tie_break_objective(pool, selected_vars))
        stats = _model_stats(
            model,
            candidate_variables=len(selected_vars),
            sample_coverage_variables=len(sample_vars),
            transition_conflict_constraints=transition_conflict_constraints,
            anchor_conflict_constraints=anchor_conflict_constraints,
            coverage_link_constraints=coverage_link_constraints + 1,
        )
        metrics.model_constraints += 1
        metrics.coverage_link_constraints += 1
        second_solver = _new_solver(cp_model, config, remaining_s)
        second_status = second_solver.Solve(model)
        second_status_name = second_solver.StatusName(second_status)
        _record_solver_stats(metrics, second_status_name, second_solver)
        solve_elapsed = perf_counter() - solve_start
        if second_status in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
            selected_ids = _selected_ids(pool, selected_vars, second_solver)
            best_status_name = second_status_name
            best_stop_reason = _stop_reason(second_status_name, second_solver, config)
        else:
            _record_stop(metrics, second_status_name, second_solver, config)

    metrics.solve_time_s += solve_elapsed
    selected = tuple(candidate for candidate in pool if candidate.candidate_id in selected_ids)
    schedule = kept + list(selected)
    key = _objective_key(case, schedule, coverage_index) if _schedule_valid(case, schedule) else None
    stop_reason = best_stop_reason
    if key is None:
        stop_reason = "infeasible"
    return _finish_result(
        config,
        metrics,
        selected,
        key,
        before_key,
        stats,
        build_elapsed,
        solve_elapsed,
        branches=metrics.branches - branches_before,
        conflicts=metrics.conflicts - conflicts_before,
        stop_reason=stop_reason,
        solver_status=best_status_name,
        objective_bound_m2=objective_bound_m2,
    )


def _finish_result(
    config: CPRepairConfig,
    metrics: CPMetrics,
    best_subset: tuple[Candidate, ...],
    best_key: tuple[Any, ...] | None,
    before_key: tuple[Any, ...],
    stats: _ModelStats,
    build_elapsed: float,
    solve_elapsed: float,
    *,
    branches: int,
    conflicts: int,
    stop_reason: str,
    solver_status: str | None,
    objective_bound_m2: float | None,
) -> CPRepairResult:
    feasible = best_key is not None
    improving = feasible and _objective_key_strictly_better(
        best_key,
        before_key,
        min_improvement_weight_m2=config.min_improvement_weight_m2,
    )
    if feasible:
        metrics.feasible_solutions += 1
    if solver_status == "OPTIMAL":
        metrics.optimal_solutions += 1
    if improving:
        metrics.improving_solutions += 1
    if not feasible and stop_reason == "infeasible":
        metrics.infeasible_stops += 1
    return CPRepairResult(
        attempted=True,
        backend=config.backend,
        selected_candidate_ids=tuple(candidate.candidate_id for candidate in best_subset),
        feasible=feasible,
        improving=improving,
        stop_reason=stop_reason if feasible else "infeasible",
        solver_status=solver_status,
        objective_key=best_key,
        coverage_objective_m2=0.0 if best_key is None else float(best_key[1]),
        objective_bound_m2=objective_bound_m2,
        model_bool_variables=stats.model_bool_variables,
        model_constraints=stats.model_constraints,
        candidate_variables=stats.candidate_variables,
        sample_coverage_variables=stats.sample_coverage_variables,
        transition_conflict_constraints=stats.transition_conflict_constraints,
        anchor_conflict_constraints=stats.anchor_conflict_constraints,
        coverage_link_constraints=stats.coverage_link_constraints,
        branches=branches,
        conflicts=conflicts,
        model_build_time_s=build_elapsed,
        solve_time_s=solve_elapsed,
    )


def _not_attempted(config: CPRepairConfig, reason: str) -> CPRepairResult:
    return CPRepairResult(
        attempted=False,
        backend=config.backend,
        selected_candidate_ids=(),
        feasible=False,
        improving=False,
        stop_reason=reason,
        solver_status=None,
        objective_key=None,
        coverage_objective_m2=0.0,
        objective_bound_m2=None,
        model_bool_variables=0,
        model_constraints=0,
        candidate_variables=0,
        sample_coverage_variables=0,
        transition_conflict_constraints=0,
        anchor_conflict_constraints=0,
        coverage_link_constraints=0,
        branches=0,
        conflicts=0,
        model_build_time_s=0.0,
        solve_time_s=0.0,
    )


def _load_cp_sat_backend():
    try:
        import ortools
        from ortools.sat.python import cp_model
    except ImportError as exc:  # pragma: no cover - depends on environment state
        raise RuntimeError(
            "OR-Tools CP-SAT backend is not installed; run solvers/regional_coverage/cp_local_search/setup.sh"
        ) from exc
    return cp_model, str(getattr(ortools, "__version__", "unknown"))


def _add_pool_transition_constraints(case, model, pool, selected_vars) -> int:
    count = 0
    for left_index, left in enumerate(pool):
        for right in pool[left_index + 1:]:
            if left.satellite_id != right.satellite_id:
                continue
            if _pair_feasible(case, left, right):
                continue
            model.Add(selected_vars[left.candidate_id] + selected_vars[right.candidate_id] <= 1)
            count += 1
    return count


def _add_anchor_constraints(case, model, kept, pool, selected_vars) -> int:
    count = 0
    for candidate in pool:
        for anchor in kept:
            if candidate.satellite_id != anchor.satellite_id:
                continue
            if _pair_feasible(case, candidate, anchor):
                continue
            model.Add(selected_vars[candidate.candidate_id] == 0)
            count += 1
            break
    return count


def _add_coverage_objective(model, kept, pool, selected_vars, coverage_index):
    already_covered = _covered_sample_ids(kept)
    sample_to_candidate_ids: dict[str, list[str]] = {}
    for candidate in pool:
        for sample_id in candidate.coverage_sample_ids:
            if sample_id in already_covered:
                continue
            sample_to_candidate_ids.setdefault(sample_id, []).append(candidate.candidate_id)

    sample_vars = {
        sample_id: model.NewBoolVar(_safe_var_name(f"cov_{sample_id}"))
        for sample_id in sorted(sample_to_candidate_ids)
    }
    constraints = 0
    weighted_terms = []
    for sample_id, var in sample_vars.items():
        covering = [selected_vars[cid] for cid in sorted(sample_to_candidate_ids[sample_id])]
        model.Add(var <= sum(covering))
        constraints += 1
        for selected_var in covering:
            model.Add(var >= selected_var)
            constraints += 1
        weighted_terms.append(_weight_int(coverage_index.sample_weight_by_id.get(sample_id, 0.0)) * var)
    return sum(weighted_terms), sample_vars, constraints


def _new_solver(cp_model, config: CPRepairConfig, time_limit_s: float):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(1.0e-6, float(time_limit_s))
    solver.parameters.max_number_of_conflicts = int(config.max_conflicts)
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.log_search_progress = False
    return solver


def _selected_ids(pool: list[Candidate], selected_vars, solver) -> set[str]:
    return {
        candidate.candidate_id
        for candidate in pool
        if solver.BooleanValue(selected_vars[candidate.candidate_id])
    }


def _tie_break_objective(pool: list[Candidate], selected_vars):
    max_rank_sum = max(1, len(pool) * (len(pool) + 1))
    max_actions = max(1, len(pool) + 1)
    energy_weight = max_rank_sum * max_actions
    action_weight = max_rank_sum
    terms = []
    for rank, candidate in enumerate(pool, start=1):
        penalty = (
            _energy_int(candidate.estimated_energy_wh) * energy_weight
            + action_weight
            + rank
        )
        terms.append(-penalty * selected_vars[candidate.candidate_id])
    return sum(terms)


def _model_stats(
    model,
    *,
    candidate_variables: int,
    sample_coverage_variables: int,
    transition_conflict_constraints: int,
    anchor_conflict_constraints: int,
    coverage_link_constraints: int,
) -> _ModelStats:
    proto = model.Proto()
    return _ModelStats(
        model_bool_variables=len(proto.variables),
        model_constraints=len(proto.constraints),
        candidate_variables=candidate_variables,
        sample_coverage_variables=sample_coverage_variables,
        transition_conflict_constraints=transition_conflict_constraints,
        anchor_conflict_constraints=anchor_conflict_constraints,
        coverage_link_constraints=coverage_link_constraints,
    )


def _add_model_stats(metrics: CPMetrics, stats: _ModelStats) -> None:
    metrics.model_bool_variables += stats.model_bool_variables
    metrics.model_constraints += stats.model_constraints
    metrics.candidate_variables += stats.candidate_variables
    metrics.sample_coverage_variables += stats.sample_coverage_variables
    metrics.transition_conflict_constraints += stats.transition_conflict_constraints
    metrics.anchor_conflict_constraints += stats.anchor_conflict_constraints
    metrics.coverage_link_constraints += stats.coverage_link_constraints


def _record_solver_stats(metrics: CPMetrics, status_name: str, solver) -> None:
    metrics.status_counts[status_name] = metrics.status_counts.get(status_name, 0) + 1
    metrics.branches += int(solver.NumBranches())
    metrics.conflicts += int(solver.NumConflicts())


def _record_stop(metrics: CPMetrics, status_name: str, solver, config: CPRepairConfig) -> None:
    reason = _stop_reason(status_name, solver, config)
    if reason == "time_limit":
        metrics.timeout_stops += 1
    elif reason == "conflict_limit":
        metrics.conflict_limit_stops += 1
    elif reason == "infeasible":
        metrics.infeasible_stops += 1
    elif reason == "unknown":
        metrics.unknown_stops += 1


def _stop_reason(status_name: str, solver, config: CPRepairConfig) -> str:
    if status_name == "OPTIMAL":
        return "optimal"
    if status_name == "INFEASIBLE":
        return "infeasible"
    if int(solver.NumConflicts()) >= int(config.max_conflicts):
        return "conflict_limit"
    if status_name == "FEASIBLE":
        return "time_limit"
    return "unknown"


def _objective_key_strictly_better(
    candidate_key: tuple[Any, ...] | None,
    before_key: tuple[Any, ...],
    *,
    min_improvement_weight_m2: float,
) -> bool:
    if candidate_key is None:
        return False
    if candidate_key[0] != before_key[0]:
        return candidate_key[0] > before_key[0]
    coverage_delta = float(candidate_key[1]) - float(before_key[1])
    if coverage_delta > min_improvement_weight_m2:
        return True
    if abs(coverage_delta) > min_improvement_weight_m2:
        return False
    return candidate_key[2:] > before_key[2:]


def _schedule_valid(case: RegionalCoverageCase, candidates: Iterable[Candidate]) -> bool:
    try:
        state = create_empty_state(case)
        for candidate in sorted(candidates, key=_candidate_key):
            result = insert_candidate(case, state.sequences[candidate.satellite_id], candidate)
            if not result.success:
                return False
        return all(is_consistent(case, sequence)[0] for sequence in state.sequences.values())
    except (KeyError, ValueError):
        return False


def _objective_key(
    case: RegionalCoverageCase,
    candidates: Iterable[Candidate],
    coverage_index: CoverageIndex,
) -> tuple[Any, ...]:
    schedule = list(candidates)
    covered = _covered_sample_ids(schedule)
    return (
        1,
        coverage_index.total_weight(covered),
        -sum(candidate.estimated_energy_wh for candidate in schedule),
        -_slew_burden_s(case, schedule),
        -len(schedule),
    )


def _pair_feasible(case: RegionalCoverageCase, left: Candidate, right: Candidate) -> bool:
    if left.satellite_id != right.satellite_id:
        return True
    satellite = case.satellites[left.satellite_id]
    if left.end_offset_s <= right.start_offset_s:
        return transition_result(left, right, satellite=satellite).feasible
    if right.end_offset_s <= left.start_offset_s:
        return transition_result(right, left, satellite=satellite).feasible
    return False


def _covered_sample_ids(candidates: Iterable[Candidate]) -> set[str]:
    covered: set[str] = set()
    for candidate in candidates:
        covered.update(candidate.coverage_sample_ids)
    return covered


def _slew_burden_s(case: RegionalCoverageCase, candidates: list[Candidate]) -> float:
    by_satellite: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        by_satellite.setdefault(candidate.satellite_id, []).append(candidate)
    burden = 0.0
    for satellite_id, items in by_satellite.items():
        satellite = case.satellites[satellite_id]
        ordered = sorted(items, key=_candidate_key)
        for previous, current in zip(ordered, ordered[1:]):
            burden += transition_result(previous, current, satellite=satellite).required_gap_s
    return burden


def _candidate_key(candidate: Candidate) -> tuple[int, int, str]:
    return (candidate.start_offset_s, candidate.end_offset_s, candidate.candidate_id)


def _safe_var_name(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)


def _weight_int(value: float) -> int:
    return max(0, int(round(float(value))))


def _energy_int(value: float) -> int:
    return max(0, int(round(float(value) * 1_000.0)))


def _positive_int(value: Any, field: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _non_negative_int(value: Any, field: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative")
    return parsed


def _positive_float(value: Any, field: str) -> float:
    parsed = float(value)
    if parsed <= 0.0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _non_negative_float(value: Any, field: str) -> float:
    parsed = float(value)
    if parsed < 0.0:
        raise ValueError(f"{field} must be non-negative")
    return parsed
