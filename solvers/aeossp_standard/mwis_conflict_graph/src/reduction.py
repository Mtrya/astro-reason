"""Deterministic safe reductions for weighted MWIS components."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from .candidates import Candidate


@dataclass(frozen=True, slots=True)
class ReductionStats:
    original_component_size: int
    reduced_component_size: int
    included_by_reduction_count: int = 0
    removed_by_reduction_count: int = 0
    rule_counts: dict[str, int] = field(default_factory=dict)

    @classmethod
    def empty(cls, component_size: int) -> "ReductionStats":
        return cls(
            original_component_size=component_size,
            reduced_component_size=component_size,
        )

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rule_counts"] = dict(sorted(self.rule_counts.items()))
        return payload


@dataclass(frozen=True, slots=True)
class ReductionResult:
    active_component: list[str]
    included_ids: set[str]
    removed_ids: set[str]
    stats: ReductionStats

    def reconstruct(self, reduced_selected: set[str]) -> set[str]:
        return set(reduced_selected) | set(self.included_ids)


def _dominates(
    dominator_id: str,
    dominated_id: str,
    *,
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
) -> bool:
    if dominated_id not in adjacency[dominator_id]:
        return False
    dominator = candidate_by_id[dominator_id]
    dominated = candidate_by_id[dominated_id]
    if dominator.task_weight <= dominated.task_weight + 1.0e-12:
        return False
    dominator_neighbors = adjacency[dominator_id] - {dominated_id}
    dominated_neighbors = adjacency[dominated_id] - {dominator_id}
    return dominator_neighbors <= dominated_neighbors


def reduce_component(
    component: list[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
) -> ReductionResult:
    """Apply safe weighted-MWIS reductions and keep reconstruction data."""

    active = set(component)
    included: set[str] = set()
    removed: set[str] = set()
    rule_counts: Counter[str] = Counter()

    changed = True
    while changed:
        changed = False

        isolated = [
            candidate_id
            for candidate_id in sorted(active)
            if not (adjacency[candidate_id] & active)
            and candidate_by_id[candidate_id].task_weight >= 0.0
        ]
        if isolated:
            included.update(isolated)
            active.difference_update(isolated)
            rule_counts["isolated_vertex_include"] += len(isolated)
            changed = True
            continue

        for dominated_id in sorted(active):
            dominator_id = next(
                (
                    candidate_id
                    for candidate_id in sorted(adjacency[dominated_id] & active)
                    if candidate_id != dominated_id
                    and _dominates(
                        candidate_id,
                        dominated_id,
                        candidate_by_id=candidate_by_id,
                        adjacency=adjacency,
                    )
                ),
                None,
            )
            if dominator_id is None:
                continue
            active.remove(dominated_id)
            removed.add(dominated_id)
            rule_counts["strict_weighted_dominated_vertex_remove"] += 1
            changed = True
            break

    active_component = [candidate_id for candidate_id in component if candidate_id in active]
    stats = ReductionStats(
        original_component_size=len(component),
        reduced_component_size=len(active_component),
        included_by_reduction_count=len(included),
        removed_by_reduction_count=len(removed),
        rule_counts=dict(rule_counts),
    )
    return ReductionResult(
        active_component=active_component,
        included_ids=included,
        removed_ids=removed,
        stats=stats,
    )
