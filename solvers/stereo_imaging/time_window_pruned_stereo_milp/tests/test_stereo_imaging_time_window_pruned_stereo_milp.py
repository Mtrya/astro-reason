"""Focused tests for the time-window-pruned stereo MILP solver."""

from __future__ import annotations

import json
import math
import os
import shlex
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

SOLVER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SOLVER_ROOT.parents[2]
SOLVER_DIR = SOLVER_ROOT / "src"
sys.path.insert(0, str(SOLVER_DIR))

import candidates as candidate_module  # noqa: E402
import products as product_module  # noqa: E402
from models import (  # noqa: E402
    CandidateObservation,
    CandidateSummary,
    Mission,
    QualityModel,
    Satellite,
    StereoPair,
    Target,
    ValidityThresholds,
)
from products import (  # noqa: E402
    _CandidateGeometry,
    _pair_geom_quality,
    _precompute_candidate_geometry,
    _stereo_pair_mode,
    _tri_bonus_R,
    evaluate_pair,
    evaluate_tri,
    enumerate_products,
)
from case_io import load_case as solver_load_case, load_solver_config  # noqa: E402
from milp_model import (  # noqa: E402
    BackendUnavailable,
    _evaluate_solution,
    build_conflict_graph,
    build_milp,
    solve_greedy_heuristic,
    solve_milp,
    solve_with_ortools,
)
from repair import repair_solution  # noqa: E402
from pruning import (  # noqa: E402
    _build_candidate_to_metrics,
    _CandidateScore,
    _rank_key,
    _score_candidates,
    cluster_candidates_by_gap,
    compute_cluster_gap_s,
    compute_lambda_lb,
    prune_candidates,
)


def _prepared_solver_env(tmp_path: Path) -> dict[str, str]:
    """Point solve.sh at the current test interpreter as a prepared solver env."""
    env_dir = tmp_path / "solver_env"
    bin_dir = env_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    python_shim = bin_dir / "python"
    if not python_shim.exists():
        python_shim.write_text(
            f"#!/usr/bin/env bash\nexec {shlex.quote(sys.executable)} \"$@\"\n",
            encoding="utf-8",
        )
        python_shim.chmod(0o755)
    return {**os.environ, "SOLVER_VENV_DIR": str(env_dir)}


def _satellite(
    sat_id: str = "sat_test",
    pixel_ifov_deg: float = 4.0e-05,
    cross_track_pixels: int = 20000,
    max_off_nadir_deg: float = 30.0,
) -> Satellite:
    return Satellite(
        id=sat_id,
        norad_catalog_id=1,
        tle_line1="1 00000U 00000A   00000.00000000  .00000000  00000+0  00000-0 0  0000",
        tle_line2="2 00000   0.0000   0.0000 0000000   0.0000   0.0000  0.00000000000000",
        pixel_ifov_deg=pixel_ifov_deg,
        cross_track_pixels=cross_track_pixels,
        max_off_nadir_deg=max_off_nadir_deg,
        max_slew_velocity_deg_per_s=1.0,
        max_slew_acceleration_deg_per_s2=1.0,
        settling_time_s=1.0,
        min_obs_duration_s=2.0,
        max_obs_duration_s=60.0,
    )


def _target(
    target_id: str = "t1",
    lat: float = 0.0,
    lon: float = 0.0,
    aoi_radius_m: float = 5000.0,
    scene_type: str = "urban_structured",
) -> Target:
    return Target(
        id=target_id,
        latitude_deg=lat,
        longitude_deg=lon,
        aoi_radius_m=aoi_radius_m,
        elevation_ref_m=0.0,
        scene_type=scene_type,
    )


def _mission(
    *,
    allow_cross_satellite_stereo: bool = False,
    max_stereo_pair_separation_s: float = 3600.0,
    min_overlap_fraction: float = 0.8,
    min_convergence_deg: float = 5.0,
    max_convergence_deg: float = 45.0,
    max_pixel_scale_ratio: float = 1.5,
    min_solar_elevation_deg: float = 10.0,
    near_nadir_anchor_max_off_nadir_deg: float = 10.0,
) -> Mission:
    return Mission(
        horizon_start=datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC),
        horizon_end=datetime(2026, 6, 19, 0, 0, 0, tzinfo=UTC),
        allow_cross_satellite_stereo=allow_cross_satellite_stereo,
        max_stereo_pair_separation_s=max_stereo_pair_separation_s,
        validity_thresholds=ValidityThresholds(
            min_overlap_fraction=min_overlap_fraction,
            min_convergence_deg=min_convergence_deg,
            max_convergence_deg=max_convergence_deg,
            max_pixel_scale_ratio=max_pixel_scale_ratio,
            min_solar_elevation_deg=min_solar_elevation_deg,
            near_nadir_anchor_max_off_nadir_deg=near_nadir_anchor_max_off_nadir_deg,
        ),
        quality_model=QualityModel(
            pair_weights={"geometry": 0.5, "overlap": 0.35, "resolution": 0.15},
            tri_stereo_bonus_by_scene={
                "urban_structured": 0.12,
                "rugged": 0.10,
                "vegetated": 0.08,
                "open": 0.05,
            },
        ),
    )


def _candidate(
    sat_id: str = "sat_test",
    target_id: str = "t1",
    interval_id: str = "sat_test::t1::0",
    start_offset_s: int = 0,
    end_offset_s: int = 10,
    along: float = 0.0,
    across: float = 0.0,
) -> CandidateObservation:
    base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)
    return CandidateObservation(
        sat_id=sat_id,
        target_id=target_id,
        access_interval_id=interval_id,
        start=base + timedelta(seconds=start_offset_s),
        end=base + timedelta(seconds=end_offset_s),
        off_nadir_along_deg=along,
        off_nadir_across_deg=across,
        combined_off_nadir_deg=math.degrees(
            math.atan(math.sqrt(math.tan(math.radians(along)) ** 2 + math.tan(math.radians(across)) ** 2))
        ),
    )


def _pair(
    candidate_i: CandidateObservation,
    candidate_j: CandidateObservation,
    *,
    target_id: str | None = None,
    q_pair: float = 0.8,
) -> StereoPair:
    return StereoPair(
        target_id=target_id or candidate_i.target_id,
        candidate_i=candidate_i,
        candidate_j=candidate_j,
        convergence_deg=10.0,
        overlap_fraction=0.9,
        pixel_scale_ratio=1.0,
        valid=True,
        q_geom=q_pair,
        q_overlap=q_pair,
        q_res=q_pair,
        q_pair=q_pair,
    )


# ---------------------------------------------------------------------------
# Pure logic tests
# ---------------------------------------------------------------------------

class TestPairGeomQuality:
    def test_mid_band(self):
        assert _pair_geom_quality(13.0, "urban_structured") == pytest.approx(1.0)

    def test_edge(self):
        assert _pair_geom_quality(8.0, "urban_structured") == pytest.approx(1.0)
        assert _pair_geom_quality(18.0, "urban_structured") == pytest.approx(1.0)

    def test_outside_band(self):
        assert _pair_geom_quality(3.0, "urban_structured") == pytest.approx(0.5)
        assert _pair_geom_quality(28.0, "urban_structured") == pytest.approx(0.0)


class TestTriBonusR:
    def test_none(self):
        assert _tri_bonus_R([False, False, False], False) == pytest.approx(0.0)

    def test_two_pairs_plus_anchor(self):
        assert _tri_bonus_R([True, True, False], True) == pytest.approx(1.0)

    def test_one_pair_plus_anchor(self):
        assert _tri_bonus_R([True, False, False], True) == pytest.approx(0.4)

    def test_three_pairs_no_anchor(self):
        assert _tri_bonus_R([True, True, True], False) == pytest.approx(0.6)

    def test_no_pairs_anchor_only(self):
        assert _tri_bonus_R([False, False, False], True) == pytest.approx(0.4)


class TestContractAlignment:
    def test_load_case_keeps_max_stereo_pair_separation(self):
        case_dir = (
            REPO_ROOT
            / "benchmarks"
            / "stereo_imaging"
            / "dataset"
            / "cases"
            / "test"
            / "case_0001"
        )
        mission, satellites, targets = solver_load_case(case_dir)

        assert mission.allow_cross_satellite_stereo is True
        assert mission.max_stereo_pair_separation_s == pytest.approx(3600.0)
        assert satellites
        assert targets

    def test_stereo_pair_representation_handles_cross_satellite_metadata(self):
        c1 = _candidate(sat_id="sat_a", interval_id="sat_a::t1::0")
        c2 = _candidate(sat_id="sat_b", interval_id="sat_b::t1::2", start_offset_s=30, end_offset_s=40)

        pair = StereoPair(
            target_id="t1",
            candidate_i=c1,
            candidate_j=c2,
            convergence_deg=10.0,
            overlap_fraction=0.9,
            pixel_scale_ratio=1.0,
            valid=True,
            q_geom=1.0,
            q_overlap=1.0,
            q_res=1.0,
            q_pair=0.95,
        )

        assert pair.satellite_ids == ("sat_a", "sat_b")
        assert pair.access_interval_ids == ("sat_a::t1::0", "sat_b::t1::2")
        assert pair.pair_mode == "cross_satellite"
        assert pair.sat_id == "__cross_satellite__"
        assert pair.access_interval_id == "__multiple_intervals__"

    def test_tri_representation_handles_multi_satellite_metadata(self):
        c1 = _candidate(sat_id="sat_a", interval_id="sat_a::t1::0")
        c2 = _candidate(sat_id="sat_b", interval_id="sat_b::t1::1", start_offset_s=20, end_offset_s=30)
        c3 = _candidate(sat_id="sat_c", interval_id="sat_c::t1::2", start_offset_s=40, end_offset_s=50)

        from models import TriStereoSet

        tri = TriStereoSet(
            target_id="t1",
            candidates=(c1, c2, c3),
            common_overlap_fraction=0.85,
            pair_valid_flags=[True, True, False],
            pair_qs=[0.8, 0.75, 0.0],
            has_anchor=True,
            valid=True,
            q_tri=0.9,
        )

        assert tri.satellite_ids == ("sat_a", "sat_b", "sat_c")
        assert tri.access_interval_ids == ("sat_a::t1::0", "sat_b::t1::1", "sat_c::t1::2")
        assert tri.sat_id == "__multi_satellite__"
        assert tri.access_interval_id == "__multiple_intervals__"


