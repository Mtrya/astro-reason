"""Focused tests for relay_constellation UMCF/SRR solver action generation."""

from __future__ import annotations

from datetime import UTC, datetime
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
from solvers.relay_constellation.umcf_srr_contact_plan.src.umcf import (
    Commodity,
    UMCFInstance,
)
from solvers.relay_constellation.umcf_srr_contact_plan.src.srr import Path as SRRPath
from solvers.relay_constellation.umcf_srr_contact_plan.src.action_generation import (
    LinkAction,
    extract_edge_samples,
    repair_degree_caps,
    compact_actions,
    actions_to_json,
)


def _make_manifest() -> Manifest:
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

    node_capacity: dict[str, int] = {}
    all_nodes = set(adjacency.keys())
    for node in all_nodes:
        if node.startswith("ep"):
            node_capacity[node] = 2
        else:
            node_capacity[node] = 4

    endpoint_ids = {n for n in all_nodes if n.startswith("ep")}
    satellite_ids = all_nodes - endpoint_ids

    return UMCFInstance(
        sample_index=sample_index,
        commodities=commodities,
        adjacency=adjacency,
        edge_capacity=edge_capacity,
        node_capacity=node_capacity,
        endpoint_ids=endpoint_ids,
        satellite_ids=satellite_ids,
    )


class TestExtractEdgeSamples:
    def test_basic_extraction(self) -> None:
        inst = _make_instance(
            0,
            [Commodity("d1", "ep1", "ep2", 1.0)],
            {
                "ep1": [("sat1", 100.0)],
                "sat1": [("ep1", 100.0), ("ep2", 100.0)],
                "ep2": [("sat1", 100.0)],
            },
        )
        assignments = [{"d1": SRRPath(("ep1", "sat1", "ep2"), (("ep1", "sat1"), ("ep2", "sat1")), 200.0, 2)}]
        edge_samples = extract_edge_samples([inst], assignments)
        assert edge_samples == {
            ("ep1", "sat1"): {0},
            ("ep2", "sat1"): {0},
        }

    def test_multiple_samples(self) -> None:
        inst0 = _make_instance(
            0,
            [Commodity("d1", "ep1", "ep2", 1.0)],
            {"ep1": [("sat1", 100.0)], "sat1": [("ep1", 100.0), ("ep2", 100.0)], "ep2": [("sat1", 100.0)]},
        )
        inst1 = _make_instance(
            1,
            [Commodity("d1", "ep1", "ep2", 1.0)],
            {"ep1": [("sat1", 100.0)], "sat1": [("ep1", 100.0), ("ep2", 100.0)], "ep2": [("sat1", 100.0)]},
        )
        assignments = [
            {"d1": SRRPath(("ep1", "sat1", "ep2"), (("ep1", "sat1"), ("ep2", "sat1")), 200.0, 2)},
            {"d1": SRRPath(("ep1", "sat1", "ep2"), (("ep1", "sat1"), ("ep2", "sat1")), 200.0, 2)},
        ]
        edge_samples = extract_edge_samples([inst0, inst1], assignments)
        assert edge_samples == {
            ("ep1", "sat1"): {0, 1},
            ("ep2", "sat1"): {0, 1},
        }

    def test_shared_edge_across_demands(self) -> None:
        inst = _make_instance(
            0,
            [
                Commodity("d1", "ep1", "ep2", 10.0),
                Commodity("d2", "ep1", "ep3", 5.0),
            ],
            {
                "ep1": [("sat1", 100.0)],
                "sat1": [("ep1", 100.0), ("ep2", 100.0), ("ep3", 100.0)],
                "ep2": [("sat1", 100.0)],
                "ep3": [("sat1", 100.0)],
            },
        )
        assignments = [
            {
                "d1": SRRPath(("ep1", "sat1", "ep2"), (("ep1", "sat1"), ("ep2", "sat1")), 200.0, 2),
                "d2": SRRPath(("ep1", "sat1", "ep3"), (("ep1", "sat1"), ("ep3", "sat1")), 200.0, 2),
            }
        ]
        edge_samples = extract_edge_samples([inst], assignments)
        assert edge_samples[("ep1", "sat1")] == {0}


