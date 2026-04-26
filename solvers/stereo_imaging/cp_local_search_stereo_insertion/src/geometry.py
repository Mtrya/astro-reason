"""Solver-local geometry, access intervals, and stereo product evaluation.

This module duplicates the minimal subset of the benchmark verifier's geometry
needed for candidate observation enumeration and pair/tri-stereo product scoring.
All constants and formulas are kept identical to the verifier to prevent drift.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import brahe
import numpy as np
from skyfield.api import EarthSatellite, load
from skyfield.framelib import itrs

from case_io import Mission, SatelliteDef, TargetDef

# ---------------------------------------------------------------------------
# Globals / frames
# ---------------------------------------------------------------------------

_NUMERICAL_EPS = 1e-9
_WGS84_A_M = 6378137.0
_WGS84_B_M = 6356752.3142451793

_TS = load.timescale()
brahe.set_global_eop_provider_from_static_provider(brahe.StaticEOPProvider.from_zero())

_SCENE_GEOM_BANDS_DEG: dict[str, tuple[float, float]] = {
    "urban_structured": (8.0, 18.0),
    "vegetated": (8.0, 14.0),
    "rugged": (10.0, 20.0),
    "open": (15.0, 25.0),
}


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _datetime_to_epoch(value: datetime) -> brahe.Epoch:
    value = value.astimezone(UTC)
    second = float(value.second) + (value.microsecond / 1_000_000.0)
    return brahe.Epoch.from_datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        second,
        0.0,
        brahe.TimeSystem.UTC,
    )


# ---------------------------------------------------------------------------
# Frame / vector helpers
# ---------------------------------------------------------------------------

def _angle_between_deg(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < _NUMERICAL_EPS or nb < _NUMERICAL_EPS:
        return 0.0
    c = float(np.dot(a, b) / (na * nb))
    c = max(-1.0, min(1.0, c))
    return math.degrees(math.acos(c))


# Cache for satellite state lookups; keyed by (satellite_id, dt_isoformat).
# This eliminates repeated SGP4 propagation for the same fixed candidate times.
_sat_state_cache: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}


def _clear_sat_state_cache() -> None:
    _sat_state_cache.clear()


def _satellite_state_ecef_m(sat: EarthSatellite, dt: datetime) -> tuple[np.ndarray, np.ndarray]:
    key = (sat.name, dt.astimezone(UTC).isoformat())
    cached = _sat_state_cache.get(key)
    if cached is not None:
        return cached
    t = _TS.from_datetime(dt.astimezone(UTC))
    g = sat.at(t)
    pos, vel = g.frame_xyz_and_velocity(itrs)
    pos_m = np.asarray(pos.km, dtype=float).reshape(3) * 1000.0
    vel_mps = np.asarray(vel.km_per_s, dtype=float).reshape(3) * 1000.0
    result = (pos_m, vel_mps)
    _sat_state_cache[key] = result
    return result


def _target_ecef_m(target: TargetDef) -> np.ndarray:
    return np.asarray(
        brahe.position_geodetic_to_ecef(
            [target.longitude_deg, target.latitude_deg, target.elevation_ref_m],
            brahe.AngleFormat.DEGREES,
        ),
        dtype=float,
    ).reshape(3)


def _ray_ellipsoid_intersection_m(
    origin_m: np.ndarray,
    direction_unit: np.ndarray,
) -> float | None:
    ox, oy, oz = (float(origin_m[i]) for i in range(3))
    dx, dy, dz = (float(direction_unit[i]) for i in range(3))
    a2 = _WGS84_A_M * _WGS84_A_M
    b2 = _WGS84_B_M * _WGS84_B_M
    inv_a2 = 1.0 / a2
    inv_b2 = 1.0 / b2
    aa = (dx * dx + dy * dy) * inv_a2 + dz * dz * inv_b2
    bb = 2.0 * ((ox * dx + oy * dy) * inv_a2 + oz * dz * inv_b2)
    cc = (ox * ox + oy * oy) * inv_a2 + oz * oz * inv_b2 - 1.0
    disc = bb * bb - 4.0 * aa * cc
    if disc < 0.0 or abs(aa) < 1.0e-30:
        return None
    sqrt_disc = math.sqrt(disc)
    t1 = (-bb - sqrt_disc) / (2.0 * aa)
    t2 = (-bb + sqrt_disc) / (2.0 * aa)
    candidates = [t for t in (t1, t2) if t > _NUMERICAL_EPS]
    if not candidates:
        return None
    return min(candidates)


def _line_of_sight_clear(sat_pos_m: np.ndarray, target_pos_m: np.ndarray) -> bool:
    los = target_pos_m - sat_pos_m
    dist = float(np.linalg.norm(los))
    if dist < _NUMERICAL_EPS:
        return True
    d = los / dist
    t_hit = _ray_ellipsoid_intersection_m(sat_pos_m, d)
    if t_hit is None:
        return False
    tx, ty, tz = (float(target_pos_m[i]) for i in range(3))
    inv_a2 = 1.0 / (_WGS84_A_M * _WGS84_A_M)
    inv_b2 = 1.0 / (_WGS84_B_M * _WGS84_B_M)
    q = (tx * tx + ty * ty) * inv_a2 + tz * tz * inv_b2
    if q >= 1.0 - _NUMERICAL_EPS:
        return t_hit + 1.0 >= dist
    r_target = float(np.linalg.norm(target_pos_m))
    depth_m = r_target * (1.0 / math.sqrt(q) - 1.0)
    return t_hit + depth_m + 10.0 >= dist


def _off_nadir_deg(sat_pos_m: np.ndarray, target_pos_m: np.ndarray) -> float:
    los = target_pos_m - sat_pos_m
    if float(np.linalg.norm(los)) < _NUMERICAL_EPS:
        return 0.0
    los_hat = los / np.linalg.norm(los)
    nadir = -sat_pos_m / np.linalg.norm(sat_pos_m)
    c = float(np.dot(nadir, los_hat))
    c = max(-1.0, min(1.0, c))
    return math.degrees(math.acos(c))


def _solar_elevation_azimuth_deg(epoch: brahe.Epoch, target_ecef_m: np.ndarray) -> tuple[float, float]:
    sun_hat = np.asarray(brahe.sun_position(epoch), dtype=float).reshape(3)
    sun_hat = sun_hat / np.linalg.norm(sun_hat)
    r = np.asarray(brahe.rotation_eci_to_ecef(epoch), dtype=float).reshape(3, 3)
    sun_dir_ecef = (r @ sun_hat).reshape(3)
    au = 1.496e11
    r_t = target_ecef_m.reshape(3)
    up = r_t / np.linalg.norm(r_t)
    v = au * sun_dir_ecef - r_t
    v = v / np.linalg.norm(v)
    el = math.degrees(math.asin(max(-1.0, min(1.0, float(np.dot(up, v))))))
    east = np.cross(np.array([0.0, 0.0, 1.0]), up)
    if float(np.linalg.norm(east)) < _NUMERICAL_EPS:
        east = np.array([0.0, 1.0, 0.0])
    else:
        east = east / np.linalg.norm(east)
    north = np.cross(up, east)
    north = north / np.linalg.norm(north)
    proj = v - float(np.dot(v, up)) * up
    if float(np.linalg.norm(proj)) < _NUMERICAL_EPS:
        az = 0.0
    else:
        proj = proj / np.linalg.norm(proj)
        az = math.degrees(math.atan2(float(np.dot(proj, east)), float(np.dot(proj, north))))
        if az < 0.0:
            az += 360.0
    return el, az


def _ecef_to_enz(target_ecef_m: np.ndarray, point_ecef_m: np.ndarray) -> np.ndarray:
    return np.asarray(
        brahe.relative_position_ecef_to_enz(
            target_ecef_m,
            point_ecef_m,
            brahe.EllipsoidalConversionType.GEOCENTRIC,
        ),
        dtype=float,
    ).reshape(3)


def _satellite_local_axes(
    sat_pos_m: np.ndarray,
    sat_vel_mps: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nadir = -sat_pos_m / np.linalg.norm(sat_pos_m)
    along = sat_vel_mps - float(np.dot(sat_vel_mps, nadir)) * nadir
    if float(np.linalg.norm(along)) < _NUMERICAL_EPS:
        fallback = np.array([0.0, 0.0, 1.0])
        if abs(float(np.dot(fallback, nadir))) > 0.9:
            fallback = np.array([0.0, 1.0, 0.0])
        along = fallback - float(np.dot(fallback, nadir)) * nadir
    along = along / np.linalg.norm(along)
    across = np.cross(along, nadir)
    if float(np.linalg.norm(across)) < _NUMERICAL_EPS:
        across = np.array([1.0, 0.0, 0.0])
    else:
        across = across / np.linalg.norm(across)
    return along, across, nadir


def _boresight_unit_vector(
    sat_pos_m: np.ndarray,
    sat_vel_mps: np.ndarray,
    off_nadir_along_deg: float,
    off_nadir_across_deg: float,
) -> np.ndarray:
    along_hat, across_hat, nadir_hat = _satellite_local_axes(sat_pos_m, sat_vel_mps)
    vec = (
        nadir_hat
        + math.tan(math.radians(float(off_nadir_along_deg))) * along_hat
        + math.tan(math.radians(float(off_nadir_across_deg))) * across_hat
    )
    return vec / np.linalg.norm(vec)


def _boresight_ground_intercept_ecef_m(
    sat_pos_m: np.ndarray,
    sat_vel_mps: np.ndarray,
    off_nadir_along_deg: float,
    off_nadir_across_deg: float,
) -> np.ndarray | None:
    d = _boresight_unit_vector(
        sat_pos_m,
        sat_vel_mps,
        off_nadir_along_deg,
        off_nadir_across_deg,
    )
    t_hit = _ray_ellipsoid_intersection_m(sat_pos_m, d)
    if t_hit is None:
        return None
    return sat_pos_m + t_hit * d


def _boresight_azimuth_deg(target_ecef_m: np.ndarray, boresight_ground_ecef_m: np.ndarray) -> float:
    rel = _ecef_to_enz(target_ecef_m, boresight_ground_ecef_m)
    e, n = float(rel[0]), float(rel[1])
    if abs(e) < _NUMERICAL_EPS and abs(n) < _NUMERICAL_EPS:
        return 0.0
    return math.degrees(math.atan2(e, n)) % 360.0


def _combined_off_nadir_deg(along: float, across: float) -> float:
    a = math.radians(float(along))
    b = math.radians(float(across))
    return math.degrees(math.atan(math.sqrt(math.tan(a) ** 2 + math.tan(b) ** 2)))


# ---------------------------------------------------------------------------
# Slew
# ---------------------------------------------------------------------------

def _min_slew_time_s(delta_deg: float, sat_def: SatelliteDef) -> float:
    d = abs(delta_deg)
    if d < _NUMERICAL_EPS:
        return 0.0
    omega = sat_def.max_slew_velocity_deg_per_s
    alpha = sat_def.max_slew_acceleration_deg_per_s2
    if omega < _NUMERICAL_EPS or alpha < _NUMERICAL_EPS:
        return float("inf")
    d_triangular = omega * omega / alpha
    if d <= d_triangular:
        return 2.0 * math.sqrt(d / alpha)
    else:
        return d / omega + omega / alpha


# ---------------------------------------------------------------------------
# Access intervals
# ---------------------------------------------------------------------------

def _access_predicate(
    sat: EarthSatellite,
    target: TargetDef,
    target_ecef_m: np.ndarray,
    sat_def: SatelliteDef,
    mission: Mission,
    dt: datetime,
) -> bool:
    sp, _ = _satellite_state_ecef_m(sat, dt)
    if not _line_of_sight_clear(sp, target_ecef_m):
        return False
    off = _off_nadir_deg(sp, target_ecef_m)
    if off > sat_def.max_off_nadir_deg + 1e-6:
        return False
    epoch = _datetime_to_epoch(dt)
    el, _ = _solar_elevation_azimuth_deg(epoch, target_ecef_m)
    if el < mission.min_solar_elevation_deg - 1e-6:
        return False
    return True


def _access_interval_sampling_step_s(sat_def: SatelliteDef) -> float:
    return max(0.25, min(1.0, sat_def.min_obs_duration_s / 2.0))


def _iter_window_samples(
    start: datetime,
    end: datetime,
    *,
    step_s: float,
):
    if end < start:
        return
    yield start
    if end == start:
        return
    step = timedelta(seconds=step_s)
    current = start
    while current + step < end:
        current += step
        yield current
    yield end


def _access_holds_over_window(
    sat: EarthSatellite,
    target: TargetDef,
    target_ecef_m: np.ndarray,
    sat_def: SatelliteDef,
    mission: Mission,
    start: datetime,
    end: datetime,
    *,
    step_s: float,
) -> bool:
    return all(
        _access_predicate(sat, target, target_ecef_m, sat_def, mission, dt)
        for dt in _iter_window_samples(start, end, step_s=step_s)
    )


def _discover_access_interval_around_action(
    sat: EarthSatellite,
    target: TargetDef,
    target_ecef_m: np.ndarray,
    sat_def: SatelliteDef,
    mission: Mission,
    horizon_start: datetime,
    horizon_end: datetime,
    start: datetime,
    end: datetime,
    *,
    step_s: float,
) -> tuple[datetime, datetime]:
    step = timedelta(seconds=step_s)

    interval_start = start
    probe = start
    while probe > horizon_start:
        prev = max(horizon_start, probe - step)
        if not _access_predicate(sat, target, target_ecef_m, sat_def, mission, prev):
            break
        interval_start = prev
        if prev == horizon_start:
            break
        probe = prev

    interval_end = end
    probe = end
    while probe < horizon_end:
        nxt = min(horizon_end, probe + step)
        if not _access_predicate(sat, target, target_ecef_m, sat_def, mission, nxt):
            break
        interval_end = nxt
        if nxt == horizon_end:
            break
        probe = nxt

    return interval_start, interval_end


def _register_access_interval(
    intervals: list[tuple[datetime, datetime, str]],
    sat_id: str,
    target_id: str,
    start: datetime,
    end: datetime,
) -> str:
    for idx, (existing_start, existing_end, aid) in enumerate(intervals):
        if end < existing_start or existing_end < start:
            continue
        merged = (min(start, existing_start), max(end, existing_end), aid)
        intervals[idx] = merged
        return aid
    aid = f"{sat_id}::{target_id}::{len(intervals)}"
    intervals.append((start, end, aid))
    intervals.sort(key=lambda item: item[0])
    return aid


def discover_access_intervals(
    sat: EarthSatellite,
    sat_def: SatelliteDef,
    target: TargetDef,
    target_ecef_m: np.ndarray,
    mission: Mission,
    discovery_step_s: float = 60.0,
) -> list[tuple[datetime, datetime, str]]:
    """Discover all continuous access intervals for a (satellite, target) pair.

    Uses a coarse `discovery_step_s` for fast scanning (default 60 s), then
    expands to the true interval edges using the finer access-sampling step.

    Returns a list of (start, end, access_interval_id) sorted by start time.
    """
    intervals: list[tuple[datetime, datetime, str]] = []
    coarse_step = timedelta(seconds=max(1.0, discovery_step_s))
    fine_step_s = _access_interval_sampling_step_s(sat_def)
    current = mission.horizon_start

    while current <= mission.horizon_end:
        if _access_predicate(sat, target, target_ecef_m, sat_def, mission, current):
            interval_start = current
            interval_end = current
            # Expand backward with fine step to true edge
            probe = current
            while probe > mission.horizon_start:
                prev = max(mission.horizon_start, probe - timedelta(seconds=fine_step_s))
                if not _access_predicate(sat, target, target_ecef_m, sat_def, mission, prev):
                    break
                interval_start = prev
                if prev == mission.horizon_start:
                    break
                probe = prev
            # Expand forward with fine step to true edge
            probe = current
            while probe < mission.horizon_end:
                nxt = min(mission.horizon_end, probe + timedelta(seconds=fine_step_s))
                if not _access_predicate(sat, target, target_ecef_m, sat_def, mission, nxt):
                    break
                interval_end = nxt
                if nxt == mission.horizon_end:
                    break
                probe = nxt
            _register_access_interval(intervals, sat_def.sat_id, target.target_id, interval_start, interval_end)
            current = interval_end + coarse_step
        else:
            current += coarse_step

    return intervals


# ---------------------------------------------------------------------------
# Strip / overlap helpers
# ---------------------------------------------------------------------------

def _point_distance_to_polyline_2d(
    p_en: tuple[float, float],
    poly: list[tuple[float, float]],
) -> float:
    if not poly:
        return float("inf")
    px, py = p_en
    best = float("inf")
    for i in range(len(poly) - 1):
        x1, y1 = poly[i]
        x2, y2 = poly[i + 1]
        vx, vy = x2 - x1, y2 - y1
        seg_len2 = vx * vx + vy * vy
        if seg_len2 < _NUMERICAL_EPS:
            d = math.hypot(px - x1, py - y1)
            best = min(best, d)
            continue
        t = max(0.0, min(1.0, ((px - x1) * vx + (py - y1) * vy) / seg_len2))
        qx = x1 + t * vx
        qy = y1 + t * vy
        best = min(best, math.hypot(px - qx, py - qy))
    return best


def _strip_polyline_en(
    sat: EarthSatellite,
    target_ecef_m: np.ndarray,
    start: datetime,
    end: datetime,
    sample_step_s: float,
    *,
    off_nadir_along_deg: float = 0.0,
    off_nadir_across_deg: float = 0.0,
) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    if end <= start:
        return pts
    t = start
    while t <= end:
        sp, sv = _satellite_state_ecef_m(sat, t)
        gp = _boresight_ground_intercept_ecef_m(
            sp,
            sv,
            off_nadir_along_deg,
            off_nadir_across_deg,
        )
        if gp is None:
            t += timedelta(seconds=sample_step_s)
            continue
        enz = _ecef_to_enz(target_ecef_m, gp)
        e, n = float(enz[0]), float(enz[1])
        pts.append((e, n))
        t += timedelta(seconds=sample_step_s)
    if not pts or t - timedelta(seconds=sample_step_s) < end:
        sp, sv = _satellite_state_ecef_m(sat, end)
        gp = _boresight_ground_intercept_ecef_m(
            sp,
            sv,
            off_nadir_along_deg,
            off_nadir_across_deg,
        )
        if gp is not None:
            enz = _ecef_to_enz(target_ecef_m, gp)
            e, n = float(enz[0]), float(enz[1])
            tail = (e, n)
            if not pts or pts[-1] != tail:
                pts.append(tail)
    return pts


# ---------------------------------------------------------------------------
# Monte Carlo overlap
# ---------------------------------------------------------------------------

def _observation_window_key(start: datetime, end: datetime) -> tuple[str, str]:
    return (_iso_z(start), _iso_z(end))


def _stereo_mc_rng(
    case_id: str,
    satellite_id: str,
    target_id: str,
    access_interval_id: str,
    *,
    window_keys: tuple[tuple[str, str], ...],
    n_samples: int,
    role: str,
) -> random.Random:
    flat = "\x1f".join(f"{w[0]}\x1f{w[1]}" for w in sorted(window_keys))
    payload = "\x1e".join(
        (case_id, satellite_id, target_id, access_interval_id, role, str(n_samples), flat)
    ).encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return random.Random(seed)


def _monte_carlo_overlap_fraction(
    aoi_radius_m: float,
    poly_a: list[tuple[float, float]],
    half_w_a_m: float,
    poly_b: list[tuple[float, float]],
    half_w_b_m: float,
    *,
    n_samples: int,
    rng: random.Random,
) -> float:
    if aoi_radius_m <= _NUMERICAL_EPS:
        return 0.0
    inside_both = 0
    for _ in range(n_samples):
        r = aoi_radius_m * math.sqrt(rng.random())
        theta = rng.random() * 2.0 * math.pi
        e = r * math.cos(theta)
        n = r * math.sin(theta)
        da = _point_distance_to_polyline_2d((e, n), poly_a)
        db = _point_distance_to_polyline_2d((e, n), poly_b)
        if da <= half_w_a_m + _NUMERICAL_EPS and db <= half_w_b_m + _NUMERICAL_EPS:
            inside_both += 1
    return inside_both / n_samples


def _monte_carlo_tri_overlap(
    aoi_radius_m: float,
    polys: list[list[tuple[float, float]]],
    half_ws: list[float],
    *,
    n_samples: int,
    rng: random.Random,
) -> float:
    if aoi_radius_m <= _NUMERICAL_EPS:
        return 0.0
    ok = 0
    for _ in range(n_samples):
        r = aoi_radius_m * math.sqrt(rng.random())
        theta = rng.random() * 2.0 * math.pi
        e = r * math.cos(theta)
        n = r * math.sin(theta)
        if all(
            _point_distance_to_polyline_2d((e, n), polys[i]) <= half_ws[i] + _NUMERICAL_EPS
            for i in range(3)
        ):
            ok += 1
    return ok / n_samples


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

def _pair_geom_quality(gamma_deg: float, scene: str) -> float:
    lo, hi = _SCENE_GEOM_BANDS_DEG.get(scene, (8.0, 18.0))
    if lo <= gamma_deg <= hi:
        return 1.0
    dist = min(abs(gamma_deg - lo), abs(gamma_deg - hi))
    return max(0.0, 1.0 - dist / 10.0)


def _tri_bonus_R(pair_ok: list[bool], has_anchor: bool) -> float:
    r = 0.0
    if sum(pair_ok) >= 2:
        r += 0.6
    if has_anchor:
        r += 0.4
    return min(1.0, r)


def _tri_quality_from_valid_pairs(
    pair_flags: list[bool],
    pair_qs: list[float],
    *,
    beta: float,
    tri_bonus_R: float,
) -> float:
    valid_pair_qs = [q for ok, q in zip(pair_flags, pair_qs, strict=True) if ok]
    if not valid_pair_qs:
        return 0.0
    return min(1.0, max(valid_pair_qs) + beta * tri_bonus_R)


# ---------------------------------------------------------------------------
# Steering helper for candidate generation
# ---------------------------------------------------------------------------

def compute_steering_angles_to_target(
    sat_pos_m: np.ndarray,
    sat_vel_mps: np.ndarray,
    target_ecef_m: np.ndarray,
) -> tuple[float, float]:
    """Return (off_nadir_along_deg, off_nadir_across_deg) that point boresight at target.

    Solves:
        los_hat = (target - sat) / |target - sat|
        vec = nadir + tan(a)*along + tan(b)*across
        los_hat = vec / |vec|

    Returns (0.0, 0.0) if the target is directly below the satellite (nadir).
    """
    los = target_ecef_m - sat_pos_m
    dist = float(np.linalg.norm(los))
    if dist < _NUMERICAL_EPS:
        return 0.0, 0.0
    los_hat = los / dist
    along_hat, across_hat, nadir_hat = _satellite_local_axes(sat_pos_m, sat_vel_mps)
    dot_nadir = float(np.dot(los_hat, nadir_hat))
    if abs(dot_nadir) < _NUMERICAL_EPS:
        # Nearly horizontal; would require huge steering angles.
        # Return large angles so caller can reject.
        return 89.0, 89.0
    tan_along = float(np.dot(los_hat, along_hat)) / dot_nadir
    tan_across = float(np.dot(los_hat, across_hat)) / dot_nadir
    along_deg = math.degrees(math.atan(tan_along))
    across_deg = math.degrees(math.atan(tan_across))
    return along_deg, across_deg
