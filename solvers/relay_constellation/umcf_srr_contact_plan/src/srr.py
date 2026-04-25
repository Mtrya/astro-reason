"""Sequential Randomized Rounding (SRR) oracle for UMCF instances."""

from __future__ import annotations

import heapq
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any

from .umcf import UMCFInstance


@dataclass(frozen=True)
class Path:
    """A simple path through the graph."""

    nodes: tuple[str, ...]
    # Undirected edges as canonical (min, max) tuples
    edges: tuple[tuple[str, str], ...]
    total_distance_m: float
    hop_count: int


@dataclass
class SRRConfig:
    """Configuration for the SRR oracle."""

    seed: int | None = 42
    deterministic: bool = False
    k_paths: int = 4
    path_change_penalty: float = 1.0
    multi_run_count: int = 1
    max_path_hops: int = 10


@dataclass
class SRRResult:
    """Result of running the SRR oracle over a sequence of UMCF instances."""

    sample_assignments: list[dict[str, Path]]
    dropped_by_sample: list[list[str]]
    path_changes: int
    seed: int | None
    deterministic: bool
    execution_time_s: float
    timing_breakdown: dict[str, float] = field(default_factory=dict)
    rounding_diagnostics: dict[str, int] = field(default_factory=dict)


def _canonical_edge(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _dijkstra(
    adjacency: dict[str, list[tuple[str, float]]],
    source: str,
    destination: str,
    endpoint_ids: set[str],
) -> list[str] | None:
    """Return the shortest path by distance as a list of nodes, or None.

    Intermediate ground endpoints (other than source and destination) are not
    traversed.
    """
    if source == destination:
        return [source]
    if source not in adjacency:
        return None

    dist: dict[str, float] = {source: 0.0}
    prev: dict[str, str | None] = {source: None}
    heap: list[tuple[float, str]] = [(0.0, source)]
    visited: set[str] = set()

    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        if u == destination:
            break
        for v, w in adjacency.get(u, []):
            if v in visited:
                continue
            if v in endpoint_ids and v != destination:
                continue
            nd = d + w
            if nd < dist.get(v, math.inf) - 1e-12:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))

    if destination not in prev:
        return None

    # Reconstruct
    path: list[str] = []
    node: str | None = destination
    while node is not None:
        path.append(node)
        node = prev[node]
    path.reverse()
    return path


def _path_from_nodes(
    nodes: list[str],
    adjacency: dict[str, list[tuple[str, float]]],
) -> Path | None:
    """Build a Path from a node sequence, looking up distances."""
    if len(nodes) < 2:
        return None
    edges: list[tuple[str, str]] = []
    total_distance = 0.0
    for i in range(len(nodes) - 1):
        a, b = nodes[i], nodes[i + 1]
        found = False
        for neighbor, dist in adjacency.get(a, []):
            if neighbor == b:
                total_distance += dist
                edges.append(_canonical_edge(a, b))
                found = True
                break
        if not found:
            return None
    return Path(
        nodes=tuple(nodes),
        edges=tuple(edges),
        total_distance_m=total_distance,
        hop_count=len(edges),
    )


def k_shortest_paths(
    adjacency: dict[str, list[tuple[str, float]]],
    source: str,
    destination: str,
    k: int,
    endpoint_ids: set[str],
    max_hops: int,
) -> list[Path]:
    """Generate up to k shortest simple paths from source to destination.

    Paths are sorted by (hop_count, total_distance_m).  No intermediate
    ground-endpoint transit is allowed: endpoints other than source and
    destination are forbidden as intermediate nodes.
    """
    if source not in adjacency or destination not in adjacency:
        return []

    # 1. Dijkstra shortest path (respects no-ground-transit)
    shortest = _dijkstra(adjacency, source, destination, endpoint_ids)
    if shortest is None:
        return []

    spath = _path_from_nodes(shortest, adjacency)
    if spath is None:
        return []

    unique_paths: dict[tuple[str, ...], Path] = {}
    if spath.hop_count <= max_hops:
        unique_paths[spath.nodes] = spath

    # 2. DFS enumeration of simple paths, capped by max_hops and a visit limit
    #    to keep runtime bounded on small dense graphs.
    stack: list[tuple[str, list[str], set[str]]] = [
        (source, [source], {source})
    ]
    visit_budget = k * 50  # generous cap to avoid explosion

    while stack and len(unique_paths) < k and visit_budget > 0:
        node, path_nodes, visited = stack.pop()
        visit_budget -= 1
        if len(path_nodes) > max_hops:
            continue
        if node == destination and len(path_nodes) > 1:
            p = _path_from_nodes(path_nodes, adjacency)
            if p is not None:
                unique_paths[p.nodes] = p
            continue
        # Expand neighbors in deterministic order for reproducibility
        for neighbor, _ in sorted(adjacency.get(node, []), key=lambda x: x[0]):
            if neighbor in visited:
                continue
            # No intermediate ground transit
            if neighbor in endpoint_ids and neighbor != destination:
                continue
            stack.append(
                (neighbor, path_nodes + [neighbor], visited | {neighbor})
            )

    paths = list(unique_paths.values())
    paths.sort(key=lambda p: (p.hop_count, p.total_distance_m, p.nodes))
    return paths[:k]


