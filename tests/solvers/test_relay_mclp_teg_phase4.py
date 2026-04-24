"""Focused tests for Phase 4: MILP contact scheduler, bounds, and fallback."""

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
from solvers.relay_constellation.mclp_teg_contact_plan.src.milp_scheduler import (
    milp_scheduler_available,
    milp_select_links,
    run_milp_scheduler,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.scheduler import (
    greedy_select_links,
    run_scheduler,
    _build_ground_adjacency_at_sample,
    score_ground_link,
    score_isl,
    _normalize_link_key,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.time_grid import build_time_grid


def _make_tiny_case(
    demand_windows: list[DemandWindow],
    backbone_sats: list[BackboneSatellite] | None = None,
    max_added: int = 2,
    max_links_per_satellite: int = 3,
    max_links_per_endpoint: int = 1,
    horizon_minutes: int = 60,
    routing_step_s: int = 300,
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
        horizon_end=epoch + timedelta(minutes=horizon_minutes),
        horizon_start=epoch,
        routing_step_s=routing_step_s,
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


@pytest.mark.skipif(not milp_scheduler_available(), reason="PuLP/CBC not available")
def test_milp_select_links_beats_greedy_on_contrived_case() -> None:
    """On a case where greedy's first pick blocks a better combination, MILP should do at least as well."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    demands = [
        DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=epoch,
            end_time=epoch,
            weight=5.0,
        ),
        DemandWindow(
            demand_id="d2",
            source_endpoint_id="ep_dst",
            destination_endpoint_id="ep_src",
            start_time=epoch,
            end_time=epoch,
            weight=4.0,
        ),
    ]
    case = _make_tiny_case(demands, max_links_per_satellite=1, max_links_per_endpoint=1)

    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat1", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat1", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat2", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat2", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="sat1", node_b="sat2", distance_m=1e6, link_type="isl"),
    ]

    _, sat_to_eps = _build_ground_adjacency_at_sample(links, 0)

    def total_utility(selected: set[tuple[str, str, str]]) -> float:
        u = 0.0
        for key in selected:
            link_type, node_a, node_b = key
            for rec in links:
                if rec.link_type == link_type:
                    nkey = _normalize_link_key(rec.link_type, rec.node_a, rec.node_b)
                    if nkey == key:
                        if link_type == "ground":
                            u += score_ground_link(rec, demands)
                        else:
                            u += score_isl(rec, demands, sat_to_eps)
                        break
        return u

    greedy_selected = greedy_select_links(0, links, demands, max_links_per_satellite=1, max_links_per_endpoint=1)
    milp_selected = milp_select_links(0, links, demands, max_links_per_satellite=1, max_links_per_endpoint=1)

    assert milp_selected is not None
    greedy_u = total_utility(greedy_selected)
    milp_u = total_utility(milp_selected)
    assert milp_u >= greedy_u, f"MILP utility {milp_u} < greedy utility {greedy_u}"


@pytest.mark.skipif(not milp_scheduler_available(), reason="PuLP/CBC not available")
def test_milp_select_links_respects_satellite_degree_cap() -> None:
    """MILP output must never exceed per-satellite degree cap."""
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

    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat1", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat1", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="sat1", node_b="sat2", distance_m=1e6, link_type="isl"),
    ]

    selected = milp_select_links(0, links, demands, max_links_per_satellite=1, max_links_per_endpoint=10)
    assert selected is not None
    sat1_count = sum(1 for k in selected if "sat1" in (k[1], k[2]))
    assert sat1_count <= 1


@pytest.mark.skipif(not milp_scheduler_available(), reason="PuLP/CBC not available")
def test_milp_select_links_respects_endpoint_degree_cap() -> None:
    """MILP output must never exceed per-endpoint degree cap."""
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

    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat1", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat2", distance_m=1e6, link_type="ground"),
    ]

    selected = milp_select_links(0, links, demands, max_links_per_satellite=10, max_links_per_endpoint=1)
    assert selected is not None
    ep_src_count = sum(1 for k in selected if k[1] == "ep_src")
    assert ep_src_count <= 1


@pytest.mark.skipif(not milp_scheduler_available(), reason="PuLP/CBC not available")
def test_milp_select_links_no_duplicate_links() -> None:
    """The same physical link cannot be selected twice by MILP."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    demands = []
    case = _make_tiny_case(demands)
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
    # Include duplicate ISL records for the same physical link
    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat_b", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="sat_a", node_b="sat_b", distance_m=1e6, link_type="isl"),
        LinkRecord(sample_index=0, node_a="sat_b", node_b="sat_a", distance_m=1e6, link_type="isl"),
    ]
    selected = milp_select_links(0, links, demands, max_links_per_satellite=3, max_links_per_endpoint=1)
    assert selected is not None
    # The normalized ISL key should appear at most once
    isl_keys = [k for k in selected if k[0] == "isl"]
    assert len(isl_keys) <= 1


@pytest.mark.skipif(not milp_scheduler_available(), reason="PuLP/CBC not available")
def test_milp_scheduler_runnable_on_tiny_case() -> None:
    """End-to-end MILP scheduler run on a synthetic tiny case."""
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

    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="sat_a", node_b="sat_b", distance_m=1e6, link_type="isl"),
    ]

    result = run_milp_scheduler(case, sample_times, links)
    assert result is not None
    actions, summary = result
    assert isinstance(actions, list)
    assert summary["scheduler_mode"] == "milp"
    assert summary["local_violations"] == []


