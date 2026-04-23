"""Focused tests for stereo MILP Phase-2 product enumeration and scoring."""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SOLVER_DIR = REPO_ROOT / "solvers" / "stereo_imaging" / "time_window_pruned_stereo_milp" / "src"
sys.path.insert(0, str(SOLVER_DIR))

from models import (  # noqa: E402
    CandidateObservation,
    Mission,
    QualityModel,
    Satellite,
    StereoPair,
    Target,
    ValidityThresholds,
)
from products import (  # noqa: E402
    _pair_geom_quality,
    _precompute_candidate_geometry,
    _tri_bonus_R,
    evaluate_pair,
    evaluate_tri,
    enumerate_products,
)
from milp_model import (  # noqa: E402
    build_conflict_graph,
    build_milp,
    solve_greedy_fallback,
    solve_milp,
)
from repair import repair_solution  # noqa: E402
from pruning import (  # noqa: E402
    _CandidateScore,
    _rank_key,
    _score_candidates,
    cluster_candidates_by_gap,
    compute_cluster_gap_s,
    compute_lambda_lb,
    prune_candidates,
)


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
        allow_cross_satellite_stereo=False,
        allow_cross_date_stereo=False,
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

        def fake_precompute(cand, sat, target, step):
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

        def fake_precompute(cand, sat, target, step):
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

        def fake_precompute(cand, sat, target, step):
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
        def fake_precompute2(cand, sat, target, step):
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

        def fake_precompute(cand, sat, target, step):
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

        def fake_precompute(cand, sat, target, step):
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

        def fake_precompute(cand, sat, target, step):
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

        def fake_precompute(cand, sat, target, step):
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
    def test_only_same_interval_produces_pairs(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {"overlap_grid_angles": 4, "overlap_grid_radii": 1}

        def fake_precompute(cand, sat, target, step):
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
        pairs, tris, summary = enumerate_products([c1, c2, c3], {"sat_test": sat}, {"t1": target}, mission, config)
        assert len(pairs) == 1  # only (c1,c2)
        assert pairs[0].access_interval_id == "i1"
        assert len(tris) == 0


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

        def fake_precompute(cand, sat, target, step):
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
        scores = _score_candidates(
            [c1, c2, c3], pairs, tris, target_totals,
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

        def fake_precompute(cand, sat, target, step):
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
        scores = _score_candidates(
            cluster, pairs, tris, target_totals,
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

        def fake_precompute(cand, sat, target, step):
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

        def fake_precompute(cand, sat, target, step):
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

        def fake_precompute(cand, sat, target, step):
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

        def fake_precompute(cand, sat, target, step):
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

        def fake_precompute(cand, sat, target, step):
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
# MILP / conflict / greedy fallback tests
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
            "optimization": {"coverage_weight": 1000.0},
        }
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sat, target, step):
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
        # Tri links: 3 per tri = 3
        assert len(model.tri_link_constraints) == 3
        # Coverage constraint: 1
        assert len(model.target_coverage_constraints) == 1

    def test_coverage_weight_in_objective(self):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {"optimization": {"coverage_weight": 500.0}}
        cands = [_candidate(start_offset_s=0)]
        model = build_milp(cands, [], [], {"t1": target}, {"sat_test": sat}, mission, config)
        assert model.coverage_weight == 500.0


class TestGreedyFallback:
    def test_selects_single_valid_pair(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
            "optimization": {"greedy_coverage_augment": False},
        }
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sat, target, step):
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
        selected, obj, stats = solve_greedy_fallback(model, config)

        assert len(selected) == 2
        assert obj > 0

    def test_prefers_higher_quality_pair(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
            "optimization": {"greedy_coverage_augment": False},
        }
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sat, target, step):
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
        selected, obj, stats = solve_greedy_fallback(model, config)

        # Should select at least one pair (2 observations)
        assert len(selected) >= 2

    def test_deterministic(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
            "optimization": {"greedy_coverage_augment": False},
        }
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sat, target, step):
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
        r1, _, _ = solve_greedy_fallback(model, config)
        r2, _, _ = solve_greedy_fallback(model, config)
        assert r1 == r2


class TestSolveMILP:
    def test_fallback_when_no_backend(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
            "optimization": {"backend": "ortools", "greedy_coverage_augment": False},
        }
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sat, target, step):
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

        assert summary.backend_used == "greedy_fallback"
        assert summary.fallback_reason is not None
        assert "ortools" in summary.fallback_reason
        assert len(selected) == 2

    def test_greedy_backend_explicit(self, monkeypatch):
        sat = _satellite()
        target = _target()
        mission = _mission()
        config = {
            "overlap_grid_angles": 4,
            "overlap_grid_radii": 1,
            "optimization": {"backend": "greedy", "greedy_coverage_augment": False},
        }
        base = datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)

        def fake_precompute(cand, sat, target, step):
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

        assert summary.backend_used == "greedy_fallback"
        # When backend is explicitly "greedy", fallback_reason should be None (not a fallback)
        assert summary.fallback_reason is None
        assert len(selected) == 2
        assert summary.selected_pairs == 1
        assert summary.covered_targets == 1


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
            sat_id="sat_test",
            target_id="t1",
            access_interval_id="i1",
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
            sat_id="sat_test",
            target_id="t2",
            access_interval_id="i1",
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
            sat_id="sat_test",
            target_id="t2",
            access_interval_id="i1",
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

class TestEndToEnd:
    @pytest.mark.skipif(
        not (Path(__file__).resolve().parents[2] / "benchmarks" / "stereo_imaging" / "dataset" / "cases" / "test" / "case_0001").exists(),
        reason="case_0001 dataset not present",
    )
    def test_smoke_case_0001(self, tmp_path):
        import subprocess

        repo_root = Path(__file__).resolve().parents[2]
        solver_dir = repo_root / "solvers" / "stereo_imaging" / "time_window_pruned_stereo_milp"
        case_dir = repo_root / "benchmarks" / "stereo_imaging" / "dataset" / "cases" / "test" / "case_0001"
        solution_dir = tmp_path / "solution"
        config_dir = solver_dir / "config.yaml"

        result = subprocess.run(
            [
                "./solve.sh",
                str(case_dir),
                str(config_dir),
                str(solution_dir),
            ],
            cwd=solver_dir,
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
        assert status["status"] == "phase_5_solved"
        assert status["phase"] == 5
        assert "repair_summary" in status
