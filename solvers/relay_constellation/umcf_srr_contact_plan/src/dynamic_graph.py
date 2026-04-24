"""Per-sample dynamic communication graph construction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .case_io import Case, Endpoint, Satellite
from .link_geometry import ground_links_feasible, isl_links_feasible
from .propagation import propagate_all_to_samples


@dataclass(frozen=True)
class GraphEdge:
    edge_type: str  # "ground_link" or "inter_satellite_link"
    node_a: str
    node_b: str
    distance_m: float
    capacity: int = 1


@dataclass
class SampleGraph:
    sample_index: int
    nodes: set[str] = field(default_factory=set)
    adjacency: dict[str, list[GraphEdge]] = field(default_factory=dict)
    endpoint_ids: set[str] = field(default_factory=set)
    satellite_ids: set[str] = field(default_factory=set)

    def add_edge(self, edge: GraphEdge) -> None:
        self.nodes.add(edge.node_a)
        self.nodes.add(edge.node_b)
        self.adjacency.setdefault(edge.node_a, []).append(edge)
        # Undirected: add reverse too
        reverse = GraphEdge(
            edge_type=edge.edge_type,
            node_a=edge.node_b,
            node_b=edge.node_a,
            distance_m=edge.distance_m,
            capacity=edge.capacity,
        )
        self.adjacency.setdefault(edge.node_b, []).append(reverse)


def build_sample_graphs(
    case: Case,
    satellites: dict[str, Satellite],
    positions_ecef: dict[str, np.ndarray] | None = None,
) -> list[SampleGraph]:
    """Build a communication graph for every routing sample.

    Parameters
    ----------
    satellites : dict[str, Satellite]
        All satellites to include (backbone + any candidates).
    positions_ecef : optional pre-computed ECEF positions
        If None, propagation is run internally.

    Returns
    -------
    list[SampleGraph]
        One graph per sample index.
    """
    if positions_ecef is None:
        positions_ecef = propagate_all_to_samples(case.manifest, satellites)

    # Compute feasibility masks and distances
    ground_feasible, ground_distances = ground_links_feasible(
        case.manifest,
        case.ground_endpoints,
        positions_ecef,
    )
    isl_feasible, isl_distances = isl_links_feasible(
        case.manifest,
        positions_ecef,
    )

    n_samples = case.manifest.total_samples
    graphs: list[SampleGraph] = []

    satellite_ids = sorted(satellites.keys())
    endpoint_ids = sorted(case.ground_endpoints.keys())

    for sample_index in range(n_samples):
        graph = SampleGraph(
            sample_index=sample_index,
            endpoint_ids=set(endpoint_ids),
            satellite_ids=set(satellite_ids),
        )

        # Ground links
        for endpoint_id in endpoint_ids:
            for sat_id in satellite_ids:
                if ground_feasible[endpoint_id][sat_id][sample_index]:
                    graph.add_edge(
                        GraphEdge(
                            edge_type="ground_link",
                            node_a=endpoint_id,
                            node_b=sat_id,
                            distance_m=float(ground_distances[endpoint_id][sat_id][sample_index]),
                        )
                    )

        # ISLs
        for i, sid_i in enumerate(satellite_ids):
            for j in range(i + 1, len(satellite_ids)):
                sid_j = satellite_ids[j]
                if isl_feasible[sid_i][sid_j][sample_index]:
                    graph.add_edge(
                        GraphEdge(
                            edge_type="inter_satellite_link",
                            node_a=sid_i,
                            node_b=sid_j,
                            distance_m=float(isl_distances[sid_i][sid_j][sample_index]),
                        )
                    )

        graphs.append(graph)

    return graphs


def graph_summary(graphs: list[SampleGraph]) -> dict[str, Any]:
    """Return summary statistics for a list of sample graphs."""
    total_edges = 0
    total_nodes = 0
    for g in graphs:
        total_edges += sum(len(edges) for edges in g.adjacency.values()) // 2
        total_nodes += len(g.nodes)
    return {
        "num_samples": len(graphs),
        "avg_nodes": total_nodes / len(graphs) if graphs else 0.0,
        "avg_edges": total_edges / len(graphs) if graphs else 0.0,
        "total_edges": total_edges,
    }