def heuristic_probabilities(
    paths: list[Path],
    prev_path: Path | None,
    penalty_alpha: float,
) -> list[float]:
    """Compute heuristic selection probabilities over paths.

    Base weights are uniform.  If ``prev_path`` is present and matches one of
    the candidate paths, its weight is boosted by ``exp(penalty_alpha)``.
    """
    if not paths:
        return []

    weights = [1.0] * len(paths)
    if prev_path is not None and penalty_alpha > 0:
        prev_nodes = prev_path.nodes
        for i, p in enumerate(paths):
            if p.nodes == prev_nodes:
                weights[i] = math.exp(penalty_alpha)
                break

    total = sum(weights)
    return [w / total for w in weights]


def path_node_usage(path: Path) -> dict[str, int]:
    """Return per-node degree consumed by a selected path."""
    usage: dict[str, int] = {}
    for a, b in path.edges:
        usage[a] = usage.get(a, 0) + 1
        usage[b] = usage.get(b, 0) + 1
    return usage


def sequential_rounding(
    instance: UMCFInstance,
    prev_assignments: dict[str, Path] | None,
    config: SRRConfig,
    rng: random.Random,
) -> tuple[dict[str, Path], dict[str, Any]]:
    """Fix one path per commodity using SRR-style sequential rounding.

    Commodities are processed in decreasing weight order.  Edge capacities
    and node degree capacities are updated after each fixation.  Node
    capacities approximate the benchmark's per-sample endpoint and satellite
    link caps inside the oracle; action-generation repair remains a final
    validity backstop.

    Returns (assignments, timing) where timing contains ``path_generation_s``
    and ``rounding_s`` plus a nested ``diagnostics`` mapping.
    """
    if prev_assignments is None:
        prev_assignments = {}

    # Working copies of per-sample capacities.
    edge_cap: dict[tuple[str, str], int] = dict(instance.edge_capacity)
    node_cap: dict[str, int] = dict(instance.node_capacity)

    # Sort commodities by decreasing weight, then deterministic id tie-break
    commodities = sorted(
        instance.commodities,
        key=lambda c: (-c.weight, c.demand_id),
    )

    assignments: dict[str, Path] = {}
    t_path = 0.0
    t_round = 0.0
    diagnostics = {
        "paths_rejected_edge_capacity": 0,
        "paths_rejected_node_capacity": 0,
        "commodities_dropped_no_paths": 0,
        "commodities_dropped_edge_capacity": 0,
        "commodities_dropped_node_capacity": 0,
        "commodities_dropped_mixed_capacity": 0,
    }

    for commodity in commodities:
        t0 = time.perf_counter()
        paths = k_shortest_paths(
            instance.adjacency,
            commodity.source,
            commodity.destination,
            config.k_paths,
            instance.endpoint_ids,
            config.max_path_hops,
        )
        t_path += time.perf_counter() - t0

        if not paths:
            diagnostics["commodities_dropped_no_paths"] += 1
            continue

        t0 = time.perf_counter()
        # Filter to paths with available edge and node capacity.
        feasible: list[Path] = []
        rejected_by_edge = False
        rejected_by_node = False
        for p in paths:
            edge_ok = True
            for e in p.edges:
                if edge_cap.get(e, 0) < 1:
                    edge_ok = False
                    break
            node_usage = path_node_usage(p)
            node_ok = all(
                node_cap.get(node, 0) >= demand
                for node, demand in node_usage.items()
            )

            if edge_ok and node_ok:
                feasible.append(p)
            else:
                if not edge_ok:
                    diagnostics["paths_rejected_edge_capacity"] += 1
                    rejected_by_edge = True
                if not node_ok:
                    diagnostics["paths_rejected_node_capacity"] += 1
                    rejected_by_node = True

        if not feasible:
            if rejected_by_edge and rejected_by_node:
                diagnostics["commodities_dropped_mixed_capacity"] += 1
            elif rejected_by_edge:
                diagnostics["commodities_dropped_edge_capacity"] += 1
            elif rejected_by_node:
                diagnostics["commodities_dropped_node_capacity"] += 1
            t_round += time.perf_counter() - t0
            continue

        prev = prev_assignments.get(commodity.demand_id)
        probs = heuristic_probabilities(feasible, prev, config.path_change_penalty)

        if config.deterministic:
            chosen = feasible[probs.index(max(probs))]
        else:
            # Inverse-transform sampling
            r = rng.random()
            cumulative = 0.0
            chosen = feasible[-1]
            for p, pr in zip(feasible, probs):
                cumulative += pr
                if r <= cumulative:
                    chosen = p
                    break

        assignments[commodity.demand_id] = chosen
        for e in chosen.edges:
            edge_cap[e] = edge_cap.get(e, 0) - 1
        for node, demand in path_node_usage(chosen).items():
            node_cap[node] = node_cap.get(node, 0) - demand
        t_round += time.perf_counter() - t0

    return assignments, {
        "path_generation_s": t_path,
        "rounding_s": t_round,
        "diagnostics": diagnostics,
    }


