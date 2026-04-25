"""Connected-component local search for AEOSSP greedy-LNS solver."""

from __future__ import annotations

import random
import time
from bisect import bisect_left
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

from .candidates import Candidate
from .case_io import AeosspCase
from .components import Component, ComponentIndex, build_component_index
from .geometry import PropagationContext, initial_slew_feasible
from .insertion import _insertion_position
from .transition import TransitionVectorCache, transition_result
from .validation import BatteryGuardConfig, evaluate_battery_guard


@dataclass(frozen=True, slots=True)
class LocalSearchConfig:
    max_local_search_iterations: int = 1000
    max_local_search_time_s: float | None = None
    restart_count: int = 0
    random_seed: int | None = None
    stochastic_ordering: bool = False
    local_search_workers: int = 1
    enable_exact_reinsertion: bool = False
    max_exact_component_size: int = 8
    exact_subproblem_timeout_s: float | None = 0.05

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "LocalSearchConfig":
        payload = payload or {}
        return cls(
            max_local_search_iterations=max(0, int(payload.get("max_local_search_iterations", 1000))),
            max_local_search_time_s=_optional_positive_float(payload.get("max_local_search_time_s")),
            restart_count=max(0, int(payload.get("restart_count", 0))),
            random_seed=_optional_int(payload.get("random_seed")),
            stochastic_ordering=bool(payload.get("stochastic_ordering", False)),
            local_search_workers=_positive_int(payload.get("local_search_workers", 1)),
            enable_exact_reinsertion=bool(payload.get("enable_exact_reinsertion", False)),
            max_exact_component_size=max(0, int(payload.get("max_exact_component_size", 8))),
            exact_subproblem_timeout_s=_optional_positive_float(
                payload.get("exact_subproblem_timeout_s", 0.05)
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LocalSearchStartStats:
    start_index: int
    is_restart: bool
    seed: int | None
    time_slice_s: float | None = None
    elapsed_s: float = 0.0
    initial_objective: float = 0.0
    best_objective: float = 0.0
    final_objective: float = 0.0
    iterations: int = 0
    moves_attempted: int = 0
    moves_accepted: int = 0
    perturbation_removals: int = 0
    insertion_failures: int = 0
    stop_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LocalSearchStats:
    greedy_objective: float = 0.0
    best_objective: float = 0.0
    final_objective: float = 0.0
    iterations: int = 0
    moves_attempted: int = 0
    moves_accepted: int = 0
    restarts_executed: int = 0
    stop_reason: str = ""
    component_count: int = 0
    largest_component_size: int = 0
    exact_subproblem_solver: str = "none"
    insertion_failures_during_local_search: int = 0
    run_policy: dict[str, Any] = field(default_factory=dict)
    exact_reinsertion: dict[str, Any] = field(default_factory=dict)
    battery_guard: dict[str, Any] = field(default_factory=dict)
    starts: list[LocalSearchStartStats] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["starts"] = [start.as_dict() for start in self.starts]
        return payload


@dataclass(slots=True)
class LocalSearchResult:
    candidates: list[Candidate]
    stats: LocalSearchStats

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidates_count": len(self.candidates),
            "stats": self.stats.as_dict(),
        }


def _optional_positive_float(value: Any) -> float | None:
    if value is None:
        return None
    f = float(value)
    if f <= 0:
        return None
    return f


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _positive_int(value: Any) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("local_search_workers must be a positive integer")
    return parsed


def _total_weight(candidates: list[Candidate]) -> float:
    return sum(c.task_weight for c in candidates)


def _by_satellite(candidates: list[Candidate]) -> dict[str, list[Candidate]]:
    result: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        result.setdefault(candidate.satellite_id, []).append(candidate)
    for satellite_id in result:
        result[satellite_id].sort(
            key=lambda item: (item.start_offset_s, item.end_offset_s, item.candidate_id)
        )
    return result


def _try_insert_into_satellite(
    case: AeosspCase,
    satellite_id: str,
    satellite_schedule: list[Candidate],
    candidate: Candidate,
    propagation: PropagationContext,
    vector_cache: TransitionVectorCache,
) -> bool:
    """Try to insert *candidate* into *satellite_schedule* while preserving
    ordering and feasibility.  Return True if inserted.
    """
    pos = _insertion_position(satellite_schedule, candidate)

    # overlap checks
    left = satellite_schedule[pos - 1] if pos > 0 else None
    right = satellite_schedule[pos] if pos < len(satellite_schedule) else None

    if left is not None and left.end_offset_s > candidate.start_offset_s:
        return False
    if right is not None and candidate.end_offset_s > right.start_offset_s:
        return False

    # transition checks
    if left is not None:
        result = transition_result(left, candidate, case=case, vector_cache=vector_cache)
        if not result.feasible:
            return False
    if right is not None:
        result = transition_result(candidate, right, case=case, vector_cache=vector_cache)
        if not result.feasible:
            return False

    # initial slew check (only if first on this satellite)
    if left is None:
        start_time = case.mission.horizon_start + timedelta(seconds=candidate.start_offset_s)
        if not initial_slew_feasible(
            mission=case.mission,
            satellite=case.satellites[satellite_id],
            task=case.tasks[candidate.task_id],
            propagation=propagation,
            start_time=start_time,
        ):
            return False

    satellite_schedule.insert(pos, candidate)
    return True


def _marginal_profit(
    candidate: Candidate,
    scheduled_tasks: dict[str, Candidate],
) -> float:
    """Marginal profit of selecting *candidate* given current schedule."""
    existing = scheduled_tasks.get(candidate.task_id)
    if existing is None:
        return candidate.task_weight
    if existing.candidate_id == candidate.candidate_id:
        return candidate.task_weight
    return candidate.task_weight - existing.task_weight


def _exact_reinsertion_stats(config: LocalSearchConfig) -> dict[str, Any]:
    return {
        "enabled": config.enable_exact_reinsertion,
        "solver": (
            "bounded_enumeration"
            if config.enable_exact_reinsertion
            else "none"
        ),
        "max_component_size": config.max_exact_component_size,
        "timeout_s": config.exact_subproblem_timeout_s,
        "components_considered": 0,
        "components_solved_exactly": 0,
        "components_skipped_oversized": 0,
        "components_timed_out": 0,
        "components_fell_back_to_greedy": 0,
        "subsets_evaluated": 0,
        "feasible_subsets": 0,
        "infeasible_subsets": 0,
    }


def _battery_guard_stats(config: BatteryGuardConfig) -> dict[str, Any]:
    return {
        "enabled": config.enable_battery_guardrails,
        "battery_guard_min_wh": config.battery_guard_min_wh,
        "checks": 0,
        "accepted_checks": 0,
        "rejected_moves": 0,
        "affected_satellites_checked": 0,
        "last_rejection": None,
    }


def _replace_state(
    target_by_satellite: dict[str, list[Candidate]],
    target_scheduled_tasks: dict[str, Candidate],
    source_by_satellite: dict[str, list[Candidate]],
    source_scheduled_tasks: dict[str, Candidate],
) -> None:
    target_by_satellite.clear()
    target_by_satellite.update(
        {sid: list(schedule) for sid, schedule in source_by_satellite.items()}
    )
    target_scheduled_tasks.clear()
    target_scheduled_tasks.update(source_scheduled_tasks)


def _remove_candidate_from_state(
    by_satellite: dict[str, list[Candidate]],
    scheduled_tasks: dict[str, Candidate],
    candidate: Candidate,
) -> None:
    schedule = by_satellite.get(candidate.satellite_id)
    if schedule is not None and candidate in schedule:
        schedule.remove(candidate)
    if scheduled_tasks.get(candidate.task_id) == candidate:
        del scheduled_tasks[candidate.task_id]


@dataclass(frozen=True, slots=True)
class _ExactReinsertionResult:
    solved: bool
    new_component_weight: float = 0.0
    subsets_evaluated: int = 0
    feasible_subsets: int = 0
    infeasible_subsets: int = 0
    timed_out: bool = False


def _try_exact_reinsert_component(
    case: AeosspCase,
    component: Component,
    by_satellite: dict[str, list[Candidate]],
    scheduled_tasks: dict[str, Candidate],
    propagation: PropagationContext,
    vector_cache: TransitionVectorCache,
    *,
    timeout_s: float | None,
) -> _ExactReinsertionResult:
    candidates = sorted(
        component.candidates,
        key=lambda c: (c.start_offset_s, c.end_offset_s, c.candidate_id),
    )
    best_by_satellite: dict[str, list[Candidate]] | None = None
    best_scheduled_tasks: dict[str, Candidate] | None = None
    best_objective = float("-inf")
    best_ids: tuple[str, ...] | None = None
    subsets_evaluated = 0
    feasible_subsets = 0
    infeasible_subsets = 0
    start_time = time.perf_counter()

    for mask in range(1 << len(candidates)):
        if timeout_s is not None and time.perf_counter() - start_time >= timeout_s:
            return _ExactReinsertionResult(
                solved=False,
                subsets_evaluated=subsets_evaluated,
                feasible_subsets=feasible_subsets,
                infeasible_subsets=infeasible_subsets,
                timed_out=True,
            )

        subsets_evaluated += 1
        selected = [
            candidate
            for index, candidate in enumerate(candidates)
            if mask & (1 << index)
        ]
        task_ids = [candidate.task_id for candidate in selected]
        if len(task_ids) != len(set(task_ids)):
            infeasible_subsets += 1
            continue

        trial_by_satellite, trial_scheduled_tasks = _copy_state(
            by_satellite, scheduled_tasks
        )
        feasible = True
        selected_weight = 0.0

        for candidate in selected:
            existing = trial_scheduled_tasks.get(candidate.task_id)
            if existing is not None and existing.candidate_id != candidate.candidate_id:
                _remove_candidate_from_state(
                    trial_by_satellite,
                    trial_scheduled_tasks,
                    existing,
                )

            inserted = _try_insert_into_satellite(
                case,
                component.satellite_id,
                trial_by_satellite.setdefault(component.satellite_id, []),
                candidate,
                propagation,
                vector_cache,
            )
            if not inserted:
                feasible = False
                break
            trial_scheduled_tasks[candidate.task_id] = candidate
            selected_weight += candidate.task_weight

        if not feasible:
            infeasible_subsets += 1
            continue

        feasible_subsets += 1
        objective = _objective(trial_scheduled_tasks)
        selected_ids = tuple(sorted(candidate.candidate_id for candidate in selected))
        if (
            objective > best_objective + 1.0e-9
            or (
                abs(objective - best_objective) <= 1.0e-9
                and (best_ids is None or selected_ids < best_ids)
            )
        ):
            best_objective = objective
            best_ids = selected_ids
            best_by_satellite = trial_by_satellite
            best_scheduled_tasks = trial_scheduled_tasks
            best_component_weight = selected_weight

    if best_by_satellite is None or best_scheduled_tasks is None:
        return _ExactReinsertionResult(
            solved=True,
            subsets_evaluated=subsets_evaluated,
            feasible_subsets=feasible_subsets,
            infeasible_subsets=infeasible_subsets,
        )

    _replace_state(
        by_satellite,
        scheduled_tasks,
        best_by_satellite,
        best_scheduled_tasks,
    )
    return _ExactReinsertionResult(
        solved=True,
        new_component_weight=best_component_weight,
        subsets_evaluated=subsets_evaluated,
        feasible_subsets=feasible_subsets,
        infeasible_subsets=infeasible_subsets,
    )


def _greedy_reinsert_component(
    case: AeosspCase,
    component: Component,
    by_satellite: dict[str, list[Candidate]],
    scheduled_tasks: dict[str, Candidate],
    propagation: PropagationContext,
    vector_cache: TransitionVectorCache,
) -> tuple[float, int]:
    """Recompute one connected component in-place.

    Mutates *by_satellite* and *scheduled_tasks*.  Returns
    (new_component_weight, insertion_failures).
    """
    satellite_id = component.satellite_id
    satellite_schedule = by_satellite.setdefault(satellite_id, [])

    # 2. Compute marginal profit for every candidate in the component
    component_candidates = list(component.candidates)
    component_candidates.sort(
        key=lambda c: (
            -_marginal_profit(c, scheduled_tasks),
            -c.task_weight,
            c.start_offset_s,
            c.candidate_id,
        )
    )

    # 3. Greedy insert in marginal-profit order, stopping at first non-positive
    new_component_weight = 0.0
    insertion_failures = 0

    for candidate in component_candidates:
        mp = _marginal_profit(candidate, scheduled_tasks)
        if mp <= 0:
            break
        inserted = _try_insert_into_satellite(
            case,
            satellite_id,
            satellite_schedule,
            candidate,
            propagation,
            vector_cache,
        )
        if inserted:
            # If this task was selected by an alternative outside the component,
            # remove that alternative now.
            existing = scheduled_tasks.get(candidate.task_id)
            if existing is not None and existing.candidate_id != candidate.candidate_id:
                by_satellite[existing.satellite_id].remove(existing)
            scheduled_tasks[candidate.task_id] = candidate
            new_component_weight += candidate.task_weight
        else:
            insertion_failures += 1

    return new_component_weight, insertion_failures


def _recompute_component(
    case: AeosspCase,
    component: Component,
    by_satellite: dict[str, list[Candidate]],
    scheduled_tasks: dict[str, Candidate],
    propagation: PropagationContext,
    vector_cache: TransitionVectorCache,
    *,
    exact_config: LocalSearchConfig | None = None,
    exact_stats: dict[str, Any] | None = None,
) -> tuple[float, int]:
    """Recompute one connected component in-place.

    Mutates *by_satellite* and *scheduled_tasks*.  Returns
    (new_component_weight, insertion_failures).
    """
    satellite_schedule = by_satellite.setdefault(component.satellite_id, [])

    selected_in_component = [
        scheduled_tasks[c.task_id]
        for c in component.candidates
        if c.task_id in scheduled_tasks
        and scheduled_tasks[c.task_id].candidate_id == c.candidate_id
    ]

    for candidate in selected_in_component:
        satellite_schedule.remove(candidate)
        del scheduled_tasks[candidate.task_id]

    if exact_config is not None and exact_config.enable_exact_reinsertion:
        if exact_stats is not None:
            exact_stats["components_considered"] += 1

        if component.size <= exact_config.max_exact_component_size:
            exact_result = _try_exact_reinsert_component(
                case,
                component,
                by_satellite,
                scheduled_tasks,
                propagation,
                vector_cache,
                timeout_s=exact_config.exact_subproblem_timeout_s,
            )
            if exact_stats is not None:
                exact_stats["subsets_evaluated"] += exact_result.subsets_evaluated
                exact_stats["feasible_subsets"] += exact_result.feasible_subsets
                exact_stats["infeasible_subsets"] += exact_result.infeasible_subsets

            if exact_result.solved:
                if exact_stats is not None:
                    exact_stats["components_solved_exactly"] += 1
                return exact_result.new_component_weight, 0

            if exact_stats is not None and exact_result.timed_out:
                exact_stats["components_timed_out"] += 1
        elif exact_stats is not None:
            exact_stats["components_skipped_oversized"] += 1

        if exact_stats is not None:
            exact_stats["components_fell_back_to_greedy"] += 1

    return _greedy_reinsert_component(
        case,
        component,
        by_satellite,
        scheduled_tasks,
        propagation,
        vector_cache,
    )


def _flatten_schedule(by_satellite: dict[str, list[Candidate]]) -> list[Candidate]:
    return [
        candidate
        for satellite_id in sorted(by_satellite)
        for candidate in by_satellite[satellite_id]
    ]


def _changed_satellite_ids(
    before: dict[str, list[Candidate]],
    after: dict[str, list[Candidate]],
) -> set[str]:
    changed: set[str] = set()
    for satellite_id in set(before) | set(after):
        before_ids = tuple(candidate.candidate_id for candidate in before.get(satellite_id, []))
        after_ids = tuple(candidate.candidate_id for candidate in after.get(satellite_id, []))
        if before_ids != after_ids:
            changed.add(satellite_id)
    return changed


def _copy_state(
    by_satellite: dict[str, list[Candidate]],
    scheduled_tasks: dict[str, Candidate],
) -> tuple[dict[str, list[Candidate]], dict[str, Candidate]]:
    return (
        {sid: list(schedule) for sid, schedule in by_satellite.items()},
        dict(scheduled_tasks),
    )


def _objective(scheduled_tasks: dict[str, Candidate]) -> float:
    return sum(c.task_weight for c in scheduled_tasks.values())


def _ordered_components(
    component_index: ComponentIndex,
    stochastic: bool,
    rng: random.Random,
) -> list[Component]:
    components = list(component_index.components)
    if stochastic:
        rng.shuffle(components)
    return components


def _perturb(
    by_satellite: dict[str, list[Candidate]],
    scheduled_tasks: dict[str, Candidate],
    rng: random.Random,
    fraction: float = 0.05,
) -> tuple[dict[str, list[Candidate]], dict[str, Candidate], int]:
    """Randomly deselect a fraction of candidates and return new state."""
    by_satellite = {sid: list(schedule) for sid, schedule in by_satellite.items()}
    scheduled_tasks = dict(scheduled_tasks)

    all_selected = list(scheduled_tasks.values())
    if not all_selected:
        return by_satellite, scheduled_tasks, 0
    to_remove = rng.sample(all_selected, max(1, int(len(all_selected) * fraction)))

    for candidate in to_remove:
        by_satellite[candidate.satellite_id].remove(candidate)
        del scheduled_tasks[candidate.task_id]

    return by_satellite, scheduled_tasks, len(to_remove)


def _start_seeds(config: LocalSearchConfig, start_count: int) -> list[int | None]:
    if config.random_seed is None:
        return [None for _ in range(start_count)]
    rng = random.Random(config.random_seed)
    return [rng.randrange(0, 2**63) for _ in range(start_count)]


@dataclass(slots=True)
class _SearchStartResult:
    start_stats: LocalSearchStartStats
    by_satellite: dict[str, list[Candidate]]
    scheduled_tasks: dict[str, Candidate]
    exact_reinsertion: dict[str, Any]
    battery_guard: dict[str, Any]
    iterations: int = 0
    moves_attempted: int = 0
    moves_accepted: int = 0
    insertion_failures: int = 0


def _build_runtime_helpers(
    case: AeosspCase,
    propagation: PropagationContext | None,
    vector_cache: TransitionVectorCache | None,
) -> tuple[PropagationContext, TransitionVectorCache]:
    if propagation is None:
        step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
        propagation = PropagationContext(case.satellites, step_s=step_s)
    if vector_cache is None:
        vector_cache = TransitionVectorCache(case, propagation)
    return propagation, vector_cache


def _run_search_start(
    case: AeosspCase,
    component_index: ComponentIndex,
    base_by_satellite: dict[str, list[Candidate]],
    base_scheduled_tasks: dict[str, Candidate],
    config: LocalSearchConfig,
    battery_guard_config: BatteryGuardConfig,
    *,
    start_index: int,
    seed: int | None,
    time_slice_s: float | None,
    propagation: PropagationContext | None = None,
    vector_cache: TransitionVectorCache | None = None,
) -> _SearchStartResult:
    propagation, vector_cache = _build_runtime_helpers(case, propagation, vector_cache)
    exact_stats = _exact_reinsertion_stats(config)
    battery_stats = _battery_guard_stats(battery_guard_config)
    start_rng = random.Random(seed)
    is_restart = start_index > 0
    start_begin = time.perf_counter()

    if is_restart:
        by_satellite, scheduled_tasks, perturbation_removals = _perturb(
            base_by_satellite, base_scheduled_tasks, start_rng
        )
    else:
        by_satellite, scheduled_tasks = _copy_state(
            base_by_satellite, base_scheduled_tasks
        )
        perturbation_removals = 0

    initial_objective = _objective(scheduled_tasks)
    start_stats = LocalSearchStartStats(
        start_index=start_index,
        is_restart=is_restart,
        seed=seed,
        time_slice_s=time_slice_s,
        initial_objective=initial_objective,
        best_objective=initial_objective,
        final_objective=initial_objective,
        perturbation_removals=perturbation_removals,
    )
    totals = {
        "iterations": 0,
        "moves_attempted": 0,
        "moves_accepted": 0,
        "insertion_failures": 0,
    }

    for _ in range(config.max_local_search_iterations):
        if time_slice_s is not None and time.perf_counter() - start_begin >= time_slice_s:
            start_stats.stop_reason = "time_slice"
            break

        totals["iterations"] += 1
        start_stats.iterations += 1

        improved = False
        components = _ordered_components(
            component_index, config.stochastic_ordering, start_rng
        )

        for component in components:
            totals["moves_attempted"] += 1
            start_stats.moves_attempted += 1

            old_by_satellite, old_scheduled_tasks = _copy_state(
                by_satellite, scheduled_tasks
            )

            _, failures = _recompute_component(
                case,
                component,
                by_satellite,
                scheduled_tasks,
                propagation,
                vector_cache,
                exact_config=config,
                exact_stats=exact_stats,
            )
            totals["insertion_failures"] += failures
            start_stats.insertion_failures += failures

            new_objective = _objective(scheduled_tasks)
            old_objective = _objective(old_scheduled_tasks)

            if new_objective > old_objective:
                if battery_guard_config.enable_battery_guardrails:
                    guard_decision = evaluate_battery_guard(
                        case,
                        _flatten_schedule(old_by_satellite),
                        _flatten_schedule(by_satellite),
                        affected_satellite_ids=_changed_satellite_ids(
                            old_by_satellite, by_satellite
                        ),
                        config=battery_guard_config,
                        propagation=propagation,
                        vector_cache=vector_cache,
                    )
                    battery_stats["checks"] += 1
                    battery_stats["affected_satellites_checked"] += len(
                        guard_decision.affected_satellites
                    )
                    if not guard_decision.allowed:
                        battery_stats["rejected_moves"] += 1
                        battery_stats["last_rejection"] = guard_decision.as_dict()
                        by_satellite, scheduled_tasks = (
                            old_by_satellite,
                            old_scheduled_tasks,
                        )
                        continue
                    battery_stats["accepted_checks"] += 1

                totals["moves_accepted"] += 1
                start_stats.moves_accepted += 1
                improved = True
                if new_objective > start_stats.best_objective:
                    start_stats.best_objective = new_objective
                break

            by_satellite, scheduled_tasks = old_by_satellite, old_scheduled_tasks

        if not improved:
            start_stats.stop_reason = "local_minimum"
            break

        if start_stats.stop_reason:
            break

    if not start_stats.stop_reason:
        start_stats.stop_reason = "max_iterations"
    start_stats.final_objective = _objective(scheduled_tasks)
    start_stats.elapsed_s = time.perf_counter() - start_begin
    return _SearchStartResult(
        start_stats=start_stats,
        by_satellite=by_satellite,
        scheduled_tasks=scheduled_tasks,
        exact_reinsertion=exact_stats,
        battery_guard=battery_stats,
        iterations=totals["iterations"],
        moves_attempted=totals["moves_attempted"],
        moves_accepted=totals["moves_accepted"],
        insertion_failures=totals["insertion_failures"],
    )


_ADDITIVE_START_STAT_KEYS = {
    "accepted_checks",
    "affected_satellites_checked",
    "checks",
    "components_considered",
    "components_fell_back_to_greedy",
    "components_skipped_oversized",
    "components_solved_exactly",
    "components_timed_out",
    "feasible_subsets",
    "infeasible_subsets",
    "rejected_moves",
    "subsets_evaluated",
}


def _merge_numeric_stats(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, bool):
            continue
        if key in _ADDITIVE_START_STAT_KEYS and isinstance(value, int | float):
            target[key] = target.get(key, 0) + value
    if source.get("last_rejection") is not None:
        target["last_rejection"] = source["last_rejection"]


def _apply_start_result(stats: LocalSearchStats, result: _SearchStartResult) -> None:
    stats.starts.append(result.start_stats)
    stats.iterations += result.iterations
    stats.moves_attempted += result.moves_attempted
    stats.moves_accepted += result.moves_accepted
    stats.insertion_failures_during_local_search += result.insertion_failures
    if result.start_stats.is_restart:
        stats.restarts_executed += 1
    _merge_numeric_stats(stats.exact_reinsertion, result.exact_reinsertion)
    _merge_numeric_stats(stats.battery_guard, result.battery_guard)


def _better_than_incumbent(
    result: _SearchStartResult,
    incumbent: tuple[dict[str, list[Candidate]], dict[str, Candidate]],
) -> bool:
    return _objective(result.scheduled_tasks) > _objective(incumbent[1]) + 1.0e-9


def _run_parallel_restart_waves(
    *,
    case: AeosspCase,
    component_index: ComponentIndex,
    initial_by_satellite: dict[str, list[Candidate]],
    initial_scheduled_tasks: dict[str, Candidate],
    config: LocalSearchConfig,
    battery_guard_config: BatteryGuardConfig,
    seeds: list[int | None],
    time_limit: float | None,
    propagation: PropagationContext,
    vector_cache: TransitionVectorCache,
    stats: LocalSearchStats,
) -> tuple[dict[str, list[Candidate]], dict[str, Candidate]]:
    start_count = len(seeds)
    per_start_time_slice_s = None if time_limit is None else time_limit / float(start_count)
    effective_workers = min(config.local_search_workers, max(1, start_count - 1))
    stats.run_policy["effective_local_search_workers"] = effective_workers
    stats.run_policy["parallel_restart_policy"] = "process_pool_restart_waves"
    stats.run_policy["per_start_time_slice_s"] = per_start_time_slice_s

    best_by_satellite, best_scheduled_tasks = _copy_state(
        initial_by_satellite, initial_scheduled_tasks
    )

    first_result = _run_search_start(
        case,
        component_index,
        best_by_satellite,
        best_scheduled_tasks,
        config,
        battery_guard_config,
        start_index=0,
        seed=seeds[0],
        time_slice_s=per_start_time_slice_s,
        propagation=propagation,
        vector_cache=vector_cache,
    )
    _apply_start_result(stats, first_result)
    stats.run_policy["attempted_start_count"] = len(stats.starts)
    stats.run_policy["completed_start_count"] = len(stats.starts)
    if _better_than_incumbent(first_result, (best_by_satellite, best_scheduled_tasks)):
        best_by_satellite, best_scheduled_tasks = _copy_state(
            first_result.by_satellite, first_result.scheduled_tasks
        )
        stats.best_objective = _objective(best_scheduled_tasks)

    pending_start_indices = list(range(1, start_count))
    with ProcessPoolExecutor(max_workers=effective_workers) as executor:
        for wave_offset in range(0, len(pending_start_indices), effective_workers):
            wave_indices = pending_start_indices[
                wave_offset : wave_offset + effective_workers
            ]
            base_by_satellite, base_scheduled_tasks = _copy_state(
                best_by_satellite, best_scheduled_tasks
            )
            futures = [
                executor.submit(
                    _run_search_start,
                    case,
                    component_index,
                    base_by_satellite,
                    base_scheduled_tasks,
                    config,
                    battery_guard_config,
                    start_index=start_index,
                    seed=seeds[start_index],
                    time_slice_s=per_start_time_slice_s,
                )
                for start_index in wave_indices
            ]
            for result in [future.result() for future in futures]:
                _apply_start_result(stats, result)
                stats.run_policy["attempted_start_count"] = len(stats.starts)
                stats.run_policy["completed_start_count"] = len(stats.starts)
                if _better_than_incumbent(
                    result, (best_by_satellite, best_scheduled_tasks)
                ):
                    best_by_satellite, best_scheduled_tasks = _copy_state(
                        result.by_satellite, result.scheduled_tasks
                    )
                    stats.best_objective = _objective(best_scheduled_tasks)

    stats.starts.sort(key=lambda item: item.start_index)
    if time_limit is not None and any(
        start.stop_reason in {"time_slice", "time_limit"} for start in stats.starts
    ):
        stats.stop_reason = "time_limit"
    elif stats.starts:
        stats.stop_reason = stats.starts[-1].stop_reason
    else:
        stats.stop_reason = "time_limit"
    return best_by_satellite, best_scheduled_tasks


def local_search(
    case: AeosspCase,
    all_candidates: list[Candidate],
    greedy_solution: list[Candidate],
    config: LocalSearchConfig | None = None,
    *,
    propagation: PropagationContext | None = None,
    vector_cache: TransitionVectorCache | None = None,
    battery_guard_config: BatteryGuardConfig | None = None,
) -> LocalSearchResult:
    """Improve a greedy solution via connected-component local search.

    Implements first-improving descent over per-satellite connected components
    with optional bounded restarts.  When enabled, small components are
    reinserted by bounded exact enumeration; otherwise the solver uses greedy
    marginal-profit reinsertion.
    """
    config = config or LocalSearchConfig()
    battery_guard_config = battery_guard_config or BatteryGuardConfig()
    stats = LocalSearchStats()
    stats.exact_subproblem_solver = (
        "bounded_enumeration"
        if config.enable_exact_reinsertion
        else "none"
    )
    stats.exact_reinsertion = _exact_reinsertion_stats(config)
    stats.battery_guard = _battery_guard_stats(battery_guard_config)

    if propagation is None:
        step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
        propagation = PropagationContext(case.satellites, step_s=step_s)
    if vector_cache is None:
        vector_cache = TransitionVectorCache(case, propagation)

    # Build component index over all candidates
    component_index = build_component_index(
        case,
        all_candidates,
        propagation=propagation,
        vector_cache=vector_cache,
    )
    stats.component_count = component_index.stats.component_count
    stats.largest_component_size = component_index.stats.largest_component_size

    # Initialize state from greedy solution
    by_satellite = _by_satellite(greedy_solution)
    scheduled_tasks: dict[str, Candidate] = {c.task_id: c for c in greedy_solution}

    greedy_objective = _objective(scheduled_tasks)
    stats.greedy_objective = greedy_objective
    stats.best_objective = greedy_objective
    stats.final_objective = greedy_objective

    best_by_satellite = _copy_state(by_satellite, scheduled_tasks)

    start_count = config.restart_count + 1
    seeds = _start_seeds(config, start_count)
    time_limit = config.max_local_search_time_s
    start_time = time.perf_counter()
    stats.run_policy = {
        "configured_start_count": start_count,
        "configured_restart_count": config.restart_count,
        "attempted_start_count": 0,
        "completed_start_count": 0,
        "stochastic_ordering": config.stochastic_ordering,
        "random_seed": config.random_seed,
        "seed_policy": "derived_from_random_seed" if config.random_seed is not None else "system_random",
        "start_seeds": seeds,
        "max_iterations_per_start": config.max_local_search_iterations,
        "max_local_search_time_s": time_limit,
        "fair_time_slicing": time_limit is not None and start_count > 1,
        "configured_local_search_workers": config.local_search_workers,
        "effective_local_search_workers": 1,
        "parallel_restart_policy": "sequential",
    }

    if config.local_search_workers > 1 and start_count > 1:
        best_by_satellite, scheduled_tasks = _run_parallel_restart_waves(
            case=case,
            component_index=component_index,
            initial_by_satellite=by_satellite,
            initial_scheduled_tasks=scheduled_tasks,
            config=config,
            battery_guard_config=battery_guard_config,
            seeds=seeds,
            time_limit=time_limit,
            propagation=propagation,
            vector_cache=vector_cache,
            stats=stats,
        )
        stats.final_objective = _objective(scheduled_tasks)
        final_candidates = _flatten_schedule(best_by_satellite)
        return LocalSearchResult(candidates=final_candidates, stats=stats)

    for start_index in range(start_count):
        now = time.perf_counter()
        time_slice_s = None
        if time_limit is not None:
            elapsed_total = now - start_time
            remaining_total = time_limit - elapsed_total
            if remaining_total <= 0.0:
                stats.stop_reason = "time_limit"
                break
            time_slice_s = remaining_total / float(start_count - start_index)

        result = _run_search_start(
            case,
            component_index,
            best_by_satellite[0],
            best_by_satellite[1],
            config,
            battery_guard_config,
            start_index=start_index,
            seed=seeds[start_index],
            time_slice_s=time_slice_s,
            propagation=propagation,
            vector_cache=vector_cache,
        )
        _apply_start_result(stats, result)
        stats.run_policy["attempted_start_count"] = len(stats.starts)
        stats.run_policy["completed_start_count"] = len(stats.starts)
        by_satellite, scheduled_tasks = result.by_satellite, result.scheduled_tasks
        start_stats = result.start_stats

        if _better_than_incumbent(result, best_by_satellite):
            stats.best_objective = _objective(result.scheduled_tasks)
            best_by_satellite = _copy_state(result.by_satellite, result.scheduled_tasks)

        if start_stats.stop_reason == "time_limit":
            stats.stop_reason = "time_limit"
            break

    if not stats.stop_reason:
        if any(start.stop_reason == "time_slice" for start in stats.starts):
            stats.stop_reason = "time_limit"
        elif stats.starts:
            stats.stop_reason = stats.starts[-1].stop_reason
        else:
            stats.stop_reason = "time_limit"

    # Restore best incumbent
    by_satellite, scheduled_tasks = best_by_satellite
    stats.final_objective = _objective(scheduled_tasks)

    final_candidates = _flatten_schedule(by_satellite)
    return LocalSearchResult(candidates=final_candidates, stats=stats)
