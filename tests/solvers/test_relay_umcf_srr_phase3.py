"""Focused tests for relay_constellation UMCF/SRR solver Phase 3 oracle."""

from __future__ import annotations

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
    load_case,
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
    k_shortest_paths,
    heuristic_probabilities,
    sequential_rounding,
    run_srr_oracle,
)


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
        # 4 undirected edges => 4 canonical keys
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
        # Shortest by hop count should be ep1-sat2-ep2 (1 hop)
        assert paths[0].nodes == ("ep1", "sat2", "ep2")
        # Second should be ep1-sat1-sat2-ep2 (2 hops)
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
        # No valid simple path exists that doesn't go through ep2 as intermediate
        # because ep1--sat1--ep2--sat2--ep3 is the only topology and ep2 is an endpoint
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
        # Only 1-hop path fits
        assert all(p.hop_count <= 2 for p in paths)


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
        # p1 should have higher probability due to penalty boost
        assert probs[0] > probs[1]
        assert pytest.approx(probs[0] + probs[1]) == 1.0


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

        config = SRRConfig(deterministic=True, k_paths=4)
        import random

        assignments, _ = sequential_rounding(inst, None, config, random.Random(42))
        # Only one path exists (ep1-sat1-ep2), capacity 1
        assert len(assignments) == 1
        assert "d1" in assignments  # largest weight wins

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

        config = SRRConfig(deterministic=True, k_paths=4)
        import random

        assignments1, _ = sequential_rounding(inst, None, config, random.Random(42))
        assignments2, _ = sequential_rounding(inst, None, config, random.Random(99))
        # Deterministic mode should give the same result regardless of RNG
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

        config = SRRConfig(deterministic=False, seed=42, k_paths=4)
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

        # First round: deterministic, pick shortest path
        config = SRRConfig(deterministic=True, k_paths=4, path_change_penalty=0.0)
        import random

        first, _ = sequential_rounding(inst, None, config, random.Random(42))
        prev = first

        # Second round with penalty: should pick same path
        config_pen = SRRConfig(deterministic=True, k_paths=4, path_change_penalty=5.0)
        second, _ = sequential_rounding(inst, prev, config_pen, random.Random(42))
        assert second[case.demands[0].demand_id].nodes == prev[case.demands[0].demand_id].nodes


class TestSmoke:
    def test_solve_produces_oracle_debug(self, tmp_path: Path) -> None:
        from solvers.relay_constellation.umcf_srr_contact_plan.src.solve import solve

        case_dir = REPO_ROOT / "benchmarks" / "relay_constellation" / "dataset" / "cases" / "test" / "case_0001"
        result = solve(case_dir, tmp_path / "solution")
        debug_dir = tmp_path / "solution" / "debug"
        assert (debug_dir / "umcf_instances.json").exists()
        assert (debug_dir / "srr_summary.json").exists()
        assert result["summary"]["srr_served_commodities"] >= 0
        assert result["summary"]["srr_dropped_commodities"] >= 0
        assert "srr_execution_time_s" in result["summary"]

    def test_solution_still_verifier_valid(self, tmp_path: Path) -> None:
        from benchmarks.relay_constellation.verifier import verify_solution
        from solvers.relay_constellation.umcf_srr_contact_plan.src.solve import solve

        case_dir = REPO_ROOT / "benchmarks" / "relay_constellation" / "dataset" / "cases" / "test" / "case_0001"
        result = solve(case_dir, tmp_path / "solution")
        solution_path = tmp_path / "solution" / "solution.json"
        verdict = verify_solution(case_dir, solution_path)
        assert verdict.valid is True
