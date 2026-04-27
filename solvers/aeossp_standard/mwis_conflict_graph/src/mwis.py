"""Deterministic weighted independent-set selection with bounded refinement."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from itertools import combinations
import time
from typing import Any

from .backend import BackendResolution, parse_backend, resolve_backend
from .candidates import Candidate
from .graph import ConflictGraph, connected_components
from .reduction import ReductionResult, reduce_component


SELECTION_POLICIES = ("weight_end_degree", "weight_degree_end")


@dataclass(frozen=True, slots=True)
class MwisConfig:
    max_exact_component_size: int = 20
    selection_policy: str = "weight_degree_end"
    time_limit_s: float | None = None
    max_local_passes: int = 8
    population_size: int = 4
    recombination_rounds: int = 6
    backend: str = "internal_reduction"

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "MwisConfig":
        payload = payload or {}
        selection_policy = str(payload.get("selection_policy", "weight_degree_end"))
        if selection_policy not in SELECTION_POLICIES:
            raise ValueError(
                "selection_policy must be one of: weight_end_degree, weight_degree_end"
            )
        time_limit_raw = payload.get("time_limit_s")
        time_limit_s = None if time_limit_raw in {None, ""} else float(time_limit_raw)
        if time_limit_s is not None and time_limit_s < 0.0:
            raise ValueError("time_limit_s must be null or non-negative")
        return cls(
            max_exact_component_size=max(0, int(payload.get("max_exact_component_size", 20))),
            selection_policy=selection_policy,
            time_limit_s=time_limit_s,
            max_local_passes=max(0, int(payload.get("max_local_passes", 8))),
            population_size=max(1, int(payload.get("population_size", 4))),
            recombination_rounds=max(0, int(payload.get("recombination_rounds", 6))),
            backend=parse_backend(payload.get("backend")),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ComponentSearchStats:
    component_index: int
    component_size: int
    reduced_component_size: int
    mode: str
    baseline_source: str
    incumbent_source: str
    baseline_weight: float
    baseline_count: int
    final_weight: float
    final_count: int
    initial_population_size: int
    local_improvement_count: int
    successful_two_swap_count: int
    recombination_attempt_count: int
    recombination_win_count: int
    elapsed_s: float
    time_limit_hit: bool
    stop_reason: str
    reduction_elapsed_s: float = 0.0
    included_by_reduction_count: int = 0
    removed_by_reduction_count: int = 0
    reduction_rule_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reduction_rule_counts"] = dict(sorted(self.reduction_rule_counts.items()))
        return payload


@dataclass(slots=True)
class MwisStats:
    selected_candidate_count: int
    selected_total_weight: float
    exact_component_count: int
    greedy_component_count: int
    refined_component_count: int
    independent_set_valid: bool
    selection_policy: str
    max_exact_component_size: int
    time_limit_s: float | None
    effective_time_limit_s: float | None
    deadline_source: str
    selection_started_after_deadline: bool
    max_local_passes: int
    population_size: int
    recombination_rounds: int
    search_elapsed_s: float
    time_limit_hit: bool
    search_stop_reason: str
    local_improvement_count: int
    successful_two_swap_count: int
    recombination_attempt_count: int
    recombination_win_count: int
    incumbent_source: str
    reduction_elapsed_s: float = 0.0
    requested_backend: str = "internal_reduction"
    backend: str = "internal_reduction"
    backend_available: bool = True
    backend_fallback_reason: str | None = None
    reduction_original_vertex_count: int = 0
    reduction_reduced_vertex_count: int = 0
    included_by_reduction_count: int = 0
    removed_by_reduction_count: int = 0
    reduction_rule_counts: dict[str, int] = field(default_factory=dict)
    component_search: list[ComponentSearchStats] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "selected_candidate_count": self.selected_candidate_count,
            "selected_total_weight": self.selected_total_weight,
            "exact_component_count": self.exact_component_count,
            "greedy_component_count": self.greedy_component_count,
            "refined_component_count": self.refined_component_count,
            "independent_set_valid": self.independent_set_valid,
            "selection_policy": self.selection_policy,
            "max_exact_component_size": self.max_exact_component_size,
            "time_limit_s": self.time_limit_s,
            "effective_time_limit_s": self.effective_time_limit_s,
            "deadline_source": self.deadline_source,
            "selection_started_after_deadline": self.selection_started_after_deadline,
            "max_local_passes": self.max_local_passes,
            "population_size": self.population_size,
            "recombination_rounds": self.recombination_rounds,
            "search_elapsed_s": self.search_elapsed_s,
            "time_limit_hit": self.time_limit_hit,
            "search_stop_reason": self.search_stop_reason,
            "local_improvement_count": self.local_improvement_count,
            "successful_two_swap_count": self.successful_two_swap_count,
            "recombination_attempt_count": self.recombination_attempt_count,
            "recombination_win_count": self.recombination_win_count,
            "incumbent_source": self.incumbent_source,
            "reduction_elapsed_s": self.reduction_elapsed_s,
            "requested_backend": self.requested_backend,
            "backend": self.backend,
            "backend_available": self.backend_available,
            "backend_fallback_reason": self.backend_fallback_reason,
            "reduction_original_vertex_count": self.reduction_original_vertex_count,
            "reduction_reduced_vertex_count": self.reduction_reduced_vertex_count,
            "included_by_reduction_count": self.included_by_reduction_count,
            "removed_by_reduction_count": self.removed_by_reduction_count,
            "reduction_rule_counts": dict(sorted(self.reduction_rule_counts.items())),
            "component_stop_reasons": dict(
                sorted(Counter(item.stop_reason for item in self.component_search).items())
            ),
            "component_search": self.component_search_status(),
        }

    def component_search_status(self) -> list[dict[str, Any]]:
        return [
            {
                "component_index": item.component_index,
                "component_size": item.component_size,
                "reduced_component_size": item.reduced_component_size,
                "mode": item.mode,
                "stop_reason": item.stop_reason,
                "time_limit_hit": item.time_limit_hit,
                "elapsed_s": item.elapsed_s,
                "reduction_elapsed_s": item.reduction_elapsed_s,
                "included_by_reduction_count": item.included_by_reduction_count,
                "removed_by_reduction_count": item.removed_by_reduction_count,
                "reduction_rule_counts": dict(sorted(item.reduction_rule_counts.items())),
            }
            for item in self.component_search
        ]

    def component_search_debug(self) -> list[dict[str, Any]]:
        return [item.as_dict() for item in self.component_search]


@dataclass(slots=True)
class LocalImproveStats:
    improvement_count: int = 0
    successful_two_swap_count: int = 0
    stop_reason: str = "converged"


@dataclass(slots=True)
class _PopulationEntry:
    selected: set[str]
    source: str


class _ExactDeadlineReached(Exception):
    """Raised internally when a bounded exact solve exhausts its deadline."""


def greedy_priority(candidate: Candidate, degree: int, *, policy: str) -> tuple[Any, ...]:
    if policy == "weight_end_degree":
        return (-candidate.task_weight, candidate.end_offset_s, degree, candidate.candidate_id)
    if policy == "weight_degree_end":
        return (-candidate.task_weight, degree, candidate.end_offset_s, candidate.candidate_id)
    raise ValueError(f"unsupported selection policy: {policy}")


def validate_independent_set(
    selected_candidate_ids: set[str],
    adjacency: dict[str, set[str]],
) -> bool:
    for candidate_id in selected_candidate_ids:
        if adjacency.get(candidate_id, set()) & selected_candidate_ids:
            return False
    return True


def _selected_key(selected: set[str], candidate_by_id: dict[str, Candidate]) -> tuple[Any, ...]:
    total_weight = sum(candidate_by_id[candidate_id].task_weight for candidate_id in selected)
    total_count = len(selected)
    total_completion = sum(candidate_by_id[candidate_id].end_offset_s for candidate_id in selected)
    return (
        round(total_weight, 12),
        total_count,
        -total_completion,
        tuple(sorted(selected)),
    )


def _is_better(
    candidate_set: set[str],
    incumbent_set: set[str],
    candidate_by_id: dict[str, Candidate],
) -> bool:
    return _selected_key(candidate_set, candidate_by_id) > _selected_key(
        incumbent_set,
        candidate_by_id,
    )


def _ordered_component(
    component: list[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
    *,
    policy: str,
    reverse: bool = False,
) -> list[str]:
    return sorted(
        component,
        key=lambda candidate_id: greedy_priority(
            candidate_by_id[candidate_id],
            len(adjacency[candidate_id]),
            policy=policy,
        ),
        reverse=reverse,
    )


def solve_exact_component(
    component: list[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
    *,
    policy: str,
    deadline: float | None = None,
) -> set[str]:
    ordered = _ordered_component(
        component,
        candidate_by_id,
        adjacency,
        policy=policy,
    )
    index_by_id = {candidate_id: index for index, candidate_id in enumerate(ordered)}
    adjacency_masks = [0] * len(ordered)
    for candidate_id, index in index_by_id.items():
        mask = 0
        for neighbor_id in adjacency[candidate_id]:
            neighbor_index = index_by_id.get(neighbor_id)
            if neighbor_index is not None:
                mask |= 1 << neighbor_index
        adjacency_masks[index] = mask
    closed_masks = [
        adjacency_masks[index] | (1 << index)
        for index in range(len(ordered))
    ]
    component_degrees = [
        adjacency_masks[index].bit_count()
        for index in range(len(ordered))
    ]
    full_mask = (1 << len(ordered)) - 1

    @lru_cache(maxsize=None)
    def selected_key(mask: int) -> tuple[Any, ...]:
        selected_ids = [
            ordered[index]
            for index in range(len(ordered))
            if mask & (1 << index)
        ]
        total_weight = sum(candidate_by_id[candidate_id].task_weight for candidate_id in selected_ids)
        total_count = len(selected_ids)
        total_completion = sum(candidate_by_id[candidate_id].end_offset_s for candidate_id in selected_ids)
        return (
            round(total_weight, 12),
            total_count,
            -total_completion,
            tuple(sorted(selected_ids)),
        )

    @lru_cache(maxsize=None)
    def search(mask: int) -> int:
        if mask == 0:
            return 0
        if deadline is not None and time.perf_counter() >= deadline:
            raise _ExactDeadlineReached

        branch_index = max(
            (index for index in range(len(ordered)) if mask & (1 << index)),
            key=lambda index: (
                (adjacency_masks[index] & mask).bit_count(),
                component_degrees[index],
                ordered[index],
            ),
        )
        branch_bit = 1 << branch_index
        include_mask = branch_bit | search(mask & ~closed_masks[branch_index])
        exclude_mask = search(mask & ~branch_bit)
        if selected_key(include_mask) > selected_key(exclude_mask):
            return include_mask
        return exclude_mask

    selected_mask = search(full_mask)
    return {
        ordered[index]
        for index in range(len(ordered))
        if selected_mask & (1 << index)
    }


def solve_greedy_component(
    component: list[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
    *,
    policy: str,
    reverse: bool = False,
) -> set[str]:
    selected: set[str] = set()
    for candidate_id in _ordered_component(
        component,
        candidate_by_id,
        adjacency,
        policy=policy,
        reverse=reverse,
    ):
        if not adjacency[candidate_id] & selected:
            selected.add(candidate_id)
    return selected


def _augment_independent_set(
    selected: set[str],
    component: list[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
    *,
    policy: str,
) -> set[str]:
    augmented = set(selected)
    for candidate_id in _ordered_component(
        component,
        candidate_by_id,
        adjacency,
        policy=policy,
    ):
        if candidate_id in augmented:
            continue
        if not adjacency[candidate_id] & augmented:
            augmented.add(candidate_id)
    return augmented


def _find_best_one_improvement(
    component: list[str],
    selected: set[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
    *,
    deadline: float | None = None,
) -> str | None:
    best_candidate_id: str | None = None
    best_result: set[str] | None = None
    for candidate_id in component:
        if deadline is not None and time.perf_counter() >= deadline:
            raise _ExactDeadlineReached
        if candidate_id in selected:
            continue
        if adjacency[candidate_id] & selected:
            continue
        candidate_result = set(selected)
        candidate_result.add(candidate_id)
        if best_result is None or _is_better(candidate_result, best_result, candidate_by_id):
            best_result = candidate_result
            best_candidate_id = candidate_id
    return best_candidate_id


def _find_best_two_improvement(
    component: list[str],
    selected: set[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
    *,
    deadline: float | None = None,
) -> tuple[str, str, str] | None:
    selected_conflicts: dict[str, set[str]] = {}
    free_candidates: list[str] = []
    blocked_by: dict[str, list[str]] = defaultdict(list)
    for candidate_id in component:
        if candidate_id in selected:
            continue
        conflicts = adjacency[candidate_id] & selected
        selected_conflicts[candidate_id] = conflicts
        if not conflicts:
            free_candidates.append(candidate_id)
        elif len(conflicts) == 1:
            blocked_by[next(iter(conflicts))].append(candidate_id)

    best_move: tuple[str, str, str] | None = None
    best_key = _selected_key(selected, candidate_by_id)
    selected_weight = sum(candidate_by_id[candidate_id].task_weight for candidate_id in selected)
    selected_completion = sum(
        candidate_by_id[candidate_id].end_offset_s for candidate_id in selected
    )
    selected_count = len(selected)
    for removed_id in sorted(selected):
        if deadline is not None and time.perf_counter() >= deadline:
            raise _ExactDeadlineReached
        eligible = sorted(set(free_candidates) | set(blocked_by.get(removed_id, [])))
        if len(eligible) < 2:
            continue
        for added_a, added_b in combinations(eligible, 2):
            if deadline is not None and time.perf_counter() >= deadline:
                raise _ExactDeadlineReached
            if removed_id not in (selected_conflicts[added_a] | selected_conflicts[added_b]):
                continue
            if added_b in adjacency[added_a]:
                continue
            candidate_weight = (
                selected_weight
                - candidate_by_id[removed_id].task_weight
                + candidate_by_id[added_a].task_weight
                + candidate_by_id[added_b].task_weight
            )
            candidate_completion = (
                selected_completion
                - candidate_by_id[removed_id].end_offset_s
                + candidate_by_id[added_a].end_offset_s
                + candidate_by_id[added_b].end_offset_s
            )
            candidate_key = (
                round(candidate_weight, 12),
                selected_count + 1,
                -candidate_completion,
                tuple(sorted((selected - {removed_id}) | {added_a, added_b})),
            )
            if candidate_key > best_key:
                best_key = candidate_key
                best_move = (removed_id, added_a, added_b)
    return best_move


def _local_improve_component(
    component: list[str],
    selected: set[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
    *,
    config: MwisConfig,
    deadline: float | None,
) -> tuple[set[str], LocalImproveStats]:
    improved = set(selected)
    stats = LocalImproveStats(stop_reason="converged")
    for _ in range(config.max_local_passes):
        if deadline is not None and time.perf_counter() >= deadline:
            stats.stop_reason = "time_limit"
            break
        try:
            insertion = _find_best_one_improvement(
                component,
                improved,
                candidate_by_id,
                adjacency,
                deadline=deadline,
            )
        except _ExactDeadlineReached:
            stats.stop_reason = "time_limit"
            break
        if insertion is not None:
            improved.add(insertion)
            stats.improvement_count += 1
            continue
        try:
            two_improvement = _find_best_two_improvement(
                component,
                improved,
                candidate_by_id,
                adjacency,
                deadline=deadline,
            )
        except _ExactDeadlineReached:
            stats.stop_reason = "time_limit"
            break
        if two_improvement is None:
            stats.stop_reason = "converged"
            break
        removed_id, added_a, added_b = two_improvement
        improved.remove(removed_id)
        improved.add(added_a)
        improved.add(added_b)
        stats.improvement_count += 1
        stats.successful_two_swap_count += 1
    else:
        stats.stop_reason = "max_local_passes"
    return improved, stats


def _alternate_policy(policy: str) -> str:
    return "weight_degree_end" if policy == "weight_end_degree" else "weight_end_degree"


def _component_partition(
    component: list[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
) -> tuple[set[str], set[str], set[str]]:
    ordered = sorted(
        component,
        key=lambda candidate_id: (
            candidate_by_id[candidate_id].start_offset_s,
            candidate_by_id[candidate_id].candidate_id,
        ),
    )
    split_index = len(ordered) // 2
    left = set(ordered[:split_index])
    right = set(ordered[split_index:])
    separator = {
        candidate_id
        for candidate_id in left
        if adjacency[candidate_id] & right
    } | {
        candidate_id
        for candidate_id in right
        if adjacency[candidate_id] & left
    }
    return left - separator, right - separator, separator


def _combine_population_entries(
    parent_left: _PopulationEntry,
    parent_right: _PopulationEntry,
    component: list[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
    *,
    policy: str,
) -> _PopulationEntry:
    left_core, right_core, _separator = _component_partition(
        component,
        candidate_by_id,
        adjacency,
    )
    child_selected = (parent_left.selected & left_core) | (parent_right.selected & right_core)
    child_selected = _augment_independent_set(
        child_selected,
        component,
        candidate_by_id,
        adjacency,
        policy=policy,
    )
    return _PopulationEntry(
        selected=child_selected,
        source=f"recombination:{parent_left.source}+{parent_right.source}",
    )


def _insert_population_entry(
    population: list[_PopulationEntry],
    candidate_entry: _PopulationEntry,
    candidate_by_id: dict[str, Candidate],
    *,
    max_population_size: int,
) -> tuple[list[_PopulationEntry], bool]:
    encoded = tuple(sorted(candidate_entry.selected))
    existing = {tuple(sorted(entry.selected)) for entry in population}
    if encoded in existing:
        return population, False
    updated = population + [candidate_entry]
    updated.sort(
        key=lambda entry: _selected_key(entry.selected, candidate_by_id),
        reverse=True,
    )
    trimmed = updated[:max_population_size]
    inserted = any(tuple(sorted(entry.selected)) == encoded for entry in trimmed)
    return trimmed, inserted


def _summarize_global_incumbent_source(component_sources: list[str]) -> str:
    unique_sources = sorted(set(component_sources))
    if not unique_sources:
        return "exact_only"
    if len(unique_sources) == 1:
        return unique_sources[0]
    if "recombination" in unique_sources:
        return "mixed_with_recombination"
    if "local_improvement" in unique_sources:
        return "mixed_with_local_improvement"
    return "mixed"


def _apply_reduction_stats(
    stats: ComponentSearchStats,
    reduction: ReductionResult,
    candidate_by_id: dict[str, Candidate],
    *,
    reduction_elapsed_s: float,
) -> ComponentSearchStats:
    included_key = _selected_key(reduction.included_ids, candidate_by_id)
    stats.component_size = reduction.stats.original_component_size
    stats.reduced_component_size = reduction.stats.reduced_component_size
    stats.reduction_elapsed_s = reduction_elapsed_s
    stats.baseline_weight += included_key[0]
    stats.baseline_count += reduction.stats.included_by_reduction_count
    stats.final_weight += included_key[0]
    stats.final_count += reduction.stats.included_by_reduction_count
    stats.included_by_reduction_count = reduction.stats.included_by_reduction_count
    stats.removed_by_reduction_count = reduction.stats.removed_by_reduction_count
    stats.reduction_rule_counts = dict(reduction.stats.rule_counts)
    return stats


def _select_component_with_backend(
    component_index: int,
    component: list[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
    *,
    config: MwisConfig,
    deadline: float | None,
    backend: BackendResolution,
) -> tuple[set[str], ComponentSearchStats, bool]:
    if backend.backend not in {"internal_reduction", "fallback_python"}:
        raise RuntimeError(f"unsupported resolved MWIS backend: {backend.backend}")
    reduction_start = time.perf_counter()
    reduction = reduce_component(component, candidate_by_id, adjacency)
    reduction_elapsed_s = time.perf_counter() - reduction_start
    reduced_component = reduction.active_component

    if len(reduced_component) <= config.max_exact_component_size:
        exact_start = time.perf_counter()
        time_limit_hit = False
        stop_reason = "exact"
        incumbent_source = "exact"
        try:
            reduced_selected = solve_exact_component(
                reduced_component,
                candidate_by_id,
                adjacency,
                policy=config.selection_policy,
                deadline=deadline,
            )
        except _ExactDeadlineReached:
            reduced_selected = solve_greedy_component(
                reduced_component,
                candidate_by_id,
                adjacency,
                policy=config.selection_policy,
            )
            time_limit_hit = True
            stop_reason = "time_limit"
            incumbent_source = "deadline_greedy_fallback"
        elapsed_s = time.perf_counter() - exact_start
        component_selected = reduction.reconstruct(reduced_selected)
        selected_key = _selected_key(component_selected, candidate_by_id)
        return (
            component_selected,
            ComponentSearchStats(
                component_index=component_index,
                component_size=len(component),
                reduced_component_size=len(reduced_component),
                mode="exact" if not time_limit_hit else "baseline_only",
                baseline_source=incumbent_source,
                incumbent_source=incumbent_source,
                baseline_weight=selected_key[0],
                baseline_count=len(component_selected),
                final_weight=selected_key[0],
                final_count=len(component_selected),
                initial_population_size=1,
                local_improvement_count=0,
                successful_two_swap_count=0,
                recombination_attempt_count=0,
                recombination_win_count=0,
                elapsed_s=elapsed_s,
                time_limit_hit=time_limit_hit,
                stop_reason=stop_reason,
                reduction_elapsed_s=reduction_elapsed_s,
                included_by_reduction_count=reduction.stats.included_by_reduction_count,
                removed_by_reduction_count=reduction.stats.removed_by_reduction_count,
                reduction_rule_counts=dict(reduction.stats.rule_counts),
            ),
            not time_limit_hit,
        )

    reduced_selected, component_stats = _refine_large_component(
        component_index,
        reduced_component,
        candidate_by_id,
        adjacency,
        config=config,
        deadline=deadline,
    )
    component_selected = reduction.reconstruct(reduced_selected)
    component_stats = _apply_reduction_stats(
        component_stats,
        reduction,
        candidate_by_id,
        reduction_elapsed_s=reduction_elapsed_s,
    )
    return component_selected, component_stats, False


def _deadline_accounting(
    *,
    search_start: float,
    time_limit_s: float | None,
    deadline: float | None,
) -> tuple[float | None, float | None, str, bool]:
    refinement_deadline = (
        search_start + time_limit_s
        if time_limit_s is not None
        else None
    )
    deadline_options: list[tuple[str, float]] = []
    if refinement_deadline is not None:
        deadline_options.append(("time_limit_s", refinement_deadline))
    if deadline is not None:
        deadline_options.append(("total_time_budget_s", deadline))
    if not deadline_options:
        return None, None, "none", False

    effective_source, effective_deadline = min(
        deadline_options,
        key=lambda item: (item[1], item[0]),
    )
    if (
        refinement_deadline is not None
        and deadline is not None
        and abs(refinement_deadline - deadline) <= 1.0e-12
    ):
        effective_source = "time_limit_s_and_total_time_budget_s"
    effective_time_limit_s = max(0.0, effective_deadline - search_start)
    return (
        effective_deadline,
        effective_time_limit_s,
        effective_source,
        effective_deadline <= search_start,
    )


def _baseline_population(
    component: list[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
    *,
    config: MwisConfig,
) -> list[_PopulationEntry]:
    seed_specs = [
        ("configured", config.selection_policy, False),
        ("alternate", _alternate_policy(config.selection_policy), False),
        ("reverse", config.selection_policy, True),
    ]
    population: list[_PopulationEntry] = []
    for source, policy, reverse in seed_specs:
        entry = _PopulationEntry(
            selected=solve_greedy_component(
                component,
                candidate_by_id,
                adjacency,
                policy=policy,
                reverse=reverse,
            ),
            source=source,
        )
        population, _ = _insert_population_entry(
            population,
            entry,
            candidate_by_id,
            max_population_size=config.population_size,
        )
    population.sort(
        key=lambda entry: _selected_key(entry.selected, candidate_by_id),
        reverse=True,
    )
    return population


def _refine_large_component(
    component_index: int,
    component: list[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
    *,
    config: MwisConfig,
    deadline: float | None,
) -> tuple[set[str], ComponentSearchStats]:
    component_start = time.perf_counter()
    population = _baseline_population(
        component,
        candidate_by_id,
        adjacency,
        config=config,
    )
    baseline_entry = population[0]
    incumbent = _PopulationEntry(set(baseline_entry.selected), baseline_entry.source)
    stop_reason = "baseline_only"
    local_improvement_count = 0
    successful_two_swap_count = 0
    recombination_attempt_count = 0
    recombination_win_count = 0
    refined = False
    time_limit_hit = False

    if deadline is not None and time.perf_counter() >= deadline:
        time_limit_hit = True
        stop_reason = "time_limit"
    else:
        improved_population: list[_PopulationEntry] = []
        for entry in population:
            refined = True
            improved_selected, improve_stats = _local_improve_component(
                component,
                entry.selected,
                candidate_by_id,
                adjacency,
                config=config,
                deadline=deadline,
            )
            local_improvement_count += improve_stats.improvement_count
            successful_two_swap_count += improve_stats.successful_two_swap_count
            improved_entry = _PopulationEntry(improved_selected, entry.source)
            improved_population, _ = _insert_population_entry(
                improved_population,
                improved_entry,
                candidate_by_id,
                max_population_size=config.population_size,
            )
            if _is_better(improved_entry.selected, incumbent.selected, candidate_by_id):
                incumbent = _PopulationEntry(set(improved_entry.selected), "local_improvement")
            if improve_stats.stop_reason == "time_limit":
                time_limit_hit = True
                stop_reason = "time_limit"
                break
        if improved_population:
            population = improved_population
        if not time_limit_hit:
            parent_pairs = list(combinations(range(len(population)), 2))
            if not parent_pairs:
                stop_reason = "single_seed_population"
            else:
                stop_reason = "recombination_converged"
                for round_index in range(config.recombination_rounds):
                    if deadline is not None and time.perf_counter() >= deadline:
                        time_limit_hit = True
                        stop_reason = "time_limit"
                        break
                    pair_index = round_index % len(parent_pairs)
                    left_index, right_index = parent_pairs[pair_index]
                    parent_left = population[left_index]
                    parent_right = population[right_index]
                    improved_this_round = False
                    for orientation in (
                        (parent_left, parent_right),
                        (parent_right, parent_left),
                    ):
                        recombination_attempt_count += 1
                        child = _combine_population_entries(
                            orientation[0],
                            orientation[1],
                            component,
                            candidate_by_id,
                            adjacency,
                            policy=config.selection_policy,
                        )
                        child_selected, improve_stats = _local_improve_component(
                            component,
                            child.selected,
                            candidate_by_id,
                            adjacency,
                            config=config,
                            deadline=deadline,
                        )
                        local_improvement_count += improve_stats.improvement_count
                        successful_two_swap_count += improve_stats.successful_two_swap_count
                        child_entry = _PopulationEntry(child_selected, "recombination")
                        population, inserted = _insert_population_entry(
                            population,
                            child_entry,
                            candidate_by_id,
                            max_population_size=config.population_size,
                        )
                        if _is_better(child_entry.selected, incumbent.selected, candidate_by_id):
                            incumbent = _PopulationEntry(set(child_entry.selected), "recombination")
                            recombination_win_count += 1
                            improved_this_round = True
                        if improve_stats.stop_reason == "time_limit":
                            time_limit_hit = True
                            stop_reason = "time_limit"
                            break
                    if time_limit_hit:
                        break
                    if improved_this_round:
                        stop_reason = "recombination_improved"
                if (
                    stop_reason == "recombination_improved"
                    and recombination_win_count == 0
                ):
                    stop_reason = "recombination_converged"

    selected = incumbent.selected
    stats = ComponentSearchStats(
        component_index=component_index,
        component_size=len(component),
        reduced_component_size=len(component),
        mode="refined" if refined else "baseline_only",
        baseline_source=baseline_entry.source,
        incumbent_source=incumbent.source,
        baseline_weight=_selected_key(baseline_entry.selected, candidate_by_id)[0],
        baseline_count=len(baseline_entry.selected),
        final_weight=_selected_key(selected, candidate_by_id)[0],
        final_count=len(selected),
        initial_population_size=len(population),
        local_improvement_count=local_improvement_count,
        successful_two_swap_count=successful_two_swap_count,
        recombination_attempt_count=recombination_attempt_count,
        recombination_win_count=recombination_win_count,
        elapsed_s=time.perf_counter() - component_start,
        time_limit_hit=time_limit_hit,
        stop_reason=stop_reason,
    )
    return selected, stats


def select_weighted_independent_set(
    candidates: list[Candidate],
    graph: ConflictGraph,
    config: MwisConfig | None = None,
    *,
    deadline: float | None = None,
) -> tuple[list[Candidate], MwisStats]:
    config = config or MwisConfig()
    backend = resolve_backend(config.backend)
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    selected_ids: set[str] = set()
    exact_components = 0
    large_components = 0
    refined_components = 0
    search_start = time.perf_counter()
    (
        effective_deadline,
        effective_time_limit_s,
        deadline_source,
        selection_started_after_deadline,
    ) = _deadline_accounting(
        search_start=search_start,
        time_limit_s=config.time_limit_s,
        deadline=deadline,
    )
    time_limit_hit = False
    global_stop_reason = "converged"
    local_improvement_count = 0
    successful_two_swap_count = 0
    recombination_attempt_count = 0
    recombination_win_count = 0
    reduction_original_vertex_count = 0
    reduction_reduced_vertex_count = 0
    included_by_reduction_count = 0
    removed_by_reduction_count = 0
    reduction_rule_counts: Counter[str] = Counter()
    component_search: list[ComponentSearchStats] = []
    component_sources: list[str] = []

    for component_index, component in enumerate(connected_components(graph.adjacency), start=1):
        component_selected, component_stats, exact_component = _select_component_with_backend(
            component_index,
            component,
            candidate_by_id,
            graph.adjacency,
            config=config,
            deadline=effective_deadline,
            backend=backend,
        )
        reduction_original_vertex_count += component_stats.component_size
        reduction_reduced_vertex_count += component_stats.reduced_component_size
        included_by_reduction_count += component_stats.included_by_reduction_count
        removed_by_reduction_count += component_stats.removed_by_reduction_count
        reduction_rule_counts.update(component_stats.reduction_rule_counts)

        if exact_component:
            exact_components += 1
            component_search.append(component_stats)
            component_sources.append("exact")
        else:
            large_components += 1
            component_search.append(component_stats)
            if component_stats.mode == "refined":
                refined_components += 1
            local_improvement_count += component_stats.local_improvement_count
            successful_two_swap_count += component_stats.successful_two_swap_count
            recombination_attempt_count += component_stats.recombination_attempt_count
            recombination_win_count += component_stats.recombination_win_count
            component_sources.append(component_stats.incumbent_source)
            if component_stats.time_limit_hit:
                time_limit_hit = True
                global_stop_reason = "time_limit"
        selected_ids.update(component_selected)

    if not time_limit_hit and recombination_attempt_count == 0 and refined_components == 0:
        global_stop_reason = "exact_only"
    elif not time_limit_hit and recombination_win_count == 0 and local_improvement_count == 0:
        global_stop_reason = "baseline_population"

    valid = validate_independent_set(selected_ids, graph.adjacency)
    selected = sorted(
        (candidate_by_id[candidate_id] for candidate_id in selected_ids),
        key=lambda item: (item.start_offset_s, item.satellite_id, item.task_id, item.candidate_id),
    )
    stats = MwisStats(
        selected_candidate_count=len(selected),
        selected_total_weight=sum(candidate.task_weight for candidate in selected),
        exact_component_count=exact_components,
        greedy_component_count=large_components,
        refined_component_count=refined_components,
        independent_set_valid=valid,
        selection_policy=config.selection_policy,
        max_exact_component_size=config.max_exact_component_size,
        time_limit_s=config.time_limit_s,
        effective_time_limit_s=effective_time_limit_s,
        deadline_source=deadline_source,
        selection_started_after_deadline=selection_started_after_deadline,
        max_local_passes=config.max_local_passes,
        population_size=config.population_size,
        recombination_rounds=config.recombination_rounds,
        search_elapsed_s=time.perf_counter() - search_start,
        time_limit_hit=time_limit_hit,
        search_stop_reason=global_stop_reason,
        local_improvement_count=local_improvement_count,
        successful_two_swap_count=successful_two_swap_count,
        recombination_attempt_count=recombination_attempt_count,
        recombination_win_count=recombination_win_count,
        incumbent_source=_summarize_global_incumbent_source(component_sources),
        reduction_elapsed_s=sum(item.reduction_elapsed_s for item in component_search),
        requested_backend=backend.requested_backend,
        backend=backend.backend,
        backend_available=backend.backend_available,
        backend_fallback_reason=backend.backend_fallback_reason,
        reduction_original_vertex_count=reduction_original_vertex_count,
        reduction_reduced_vertex_count=reduction_reduced_vertex_count,
        included_by_reduction_count=included_by_reduction_count,
        removed_by_reduction_count=removed_by_reduction_count,
        reduction_rule_counts=dict(reduction_rule_counts),
        component_search=component_search,
    )
    return selected, stats