class TestRuntimeModeConfig:
    def test_default_mode_is_thorough(self):
        config = load_solver_config(None)

        assert config["runtime"]["mode"] == "thorough"
        assert config["_resolved_runtime_mode"] == "thorough"
        assert config["time_step_s"] == 30
        assert config["optimization"]["backend"] == "ortools"
        assert config["optimization"]["time_limit_s"] == 1800

    def test_fast_mode_applies_preset(self, tmp_path):
        (tmp_path / "config.yaml").write_text("runtime:\n  mode: fast\n", encoding="utf-8")

        config = load_solver_config(tmp_path)

        assert config["runtime"]["mode"] == "fast"
        assert config["time_step_s"] == 60
        assert config["sample_stride_s"] == 60
        assert config["overlap_grid_angles"] == 4
        assert config["optimization"]["backend"] == "greedy"

    def test_explicit_overrides_win_over_preset(self, tmp_path):
        (tmp_path / "config.yaml").write_text(
            "runtime:\n  mode: fast\n"
            "time_step_s: 42\n"
            "optimization:\n  backend: ortools\n  time_limit_s: 99\n",
            encoding="utf-8",
        )

        config = load_solver_config(tmp_path)

        assert config["runtime"]["mode"] == "fast"
        assert config["time_step_s"] == 42
        assert config["optimization"]["backend"] == "ortools"
        assert config["optimization"]["time_limit_s"] == 99


class TestPairPolicy:
    def test_stereo_pair_mode_accepts_same_satellite_same_pass(self):
        mission = _mission()
        c1 = _candidate(sat_id="sat_a", interval_id="i1", start_offset_s=0, end_offset_s=10)
        c2 = _candidate(sat_id="sat_a", interval_id="i1", start_offset_s=20, end_offset_s=30)

        assert _stereo_pair_mode(mission, c1, c2) == "same_satellite_same_pass"

    def test_stereo_pair_mode_rejects_same_satellite_other_interval(self):
        mission = _mission()
        c1 = _candidate(sat_id="sat_a", interval_id="i1", start_offset_s=0, end_offset_s=10)
        c2 = _candidate(sat_id="sat_a", interval_id="i2", start_offset_s=20, end_offset_s=30)

        assert _stereo_pair_mode(mission, c1, c2) is None

    def test_stereo_pair_mode_respects_cross_satellite_policy(self):
        c1 = _candidate(sat_id="sat_a", interval_id="i1", start_offset_s=0, end_offset_s=10)
        c2 = _candidate(sat_id="sat_b", interval_id="j1", start_offset_s=20, end_offset_s=30)

        assert _stereo_pair_mode(_mission(allow_cross_satellite_stereo=False), c1, c2) is None
        assert _stereo_pair_mode(_mission(allow_cross_satellite_stereo=True), c1, c2) == "cross_satellite"

    def test_stereo_pair_mode_accepts_exact_time_separation_bound(self):
        mission = _mission(allow_cross_satellite_stereo=True, max_stereo_pair_separation_s=20.0)
        c1 = _candidate(sat_id="sat_a", interval_id="i1", start_offset_s=0, end_offset_s=10)
        c2 = _candidate(sat_id="sat_b", interval_id="j1", start_offset_s=20, end_offset_s=30)

        assert _stereo_pair_mode(mission, c1, c2) == "cross_satellite"

    def test_stereo_pair_mode_rejects_time_separation_above_bound(self):
        mission = _mission(allow_cross_satellite_stereo=True, max_stereo_pair_separation_s=19.0)
        c1 = _candidate(sat_id="sat_a", interval_id="i1", start_offset_s=0, end_offset_s=10)
        c2 = _candidate(sat_id="sat_b", interval_id="j1", start_offset_s=20, end_offset_s=30)

        assert _stereo_pair_mode(mission, c1, c2) is None


def _stub_geo(
    sat_pos_m: np.ndarray,
    *,
    slant_range_m: float = 700000.0,
    pixel_scale: float = 1.0,
) -> _CandidateGeometry:
    return _CandidateGeometry(
        sat_pos_m=np.asarray(sat_pos_m, dtype=float),
        boresight_ground_m=np.asarray([6378137.0, 0.0, 0.0], dtype=float),
        slant_range_m=slant_range_m,
        pixel_scale_m=pixel_scale,
    )


class TestGeometryShortCircuits:
    def test_pair_skips_overlap_when_convergence_already_fails(self, monkeypatch):
        monkeypatch.setattr(product_module, "overlap_fraction_grid", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("overlap should not run")))

        target = _target()
        mission = _mission()
        sat = _satellite()
        c1 = _candidate()
        c2 = _candidate(start_offset_s=20, end_offset_s=30)
        target_ecef = np.asarray([6378137.0, 0.0, 0.0], dtype=float)

        pair = evaluate_pair(
            c1,
            c2,
            _stub_geo([7000000.0, 0.0, 0.0], pixel_scale=1.0),
            _stub_geo([7000000.0, 0.0, 0.0], pixel_scale=1.0),
            target,
            mission,
            {"overlap_grid_angles": 4, "overlap_grid_radii": 1},
            "same_satellite_same_pass",
            sf_i=object(),
            sf_j=object(),
            sat_i=sat,
            sat_j=sat,
            target_ecef=target_ecef,
            strip_step_s=8.0,
        )

        assert pair.valid is False
        assert pair.overlap_fraction == pytest.approx(0.0)

    def test_pair_skips_overlap_when_pixel_scale_already_fails(self, monkeypatch):
        monkeypatch.setattr(product_module, "overlap_fraction_grid", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("overlap should not run")))

        target = _target()
        mission = _mission()
        sat = _satellite()
        c1 = _candidate()
        c2 = _candidate(start_offset_s=20, end_offset_s=30)
        target_ecef = np.asarray([6378137.0, 0.0, 0.0], dtype=float)

        pair = evaluate_pair(
            c1,
            c2,
            _stub_geo([7000000.0, 0.0, 0.0], pixel_scale=1.0),
            _stub_geo([6950000.0, 800000.0, 0.0], pixel_scale=2.0),
            target,
            mission,
            {"overlap_grid_angles": 4, "overlap_grid_radii": 1},
            "same_satellite_same_pass",
            sf_i=object(),
            sf_j=object(),
            sat_i=sat,
            sat_j=sat,
            target_ecef=target_ecef,
            strip_step_s=8.0,
        )

        assert pair.valid is False
        assert pair.pixel_scale_ratio > mission.validity_thresholds.max_pixel_scale_ratio

    def test_tri_skips_overlap_without_anchor(self, monkeypatch):
        monkeypatch.setattr(product_module, "tri_overlap_fraction_grid", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("tri overlap should not run")))

        target = _target()
        mission = _mission(near_nadir_anchor_max_off_nadir_deg=5.0)
        sat = _satellite()
        c1 = _candidate(along=20.0)
        c2 = _candidate(start_offset_s=20, end_offset_s=30, along=22.0)
        c3 = _candidate(start_offset_s=40, end_offset_s=50, along=24.0)
        pair_results = {
            (0, 1): _pair(c1, c2, q_pair=0.8),
            (0, 2): _pair(c1, c3, q_pair=0.7),
            (1, 2): _pair(c2, c3, q_pair=0.6),
        }

        tri = evaluate_tri(
            (c1, c2, c3),
            (_stub_geo([7000000.0, 0.0, 0.0]), _stub_geo([6950000.0, 800000.0, 0.0]), _stub_geo([6900000.0, -900000.0, 0.0])),
            pair_results,
            (0, 1, 2),
            target,
            mission,
            {"overlap_grid_angles": 4, "overlap_grid_radii": 1},
            sfs=(object(), object(), object()),
            sats=(sat, sat, sat),
            target_ecef=np.asarray([6378137.0, 0.0, 0.0], dtype=float),
            strip_step_s=8.0,
        )

        assert tri.valid is False
        assert tri.common_overlap_fraction == pytest.approx(0.0)
        assert tri.has_anchor is False

    def test_tri_skips_overlap_with_only_one_valid_pair(self, monkeypatch):
        monkeypatch.setattr(product_module, "tri_overlap_fraction_grid", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("tri overlap should not run")))

        target = _target()
        mission = _mission()
        sat = _satellite()
        c1 = _candidate(across=2.0)
        c2 = _candidate(start_offset_s=20, end_offset_s=30, across=3.0)
        c3 = _candidate(start_offset_s=40, end_offset_s=50, across=12.0)
        pair_results = {
            (0, 1): _pair(c1, c2, q_pair=0.8),
            (0, 2): StereoPair(target_id="t1", candidate_i=c1, candidate_j=c3, convergence_deg=10.0, overlap_fraction=0.0, pixel_scale_ratio=1.0, valid=False, q_geom=0.0, q_overlap=0.0, q_res=0.0, q_pair=0.0),
            (1, 2): StereoPair(target_id="t1", candidate_i=c2, candidate_j=c3, convergence_deg=10.0, overlap_fraction=0.0, pixel_scale_ratio=1.0, valid=False, q_geom=0.0, q_overlap=0.0, q_res=0.0, q_pair=0.0),
        }

        tri = evaluate_tri(
            (c1, c2, c3),
            (_stub_geo([7000000.0, 0.0, 0.0]), _stub_geo([6950000.0, 800000.0, 0.0]), _stub_geo([6900000.0, -900000.0, 0.0])),
            pair_results,
            (0, 1, 2),
            target,
            mission,
            {"overlap_grid_angles": 4, "overlap_grid_radii": 1},
            sfs=(object(), object(), object()),
            sats=(sat, sat, sat),
            target_ecef=np.asarray([6378137.0, 0.0, 0.0], dtype=float),
            strip_step_s=8.0,
        )

        assert tri.valid is False
        assert tri.common_overlap_fraction == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Pair evaluation with mocked geometry
