"""Focused tests for stereo MILP Phase-2 product enumeration and scoring."""

from __future__ import annotations

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
