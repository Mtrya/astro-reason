"""Focused tests for the MCLP+TEG relay solver.

This is the single consolidated test file. It replaces the previous phase-split
test files.  Keep tests here minimal, fast, and behaviour-focused.  Heavy e2e
work belongs in experiment harnesses, not in the focused solver test suite.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import brahe
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CASE_0001 = REPO_ROOT / "benchmarks" / "relay_constellation" / "dataset" / "cases" / "test" / "case_0001"
SOLVER_MODULE = "solvers.relay_constellation.mclp_teg_contact_plan.src.solve"
VERIFIER_MODULE = "benchmarks.relay_constellation.verifier.run"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tiny_case(
    demand_windows: list,
    backbone_sats: list | None = None,
    max_added: int = 2,
    max_links_per_satellite: int = 3,
    max_links_per_endpoint: int = 1,
) -> object:
    """Build a minimal synthetic Case for cheap unit tests."""
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


def _run_solver(case_dir: Path, config: dict) -> tuple[Path, dict]:
    """Run solver with config, return (solution_dir, status). Caller must clean up."""
    import tempfile

    tmp_path = Path(tempfile.mkdtemp())
    config_dir = tmp_path / "config"
    solution_dir = tmp_path / "solution"
    config_dir.mkdir()
    solution_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            SOLVER_MODULE,
            "--case-dir",
            str(case_dir),
            "--config-dir",
            str(config_dir),
            "--solution-dir",
            str(solution_dir),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**dict(__import__("os").environ), "PYTHONPATH": str(REPO_ROOT)},
    )
    assert result.returncode == 0, f"solver failed: {result.stderr}"
    status = json.loads((solution_dir / "status.json").read_text(encoding="utf-8"))
    return solution_dir, status


def _run_verifier(case_dir: Path, solution_path: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", VERIFIER_MODULE, str(case_dir), str(solution_path)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**dict(__import__("os").environ), "PYTHONPATH": str(REPO_ROOT)},
    )
    stdout = result.stdout.strip()
    try:
        return json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        return {"raw_stdout": stdout}


# ---------------------------------------------------------------------------
# 1. Case I/O and candidate generation (fast)
# ---------------------------------------------------------------------------


def test_load_smoke_case() -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.case_io import load_case

    if not CASE_0001.exists():
        pytest.skip("Smoke case not available")
    case = load_case(CASE_0001)
    assert case.manifest.benchmark == "relay_constellation"
    assert len(case.network.backbone_satellites) > 0
    assert len(case.demands.demanded_windows) > 0


def test_candidate_generation_respects_bounds() -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.case_io import Constraints
    from solvers.relay_constellation.mclp_teg_contact_plan.src.orbit_library import generate_candidates

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
    ids = [c.satellite_id for c in candidates]
    assert len(ids) == len(set(ids))
    for c in candidates:
        assert constraints.min_altitude_m - 1.0 <= c.altitude_m <= constraints.max_altitude_m + 1.0
        if constraints.max_eccentricity is not None:
            assert c.eccentricity <= constraints.max_eccentricity + 1e-9
        if constraints.min_inclination_deg is not None:
            assert c.inclination_deg >= constraints.min_inclination_deg - 1.0
        if constraints.max_inclination_deg is not None:
            assert c.inclination_deg <= constraints.max_inclination_deg + 1.0


# ---------------------------------------------------------------------------
# 2. Link geometry (fast)
# ---------------------------------------------------------------------------


def test_ground_link_elevation_filtering() -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.link_geometry import ground_link_feasible

    endpoint_ecef = np.array([brahe.R_EARTH, 0.0, 0.0], dtype=float)
    satellite_ecef = np.array([brahe.R_EARTH + 400_000.0, 0.0, 0.0], dtype=float)

    feasible, _ = ground_link_feasible(
        tuple(endpoint_ecef.tolist()), satellite_ecef, min_elevation_deg=10.0
    )
    assert feasible is True

    satellite_below = np.array([brahe.R_EARTH - 100_000.0, 0.0, 0.0], dtype=float)
    feasible2, _ = ground_link_feasible(
        tuple(endpoint_ecef.tolist()), satellite_below, min_elevation_deg=10.0
    )
    assert feasible2 is False


def test_isl_range_and_occultation() -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.link_geometry import isl_feasible

    pos_a = np.array([brahe.R_EARTH + 500_000.0, 0.0, 0.0], dtype=float)
    pos_b = np.array([brahe.R_EARTH + 500_000.0, 100_000.0, 0.0], dtype=float)
    feasible, _ = isl_feasible(pos_a, pos_b, max_isl_range_m=20_000_000.0)
    assert feasible is True

    pos_c = np.array([brahe.R_EARTH + 500_000.0, 30_000_000.0, 0.0], dtype=float)
    feasible2, _ = isl_feasible(pos_a, pos_c, max_isl_range_m=20_000_000.0)
    assert feasible2 is False

    pos_d = np.array([-(brahe.R_EARTH + 500_000.0), 0.0, 0.0], dtype=float)
    feasible3, _ = isl_feasible(pos_a, pos_d, max_isl_range_m=50_000_000.0)
    assert feasible3 is False


# ---------------------------------------------------------------------------
# 3. MCLP reward and greedy selection (fast)
# ---------------------------------------------------------------------------


def test_build_demand_sample_indices() -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.case_io import DemandWindow
    from solvers.relay_constellation.mclp_teg_contact_plan.src.mclp import build_demand_sample_indices
    from solvers.relay_constellation.mclp_teg_contact_plan.src.time_grid import build_time_grid

    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    # Align to the case's routing_step_s=300 grid
    case = _make_tiny_case(
        demand_windows=[
            DemandWindow(
                demand_id="d1",
                source_endpoint_id="ep_src",
                destination_endpoint_id="ep_dst",
                start_time=epoch,
                end_time=epoch + timedelta(seconds=600),
                weight=1.0,
            ),
        ]
    )
    sample_times = build_time_grid(epoch, epoch + timedelta(seconds=900), 300)
    result = build_demand_sample_indices(case, sample_times)
    assert result["d1"] == [0, 1, 2]


def test_compute_covered_samples_two_hop_relay() -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.case_io import DemandWindow
    from solvers.relay_constellation.mclp_teg_contact_plan.src.mclp import (
        DemandSample,
        _compute_covered_samples,
        build_demand_sample_indices,
        build_ground_and_isl_maps,
    )

    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    case = _make_tiny_case(
        demand_windows=[
            DemandWindow(
                demand_id="d1",
                source_endpoint_id="ep_src",
                destination_endpoint_id="ep_dst",
                start_time=epoch,
                end_time=epoch + timedelta(seconds=300),
                weight=1.0,
            ),
        ]
    )
    sample_times = [
        epoch,
        epoch + timedelta(seconds=60),
        epoch + timedelta(seconds=120),
    ]
    demand_samples = build_demand_sample_indices(case, sample_times)

    # Synthetic link records:
    #   backbone_1 sees ep_src at sample 0
    #   backbone_1 has ISL to backbone_2 at sample 0
    #   backbone_2 sees ep_dst at sample 0
    from solvers.relay_constellation.mclp_teg_contact_plan.src.link_cache import LinkRecord

    link_records = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="backbone_1", distance_m=1_000_000.0, link_type="ground"),
        LinkRecord(sample_index=0, node_a="backbone_1", node_b="backbone_2", distance_m=500_000.0, link_type="isl"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="backbone_2", distance_m=1_000_000.0, link_type="ground"),
    ]
    ground_map, isl_map = build_ground_and_isl_maps(link_records)
    demands_by_id = {d.demand_id: d for d in case.demands.demanded_windows}

    active = {"backbone_1", "backbone_2"}
    covered = _compute_covered_samples(
        active, demand_samples, demands_by_id, ground_map, isl_map
    )
    assert DemandSample("d1", 0) in covered


def test_greedy_select_marginal_gain() -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.case_io import DemandWindow
    from solvers.relay_constellation.mclp_teg_contact_plan.src.mclp import greedy_select
    from solvers.relay_constellation.mclp_teg_contact_plan.src.link_cache import LinkRecord

    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    case = _make_tiny_case(
        demand_windows=[
            DemandWindow(
                demand_id="d1",
                source_endpoint_id="ep_src",
                destination_endpoint_id="ep_dst",
                start_time=epoch,
                end_time=epoch + timedelta(seconds=300),
                weight=10.0,
            ),
        ],
        max_added=2,
    )
    sample_times = [epoch, epoch + timedelta(seconds=60), epoch + timedelta(seconds=120)]

    # Candidate A: sees both endpoints (direct relay, high marginal gain)
    # Candidate B: sees only source (needs ISL to backbone that sees dest)
    from solvers.relay_constellation.mclp_teg_contact_plan.src.orbit_library import CandidateSatellite

    cand_a = CandidateSatellite(
        satellite_id="cand_A",
        state_eci_m_mps=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        altitude_m=550_000.0,
        inclination_deg=45.0,
        raan_deg=0.0,
        mean_anomaly_deg=0.0,
        eccentricity=0.0,
    )
    cand_b = CandidateSatellite(
        satellite_id="cand_B",
        state_eci_m_mps=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        altitude_m=550_000.0,
        inclination_deg=45.0,
        raan_deg=0.0,
        mean_anomaly_deg=0.0,
        eccentricity=0.0,
    )

    link_records = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="cand_A", distance_m=1_000_000.0, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="cand_A", distance_m=1_000_000.0, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_src", node_b="cand_B", distance_m=1_000_000.0, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="backbone_1", distance_m=1_000_000.0, link_type="ground"),
        LinkRecord(sample_index=0, node_a="cand_B", node_b="backbone_1", distance_m=500_000.0, link_type="isl"),
    ]

    selected, summary = greedy_select((cand_a, cand_b), case, sample_times, link_records)
    assert len(selected) <= case.manifest.constraints.max_added_satellites
    # cand_A has higher marginal gain because it sees both endpoints directly
    assert selected[0].satellite_id == "cand_A"


# ---------------------------------------------------------------------------
# 4. Scheduler and interval compaction (fast)
# ---------------------------------------------------------------------------


def test_greedy_scheduler_respects_degree_caps() -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.link_cache import LinkRecord
    from solvers.relay_constellation.mclp_teg_contact_plan.src.scheduler import greedy_select_links

    sample_index = 0
    feasible = [
        LinkRecord(sample_index=0, node_a="ep_1", node_b="sat_1", distance_m=1_000_000.0, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_2", node_b="sat_1", distance_m=1_000_000.0, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_3", node_b="sat_1", distance_m=1_000_000.0, link_type="ground"),
        LinkRecord(sample_index=0, node_a="sat_1", node_b="sat_2", distance_m=500_000.0, link_type="isl"),
    ]
    selected = greedy_select_links(
        sample_index, feasible, active_demands=[], max_links_per_satellite=2, max_links_per_endpoint=1
    )
    # sat_1 can have at most 2 links total
    sat1_count = sum(1 for k in selected if "sat_1" in (k[1], k[2]))
    assert sat1_count <= 2


@pytest.mark.parametrize("gap,expected_runs", [(0, 1), (1, 2)])
def test_compact_intervals(gap: int, expected_runs: int) -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.scheduler import compact_intervals

    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    sample_times = tuple(epoch + timedelta(seconds=i * 60) for i in range(6))

    key = ("ground", "ep_1", "sat_1")
    if gap == 0:
        selected = {0: {key}, 1: {key}, 2: {key}}
    else:
        selected = {0: {key}, 1: {key}, 3: {key}, 4: {key}}

    actions = compact_intervals(selected, sample_times, routing_step_s=60)
    assert len(actions) == expected_runs
    for a in actions:
        assert a["action_type"] == "ground_link"
        assert a["endpoint_id"] == "ep_1"
        assert a["satellite_id"] == "sat_1"


# ---------------------------------------------------------------------------
# 5. MILP bounds and fallback (fast)
# ---------------------------------------------------------------------------


def test_milp_returns_none_when_too_large() -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.mclp import milp_select
    from solvers.relay_constellation.mclp_teg_contact_plan.src.orbit_library import CandidateSatellite

    # Create 30 dummy candidates (> default max_candidates_for_milp=20)
    candidates = tuple(
        CandidateSatellite(
            satellite_id=f"cand_{i}",
            state_eci_m_mps=(0.0,) * 6,
            altitude_m=550_000.0,
            inclination_deg=45.0,
            raan_deg=0.0,
            mean_anomaly_deg=0.0,
            eccentricity=0.0,
        )
        for i in range(30)
    )
    # milp_select returns None immediately without trying to solve
    result = milp_select(candidates, None, [], [])
    assert result is None


def test_scheduler_auto_fallback_when_too_large() -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.case_io import DemandWindow
    from solvers.relay_constellation.mclp_teg_contact_plan.src.scheduler import run_scheduler
    from solvers.relay_constellation.mclp_teg_contact_plan.src.link_cache import LinkRecord

    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    case = _make_tiny_case(
        demand_windows=[
            DemandWindow(
                demand_id="d1",
                source_endpoint_id="ep_src",
                destination_endpoint_id="ep_dst",
                start_time=epoch,
                end_time=epoch + timedelta(seconds=300),
                weight=1.0,
            ),
        ]
    )
    sample_times = tuple(
        epoch + timedelta(seconds=i * 60) for i in range(6)
    )
    link_records = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="backbone_1", distance_m=1_000_000.0, link_type="ground"),
    ]

    actions, summary = run_scheduler(
        case,
        sample_times,
        link_records,
        scheduler_mode="auto",
        milp_config={"max_total_variables": 0, "max_samples": 0},
    )
    assert summary["scheduler_mode"] == "greedy"
    assert summary.get("milp_fallback_reason") is not None or summary.get("milp_attempted") is False


# ---------------------------------------------------------------------------
# 6. Parallel correctness (medium)
# ---------------------------------------------------------------------------


def test_parallel_matches_sequential() -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.parallel import (
        propagate_satellites_parallel,
        build_link_cache_parallel,
    )
    from solvers.relay_constellation.mclp_teg_contact_plan.src.propagation import propagate_satellite
    from solvers.relay_constellation.mclp_teg_contact_plan.src.link_cache import build_link_cache
    from solvers.relay_constellation.mclp_teg_contact_plan.src.time_grid import build_time_grid

    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    sample_times = tuple(epoch + timedelta(seconds=i * 60) for i in range(6))

    altitude_m = 600_000.0
    sma = brahe.R_EARTH + altitude_m
    koe_a = np.array([sma, 0.0, 45.0, 0.0, 0.0, 0.0], dtype=float)
    state_a = tuple(float(v) for v in brahe.state_koe_to_eci(koe_a, brahe.AngleFormat.DEGREES).tolist())
    koe_b = np.array([sma, 0.0, 45.0, 0.0, 0.0, 60.0], dtype=float)
    state_b = tuple(float(v) for v in brahe.state_koe_to_eci(koe_b, brahe.AngleFormat.DEGREES).tolist())

    satellites = [("sat_a", state_a), ("sat_b", state_b)]

    # Propagation equivalence
    seq_positions = {
        sid: propagate_satellite(state, epoch, sample_times) for sid, state in satellites
    }
    par_positions, timings = propagate_satellites_parallel(satellites, epoch, sample_times)
    for sid in seq_positions:
        for idx in seq_positions[sid]:
            assert np.allclose(seq_positions[sid][idx], par_positions[sid][idx])
    assert len(timings) == 2

    # Link cache equivalence (using the propagated positions)
    from solvers.relay_constellation.mclp_teg_contact_plan.src.case_io import (
        BackboneSatellite, Constraints, GroundEndpoint, Manifest, Network, Case, Demands,
    )

    manifest = Manifest(
        benchmark="relay_constellation",
        case_id="tiny",
        epoch=epoch,
        horizon_start=epoch,
        horizon_end=epoch + timedelta(seconds=300),
        routing_step_s=60,
        seed=42,
        constraints=Constraints(
            max_added_satellites=2,
            min_altitude_m=500_000.0,
            max_altitude_m=1_500_000.0,
            max_eccentricity=0.02,
            min_inclination_deg=0.0,
            max_inclination_deg=180.0,
            max_isl_range_m=20_000_000.0,
            max_links_per_satellite=3,
            max_links_per_endpoint=2,
            max_ground_range_m=None,
        ),
    )
    network = Network(
        backbone_satellites=(
            BackboneSatellite(satellite_id="sat_a", x_m=state_a[0], y_m=state_a[1], z_m=state_a[2],
                              vx_m_s=state_a[3], vy_m_s=state_a[4], vz_m_s=state_a[5]),
            BackboneSatellite(satellite_id="sat_b", x_m=state_b[0], y_m=state_b[1], z_m=state_b[2],
                              vx_m_s=state_b[3], vy_m_s=state_b[4], vz_m_s=state_b[5]),
        ),
        ground_endpoints=(
            GroundEndpoint(endpoint_id="ep_1", latitude_deg=0.0, longitude_deg=0.0, altitude_m=0.0, min_elevation_deg=10.0),
        ),
    )
    case = Case(manifest=manifest, network=network, demands=Demands(demanded_windows=()))

    backbone_positions = {
        "sat_a": par_positions["sat_a"],
        "sat_b": par_positions["sat_b"],
    }
    seq_records, seq_summary = build_link_cache(case, backbone_positions, {})
    par_records, par_summary = build_link_cache_parallel(case, backbone_positions, {})
    assert len(seq_records) == len(par_records)
    assert seq_summary["total_records"] == par_summary["total_records"]


# ---------------------------------------------------------------------------
# 7. End-to-end smoke (slow — keep to one test)
# ---------------------------------------------------------------------------


@pytest.mark.timeout(300)
def test_end_to_end_smoke() -> None:
    """One end-to-end test: solver runs on a public case and produces a valid solution."""
    if not CASE_0001.exists():
        pytest.skip("Smoke case not available")

    solution_dir, status = _run_solver(CASE_0001, {})
    try:
        verifier = _run_verifier(CASE_0001, solution_dir / "solution.json")
        assert verifier.get("valid") is True
        assert status["mclp_policy"] in ("greedy", "milp", "none")
        assert "execution_model" in status
        assert "timings_s" in status
    finally:
        shutil.rmtree(solution_dir.parent)


# ---------------------------------------------------------------------------
# 8. Config-driven grid (fast)
# ---------------------------------------------------------------------------


def test_default_grid_generates_24_candidates() -> None:
    from solvers.relay_constellation.mclp_teg_contact_plan.src.case_io import load_case
    from solvers.relay_constellation.mclp_teg_contact_plan.src.orbit_library import generate_candidates

    if not CASE_0001.exists():
        pytest.skip("Smoke case not available")
    case = load_case(CASE_0001)
    cands = generate_candidates(
        case.manifest.constraints,
        altitude_step_m=None,
        inclination_step_deg=None,
        num_raan_planes=3,
        num_phase_slots=2,
    )
    assert len(cands) == 24