# ---------------------------------------------------------------------------

class TestEvaluatePair:
    def test_convergence_threshold_boundary(self, monkeypatch):
        """Exactly 5.0 and 45.0 deg should be valid; outside should be invalid."""
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        # Force target to origin so convergence equals the angle between sat vectors
        monkeypatch.setattr("products.target_ecef_m", lambda t: np.array([0.0, 0.0, 0.0]))

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 0.0])
            offset_s = (cand.start - base).total_seconds()
            angle_rad = math.radians(offset_s)
            sp = np.array([math.sin(angle_rad) * 7e6, 0.0, math.cos(angle_rad) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=target.aoi_radius_m * 2.0,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c5 = _candidate(start_offset_s=0, end_offset_s=10)
        c6 = _candidate(start_offset_s=5, end_offset_s=15)
        pairs, tris, summary = enumerate_products([c5, c6], {"sat_test": sat}, {"t1": target}, mission, config)
        assert len(pairs) == 1
        assert pairs[0].convergence_deg == pytest.approx(5.0, abs=1e-6)
        assert pairs[0].valid is True

    def test_overlap_threshold(self, monkeypatch):
        """Construct strips with known grid overlap."""
        sat = _satellite()
        target = _target(aoi_radius_m=500.0)
        mission = _mission(min_overlap_fraction=0.8)
        config = {"overlap_grid_angles": 8, "overlap_grid_radii": 3}

        # Force target to origin and give different sat positions for valid convergence
        monkeypatch.setattr("products.target_ecef_m", lambda t: np.array([0.0, 0.0, 0.0]))

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 0.0])
            # Use off_nadir_along_deg to select sat angle: 0 -> 0deg, 300 -> 10deg, 2000 -> 90deg
            angle = math.radians(cand.off_nadir_along_deg / 30.0)
            sp = np.array([math.sin(angle) * 7e6, 0.0, math.cos(angle) * 7e6])
            offset = cand.off_nadir_along_deg
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(offset, -2000.0), (offset, 2000.0)],
                strip_half_width_m=600.0,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c_full = _candidate(along=0.0)
        c_partial = _candidate(along=300.0)
        pairs, _, _ = enumerate_products([c_full, c_partial], {"sat_test": sat}, {"t1": target}, mission, config)
        assert len(pairs) == 1
        # offset 300 with half-width 600 and AOI radius 500 -> overlap > 0.8
        assert pairs[0].overlap_fraction >= 0.8
        assert pairs[0].valid is True

        c_miss = _candidate(along=2000.0)
        pairs2, _, _ = enumerate_products([c_full, c_miss], {"sat_test": sat}, {"t1": target}, mission, config)
        assert len(pairs2) == 1
        assert pairs2[0].overlap_fraction < 0.8
        assert pairs2[0].valid is False

    def test_pixel_scale_ratio_threshold(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission(max_pixel_scale_ratio=1.5)
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            offset_s = (cand.start - base).total_seconds()
            angle_rad = math.radians(offset_s)
            sp = np.array([math.sin(angle_rad) * 7e6, 0.0, math.cos(angle_rad) * 7e6])
            ps = 1.0 if offset_s == 0.0 else 1.5
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=ps,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c1 = _candidate(start_offset_s=0)
        c2 = _candidate(start_offset_s=10)
        pairs, _, _ = enumerate_products([c1, c2], {"sat_test": sat}, {"t1": target}, mission, config)
        assert len(pairs) == 1
        assert pairs[0].pixel_scale_ratio == pytest.approx(1.5, abs=1e-9)
        assert pairs[0].valid is True

        c3 = _candidate(start_offset_s=20)
        # make c3 have pixel_scale > 1.5
        def fake_precompute2(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            offset_s = (cand.start - base).total_seconds()
            angle_rad = math.radians(offset_s)
            sp = np.array([math.sin(angle_rad) * 7e6, 0.0, math.cos(angle_rad) * 7e6])
            ps = 1.0 if offset_s == 0.0 else 2.0
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=ps,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute2)
        pairs2, _, _ = enumerate_products([c1, c3], {"sat_test": sat}, {"t1": target}, mission, config)
        assert len(pairs2) == 1
        assert pairs2[0].pixel_scale_ratio > 1.5
        assert pairs2[0].valid is False

    def test_pair_quality_formula(self, monkeypatch):
        sat = _satellite()
        target = _target(scene_type="urban_structured")
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            return _CandidateGeometry(
                sat_pos_m=np.array([0.0, 0.0, 7e6]),
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, 0.0), (0.0, 100.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c1 = _candidate(along=0.0)
        c2 = _candidate(along=1.0)
        pairs, _, _ = enumerate_products([c1, c2], {"sat_test": sat}, {"t1": target}, mission, config)
        assert len(pairs) == 1
        p = pairs[0]
        expected_q = 0.5 * p.q_geom + 0.35 * p.q_overlap + 0.15 * p.q_res
        assert p.q_pair == pytest.approx(expected_q, abs=1e-9)


# ---------------------------------------------------------------------------
# Tri-stereo evaluation
# ---------------------------------------------------------------------------

class TestEvaluateTri:
    def test_tri_requires_two_valid_pairs_and_anchor(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            offset_s = (cand.start - base).total_seconds()
            angle_rad = math.radians(offset_s)
            sp = np.array([math.sin(angle_rad) * 7e6, 0.0, math.cos(angle_rad) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        # three candidates at 0, 10, 20 deg -> all pairs valid (10 and 20 deg differences), all nadir -> anchor present
        c1 = _candidate(start_offset_s=0, along=0.0)
        c2 = _candidate(start_offset_s=10, along=0.0)
        c3 = _candidate(start_offset_s=20, along=0.0)
        pairs, tris, _ = enumerate_products([c1, c2, c3], {"sat_test": sat}, {"t1": target}, mission, config)
        assert len(pairs) == 3
        assert all(p.valid for p in pairs)
        assert len(tris) == 1
        assert tris[0].valid is True
        assert tris[0].has_anchor is True

    def test_tri_fails_without_anchor(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission(near_nadir_anchor_max_off_nadir_deg=5.0)
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            return _CandidateGeometry(
                sat_pos_m=np.array([0.0, 0.0, 7e6]),
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, 0.0), (0.0, 100.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        # all candidates have combined off-nadir > 5.0 (we set along=10.0)
        c1 = _candidate(along=10.0)
        c2 = _candidate(along=10.0)
        c3 = _candidate(along=10.0)
        _, tris, _ = enumerate_products([c1, c2, c3], {"sat_test": sat}, {"t1": target}, mission, config)
        assert len(tris) == 1
        assert tris[0].has_anchor is False
        assert tris[0].valid is False

    def test_tri_fails_with_only_one_valid_pair(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission(min_convergence_deg=5.0, max_convergence_deg=45.0)
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            offset_s = (cand.start - base).total_seconds()
            angle = math.radians(offset_s)
            sp = np.array([math.sin(angle) * 7e6, 0.0, math.cos(angle) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c1 = _candidate(start_offset_s=0, along=0.0)    # anchor
        c2 = _candidate(start_offset_s=10, along=0.0)   # 10 deg -> valid pair with c1
        c3 = _candidate(start_offset_s=90, along=0.0)   # 90 deg -> invalid pair with c1 and c2
        pairs, tris, _ = enumerate_products([c1, c2, c3], {"sat_test": sat}, {"t1": target}, mission, config)
        # pairs: (c1,c2) valid, (c1,c3) invalid, (c2,c3) invalid
        assert sum(p.valid for p in pairs) == 1
        assert len(tris) == 1
        assert tris[0].pair_valid_flags.count(True) == 1
        assert tris[0].valid is False


# ---------------------------------------------------------------------------
# Grouping / enumeration integration
# ---------------------------------------------------------------------------

class TestEnumerateProducts:
    def test_same_satellite_different_interval_is_rejected(self, monkeypatch):
        sat = _satellite(sat_id="sat_a")
        target = _target()
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            return _CandidateGeometry(
                sat_pos_m=np.array([0.0, 0.0, 7e6]),
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, 0.0), (0.0, 100.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c1 = _candidate(interval_id="i1")
        c2 = _candidate(interval_id="i1")
        c3 = _candidate(interval_id="i2")
        pairs, tris, summary = enumerate_products([c1, c2, c3], {"sat_test": sat, "sat_a": sat}, {"t1": target}, mission, config)
        assert len(pairs) == 1
        assert pairs[0].access_interval_id == "i1"
        assert len(tris) == 0

    def test_cross_satellite_pair_enumerates_when_mission_allowed(self, monkeypatch):
        sat_a = _satellite(sat_id="sat_a")
        sat_b = _satellite(sat_id="sat_b")
        target = _target()
        mission = _mission(allow_cross_satellite_stereo=True, max_stereo_pair_separation_s=30.0)
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry

            te = np.array([0.0, 0.0, 6378137.0])
            angle_deg = {"sat_a": 0.0, "sat_b": 10.0}.get(cand.sat_id, 0.0)
            angle = math.radians(angle_deg)
            sp = np.array([math.sin(angle) * 7e6, 0.0, math.cos(angle) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c1 = _candidate(sat_id="sat_a", interval_id="sat_a::t1::0", start_offset_s=0, end_offset_s=10)
        c2 = _candidate(sat_id="sat_b", interval_id="sat_b::t1::1", start_offset_s=20, end_offset_s=30)

        pairs, tris, summary = enumerate_products(
            [c1, c2],
            {"sat_a": sat_a, "sat_b": sat_b},
            {"t1": target},
            mission,
            config,
        )

        assert len(pairs) == 1
        assert len(tris) == 0
        pair = pairs[0]
        assert pair.valid is True
        assert pair.pair_mode == "cross_satellite"
        assert pair.satellite_ids == ("sat_a", "sat_b")
        assert pair.access_interval_ids == ("sat_a::t1::0", "sat_b::t1::1")
        assert pair.time_separation_s == pytest.approx(20.0)
        assert summary.pair_mode_counts == {"cross_satellite": 1}
        assert summary.valid_pair_mode_counts == {"cross_satellite": 1}

    def test_cross_satellite_pair_rejected_when_mission_disabled(self, monkeypatch):
        sat_a = _satellite(sat_id="sat_a")
        sat_b = _satellite(sat_id="sat_b")
        target = _target()
        mission = _mission(allow_cross_satellite_stereo=False)
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry

            te = np.array([0.0, 0.0, 6378137.0])
            angle_deg = {"sat_a": 0.0, "sat_b": 10.0}.get(cand.sat_id, 0.0)
            angle = math.radians(angle_deg)
            sp = np.array([math.sin(angle) * 7e6, 0.0, math.cos(angle) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c1 = _candidate(sat_id="sat_a", interval_id="sat_a::t1::0", start_offset_s=0, end_offset_s=10)
        c2 = _candidate(sat_id="sat_b", interval_id="sat_b::t1::1", start_offset_s=20, end_offset_s=30)

        pairs, tris, summary = enumerate_products(
            [c1, c2],
            {"sat_a": sat_a, "sat_b": sat_b},
            {"t1": target},
            mission,
            config,
        )

        assert len(pairs) == 0
        assert len(tris) == 0
        assert summary.total_pairs == 0
        assert summary.pair_mode_counts == {}

    def test_pair_above_separation_bound_is_rejected(self, monkeypatch):
        sat_a = _satellite(sat_id="sat_a")
        sat_b = _satellite(sat_id="sat_b")
        target = _target()
        mission = _mission(allow_cross_satellite_stereo=True, max_stereo_pair_separation_s=10.0)
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry

            te = np.array([0.0, 0.0, 6378137.0])
            angle_deg = {"sat_a": 0.0, "sat_b": 10.0}.get(cand.sat_id, 0.0)
            angle = math.radians(angle_deg)
            sp = np.array([math.sin(angle) * 7e6, 0.0, math.cos(angle) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c1 = _candidate(sat_id="sat_a", interval_id="sat_a::t1::0", start_offset_s=0, end_offset_s=10)
        c2 = _candidate(sat_id="sat_b", interval_id="sat_b::t1::1", start_offset_s=20, end_offset_s=30)

        pairs, tris, summary = enumerate_products(
            [c1, c2],
            {"sat_a": sat_a, "sat_b": sat_b},
            {"t1": target},
            mission,
            config,
        )

        assert len(pairs) == 0
        assert len(tris) == 0
        assert summary.total_pairs == 0

    def test_cross_satellite_tri_requires_policy_compliant_edges(self, monkeypatch):
        sat_a = _satellite(sat_id="sat_a")
        sat_b = _satellite(sat_id="sat_b")
        target = _target()
        mission = _mission(allow_cross_satellite_stereo=True, max_stereo_pair_separation_s=40.0)
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry

            te = np.array([0.0, 0.0, 6378137.0])
            angle_deg = {"sat_a": 0.0, "sat_b": 10.0}.get(cand.sat_id, 0.0)
            angle = math.radians(angle_deg)
            sp = np.array([math.sin(angle) * 7e6, 0.0, math.cos(angle) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c1 = _candidate(sat_id="sat_a", interval_id="sat_a::t1::0", start_offset_s=0, end_offset_s=10)
        c2 = _candidate(sat_id="sat_b", interval_id="sat_b::t1::1", start_offset_s=10, end_offset_s=20)
        c3 = _candidate(sat_id="sat_a", interval_id="sat_a::t1::2", start_offset_s=20, end_offset_s=30)

        pairs, tris, summary = enumerate_products(
            [c1, c2, c3],
            {"sat_a": sat_a, "sat_b": sat_b},
            {"t1": target},
            mission,
            config,
        )

        assert len(pairs) == 2
        assert len(tris) == 0
        assert summary.total_pairs == 2
        assert summary.total_tris == 0

    def test_cross_satellite_tri_can_enumerate(self, monkeypatch):
        sat_a = _satellite(sat_id="sat_a")
        sat_b = _satellite(sat_id="sat_b")
        sat_c = _satellite(sat_id="sat_c")
        target = _target()
        mission = _mission(allow_cross_satellite_stereo=True, max_stereo_pair_separation_s=40.0)
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry

            te = np.array([0.0, 0.0, 6378137.0])
            angle_deg = {"sat_a": 0.0, "sat_b": 10.0, "sat_c": 20.0}.get(cand.sat_id, 0.0)
            angle = math.radians(angle_deg)
            sp = np.array([math.sin(angle) * 7e6, 0.0, math.cos(angle) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c1 = _candidate(sat_id="sat_a", interval_id="sat_a::t1::0", start_offset_s=0, end_offset_s=10)
        c2 = _candidate(sat_id="sat_b", interval_id="sat_b::t1::1", start_offset_s=10, end_offset_s=20)
        c3 = _candidate(sat_id="sat_c", interval_id="sat_c::t1::2", start_offset_s=20, end_offset_s=30)

        pairs, tris, summary = enumerate_products(
            [c1, c2, c3],
            {"sat_a": sat_a, "sat_b": sat_b, "sat_c": sat_c},
            {"t1": target},
            mission,
            config,
        )

        assert len(pairs) == 3
        assert all(pair.valid for pair in pairs)
        assert len(tris) == 1
        assert tris[0].valid is True
        assert tris[0].satellite_ids == ("sat_a", "sat_b", "sat_c")
        assert summary.multi_satellite_tris == 1
        assert summary.valid_multi_satellite_tris == 1


# ---------------------------------------------------------------------------
# Pruning tests
# ---------------------------------------------------------------------------

class TestClusterByGap:
    def test_one_cluster_when_gap_small(self):
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)
        cands = [
            _candidate(start_offset_s=i, end_offset_s=i + 2)
            for i in range(0, 10, 3)
        ]
        clusters = cluster_candidates_by_gap(cands, gap_s=5.0)
        assert len(clusters) == 1
        assert len(clusters[0]) == 4

    def test_two_clusters_when_gap_large(self):
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)
        cands = [
            _candidate(start_offset_s=0, end_offset_s=2),
            _candidate(start_offset_s=3, end_offset_s=5),
            _candidate(start_offset_s=20, end_offset_s=22),
            _candidate(start_offset_s=23, end_offset_s=25),
        ]
        clusters = cluster_candidates_by_gap(cands, gap_s=5.0)
        assert len(clusters) == 2
        assert len(clusters[0]) == 2
        assert len(clusters[1]) == 2

    def test_mixed_gap_boundary(self):
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)
        cands = [
            _candidate(start_offset_s=0, end_offset_s=2),
            _candidate(start_offset_s=3, end_offset_s=5),
            _candidate(start_offset_s=7, end_offset_s=9),   # gap from prev = 2s (<=5)
            _candidate(start_offset_s=15, end_offset_s=17), # gap from prev = 6s (>5)
        ]
        clusters = cluster_candidates_by_gap(cands, gap_s=5.0)
        assert len(clusters) == 2
        assert len(clusters[0]) == 3
        assert len(clusters[1]) == 1

    def test_per_satellite_isolation(self):
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)
        cands = [
            _candidate(sat_id="sat_a", start_offset_s=0, end_offset_s=2),
            _candidate(sat_id="sat_a", start_offset_s=3, end_offset_s=5),
            _candidate(sat_id="sat_b", start_offset_s=1, end_offset_s=3),
            _candidate(sat_id="sat_b", start_offset_s=4, end_offset_s=6),
        ]
        clusters = cluster_candidates_by_gap(cands, gap_s=5.0)
        assert len(clusters) == 2  # one per satellite


class TestComputeClusterGapS:
    def test_typical_satellite(self):
        sat = Satellite(
            id="sat_test",
            norad_catalog_id=1,
            tle_line1="1 00000U 00000A   00000.00000000  .00000000  00000+0  00000-0 0  0000",
            tle_line2="2 00000   0.0000   0.0000 0000000   0.0000   0.0000  0.00000000000000",
            pixel_ifov_deg=4.0e-05,
            cross_track_pixels=20000,
            max_off_nadir_deg=30.0,
            max_slew_velocity_deg_per_s=1.0,
            max_slew_acceleration_deg_per_s2=1.0,
            settling_time_s=5.0,
            min_obs_duration_s=2.0,
            max_obs_duration_s=60.0,
        )
        gap = compute_cluster_gap_s(sat)
        assert gap == pytest.approx(4.0 * 30.0 / 1.0 + 5.0)


class TestComputeLambdaLB:
    def test_typical(self):
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)
        sat = Satellite(
            id="sat_test",
            norad_catalog_id=1,
            tle_line1="1 00000U 00000A   00000.00000000  .00000000  00000+0  00000-0 0  0000",
            tle_line2="2 00000   0.0000   0.0000 0000000   0.0000   0.0000  0.00000000000000",
            pixel_ifov_deg=4.0e-05,
            cross_track_pixels=20000,
            max_off_nadir_deg=30.0,
            max_slew_velocity_deg_per_s=1.0,
            max_slew_acceleration_deg_per_s2=1.0,
            settling_time_s=5.0,
            min_obs_duration_s=2.0,
            max_obs_duration_s=60.0,
        )
        cands = [
            _candidate(start_offset_s=0, end_offset_s=10),
            _candidate(start_offset_s=20, end_offset_s=30),
        ]
        lb = compute_lambda_lb(cands, {"sat_test": sat})
        avg_obs = 10.0
        avg_settle = 5.0
        expected = max(1, int(avg_obs / (avg_obs + avg_settle)))
        assert lb == expected

    def test_empty_returns_one(self):
        assert compute_lambda_lb([], {}) == 1


class TestScoreCandidates:
    def test_scarcity_and_product_count(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            offset_s = (cand.start - base).total_seconds()
            angle = math.radians(offset_s)
            sp = np.array([math.sin(angle) * 7e6, 0.0, math.cos(angle) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c1 = _candidate(start_offset_s=0, along=0.0)
        c2 = _candidate(start_offset_s=10, along=0.0)
        c3 = _candidate(start_offset_s=20, along=0.0)
        pairs, tris, _ = enumerate_products([c1, c2, c3], {"sat_test": sat}, {"t1": target}, mission, config)

        target_totals = {"t1": 3}
        metrics = _build_candidate_to_metrics(pairs, tris)
        scores = _score_candidates(
            [c1, c2, c3], metrics, target_totals,
            mission.validity_thresholds.near_nadir_anchor_max_off_nadir_deg,
        )
        assert len(scores) == 3
        # All should have valid products (pairs + one tri) because 10° and 20° separations
        assert all(s.has_valid_product for s in scores)
        # All are anchors (combined_off_nadir = 0)
        assert all(s.is_anchor for s in scores)

    def test_orphan_has_no_product(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            return _CandidateGeometry(
                sat_pos_m=np.array([0.0, 0.0, 7e6]),
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, 0.0), (0.0, 100.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c1 = _candidate(start_offset_s=0, along=0.0)
        c2 = _candidate(start_offset_s=10, along=0.0)
        pairs, tris, _ = enumerate_products([c1, c2], {"sat_test": sat}, {"t1": target}, mission, config)

        # Add an orphan that is far apart -> no pair
        c_orphan = _candidate(start_offset_s=1000, along=0.0)
        cluster = [c1, c2, c_orphan]
        target_totals = {"t1": 3}
        metrics = _build_candidate_to_metrics(pairs, tris)
        scores = _score_candidates(
            cluster, metrics, target_totals,
            mission.validity_thresholds.near_nadir_anchor_max_off_nadir_deg,
        )
        orphan_score = next(s for s in scores if s.cand is c_orphan)
        assert orphan_score.has_valid_product is False
        assert orphan_score.valid_pair_count == 0


class TestRankKey:
    def test_product_participant_ranks_above_orphan(self):
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)
        c_prod = _candidate(start_offset_s=0)
        c_orphan = _candidate(start_offset_s=10)

        s_prod = _CandidateScore(c_prod, has_valid_product=True, scarcity=0.5, max_q=0.8, is_anchor=True, valid_pair_count=1, valid_tri_count=0)
        s_orphan = _CandidateScore(c_orphan, has_valid_product=False, scarcity=0.5, max_q=0.0, is_anchor=True, valid_pair_count=0, valid_tri_count=0)

        r_prod = _rank_key(s_prod, cluster_mean_on=0.0)
        r_orphan = _rank_key(s_orphan, cluster_mean_on=0.0)
        assert r_prod < r_orphan  # lower is better

    def test_scarcer_target_ranks_higher(self):
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)
        c_scarce = _candidate(target_id="t_scarce", start_offset_s=0)
        c_abundant = _candidate(target_id="t_abundant", start_offset_s=0)

        s_scarce = _CandidateScore(c_scarce, has_valid_product=True, scarcity=0.9, max_q=0.5, is_anchor=True, valid_pair_count=1, valid_tri_count=0)
        s_abundant = _CandidateScore(c_abundant, has_valid_product=True, scarcity=0.1, max_q=0.5, is_anchor=True, valid_pair_count=1, valid_tri_count=0)

        r_scarce = _rank_key(s_scarce, cluster_mean_on=0.0)
        r_abundant = _rank_key(s_abundant, cluster_mean_on=0.0)
        assert r_scarce < r_abundant


class TestPruneCandidates:
    def test_reduces_model_size(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
            "pruning": {
                "enabled": True,
                "cluster_gap_s": 1000.0,  # one big cluster
                "max_candidates_per_cluster": 2,
                "min_candidates_per_cluster": 1,
                "max_total_candidates": 10000,
                "preserve_anchors": True,
                "preserve_products": True,
            },
        }

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            return _CandidateGeometry(
                sat_pos_m=np.array([0.0, 0.0, 7e6]),
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, 0.0), (0.0, 100.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        cands = [_candidate(start_offset_s=i * 10, along=0.0) for i in range(6)]
        pairs, tris, _ = enumerate_products(cands, {"sat_test": sat}, {"t1": target}, mission, config)
        pre_pairs = len(pairs)

        pruned_cands, pruned_pairs, pruned_tris, summary = prune_candidates(
            cands, pairs, tris, {"sat_test": sat}, {"t1": target}, mission, config
        )

        assert summary.enabled is True
        assert summary.pre_candidates == 6
        assert summary.post_candidates <= 6
        assert summary.post_candidates < summary.pre_candidates or pre_pairs == 0
        assert summary.lambda_cap == 2

    def test_disabled_passthrough(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
            "pruning": {"enabled": False},
        }

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            return _CandidateGeometry(
                sat_pos_m=np.array([0.0, 0.0, 7e6]),
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, 0.0), (0.0, 100.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        cands = [_candidate(start_offset_s=i * 10, along=0.0) for i in range(4)]
        pairs, tris, _ = enumerate_products(cands, {"sat_test": sat}, {"t1": target}, mission, config)

        pruned_cands, pruned_pairs, pruned_tris, summary = prune_candidates(
            cands, pairs, tris, {"sat_test": sat}, {"t1": target}, mission, config
        )

        # When pruning is disabled in config, prune_candidates should return passthrough
        assert summary.enabled is False
        assert summary.post_candidates == summary.pre_candidates
        assert summary.post_pairs == summary.pre_pairs

    def test_deterministic(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
            "pruning": {
                "enabled": True,
                "cluster_gap_s": 1000.0,
                "max_candidates_per_cluster": 3,
                "min_candidates_per_cluster": 1,
                "max_total_candidates": 10000,
                "preserve_anchors": True,
                "preserve_products": True,
            },
        }

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            return _CandidateGeometry(
                sat_pos_m=np.array([0.0, 0.0, 7e6]),
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, 0.0), (0.0, 100.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        cands = [_candidate(start_offset_s=i * 10, along=float(i)) for i in range(6)]
        pairs, tris, _ = enumerate_products(cands, {"sat_test": sat}, {"t1": target}, mission, config)

        r1 = prune_candidates(cands, pairs, tris, {"sat_test": sat}, {"t1": target}, mission, config)
        r2 = prune_candidates(cands, pairs, tris, {"sat_test": sat}, {"t1": target}, mission, config)

        assert [c.start for c in r1[0]] == [c.start for c in r2[0]]

    def test_no_silent_target_loss(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
            "pruning": {
                "enabled": True,
                "cluster_gap_s": 1000.0,
                "max_candidates_per_cluster": 1,
                "min_candidates_per_cluster": 1,
                "max_total_candidates": 10000,
                "preserve_anchors": True,
                "preserve_products": True,
            },
        }

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            return _CandidateGeometry(
                sat_pos_m=np.array([0.0, 0.0, 7e6]),
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, 0.0), (0.0, 100.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)
        cands = [
            _candidate(target_id="t1", start_offset_s=0, along=0.0),
            _candidate(target_id="t1", start_offset_s=10, along=1.0),
            _candidate(target_id="t2", start_offset_s=20, along=0.0),
            _candidate(target_id="t2", start_offset_s=30, along=1.0),
        ]
        pairs, tris, _ = enumerate_products(cands, {"sat_test": sat}, {"t1": target, "t2": _target(target_id="t2")}, mission, config)

        pruned_cands, _, _, summary = prune_candidates(
            cands, pairs, tris, {"sat_test": sat}, {"t1": target, "t2": _target(target_id="t2")}, mission, config
        )

        # Every target should have a by_target entry
        assert "t1" in summary.by_target
        assert "t2" in summary.by_target
        # If a target lost all candidates, pre > 0 and post == 0 should be recorded
        for tid, info in summary.by_target.items():
            assert info["pre"] > 0

    def test_anchor_preservation(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
            "pruning": {
                "enabled": True,
                "cluster_gap_s": 1000.0,
                "max_candidates_per_cluster": 1,
                "min_candidates_per_cluster": 1,
                "max_total_candidates": 10000,
                "preserve_anchors": True,
                "preserve_products": False,
            },
        }

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            return _CandidateGeometry(
                sat_pos_m=np.array([0.0, 0.0, 7e6]),
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, 0.0), (0.0, 100.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        # One anchor (along=0) and one non-anchor (along=20)
        c_anchor = _candidate(start_offset_s=0, along=0.0)
        c_non_anchor = _candidate(start_offset_s=10, along=20.0)
        cands = [c_anchor, c_non_anchor]
        pairs, tris, _ = enumerate_products(cands, {"sat_test": sat}, {"t1": target}, mission, config)

        pruned_cands, _, _, summary = prune_candidates(
            cands, pairs, tris, {"sat_test": sat}, {"t1": target}, mission, config
        )

        # The anchor should be preserved even if lambda=1 and non-anchor has higher rank
        assert len(pruned_cands) >= 1
        assert any(c.combined_off_nadir_deg <= mission.validity_thresholds.near_nadir_anchor_max_off_nadir_deg + 1e-6 for c in pruned_cands)
        assert summary.preservation_forced >= 1


# ---------------------------------------------------------------------------
# MILP / conflict / greedy heuristic tests
# ---------------------------------------------------------------------------

class TestConflictGraph:
    def test_overlap_conflict(self):
        sat = _satellite()
        c1 = _candidate(start_offset_s=0, end_offset_s=10)
        c2 = _candidate(start_offset_s=5, end_offset_s=15)
        conflicts = build_conflict_graph([c1, c2], {"sat_test": sat})
        assert (0, 1) in conflicts
        assert conflicts[(0, 1)] == "overlap"

    def test_no_conflict_when_gap_sufficient(self):
        sat = Satellite(
            id="sat_test",
            norad_catalog_id=1,
            tle_line1="1 00000U 00000A   00000.00000000  .00000000  00000+0  00000-0 0  0000",
            tle_line2="2 00000   0.0000   0.0000 0000000   0.0000   0.0000  0.00000000000000",
            pixel_ifov_deg=4.0e-05,
            cross_track_pixels=20000,
            max_off_nadir_deg=30.0,
            max_slew_velocity_deg_per_s=1.0,
            max_slew_acceleration_deg_per_s2=1.0,
            settling_time_s=1.0,
            min_obs_duration_s=2.0,
            max_obs_duration_s=60.0,
        )
        c1 = _candidate(start_offset_s=0, end_offset_s=2)
        c2 = _candidate(start_offset_s=200, end_offset_s=202)
        conflicts = build_conflict_graph([c1, c2], {"sat_test": sat})
        assert (0, 1) not in conflicts

    def test_no_conflict_different_satellites(self):
        sat = _satellite()
        c1 = _candidate(sat_id="sat_a", start_offset_s=0, end_offset_s=10)
        c2 = _candidate(sat_id="sat_b", start_offset_s=5, end_offset_s=15)
        conflicts = build_conflict_graph([c1, c2], {"sat_a": sat, "sat_b": sat})
        assert (0, 1) not in conflicts

    def test_slew_conflict_small_gap(self):
        sat = Satellite(
            id="sat_test",
            norad_catalog_id=1,
            tle_line1="1 00000U 00000A   00000.00000000  .00000000  00000+0  00000-0 0  0000",
            tle_line2="2 00000   0.0000   0.0000 0000000   0.0000   0.0000  0.00000000000000",
            pixel_ifov_deg=4.0e-05,
            cross_track_pixels=20000,
            max_off_nadir_deg=30.0,
            max_slew_velocity_deg_per_s=1.0,
            max_slew_acceleration_deg_per_s2=1.0,
            settling_time_s=5.0,
            min_obs_duration_s=2.0,
            max_obs_duration_s=60.0,
        )
        c1 = _candidate(start_offset_s=0, end_offset_s=2)
        c2 = _candidate(start_offset_s=3, end_offset_s=5)
        conflicts = build_conflict_graph([c1, c2], {"sat_test": sat})
        assert (0, 1) in conflicts
        assert conflicts[(0, 1)] == "slew"


class TestBuildMILP:
    def test_model_counts(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
        }
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            offset_s = (cand.start - base).total_seconds()
            angle = math.radians(offset_s)
            sp = np.array([math.sin(angle) * 7e6, 0.0, math.cos(angle) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c1 = _candidate(start_offset_s=0, along=0.0)
        c2 = _candidate(start_offset_s=10, along=0.0)
        c3 = _candidate(start_offset_s=20, along=0.0)
        cands = [c1, c2, c3]
        pairs, tris, _ = enumerate_products(cands, {"sat_test": sat}, {"t1": target}, mission, config)

        model = build_milp(cands, pairs, tris, {"t1": target}, {"sat_test": sat}, mission, config)

        assert len(model.obs_vars) == 3
        assert len(model.pair_vars) == 3  # 3 choose 2
        assert len(model.tri_vars) == 1  # 3 choose 3
        assert len(model.target_coverage_vars) == 1
        # Pair links: 2 per pair = 6
        assert len(model.pair_link_constraints) == 6
        assert len(model.pair_activation_constraints) == 3
        # Tri links: 3 per tri = 3
        assert len(model.tri_link_constraints) == 3
        assert len(model.tri_activation_constraints) == 1
        # Coverage constraint: 1
        assert len(model.target_coverage_constraints) == 1

    def test_coverage_bonus_is_lexicographic(self):
        sat = _satellite()
        target_a = _target(target_id="t1")
        target_b = _target(target_id="t2")
        mission = _mission()
        config = {}
        cands = [_candidate(start_offset_s=0)]
        model = build_milp(cands, [], [], {"t1": target_a, "t2": target_b}, {"sat_test": sat}, mission, config)
        assert model.coverage_bonus == pytest.approx(3.0)

    def test_evaluate_solution_uses_best_per_target_quality(self):
        sat = _satellite()
        target = _target()
        mission = _mission()
        c1 = _candidate(start_offset_s=0, end_offset_s=10)
        c2 = _candidate(start_offset_s=20, end_offset_s=30)
        c3 = _candidate(start_offset_s=40, end_offset_s=50)
        c4 = _candidate(start_offset_s=60, end_offset_s=70)

        high = _pair(c1, c2, q_pair=0.9)
        low = _pair(c3, c4, q_pair=0.6)
        model = build_milp(
            [c1, c2, c3, c4],
            [high, low],
            [],
            {"t1": target},
            {"sat_test": sat},
            mission,
            {},
        )

        evaluation = _evaluate_solution(model, [0, 1, 2, 3])

        assert evaluation["selected_pairs"] == 2
        assert evaluation["covered_targets"] == 1
        assert evaluation["best_target_quality_sum"] == pytest.approx(0.9)
        assert evaluation["normalized_quality"] == pytest.approx(0.9)
        assert evaluation["per_target_best_score"] == {"t1": pytest.approx(0.9)}


class TestGreedyHeuristic:
    def test_selects_single_valid_pair(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
        }
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            offset_s = (cand.start - base).total_seconds()
            angle = math.radians(offset_s)
            sp = np.array([math.sin(angle) * 7e6, 0.0, math.cos(angle) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        # Use large gap to avoid slew conflict (same boresight -> delta=0, need=settle+0.5)
        c1 = _candidate(start_offset_s=0, end_offset_s=2)
        c2 = _candidate(start_offset_s=20, end_offset_s=22)
        cands = [c1, c2]
        pairs, tris, _ = enumerate_products(cands, {"sat_test": sat}, {"t1": target}, mission, config)

        model = build_milp(cands, pairs, tris, {"t1": target}, {"sat_test": sat}, mission, config)
        selected, obj, stats = solve_greedy_heuristic(model, config)

        assert len(selected) == 2
        assert obj > 0

    def test_prefers_higher_quality_pair(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
        }
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            offset_s = (cand.start - base).total_seconds()
            angle = math.radians(offset_s)
            sp = np.array([math.sin(angle) * 7e6, 0.0, math.cos(angle) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        # c1-c2 and c1-c3 are valid pairs; c2-c3 is also valid
        # We want greedy to pick the best quality pair(s)
        c1 = _candidate(start_offset_s=0, along=0.0)
        c2 = _candidate(start_offset_s=10, along=0.0)
        c3 = _candidate(start_offset_s=20, along=0.0)
        cands = [c1, c2, c3]
        pairs, tris, _ = enumerate_products(cands, {"sat_test": sat}, {"t1": target}, mission, config)

        model = build_milp(cands, pairs, tris, {"t1": target}, {"sat_test": sat}, mission, config)
        selected, obj, stats = solve_greedy_heuristic(model, config)

        # Should select at least one pair (2 observations)
        assert len(selected) >= 2

    def test_deterministic(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
        }
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            offset_s = (cand.start - base).total_seconds()
            angle = math.radians(offset_s)
            sp = np.array([math.sin(angle) * 7e6, 0.0, math.cos(angle) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        c1 = _candidate(start_offset_s=0, along=0.0)
        c2 = _candidate(start_offset_s=10, along=0.0)
        c3 = _candidate(start_offset_s=20, along=0.0)
        cands = [c1, c2, c3]
        pairs, tris, _ = enumerate_products(cands, {"sat_test": sat}, {"t1": target}, mission, config)

        model = build_milp(cands, pairs, tris, {"t1": target}, {"sat_test": sat}, mission, config)
        r1, _, _ = solve_greedy_heuristic(model, config)
        r2, _, _ = solve_greedy_heuristic(model, config)
        assert r1 == r2

    def test_prefers_new_target_over_redundant_same_target_quality(self):
        sat_a = _satellite("sat_a")
        sat_b = _satellite("sat_b")
        mission = _mission()
        target1 = _target("t1")
        target2 = _target("t2")
        config = {}

        a1 = _candidate(sat_id="sat_a", target_id="t1", interval_id="sat_a::t1::0", start_offset_s=0, end_offset_s=10)
        a2 = _candidate(sat_id="sat_b", target_id="t1", interval_id="sat_b::t1::0", start_offset_s=20, end_offset_s=30)
        b1 = _candidate(sat_id="sat_a", target_id="t1", interval_id="sat_a::t1::1", start_offset_s=40, end_offset_s=50)
        b2 = _candidate(sat_id="sat_b", target_id="t1", interval_id="sat_b::t1::1", start_offset_s=60, end_offset_s=70)
        c1 = _candidate(sat_id="sat_a", target_id="t2", interval_id="sat_a::t2::0", start_offset_s=80, end_offset_s=90)
        c2 = _candidate(sat_id="sat_b", target_id="t2", interval_id="sat_b::t2::0", start_offset_s=100, end_offset_s=110)

        pairs = [
            _pair(a1, a2, target_id="t1", q_pair=0.9),
            _pair(b1, b2, target_id="t1", q_pair=0.6),
            _pair(c1, c2, target_id="t2", q_pair=0.55),
        ]
        model = build_milp(
            [a1, a2, b1, b2, c1, c2],
            pairs,
            [],
            {"t1": target1, "t2": target2},
            {"sat_a": sat_a, "sat_b": sat_b},
            mission,
            config,
            prebuilt_conflicts={(2, 4): "overlap"},
        )

        selected, _, _ = solve_greedy_heuristic(model, config)
        evaluation = _evaluate_solution(model, selected)

        assert selected == [0, 1, 4, 5]
        assert evaluation["covered_targets"] == 2
        assert evaluation["best_target_quality_sum"] == pytest.approx(1.45)
        assert evaluation["per_target_best_score"] == {
            "t1": pytest.approx(0.9),
            "t2": pytest.approx(0.55),
        }


class TestSolveMILP:
    def test_ortools_exact_suppresses_redundant_observation(self):
        pytest.importorskip("ortools.sat.python.cp_model")

        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {"optimization": {"backend": "ortools", "time_limit_s": 30.0}}

        c1 = _candidate(start_offset_s=0, end_offset_s=10)
        c2 = _candidate(start_offset_s=100, end_offset_s=110)
        redundant = _candidate(target_id="unused", start_offset_s=200, end_offset_s=210)
        model = build_milp(
            [c1, c2, redundant],
            [_pair(c1, c2, target_id="t1", q_pair=0.9)],
            [],
            {"t1": target},
            {"sat_test": sat},
            mission,
            config,
            prebuilt_conflicts={},
        )

        selected, objective_value, stats = solve_with_ortools(model, time_limit_s=30.0)
        evaluation = _evaluate_solution(model, selected)

        assert selected == [0, 1]
        assert objective_value == pytest.approx(model.coverage_bonus + 0.9)
        assert evaluation["covered_targets"] == 1
        assert evaluation["best_target_quality_sum"] == pytest.approx(0.9)
        assert stats["tie_break_status"] in {"OPTIMAL", "FEASIBLE"}
        assert stats["tie_break_selected_observations"] == 2
        assert stats["is_exact_backend"] is True

    def test_exact_backend_missing_fails_hard(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {"optimization": {"backend": "ortools"}}

        def fake_ortools(model, time_limit_s):
            raise BackendUnavailable("ortools import failed")

        monkeypatch.setattr("milp_model.solve_with_ortools", fake_ortools)

        c1 = _candidate(start_offset_s=0, end_offset_s=2)
        c2 = _candidate(start_offset_s=20, end_offset_s=22)
        cands = [c1, c2]
        pairs = [_pair(c1, c2)]

        with pytest.raises(BackendUnavailable, match="OR-Tools exact backend unavailable"):
            solve_milp(cands, pairs, [], {"t1": target}, {"sat_test": sat}, mission, config)

    def test_auto_backend_is_not_supported(self):
        sat = _satellite()
        target = _target()
        mission = _mission()
        c1 = _candidate(start_offset_s=0, end_offset_s=2)
        c2 = _candidate(start_offset_s=20, end_offset_s=22)
        config = {"optimization": {"backend": "auto"}}

        with pytest.raises(ValueError, match="unknown optimization.backend"):
            solve_milp([c1, c2], [_pair(c1, c2)], [], {"t1": target}, {"sat_test": sat}, mission, config)

    def test_greedy_backend_explicit(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
            "optimization": {"backend": "greedy"},
        }
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sf, sat, target):
            from products import _CandidateGeometry
            te = np.array([0.0, 0.0, 6378137.0])
            offset_s = (cand.start - base).total_seconds()
            angle = math.radians(offset_s)
            sp = np.array([math.sin(angle) * 7e6, 0.0, math.cos(angle) * 7e6])
            return _CandidateGeometry(
                sat_pos_m=sp,
                boresight_ground_m=te,
                slant_range_m=1e6,
                pixel_scale_m=1.0,
                strip_polyline_en=[(0.0, -5000.0), (0.0, 5000.0)],
                strip_half_width_m=1e6,
            )

        monkeypatch.setattr("products._precompute_candidate_geometry", fake_precompute)

        # Use large gap to avoid slew conflict
        c1 = _candidate(start_offset_s=0, end_offset_s=2)
        c2 = _candidate(start_offset_s=20, end_offset_s=22)
        cands = [c1, c2]
        pairs, tris, _ = enumerate_products(cands, {"sat_test": sat}, {"t1": target}, mission, config)

        selected, summary = solve_milp(cands, pairs, tris, {"t1": target}, {"sat_test": sat}, mission, config)

        assert summary.backend_used == "greedy"
        assert len(selected) == 2
        assert summary.selected_pairs == 1
        assert summary.covered_targets == 1
        assert summary.coverage_ratio == pytest.approx(1.0)
        assert summary.best_target_quality_sum == pytest.approx(summary.objective_quality)
        assert summary.normalized_quality == pytest.approx(summary.best_target_quality_sum)

    def test_summary_reports_best_per_target_scores(self):
        sat_a = _satellite("sat_a")
        sat_b = _satellite("sat_b")
        mission = _mission()
        target1 = _target("t1")
        target2 = _target("t2")
        config = {"optimization": {"backend": "greedy"}}

        a1 = _candidate(sat_id="sat_a", target_id="t1", interval_id="sat_a::t1::0", start_offset_s=0, end_offset_s=10)
        a2 = _candidate(sat_id="sat_b", target_id="t1", interval_id="sat_b::t1::0", start_offset_s=20, end_offset_s=30)
        b1 = _candidate(sat_id="sat_a", target_id="t1", interval_id="sat_a::t1::1", start_offset_s=40, end_offset_s=50)
        b2 = _candidate(sat_id="sat_b", target_id="t1", interval_id="sat_b::t1::1", start_offset_s=60, end_offset_s=70)
        c1 = _candidate(sat_id="sat_a", target_id="t2", interval_id="sat_a::t2::0", start_offset_s=80, end_offset_s=90)
        c2 = _candidate(sat_id="sat_b", target_id="t2", interval_id="sat_b::t2::0", start_offset_s=100, end_offset_s=110)

        pairs = [
            _pair(a1, a2, target_id="t1", q_pair=0.9),
            _pair(b1, b2, target_id="t1", q_pair=0.6),
            _pair(c1, c2, target_id="t2", q_pair=0.55),
        ]

        selected, summary = solve_milp(
            [a1, a2, b1, b2, c1, c2],
            pairs,
            [],
            {"t1": target1, "t2": target2},
            {"sat_a": sat_a, "sat_b": sat_b},
            mission,
            config,
        )

        assert selected == [0, 1, 4, 5]
        assert summary.covered_targets == 2
        assert summary.coverage_ratio == pytest.approx(1.0)
        assert summary.best_target_quality_sum == pytest.approx(1.45)
        assert summary.normalized_quality == pytest.approx(0.725)
        assert summary.per_target_best_score == {
            "t1": pytest.approx(0.9),
            "t2": pytest.approx(0.55),
        }


# ---------------------------------------------------------------------------
# Repair tests
# ---------------------------------------------------------------------------

class TestRepair:
    def test_deduplicate_identical_observations(self):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        c1 = _candidate(start_offset_s=0, end_offset_s=10)
        c2 = _candidate(start_offset_s=0, end_offset_s=10)
        c3 = _candidate(start_offset_s=20, end_offset_s=30)
        assert c1 == c2  # frozen dataclass equality

        repaired, log = repair_solution(
            [c1, c2, c3], [], [], {"sat_test": sat}, {"t1": target}, mission, config
        )
        assert len(repaired) == 2
        assert log.pre_repair_obs_count == 3
        assert log.post_repair_obs_count == 2
        assert len(log.removed_observations) == 1
        assert log.removed_observations[0]["reason"] == "duplicate"

    def test_removes_overlap_on_same_satellite(self):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        c1 = _candidate(start_offset_s=0, end_offset_s=10)
        c2 = _candidate(start_offset_s=5, end_offset_s=15)
        # Both on same sat -> overlap

        repaired, log = repair_solution(
            [c1, c2], [], [], {"sat_test": sat}, {"t1": target}, mission, config
        )
        assert len(repaired) == 1
        assert len(log.removed_observations) == 1
        assert log.removed_observations[0]["reason"] == "overlap"

    def test_removes_slew_violation(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        c1 = _candidate(start_offset_s=0, end_offset_s=2)
        c2 = _candidate(start_offset_s=3, end_offset_s=5)
        # Small gap -> slew conflict if angle is large

        monkeypatch.setattr(
            "repair._boresight_angle_at_boundary", lambda a, b, s: 180.0
        )

        repaired, log = repair_solution(
            [c1, c2], [], [], {"sat_test": sat}, {"t1": target}, mission, config
        )
        assert len(repaired) == 1
        assert len(log.removed_observations) == 1
        assert log.removed_observations[0]["reason"] == "slew"

    def test_preserves_coverage_when_possible(self):
        sat = _satellite()
        target1 = _target(target_id="t1")
        target2 = _target(target_id="t2")
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        # t1 pair: (c1, c2)
        c1 = _candidate(target_id="t1", start_offset_s=0, end_offset_s=10)
        c2 = _candidate(target_id="t1", start_offset_s=20, end_offset_s=30)
        # t2 pairs: (c2, c3) and (c4, c5)
        c3 = _candidate(target_id="t2", start_offset_s=40, end_offset_s=50)
        c4 = _candidate(target_id="t2", start_offset_s=25, end_offset_s=35)
        c5 = _candidate(target_id="t2", start_offset_s=60, end_offset_s=70)
        # c2 and c4 overlap on same satellite -> conflict

        pair_t1 = StereoPair(
            target_id="t1",
            candidate_i=c1,
            candidate_j=c2,
            convergence_deg=10.0,
            overlap_fraction=0.9,
            pixel_scale_ratio=1.0,
            valid=True,
            q_geom=1.0,
            q_overlap=1.0,
            q_res=1.0,
            q_pair=1.0,
        )
        pair_t2a = StereoPair(
            target_id="t2",
            candidate_i=c2,
            candidate_j=c3,
            convergence_deg=10.0,
            overlap_fraction=0.9,
            pixel_scale_ratio=1.0,
            valid=True,
            q_geom=0.5,
            q_overlap=0.5,
            q_res=0.5,
            q_pair=0.5,
        )
        pair_t2b = StereoPair(
            target_id="t2",
            candidate_i=c4,
            candidate_j=c5,
            convergence_deg=10.0,
            overlap_fraction=0.9,
            pixel_scale_ratio=1.0,
            valid=True,
            q_geom=0.5,
            q_overlap=0.5,
            q_res=0.5,
            q_pair=0.5,
        )

        repaired, log = repair_solution(
            [c1, c2, c3, c4, c5],
            [pair_t1, pair_t2a, pair_t2b],
            [],
            {"sat_test": sat},
            {"t1": target1, "t2": target2},
            mission,
            config,
        )
        # Removing c4 causes 0 coverage loss (t2 still has pair_t2a via c2,c3)
        # Removing c2 causes t1 to lose coverage
        # Therefore c4 should be removed.
        removed_ids = {r["target_id"] for r in log.removed_observations}
        assert "t1" not in removed_ids
        assert len(repaired) == 4
        assert log.post_repair_covered_targets == 2

    def test_prefers_higher_best_target_quality_when_coverage_ties(self):
        sat_a = _satellite("sat_a")
        sat_b = _satellite("sat_b")
        target = _target("t1")
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        high_a = _candidate(sat_id="sat_a", target_id="t1", interval_id="sat_a::t1::0", start_offset_s=0, end_offset_s=10)
        low_a = _candidate(sat_id="sat_a", target_id="t1", interval_id="sat_a::t1::1", start_offset_s=5, end_offset_s=15)
        high_b = _candidate(sat_id="sat_b", target_id="t1", interval_id="sat_b::t1::0", start_offset_s=20, end_offset_s=30)
        low_b = _candidate(sat_id="sat_b", target_id="t1", interval_id="sat_b::t1::1", start_offset_s=40, end_offset_s=50)

        repaired, log = repair_solution(
            [high_a, low_a, high_b, low_b],
            [
                _pair(high_a, high_b, target_id="t1", q_pair=0.9),
                _pair(low_a, low_b, target_id="t1", q_pair=0.5),
            ],
            [],
            {"sat_a": sat_a, "sat_b": sat_b},
            {"t1": target},
            mission,
            config,
        )

        assert high_a in repaired
        assert low_a not in repaired
        assert log.post_repair_covered_targets == 1
        assert log.post_repair_best_target_quality_sum == pytest.approx(0.9)

    def test_deterministic(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        c1 = _candidate(start_offset_s=0, end_offset_s=2)
        c2 = _candidate(start_offset_s=3, end_offset_s=5)

        monkeypatch.setattr(
            "repair._boresight_angle_at_boundary", lambda a, b, s: 180.0
        )

        r1, log1 = repair_solution(
            [c1, c2], [], [], {"sat_test": sat}, {"t1": target}, mission, config
        )
        r2, log2 = repair_solution(
            [c1, c2], [], [], {"sat_test": sat}, {"t1": target}, mission, config
        )
        assert [c.start for c in r1] == [c.start for c in r2]
        assert log1.removed_observations == log2.removed_observations

    def test_no_repair_when_already_valid(self):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        c1 = _candidate(start_offset_s=0, end_offset_s=2)
        c2 = _candidate(start_offset_s=200, end_offset_s=202)
        # Large gap -> no overlap, no slew issue

        repaired, log = repair_solution(
            [c1, c2], [], [], {"sat_test": sat}, {"t1": target}, mission, config
        )
        assert len(repaired) == 2
        assert len(log.removed_observations) == 0
        assert log.pre_repair_obs_count == log.post_repair_obs_count


# ---------------------------------------------------------------------------
# End-to-end integration test (slow; marked optional)
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_candidate_generation_parallel_path_matches_sequential(self, monkeypatch):
        class FakePool:
            def __init__(self, processes):
                self.processes = processes

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def starmap(self, func, args):
                return [func(*arg) for arg in args]

        def fake_worker(
            sat,
            target_list,
            mission,
            time_step_s,
            sample_stride_s,
            max_candidates_per_interval,
            along_samples,
            across_samples,
            use_target_centered,
            steering_spread_deg,
        ):
            del mission, time_step_s, sample_stride_s, max_candidates_per_interval
            del along_samples, across_samples, use_target_centered, steering_spread_deg
            target = target_list[0]
            cand = _candidate(
                sat_id=sat.id,
                target_id=target.id,
                interval_id=f"{sat.id}::{target.id}::0",
                start_offset_s=0 if sat.id == "sat_a" else 20,
                end_offset_s=10 if sat.id == "sat_a" else 30,
            )
            summary = CandidateSummary()
            summary.record(True, sat.id, target.id, cand.access_interval_id)
            summary.profiling = {
                "satellite_workers": 1,
                "state_batch_build_s": 0.0,
                "access_interval_search_s": 0.0,
                "candidate_sampling_s": 0.0,
                "solar_checks": 0,
                "candidates_emitted": 1,
                "total_s": 0.0,
            }
            return [cand], [], summary

        monkeypatch.setattr(candidate_module, "Pool", FakePool)
        monkeypatch.setattr(candidate_module.os, "cpu_count", lambda: 4)
        monkeypatch.setattr(candidate_module, "_generate_candidates_for_satellite", fake_worker)

        mission = _mission()
        satellites = {"sat_a": _satellite("sat_a"), "sat_b": _satellite("sat_b")}
        targets = {"t1": _target()}

        seq_candidates, seq_rejections, seq_summary = candidate_module.generate_candidates(
            mission,
            satellites,
            targets,
            {"parallel_candidate_generation": False},
        )
        par_candidates, par_rejections, par_summary = candidate_module.generate_candidates(
            mission,
            satellites,
            targets,
            {"parallel_candidate_generation": True},
        )

        assert seq_candidates == par_candidates
        assert seq_rejections == par_rejections
        assert seq_summary.as_dict() == par_summary.as_dict()

    @pytest.mark.timeout(300)
    @pytest.mark.skipif(
        not (REPO_ROOT / "benchmarks" / "stereo_imaging" / "dataset" / "cases" / "test" / "case_0001").exists(),
        reason="case_0001 dataset not present",
    )
    def test_three_runs_identical(self, tmp_path):
        import subprocess

        repo_root = REPO_ROOT
        solver_dir = repo_root / "solvers" / "stereo_imaging" / "time_window_pruned_stereo_milp"
        case_dir = repo_root / "benchmarks" / "stereo_imaging" / "dataset" / "cases" / "test" / "case_0001"
        config_dir = tmp_path / "fast_config"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(
            json.dumps(
                {
                    "runtime": {"mode": "fast"},
                    "debug": False,
                    "time_step_s": 120,
                    "sample_stride_s": 120,
                    "max_candidates_per_interval": 1,
                    "optimization": {"backend": "greedy"},
                }
            ),
            encoding="utf-8",
        )

        statuses: list[dict[str, Any]] = []
        for i in range(3):
            solution_dir = tmp_path / f"det_{i}"
            result = subprocess.run(
                [
                    "./solve.sh",
                    str(case_dir),
                    str(config_dir),
                    str(solution_dir),
                ],
                cwd=solver_dir,
                env=_prepared_solver_env(tmp_path),
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr
            status = json.loads((solution_dir / "status.json").read_text(encoding="utf-8"))
            statuses.append(status)

        s0, s1, s2 = statuses
        assert s0["candidate_counts"] == s1["candidate_counts"] == s2["candidate_counts"]
        assert s0["product_counts"] == s1["product_counts"] == s2["product_counts"]
        # solve_time_s is timing noise; compare everything else
        def _drop_timing(d):
            d = dict(d)
            d.pop("solve_time_s", None)
            return d
        assert _drop_timing(s0["solve_summary"]) == _drop_timing(s1["solve_summary"]) == _drop_timing(s2["solve_summary"])
        assert s0["repair_summary"] == s1["repair_summary"] == s2["repair_summary"]

        actions0 = json.loads((tmp_path / "det_0" / "solution.json").read_text(encoding="utf-8"))["actions"]
        actions1 = json.loads((tmp_path / "det_1" / "solution.json").read_text(encoding="utf-8"))["actions"]
        actions2 = json.loads((tmp_path / "det_2" / "solution.json").read_text(encoding="utf-8"))["actions"]
        assert actions0 == actions1 == actions2


class TestEndToEnd:
    @pytest.mark.skipif(
        not (REPO_ROOT / "benchmarks" / "stereo_imaging" / "dataset" / "cases" / "test" / "case_0001").exists(),
        reason="case_0001 dataset not present",
    )
    def test_smoke_case_0001(self, tmp_path):
        import subprocess

        repo_root = REPO_ROOT
        solver_dir = repo_root / "solvers" / "stereo_imaging" / "time_window_pruned_stereo_milp"
        case_dir = repo_root / "benchmarks" / "stereo_imaging" / "dataset" / "cases" / "test" / "case_0001"
        config_dir = tmp_path / "fast_config"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(
            json.dumps(
                {
                    "runtime": {"mode": "fast"},
                    "debug": False,
                    "time_step_s": 120,
                    "sample_stride_s": 120,
                    "max_candidates_per_interval": 1,
                    "optimization": {"backend": "greedy"},
                }
            ),
            encoding="utf-8",
        )

        solution_dir = tmp_path / "solution"
        result = subprocess.run(
            [
                "./solve.sh",
                str(case_dir),
                str(config_dir),
                str(solution_dir),
            ],
            cwd=solver_dir,
            env=_prepared_solver_env(tmp_path),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

        solution_path = solution_dir / "solution.json"
        status_path = solution_dir / "status.json"
        assert solution_path.exists()
        assert status_path.exists()

        solution = json.loads(solution_path.read_text(encoding="utf-8"))
        assert "actions" in solution
        for action in solution["actions"]:
            assert action["type"] == "observation"
            assert "satellite_id" in action
            assert "target_id" in action
            assert "start_time" in action
            assert "end_time" in action
            assert action["start_time"].endswith("Z")
            assert action["end_time"].endswith("Z")

        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["status"] == "solved"
        assert status["solver_version"] == "time_window_pruned_stereo_milp"
        assert "repair_summary" in status
        assert status["profiling"]["runtime_mode"] == "fast"
        assert status["solve_summary"]["backend_used"] == "greedy"
        assert "candidate_generation" in status["profiling"]
        assert "product_enumeration" in status["profiling"]
        assert "solve" in status["profiling"]
