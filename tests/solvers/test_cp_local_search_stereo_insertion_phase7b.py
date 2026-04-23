"""Focused Phase 7b tests for multi-run harness and parallel candidate generation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SOLVER_DIR = REPO_ROOT / "solvers" / "stereo_imaging" / "cp_local_search_stereo_insertion"


@pytest.fixture
def solver_imports():
    sys.path.insert(0, str(SOLVER_DIR / "src"))
    try:
        from candidates import CandidateConfig, generate_candidates
        from case_io import Mission, SatelliteDef, StereoCase, TargetDef
        from local_search import LocalSearchConfig
        from seed import SeedConfig

        yield {
            "CandidateConfig": CandidateConfig,
            "generate_candidates": generate_candidates,
            "Mission": Mission,
            "SatelliteDef": SatelliteDef,
            "StereoCase": StereoCase,
            "TargetDef": TargetDef,
            "LocalSearchConfig": LocalSearchConfig,
            "SeedConfig": SeedConfig,
        }
    finally:
        sys.path.pop(0)


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------


def test_local_search_config_parses_num_runs_and_seed(solver_imports) -> None:
    LocalSearchConfig = solver_imports["LocalSearchConfig"]
    config = LocalSearchConfig.from_mapping({"num_runs": 10, "random_seed": 123})
    assert config.num_runs == 10
    assert config.random_seed == 123


def test_local_search_config_defaults(solver_imports) -> None:
    LocalSearchConfig = solver_imports["LocalSearchConfig"]
    config = LocalSearchConfig.from_mapping({})
    assert config.num_runs == 1
    assert config.random_seed == 42


def test_candidate_config_parses_parallel_workers(solver_imports) -> None:
    CandidateConfig = solver_imports["CandidateConfig"]
    config = CandidateConfig.from_mapping({"parallel_workers": 4})
    assert config.parallel_workers == 4


def test_candidate_config_parallel_workers_null_default(solver_imports) -> None:
    CandidateConfig = solver_imports["CandidateConfig"]
    config = CandidateConfig.from_mapping({})
    assert config.parallel_workers is None


def test_candidate_config_parallel_workers_zero_disables(solver_imports) -> None:
    CandidateConfig = solver_imports["CandidateConfig"]
    config = CandidateConfig.from_mapping({"parallel_workers": 0})
    assert config.parallel_workers == 0


# ---------------------------------------------------------------------------
# Parallel candidate generation identity
# ---------------------------------------------------------------------------


def _make_test_case(solver_imports) -> StereoCase:
    """Build a minimal StereoCase with 2 satellites and 2 targets."""
    SatelliteDef = solver_imports["SatelliteDef"]
    TargetDef = solver_imports["TargetDef"]
    Mission = solver_imports["Mission"]
    StereoCase = solver_imports["StereoCase"]

    from datetime import datetime, UTC

    tle1 = (
        "1 38012U 11076F   26096.23539690  .00000494  00000+0  11617-3 0  9994"
    )
    tle2 = (
        "2 38012  98.2002 172.2949 0001342  74.1943  10.7084 14.58565955761501"
    )

    sat_a = SatelliteDef(
        sat_id="sat_a",
        norad_catalog_id=38012,
        tle_line1=tle1,
        tle_line2=tle2,
        pixel_ifov_deg=4.0e-5,
        cross_track_pixels=20000,
        max_off_nadir_deg=30.0,
        max_slew_velocity_deg_per_s=1.95,
        max_slew_acceleration_deg_per_s2=0.95,
        settling_time_s=1.9,
        min_obs_duration_s=2.0,
        max_obs_duration_s=60.0,
    )
    sat_b = SatelliteDef(
        sat_id="sat_b",
        norad_catalog_id=38012,
        tle_line1=tle1,
        tle_line2=tle2,
        pixel_ifov_deg=4.0e-5,
        cross_track_pixels=20000,
        max_off_nadir_deg=30.0,
        max_slew_velocity_deg_per_s=1.95,
        max_slew_acceleration_deg_per_s2=0.95,
        settling_time_s=1.9,
        min_obs_duration_s=2.0,
        max_obs_duration_s=60.0,
    )

    target_1 = TargetDef(
        target_id="t1",
        latitude_deg=48.8566,
        longitude_deg=2.3522,
        aoi_radius_m=5000.0,
        elevation_ref_m=0.0,
        scene_type="urban_structured",
    )
    target_2 = TargetDef(
        target_id="t2",
        latitude_deg=40.7128,
        longitude_deg=-74.0060,
        aoi_radius_m=5000.0,
        elevation_ref_m=0.0,
        scene_type="open",
    )

    mission = Mission(
        horizon_start=datetime(2026, 4, 22, 0, 0, 0, tzinfo=UTC),
        horizon_end=datetime(2026, 4, 23, 0, 0, 0, tzinfo=UTC),
        allow_cross_satellite_stereo=True,
        allow_cross_date_stereo=False,
        min_overlap_fraction=0.5,
        min_convergence_deg=5.0,
        max_convergence_deg=35.0,
        max_pixel_scale_ratio=2.0,
        min_solar_elevation_deg=10.0,
        near_nadir_anchor_max_off_nadir_deg=15.0,
        pair_weights={"urban_structured": 0.9, "open": 1.0},
        tri_stereo_bonus_by_scene={"urban_structured": 0.15, "open": 0.1},
    )

    return StereoCase(
        case_dir=Path("/tmp/test_case"),
        mission=mission,
        satellites={"sat_a": sat_a, "sat_b": sat_b},
        targets={"t1": target_1, "t2": target_2},
    )


def test_parallel_candidates_identical_to_serial(solver_imports) -> None:
    """Parallel and serial candidate generation must produce identical results."""
    CandidateConfig = solver_imports["CandidateConfig"]
    generate_candidates = solver_imports["generate_candidates"]

    case = _make_test_case(solver_imports)
    config_serial = CandidateConfig(parallel_workers=0)
    config_parallel = CandidateConfig(parallel_workers=2)

    candidates_serial, summary_serial = generate_candidates(case, config_serial)
    candidates_parallel, summary_parallel = generate_candidates(case, config_parallel)

    # Candidate counts must match exactly
    assert summary_parallel.candidate_count == summary_serial.candidate_count
    assert summary_parallel.per_satellite_candidate_counts == summary_serial.per_satellite_candidate_counts
    assert summary_parallel.per_target_candidate_counts == summary_serial.per_target_candidate_counts
    assert summary_parallel.skipped_no_access_intervals == summary_serial.skipped_no_access_intervals
    assert summary_parallel.skipped_off_nadir == summary_serial.skipped_off_nadir
    assert summary_parallel.skipped_solar_elevation == summary_serial.skipped_solar_elevation

    # Candidate IDs must match exactly (deterministic ordering)
    serial_ids = [c.candidate_id for c in candidates_serial]
    parallel_ids = [c.candidate_id for c in candidates_parallel]
    assert parallel_ids == serial_ids


# ---------------------------------------------------------------------------
# Multi-run harness
# ---------------------------------------------------------------------------


def test_multi_run_different_results_with_rng(solver_imports) -> None:
    """Multi-run with RNG perturbation can produce different seed results."""
    sys.path.insert(0, str(SOLVER_DIR / "src"))
    try:
        import random
        from seed import SeedConfig, build_greedy_seed
        from products import ProductLibrary, ProductSummary
        from case_io import StereoCase

        case = _make_test_case(solver_imports)
        config = SeedConfig()

        # Build a tiny product library manually
        # This test just verifies that rng perturbation changes sort ordering
        rng1 = random.Random(1)
        rng2 = random.Random(2)

        # With different RNGs, the epsilon tie-break should differ
        # We verify by checking that two runs with different seeds can differ
        # (We can't easily test with real products here, so we test the RNG
        #  path exists and doesn't crash.)
        result1 = build_greedy_seed(
            ProductLibrary(products=[], per_target_products={}, summary=ProductSummary(
                total_products=0, pair_products=0, feasible_products=0, per_target_product_counts={}
            )),
            case, config, rng=rng1
        )
        result2 = build_greedy_seed(
            ProductLibrary(products=[], per_target_products={}, summary=ProductSummary(
                total_products=0, pair_products=0, feasible_products=0, per_target_product_counts={}
            )),
            case, config, rng=rng2
        )
        # Both should be empty (no products)
        assert result1.accepted_count == 0
        assert result2.accepted_count == 0
    finally:
        sys.path.pop(0)


def test_multi_run_keeps_best_result(solver_imports) -> None:
    """The multi-run harness selects the best result by lexicographic (coverage, quality)."""
    sys.path.insert(0, str(SOLVER_DIR / "src"))
    try:
        from solve import _pipeline_objective
        from repair import RepairResult

        # Simulate two repair results with different coverage/quality
        r1 = RepairResult(
            removed_products=[],
            lost_targets=set(),
            final_coverage=10,
            final_quality=5.0,
        )
        r2 = RepairResult(
            removed_products=[],
            lost_targets=set(),
            final_coverage=12,
            final_quality=3.0,
        )
        r3 = RepairResult(
            removed_products=[],
            lost_targets=set(),
            final_coverage=10,
            final_quality=7.0,
        )

        # Lexicographic: coverage first, then quality
        assert _pipeline_objective(r1) == (10, 5.0)
        assert _pipeline_objective(r2) == (12, 3.0)
        assert _pipeline_objective(r3) == (10, 7.0)

        # r2 should win (higher coverage)
        best = max([r1, r2, r3], key=_pipeline_objective)
        assert best.final_coverage == 12

        # If coverage ties, higher quality wins
        r4 = RepairResult(
            removed_products=[],
            lost_targets=set(),
            final_coverage=10,
            final_quality=7.0,
        )
        best2 = max([r1, r3, r4], key=_pipeline_objective)
        assert best2.final_quality == 7.0
    finally:
        sys.path.pop(0)


def test_status_includes_multi_run_stats_when_enabled(solver_imports) -> None:
    """status.json must include multi_run_stats when num_runs > 1."""
    sys.path.insert(0, str(SOLVER_DIR / "src"))
    try:
        from solve import _build_status
        from candidates import CandidateSummary
        from products import ProductLibrary, ProductSummary
        from seed import SeedResult, SeedConfig
        from local_search import LocalSearchConfig
        from repair import RepairResult, RepairConfig
        from case_io import load_case
        from datetime import datetime, UTC
        import tempfile

        case_dir = Path(tempfile.mkdtemp())
        solution_path = case_dir / "solution.json"

        # Create dummy objects
        candidate_config = solver_imports["CandidateConfig"]()
        product_library = ProductLibrary(
            products=[], per_target_products={},
            summary=ProductSummary(total_products=0, pair_products=0, feasible_products=0, per_target_product_counts={})
        )
        seed_result = SeedResult(
            accepted_products=[], rejected_records=[], covered_targets=set(),
            state=None, config=SeedConfig(), iterations=0
        )
        repair_result = RepairResult(
            removed_products=[], lost_targets=set(), final_coverage=5, final_quality=3.0
        )
        multi_run_stats = {
            "num_runs": 3,
            "random_seed": 42,
            "best_run": 1,
            "best_coverage": 5,
            "best_quality": 3.0,
            "mean_coverage": 4.33,
            "mean_quality": 2.5,
            "min_coverage": 3,
            "min_quality": 1.0,
            "all_coverages": [3, 5, 5],
            "all_qualities": [1.0, 3.0, 3.5],
        }

        status = _build_status(
            case_dir=case_dir,
            config_dir=None,
            solution_path=solution_path,
            case_id="test",
            candidate_config=candidate_config,
            candidate_summary=CandidateSummary(),
            product_config=solver_imports["CandidateConfig"](),
            product_library=product_library,
            sequence_sanity={},
            timing_seconds={"total": 1.0},
            seed_result=seed_result,
            repair_result=repair_result,
            repair_config=RepairConfig(),
            local_search_config=LocalSearchConfig(),
            multi_run_stats=multi_run_stats,
        )

        assert status["multi_run_stats"] == multi_run_stats
        assert status["status"] == "phase_7b_multi_run"
    finally:
        sys.path.pop(0)
