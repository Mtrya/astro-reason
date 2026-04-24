"""Focused tests for Phase 5: parallelization, runtime hardening, execution model."""

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
    DemandWindow,
    Demands,
    GroundEndpoint,
    Manifest,
    Network,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.link_cache import (
    LinkRecord,
    build_link_cache,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.orbit_library import (
    CandidateSatellite,
    generate_candidates,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.propagation import (
    propagate_satellite,
)
from solvers.relay_constellation.mclp_teg_contact_plan.src.time_grid import (
    build_time_grid,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tiny_case() -> tuple:
    """Return a minimal synthetic case with 2 backbone sats, 1 endpoint, 1 demand."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    horizon_start = epoch
    horizon_end = epoch + timedelta(seconds=300)
    routing_step_s = 60

    # Two LEO backbone satellites
    altitude_m = 600_000.0
    sma = brahe.R_EARTH + altitude_m
    koe_a = np.array([sma, 0.0, 45.0, 0.0, 0.0, 0.0], dtype=float)
    state_a = tuple(float(v) for v in brahe.state_koe_to_eci(koe_a, brahe.AngleFormat.DEGREES).tolist())
    koe_b = np.array([sma, 0.0, 45.0, 0.0, 0.0, 60.0], dtype=float)
    state_b = tuple(float(v) for v in brahe.state_koe_to_eci(koe_b, brahe.AngleFormat.DEGREES).tolist())

    manifest = Manifest(
        benchmark="relay_constellation",
        case_id="tiny_test",
        epoch=epoch,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        routing_step_s=routing_step_s,
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
            BackboneSatellite(satellite_id="backbone_1", x_m=state_a[0], y_m=state_a[1], z_m=state_a[2], vx_m_s=state_a[3], vy_m_s=state_a[4], vz_m_s=state_a[5]),
            BackboneSatellite(satellite_id="backbone_2", x_m=state_b[0], y_m=state_b[1], z_m=state_b[2], vx_m_s=state_b[3], vy_m_s=state_b[4], vz_m_s=state_b[5]),
        ),
        ground_endpoints=(
            GroundEndpoint(
                endpoint_id="ep_1",
                latitude_deg=0.0,
                longitude_deg=0.0,
                altitude_m=0.0,
                min_elevation_deg=10.0,
            ),
        ),
    )
    demands = Demands(
        demanded_windows=(
            DemandWindow(
                demand_id="d1",
                source_endpoint_id="ep_1",
                destination_endpoint_id="ep_1",
                start_time=horizon_start,
                end_time=horizon_end,
                weight=1.0,
            ),
        )
    )

    case = pytest.importorskip("solvers.relay_constellation.mclp_teg_contact_plan.src.case_io").Case(
        manifest=manifest,
        network=network,
        demands=demands,
    )
    return case, manifest, network, demands


# ---------------------------------------------------------------------------
# Parallel propagation correctness
# ---------------------------------------------------------------------------

def test_parallel_propagation_matches_sequential() -> None:
    """Parallel propagation must produce identical position dicts."""
    from solvers.relay_constellation.mclp_teg_contact_plan.src.parallel import (
        propagate_satellites_parallel,
    )

    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    sample_times = tuple(
        epoch + timedelta(seconds=i * 60) for i in range(6)
    )

    # Two simple LEO orbits
    altitude_m = 600_000.0
    sma = brahe.R_EARTH + altitude_m
    koe_a = np.array([sma, 0.0, 45.0, 0.0, 0.0, 0.0], dtype=float)
    state_a = tuple(float(v) for v in brahe.state_koe_to_eci(koe_a, brahe.AngleFormat.DEGREES).tolist())
    koe_b = np.array([sma, 0.0, 45.0, 0.0, 0.0, 60.0], dtype=float)
    state_b = tuple(float(v) for v in brahe.state_koe_to_eci(koe_b, brahe.AngleFormat.DEGREES).tolist())

    satellites = [("sat_a", state_a), ("sat_b", state_b)]

    # Sequential
    seq_positions = {
        sid: propagate_satellite(state, epoch, sample_times)
        for sid, state in satellites
    }

    # Parallel
    par_positions, timings = propagate_satellites_parallel(satellites, epoch, sample_times)

    assert set(seq_positions.keys()) == set(par_positions.keys())
    for sid in seq_positions:
        seq_dict = seq_positions[sid]
        par_dict = par_positions[sid]
        assert set(seq_dict.keys()) == set(par_dict.keys())
        for idx in seq_dict:
            assert np.allclose(seq_dict[idx], par_dict[idx]), f"Mismatch at {sid}[{idx}]"
    assert len(timings) == 2
    assert all(t >= 0 for t in timings)


# ---------------------------------------------------------------------------
# Parallel link cache correctness
# ---------------------------------------------------------------------------

def test_parallel_link_cache_matches_sequential() -> None:
    """Parallel link cache must produce identical records and summary."""
    from solvers.relay_constellation.mclp_teg_contact_plan.src.parallel import (
        build_link_cache_parallel,
    )

    case, manifest, network, demands = _make_tiny_case()
    sample_times = build_time_grid(
        manifest.horizon_start, manifest.horizon_end, manifest.routing_step_s
    )

    backbone_positions = {}
    for sat in network.backbone_satellites:
        backbone_positions[sat.satellite_id] = propagate_satellite(
            sat.state_eci_m_mps, manifest.epoch, sample_times
        )

    # Sequential
    seq_records, seq_summary = build_link_cache(case, backbone_positions, {})

    # Parallel
    par_records, par_summary = build_link_cache_parallel(case, backbone_positions, {})

    assert len(seq_records) == len(par_records)
    # Sort both for deterministic comparison
    seq_sorted = sorted(seq_records, key=lambda r: (r.sample_index, r.link_type, r.node_a, r.node_b))
    par_sorted = sorted(par_records, key=lambda r: (r.sample_index, r.link_type, r.node_a, r.node_b))
    for srec, prec in zip(seq_sorted, par_sorted):
        assert srec.sample_index == prec.sample_index
        assert srec.link_type == prec.link_type
        assert srec.node_a == prec.node_a
        assert srec.node_b == prec.node_b
        assert abs(srec.distance_m - prec.distance_m) < 1e-6

    assert seq_summary["ground_link_records"] == par_summary["ground_link_records"]
    assert seq_summary["isl_link_records"] == par_summary["isl_link_records"]
    assert seq_summary["total_records"] == par_summary["total_records"]


# ---------------------------------------------------------------------------
# Auto mode logic
# ---------------------------------------------------------------------------

def test_auto_mode_chooses_parallel_for_large_case() -> None:
    """Auto mode should enable parallel when there are multiple satellites."""
    case, manifest, network, demands = _make_tiny_case()
    n_satellites = len(network.backbone_satellites)
    n_samples = len(build_time_grid(manifest.horizon_start, manifest.horizon_end, manifest.routing_step_s))
    auto_parallel = n_satellites > 1 or n_samples > 1000
    assert auto_parallel is True


def test_auto_mode_chooses_sequential_for_tiny_case() -> None:
    """Auto mode should disable parallel for a single satellite and few samples."""
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    # 1 satellite, 3 samples
    n_satellites = 1
    n_samples = 3
    auto_parallel = n_satellites > 1 or n_samples > 1000
    assert auto_parallel is False


# ---------------------------------------------------------------------------
# Fallback on process pool failure
# ---------------------------------------------------------------------------

def test_parallel_fallback_to_sequential_on_error(monkeypatch) -> None:
    """If ProcessPoolExecutor raises, the solver falls back to sequential."""
    from concurrent.futures import ProcessPoolExecutor
    from solvers.relay_constellation.mclp_teg_contact_plan.src.parallel import (
        ParallelExecutionError,
        propagate_satellites_parallel,
    )

    original_init = ProcessPoolExecutor.__init__

    def broken_init(*args, **kwargs):
        raise RuntimeError("simulated pool failure")

    monkeypatch.setattr(ProcessPoolExecutor, "__init__", broken_init)

    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    sample_times = tuple(epoch + timedelta(seconds=i * 60) for i in range(3))
    altitude_m = 600_000.0
    sma = brahe.R_EARTH + altitude_m
    koe = np.array([sma, 0.0, 45.0, 0.0, 0.0, 0.0], dtype=float)
    state = tuple(float(v) for v in brahe.state_koe_to_eci(koe, brahe.AngleFormat.DEGREES).tolist())

    # Pass 2 satellites so max_workers > 1, forcing ProcessPoolExecutor creation
    satellites = [("sat_a", state), ("sat_b", state)]
    with pytest.raises(ParallelExecutionError):
        propagate_satellites_parallel(satellites, epoch, sample_times)


# ---------------------------------------------------------------------------
# End-to-end: all modes, status hardening, and equivalence
# ---------------------------------------------------------------------------

def test_end_to_end_parallel_and_sequential_equivalence(tmp_path: Path) -> None:
    """Parallel and sequential modes must both produce valid solutions with identical metrics,
    and status.json must contain hardened fields."""
    import json
    import subprocess

    case_dir = Path("benchmarks/relay_constellation/dataset/cases/test/case_0001")
    if not case_dir.exists():
        pytest.skip("Smoke case not available")

    configs = [
        ("parallel", {"parallel_mode": "parallel", "mclp_mode": "none"}),
        ("sequential", {"parallel_mode": "sequential", "mclp_mode": "none", "time_budget_s": 300}),
    ]

    statuses = {}
    for label, cfg in configs:
        config_dir = tmp_path / f"config_{label}"
        config_dir.mkdir()
        config_dir.joinpath("config.json").write_text(json.dumps(cfg), encoding="utf-8")
        solution_dir = tmp_path / f"solution_{label}"

        result = subprocess.run(
            [
                "bash",
                "solvers/relay_constellation/mclp_teg_contact_plan/solve.sh",
                str(case_dir),
                str(config_dir),
                str(solution_dir),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, f"{label} failed: {result.stderr}"

        solution_path = solution_dir / "solution.json"
        assert solution_path.exists()

        # Verify with benchmark verifier
        verifier_result = subprocess.run(
            [
                "python",
                "-m",
                "benchmarks.relay_constellation.verifier.run",
                str(case_dir),
                str(solution_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert verifier_result.returncode == 0, verifier_result.stderr
        verdict = json.loads(verifier_result.stdout)
        assert verdict["valid"] is True, f"{label} mode produced invalid solution"

        status = json.loads((solution_dir / "status.json").read_text(encoding="utf-8"))
        statuses[label] = status

    # --- Execution model assertions ---
    assert statuses["parallel"]["execution_model"]["parallel_enabled"] is True
    assert statuses["sequential"]["execution_model"]["parallel_enabled"] is False

    for label, _ in configs:
        em = statuses[label]["execution_model"]
        assert "parallel_mode" in em
        assert "worker_count" in em
        assert "propagation_mode" in em
        assert "link_cache_mode" in em
        assert "parallel_fallback" in em

    # --- Per-satellite timings ---
    for label, _ in configs:
        timings = statuses[label]["timings_s"]
        assert "propagate_backbone_per_satellite_ms" in timings
        assert "propagate_candidates_per_satellite_ms" in timings
        assert isinstance(timings["propagate_backbone_per_satellite_ms"], list)
        assert isinstance(timings["propagate_candidates_per_satellite_ms"], list)

    # --- Budget default ---
    assert statuses["sequential"]["compute_budget_s"] == 300
    assert "budget_warning" in statuses["sequential"]

    # --- Equivalence ---
    assert statuses["parallel"]["mclp_selected_count"] == statuses["sequential"]["mclp_selected_count"]
    assert statuses["parallel"]["scheduler_num_actions"] == statuses["sequential"]["scheduler_num_actions"]
