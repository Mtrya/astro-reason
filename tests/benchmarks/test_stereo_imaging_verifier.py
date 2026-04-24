"""Focused tests for the stereo_imaging verifier."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import yaml

from benchmarks.stereo_imaging.verifier.engine import (
    _angle_between_deg,
    _boresight_ground_intercept_ecef_m,
    _boresight_unit_vector,
    _combined_off_nadir_deg,
    _line_of_sight_clear,
    _min_slew_time_s,
    _observation_window_key,
    _off_nadir_deg,
    _pair_geom_quality,
    _point_distance_to_polyline_2d,
    _product_time_separation_s,
    _ray_ellipsoid_intersection_m,
    _satellite_local_axes,
    _stereo_mc_rng,
    _stereo_pair_mode,
    _tri_bonus_R,
    _tri_quality_from_valid_pairs,
    _WGS84_A_M,
    _evaluate_stereo_pair,
    verify_solution,
)
from benchmarks.stereo_imaging.verifier.io import load_case, load_solution_actions
from benchmarks.stereo_imaging.verifier.models import (
    DerivedObservation,
    Mission,
    ObservationAction,
    SatelliteDef,
    TargetDef,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "stereo_imaging"
GOLDEN_FIXTURE_NAMES = (
    "empty_solution",
    "time_overlap_invalid",
    "slew_too_fast_invalid",
)

# Pleiades-1A TLE from case_0001 — a real LEO EO satellite.
_PLEIADES_TLE_LINE1 = (
    "1 38012U 11076F   26096.23539690  .00000494  00000+0  11617-3 0  9994"
)
_PLEIADES_TLE_LINE2 = (
    "2 38012  98.2002 172.2949 0001342  74.1943  10.7084 14.58565955761501"
)


# ---------------------------------------------------------------------------
# Synthetic case helpers
# ---------------------------------------------------------------------------


def _base_mission_dict(
    *,
    horizon_start: str = "2026-06-18T00:00:00Z",
    horizon_end: str = "2026-06-18T06:00:00Z",
) -> dict:
    return {
        "mission": {
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
            "allow_cross_satellite_stereo": False,
            "max_stereo_pair_separation_s": 7200.0,
            "validity_thresholds": {
                "min_overlap_fraction": 0.8,
                "min_convergence_deg": 5.0,
                "max_convergence_deg": 45.0,
                "max_pixel_scale_ratio": 1.5,
                "min_solar_elevation_deg": 10.0,
                "near_nadir_anchor_max_off_nadir_deg": 10.0,
            },
            "quality_model": {
                "pair_weights": {
                    "geometry": 0.5,
                    "overlap": 0.35,
                    "resolution": 0.15,
                },
                "tri_stereo_bonus_by_scene": {
                    "urban_structured": 0.12,
                    "rugged": 0.10,
                    "vegetated": 0.08,
                    "open": 0.05,
                },
            },
        },
    }


def _base_satellite_dict(
    *,
    sat_id: str = "sat_test",
    tle1: str = _PLEIADES_TLE_LINE1,
    tle2: str = _PLEIADES_TLE_LINE2,
) -> dict:
    return {
        "id": sat_id,
        "norad_catalog_id": 38012,
        "tle_line1": tle1,
        "tle_line2": tle2,
        "pixel_ifov_deg": 4.0e-05,
        "cross_track_pixels": 20000,
        "max_off_nadir_deg": 30.0,
        "max_slew_velocity_deg_per_s": 1.95,
        "max_slew_acceleration_deg_per_s2": 0.95,
        "settling_time_s": 1.9,
        "min_obs_duration_s": 2.0,
        "max_obs_duration_s": 60.0,
    }


def _base_target_dict(
    *,
    target_id: str = "t1",
    lat: float = 0.0,
    lon: float = 30.0,
) -> dict:
    return {
        "id": target_id,
        "latitude_deg": lat,
        "longitude_deg": lon,
        "aoi_radius_m": 5000.0,
        "elevation_ref_m": 0.0,
        "scene_type": "urban_structured",
    }


def _make_sat_def(
    *,
    omega: float = 1.95,
    alpha: float = 0.95,
    settling: float = 1.9,
    min_dur: float = 2.0,
    max_dur: float = 60.0,
    max_off_nadir: float = 30.0,
) -> SatelliteDef:
    return SatelliteDef(
        sat_id="sat_test",
        norad_catalog_id=38012,
        tle_line1=_PLEIADES_TLE_LINE1,
        tle_line2=_PLEIADES_TLE_LINE2,
        pixel_ifov_deg=4.0e-5,
        cross_track_pixels=20000,
        max_off_nadir_deg=max_off_nadir,
        max_slew_velocity_deg_per_s=omega,
        max_slew_acceleration_deg_per_s2=alpha,
        settling_time_s=settling,
        min_obs_duration_s=min_dur,
        max_obs_duration_s=max_dur,
    )


def _write_yaml(path: Path, payload: object) -> None:
    path.write_text(yaml.dump(payload, default_flow_style=False), encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_case(
    case_dir: Path,
    *,
    mission: dict | None = None,
    satellites: list[dict] | None = None,
    targets: list[dict] | None = None,
) -> Path:
    case_dir.mkdir(parents=True, exist_ok=True)
    _write_yaml(case_dir / "mission.yaml", mission or _base_mission_dict())
    _write_yaml(case_dir / "satellites.yaml", satellites or [_base_satellite_dict()])
    _write_yaml(case_dir / "targets.yaml", targets or [_base_target_dict()])
    return case_dir


def _write_solution(path: Path, actions: list[dict]) -> Path:
    _write_json(path, {"actions": actions})
    return path


def _obs_action(
    *,
    sat: str = "sat_test",
    target: str = "t1",
    start: str = "2026-06-18T01:00:00Z",
    end: str = "2026-06-18T01:00:05Z",
    along: float = 0.0,
    across: float = 0.0,
) -> dict:
    return {
        "type": "observation",
        "satellite_id": sat,
        "target_id": target,
        "start_time": start,
        "end_time": end,
        "off_nadir_along_deg": along,
        "off_nadir_across_deg": across,
    }


def _mission_model(
    *,
    allow_cross_satellite: bool = False,
    max_pair_separation_s: float = 7200.0,
) -> Mission:
    return Mission(
        horizon_start=datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC),
        horizon_end=datetime(2026, 6, 19, 6, 0, 0, tzinfo=UTC),
        allow_cross_satellite_stereo=allow_cross_satellite,
        max_stereo_pair_separation_s=max_pair_separation_s,
        min_overlap_fraction=0.8,
        min_convergence_deg=5.0,
        max_convergence_deg=45.0,
        max_pixel_scale_ratio=1.5,
        min_solar_elevation_deg=10.0,
        near_nadir_anchor_max_off_nadir_deg=10.0,
        pair_weights={"geometry": 0.5, "overlap": 0.35, "resolution": 0.15},
        tri_stereo_bonus_by_scene={
            "urban_structured": 0.12,
            "rugged": 0.10,
            "vegetated": 0.08,
            "open": 0.05,
        },
    )


def _derived_obs(
    *,
    sat: str = "sat_test",
    target: str = "t1",
    action_index: int = 0,
    access_interval_id: str = "access_0",
    midpoint: str = "2026-06-18T01:00:02Z",
    scale_m: float = 0.5,
    slant_m: float = 700000.0,
    off_nadir: float = 0.0,
) -> DerivedObservation:
    return DerivedObservation(
        satellite_id=sat,
        target_id=target,
        action_index=action_index,
        start_time="2026-06-18T01:00:00Z",
        end_time="2026-06-18T01:00:05Z",
        midpoint_time=midpoint,
        sat_position_ecef_m=[0.0, 0.0, 0.0],
        sat_velocity_ecef_mps=[0.0, 0.0, 0.0],
        boresight_off_nadir_deg=off_nadir,
        boresight_azimuth_deg=0.0,
        solar_elevation_deg=45.0,
        solar_azimuth_deg=180.0,
        effective_pixel_scale_m=scale_m,
        access_interval_id=access_interval_id,
        slant_range_m=slant_m,
    )


# ===================================================================
# Group 1: Geometry helpers
# ===================================================================


class TestAngleBetweenDeg:
    @pytest.mark.parametrize(
        "a, b, expected",
        [
            ([1, 0, 0], [2, 0, 0], 0.0),
            ([1, 0, 0], [-1, 0, 0], 180.0),
            ([1, 0, 0], [0, 1, 0], 90.0),
            ([0, 0, 0], [1, 0, 0], 0.0),
        ],
        ids=["parallel", "antiparallel", "orthogonal", "zero-norm"],
    )
    def test_basic(self, a, b, expected):
        result = _angle_between_deg(np.array(a, dtype=float), np.array(b, dtype=float))
        assert result == pytest.approx(expected, abs=1e-6)


class TestRayEllipsoidIntersection:
    def test_downward_from_altitude_hits_surface(self):
        origin = np.array([7e6, 0.0, 0.0])
        direction = np.array([-1.0, 0.0, 0.0])
        t = _ray_ellipsoid_intersection_m(origin, direction)
        assert t is not None
        assert t == pytest.approx(7e6 - _WGS84_A_M, rel=1e-6)

    def test_tangent_direction_misses(self):
        origin = np.array([7e6, 0.0, 0.0])
        direction = np.array([0.0, 1.0, 0.0])
        assert _ray_ellipsoid_intersection_m(origin, direction) is None

    def test_origin_at_center_returns_forward_hit(self):
        origin = np.array([0.0, 0.0, 0.0])
        direction = np.array([1.0, 0.0, 0.0])
        t = _ray_ellipsoid_intersection_m(origin, direction)
        assert t is not None
        assert t == pytest.approx(_WGS84_A_M, rel=1e-6)


class TestLineOfSightClear:
    def test_visible_equatorial_target(self):
        sat = np.array([7e6, 0.0, 0.0])
        target = np.array([_WGS84_A_M, 0.0, 0.0])
        assert _line_of_sight_clear(sat, target) is True

    def test_far_side_target_blocked(self):
        sat = np.array([7e6, 0.0, 0.0])
        target = np.array([-_WGS84_A_M, 0.0, 0.0])
        assert _line_of_sight_clear(sat, target) is False


class TestOffNadirDeg:
    def test_nadir_is_zero(self):
        sat = np.array([7e6, 0.0, 0.0])
        target = np.array([_WGS84_A_M, 0.0, 0.0])
        assert _off_nadir_deg(sat, target) == pytest.approx(0.0, abs=1e-6)

    def test_45_degrees(self):
        sat = np.array([7e6, 0.0, 0.0])
        d = 1000.0
        target = sat + d * np.array([-1 / math.sqrt(2), 1 / math.sqrt(2), 0.0])
        assert _off_nadir_deg(sat, target) == pytest.approx(45.0, abs=1e-6)


class TestSatelliteLocalAxes:
    def test_equatorial_prograde(self):
        pos = np.array([7e6, 0.0, 0.0])
        vel = np.array([0.0, 7500.0, 0.0])
        along, across, nadir = _satellite_local_axes(pos, vel)
        np.testing.assert_allclose(along, [0, 1, 0], atol=1e-10)
        np.testing.assert_allclose(across, [0, 0, 1], atol=1e-10)
        np.testing.assert_allclose(nadir, [-1, 0, 0], atol=1e-10)

    def test_axes_are_orthonormal(self):
        pos = np.array([7e6, 0.0, 0.0])
        vel = np.array([0.0, 7500.0, 0.0])
        along, across, nadir = _satellite_local_axes(pos, vel)
        assert np.dot(along, across) == pytest.approx(0.0, abs=1e-10)
        assert np.dot(along, nadir) == pytest.approx(0.0, abs=1e-10)
        assert np.dot(across, nadir) == pytest.approx(0.0, abs=1e-10)
        assert np.linalg.norm(along) == pytest.approx(1.0, abs=1e-10)
        assert np.linalg.norm(across) == pytest.approx(1.0, abs=1e-10)
        assert np.linalg.norm(nadir) == pytest.approx(1.0, abs=1e-10)


class TestBoresightUnitVector:
    def test_zero_steering_returns_nadir(self):
        pos = np.array([7e6, 0.0, 0.0])
        vel = np.array([0.0, 7500.0, 0.0])
        b = _boresight_unit_vector(pos, vel, 0.0, 0.0)
        np.testing.assert_allclose(b, [-1, 0, 0], atol=1e-10)

    def test_nonzero_steering_tilts_along_track(self):
        pos = np.array([7e6, 0.0, 0.0])
        vel = np.array([0.0, 7500.0, 0.0])
        b = _boresight_unit_vector(pos, vel, 20.0, 0.0)
        assert b[1] > 0.0, "should tilt toward along-track (y)"
        assert abs(b[2]) < 1e-10, "no across-track component"
        assert np.linalg.norm(b) == pytest.approx(1.0, abs=1e-10)


class TestBoresightGroundIntercept:
    def test_nadir_hits_equator(self):
        pos = np.array([7e6, 0.0, 0.0])
        vel = np.array([0.0, 7500.0, 0.0])
        gp = _boresight_ground_intercept_ecef_m(pos, vel, 0.0, 0.0)
        assert gp is not None
        assert gp[0] == pytest.approx(_WGS84_A_M, rel=1e-6)
        assert abs(gp[1]) < 1.0
        assert abs(gp[2]) < 1.0

    def test_extreme_steering_misses(self):
        pos = np.array([7e6, 0.0, 0.0])
        vel = np.array([0.0, 7500.0, 0.0])
        gp = _boresight_ground_intercept_ecef_m(pos, vel, 0.0, 89.5)
        assert gp is None


class TestCombinedOffNadir:
    def test_zero(self):
        assert _combined_off_nadir_deg(0.0, 0.0) == pytest.approx(0.0)

    def test_axis_matches_single_component(self):
        assert _combined_off_nadir_deg(22.5, 0.0) == pytest.approx(22.5)
        assert _combined_off_nadir_deg(0.0, 18.0) == pytest.approx(18.0)

    def test_tangent_model_not_euclidean_hypot(self):
        # atan(sqrt(tan^2 a + tan^2 b)) — for (3°,4°) this is ~4.994°, not 5° from hypot(3,4).
        assert _combined_off_nadir_deg(3.0, 4.0) == pytest.approx(4.994169393106, abs=1e-9)
        # Equal split on a 30° hypot circle: geometric tilt ~28.76°, not 30°.
        s = 30.0 / math.sqrt(2.0)
        assert _combined_off_nadir_deg(s, s) == pytest.approx(28.762922637351, abs=1e-9)


class TestPointDistanceToPolyline:
    def test_point_on_segment(self):
        poly = [(0.0, 0.0), (10.0, 0.0)]
        assert _point_distance_to_polyline_2d((5.0, 0.0), poly) == pytest.approx(0.0)

    def test_perpendicular_offset(self):
        poly = [(0.0, 0.0), (10.0, 0.0)]
        assert _point_distance_to_polyline_2d((5.0, 3.0), poly) == pytest.approx(3.0)

    def test_beyond_endpoint(self):
        poly = [(0.0, 0.0), (10.0, 0.0)]
        assert _point_distance_to_polyline_2d((15.0, 0.0), poly) == pytest.approx(5.0)

    def test_empty_polyline(self):
        assert _point_distance_to_polyline_2d((0.0, 0.0), []) == float("inf")

    def test_single_point_polyline(self):
        assert _point_distance_to_polyline_2d((3.0, 4.0), [(0.0, 0.0)]) == float("inf")


# ===================================================================
# Group 2: Scoring helpers
# ===================================================================


class TestPairGeomQuality:
    @pytest.mark.parametrize(
        "gamma, scene, expected",
        [
            (13.0, "urban_structured", 1.0),
            (8.0, "urban_structured", 1.0),
            (18.0, "urban_structured", 1.0),
            (3.0, "urban_structured", 0.5),
            (28.0, "urban_structured", 0.0),
            (12.0, "rugged", 1.0),
            (5.0, "rugged", 0.5),
        ],
        ids=[
            "mid-band",
            "low-edge",
            "high-edge",
            "below-band",
            "far-above-band",
            "rugged-mid",
            "rugged-below",
        ],
    )
    def test_quality(self, gamma, scene, expected):
        assert _pair_geom_quality(gamma, scene) == pytest.approx(expected, abs=1e-6)


class TestTriBonusR:
    @pytest.mark.parametrize(
        "pair_ok, anchor, expected",
        [
            ([False, False, False], False, 0.0),
            ([True, True, False], True, 1.0),
            ([True, False, False], True, 0.4),
            ([True, True, True], False, 0.6),
            ([False, False, False], True, 0.4),
        ],
        ids=[
            "none",
            "two-pairs-plus-anchor",
            "one-pair-plus-anchor",
            "three-pairs-no-anchor",
            "no-pairs-anchor-only",
        ],
    )
    def test_bonus(self, pair_ok, anchor, expected):
        assert _tri_bonus_R(pair_ok, anchor) == pytest.approx(expected)


class TestTriQualityFromValidPairs:
    def test_no_valid_pairs(self):
        q = _tri_quality_from_valid_pairs(
            [False, False, False], [0.5, 0.5, 0.5], beta=0.1, tri_bonus_R=1.0
        )
        assert q == 0.0

    def test_single_valid_pair(self):
        q = _tri_quality_from_valid_pairs(
            [True, False, False], [0.8, 0.5, 0.5], beta=0.1, tri_bonus_R=1.0
        )
        assert q == pytest.approx(0.9)

    def test_clamped_at_one(self):
        q = _tri_quality_from_valid_pairs(
            [True, True, True], [0.95, 0.9, 0.85], beta=0.12, tri_bonus_R=1.0
        )
        assert q == pytest.approx(1.0)


class TestMinSlewTime:
    def test_zero_angle(self):
        sd = _make_sat_def()
        assert _min_slew_time_s(0.0, sd) == 0.0

    def test_triangular_profile(self):
        sd = _make_sat_def(omega=1.95, alpha=0.95)
        d_tri = 1.95**2 / 0.95
        assert 2.0 < d_tri, "sanity: threshold is above test angle"
        t = _min_slew_time_s(2.0, sd)
        assert t == pytest.approx(2.0 * math.sqrt(2.0 / 0.95), rel=1e-6)

    def test_trapezoidal_profile(self):
        sd = _make_sat_def(omega=1.95, alpha=0.95)
        t = _min_slew_time_s(10.0, sd)
        assert t == pytest.approx(10.0 / 1.95 + 1.95 / 0.95, rel=1e-6)

    def test_zero_omega_returns_inf(self):
        sd = _make_sat_def(omega=0.0)
        assert _min_slew_time_s(5.0, sd) == float("inf")


# ===================================================================
# Group 3: IO and schema validation
# ===================================================================


class TestIOLoadCase:
    def test_missing_mission_yaml(self, tmp_path):
        case_dir = tmp_path / "case"
        case_dir.mkdir()
        _write_yaml(case_dir / "satellites.yaml", [_base_satellite_dict()])
        _write_yaml(case_dir / "targets.yaml", [_base_target_dict()])
        with pytest.raises(FileNotFoundError, match="mission.yaml"):
            load_case(case_dir)

    def test_missing_satellites_yaml(self, tmp_path):
        case_dir = tmp_path / "case"
        case_dir.mkdir()
        _write_yaml(case_dir / "mission.yaml", _base_mission_dict())
        _write_yaml(case_dir / "targets.yaml", [_base_target_dict()])
        with pytest.raises(FileNotFoundError, match="satellites.yaml"):
            load_case(case_dir)

    def test_missing_targets_yaml(self, tmp_path):
        case_dir = tmp_path / "case"
        case_dir.mkdir()
        _write_yaml(case_dir / "mission.yaml", _base_mission_dict())
        _write_yaml(case_dir / "satellites.yaml", [_base_satellite_dict()])
        with pytest.raises(FileNotFoundError, match="targets.yaml"):
            load_case(case_dir)

    def test_valid_case_loads(self, tmp_path):
        case_dir = _write_case(tmp_path / "case")
        mission, sats, targets = load_case(case_dir)
        assert "sat_test" in sats
        assert "t1" in targets
        assert mission.min_overlap_fraction == pytest.approx(0.8)

    def test_rejects_nonpositive_stereo_pair_separation(self, tmp_path):
        mission = _base_mission_dict()
        mission["mission"]["max_stereo_pair_separation_s"] = 0.0
        case_dir = _write_case(tmp_path / "case", mission=mission)

        with pytest.raises(ValueError, match="max_stereo_pair_separation_s"):
            load_case(case_dir)


class TestParseIsoUtcStrict:
    def test_mission_rejects_naive_timestamp(self, tmp_path):
        case_dir = tmp_path / "case"
        case_dir.mkdir()
        m = _base_mission_dict()
        m["mission"]["horizon_start"] = "2026-06-18T00:00:00"
        _write_yaml(case_dir / "mission.yaml", m)
        _write_yaml(case_dir / "satellites.yaml", [_base_satellite_dict()])
        _write_yaml(case_dir / "targets.yaml", [_base_target_dict()])
        with pytest.raises(ValueError, match="naive|timezone|offset"):
            load_case(case_dir)

    def test_solution_rejects_naive_timestamp(self, tmp_path):
        case_dir = _write_case(tmp_path / "case")
        sol = _write_solution(
            tmp_path / "sol.json",
            [
                {
                    "type": "observation",
                    "satellite_id": "sat_test",
                    "target_id": "t1",
                    "start_time": "2026-06-18T01:00:00",
                    "end_time": "2026-06-18T01:00:05Z",
                    "off_nadir_along_deg": 0.0,
                    "off_nadir_across_deg": 0.0,
                },
            ],
        )
        with pytest.raises(ValueError, match="naive|timezone|offset"):
            load_solution_actions(sol, "case")


class TestStereoMcRng:
    def test_pair_seed_invariant_to_observation_order(self):
        t0 = datetime(2026, 6, 18, 1, 0, 0, tzinfo=UTC)
        t1 = datetime(2026, 6, 18, 1, 0, 10, tzinfo=UTC)
        t2 = datetime(2026, 6, 18, 1, 0, 20, tzinfo=UTC)
        t3 = datetime(2026, 6, 18, 1, 0, 30, tzinfo=UTC)
        a = ObservationAction("sat", "t1", t0, t1, 0.0, 0.0)
        b = ObservationAction("sat", "t1", t2, t3, 0.0, 0.0)
        w1 = tuple(sorted((_observation_window_key(a), _observation_window_key(b))))
        w2 = tuple(sorted((_observation_window_key(b), _observation_window_key(a))))
        assert w1 == w2
        r1 = _stereo_mc_rng(
            "case_x",
            "sat",
            "t1",
            "acc1",
            window_keys=w1,
            n_samples=100,
            role="pair_overlap",
        )
        r2 = _stereo_mc_rng(
            "case_x",
            "sat",
            "t1",
            "acc1",
            window_keys=w2,
            n_samples=100,
            role="pair_overlap",
        )
        assert [r1.random() for _ in range(20)] == [r2.random() for _ in range(20)]

    def test_role_and_n_samples_change_stream(self):
        w_pair = tuple(
            sorted(
                (
                    ("2026-06-18T01:00:00Z", "2026-06-18T01:00:10Z"),
                    ("2026-06-18T01:00:20Z", "2026-06-18T01:00:30Z"),
                )
            )
        )
        r_a = _stereo_mc_rng(
            "c", "s", "t", "a", window_keys=w_pair, n_samples=100, role="pair_overlap"
        )
        r_b = _stereo_mc_rng(
            "c", "s", "t", "a", window_keys=w_pair, n_samples=80, role="pair_overlap"
        )
        assert r_a.random() != r_b.random()


class TestStereoPairPolicy:
    def test_same_satellite_same_access_allowed_without_cross_satellite(self):
        mission = _mission_model(allow_cross_satellite=False)
        a0 = ObservationAction(
            "sat_a",
            "t1",
            datetime(2026, 6, 18, 1, 0, 0, tzinfo=UTC),
            datetime(2026, 6, 18, 1, 0, 5, tzinfo=UTC),
            0.0,
            0.0,
        )
        a1 = ObservationAction(
            "sat_a",
            "t1",
            datetime(2026, 6, 18, 1, 1, 0, tzinfo=UTC),
            datetime(2026, 6, 18, 1, 1, 5, tzinfo=UTC),
            0.0,
            0.0,
        )
        d0 = _derived_obs(sat="sat_a", action_index=0, access_interval_id="pass_0")
        d1 = _derived_obs(sat="sat_a", action_index=1, access_interval_id="pass_0")

        assert _stereo_pair_mode(mission, a0, a1, d0, d1) == "same_satellite_same_pass"

    def test_same_satellite_different_access_rejected(self):
        mission = _mission_model(allow_cross_satellite=True)
        a0 = ObservationAction(
            "sat_a",
            "t1",
            datetime(2026, 6, 18, 1, 0, 0, tzinfo=UTC),
            datetime(2026, 6, 18, 1, 0, 5, tzinfo=UTC),
            0.0,
            0.0,
        )
        a1 = ObservationAction(
            "sat_a",
            "t1",
            datetime(2026, 6, 18, 2, 0, 0, tzinfo=UTC),
            datetime(2026, 6, 18, 2, 0, 5, tzinfo=UTC),
            0.0,
            0.0,
        )
        d0 = _derived_obs(sat="sat_a", action_index=0, access_interval_id="pass_0")
        d1 = _derived_obs(sat="sat_a", action_index=1, access_interval_id="pass_1")

        assert _stereo_pair_mode(mission, a0, a1, d0, d1) is None

    def test_cross_satellite_requires_enablement(self):
        mission = _mission_model(allow_cross_satellite=False)
        a0 = ObservationAction(
            "sat_a",
            "t1",
            datetime(2026, 6, 18, 1, 0, 0, tzinfo=UTC),
            datetime(2026, 6, 18, 1, 0, 5, tzinfo=UTC),
            0.0,
            0.0,
        )
        a1 = ObservationAction(
            "sat_b",
            "t1",
            datetime(2026, 6, 18, 1, 1, 0, tzinfo=UTC),
            datetime(2026, 6, 18, 1, 1, 5, tzinfo=UTC),
            0.0,
            0.0,
        )
        d0 = _derived_obs(sat="sat_a", action_index=0, access_interval_id="sat_a_pass_0")
        d1 = _derived_obs(sat="sat_b", action_index=1, access_interval_id="sat_b_pass_0")

        assert _stereo_pair_mode(mission, a0, a1, d0, d1) is None

    def test_cross_midnight_pair_uses_temporal_bound_not_date_boundary(self):
        mission = _mission_model(allow_cross_satellite=True, max_pair_separation_s=180.0)
        a0 = ObservationAction(
            "sat_a",
            "t1",
            datetime(2026, 6, 18, 23, 58, 55, tzinfo=UTC),
            datetime(2026, 6, 18, 23, 59, 5, tzinfo=UTC),
            0.0,
            0.0,
        )
        a1 = ObservationAction(
            "sat_b",
            "t1",
            datetime(2026, 6, 19, 0, 0, 55, tzinfo=UTC),
            datetime(2026, 6, 19, 0, 1, 5, tzinfo=UTC),
            0.0,
            0.0,
        )
        d0 = _derived_obs(sat="sat_a", action_index=0, access_interval_id="sat_a_pass_0")
        d1 = _derived_obs(sat="sat_b", action_index=1, access_interval_id="sat_b_pass_0")

        assert _product_time_separation_s([a0, a1]) == pytest.approx(120.0)
        assert _stereo_pair_mode(mission, a0, a1, d0, d1) == "cross_satellite"

    def test_pair_over_temporal_bound_rejected(self):
        mission = _mission_model(allow_cross_satellite=True, max_pair_separation_s=60.0)
        a0 = ObservationAction(
            "sat_a",
            "t1",
            datetime(2026, 6, 18, 23, 58, 55, tzinfo=UTC),
            datetime(2026, 6, 18, 23, 59, 5, tzinfo=UTC),
            0.0,
            0.0,
        )
        a1 = ObservationAction(
            "sat_b",
            "t1",
            datetime(2026, 6, 19, 0, 0, 55, tzinfo=UTC),
            datetime(2026, 6, 19, 0, 1, 5, tzinfo=UTC),
            0.0,
            0.0,
        )
        d0 = _derived_obs(sat="sat_a", action_index=0, access_interval_id="sat_a_pass_0")
        d1 = _derived_obs(sat="sat_b", action_index=1, access_interval_id="sat_b_pass_0")

        assert _stereo_pair_mode(mission, a0, a1, d0, d1) is None


class TestEvaluateStereoPair:
    def test_mixed_satellite_pair_uses_each_satellite_geometry(self, monkeypatch):
        target_pos = np.array([_WGS84_A_M, 0.0, 0.0])
        baseline_angle = math.radians(10.0)
        sat_a_pos = target_pos + np.array([700000.0, 0.0, 0.0])
        sat_b_pos = target_pos + 700000.0 * np.array(
            [math.cos(baseline_angle), math.sin(baseline_angle), 0.0]
        )

        class FakeSat:
            def __init__(self, name: str):
                self.name = name

        def fake_state(sat, _dt):
            if sat.name == "sat_a":
                return sat_a_pos, np.array([0.0, 7500.0, 0.0])
            return sat_b_pos, np.array([0.0, 7500.0, 0.0])

        monkeypatch.setattr(
            "benchmarks.stereo_imaging.verifier.engine._satellite_state_ecef_m",
            fake_state,
        )
        monkeypatch.setattr(
            "benchmarks.stereo_imaging.verifier.engine._strip_polyline_en",
            lambda *args, **kwargs: [(0.0, 0.0), (100.0, 0.0)],
        )
        monkeypatch.setattr(
            "benchmarks.stereo_imaging.verifier.engine._monte_carlo_overlap_fraction",
            lambda *args, **kwargs: 1.0,
        )

        actions = [
            ObservationAction(
                "sat_a",
                "t1",
                datetime(2026, 6, 18, 1, 0, 0, tzinfo=UTC),
                datetime(2026, 6, 18, 1, 0, 5, tzinfo=UTC),
                0.0,
                0.0,
            ),
            ObservationAction(
                "sat_b",
                "t1",
                datetime(2026, 6, 18, 1, 1, 0, tzinfo=UTC),
                datetime(2026, 6, 18, 1, 1, 5, tzinfo=UTC),
                0.0,
                0.0,
            ),
        ]
        satellites = {
            "sat_a": _make_sat_def(),
            "sat_b": _make_sat_def(),
        }
        target_defs = {
            "t1": TargetDef(
                target_id="t1",
                latitude_deg=0.0,
                longitude_deg=0.0,
                aoi_radius_m=5000.0,
                elevation_ref_m=0.0,
                scene_type="urban_structured",
            )
        }

        result = _evaluate_stereo_pair(
            case_id="case_x",
            mission=_mission_model(allow_cross_satellite=True),
            satellites=satellites,
            targets=target_defs,
            sf_sats={"sat_a": FakeSat("sat_a"), "sat_b": FakeSat("sat_b")},
            target_ecef={"t1": target_pos},
            actions=actions,
            first_index=0,
            second_index=1,
            first_derived=_derived_obs(sat="sat_a", action_index=0, scale_m=0.5),
            second_derived=_derived_obs(sat="sat_b", action_index=1, scale_m=0.5),
            stereo_mode="cross_satellite",
            n_samples=100,
            role="pair_overlap",
        )

        assert result["valid_pair"] is True
        assert result["stereo_mode"] == "cross_satellite"
        assert result["satellite_ids"] == ["sat_a", "sat_b"]
        assert result["gamma_deg"] == pytest.approx(10.0, abs=1e-6)


class TestIOLoadSolution:
    def test_malformed_no_actions(self, tmp_path):
        sol = tmp_path / "sol.json"
        _write_json(sol, {"not_actions": []})
        with pytest.raises(ValueError):
            load_solution_actions(sol, "case")

    def test_empty_actions(self, tmp_path):
        sol = _write_solution(tmp_path / "sol.json", [])
        actions = load_solution_actions(sol, "case")
        assert actions == []

    def test_rejects_legacy_case_id_mapping(self, tmp_path):
        sol = tmp_path / "sol.json"
        _write_json(sol, {"my_case": {"actions": []}})
        with pytest.raises(ValueError, match="actions"):
            load_solution_actions(sol, "my_case")


# ===================================================================
# Group 4: Action-level constraint tests (end-to-end via verify_solution)
# ===================================================================


class TestEmptySolution:
    def test_valid_zero_coverage(self, tmp_path):
        case_dir = _write_case(tmp_path / "case")
        sol = _write_solution(tmp_path / "sol.json", [])
        report = verify_solution(case_dir, sol)
        assert report.valid is True
        assert report.metrics["coverage_ratio"] == pytest.approx(0.0)
        assert report.metrics["normalized_quality"] == pytest.approx(0.0)


class TestDerivedObservationActionIndex:
    """Regression: pair/tri scoring must index actions by original solution index, not derived-list position."""

    def test_skipped_unknown_target_action_does_not_shift_indices(self, tmp_path):
        case_dir = _write_case(tmp_path / "case")
        sol = _write_solution(
            tmp_path / "sol.json",
            [
                _obs_action(target="nonexistent_target"),
                _obs_action(
                    start="2026-06-18T01:00:00Z",
                    end="2026-06-18T01:00:05Z",
                ),
            ],
        )
        report = verify_solution(case_dir, sol)
        assert len(report.derived_observations) == 1
        assert report.derived_observations[0]["action_index"] == 1


class TestZeroTargetsCase:
    """Regression: empty targets.yaml must not crash verify_solution with ZeroDivisionError."""

    def test_returns_report_with_zero_metrics_and_violation(self, tmp_path):
        # _write_case uses `targets or [default]`; [] is falsy, so write an empty list explicitly.
        case_dir = tmp_path / "case"
        case_dir.mkdir(parents=True)
        _write_yaml(case_dir / "mission.yaml", _base_mission_dict())
        _write_yaml(case_dir / "satellites.yaml", [_base_satellite_dict()])
        _write_yaml(case_dir / "targets.yaml", [])
        sol = _write_solution(tmp_path / "sol.json", [])
        report = verify_solution(case_dir, sol)
        assert report.metrics["coverage_ratio"] == pytest.approx(0.0)
        assert report.metrics["normalized_quality"] == pytest.approx(0.0)
        assert any("no targets" in v.lower() for v in report.violations)


class TestUnknownIds:
    def test_unknown_satellite_id(self, tmp_path):
        case_dir = _write_case(tmp_path / "case")
        sol = _write_solution(
            tmp_path / "sol.json",
            [_obs_action(sat="nonexistent_sat")],
        )
        report = verify_solution(case_dir, sol)
        assert report.valid is False
        assert any("unknown satellite_id" in v for v in report.violations)

    def test_unknown_target_id(self, tmp_path):
        case_dir = _write_case(tmp_path / "case")
        sol = _write_solution(
            tmp_path / "sol.json",
            [_obs_action(target="nonexistent_target")],
        )
        report = verify_solution(case_dir, sol)
        assert report.valid is False
        assert any("unknown target_id" in v for v in report.violations)


class TestDurationViolations:
    def test_end_before_start(self, tmp_path):
        case_dir = _write_case(tmp_path / "case")
        sol = _write_solution(
            tmp_path / "sol.json",
            [
                _obs_action(
                    start="2026-06-18T01:00:05Z",
                    end="2026-06-18T01:00:00Z",
                ),
            ],
        )
        report = verify_solution(case_dir, sol)
        assert report.valid is False
        assert any("end_time must be after start_time" in v for v in report.violations)

    def test_too_short(self, tmp_path):
        case_dir = _write_case(tmp_path / "case")
        sol = _write_solution(
            tmp_path / "sol.json",
            [
                _obs_action(
                    start="2026-06-18T01:00:00Z",
                    end="2026-06-18T01:00:01Z",
                ),
            ],
        )
        report = verify_solution(case_dir, sol)
        assert report.valid is False
        assert any("duration" in v for v in report.violations)

    def test_too_long(self, tmp_path):
        case_dir = _write_case(tmp_path / "case")
        sol = _write_solution(
            tmp_path / "sol.json",
            [
                _obs_action(
                    start="2026-06-18T01:00:00Z",
                    end="2026-06-18T01:02:00Z",
                ),
            ],
        )
        report = verify_solution(case_dir, sol)
        assert report.valid is False
        assert any("duration" in v for v in report.violations)


class TestHorizonViolation:
    def test_outside_horizon(self, tmp_path):
        case_dir = _write_case(tmp_path / "case")
        sol = _write_solution(
            tmp_path / "sol.json",
            [
                _obs_action(
                    start="2026-06-19T01:00:00Z",
                    end="2026-06-19T01:00:05Z",
                ),
            ],
        )
        report = verify_solution(case_dir, sol)
        assert report.valid is False
        assert any("outside mission horizon" in v for v in report.violations)


class TestOffNadirViolation:
    def test_combined_exceeds_max(self, tmp_path):
        case_dir = _write_case(tmp_path / "case")
        sol = _write_solution(
            tmp_path / "sol.json",
            [_obs_action(along=25.0, across=25.0)],
        )
        report = verify_solution(case_dir, sol)
        assert report.valid is False
        assert any("combined off-nadir" in v for v in report.violations)


class TestTimeOverlap:
    def test_overlapping_observations(self, tmp_path):
        case_dir = _write_case(tmp_path / "case")
        sol = _write_solution(
            tmp_path / "sol.json",
            [
                _obs_action(
                    start="2026-06-18T01:00:00Z",
                    end="2026-06-18T01:00:10Z",
                ),
                _obs_action(
                    start="2026-06-18T01:00:05Z",
                    end="2026-06-18T01:00:15Z",
                ),
            ],
        )
        report = verify_solution(case_dir, sol)
        assert report.valid is False
        assert any("overlapping observations" in v for v in report.violations)


class TestSlewTooFast:
    def test_insufficient_gap(self, tmp_path):
        targets = [
            _base_target_dict(target_id="t1", lat=0.0, lon=30.0),
            _base_target_dict(target_id="t2", lat=0.0, lon=60.0),
        ]
        case_dir = _write_case(tmp_path / "case", targets=targets)
        sol = _write_solution(
            tmp_path / "sol.json",
            [
                _obs_action(
                    target="t1",
                    start="2026-06-18T01:00:00Z",
                    end="2026-06-18T01:00:05Z",
                ),
                _obs_action(
                    target="t2",
                    start="2026-06-18T01:00:05Z",
                    end="2026-06-18T01:00:10Z",
                ),
            ],
        )
        report = verify_solution(case_dir, sol)
        assert report.valid is False
        assert any("insufficient slew/settle" in v for v in report.violations)


class TestBoresightMiss:
    def test_extreme_off_nadir(self, tmp_path):
        case_dir = _write_case(
            tmp_path / "case",
            satellites=[_base_satellite_dict(sat_id="sat_test")],
        )
        sat_dict = _base_satellite_dict()
        sat_dict["max_off_nadir_deg"] = 90.0
        case_dir = _write_case(
            tmp_path / "case2",
            satellites=[sat_dict],
        )
        sol = _write_solution(
            tmp_path / "sol.json",
            [_obs_action(along=0.0, across=89.5)],
        )
        report = verify_solution(case_dir, sol)
        assert report.valid is False
        assert any(
            "boresight does not intersect" in v or "access" in v.lower()
            for v in report.violations
        )


# ===================================================================
# Group 5: Golden end-to-end fixtures
# ===================================================================


def _fixture_dir(name: str) -> Path:
    return FIXTURES_DIR / name


def _assert_expected_value(actual: object, expected: object) -> None:
    if isinstance(expected, float):
        assert actual == pytest.approx(expected)
        return
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        for key, value in expected.items():
            assert key in actual, f"missing key: {key}"
            _assert_expected_value(actual[key], value)
        return
    if isinstance(expected, list):
        assert isinstance(actual, list)
        assert len(actual) == len(expected)
        for actual_item, expected_item in zip(actual, expected):
            _assert_expected_value(actual_item, expected_item)
        return
    assert actual == expected


@pytest.mark.parametrize("fixture_name", GOLDEN_FIXTURE_NAMES)
def test_golden_fixture(fixture_name: str):
    fdir = _fixture_dir(fixture_name)
    if not fdir.is_dir():
        pytest.skip(f"fixture {fixture_name} not found at {fdir}")

    expected_path = fdir / "expected.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    case_dir = fdir
    sol_path = fdir / "solution.json"
    report = verify_solution(case_dir, sol_path)
    report_dict = report.to_dict()

    assert report_dict["valid"] == expected["valid"]

    if "metrics" in expected:
        _assert_expected_value(report_dict["metrics"], expected["metrics"])

    if "violation_count" in expected:
        assert len(report_dict["violations"]) == expected["violation_count"]

    if "violations_contain" in expected:
        for substring in expected["violations_contain"]:
            assert any(
                substring in v for v in report_dict["violations"]
            ), f"no violation containing {substring!r}"
