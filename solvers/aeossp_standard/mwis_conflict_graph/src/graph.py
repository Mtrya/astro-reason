"""Sparse infeasibility graph construction for AEOSSP candidates."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from itertools import combinations
from typing import Any

from .candidates import Candidate
from .case_io import AeosspCase
from .geometry import PropagationContext
from .transition import (
    TransitionVectorCache,
    max_transition_gap_s,
    transition_gap_conflict,
)


Edge = tuple[str, str]


@dataclass(frozen=True, slots=True)
class GraphBuildConfig:
    graph_workers: int = 1

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "GraphBuildConfig":
        payload = payload or {}
        return cls(graph_workers=_positive_int(payload.get("graph_workers", 1)))

    def as_status_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GraphStats:
    vertex_count: int = 0
    edge_count: int = 0
    duplicate_task_edge_count: int = 0
    overlap_edge_count: int = 0
    transition_edge_count: int = 0
    component_count: int = 0
    largest_component_size: int = 0
    component_size_histogram: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ConflictGraph:
    adjacency: dict[str, set[str]]
    stats: GraphStats
    reason_edges: dict[str, set[Edge]] = field(default_factory=dict)

    def has_edge(self, candidate_a: str, candidate_b: str) -> bool:
        return candidate_b in self.adjacency.get(candidate_a, set())


@dataclass(frozen=True, slots=True)
class _SatelliteTemporalEdges:
    satellite_id: str
    overlap_edges: set[Edge]
    transition_edges: set[Edge]


def _positive_int(value: Any) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("graph worker count must be a positive integer")
    return parsed


def normalized_edge(candidate_a: str, candidate_b: str) -> Edge:
    if candidate_a == candidate_b:
        raise ValueError("self edges are not supported")
    return (candidate_a, candidate_b) if candidate_a < candidate_b else (candidate_b, candidate_a)


def add_edge(
    adjacency: dict[str, set[str]],
    reason_edges: dict[str, set[Edge]],
    candidate_a: str,
    candidate_b: str,
    reason: str,
) -> None:
    edge = normalized_edge(candidate_a, candidate_b)
    adjacency[edge[0]].add(edge[1])
    adjacency[edge[1]].add(edge[0])
    reason_edges[reason].add(edge)


def _add_reason_edges(
    adjacency: dict[str, set[str]],
    reason_edges: dict[str, set[Edge]],
    reason: str,
    edges: set[Edge],
) -> None:
    reason_edges[reason].update(edges)
    for left_id, right_id in sorted(edges):
        adjacency[left_id].add(right_id)
        adjacency[right_id].add(left_id)


def connected_components(adjacency: dict[str, set[str]]) -> list[list[str]]:
    remaining = set(adjacency)
    components: list[list[str]] = []
    while remaining:
        root = min(remaining)
        stack = [root]
        remaining.remove(root)
        component: list[str] = []
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    return sorted(components, key=lambda item: (len(item), item[0]))


def _duplicate_task_edges(candidates: list[Candidate]) -> set[Edge]:
    by_task: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_task[candidate.task_id].append(candidate)
    edges: set[Edge] = set()
    for task_id in sorted(by_task):
        for candidate_a, candidate_b in combinations(
            sorted(by_task[task_id], key=lambda item: item.candidate_id),
            2,
        ):
            edges.add(
                normalized_edge(
                    candidate_a.candidate_id,
                    candidate_b.candidate_id,
                )
            )
    return edges


def _satellite_temporal_edges(
    case: AeosspCase,
    satellite_id: str,
    satellite_candidates: list[Candidate],
) -> _SatelliteTemporalEdges:
    step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
    propagation = PropagationContext(
        {satellite_id: case.satellites[satellite_id]},
        step_s=step_s,
    )
    vector_cache = TransitionVectorCache(case, propagation)
    satellite = case.satellites[satellite_id]
    safe_gap_s = max_transition_gap_s(satellite)
    ordered = sorted(
        satellite_candidates,
        key=lambda item: (item.start_offset_s, item.end_offset_s, item.candidate_id),
    )
    overlap_edges: set[Edge] = set()
    transition_edges: set[Edge] = set()
    for left_index, candidate_a in enumerate(ordered):
        for candidate_b in ordered[left_index + 1 :]:
            if candidate_b.start_offset_s < candidate_a.end_offset_s:
                overlap_edges.add(
                    normalized_edge(
                        candidate_a.candidate_id,
                        candidate_b.candidate_id,
                    )
                )
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
                transition_edges.add(
                    normalized_edge(
                        candidate_a.candidate_id,
                        candidate_b.candidate_id,
                    )
                )
    return _SatelliteTemporalEdges(
        satellite_id=satellite_id,
        overlap_edges=overlap_edges,
        transition_edges=transition_edges,
    )


def _satellite_temporal_edges_task(
    payload: tuple[AeosspCase, str, list[Candidate]],
) -> _SatelliteTemporalEdges:
    case, satellite_id, satellite_candidates = payload
    return _satellite_temporal_edges(case, satellite_id, satellite_candidates)


def _same_satellite_temporal_edges(
    case: AeosspCase,
    candidates: list[Candidate],
    *,
    config: GraphBuildConfig,
) -> tuple[set[Edge], set[Edge]]:
    by_satellite: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_satellite[candidate.satellite_id].append(candidate)

    tasks = [
        (case, satellite_id, by_satellite[satellite_id])
        for satellite_id in sorted(by_satellite)
    ]
    if config.graph_workers > 1 and len(tasks) > 1:
        max_workers = min(config.graph_workers, len(tasks))
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(_satellite_temporal_edges_task, tasks))
    else:
        results = [_satellite_temporal_edges_task(task) for task in tasks]

    overlap_edges: set[Edge] = set()
    transition_edges: set[Edge] = set()
    for result in sorted(results, key=lambda item: item.satellite_id):
        overlap_edges.update(result.overlap_edges)
        transition_edges.update(result.transition_edges)
    return overlap_edges, transition_edges


def _build_duplicate_task_edges(
    candidates: list[Candidate],
    adjacency: dict[str, set[str]],
    reason_edges: dict[str, set[Edge]],
) -> None:
    _add_reason_edges(
        adjacency,
        reason_edges,
        "duplicate_task",
        _duplicate_task_edges(candidates),
    )


def _build_same_satellite_temporal_edges(
    case: AeosspCase,
    candidates: list[Candidate],
    adjacency: dict[str, set[str]],
    reason_edges: dict[str, set[Edge]],
    *,
    config: GraphBuildConfig,
) -> None:
    overlap_edges, transition_edges = _same_satellite_temporal_edges(
        case,
        candidates,
        config=config,
    )
    _add_reason_edges(adjacency, reason_edges, "overlap", overlap_edges)
    _add_reason_edges(adjacency, reason_edges, "transition", transition_edges)


def graph_build_execution_model(
    graph_config: GraphBuildConfig,
    *,
    satellite_count: int,
) -> dict[str, Any]:
    effective_workers = (
        min(graph_config.graph_workers, satellite_count)
        if graph_config.graph_workers > 1 and satellite_count > 1
        else 1
    )
    if effective_workers > 1:
        return {
            "model": "process_pool_python",
            "bounded_by_search_budget": False,
            "parallelism_scope": "satellite_temporal_edges",
            "configured_workers": graph_config.graph_workers,
            "effective_workers": effective_workers,
            "notes": (
                "duplicate-task edges are generated serially; same-satellite overlap "
                "and transition edges are generated per satellite and merged deterministically"
            ),
        }
    return {
        "model": "optimized_single_threaded_python",
        "bounded_by_search_budget": False,
        "parallelism_scope": "none",
        "configured_workers": graph_config.graph_workers,
        "effective_workers": 1,
        "notes": (
            "grouped duplicate-task edges plus sorted same-satellite temporal windows "
            "with deterministic edge-set materialization"
        ),
    }


def _legacy_build_same_satellite_temporal_edges(
    case: AeosspCase,
    candidates: list[Candidate],
    adjacency: dict[str, set[str]],
    reason_edges: dict[str, set[Edge]],
) -> None:
    by_satellite: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_satellite[candidate.satellite_id].append(candidate)

    step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
    propagation = PropagationContext(case.satellites, step_s=step_s)
    vector_cache = TransitionVectorCache(case, propagation)

    for satellite_id, satellite_candidates in by_satellite.items():
        satellite = case.satellites[satellite_id]
        safe_gap_s = max_transition_gap_s(satellite)
        ordered = sorted(
            satellite_candidates,
            key=lambda item: (item.start_offset_s, item.end_offset_s, item.candidate_id),
        )
        for left_index, candidate_a in enumerate(ordered):
            for candidate_b in ordered[left_index + 1 :]:
                if candidate_b.start_offset_s < candidate_a.end_offset_s:
                    add_edge(
                        adjacency,
                        reason_edges,
                        candidate_a.candidate_id,
                        candidate_b.candidate_id,
                        "overlap",
                    )
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
                    add_edge(
                        adjacency,
                        reason_edges,
                        candidate_a.candidate_id,
                        candidate_b.candidate_id,
                        "transition",
                    )


def build_conflict_graph(
    case: AeosspCase,
    candidates: list[Candidate],
    config: GraphBuildConfig | None = None,
) -> ConflictGraph:
    config = config or GraphBuildConfig()
    stable_candidates = sorted(candidates, key=lambda item: item.candidate_id)
    adjacency: dict[str, set[str]] = {
        candidate.candidate_id: set() for candidate in stable_candidates
    }
    reason_edges: dict[str, set[Edge]] = {
        "duplicate_task": set(),
        "overlap": set(),
        "transition": set(),
    }
    _build_duplicate_task_edges(stable_candidates, adjacency, reason_edges)
    _build_same_satellite_temporal_edges(
        case,
        stable_candidates,
        adjacency,
        reason_edges,
        config=config,
    )

    components = connected_components(adjacency)
    component_size_histogram: dict[str, int] = {}
    for component in components:
        key = str(len(component))
        component_size_histogram[key] = component_size_histogram.get(key, 0) + 1
    stats = GraphStats(
        vertex_count=len(stable_candidates),
        edge_count=sum(len(neighbors) for neighbors in adjacency.values()) // 2,
        duplicate_task_edge_count=len(reason_edges["duplicate_task"]),
        overlap_edge_count=len(reason_edges["overlap"]),
        transition_edge_count=len(reason_edges["transition"]),
        component_count=len(components),
        largest_component_size=max((len(component) for component in components), default=0),
        component_size_histogram=dict(sorted(component_size_histogram.items(), key=lambda item: int(item[0]))),
    )
    return ConflictGraph(adjacency=adjacency, stats=stats, reason_edges=reason_edges)


def _build_conflict_graph_legacy(case: AeosspCase, candidates: list[Candidate]) -> ConflictGraph:
    stable_candidates = sorted(candidates, key=lambda item: item.candidate_id)
    adjacency: dict[str, set[str]] = {
        candidate.candidate_id: set() for candidate in stable_candidates
    }
    reason_edges: dict[str, set[Edge]] = {
        "duplicate_task": set(),
        "overlap": set(),
        "transition": set(),
    }
    by_task: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in stable_candidates:
        by_task[candidate.task_id].append(candidate)
    for task_candidates in by_task.values():
        for candidate_a, candidate_b in combinations(
            sorted(task_candidates, key=lambda item: item.candidate_id),
            2,
        ):
            add_edge(
                adjacency,
                reason_edges,
                candidate_a.candidate_id,
                candidate_b.candidate_id,
                "duplicate_task",
            )
    _legacy_build_same_satellite_temporal_edges(case, stable_candidates, adjacency, reason_edges)

    components = connected_components(adjacency)
    component_size_histogram: dict[str, int] = {}
    for component in components:
        key = str(len(component))
        component_size_histogram[key] = component_size_histogram.get(key, 0) + 1
    stats = GraphStats(
        vertex_count=len(stable_candidates),
        edge_count=sum(len(neighbors) for neighbors in adjacency.values()) // 2,
        duplicate_task_edge_count=len(reason_edges["duplicate_task"]),
        overlap_edge_count=len(reason_edges["overlap"]),
        transition_edge_count=len(reason_edges["transition"]),
        component_count=len(components),
        largest_component_size=max((len(component) for component in components), default=0),
        component_size_histogram=dict(sorted(component_size_histogram.items(), key=lambda item: int(item[0]))),
    )
    return ConflictGraph(adjacency=adjacency, stats=stats, reason_edges=reason_edges)
