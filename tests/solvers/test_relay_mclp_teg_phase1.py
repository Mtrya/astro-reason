"""Focused tests for Phase 1: scaffold, parsing, orbit library, propagation, link geometry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import brahe
import numpy as np
import pytest

from solvers.relay_constellation.mclp_teg_contact_plan.src.case_io import (
    BackboneSatellite,
    Constraints,
    GroundEndpoint,
    load_case,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.link_geometry import (
    ground_link_feasible,
    isl_feasible,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.orbit_library import (
    CandidateSatellite,
    generate_candidates,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.propagation import (
    propagate_satellite,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.solution_io import (
    write_solution,
    write_status,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.time_grid import (
    build_time_grid,
    sample_index,
)


def test_iso_timestamp_parsing() -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.case_io import _parse_iso8601_z

    dt = _parse_iso8601_z("2026-01-01T00:00:00Z")
    assert dt.year == 2026
    assert dt.month == 1
    assert dt.day == 1
    assert dt.hour == 0
    assert dt.minute == 0
    assert dt.second == 0
    assert dt.tzinfo is not None

    dt2 = _parse_iso8601_z("2026-01-01T12:30:45Z")
    assert dt2.hour == 12
    assert dt2.minute == 30
    assert dt2.second == 45


def test_routing_grid_generation() -> None:
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 0, 5, 0, tzinfo=timezone.utc)
    samples = build_time_grid(start, end, routing_step_s=60)
    assert len(samples) == 6
    assert samples[0] == start
    assert samples[-1] == end
    assert sample_index(start, start, 60) == 0
    assert sample_index(start, end, 60) == 5


def test_candidate_orbit_bounds() -> None:
    constraints = Constraints(
        max_added_satellites=6,
        min_altitude_m=500_000.0,
        max_altitude_m=1_500_000.0,
        max_eccentricity=0.02,
        min_inclination_deg=20.0,
        max_inclination_deg=85.0,
        max_isl_range_m=20_000_000.0,
        max_links_per_satellite=3,
        max_links_per_endpoint=1,
        max_ground_range_m=None,
    )
    candidates = generate_candidates(constraints)
    assert len(candidates) > 0
    for c in candidates:
        assert c.altitude_m >= constraints.min_altitude_m - 1.0
        assert c.altitude_m <= constraints.max_altitude_m + 1.0
        if constraints.max_eccentricity is not None:
            assert c.eccentricity <= constraints.max_eccentricity + 1e-9
        if constraints.min_inclination_deg is not None:
            assert c.inclination_deg >= constraints.min_inclination_deg - 1.0
        if constraints.max_inclination_deg is not None:
            assert c.inclination_deg <= constraints.max_inclination_deg + 1.0


def test_candidate_ids_are_unique() -> None:
    constraints = Constraints(
        max_added_satellites=6,
        min_altitude_m=500_000.0,
        max_altitude_m=1_500_000.0,
        max_eccentricity=0.02,
        min_inclination_deg=20.0,
        max_inclination_deg=85.0,
        max_isl_range_m=20_000_000.0,
        max_links_per_satellite=3,
        max_links_per_endpoint=1,
        max_ground_range_m=None,
    )
    candidates = generate_candidates(constraints)
    ids = [c.satellite_id for c in candidates]
    assert len(ids) == len(set(ids))


def test_ground_link_elevation_filtering() -> None:
    # Simple fixture: endpoint at 0,0,0 geodetic (roughly), satellite directly overhead at ~400km
    # Use a position roughly above the equator at 0 lon
    endpoint_ecef = np.array([brahe.R_EARTH, 0.0, 0.0], dtype=float)
    satellite_ecef = np.array([brahe.R_EARTH + 400_000.0, 0.0, 0.0], dtype=float)

    feasible, distance = ground_link_feasible(
        tuple(endpoint_ecef.tolist()),
        satellite_ecef,
        min_elevation_deg=10.0,
    )
    assert feasible is True
    assert distance > 0

    # Satellite below horizon
    satellite_below = np.array([brahe.R_EARTH - 100_000.0, 0.0, 0.0], dtype=float)
    feasible2, distance2 = ground_link_feasible(
        tuple(endpoint_ecef.tolist()),
        satellite_below,
        min_elevation_deg=10.0,
    )
    assert feasible2 is False


def test_isl_range_and_occultation() -> None:
    # Two satellites close together in LEO, should be feasible
    pos_a = np.array([brahe.R_EARTH + 500_000.0, 0.0, 0.0], dtype=float)
    pos_b = np.array([brahe.R_EARTH + 500_000.0, 100_000.0, 0.0], dtype=float)

    feasible, distance = isl_feasible(pos_a, pos_b, max_isl_range_m=20_000_000.0)
    assert feasible is True
    assert distance > 0

    # Too far apart
    pos_c = np.array([brahe.R_EARTH + 500_000.0, 30_000_000.0, 0.0], dtype=float)
    feasible2, distance2 = isl_feasible(pos_a, pos_c, max_isl_range_m=20_000_000.0)
    assert feasible2 is False

    # Earth-blocked: one on each side of Earth
    pos_d = np.array([-(brahe.R_EARTH + 500_000.0), 0.0, 0.0], dtype=float)
    feasible3, distance3 = isl_feasible(pos_a, pos_d, max_isl_range_m=50_000_000.0)
    assert feasible3 is False


def test_empty_solution_schema(tmp_path: Path) -> None:
    write_solution(
        tmp_path,
        added_satellites=[],
        actions=[],
    )
    solution_path = tmp_path / "solution.json"
    assert solution_path.exists()
    import json

    payload = json.loads(solution_path.read_text(encoding="utf-8"))
    assert "added_satellites" in payload
    assert "actions" in payload
    assert payload["added_satellites"] == []
    assert payload["actions"] == []


def test_status_schema(tmp_path: Path) -> None:
    status = {
        "benchmark": "relay_constellation",
        "case_id": "case_test",
        "routing_step_s": 60,
    }
    write_status(tmp_path, status)
    status_path = tmp_path / "status.json"
    assert status_path.exists()


def test_propagate_satellite_produces_positions() -> None:
    # Use a simple circular LEO orbit
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    altitude_m = 600_000.0
    sma = brahe.R_EARTH + altitude_m
    koe = np.array([sma, 0.0, 45.0, 0.0, 0.0, 0.0], dtype=float)
    state_eci = brahe.state_koe_to_eci(koe, brahe.AngleFormat.DEGREES)
    sample_times = [
        epoch,
        epoch + timedelta(seconds=60),
        epoch + timedelta(seconds=120),
    ]
    positions = propagate_satellite(
        tuple(float(v) for v in state_eci.tolist()),
        epoch,
        sample_times,
    )
    assert len(positions) == 3
    for i in range(3):
        assert i in positions
        pos = positions[i]
        assert pos.shape == (3,)
        # Should be above Earth surface
        assert np.linalg.norm(pos) > float(brahe.R_EARTH) - 1e3


def test_load_smoke_case() -> None:
    case_dir = Path("benchmarks/relay_constellation/dataset/cases/test/case_0001")
    if not case_dir.exists():
        pytest.skip("Smoke case not available")
    case = load_case(case_dir)
    assert case.manifest.benchmark == "relay_constellation"
    assert case.manifest.case_id == "case_0001"
    assert len(case.network.backbone_satellites) > 0
    assert len(case.network.ground_endpoints) > 0
    assert len(case.demands.demanded_windows) > 0