@pytest.mark.skipif(not milp_scheduler_available(), reason="PuLP/CBC not available")
def test_run_scheduler_auto_uses_milp_when_small() -> None:
    """With scheduler_mode='auto' and a tiny problem, MILP should be attempted and succeed."""
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

    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat_a", distance_m=1e6, link_type="ground"),
    ]

    actions, summary = run_scheduler(case, sample_times, links, scheduler_mode="auto")
    assert summary["milp_attempted"] is True
    assert summary["scheduler_mode"] == "milp"
    assert summary["milp_fallback_reason"] is None


def test_run_scheduler_auto_fallback_when_too_large() -> None:
    """Auto mode should fall back to greedy when problem exceeds MILP bounds."""
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
    backbone_sats = [
        BackboneSatellite(
            satellite_id=f"backbone_{i}",
            x_m=7_000_000.0 + i * 1000,
            y_m=0.0,
            z_m=0.0,
            vx_m_s=0.0,
            vy_m_s=7_000.0,
            vz_m_s=0.0,
        )
        for i in range(12)
    ]
    case = _make_tiny_case(demands, backbone_sats=backbone_sats)
    sample_times = build_time_grid(case.manifest.horizon_start, case.manifest.horizon_end, case.manifest.routing_step_s)

    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="backbone_1", distance_m=1e6, link_type="ground")
        for _ in range(10)
    ]
    links += [
        LinkRecord(sample_index=0, node_a="ep_dst", node_b=f"backbone_{i}", distance_m=1e6, link_type="ground")
        for i in range(2, 12)
    ]

    actions, summary = run_scheduler(
        case, sample_times, links, scheduler_mode="auto",
        milp_config={"max_total_variables": 1, "max_samples": 50},
    )
    assert summary["scheduler_mode"] == "greedy"
    assert summary["milp_attempted"] is True
    assert summary["milp_fallback_reason"] == "problem_too_large_or_solver_failed"


def test_run_scheduler_greedy_mode_unconditional() -> None:
    """With scheduler_mode='greedy', MILP is never attempted."""
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

    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_a", distance_m=1e6, link_type="ground"),
    ]

    actions, summary = run_scheduler(case, sample_times, links, scheduler_mode="greedy")
    assert summary["scheduler_mode"] == "greedy"
    assert summary["milp_attempted"] is False


def test_run_scheduler_milp_mode_raises_on_failure() -> None:
    """With scheduler_mode='milp' and a too-large problem, run_scheduler should raise."""
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

    backbone_sats = [
        BackboneSatellite(
            satellite_id=f"backbone_{i}",
            x_m=7_000_000.0 + i * 1000,
            y_m=0.0,
            z_m=0.0,
            vx_m_s=0.0,
            vy_m_s=7_000.0,
            vz_m_s=0.0,
        )
        for i in range(12)
    ]
    case = _make_tiny_case(demands, backbone_sats=backbone_sats)
    sample_times = build_time_grid(case.manifest.horizon_start, case.manifest.horizon_end, case.manifest.routing_step_s)

    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="backbone_1", distance_m=1e6, link_type="ground")
        for _ in range(10)
    ]
    links += [
        LinkRecord(sample_index=0, node_a="ep_dst", node_b=f"backbone_{i}", distance_m=1e6, link_type="ground")
        for i in range(2, 12)
    ]

    with pytest.raises(RuntimeError):
        run_scheduler(
            case, sample_times, links, scheduler_mode="milp",
            milp_config={"max_total_variables": 1, "max_samples": 50},
        )


@pytest.mark.skipif(not milp_scheduler_available(), reason="PuLP/CBC not available")
def test_milp_scheduler_deterministic() -> None:
    """Same input must produce the same MILP output every time."""
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
        LinkRecord(sample_index=0, node_a="sat_a", node_b="sat_b", distance_m=1e6, link_type="isl"),
    ]

    selected1 = milp_select_links(0, links, demands, max_links_per_satellite=2, max_links_per_endpoint=1)
    selected2 = milp_select_links(0, links, demands, max_links_per_satellite=2, max_links_per_endpoint=1)
    assert selected1 == selected2


@pytest.mark.skipif(not milp_scheduler_available(), reason="PuLP/CBC not available")
def test_milp_actions_pass_local_validate() -> None:
    """MILP-produced actions must have zero local violations."""
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
    case = _make_tiny_case(demands, max_links_per_satellite=2, max_links_per_endpoint=2)
    sample_times = build_time_grid(case.manifest.horizon_start, case.manifest.horizon_end, case.manifest.routing_step_s)

    links = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_b", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat_b", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="sat_a", node_b="sat_b", distance_m=1e6, link_type="isl"),
    ]

    result = run_milp_scheduler(case, sample_times, links)
    assert result is not None
    actions, summary = result
    assert summary["local_violations"] == []
