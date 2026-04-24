"""Focused tests for Phase 3: greedy contact scheduler, interval compaction, and action output."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import pytest

from solvers.relay_constellation.mclp_teg_contact_plan.src.case_io import (
    BackboneSatellite,
    Constraints,
    DemandWindow,
    Demands,
    GroundEndpoint,
    Manifest,
    Network,
    Case,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.link_cache import LinkRecord
from solvers.relay_constellation.mclp_teg_contact_plan.src.scheduler import (
    build_per_sample_links,
    compact_intervals,
    greedy_select_links,
    score_ground_link,
    score_isl,
    run_scheduler,
    _local_validate,
    _build_ground_adjacency_at_sample,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.time_grid import build_time_grid


def _make_tiny_case(
    demand_windows: list[DemandWindow],
    backbone_sats: list[BackboneSatellite] | None = None,
    max_added: int = 2,
    max_links_per_satellite: int = 3,
    max_links_per_endpoint: int = 1,
) -> Case:
    """Build a minimal Case for unit tests."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    constraints = Constraints(
        max_added_satellites=max_added,
        min_altitude_m=500_000.0,
        max_altitude_m=600_000.0,
        max_eccentricity=0.01,
        min_inclination_deg=0.0,
        max_inclination_deg=90.0,
        max_isl_range_m=50_000_000.0,
        max_links_per_satellite=max_links_per_satellite,
        max_links_per_endpoint=max_links_per_endpoint,
        max_ground_range_m=None,
    )
    manifest = Manifest(
        benchmark="relay_constellation",
        case_id="case_tiny",
        constraints=constraints,
        epoch=epoch,
        horizon_end=datetime(2026, 1, 1, 1, 0, 0, tzinfo=timezone.utc),
        horizon_start=epoch,
        routing_step_s=300,
        seed=42,
    )
    if backbone_sats is None:
        backbone_sats = [
            BackboneSatellite(
                satellite_id="backbone_1",
                x_m=7_000_000.0,
                y_m=0.0,
                z_m=0.0,
                vx_m_s=0.0,
                vy_m_s=7_000.0,
                vz_m_s=0.0,
            ),
        ]
    endpoints = [
        GroundEndpoint(
            endpoint_id="ep_src",
            latitude_deg=0.0,
            longitude_deg=0.0,
            altitude_m=0.0,
            min_elevation_deg=5.0,
        ),
        GroundEndpoint(
            endpoint_id="ep_dst",
            latitude_deg=10.0,
            longitude_deg=0.0,
            altitude_m=0.0,
            min_elevation_deg=5.0,
        ),
    ]
    network = Network(
        backbone_satellites=tuple(backbone_sats),
        ground_endpoints=tuple(endpoints),
    )
    demands = Demands(demanded_windows=tuple(demand_windows))
    return Case(manifest=manifest, network=network, demands=demands)


def test_build_per_sample_links() -> None:
    records = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=1, node_a="ep_src", node_b="sat_b", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=1, node_a="sat_a", node_b="sat_b", distance_m=1e6, link_type="isl"),
    ]
    per_sample = build_per_sample_links(records)
    assert set(per_sample.keys()) == {0, 1}
    assert len(per_sample[0]) == 2
    assert len(per_sample[1]) == 2
    assert all(r.link_type == "ground" for r in per_sample[0])
    assert all(r.link_type in ("ground", "isl") for r in per_sample[1])


def test_score_ground_link_with_active_demands() -> None:
    rec = LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_a", distance_m=1e6, link_type="ground")
    demands = [
        DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            weight=5.0,
        ),
        DemandWindow(
            demand_id="d2",
            source_endpoint_id="ep_dst",
            destination_endpoint_id="ep_src",
            start_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            weight=3.0,
        ),
    ]
    assert score_ground_link(rec, demands) == 8.0

    rec2 = LinkRecord(sample_index=0, node_a="ep_other", node_b="sat_a", distance_m=1e6, link_type="ground")
    assert score_ground_link(rec2, demands) == 0.0


def test_score_isl_connects_complementary_ground_links() -> None:
    """ISL utility is positive when it bridges a source-satellite to a destination-satellite."""
    rec = LinkRecord(sample_index=0, node_a="sat_a", node_b="sat_b", distance_m=1e6, link_type="isl")
    demands = [
        DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            weight=7.0,
        ),
    ]
    sat_to_eps = {
        "sat_a": {"ep_src"},
        "sat_b": {"ep_dst"},
    }
    assert score_isl(rec, demands, sat_to_eps) == 7.0

    # Reverse mapping should also work
    sat_to_eps_rev = {
        "sat_a": {"ep_dst"},
        "sat_b": {"ep_src"},
    }
    assert score_isl(rec, demands, sat_to_eps_rev) == 7.0