def run_srr_oracle(
    umcf_instances: list[UMCFInstance],
    config: SRRConfig,
) -> SRRResult:
    """Run the SRR oracle over a sequence of UMCF instances.

    If ``multi_run_count > 1``, the oracle is executed multiple times with
    different seeds and the assignment set with the highest served weight is
    returned.
    """
    if config.multi_run_count <= 0:
        raise ValueError(f"multi_run_count must be positive, got {config.multi_run_count}")

    t0 = time.perf_counter()
    path_gen_time = 0.0
    rounding_time = 0.0

    best_assignments: list[dict[str, Path]] | None = None
    best_dropped: list[list[str]] | None = None
    best_path_changes = 0
    best_served_weight = -1.0
    best_seed = config.seed
    best_diagnostics: dict[str, int] = {}

    base_seed = config.seed if config.seed is not None else 0

    for run in range(config.multi_run_count):
        seed = base_seed + run
        rng = random.Random(seed)

        sample_assignments: list[dict[str, Path]] = []
        dropped_by_sample: list[list[str]] = []
        path_changes = 0
        prev: dict[str, Path] | None = None
        total_served_weight = 0.0
        run_path_time = 0.0
        run_round_time = 0.0
        run_diagnostics = {
            "paths_rejected_edge_capacity": 0,
            "paths_rejected_node_capacity": 0,
            "commodities_dropped_no_paths": 0,
            "commodities_dropped_edge_capacity": 0,
            "commodities_dropped_node_capacity": 0,
            "commodities_dropped_mixed_capacity": 0,
        }

        for instance in umcf_instances:
            assignments, timing = sequential_rounding(instance, prev, config, rng)
            run_path_time += timing["path_generation_s"]
            run_round_time += timing["rounding_s"]
            for key, value in timing.get("diagnostics", {}).items():
                run_diagnostics[key] = run_diagnostics.get(key, 0) + int(value)

            # Compute dropped commodities and served weight
            assigned_ids = set(assignments.keys())
            dropped = [
                c.demand_id
                for c in instance.commodities
                if c.demand_id not in assigned_ids
            ]
            served_weight = sum(
                c.weight
                for c in instance.commodities
                if c.demand_id in assigned_ids
            )
            total_served_weight += served_weight

            # Count path changes vs previous sample
            if prev is not None:
                for demand_id, path in assignments.items():
                    prev_path = prev.get(demand_id)
                    if prev_path is not None and prev_path.nodes != path.nodes:
                        path_changes += 1

            sample_assignments.append(assignments)
            dropped_by_sample.append(dropped)
            prev = assignments

        path_gen_time += run_path_time
        rounding_time += run_round_time

        if total_served_weight > best_served_weight:
            best_served_weight = total_served_weight
            best_assignments = sample_assignments
            best_dropped = dropped_by_sample
            best_path_changes = path_changes
            best_seed = seed
            best_diagnostics = run_diagnostics

    total_time = time.perf_counter() - t0

    assert best_assignments is not None
    assert best_dropped is not None

    return SRRResult(
        sample_assignments=best_assignments,
        dropped_by_sample=best_dropped,
        path_changes=best_path_changes,
        seed=best_seed,
        deterministic=config.deterministic,
        execution_time_s=total_time,
        timing_breakdown={
            "path_generation_s": round(path_gen_time, 6),
            "rounding_s": round(rounding_time, 6),
        },
        rounding_diagnostics=best_diagnostics,
    )
