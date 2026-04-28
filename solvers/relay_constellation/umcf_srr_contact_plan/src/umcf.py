"""UMCF instance construction from dynamic sample graphs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .case_io import Case, Demand
from .dynamic_graph import GraphEdge, SampleGraph
from .time_grid import demand_indices


@dataclass(frozen=True)
class Commodity:
    """A routing commodity derived from an active demand."""

    demand_id: str
    source: str
    destination: str
    weight: float


@dataclass
class UMCFInstance:
    """Per-sample UMCF problem instance."""

    sample_index: int
    commodities: list[Commodity]
    # Adjacency: node -> list of (neighbor, distance_m)
    adjacency: dict[str, list[tuple[str, float]]]
    # Edge capacity for undirected edges, keyed by canonical (min, max) node pair
    edge_capacity: dict[tuple[str, str], int]
    # Node capacity (approximates degree cap in the oracle)
    node_capacity: dict[str, int]
    endpoint_ids: set[str] = field(default_factory=set)
    satellite_ids: set[str] = field(default_factory=set)


def build_umcf_instances(
    case: Case,
    sample_graphs: list[SampleGraph],
) -> list[UMCFInstance]:
    """Build a UMCF instance for every sample that has active demands.

    Edge capacities are initialised to 1 (matching the verifier's unit-capacity
    edge-disjoint allocation).  Node capacities are initialised from the manifest
    degree caps as a simplifying approximation.
    """
    # Pre-compute demand -> sample indices
    demand_samples: dict[str, tuple[int, ...]] = {}
    for demand in case.demands:
        demand_samples[demand.demand_id] = demand_indices(case.manifest, demand)

    # Invert: sample_index -> list of active demands
    active_demands_by_sample: dict[int, list[Demand]] = {}
    for demand in case.demands:
        for idx in demand_samples[demand.demand_id]:
            active_demands_by_sample.setdefault(idx, []).append(demand)

    instances: list[UMCFInstance] = []
    for graph in sample_graphs:
        idx = graph.sample_index
        active_demands = active_demands_by_sample.get(idx, [])
        if not active_demands:
            continue

        commodities = [
            Commodity(
                demand_id=d.demand_id,
                source=d.source_endpoint_id,
                destination=d.destination_endpoint_id,
                weight=d.weight,
            )
            for d in active_demands
        ]

        # Build cleaned adjacency (drop GraphEdge wrapper)
        adjacency: dict[str, list[tuple[str, float]]] = {}
        edge_capacity: dict[tuple[str, str], int] = {}
        seen_edges: set[tuple[str, str]] = set()

        for node, edges in graph.adjacency.items():
            adjacency.setdefault(node, [])
            for edge in edges:
                neighbor = edge.node_b
                adjacency[node].append((neighbor, edge.distance_m))
                canonical = (node, neighbor) if node < neighbor else (neighbor, node)
                if canonical not in seen_edges:
                    seen_edges.add(canonical)
                    edge_capacity[canonical] = 1

        # Node capacities from manifest degree caps
        node_capacity: dict[str, int] = {}
        for node in graph.nodes:
            if node in graph.endpoint_ids:
                node_capacity[node] = case.manifest.max_links_per_endpoint
            else:
                node_capacity[node] = case.manifest.max_links_per_satellite

        instances.append(
            UMCFInstance(
                sample_index=idx,
                commodities=commodities,
                adjacency=adjacency,
                edge_capacity=edge_capacity,
                node_capacity=node_capacity,
                endpoint_ids=set(graph.endpoint_ids),
                satellite_ids=set(graph.satellite_ids),
            )
        )

    return instances


def instance_summary(instances: list[UMCFInstance]) -> dict[str, Any]:
    """Return summary statistics for a list of UMCF instances."""
    if not instances:
        return {
            "num_instances": 0,
            "total_commodities": 0,
            "avg_commodities_per_instance": 0.0,
            "avg_nodes_per_instance": 0.0,
            "avg_edges_per_instance": 0.0,
        }

    total_commodities = sum(len(inst.commodities) for inst in instances)
    total_nodes = sum(len(inst.adjacency) for inst in instances)
    total_edges = sum(len(inst.edge_capacity) for inst in instances)
    return {
        "num_instances": len(instances),
        "total_commodities": total_commodities,
        "avg_commodities_per_instance": total_commodities / len(instances),
        "avg_nodes_per_instance": total_nodes / len(instances),
        "avg_edges_per_instance": total_edges / len(instances),
    }
