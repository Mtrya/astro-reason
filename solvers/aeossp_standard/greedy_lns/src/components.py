"""Per-satellite dependence graphs and connected-component extraction."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from .candidates import Candidate
from .case_io import AeosspCase
from .geometry import PropagationContext
from .transition import TransitionVectorCache, max_transition_gap_s, transition_gap_conflict


@dataclass(frozen=True, slots=True)
class Component:
    satellite_id: str
    component_id: str
    candidates: tuple[Candidate, ...]

    @property
    def size(self) -> int:
        return len(self.candidates)

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(c.candidate_id for c in self.candidates)

    def as_dict(self) -> dict[str, Any]:
        return {
            "satellite_id": self.satellite_id,
            "component_id": self.component_id,
            "size": self.size,
            "candidate_ids": list(self.candidate_ids),
        }


@dataclass(slots=True)
class ComponentStats:
    satellite_count: int = 0
    component_count: int = 0
    largest_component_size: int = 0
    singleton_count: int = 0
    component_size_histogram: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ComponentIndex:
    components: list[Component]
    candidate_id_to_component: dict[str, Component]
    per_satellite: dict[str, list[Component]]
    stats: ComponentStats

    def as_dict(self) -> dict[str, Any]:
        return {
            "stats": self.stats.as_dict(),
            "components": [c.as_dict() for c in self.components],
        }


def _build_satellite_dependence_edges(
    case: AeosspCase,
    satellite_id: str,
    candidates: list[Candidate],
) -> dict[str, set[str]]:
    """Build a dependence adjacency map for one satellite.

    An edge exists between two candidates when their time windows overlap
    after transition padding, i.e. they cannot both appear in the same
    schedule regardless of ordering.
    """
    satellite = case.satellites[satellite_id]
    safe_gap_s = max_transition_gap_s(satellite)

    adjacency: dict[str, set[str]] = {
        candidate.candidate_id: set() for candidate in candidates
    }

    ordered = sorted(
        candidates,
        key=lambda item: (item.start_offset_s, item.end_offset_s, item.candidate_id),
    )

    # We need a vector cache for transition_gap_conflict, but creating one
    # per satellite is fine.  We only use it when gap <= safe_gap_s.
    step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
    propagation = PropagationContext(case.satellites, step_s=step_s)
    vector_cache = TransitionVectorCache(case, propagation)

    for left_index, candidate_a in enumerate(ordered):
        for candidate_b in ordered[left_index + 1 :]:
            if candidate_b.start_offset_s < candidate_a.end_offset_s:
                # overlap
                adjacency[candidate_a.candidate_id].add(candidate_b.candidate_id)
                adjacency[candidate_b.candidate_id].add(candidate_a.candidate_id)
                continue
            gap_s = candidate_b.start_offset_s - candidate_a.end_offset_s
            if gap_s > safe_gap_s:
                break
            if transition_gap_conflict(
                candidate_a,
                candidate_b,
                case=case,
                vector_cache=vector_cache,
            ):
                adjacency[candidate_a.candidate_id].add(candidate_b.candidate_id)
                adjacency[candidate_b.candidate_id].add(candidate_a.candidate_id)

    return adjacency


def _extract_components(
    satellite_id: str,
    adjacency: dict[str, set[str]],
    candidate_by_id: dict[str, Candidate],
) -> list[Component]:
    """Extract connected components from a satellite's dependence graph.

    Deterministic ordering: roots chosen lexicographically, neighbors
    visited in sorted order.
    """
    remaining = set(adjacency)
    components: list[Component] = []

    while remaining:
        root_id = min(remaining)
        stack = [root_id]
        remaining.remove(root_id)
        member_ids: list[str] = []

        while stack:
            current_id = stack.pop()
            member_ids.append(current_id)
            for neighbor_id in sorted(adjacency[current_id]):
                if neighbor_id in remaining:
                    remaining.remove(neighbor_id)
                    stack.append(neighbor_id)

        member_ids.sort()
        component_id = f"{satellite_id}::{root_id}"
        components.append(
            Component(
                satellite_id=satellite_id,
                component_id=component_id,
                candidates=tuple(candidate_by_id[mid] for mid in member_ids),
            )
        )

    return sorted(components, key=lambda c: (c.satellite_id, c.component_id))


def build_component_index(
    case: AeosspCase,
    candidates: list[Candidate],
) -> ComponentIndex:
    """Build per-satellite dependence graphs and extract connected components."""
    by_satellite: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_satellite[candidate.satellite_id].append(candidate)

    all_components: list[Component] = []
    candidate_id_to_component: dict[str, Component] = {}
    per_satellite: dict[str, list[Component]] = {}

    for satellite_id in sorted(by_satellite):
        satellite_candidates = by_satellite[satellite_id]
        candidate_by_id = {c.candidate_id: c for c in satellite_candidates}
        adjacency = _build_satellite_dependence_edges(
            case, satellite_id, satellite_candidates
        )
        satellite_components = _extract_components(
            satellite_id, adjacency, candidate_by_id
        )
        per_satellite[satellite_id] = satellite_components
        all_components.extend(satellite_components)
        for component in satellite_components:
            for candidate in component.candidates:
                candidate_id_to_component[candidate.candidate_id] = component

    histogram: dict[str, int] = {}
    for component in all_components:
        key = str(component.size)
        histogram[key] = histogram.get(key, 0) + 1

    stats = ComponentStats(
        satellite_count=len(per_satellite),
        component_count=len(all_components),
        largest_component_size=max((c.size for c in all_components), default=0),
        singleton_count=histogram.get("1", 0),
        component_size_histogram=dict(sorted(histogram.items(), key=lambda item: int(item[0]))),
    )

    return ComponentIndex(
        components=sorted(all_components, key=lambda c: (c.satellite_id, c.component_id)),
        candidate_id_to_component=candidate_id_to_component,
        per_satellite=per_satellite,
        stats=stats,
    )
