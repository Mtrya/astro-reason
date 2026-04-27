"""Focused tests for the MCLP+TEG relay solver.

This is the single consolidated test file. It replaces the previous phase-split
test files.  Keep tests here minimal, fast, and behaviour-focused.  Heavy e2e
work belongs in experiment harnesses, not in the focused solver test suite.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import brahe
import numpy as np
import pytest
import yaml

def _resolve_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pytest.ini").exists() and (candidate / "benchmarks").exists():
            return candidate
    raise RuntimeError("Could not locate repository root from test file location")


REPO_ROOT = _resolve_repo_root()
SOLVER_ROOT = Path(__file__).resolve().parents[1]
if str(SOLVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SOLVER_ROOT))
CASE_0001 = REPO_ROOT / "benchmarks" / "relay_constellation" / "dataset" / "cases" / "test" / "case_0001"
SOLVER_MODULE = "src.solve"
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
    from src.case_io import (
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
        cwd=str(SOLVER_ROOT),
        env={**dict(os.environ), "PYTHONPATH": str(SOLVER_ROOT)},
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
        env={**dict(os.environ), "PYTHONPATH": str(REPO_ROOT)},
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
    from src.case_io import load_case

    if not CASE_0001.exists():
        pytest.skip("Smoke case not available")
    case = load_case(CASE_0001)
    assert case.manifest.benchmark == "relay_constellation"
    assert len(case.network.backbone_satellites) > 0
    assert len(case.demands.demanded_windows) > 0


def test_candidate_generation_respects_bounds() -> None:
    from src.case_io import Constraints
    from src.orbit_library import generate_candidates

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
    from src.link_geometry import ground_link_feasible

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
    from src.link_geometry import isl_feasible

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


def test_selection_cache_skips_candidate_candidate_isl_pairs() -> None:
    from src.case_io import DemandWindow
    from src.link_cache import build_link_cache

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
        ],
        max_added=2,
    )
    backbone_positions = {
        "backbone_1": {0: np.array([brahe.R_EARTH + 600_000.0, 0.0, 0.0], dtype=float)}
    }
    candidate_positions = {
        "cand_A": {0: np.array([brahe.R_EARTH + 600_000.0, 50_000.0, 0.0], dtype=float)},
        "cand_B": {0: np.array([brahe.R_EARTH + 600_000.0, 100_000.0, 0.0], dtype=float)},
    }

    full_records, _full_summary = build_link_cache(
        case,
        backbone_positions,
        candidate_positions,
        include_candidate_candidate_isl=True,
        cache_stage="scheduler",
    )
    selection_records, selection_summary = build_link_cache(
        case,
        backbone_positions,
        candidate_positions,
        include_candidate_candidate_isl=False,
        cache_stage="selection",
    )

    full_isl_pairs = {
        tuple(sorted((rec.node_a, rec.node_b)))
        for rec in full_records
        if rec.link_type == "isl"
    }
    selection_isl_pairs = {
        tuple(sorted((rec.node_a, rec.node_b)))
        for rec in selection_records
        if rec.link_type == "isl"
    }

    assert ("cand_A", "cand_B") in full_isl_pairs
    assert ("cand_A", "cand_B") not in selection_isl_pairs
    assert ("backbone_1", "cand_A") in selection_isl_pairs
    assert selection_summary["cache_stage"] == "selection"
    assert selection_summary["cache_exact"] is False
    assert selection_summary["candidate_pair_sample_checks_avoided"] == 1


def test_scheduler_cache_matches_full_cache_for_selected_satellites() -> None:
    from src.case_io import DemandWindow
    from src.link_cache import build_link_cache

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
        ],
        max_added=2,
    )
    backbone_positions = {
        "backbone_1": {0: np.array([brahe.R_EARTH + 600_000.0, 0.0, 0.0], dtype=float)}
    }
    candidate_positions = {
        "cand_A": {0: np.array([brahe.R_EARTH + 600_000.0, 50_000.0, 0.0], dtype=float)},
        "cand_B": {0: np.array([brahe.R_EARTH + 600_000.0, 100_000.0, 0.0], dtype=float)},
    }
    selected_positions = {"cand_A": candidate_positions["cand_A"]}

    full_records, _full_summary = build_link_cache(
        case,
        backbone_positions,
        candidate_positions,
        include_candidate_candidate_isl=True,
        cache_stage="full",
    )
    scheduler_records, scheduler_summary = build_link_cache(
        case,
        backbone_positions,
        selected_positions,
        include_candidate_candidate_isl=True,
        cache_stage="scheduler",
    )

    allowed_sats = {"backbone_1", "cand_A"}

    def key(rec: object) -> tuple:
        return (
            rec.sample_index,
            rec.link_type,
            rec.node_a,
            rec.node_b,
            round(rec.distance_m, 6),
        )

    filtered_full = {
        key(rec)
        for rec in full_records
        if (rec.link_type == "ground" and rec.node_b in allowed_sats)
        or (rec.link_type == "isl" and rec.node_a in allowed_sats and rec.node_b in allowed_sats)
    }
    scheduler_set = {key(rec) for rec in scheduler_records}

    assert scheduler_set == filtered_full
    assert scheduler_summary["cache_stage"] == "scheduler"
    assert scheduler_summary["cache_exact"] is True


# ---------------------------------------------------------------------------
# 3. MCLP reward and greedy selection (fast)
# ---------------------------------------------------------------------------


def test_build_demand_sample_indices() -> None:
    from src.case_io import DemandWindow
    from src.mclp import build_demand_sample_indices
    from src.time_grid import build_time_grid

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
    assert result["d1"] == [0, 1]


def test_compute_covered_samples_two_hop_relay() -> None:
    from src.case_io import DemandWindow
    from src.mclp import (
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
    from src.link_cache import LinkRecord

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
    from src.case_io import DemandWindow
    from src.mclp import greedy_select
    from src.link_cache import LinkRecord

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
    from src.orbit_library import CandidateSatellite

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
    assert summary["scoring_engine"] == "indexed_exact"
    assert summary["candidate_evaluations"] > 0
    assert summary["marginal_eval_total_time_s"] >= 0.0


def test_greedy_select_is_deterministic_with_indexed_scoring() -> None:
    from src.case_io import DemandWindow
    from src.link_cache import LinkRecord
    from src.mclp import greedy_select
    from src.orbit_library import CandidateSatellite

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
    candidates = tuple(
        CandidateSatellite(
            satellite_id=f"cand_{name}",
            state_eci_m_mps=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            altitude_m=550_000.0,
            inclination_deg=45.0,
            raan_deg=0.0,
            mean_anomaly_deg=0.0,
            eccentricity=0.0,
        )
        for name in ("A", "B", "C")
    )
    link_records = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="cand_B", distance_m=1_000_000.0, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="cand_B", distance_m=1_000_000.0, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_src", node_b="cand_A", distance_m=1_000_000.0, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="cand_A", distance_m=1_000_000.0, link_type="ground"),
        LinkRecord(sample_index=0, node_a="ep_src", node_b="cand_C", distance_m=1_000_000.0, link_type="ground"),
    ]

    first_selected, first_summary = greedy_select(candidates, case, sample_times, link_records)
    second_selected, second_summary = greedy_select(candidates, case, sample_times, link_records)

    first_ids = [c.satellite_id for c in first_selected]
    second_ids = [c.satellite_id for c in second_selected]
    assert first_ids == second_ids
    assert first_ids[0] == "cand_A"
    assert first_summary["selected_candidate_ids"] == second_summary["selected_candidate_ids"]
    assert first_summary["candidate_evaluations"] == second_summary["candidate_evaluations"]


# ---------------------------------------------------------------------------
# 4. Scheduler and interval compaction (fast)
# ---------------------------------------------------------------------------


def test_greedy_scheduler_respects_degree_caps() -> None:
    from src.link_cache import LinkRecord
    from src.scheduler import greedy_select_links

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


def test_route_aware_scheduler_selects_complete_demand_path() -> None:
    from src.case_io import DemandWindow
    from src.link_cache import LinkRecord
    from src.scheduler import route_aware_select_links

    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    demand = DemandWindow(
        demand_id="d1",
        source_endpoint_id="ep_src",
        destination_endpoint_id="ep_dst",
        start_time=epoch,
        end_time=epoch + timedelta(seconds=60),
        weight=10.0,
    )
    feasible = [
        LinkRecord(sample_index=0, node_a="ep_src", node_b="sat_a", distance_m=1.0, link_type="ground"),
        LinkRecord(sample_index=0, node_a="sat_a", node_b="sat_b", distance_m=1.0, link_type="isl"),
        LinkRecord(sample_index=0, node_a="ep_dst", node_b="sat_b", distance_m=1.0, link_type="ground"),
        # This tempting unrelated endpoint must not become an intermediate ground transit node.
        LinkRecord(sample_index=0, node_a="ep_other", node_b="sat_a", distance_m=0.1, link_type="ground"),
    ]

    selected, summary = route_aware_select_links(
        0,
        feasible,
        [demand],
        max_links_per_satellite=2,
        max_links_per_endpoint=1,
    )

    assert selected == {
        ("ground", "ep_src", "sat_a"),
        ("isl", "sat_a", "sat_b"),
        ("ground", "ep_dst", "sat_b"),
    }
    assert summary["route_aware_demands_routed"] == 1
    assert all("ep_other" not in key for key in selected)


@pytest.mark.parametrize("gap,expected_runs", [(0, 1), (1, 2)])
def test_compact_intervals(gap: int, expected_runs: int) -> None:
    from src.scheduler import compact_intervals

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
    from src.mclp import milp_select
    from src.orbit_library import CandidateSatellite

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
    case = _make_tiny_case([])
    result = milp_select(candidates, case, [], [])
    assert result is None


def test_scheduler_auto_fallback_when_too_large() -> None:
    pytest.importorskip("pulp")

    from src.case_io import DemandWindow
    from src.scheduler import run_scheduler
    from src.link_cache import LinkRecord

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
    from src.parallel import (
        propagate_satellites_parallel,
        build_link_cache_parallel,
    )
    from src.propagation import propagate_satellite
    from src.link_cache import build_link_cache
    from src.time_grid import build_time_grid

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
    from src.case_io import (
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
    from src.case_io import load_case
    from src.orbit_library import generate_candidates

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


def test_reproduction_config_generates_scaled_candidate_library() -> None:
    from src.case_io import load_case
    from src.orbit_library import generate_candidates

    if not CASE_0001.exists():
        pytest.skip("Smoke case not available")

    case = load_case(CASE_0001)
    profile_path = (
        REPO_ROOT
        / "experiments"
        / "main_solver"
        / "solvers"
        / "relay_constellation_mclp_teg_contact_plan.yaml"
    )
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    grid = profile["config"]["orbit_grid"]
    cands = generate_candidates(
        case.manifest.constraints,
        altitude_step_m=grid["altitude_step_m"],
        inclination_step_deg=grid["inclination_step_deg"],
        num_raan_planes=grid["num_raan_planes"],
        num_phase_slots=grid["num_phase_slots"],
    )
    assert len(cands) >= 100