class TestRepairDegreeCaps:
    def test_drops_lowest_importance_first(self) -> None:
        """Satellite with degree 6 and cap 4 should drop the two lowest-importance edges."""
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
                    ("ep1", 100.0), ("ep2", 100.0), ("ep3", 100.0),
                    ("ep4", 100.0), ("ep5", 100.0), ("ep6", 100.0),
                ],
            },
        )
        inst.node_capacity["sat1"] = 4

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
        sat1_degree = sum(
            1 for edge in repaired if "sat1" in edge
        )
        assert sat1_degree == 4
        assert ("ep5", "sat1") not in repaired or 0 not in repaired[("ep5", "sat1")]
        assert ("ep6", "sat1") not in repaired or 0 not in repaired[("ep6", "sat1")]

    def test_respects_endpoint_caps(self) -> None:
        """Endpoint with degree 3 and cap 2 should drop one edge."""
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
        assignments = [
            {
                "d1": SRRPath(("ep1", "sat1", "ep2"), (("ep1", "sat1"), ("ep2", "sat1")), 200.0, 2),
                "d2": SRRPath(("ep1", "sat2", "ep3"), (("ep1", "sat2"), ("sat2", "ep3")), 200.0, 2),
            }
        ]
        edge_samples = extract_edge_samples([inst], assignments)
        repaired, summary = repair_degree_caps(
            edge_samples,
            [inst],
            assignments,
            max_links_per_satellite=4,
            max_links_per_endpoint=1,
            endpoint_ids={"ep1", "ep2", "ep3"},
        )
        assert summary["total_dropped_edges"] >= 1
        ep1_degree = sum(
            1 for edge in repaired if "ep1" in edge
        )
        assert ep1_degree <= 1

    def test_deterministic(self) -> None:
        """Same inputs must yield identical repair results."""
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
                    ("ep1", 100.0), ("ep2", 100.0), ("ep3", 100.0),
                    ("ep4", 100.0), ("ep5", 100.0), ("ep6", 100.0),
                ],
            },
        )
        inst.node_capacity["sat1"] = 4
        assignments = [
            {
                "d1": SRRPath(("ep1", "sat1", "ep2"), (("ep1", "sat1"), ("ep2", "sat1")), 200.0, 2),
                "d2": SRRPath(("ep3", "sat1", "ep4"), (("ep3", "sat1"), ("ep4", "sat1")), 200.0, 2),
                "d3": SRRPath(("ep5", "sat1", "ep6"), (("ep5", "sat1"), ("ep6", "sat1")), 200.0, 2),
            }
        ]
        edge_samples = extract_edge_samples([inst], assignments)
        repaired1, _ = repair_degree_caps(
            edge_samples, [inst], assignments, 4, 2, {"ep1", "ep2", "ep3", "ep4", "ep5", "ep6"}
        )
        repaired2, _ = repair_degree_caps(
            edge_samples, [inst], assignments, 4, 2, {"ep1", "ep2", "ep3", "ep4", "ep5", "ep6"}
        )
        assert repaired1 == repaired2