def test_score_isl_zero_when_no_ground_access() -> None:
    rec = LinkRecord(sample_index=0, node_a="sat_a", node_b="sat_b", distance_m=1e6, link_type="isl")
    demands = [
        DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            weight=7.0,
        ),
    ]
    sat_to_eps = {
        "sat_a": set(),
        "sat_b": set(),
    }
    assert score_isl(rec, demands, sat_to_eps) == 0.0


def test_greedy_select_respects_satellite_degree_cap() -> None:
    """If a satellite already has max_links_per_satellite links, no more links involving it are selected."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    demands = [
        DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=epoch,
            end_time=epoch,
            weight=1.0,
        ),
    ]
    case = _make_tiny_case(demands, max_links_per_satellite=1, max_links_per_endpoint=10)
    sample_times = build_time_grid(case.manifest.horizon_start, case.manifest.horizon_end, case.manifest.routing_step_s)

    # sat_a can see both endpoints, plus an ISL to sat_b
    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="sat_a", node_b="sat_b", distance_m=1e6, link_type="isl"),
    ]

    selected = greedy_select_links(0, links, demands, max_links_per_satellite=1, max_links_per_endpoint=10)
    # sat_a can only have 1 link. The highest-utility link should be selected.
    # Both ground links have utility=1, ISL has utility=0 (no ground access for sat_b)
    sat_a_count = sum(1 for k in selected if "sat_a" in (k[1], k[2]))
    assert sat_a_count <= 1


def test_greedy_select_respects_endpoint_degree_cap() -> None:
    """Each endpoint can have at most max_links_per_endpoint ground links."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    demands = [
        DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=epoch,
            end_time=epoch,
            weight=1.0,
        ),
    ]
    case = _make_tiny_case(demands, max_links_per_satellite=10, max_links_per_endpoint=1)
    sample_times = build_time_grid(case.manifest.horizon_start, case.manifest.horizon_end, case.manifest.routing_step_s)

    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_b", distance_m=1e6, link_type="ground"),
    ]

    selected = greedy_select_links(0, links, demands, max_links_per_satellite=10, max_links_per_endpoint=1)
    ep_src_count = sum(1 for k in selected if k[1] == "ep_src")
    assert ep_src_count <= 1


def test_greedy_select_no_duplicate_link_at_same_sample() -> None:
    """The same physical link cannot be selected twice at the same sample."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    demands = []
    case = _make_tiny_case(demands)
    links = [
        LinkRecord(sample_index=0, node_a="sat_a", node_b="sat_b", distance_m=1e6, link_type="isl"),
    ]
    selected = greedy_select_links(0, links, demands, max_links_per_satellite=3, max_links_per_endpoint=1)
    assert len(selected) == 1


def test_greedy_select_deterministic_tiebreak() -> None:
    """Same input must produce the same output every time."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    demands = [
        DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=epoch,
            end_time=epoch,
            weight=1.0,
        ),
    ]
    case = _make_tiny_case(demands)
    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_b", distance_m=1e6, link_type="ground"),
    ]
    selected1 = greedy_select_links(0, links, demands, max_links_per_satellite=3, max_links_per_endpoint=1)
    selected2 = greedy_select_links(0, links, demands, max_links_per_satellite=3, max_links_per_endpoint=1)
    assert selected1 == selected2


