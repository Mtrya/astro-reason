"""Focused tests for relay_constellation UMCF/SRR solver SRR oracle."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from solvers.relay_constellation.umcf_srr_contact_plan.src.case_io import (
    Case,
    Demand,
    Endpoint,
    Manifest,
    Satellite,
)
from solvers.relay_constellation.umcf_srr_contact_plan.src.dynamic_graph import (
    GraphEdge,
    SampleGraph,
)
from solvers.relay_constellation.umcf_srr_contact_plan.src.umcf import (
    Commodity,
    UMCFInstance,
    build_umcf_instances,
    instance_summary,
)
from solvers.relay_constellation.umcf_srr_contact_plan.src.srr import (
    SRRConfig,
    Path as SRRPath,
    build_path_sets,
    k_shortest_paths,
    heuristic_probabilities,
    sequential_rounding,
    run_srr_oracle,
)
from solvers.relay_constellation.umcf_srr_contact_plan.src.lp_relaxation import (
    LPRelaxationConfig,
    solve_path_restricted_lp,
)
from solvers.relay_constellation.umcf_srr_contact_plan.src.action_generation import (
    LinkAction,
    actions_to_json,
    compact_actions,
    extract_edge_samples,
    repair_degree_caps,
)


pytest.importorskip("yaml")


def _make_manifest() -> Manifest:
    from datetime import UTC, datetime

    return Manifest(
        case_id="test",
        epoch=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        horizon_start=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        horizon_end=datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC),
        routing_step_s=3600,
        max_added_satellites=2,
        min_altitude_m=400_000,
        max_altitude_m=600_000,
        max_eccentricity=0.01,
        min_inclination_deg=0.0,
        max_inclination_deg=90.0,
        max_isl_range_m=5_000_000,
        max_links_per_satellite=4,
        max_links_per_endpoint=2,
        max_ground_range_m=2_000_000,
    )


def _tiny_case() -> Case:
    """Return a minimal case with 2 endpoints and 2 satellites."""
    manifest = _make_manifest()
    sat1 = Satellite(satellite_id="sat1", state_eci_m_mps=None)  # type: ignore[arg-type]
    sat2 = Satellite(satellite_id="sat2", state_eci_m_mps=None)  # type: ignore[arg-type]
    ep1 = Endpoint(
        endpoint_id="ep1",
        latitude_deg=0.0,
        longitude_deg=0.0,
        altitude_m=0.0,
        min_elevation_deg=10.0,
        ecef_position_m=None,  # type: ignore[arg-type]
    )
    ep2 = Endpoint(
        endpoint_id="ep2",
        latitude_deg=1.0,
        longitude_deg=1.0,
        altitude_m=0.0,
        min_elevation_deg=10.0,
        ecef_position_m=None,  # type: ignore[arg-type]
    )
    return Case(
        case_dir=Path("."),
        manifest=manifest,
        backbone_satellites={"sat1": sat1, "sat2": sat2},
        ground_endpoints={"ep1": ep1, "ep2": ep2},
        demands=[
            Demand(
                demand_id="d1",
                source_endpoint_id="ep1",
                destination_endpoint_id="ep2",
                start_time=manifest.horizon_start,
                end_time=manifest.horizon_end,
                weight=1.0,
            )
        ],
    )


def _graph_triangle() -> SampleGraph:
    """ep1--sat1--sat2--ep2 plus ep1--sat2 direct."""
    g = SampleGraph(sample_index=0, endpoint_ids={"ep1", "ep2"}, satellite_ids={"sat1", "sat2"})
    g.add_edge(GraphEdge("ground_link", "ep1", "sat1", 1000.0))
    g.add_edge(GraphEdge("inter_satellite_link", "sat1", "sat2", 2000.0))
    g.add_edge(GraphEdge("ground_link", "sat2", "ep2", 1000.0))
    g.add_edge(GraphEdge("ground_link", "ep1", "sat2", 1500.0))
    return g


def _graph_single_path() -> SampleGraph:
    """ep1--sat1--ep2 (only one path)."""
    g = SampleGraph(sample_index=0, endpoint_ids={"ep1", "ep2"}, satellite_ids={"sat1"})
    g.add_edge(GraphEdge("ground_link", "ep1", "sat1", 1000.0))
    g.add_edge(GraphEdge("ground_link", "sat1", "ep2", 1000.0))
    return g


def _graph_with_intermediate_endpoint() -> SampleGraph:
    """ep1--sat1--ep2--sat2--ep3  (ep2 is an intermediate endpoint)."""
    g = SampleGraph(
        sample_index=0,
        endpoint_ids={"ep1", "ep2", "ep3"},
        satellite_ids={"sat1", "sat2"},
    )
    g.add_edge(GraphEdge("ground_link", "ep1", "sat1", 1000.0))
    g.add_edge(GraphEdge("ground_link", "sat1", "ep2", 1000.0))
    g.add_edge(GraphEdge("ground_link", "ep2", "sat2", 1000.0))
    g.add_edge(GraphEdge("ground_link", "sat2", "ep3", 1000.0))
    return g


def _make_instance(
    sample_index: int,
    commodities: list[Commodity],
    adjacency: dict[str, list[tuple[str, float]]],
) -> UMCFInstance:
    edge_capacity: dict[tuple[str, str], int] = {}
    seen: set[tuple[str, str]] = set()
    for node, neighbors in adjacency.items():
        for neighbor, _ in neighbors:
            canonical = (node, neighbor) if node < neighbor else (neighbor, node)
            if canonical not in seen:
                seen.add(canonical)
                edge_capacity[canonical] = 1

    all_nodes = set(adjacency)
    endpoint_ids = {node for node in all_nodes if node.startswith("ep")}
    satellite_ids = all_nodes - endpoint_ids
    node_capacity = {
        node: 2 if node in endpoint_ids else 4
        for node in all_nodes
    }

    return UMCFInstance(
        sample_index=sample_index,
        commodities=commodities,
        adjacency=adjacency,
        edge_capacity=edge_capacity,
        node_capacity=node_capacity,
        endpoint_ids=endpoint_ids,
        satellite_ids=satellite_ids,
    )


class TestUMCFConstruction:
    def test_build_instances_filters_empty_samples(self) -> None:
        case = _tiny_case()
        graph = _graph_triangle()
        instances = build_umcf_instances(case, [graph])
        assert len(instances) == 1
        inst = instances[0]
        assert inst.sample_index == 0
        assert len(inst.commodities) == 1
        assert inst.commodities[0].demand_id == "d1"

    def test_edge_capacity_initialized_to_one(self) -> None:
        case = _tiny_case()
        graph = _graph_triangle()
        instances = build_umcf_instances(case, [graph])
        inst = instances[0]
        assert len(inst.edge_capacity) == 4
        assert all(v == 1 for v in inst.edge_capacity.values())

    def test_node_capacity_respects_manifest(self) -> None:
        case = _tiny_case()
        graph = _graph_triangle()
        instances = build_umcf_instances(case, [graph])
        inst = instances[0]
        assert inst.node_capacity["ep1"] == case.manifest.max_links_per_endpoint
        assert inst.node_capacity["sat1"] == case.manifest.max_links_per_satellite

    def test_instance_summary(self) -> None:
        case = _tiny_case()
        graph = _graph_triangle()
        instances = build_umcf_instances(case, [graph])
        summary = instance_summary(instances)
        assert summary["num_instances"] == 1
        assert summary["total_commodities"] == 1


class TestPathGeneration:
    def test_k_shortest_paths_basic(self) -> None:
        graph = _graph_triangle()
        adj = {}
        for node, edges in graph.adjacency.items():
            adj.setdefault(node, [])
            for e in edges:
                adj[node].append((e.node_b, e.distance_m))

        paths = k_shortest_paths(
            adj, "ep1", "ep2", k=4, endpoint_ids={"ep1", "ep2"}, max_hops=5
        )
        assert len(paths) >= 2
        assert paths[0].nodes == ("ep1", "sat2", "ep2")
        assert paths[1].nodes == ("ep1", "sat1", "sat2", "ep2")

    def test_no_ground_transit_in_paths(self) -> None:
        graph = _graph_with_intermediate_endpoint()
        adj = {}
        for node, edges in graph.adjacency.items():
            adj.setdefault(node, [])
            for e in edges:
                adj[node].append((e.node_b, e.distance_m))

        paths = k_shortest_paths(
            adj, "ep1", "ep3", k=4, endpoint_ids={"ep1", "ep2", "ep3"}, max_hops=5
        )
        assert len(paths) == 0

    def test_k_shortest_paths_respects_max_hops(self) -> None:
        graph = _graph_triangle()
        adj = {}
        for node, edges in graph.adjacency.items():
            adj.setdefault(node, [])
            for e in edges:
                adj[node].append((e.node_b, e.distance_m))

        paths = k_shortest_paths(
            adj, "ep1", "ep2", k=10, endpoint_ids={"ep1", "ep2"}, max_hops=2
        )
        assert all(p.hop_count <= 2 for p in paths)

    def test_dijkstra_path_respects_max_hops(self) -> None:
        """When the shortest Dijkstra path exceeds max_hops, it should be excluded."""
        graph = _graph_triangle()
        adj = {}
        for node, edges in graph.adjacency.items():
            adj.setdefault(node, [])
            for e in edges:
                adj[node].append((e.node_b, e.distance_m))

        # The Dijkstra path ep1-sat2-ep2 is 1 hop, so max_hops=0 should exclude it
        paths = k_shortest_paths(
            adj, "ep1", "ep2", k=10, endpoint_ids={"ep1", "ep2"}, max_hops=0
        )
        assert len(paths) == 0


class TestHeuristicProbabilities:
    def test_uniform_base(self) -> None:
        p1 = SRRPath(("a", "b"), (("a", "b"),), 10.0, 1)
        p2 = SRRPath(("a", "c", "b"), (("a", "c"), ("c", "b")), 20.0, 2)
        probs = heuristic_probabilities([p1, p2], None, 1.0)
        assert len(probs) == 2
        assert pytest.approx(probs[0]) == 0.5
        assert pytest.approx(probs[1]) == 0.5

    def test_path_change_penalty_boost(self) -> None:
        p1 = SRRPath(("a", "b"), (("a", "b"),), 10.0, 1)
        p2 = SRRPath(("a", "c", "b"), (("a", "c"), ("c", "b")), 20.0, 2)
        prev = SRRPath(("a", "b"), (("a", "b"),), 10.0, 1)
        probs = heuristic_probabilities([p1, p2], prev, 1.0)
        assert probs[0] > probs[1]
        assert pytest.approx(probs[0] + probs[1]) == 1.0


class TestLPRelaxation:
    @pytest.fixture(autouse=True)
    def _requires_scipy(self) -> None:
        pytest.importorskip("scipy.optimize")

    def test_one_commodity_two_paths_assigns_unit_mass(self) -> None:
        inst = _make_instance(
            0,
            [Commodity("d1", "ep1", "ep2", 3.0)],
            {
                "ep1": [("sat1", 100.0), ("sat2", 100.0)],
                "ep2": [("sat1", 100.0), ("sat2", 100.0)],
                "sat1": [("ep1", 100.0), ("ep2", 100.0)],
                "sat2": [("ep1", 100.0), ("ep2", 100.0)],
            },
        )

        path_sets = build_path_sets(inst, SRRConfig(k_paths=4))
        result = solve_path_restricted_lp(inst, path_sets, LPRelaxationConfig())

        assert result.success is True
        assert pytest.approx(sum(result.path_values["d1"])) == 1.0
        assert pytest.approx(result.objective_value) == 3.0
        assert result.variable_count == 2

    def test_edge_contention_prioritizes_higher_weight(self) -> None:
        inst = _make_instance(
            0,
            [
                Commodity("d_low", "ep1", "ep2", 1.0),
                Commodity("d_high", "ep1", "ep2", 5.0),
            ],
            {
                "ep1": [("sat1", 100.0)],
                "ep2": [("sat1", 100.0)],
                "sat1": [("ep1", 100.0), ("ep2", 100.0)],
            },
        )

        path_sets = build_path_sets(inst, SRRConfig(k_paths=4))
        result = solve_path_restricted_lp(inst, path_sets, LPRelaxationConfig())

        assert result.success is True
        assert result.path_values["d_high"] == [1.0]
        assert result.path_values["d_low"] == [0.0]
        assert pytest.approx(result.objective_value) == 5.0

    def test_node_degree_contention_is_constrained(self) -> None:
        inst = UMCFInstance(
            sample_index=0,
            commodities=[
                Commodity("d_low", "ep3", "ep4", 1.0),
                Commodity("d_high", "ep1", "ep2", 5.0),
            ],
            adjacency={
                "ep1": [("sat1", 100.0)],
                "ep2": [("sat1", 100.0)],
                "ep3": [("sat1", 100.0)],
                "ep4": [("sat1", 100.0)],
                "sat1": [
                    ("ep1", 100.0),
                    ("ep2", 100.0),
                    ("ep3", 100.0),
                    ("ep4", 100.0),
                ],
            },
            edge_capacity={
                ("ep1", "sat1"): 1,
                ("ep2", "sat1"): 1,
                ("ep3", "sat1"): 1,
                ("ep4", "sat1"): 1,
            },
            node_capacity={
                "ep1": 1,
                "ep2": 1,
                "ep3": 1,
                "ep4": 1,
                "sat1": 2,
            },
            endpoint_ids={"ep1", "ep2", "ep3", "ep4"},
            satellite_ids={"sat1"},
        )

        path_sets = build_path_sets(inst, SRRConfig(k_paths=4))
        result = solve_path_restricted_lp(inst, path_sets, LPRelaxationConfig())

        assert result.success is True
        assert result.path_values["d_high"] == [1.0]
        assert result.path_values["d_low"] == [0.0]
        assert pytest.approx(result.objective_value) == 5.0

    def test_unreachable_commodity_is_recorded(self) -> None:
        inst = _make_instance(
            0,
            [
                Commodity("d1", "ep1", "ep2", 3.0),
                Commodity("d_missing", "ep1", "ep9", 9.0),
            ],
            {
                "ep1": [("sat1", 100.0)],
                "ep2": [("sat1", 100.0)],
                "sat1": [("ep1", 100.0), ("ep2", 100.0)],
            },
        )

        path_sets = build_path_sets(inst, SRRConfig(k_paths=4))
        result = solve_path_restricted_lp(inst, path_sets, LPRelaxationConfig())

        assert result.success is True
        assert result.path_values["d_missing"] == []
        assert result.zero_path_commodities == ["d_missing"]
        assert result.path_values["d1"] == [1.0]

    def test_run_srr_oracle_uses_lp_values_by_default(self) -> None:
        inst = _make_instance(
            0,
            [
                Commodity("d_low", "ep1", "ep2", 1.0),
                Commodity("d_high", "ep1", "ep2", 5.0),
            ],
            {
                "ep1": [("sat1", 100.0)],
                "ep2": [("sat1", 100.0)],
                "sat1": [("ep1", 100.0), ("ep2", 100.0)],
            },
        )

        result = run_srr_oracle([inst], SRRConfig(deterministic=True, k_paths=4))

        assert set(result.sample_assignments[0]) == {"d_high"}
        assert result.lp_diagnostics["num_lps"] == 1
        assert result.lp_diagnostics["successful_lps"] == 1
        assert result.rounding_diagnostics["commodities_dropped_lp_probability"] == 1


class TestSequentialRounding:
    def test_capacity_exhaustion(self) -> None:
        """Only the largest-weight commodity gets the single available path."""
        case = _tiny_case()
        case = Case(
            case_dir=case.case_dir,
            manifest=case.manifest,
            backbone_satellites=case.backbone_satellites,
            ground_endpoints=case.ground_endpoints,
            demands=[
                Demand("d1", "ep1", "ep2", case.manifest.horizon_start, case.manifest.horizon_end, 10.0),
                Demand("d2", "ep1", "ep2", case.manifest.horizon_start, case.manifest.horizon_end, 5.0),
                Demand("d3", "ep1", "ep2", case.manifest.horizon_start, case.manifest.horizon_end, 1.0),
            ],
        )
        graph = _graph_single_path()
        instances = build_umcf_instances(case, [graph])
        inst = instances[0]

        config = SRRConfig(deterministic=True, k_paths=4, probability_source="heuristic")
        import random

        assignments, _ = sequential_rounding(inst, None, config, random.Random(42))
        assert len(assignments) == 1
        assert "d1" in assignments

    def test_satellite_node_capacity_blocks_edge_disjoint_path(self) -> None:
        """A shared satellite degree cap should block otherwise edge-disjoint paths."""
        inst = UMCFInstance(
            sample_index=0,
            commodities=[
                Commodity("d_low", "ep3", "ep4", 5.0),
                Commodity("d_high", "ep1", "ep2", 10.0),
            ],
            adjacency={
                "ep1": [("sat1", 100.0)],
                "ep2": [("sat1", 100.0)],
                "ep3": [("sat1", 100.0)],
                "ep4": [("sat1", 100.0)],
                "sat1": [
                    ("ep1", 100.0), ("ep2", 100.0),
                    ("ep3", 100.0), ("ep4", 100.0),
                ],
            },
            edge_capacity={
                ("ep1", "sat1"): 1,
                ("ep2", "sat1"): 1,
                ("ep3", "sat1"): 1,
                ("ep4", "sat1"): 1,
            },
            node_capacity={
                "ep1": 1, "ep2": 1, "ep3": 1, "ep4": 1,
                "sat1": 2,
            },
            endpoint_ids={"ep1", "ep2", "ep3", "ep4"},
            satellite_ids={"sat1"},
        )

        config = SRRConfig(deterministic=True, k_paths=4, probability_source="heuristic")
        import random

        assignments, timing = sequential_rounding(inst, None, config, random.Random(42))
        assert set(assignments) == {"d_high"}
        diagnostics = timing["diagnostics"]
        assert diagnostics["paths_rejected_node_capacity"] == 1
        assert diagnostics["commodities_dropped_node_capacity"] == 1

    def test_endpoint_node_capacity_blocks_edge_disjoint_path(self) -> None:
        """A shared endpoint degree cap should be consumed inside rounding."""
        inst = UMCFInstance(
            sample_index=0,
            commodities=[
                Commodity("d1", "ep1", "ep2", 10.0),
                Commodity("d2", "ep1", "ep3", 5.0),
            ],
            adjacency={
                "ep1": [("sat1", 100.0), ("sat2", 100.0)],
                "ep2": [("sat1", 100.0)],
                "ep3": [("sat2", 100.0)],
                "sat1": [("ep1", 100.0), ("ep2", 100.0)],
                "sat2": [("ep1", 100.0), ("ep3", 100.0)],
            },
            edge_capacity={
                ("ep1", "sat1"): 1,
                ("ep2", "sat1"): 1,
                ("ep1", "sat2"): 1,
                ("ep3", "sat2"): 1,
            },
            node_capacity={
                "ep1": 1, "ep2": 1, "ep3": 1,
                "sat1": 2, "sat2": 2,
            },
            endpoint_ids={"ep1", "ep2", "ep3"},
            satellite_ids={"sat1", "sat2"},
        )

        config = SRRConfig(deterministic=True, k_paths=4, probability_source="heuristic")
        import random

        assignments, timing = sequential_rounding(inst, None, config, random.Random(42))
        assert set(assignments) == {"d1"}
        diagnostics = timing["diagnostics"]
        assert diagnostics["paths_rejected_node_capacity"] == 1
        assert diagnostics["commodities_dropped_node_capacity"] == 1

    def test_higher_weight_wins_node_capacity_conflict(self) -> None:
        """Commodity weight should dominate demand-id order when node capacity is scarce."""
        inst = UMCFInstance(
            sample_index=0,
            commodities=[
                Commodity("a_low", "ep3", "ep4", 1.0),
                Commodity("z_high", "ep1", "ep2", 10.0),
            ],
            adjacency={
                "ep1": [("sat1", 100.0)],
                "ep2": [("sat1", 100.0)],
                "ep3": [("sat1", 100.0)],
                "ep4": [("sat1", 100.0)],
                "sat1": [
                    ("ep1", 100.0), ("ep2", 100.0),
                    ("ep3", 100.0), ("ep4", 100.0),
                ],
            },
            edge_capacity={
                ("ep1", "sat1"): 1,
                ("ep2", "sat1"): 1,
                ("ep3", "sat1"): 1,
                ("ep4", "sat1"): 1,
            },
            node_capacity={
                "ep1": 1, "ep2": 1, "ep3": 1, "ep4": 1,
                "sat1": 2,
            },
            endpoint_ids={"ep1", "ep2", "ep3", "ep4"},
            satellite_ids={"sat1"},
        )

        config = SRRConfig(deterministic=True, k_paths=4, probability_source="heuristic")
        import random

        assignments, _ = sequential_rounding(inst, None, config, random.Random(42))
        assert set(assignments) == {"z_high"}

    def test_deterministic_mode(self) -> None:
        graph = _graph_triangle()
        adj = {}
        for node, edges in graph.adjacency.items():
            adj.setdefault(node, [])
            for e in edges:
                adj[node].append((e.node_b, e.distance_m))

        case = _tiny_case()
        inst = UMCFInstance(
            sample_index=0,
            commodities=[
                Commodity(
                    demand_id=case.demands[0].demand_id,
                    source=case.demands[0].source_endpoint_id,
                    destination=case.demands[0].destination_endpoint_id,
                    weight=case.demands[0].weight,
                ),
            ],
            adjacency=adj,
            edge_capacity={("ep1", "sat1"): 1, ("sat1", "sat2"): 1, ("ep2", "sat2"): 1, ("ep1", "sat2"): 1},
            node_capacity={"ep1": 2, "ep2": 2, "sat1": 4, "sat2": 4},
            endpoint_ids={"ep1", "ep2"},
            satellite_ids={"sat1", "sat2"},
        )

        config = SRRConfig(deterministic=True, k_paths=4, probability_source="heuristic")
        import random

        assignments1, _ = sequential_rounding(inst, None, config, random.Random(42))
        assignments2, _ = sequential_rounding(inst, None, config, random.Random(99))
        assert assignments1 == assignments2

    def test_seeded_reproducibility(self) -> None:
        graph = _graph_triangle()
        adj = {}
        for node, edges in graph.adjacency.items():
            adj.setdefault(node, [])
            for e in edges:
                adj[node].append((e.node_b, e.distance_m))

        case = _tiny_case()
        inst = UMCFInstance(
            sample_index=0,
            commodities=[
                Commodity(
                    demand_id=case.demands[0].demand_id,
                    source=case.demands[0].source_endpoint_id,
                    destination=case.demands[0].destination_endpoint_id,
                    weight=case.demands[0].weight,
                ),
            ],
            adjacency=adj,
            edge_capacity={("ep1", "sat1"): 1, ("sat1", "sat2"): 1, ("ep2", "sat2"): 1, ("ep1", "sat2"): 1},
            node_capacity={"ep1": 2, "ep2": 2, "sat1": 4, "sat2": 4},
            endpoint_ids={"ep1", "ep2"},
            satellite_ids={"sat1", "sat2"},
        )

        config = SRRConfig(deterministic=False, seed=42, k_paths=4, probability_source="heuristic")
        result1 = run_srr_oracle([inst], config)
        result2 = run_srr_oracle([inst], config)
        assert result1.sample_assignments == result2.sample_assignments

    def test_path_change_penalty_preference(self) -> None:
        """With penalty > 0, the oracle should prefer the previous path when feasible."""
        graph = _graph_triangle()
        adj = {}
        for node, edges in graph.adjacency.items():
            adj.setdefault(node, [])
            for e in edges:
                adj[node].append((e.node_b, e.distance_m))

        case = _tiny_case()
        inst = UMCFInstance(
            sample_index=0,
            commodities=[
                Commodity(
                    demand_id=case.demands[0].demand_id,
                    source=case.demands[0].source_endpoint_id,
                    destination=case.demands[0].destination_endpoint_id,
                    weight=case.demands[0].weight,
                ),
            ],
            adjacency=adj,
            edge_capacity={("ep1", "sat1"): 1, ("sat1", "sat2"): 1, ("ep2", "sat2"): 1, ("ep1", "sat2"): 1},
            node_capacity={"ep1": 2, "ep2": 2, "sat1": 4, "sat2": 4},
            endpoint_ids={"ep1", "ep2"},
            satellite_ids={"sat1", "sat2"},
        )

        config = SRRConfig(deterministic=True, k_paths=4, path_change_penalty=0.0, probability_source="heuristic")
        import random

        first, _ = sequential_rounding(inst, None, config, random.Random(42))
        prev = first

        config_pen = SRRConfig(deterministic=True, k_paths=4, path_change_penalty=5.0, probability_source="heuristic")
        second, _ = sequential_rounding(inst, prev, config_pen, random.Random(42))
        assert second[case.demands[0].demand_id].nodes == prev[case.demands[0].demand_id].nodes

    def test_multi_run_count_zero_rejected(self) -> None:
        """A non-positive multi_run_count should raise ValueError upfront."""
        case = _tiny_case()
        graph = _graph_single_path()
        instances = build_umcf_instances(case, [graph])
        config = SRRConfig(deterministic=True, multi_run_count=0)
        with pytest.raises(ValueError):
            run_srr_oracle(instances, config)

    def test_run_srr_oracle_exposes_rounding_diagnostics(self) -> None:
        inst = UMCFInstance(
            sample_index=0,
            commodities=[
                Commodity("d1", "ep1", "ep2", 10.0),
                Commodity("d2", "ep1", "ep3", 5.0),
            ],
            adjacency={
                "ep1": [("sat1", 100.0), ("sat2", 100.0)],
                "ep2": [("sat1", 100.0)],
                "ep3": [("sat2", 100.0)],
                "sat1": [("ep1", 100.0), ("ep2", 100.0)],
                "sat2": [("ep1", 100.0), ("ep3", 100.0)],
            },
            edge_capacity={
                ("ep1", "sat1"): 1,
                ("ep2", "sat1"): 1,
                ("ep1", "sat2"): 1,
                ("ep3", "sat2"): 1,
            },
            node_capacity={
                "ep1": 1, "ep2": 1, "ep3": 1,
                "sat1": 2, "sat2": 2,
            },
            endpoint_ids={"ep1", "ep2", "ep3"},
            satellite_ids={"sat1", "sat2"},
        )

        result = run_srr_oracle([inst], SRRConfig(deterministic=True, k_paths=4, probability_source="heuristic"))
        assert result.rounding_diagnostics["paths_rejected_node_capacity"] == 1
        assert result.rounding_diagnostics["commodities_dropped_node_capacity"] == 1


class TestActionGeneration:
    def test_extract_edge_samples_basic(self) -> None:
        inst = _make_instance(
            0,
            [Commodity("d1", "ep1", "ep2", 1.0)],
            {
                "ep1": [("sat1", 100.0)],
                "sat1": [("ep1", 100.0), ("ep2", 100.0)],
                "ep2": [("sat1", 100.0)],
            },
        )
        assignments = [
            {
                "d1": SRRPath(
                    ("ep1", "sat1", "ep2"),
                    (("ep1", "sat1"), ("ep2", "sat1")),
                    200.0,
                    2,
                )
            }
        ]

        edge_samples = extract_edge_samples([inst], assignments)

        assert edge_samples == {
            ("ep1", "sat1"): {0},
            ("ep2", "sat1"): {0},
        }

    def test_repair_no_op_when_srr_consumes_node_caps(self) -> None:
        inst = _make_instance(
            0,
            [
                Commodity("d1", "ep1", "ep2", 10.0),
                Commodity("d2", "ep1", "ep3", 5.0),
            ],
            {
                "ep1": [("sat1", 100.0), ("sat2", 100.0)],
                "ep2": [("sat1", 100.0)],
                "ep3": [("sat2", 100.0)],
                "sat1": [("ep1", 100.0), ("ep2", 100.0)],
                "sat2": [("ep1", 100.0), ("ep3", 100.0)],
            },
        )
        inst.node_capacity["ep1"] = 1

        import random

        assignments, _ = sequential_rounding(
            inst,
            None,
            SRRConfig(deterministic=True, k_paths=4, probability_source="heuristic"),
            random.Random(42),
        )
        edge_samples = extract_edge_samples([inst], [assignments])
        repaired, summary = repair_degree_caps(
            edge_samples,
            [inst],
            [assignments],
            max_links_per_satellite=4,
            max_links_per_endpoint=1,
            endpoint_ids={"ep1", "ep2", "ep3"},
        )

        assert summary["total_dropped_edges"] == 0
        assert repaired == edge_samples

    def test_repair_drops_lowest_importance_first(self) -> None:
        inst = _make_instance(
            0,
            [
                Commodity("d1", "ep1", "ep2", 10.0),
                Commodity("d2", "ep3", "ep4", 5.0),
                Commodity("d3", "ep5", "ep6", 1.0),
            ],
            {
                "ep1": [("sat1", 100.0)],
                "ep2": [("sat1", 100.0)],
                "ep3": [("sat1", 100.0)],
                "ep4": [("sat1", 100.0)],
                "ep5": [("sat1", 100.0)],
                "ep6": [("sat1", 100.0)],
                "sat1": [
                    ("ep1", 100.0),
                    ("ep2", 100.0),
                    ("ep3", 100.0),
                    ("ep4", 100.0),
                    ("ep5", 100.0),
                    ("ep6", 100.0),
                ],
            },
        )
        assignments = [
            {
                "d1": SRRPath(("ep1", "sat1", "ep2"), (("ep1", "sat1"), ("ep2", "sat1")), 200.0, 2),
                "d2": SRRPath(("ep3", "sat1", "ep4"), (("ep3", "sat1"), ("ep4", "sat1")), 200.0, 2),
                "d3": SRRPath(("ep5", "sat1", "ep6"), (("ep5", "sat1"), ("ep6", "sat1")), 200.0, 2),
            }
        ]

        edge_samples = extract_edge_samples([inst], assignments)
        repaired, summary = repair_degree_caps(
            edge_samples,
            [inst],
            assignments,
            max_links_per_satellite=4,
            max_links_per_endpoint=2,
            endpoint_ids={"ep1", "ep2", "ep3", "ep4", "ep5", "ep6"},
        )

        assert summary["total_dropped_edges"] == 2
        assert sum(1 for edge in repaired if "sat1" in edge) == 4
        assert ("ep5", "sat1") not in repaired or 0 not in repaired[("ep5", "sat1")]
        assert ("ep6", "sat1") not in repaired or 0 not in repaired[("ep6", "sat1")]

    def test_compact_actions_merges_consecutive_samples(self) -> None:
        manifest = _make_manifest()
        edge_samples = {
            ("ep1", "sat1"): {0, 1, 2, 4},
        }

        actions, summary = compact_actions(edge_samples, {"ep1"}, manifest)

        assert summary["num_actions"] == 2
        assert actions[0].start_time == manifest.horizon_start
        assert actions[0].end_time == manifest.horizon_start + timedelta(hours=3)
        assert actions[1].start_time == manifest.horizon_start + timedelta(hours=4)
        assert actions[1].end_time == manifest.horizon_start + timedelta(hours=5)

    def test_actions_to_json_ground_and_isl_schema(self) -> None:
        manifest = _make_manifest()
        ground = LinkAction(
            action_type="ground_link",
            start_time=manifest.horizon_start,
            end_time=manifest.horizon_start + timedelta(seconds=manifest.routing_step_s),
            endpoint_id="ep1",
            satellite_id="sat1",
        )
        isl = LinkAction(
            action_type="inter_satellite_link",
            start_time=manifest.horizon_start,
            end_time=manifest.horizon_start + timedelta(seconds=manifest.routing_step_s),
            satellite_id_1="sat1",
            satellite_id_2="sat2",
        )

        payload = actions_to_json([isl, ground])

        assert payload[0]["action_type"] == "ground_link"
        assert payload[0]["endpoint_id"] == "ep1"
        assert payload[0]["satellite_id"] == "sat1"
        assert "satellite_id_1" not in payload[0]
        assert payload[1]["action_type"] == "inter_satellite_link"
        assert payload[1]["satellite_id_1"] == "sat1"
        assert payload[1]["satellite_id_2"] == "sat2"
        assert "endpoint_id" not in payload[1]