class TestCompactActions:
    def test_merges_consecutive_samples(self) -> None:
        manifest = _make_manifest()
        edge_samples = {
            ("ep1", "sat1"): {0, 1, 2, 4},
        }
        actions, summary = compact_actions(edge_samples, {"ep1"}, manifest)
        assert summary["num_actions"] == 2
        assert actions[0].start_time == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert actions[0].end_time == datetime(2024, 1, 1, 3, 0, 0, tzinfo=UTC)
        assert actions[1].start_time == datetime(2024, 1, 1, 4, 0, 0, tzinfo=UTC)
        assert actions[1].end_time == datetime(2024, 1, 1, 5, 0, 0, tzinfo=UTC)

    def test_grid_aligned_times(self) -> None:
        manifest = _make_manifest()
        edge_samples = {
            ("ep1", "sat1"): {5},
        }
        actions, _ = compact_actions(edge_samples, {"ep1"}, manifest)
        assert len(actions) == 1
        step = manifest.routing_step_s
        delta_start = (actions[0].start_time - manifest.horizon_start).total_seconds()
        delta_end = (actions[0].end_time - manifest.horizon_start).total_seconds()
        assert delta_start % step == 0
        assert delta_end % step == 0

    def test_no_overlap_same_link(self) -> None:
        manifest = _make_manifest()
        edge_samples = {
            ("ep1", "sat1"): {0, 2, 3},
        }
        actions, _ = compact_actions(edge_samples, {"ep1"}, manifest)
        assert len(actions) == 2
        for i in range(len(actions)):
            for j in range(i + 1, len(actions)):
                a, b = actions[i], actions[j]
                assert a.end_time <= b.start_time or b.end_time <= a.start_time

    def test_isl_action_has_sorted_satellites(self) -> None:
        manifest = _make_manifest()
        edge_samples = {
            ("sat2", "sat1"): {0},
        }
        actions, _ = compact_actions(edge_samples, set(), manifest)
        assert len(actions) == 1
        assert actions[0].action_type == "inter_satellite_link"
        assert actions[0].satellite_id_1 == "sat1"
        assert actions[0].satellite_id_2 == "sat2"


class TestActionsToJson:
    def test_ground_link_schema(self) -> None:
        manifest = _make_manifest()
        action = LinkAction(
            action_type="ground_link",
            start_time=manifest.horizon_start,
            end_time=manifest.horizon_start + __import__("datetime").timedelta(seconds=manifest.routing_step_s),
            endpoint_id="ep1",
            satellite_id="sat1",
        )
        json_actions = actions_to_json([action])
        assert len(json_actions) == 1
        payload = json_actions[0]
        assert payload["action_type"] == "ground_link"
        assert payload["endpoint_id"] == "ep1"
        assert payload["satellite_id"] == "sat1"
        assert payload["start_time"].endswith("Z")
        assert payload["end_time"].endswith("Z")
        assert "satellite_id_1" not in payload
        assert "satellite_id_2" not in payload

    def test_isl_schema(self) -> None:
        manifest = _make_manifest()
        action = LinkAction(
            action_type="inter_satellite_link",
            start_time=manifest.horizon_start,
            end_time=manifest.horizon_start + __import__("datetime").timedelta(seconds=manifest.routing_step_s),
            satellite_id_1="sat1",
            satellite_id_2="sat2",
        )
        json_actions = actions_to_json([action])
        assert len(json_actions) == 1
        payload = json_actions[0]
        assert payload["action_type"] == "inter_satellite_link"
        assert payload["satellite_id_1"] == "sat1"
        assert payload["satellite_id_2"] == "sat2"
        assert "endpoint_id" not in payload
        assert "satellite_id" not in payload

    def test_sorted_output(self) -> None:
        manifest = _make_manifest()
        actions = [
            LinkAction(
                action_type="ground_link",
                start_time=manifest.horizon_start,
                end_time=manifest.horizon_start + __import__("datetime").timedelta(seconds=manifest.routing_step_s),
                endpoint_id="ep2",
                satellite_id="sat1",
            ),
            LinkAction(
                action_type="ground_link",
                start_time=manifest.horizon_start,
                end_time=manifest.horizon_start + __import__("datetime").timedelta(seconds=manifest.routing_step_s),
                endpoint_id="ep1",
                satellite_id="sat1",
            ),
        ]
        json_actions = actions_to_json(actions)
        assert json_actions[0]["endpoint_id"] == "ep1"
        assert json_actions[1]["endpoint_id"] == "ep2"