def test_compact_intervals_consecutive_samples() -> None:
    """A link selected at consecutive samples becomes a single action."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    sample_times = tuple(epoch + timedelta(seconds=300 * i) for i in range(5))
    selected = {
        0: {("ground", "ep_src", "sat_a")},
        1: {("ground", "ep_src", "sat_a")},
        2: {("ground", "ep_src", "sat_a")},
    }
    actions = compact_intervals(selected, sample_times, routing_step_s=300)
    assert len(actions) == 1
    assert actions[0]["start_time"] == "2026-01-01T00:00:00Z"
    # end_time should be sample 3 (exclusive end for covering 0,1,2)
    assert actions[0]["end_time"] == "2026-01-01T00:15:00Z"


def test_compact_intervals_split_gap() -> None:
    """A gap in consecutive samples creates two separate actions."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    sample_times = tuple(epoch + timedelta(seconds=300 * i) for i in range(6))
    selected = {
        0: {("ground", "ep_src", "sat_a")},
        1: {("ground", "ep_src", "sat_a")},
        3: {("ground", "ep_src", "sat_a")},
        4: {("ground", "ep_src", "sat_a")},
    }
    actions = compact_intervals(selected, sample_times, routing_step_s=300)
    assert len(actions) == 2
    # First action covers samples 0-1
    assert actions[0]["start_time"] == "2026-01-01T00:00:00Z"
    assert actions[0]["end_time"] == "2026-01-01T00:10:00Z"
    # Second action covers samples 3-4
    assert actions[1]["start_time"] == "2026-01-01T00:15:00Z"
    assert actions[1]["end_time"] == "2026-01-01T00:25:00Z"


def test_action_schema_ground_link() -> None:
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    sample_times = tuple(epoch + timedelta(seconds=300 * i) for i in range(2))
    selected = {0: {("ground", "ep_src", "sat_a")}}
    actions = compact_intervals(selected, sample_times, routing_step_s=300)
    assert len(actions) == 1
    a = actions[0]
    assert a["action_type"] == "ground_link"
    assert a["endpoint_id"] == "ep_src"
    assert a["satellite_id"] == "sat_a"
    assert "start_time" in a
    assert "end_time" in a


def test_action_schema_isl() -> None:
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    sample_times = tuple(epoch + timedelta(seconds=300 * i) for i in range(2))
    selected = {0: {("isl", "sat_a", "sat_b")}}
    actions = compact_intervals(selected, sample_times, routing_step_s=300)
    assert len(actions) == 1
    a = actions[0]
    assert a["action_type"] == "inter_satellite_link"
    assert a["satellite_id_1"] == "sat_a"
    assert a["satellite_id_2"] == "sat_b"
    assert "start_time" in a
    assert "end_time" in a


def test_scheduler_runnable_on_tiny_case() -> None:
    """End-to-end scheduler run on a synthetic tiny case."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    demands = [
        DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=epoch,
            end_time=epoch + timedelta(seconds=600),
            weight=1.0,
        ),
    ]
    case = _make_tiny_case(demands)
    sample_times = build_time_grid(case.manifest.horizon_start, case.manifest.horizon_end, case.manifest.routing_step_s)

    # sat_a sees both endpoints at sample 0, sat_b sees neither
    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="sat_a", node_b="sat_b", distance_m=1e6, link_type="isl"),
    ]

    actions, summary = run_scheduler(case, sample_times, links)
    assert isinstance(actions, list)
    assert summary["num_actions"] >= 0
    assert summary["local_violations"] == []


def test_local_validate_catches_overlap() -> None:
    """Solver-side validation should detect overlapping actions on the same link."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    demands = []
    case = _make_tiny_case(demands)
    sample_times = build_time_grid(case.manifest.horizon_start, case.manifest.horizon_end, case.manifest.routing_step_s)

    actions = [
        {
            "action_type": "ground_link",
            "endpoint_id": "ep_src",
            "satellite_id": "sat_a",
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T00:10:00Z",
        },
        {
            "action_type": "ground_link",
            "endpoint_id": "ep_src",
            "satellite_id": "sat_a",
            "start_time": "2026-01-01T00:05:00Z",
            "end_time": "2026-01-01T00:15:00Z",
        },
    ]
    violations = _local_validate(actions, case, sample_times)
    assert any("overlap" in v.lower() for v in violations)


def test_local_validate_catches_degree_cap() -> None:
    """Solver-side validation should detect per-sample degree cap violations."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    demands = []
    case = _make_tiny_case(demands, max_links_per_satellite=1, max_links_per_endpoint=10)
    sample_times = build_time_grid(case.manifest.horizon_start, case.manifest.horizon_end, case.manifest.routing_step_s)

    actions = [
        {
            "action_type": "ground_link",
            "endpoint_id": "ep_src",
            "satellite_id": "sat_a",
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T00:05:00Z",
        },
        {
            "action_type": "ground_link",
            "endpoint_id": "ep_dst",
            "satellite_id": "sat_a",
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T00:05:00Z",
        },
    ]
    violations = _local_validate(actions, case, sample_times)
    assert any("exceeding max" in v.lower() for v in violations)
