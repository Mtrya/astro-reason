"""Standalone geometry helpers using skyfield and brahe."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import brahe
import numpy as np
from skyfield.api import EarthSatellite, load
from skyfield.framelib import itrs

from models import Satellite, Target

_NUMERICAL_EPS = 1e-9
_WGS84_A_M = 6378137.0
_WGS84_B_M = 6356752.3142451793

_TS = load.timescale()
brahe.set_global_eop_provider_from_static_provider(brahe.StaticEOPProvider.from_zero())


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


def make_earth_satellite(sat: Satellite) -> EarthSatellite:
    return EarthSatellite(sat.tle_line1, sat.tle_line2, name=sat.id, ts=_TS)


def satellite_state_ecef_m(sf_sat: EarthSatellite, dt: datetime) -> tuple[np.ndarray, np.ndarray]:
    t = _TS.from_datetime(dt.astimezone(UTC))
    g = sf_sat.at(t)
    pos, vel = g.frame_xyz_and_velocity(itrs)
    pos_m = np.asarray(pos.km, dtype=float).reshape(3) * 1000.0
    vel_mps = np.asarray(vel.km_per_s, dtype=float).reshape(3) * 1000.0
    return pos_m, vel_mps


def target_ecef_m(target: Target) -> np.ndarray:
    return np.asarray(
        brahe.position_geodetic_to_ecef(
            [target.longitude_deg, target.latitude_deg, target.elevation_ref_m],
            brahe.AngleFormat.DEGREES,
        ),
        dtype=float,
    ).reshape(3)


def off_nadir_deg(sat_pos_m: np.ndarray, target_pos_m: np.ndarray) -> float:
    los = target_pos_m - sat_pos_m
    norm = float(np.linalg.norm(los))
    if norm < _NUMERICAL_EPS:
        return 0.0
    los_hat = los / norm
    nadir = -sat_pos_m / np.linalg.norm(sat_pos_m)
    c = float(np.dot(nadir, los_hat))
    c = max(-1.0, min(1.0, c))
    return math.degrees(math.acos(c))


def solar_elevation_deg(epoch: brahe.Epoch, target_ecef_m: np.ndarray) -> float:
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
    return el


def combined_off_nadir_deg(along: float, across: float) -> float:
    a = math.radians(float(along))
    b = math.radians(float(across))
    return math.degrees(math.atan(math.sqrt(math.tan(a) ** 2 + math.tan(b) ** 2)))


def ray_ellipsoid_intersection_m(origin_m: np.ndarray, direction_unit: np.ndarray) -> float | None:
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


def line_of_sight_clear(sat_pos_m: np.ndarray, target_pos_m: np.ndarray) -> bool:
    los = target_pos_m - sat_pos_m
    dist = float(np.linalg.norm(los))
    if dist < _NUMERICAL_EPS:
        return True
    d = los / dist
    t_hit = ray_ellipsoid_intersection_m(sat_pos_m, d)
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


def angle_between_deg(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < _NUMERICAL_EPS or nb < _NUMERICAL_EPS:
        return 0.0
    c = float(np.dot(a, b) / (na * nb))
    c = max(-1.0, min(1.0, c))
    return math.degrees(math.acos(c))


def satellite_local_axes(sat_pos_m: np.ndarray, sat_vel_mps: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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


def required_steering_angles(
    sat_pos_m: np.ndarray, sat_vel_mps: np.ndarray, target_ecef_m: np.ndarray
) -> tuple[float, float]:
    """Compute off_nadir_along_deg and off_nadir_across_deg to point boresight at target."""
    d = (target_ecef_m - sat_pos_m) / np.linalg.norm(target_ecef_m - sat_pos_m)
    along_hat, across_hat, nadir_hat = satellite_local_axes(sat_pos_m, sat_vel_mps)
    along_deg = math.degrees(math.atan2(float(np.dot(d, along_hat)), float(np.dot(d, nadir_hat))))
    across_deg = math.degrees(math.atan2(float(np.dot(d, across_hat)), float(np.dot(d, nadir_hat))))
    return along_deg, across_deg


def boresight_unit_vector(
    sat_pos_m: np.ndarray, sat_vel_mps: np.ndarray, off_nadir_along_deg: float, off_nadir_across_deg: float
) -> np.ndarray:
    along_hat, across_hat, nadir_hat = satellite_local_axes(sat_pos_m, sat_vel_mps)
    vec = (
        nadir_hat
        + math.tan(math.radians(float(off_nadir_along_deg))) * along_hat
        + math.tan(math.radians(float(off_nadir_across_deg))) * across_hat
    )
    return vec / np.linalg.norm(vec)


def boresight_ground_intercept_ecef_m(
    sat_pos_m: np.ndarray, sat_vel_mps: np.ndarray, off_nadir_along_deg: float, off_nadir_across_deg: float
) -> np.ndarray | None:
    d = boresight_unit_vector(sat_pos_m, sat_vel_mps, off_nadir_along_deg, off_nadir_across_deg)
    t_hit = ray_ellipsoid_intersection_m(sat_pos_m, d)
    if t_hit is None:
        return None
    return sat_pos_m + t_hit * d


def ecef_to_enz(target_ecef_m: np.ndarray, point_ecef_m: np.ndarray) -> np.ndarray:
    return np.asarray(
        brahe.relative_position_ecef_to_enz(
            target_ecef_m,
            point_ecef_m,
            brahe.EllipsoidalConversionType.GEOCENTRIC,
        ),
        dtype=float,
    ).reshape(3)


def point_distance_to_polyline_2d(p_en: tuple[float, float], poly: list[tuple[float, float]]) -> float:
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


def strip_polyline_en(
    sf_sat: EarthSatellite,
    target_ecef_m: np.ndarray,
    start: datetime,
    end: datetime,
    step_s: float,
    off_nadir_along_deg: float,
    off_nadir_across_deg: float,
) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    if end <= start:
        return pts
    t = start
    while t <= end:
        sp, sv = satellite_state_ecef_m(sf_sat, t)
        gp = boresight_ground_intercept_ecef_m(sp, sv, off_nadir_along_deg, off_nadir_across_deg)
        if gp is not None:
            enz = ecef_to_enz(target_ecef_m, gp)
            pts.append((float(enz[0]), float(enz[1])))
        t += timedelta(seconds=step_s)
    if not pts or t - timedelta(seconds=step_s) < end:
        sp, sv = satellite_state_ecef_m(sf_sat, end)
        gp = boresight_ground_intercept_ecef_m(sp, sv, off_nadir_along_deg, off_nadir_across_deg)
        if gp is not None:
            enz = ecef_to_enz(target_ecef_m, gp)
            tail = (float(enz[0]), float(enz[1]))
            if not pts or pts[-1] != tail:
                pts.append(tail)
    # For short observations the polyline may miss the midpoint ground intercept
    # because the boresight sweeps across the target.  Insert midpoint explicitly
    # when it would improve the approximation (fewer than 3 unique points).
    if len(pts) < 3:
        mid = start + (end - start) / 2
        sp, sv = satellite_state_ecef_m(sf_sat, mid)
        gp = boresight_ground_intercept_ecef_m(sp, sv, off_nadir_along_deg, off_nadir_across_deg)
        if gp is not None:
            enz = ecef_to_enz(target_ecef_m, gp)
            mp = (float(enz[0]), float(enz[1]))
            # Insert midpoint between first and last if distinct
            if len(pts) == 2 and pts[0] != mp and pts[-1] != mp:
                pts.insert(1, mp)
            elif len(pts) == 1 and pts[0] != mp:
                pts.append(mp)
            elif len(pts) == 0:
                pts.append(mp)
    return pts


def pixel_scale_m(sat: Satellite, slant_range_m: float, off_nadir_deg: float = 0.0) -> float:
    """Ground pixel size including off-nadir secant correction.

    At nonzero off-nadir the ground-projected pixel is stretched by 1/cos(off_nadir).
    """
    base = slant_range_m * sat.pixel_ifov_deg * (math.pi / 180.0)
    if abs(off_nadir_deg) < _NUMERICAL_EPS:
        return base
    return base / math.cos(math.radians(off_nadir_deg))


def overlap_fraction_grid(
    aoi_radius_m: float,
    poly_a: list[tuple[float, float]],
    half_w_a_m: float,
    poly_b: list[tuple[float, float]],
    half_w_b_m: float,
    n_angles: int,
    n_radii: int,
) -> float:
    if aoi_radius_m <= _NUMERICAL_EPS:
        return 0.0
    total = 0
    inside = 0
    for i in range(n_radii):
        r = aoi_radius_m * math.sqrt((i + 1) / n_radii)
        for j in range(n_angles):
            theta = 2.0 * math.pi * j / n_angles
            e = r * math.cos(theta)
            n = r * math.sin(theta)
            total += 1
            da = point_distance_to_polyline_2d((e, n), poly_a)
            db = point_distance_to_polyline_2d((e, n), poly_b)
            if da <= half_w_a_m + _NUMERICAL_EPS and db <= half_w_b_m + _NUMERICAL_EPS:
                inside += 1
    if total == 0:
        return 0.0
    return inside / total


def tri_overlap_fraction_grid(
    aoi_radius_m: float,
    polys: list[list[tuple[float, float]]],
    half_ws: list[float],
    n_angles: int,
    n_radii: int,
) -> float:
    if aoi_radius_m <= _NUMERICAL_EPS:
        return 0.0
    total = 0
    inside = 0
    for i in range(n_radii):
        r = aoi_radius_m * math.sqrt((i + 1) / n_radii)
        for j in range(n_angles):
            theta = 2.0 * math.pi * j / n_angles
            e = r * math.cos(theta)
            n = r * math.sin(theta)
            total += 1
            if all(
                point_distance_to_polyline_2d((e, n), polys[k]) <= half_ws[k] + _NUMERICAL_EPS
                for k in range(3)
            ):
                inside += 1
    if total == 0:
        return 0.0
    return inside / total
