"""Connected-component local search for AEOSSP greedy-LNS solver."""

from __future__ import annotations

import random
import time
from bisect import bisect_left
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


@dataclass(frozen=True, slots=True)
class LocalSearchConfig:
    max_local_search_iterations: int = 1000
    max_local_search_time_s: float | None = None
    restart_count: int = 0
    random_seed: int | None = None
    stochastic_ordering: bool = False

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "LocalSearchConfig":
        payload = payload or {}
        return cls(
            max_local_search_iterations=max(0, int(payload.get("max_local_search_iterations", 1000))),
            max_local_search_time_s=_optional_positive_float(payload.get("max_local_search_time_s")),
            restart_count=max(0, int(payload.get("restart_count", 0))),
            random_seed=_optional_int(payload.get("random_seed")),
            stochastic_ordering=bool(payload.get("stochastic_ordering", False)),
        )

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

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def _recompute_component(
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

    # 1. Remove currently selected candidates in this component
    selected_in_component = [
        scheduled_tasks[c.task_id]
        for c in component.candidates
        if c.task_id in scheduled_tasks
        and scheduled_tasks[c.task_id].candidate_id == c.candidate_id
    ]

    for c in selected_in_component:
        by_satellite[satellite_id].remove(c)
        del scheduled_tasks[c.task_id]

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
            by_satellite[satellite_id],
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


def _flatten_schedule(by_satellite: dict[str, list[Candidate]]) -> list[Candidate]:
    return [
        candidate
        for satellite_id in sorted(by_satellite)
        for candidate in by_satellite[satellite_id]
    ]


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
) -> tuple[dict[str, list[Candidate]], dict[str, Candidate]]:
    """Randomly deselect a fraction of candidates and return new state."""
    by_satellite = {sid: list(schedule) for sid, schedule in by_satellite.items()}
    scheduled_tasks = dict(scheduled_tasks)

    all_selected = list(scheduled_tasks.values())
    to_remove = rng.sample(all_selected, max(1, int(len(all_selected) * fraction)))

    for candidate in to_remove:
        by_satellite[candidate.satellite_id].remove(candidate)
        del scheduled_tasks[candidate.task_id]

    return by_satellite, scheduled_tasks


def local_search(
    case: AeosspCase,
    all_candidates: list[Candidate],
    greedy_solution: list[Candidate],
    config: LocalSearchConfig | None = None,
) -> LocalSearchResult:
    """Improve a greedy solution via connected-component local search.

    Implements first-improving descent over per-satellite connected components
    with optional bounded restarts.  The paper's CP-SAT TSPTW fallback is
    omitted; greedy insertion is used exclusively within component moves.
    """
    config = config or LocalSearchConfig()
    stats = LocalSearchStats()
    stats.exact_subproblem_solver = "none"

    step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
    propagation = PropagationContext(case.satellites, step_s=step_s)
    vector_cache = TransitionVectorCache(case, propagation)

    # Build component index over all candidates
    component_index = build_component_index(case, all_candidates)
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
    rng = random.Random(config.random_seed)

    time_limit = config.max_local_search_time_s
    start_time = time.perf_counter()

    for restart in range(config.restart_count + 1):
        if restart > 0:
            by_satellite, scheduled_tasks = _perturb(
                best_by_satellite[0], best_by_satellite[1], rng
            )
            stats.restarts_executed += 1

        for iteration in range(config.max_local_search_iterations):
            stats.iterations += 1

            if time_limit is not None:
                if time.perf_counter() - start_time > time_limit:
                    stats.stop_reason = "time_limit"
                    break

            improved = False
            components = _ordered_components(
                component_index, config.stochastic_ordering, rng
            )

            for component in components:
                stats.moves_attempted += 1

                # Snapshot state before the move
                old_by_satellite, old_scheduled_tasks = _copy_state(
                    by_satellite, scheduled_tasks
                )

                new_weight, failures = _recompute_component(
                    case,
                    component,
                    by_satellite,
                    scheduled_tasks,
                    propagation,
                    vector_cache,
                )
                stats.insertion_failures_during_local_search += failures

                old_weight = sum(
                    old_scheduled_tasks[c.task_id].task_weight
                    for c in component.candidates
                    if c.task_id in old_scheduled_tasks
                    and old_scheduled_tasks[c.task_id].candidate_id == c.candidate_id
                )

                new_objective = _objective(scheduled_tasks)
                old_objective = _objective(old_scheduled_tasks)

                if new_objective > old_objective:
                    stats.moves_accepted += 1
                    improved = True
                    if new_objective > stats.best_objective:
                        stats.best_objective = new_objective
                        best_by_satellite = _copy_state(by_satellite, scheduled_tasks)
                    break  # first-improving
                else:
                    # Rollback
                    by_satellite, scheduled_tasks = old_by_satellite, old_scheduled_tasks

            if not improved:
                stats.stop_reason = "local_minimum"
                break

            if stats.stop_reason:
                break

        if stats.stop_reason == "time_limit":
            break

    if not stats.stop_reason:
        stats.stop_reason = "max_iterations"

    # Restore best incumbent
    by_satellite, scheduled_tasks = best_by_satellite
    stats.final_objective = _objective(scheduled_tasks)

    final_candidates = _flatten_schedule(by_satellite)
    return LocalSearchResult(candidates=final_candidates, stats=stats)
