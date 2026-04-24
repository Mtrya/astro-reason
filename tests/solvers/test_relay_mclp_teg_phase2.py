"""Focused tests for Phase 2: MCLP reward construction and candidate selection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
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
from solvers.relay_constellation.mclp_teg_contact_plan.src.mclp import (
    DemandSample,
    build_demand_sample_indices,
    build_ground_and_isl_maps,
    greedy_select,
    milp_select,
    _compute_covered_samples,
    _weighted_score,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.orbit_library import (
    CandidateSatellite,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.time_grid import build_time_grid


def _make_tiny_case(
    demand_windows: list[DemandWindow],
    backbone_sats: list[BackboneSatellite] | None = None,
    max_added: int = 2,
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
        max_links_per_satellite=4,
        max_links_per_endpoint=2,
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


def test_build_demand_sample_indices() -> None:
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    demands = [
        DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=epoch,
            end_time=epoch,  # single sample
            weight=1.0,
        ),
        DemandWindow(
            demand_id="d2",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=epoch + timedelta(seconds=300),
            end_time=epoch + timedelta(seconds=600),
            weight=2.0,
        ),
    ]
    case = _make_tiny_case(demands)
    sample_times = build_time_grid(
        case.manifest.horizon_start,
        case.manifest.horizon_end,
        case.manifest.routing_step_s,
    )
    indices = build_demand_sample_indices(case, sample_times)
    assert "d1" in indices
    assert indices["d1"] == [0]
    assert "d2" in indices
    assert indices["d2"] == [1, 2]


def test_build_ground_and_isl_maps() -> None:
    records = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="sat_a", node_b="sat_b", distance_m=1e6, link_type="isl"),
        LinkRecord(sample_index=1, node_a="ep_src", node_b="sat_b", distance_m=1e6, link_type="ground"),
    ]
    ground_map, isl_map = build_ground_and_isl_maps(records)

    assert 0 in ground_map
    assert ground_map[0]["ep_src"] == {"sat_a"}
    assert ground_map[0]["sat_a"] == {"ep_src", "ep_dst"}
    assert ground_map[0]["ep_dst"] == {"sat_a"}

    assert 0 in isl_map
    assert isl_map[0]["sat_a"] == {"sat_b"}
    assert isl_map[0]["sat_b"] == {"sat_a"}

    assert 1 in ground_map
    assert ground_map[1]["ep_src"] == {"sat_b"}


def test_compute_covered_samples_same_satellite_relay() -> None:
    """Demand is covered when both endpoints see the same satellite."""
    backbone_ids = {"backbone_1"}
    demand_samples = {"d1": [0]}
    demands_by_id = {
        "d1": DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            weight=1.0,
        ),
    }
    ground_map = {
        0: {
            "ep_src": {"backbone_1"},
            "ep_dst": {"backbone_1"},
        },
    }
    isl_map: dict[int, dict[str, set[str]]] = {}

    covered = _compute_covered_samples(
        backbone_ids, demand_samples, demands_by_id, ground_map, isl_map
    )
    assert DemandSample("d1", 0) in covered


def test_compute_covered_samples_two_hop_relay() -> None:
    """Demand is covered via ISL when endpoints see different satellites."""
    backbone_ids = {"backbone_1", "backbone_2"}
    demand_samples = {"d1": [0]}
    demands_by_id = {
        "d1": DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            weight=1.0,
        ),
    }
    ground_map = {
        0: {
            "ep_src": {"backbone_1"},
            "ep_dst": {"backbone_2"},
        },
    }
    isl_map = {
        0: {
            "backbone_1": {"backbone_2"},
            "backbone_2": {"backbone_1"},
        },
    }

    covered = _compute_covered_samples(
        backbone_ids, demand_samples, demands_by_id, ground_map, isl_map
    )
    assert DemandSample("d1", 0) in covered


def test_compute_covered_samples_not_covered() -> None:
    """Demand is not covered when there is no path."""
    backbone_ids = {"backbone_1", "backbone_2"}
    demand_samples = {"d1": [0]}
    demands_by_id = {
        "d1": DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            weight=1.0,
        ),
    }
    ground_map = {
        0: {
            "ep_src": {"backbone_1"},
            "ep_dst": {"backbone_2"},
        },
    }
    isl_map: dict[int, dict[str, set[str]]] = {}

    covered = _compute_covered_samples(
        backbone_ids, demand_samples, demands_by_id, ground_map, isl_map
    )
    assert DemandSample("d1", 0) not in covered


def test_weighted_score() -> None:
    demands_by_id = {
        "d1": DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            weight=3.0,
        ),
        "d2": DemandWindow(
            demand_id="d2",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            weight=5.0,
        ),
    }
    covered = {DemandSample("d1", 0), DemandSample("d2", 0)}
    assert _weighted_score(covered, demands_by_id) == 8.0


def test_greedy_select_respects_max_added() -> None:
    """Greedy selection must not exceed max_added_satellites."""
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
    case = _make_tiny_case(demands, max_added=1)
    sample_times = build_time_grid(
        case.manifest.horizon_start,
        case.manifest.horizon_end,
        case.manifest.routing_step_s,
    )

    # Create candidates with fake states
    candidates = (
        CandidateSatellite(
            satellite_id="cand_a",
            state_eci_m_mps=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            altitude_m=550_000.0,
            inclination_deg=45.0,
            raan_deg=0.0,
            mean_anomaly_deg=0.0,
            eccentricity=0.0,
        ),
        CandidateSatellite(
            satellite_id="cand_b",
            state_eci_m_mps=(2.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            altitude_m=550_000.0,
            inclination_deg=45.0,
            raan_deg=90.0,
            mean_anomaly_deg=0.0,
            eccentricity=0.0,
        ),
    )

    # No link records => no marginal gain => selects nothing
    link_records: tuple[LinkRecord, ...] = ()
    selected, summary = greedy_select(candidates, case, sample_times, link_records)
    assert len(selected) <= case.manifest.constraints.max_added_satellites
    assert summary["selected_count"] == 0


def test_greedy_select_marginal_gain() -> None:
    """Greedy should prefer the candidate with higher marginal coverage."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    demands = [
        DemandWindow(
            demand_id="d1",
            source_endpoint_id="ep_src",
            destination_endpoint_id="ep_dst",
            start_time=epoch,
            end_time=epoch,
            weight=10.0,
        ),
    ]
    case = _make_tiny_case(demands, max_added=1)
    sample_times = build_time_grid(
        case.manifest.horizon_start,
        case.manifest.horizon_end,
        case.manifest.routing_step_s,
    )

    candidates = (
        CandidateSatellite(
            satellite_id="cand_good",
            state_eci_m_mps=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            altitude_m=550_000.0,
            inclination_deg=45.0,
            raan_deg=0.0,
            mean_anomaly_deg=0.0,
            eccentricity=0.0,
        ),
        CandidateSatellite(
            satellite_id="cand_bad",
            state_eci_m_mps=(2.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            altitude_m=550_000.0,
            inclination_deg=45.0,
            raan_deg=90.0,
            mean_anomaly_deg=0.0,
            eccentricity=0.0,
        ),
    )

    # cand_good directly covers the demand (sees both endpoints)
    # cand_bad sees nothing
    link_records = (
        LinkRecord(sample_index=0, node_a="ep_src", node_b="cand_good", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="cand_good", distance_m=1e6, link_type="ground"),
    )

    selected, summary = greedy_select(candidates, case, sample_times, link_records)
    assert len(selected) == 1
    assert selected[0].satellite_id == "cand_good"
    assert summary["selected_score"] == 10.0
    assert summary["baseline_score"] == 0.0


def test_greedy_select_deterministic_tiebreak() -> None:
    """With equal marginal gain, greedy should tie-break by candidate ID."""
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
    case = _make_tiny_case(demands, max_added=1)
    sample_times = build_time_grid(
        case.manifest.horizon_start,
        case.manifest.horizon_end,
        case.manifest.routing_step_s,
    )

    candidates = (
        CandidateSatellite(
            satellite_id="cand_b",
            state_eci_m_mps=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            altitude_m=550_000.0,
            inclination_deg=45.0,
            raan_deg=0.0,
            mean_anomaly_deg=0.0,
            eccentricity=0.0,
        ),
        CandidateSatellite(
            satellite_id="cand_a",
            state_eci_m_mps=(2.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            altitude_m=550_000.0,
            inclination_deg=45.0,
            raan_deg=90.0,
            mean_anomaly_deg=0.0,
            eccentricity=0.0,
        ),
    )

    # Both candidates cover the demand equally
    link_records = (
        LinkRecord(sample_index=0, node_a="ep_src", node_b="cand_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="cand_a", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_src", node_b="cand_b", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="cand_b", distance_m=1e6, link_type="ground"),
    )

    selected, _ = greedy_select(candidates, case, sample_times, link_records)
    assert len(selected) == 1
    # Deterministic tie-break: lexicographically smaller ID wins
    assert selected[0].satellite_id == "cand_a"


def test_milp_and_greedy_agreement_on_trivial() -> None:
    """On a tiny instance with obvious optimal, MILP and greedy should agree."""
    try:
        import pulp
    except Exception:
        pytest.skip("PuLP not available")

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
    ]
    case = _make_tiny_case(demands, max_added=1)
    sample_times = build_time_grid(
        case.manifest.horizon_start,
        case.manifest.horizon_end,
        case.manifest.routing_step_s,
    )

    candidates = (
        CandidateSatellite(
            satellite_id="cand_direct",
            state_eci_m_mps=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            altitude_m=550_000.0,
            inclination_deg=45.0,
            raan_deg=0.0,
            mean_anomaly_deg=0.0,
            eccentricity=0.0,
        ),
        CandidateSatellite(
            satellite_id="cand_none",
            state_eci_m_mps=(2.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            altitude_m=550_000.0,
            inclination_deg=45.0,
            raan_deg=90.0,
            mean_anomaly_deg=0.0,
            eccentricity=0.0,
        ),
    )

    link_records = (
        LinkRecord(sample_index=0, node_a="ep_src", node_b="cand_direct", distance_m=1e6, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="cand_direct", distance_m=1e6, link_type="ground"),
    )

    greedy_selected, greedy_summary = greedy_select(candidates, case, sample_times, link_records)
    milp_result = milp_select(candidates, case, sample_times, link_records)

    if milp_result is None:
        pytest.skip("MILP did not run (instance too large or solver issue)")

    milp_selected, milp_summary = milp_result
    assert len(greedy_selected) == len(milp_selected)
    assert greedy_selected[0].satellite_id == milp_selected[0].satellite_id == "cand_direct"
    assert greedy_summary["selected_score"] == milp_summary["selected_score"]


def test_milp_returns_none_when_too_large() -> None:
    """MILP should return None when candidate count exceeds the small-instance threshold."""
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
    case = _make_tiny_case(demands, max_added=1)
    sample_times = build_time_grid(
        case.manifest.horizon_start,
        case.manifest.horizon_end,
        case.manifest.routing_step_s,
    )

    # Create 30 candidates (>20 threshold)
    candidates = tuple(
        CandidateSatellite(
            satellite_id=f"cand_{i}",
            state_eci_m_mps=(float(i), 0.0, 0.0, 0.0, 1.0, 0.0),
            altitude_m=550_000.0,
            inclination_deg=45.0,
            raan_deg=0.0,
            mean_anomaly_deg=0.0,
            eccentricity=0.0,
        )
        for i in range(30)
    )

    link_records: tuple[LinkRecord, ...] = ()
    result = milp_select(candidates, case, sample_times, link_records)
    assert result is None


