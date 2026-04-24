"""Stereo imaging v4 verification engine."""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import brahe
import numpy as np
from skyfield.api import EarthSatellite, load
from skyfield.framelib import itrs

from .io import load_case, load_solution_actions
from .models import (
    DerivedObservation,
    Mission,
    ObservationAction,
    SatelliteDef,
    TargetDef,
    VerificationReport,
)

# ---------------------------------------------------------------------------
# Numerics / frames
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


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _observation_window_key(act: ObservationAction) -> tuple[str, str]:
    """Stable (start, end) in UTC Z notation for MC seeding (order-independent identity)."""
    return (_iso_z(act.start), _iso_z(act.end))


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
    """Deterministic RNG per stereo MC evaluation; invariant to JSON action order."""
    flat = "\x1f".join(f"{w[0]}\x1f{w[1]}" for w in sorted(window_keys))
    payload = "\x1e".join(
        (case_id, satellite_id, target_id, access_interval_id, role, str(n_samples), flat)
    ).encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return random.Random(seed)


def _angle_between_deg(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < _NUMERICAL_EPS or nb < _NUMERICAL_EPS:
        return 0.0
    c = float(np.dot(a, b) / (na * nb))
    c = max(-1.0, min(1.0, c))
    return math.degrees(math.acos(c))


def _satellite_state_ecef_m(sat: EarthSatellite, dt: datetime) -> tuple[np.ndarray, np.ndarray]:
    """Return (position_m, velocity_mps) in ITRS/ECEF consistent with brahe geodetic ECEF."""
    t = _TS.from_datetime(dt.astimezone(UTC))
    g = sat.at(t)
    pos, vel = g.frame_xyz_and_velocity(itrs)
    pos_m = np.asarray(pos.km, dtype=float).reshape(3) * 1000.0
    vel_mps = np.asarray(vel.km_per_s, dtype=float).reshape(3) * 1000.0
    return pos_m, vel_mps


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
    """Smallest positive t where origin + t*dir hits WGS84-like ellipsoid."""
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


def _line_of_sight_clear(
    sat_pos_m: np.ndarray,
    target_pos_m: np.ndarray,
) -> bool:
    """True when the first Earth intersection is the target point itself."""
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


def _solar_elevation_azimuth_deg(
    epoch: brahe.Epoch,
    target_ecef_m: np.ndarray,
) -> tuple[float, float]:
    """Solar elevation and azimuth (deg) at target using brahe sun vector."""
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


def _enu_horizontal(en_vec: np.ndarray) -> tuple[float, float]:
    return float(en_vec[0]), float(en_vec[1])


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
    """Return local (along-track, across-track, nadir) unit vectors."""
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


def _boresight_azimuth_deg(
    target_ecef_m: np.ndarray,
    boresight_ground_ecef_m: np.ndarray,
) -> float:
    rel = _ecef_to_enz(target_ecef_m, boresight_ground_ecef_m)
    e, n = float(rel[0]), float(rel[1])
    if abs(e) < _NUMERICAL_EPS and abs(n) < _NUMERICAL_EPS:
        return 0.0
    return math.degrees(math.atan2(e, n)) % 360.0


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
        e, n = _enu_horizontal(enz)
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
            e, n = _enu_horizontal(enz)
            tail = (e, n)
            if not pts or pts[-1] != tail:
                pts.append(tail)
    return pts


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
    """Approximate area(intersection of strips with AOI disk) / area(disk).

    Polyline vertices and sample points are in the same local ENU frame (origin at
    target center); target ECEF is not needed here.
    """
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


def _combined_off_nadir_deg(along: float, across: float) -> float:
    """Tilt angle (deg) from nadir for the tan-steering model in `_boresight_unit_vector`."""
    a = math.radians(float(along))
    b = math.radians(float(across))
    return math.degrees(math.atan(math.sqrt(math.tan(a) ** 2 + math.tan(b) ** 2)))


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
    """
    Sample access on observation-scale resolution.

    v4 observations are 2-60 s long in the canonical release, so a 1 s grid keeps
    short valid windows and brief daylight/off-nadir outages from being aliased away.
    """
    return max(0.25, min(1.0, sat_def.min_obs_duration_s / 2.0))


def _assign_access_id(
    start: datetime,
    end: datetime,
    intervals: list[tuple[datetime, datetime, str]],
) -> str | None:
    for a, b, aid in intervals:
        if a <= start and end <= b:
            return aid
    return None


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
    """Expand from a known-valid action window to the surrounding continuous interval."""
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


def _min_slew_time_s(delta_deg: float, sat_def: SatelliteDef) -> float:
    """Minimum slew time using bang-bang (trapezoidal) profile."""
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


def _pair_geom_quality(gamma_deg: float, scene: str) -> float:
    lo, hi = _SCENE_GEOM_BANDS_DEG.get(scene, (8.0, 18.0))
    if lo <= gamma_deg <= hi:
        return 1.0
    dist = min(abs(gamma_deg - lo), abs(gamma_deg - hi))
    return max(0.0, 1.0 - dist / 10.0)


def _tri_bonus_R(
    pair_ok: list[bool],
    has_anchor: bool,
) -> float:
    """Bounded redundancy + anchor bonus in [0, 1]."""
    r = 0.0
    if sum(pair_ok) >= 2:
        r += 0.6
    if has_anchor:
        r += 0.4
    return min(1.0, r)


def _action_midpoint(action: ObservationAction) -> datetime:
    return action.start + (action.end - action.start) / 2


def _product_time_separation_s(actions: list[ObservationAction]) -> float:
    if len(actions) < 2:
        return 0.0
    midpoints = [_action_midpoint(action) for action in actions]
    return (max(midpoints) - min(midpoints)).total_seconds()


def _stereo_pair_mode(
    mission: Mission,
    first_action: ObservationAction,
    second_action: ObservationAction,
    first_derived: DerivedObservation,
    second_derived: DerivedObservation,
) -> str | None:
    """Return the stereo mode if a pair is allowed by mission-level product policy."""
    if first_derived.target_id != second_derived.target_id:
        return None
    if first_derived.access_interval_id == "none" or second_derived.access_interval_id == "none":
        return None
    separation_s = _product_time_separation_s([first_action, second_action])
    if separation_s - 1e-6 > mission.max_stereo_pair_separation_s:
        return None
    if first_derived.satellite_id == second_derived.satellite_id:
        if first_derived.access_interval_id != second_derived.access_interval_id:
            return None
        return "same_satellite_same_pass"
    if not mission.allow_cross_satellite_stereo:
        return None
    return "cross_satellite"


def _product_seed_labels(derived: list[DerivedObservation]) -> tuple[str, str]:
    satellite_label = "+".join(sorted(d.satellite_id for d in derived))
    access_label = "+".join(
        sorted(f"{d.satellite_id}:{d.access_interval_id}" for d in derived)
    )
    return satellite_label, access_label


def _evaluate_stereo_pair(
    *,
    case_id: str,
    mission: Mission,
    satellites: dict[str, SatelliteDef],
    targets: dict[str, TargetDef],
    sf_sats: dict[str, EarthSatellite],
    target_ecef: dict[str, np.ndarray],
    actions: list[ObservationAction],
    first_index: int,
    second_index: int,
    first_derived: DerivedObservation,
    second_derived: DerivedObservation,
    stereo_mode: str,
    n_samples: int,
    role: str,
) -> dict[str, Any]:
    first_action = actions[first_index]
    second_action = actions[second_index]
    target_id = first_derived.target_id
    target = targets[target_id]
    target_pos = target_ecef[target_id]
    first_sat = satellites[first_derived.satellite_id]
    second_sat = satellites[second_derived.satellite_id]
    first_sf = sf_sats[first_derived.satellite_id]
    second_sf = sf_sats[second_derived.satellite_id]

    first_pos = _satellite_state_ecef_m(first_sf, _action_midpoint(first_action))[0]
    second_pos = _satellite_state_ecef_m(second_sf, _action_midpoint(second_action))[0]
    first_view = (first_pos - target_pos) / np.linalg.norm(first_pos - target_pos)
    second_view = (second_pos - target_pos) / np.linalg.norm(second_pos - target_pos)
    gamma = _angle_between_deg(first_view, second_view)
    bisector = first_view + second_view
    bisector_norm = float(np.linalg.norm(bisector))
    if bisector_norm < _NUMERICAL_EPS:
        bisector_el_deg = 0.0
        asymmetry_deg = 90.0
    else:
        bisector_hat = bisector / bisector_norm
        up_t = target_pos / float(np.linalg.norm(target_pos))
        cos_a = max(-1.0, min(1.0, float(np.dot(up_t, bisector_hat))))
        asymmetry_deg = math.degrees(math.acos(cos_a))
        bisector_el_deg = 90.0 - asymmetry_deg

    first_half_width_m = first_derived.slant_range_m * math.tan(
        math.radians(first_sat.half_cross_track_fov_deg)
    )
    second_half_width_m = second_derived.slant_range_m * math.tan(
        math.radians(second_sat.half_cross_track_fov_deg)
    )
    first_poly = _strip_polyline_en(
        first_sf,
        target_pos,
        first_action.start,
        first_action.end,
        sample_step_s=8.0,
        off_nadir_along_deg=first_action.off_nadir_along_deg,
        off_nadir_across_deg=first_action.off_nadir_across_deg,
    )
    second_poly = _strip_polyline_en(
        second_sf,
        target_pos,
        second_action.start,
        second_action.end,
        sample_step_s=8.0,
        off_nadir_along_deg=second_action.off_nadir_along_deg,
        off_nadir_across_deg=second_action.off_nadir_across_deg,
    )
    window_keys = tuple(
        sorted((_observation_window_key(first_action), _observation_window_key(second_action)))
    )
    satellite_label, access_label = _product_seed_labels([first_derived, second_derived])
    rng_pair = _stereo_mc_rng(
        case_id,
        satellite_label,
        target_id,
        access_label,
        window_keys=window_keys,
        n_samples=n_samples,
        role=role,
    )
    overlap = _monte_carlo_overlap_fraction(
        target.aoi_radius_m,
        first_poly,
        first_half_width_m,
        second_poly,
        second_half_width_m,
        n_samples=n_samples,
        rng=rng_pair,
    )
    first_scale_m = first_derived.effective_pixel_scale_m
    second_scale_m = second_derived.effective_pixel_scale_m
    pixel_scale_ratio = max(first_scale_m, second_scale_m) / min(first_scale_m, second_scale_m)
    first_nadir_alt = float(np.linalg.norm(first_pos)) - _WGS84_A_M
    second_nadir_alt = float(np.linalg.norm(second_pos)) - _WGS84_A_M
    mean_alt = max(1000.0, 0.5 * (first_nadir_alt + second_nadir_alt))
    bh = float(np.linalg.norm(first_pos - second_pos)) / mean_alt

    ok = (
        overlap + 1e-6 >= mission.min_overlap_fraction
        and mission.min_convergence_deg - 1e-6 <= gamma <= mission.max_convergence_deg + 1e-6
        and pixel_scale_ratio <= mission.max_pixel_scale_ratio + 1e-6
    )
    q_overlap = min(1.0, overlap / 0.95)
    q_res = max(0.0, 1.0 - (pixel_scale_ratio - 1.0) / 0.5)
    q_geom = _pair_geom_quality(gamma, target.scene_type)
    weights = mission.pair_weights
    q_pair = (
        weights["geometry"] * q_geom
        + weights["overlap"] * q_overlap
        + weights["resolution"] * q_res
    )
    satellite_ids = [first_derived.satellite_id, second_derived.satellite_id]
    access_interval_ids = [first_derived.access_interval_id, second_derived.access_interval_id]
    return {
        "satellite_id": first_derived.satellite_id
        if first_derived.satellite_id == second_derived.satellite_id
        else None,
        "satellite_ids": satellite_ids,
        "target_id": target_id,
        "access_interval_id": first_derived.access_interval_id
        if first_derived.access_interval_id == second_derived.access_interval_id
        else None,
        "access_interval_ids": access_interval_ids,
        "stereo_mode": stereo_mode,
        "time_separation_s": _product_time_separation_s([first_action, second_action]),
        "gamma_deg": gamma,
        "bisector_elevation_deg": bisector_el_deg,
        "asymmetry_deg": asymmetry_deg,
        "overlap_fraction": overlap,
        "pixel_scale_ratio": pixel_scale_ratio,
        "b_h_proxy": bh,
        "valid_pair": ok,
        "q_pair": q_pair if ok else 0.0,
    }


def verify_solution(case_dir: str | Path, solution_path: str | Path) -> VerificationReport:
    case_path = Path(case_dir)
    case_id = case_path.name
    mission, satellites, targets = load_case(case_path)
    actions = load_solution_actions(solution_path, case_id)

    violations: list[str] = []

    # EarthSatellite cache
    sf_sats: dict[str, EarthSatellite] = {}
    for sid, sd in satellites.items():
        sf_sats[sid] = EarthSatellite(sd.tle_line1, sd.tle_line2, name=sid, ts=_TS)

    # Access intervals are discovered lazily around referenced observations.
    access_index: dict[tuple[str, str], list[tuple[datetime, datetime, str]]] = {}
    target_ecef: dict[str, np.ndarray] = {tid: _target_ecef_m(t) for tid, t in targets.items()}

    derived_list: list[DerivedObservation] = []

    # --- Action-level checks ---
    for k, act in enumerate(actions):
        prefix = f"actions[{k}]"
        if act.end <= act.start:
            violations.append(f"{prefix}: end_time must be after start_time")
        if act.start < mission.horizon_start or act.end > mission.horizon_end:
            violations.append(f"{prefix}: observation outside mission horizon")
        if act.satellite_id not in satellites:
            violations.append(f"{prefix}: unknown satellite_id {act.satellite_id!r}")
            continue
        if act.target_id not in targets:
            violations.append(f"{prefix}: unknown target_id {act.target_id!r}")
            continue
        sd = satellites[act.satellite_id]
        dur = (act.end - act.start).total_seconds()
        if dur + _NUMERICAL_EPS < sd.min_obs_duration_s or dur - _NUMERICAL_EPS > sd.max_obs_duration_s:
            violations.append(
                f"{prefix}: duration {dur:.3f}s not in "
                f"[{sd.min_obs_duration_s}, {sd.max_obs_duration_s}]"
            )
        comb = _combined_off_nadir_deg(act.off_nadir_along_deg, act.off_nadir_across_deg)
        if comb - 1e-6 > sd.max_off_nadir_deg:
            violations.append(
                f"{prefix}: combined off-nadir {comb:.6f}deg exceeds max_off_nadir_deg "
                f"{sd.max_off_nadir_deg}"
            )

    # Per-satellite: overlap and slew
    by_sat: dict[str, list[tuple[int, ObservationAction]]] = {}
    for i, act in enumerate(actions):
        if act.satellite_id not in satellites or act.target_id not in targets:
            continue
        by_sat.setdefault(act.satellite_id, []).append((i, act))
    for sid, lst in by_sat.items():
        lst.sort(key=lambda x: x[1].start)
        for j in range(len(lst) - 1):
            (_, a0), (_, a1) = lst[j], lst[j + 1]
            if a1.start < a0.end:
                violations.append(
                    f"satellite {sid}: overlapping observations "
                    f"[{a0.start.isoformat()}, {a0.end.isoformat()}) and "
                    f"[{a1.start.isoformat()}, {a1.end.isoformat()})"
                )
            sd = satellites[sid]
            sf = sf_sats[sid]
            sp0, sv0 = _satellite_state_ecef_m(sf, a0.end)
            sp1, sv1 = _satellite_state_ecef_m(sf, a1.start)
            b0 = _boresight_unit_vector(
                sp0, sv0, a0.off_nadir_along_deg, a0.off_nadir_across_deg
            )
            b1 = _boresight_unit_vector(
                sp1, sv1, a1.off_nadir_along_deg, a1.off_nadir_across_deg
            )
            delta_deg = _angle_between_deg(b0, b1)
            gap = (a1.start - a0.end).total_seconds()
            need = sd.settling_time_s + _min_slew_time_s(delta_deg, sd)
            if gap + 1e-6 < need:
                violations.append(
                    f"satellite {sid}: insufficient slew/settle between observations "
                    f"(need ~{need:.3f}s, gap {gap:.3f}s, delta {delta_deg:.4f}deg)"
                )

    # Derived observations + access membership
    for k, act in enumerate(actions):
        prefix = f"actions[{k}]"
        if act.satellite_id not in satellites or act.target_id not in targets:
            continue
        sd = satellites[act.satellite_id]
        tg = targets[act.target_id]
        mid = act.start + (act.end - act.start) / 2
        sf = sf_sats[act.satellite_id]
        sp, sv = _satellite_state_ecef_m(sf, mid)
        te = target_ecef[act.target_id]
        epoch = _datetime_to_epoch(mid)
        el, saz = _solar_elevation_azimuth_deg(epoch, te)
        gp = _boresight_ground_intercept_ecef_m(
            sp,
            sv,
            act.off_nadir_along_deg,
            act.off_nadir_across_deg,
        )
        if gp is None:
            violations.append(f"{prefix}: boresight does not intersect the Earth ellipsoid")
            gp = te
        boresight_vec = gp - sp
        off = _angle_between_deg(-sp, boresight_vec)
        slant = float(np.linalg.norm(gp - sp))
        eff_px = slant * sd.pixel_ifov_deg * (math.pi / 180.0)
        access_key = (act.satellite_id, act.target_id)
        intervals = access_index.setdefault(access_key, [])
        aid = _assign_access_id(act.start, act.end, intervals)
        if aid is None:
            step_s = _access_interval_sampling_step_s(sd)
            if _access_holds_over_window(
                sf,
                tg,
                te,
                sd,
                mission,
                act.start,
                act.end,
                step_s=step_s,
            ):
                interval_start, interval_end = _discover_access_interval_around_action(
                    sf,
                    tg,
                    te,
                    sd,
                    mission,
                    mission.horizon_start,
                    mission.horizon_end,
                    act.start,
                    act.end,
                    step_s=step_s,
                )
                aid = _register_access_interval(
                    intervals,
                    act.satellite_id,
                    act.target_id,
                    interval_start,
                    interval_end,
                )
            else:
                aid = None
        if aid is None:
            violations.append(
                f"{prefix}: observation is not fully contained inside a continuous access interval"
            )
        derived_list.append(
            DerivedObservation(
                satellite_id=act.satellite_id,
                target_id=act.target_id,
                action_index=k,
                start_time=_iso_z(act.start),
                end_time=_iso_z(act.end),
                midpoint_time=_iso_z(mid),
                sat_position_ecef_m=sp.tolist(),
                sat_velocity_ecef_mps=sv.tolist(),
                boresight_off_nadir_deg=float(off),
                boresight_azimuth_deg=float(_boresight_azimuth_deg(te, gp)),
                solar_elevation_deg=float(el),
                solar_azimuth_deg=float(saz),
                effective_pixel_scale_m=float(eff_px),
                access_interval_id=aid or "none",
                slant_range_m=float(slant),
            )
        )

    # Stereo products (same target; same-satellite products remain same-pass, while
    # cross-satellite products are controlled by mission policy and temporal bound).
    derived_by_target: dict[str, list[tuple[int, DerivedObservation]]] = {}
    for d in derived_list:
        if d.access_interval_id == "none":
            continue
        derived_by_target.setdefault(d.target_id, []).append((d.action_index, d))

    pair_diagnostics: list[dict[str, Any]] = []

    per_target_best: dict[str, float] = {tid: 0.0 for tid in targets}
    covered: set[str] = set()

    for target_id, group in derived_by_target.items():
        tg = targets[target_id]
        te = target_ecef[target_id]
        obs_indices = [g[0] for g in group]
        ders = [g[1] for g in group]
        n = len(ders)
        # pairwise
        for i in range(n):
            for j in range(i + 1, n):
                di, dj = ders[i], ders[j]
                ai = actions[obs_indices[i]]
                aj = actions[obs_indices[j]]
                stereo_mode = _stereo_pair_mode(mission, ai, aj, di, dj)
                if stereo_mode is None:
                    continue
                pair_result = _evaluate_stereo_pair(
                    case_id=case_id,
                    mission=mission,
                    satellites=satellites,
                    targets=targets,
                    sf_sats=sf_sats,
                    target_ecef=target_ecef,
                    actions=actions,
                    first_index=obs_indices[i],
                    second_index=obs_indices[j],
                    first_derived=di,
                    second_derived=dj,
                    stereo_mode=stereo_mode,
                    n_samples=100,
                    role="pair_overlap",
                )
                pair_diagnostics.append(pair_result)
                if pair_result["valid_pair"]:
                    covered.add(target_id)
                    if pair_result["q_pair"] > per_target_best[target_id]:
                        per_target_best[target_id] = pair_result["q_pair"]

        # triples
        for i in range(n):
            for j in range(i + 1, n):
                for k in range(j + 1, n):
                    a0, a1, a2 = actions[obs_indices[i]], actions[obs_indices[j]], actions[obs_indices[k]]
                    d0, d1, d2 = ders[i], ders[j], ders[k]
                    edge_modes = [
                        _stereo_pair_mode(mission, a0, a1, d0, d1),
                        _stereo_pair_mode(mission, a0, a2, d0, d2),
                        _stereo_pair_mode(mission, a1, a2, d1, d2),
                    ]
                    if any(mode is None for mode in edge_modes):
                        continue
                    tri_ders = [d0, d1, d2]
                    tri_sat_defs = [satellites[d.satellite_id] for d in tri_ders]
                    tri_sf_sats = [sf_sats[d.satellite_id] for d in tri_ders]
                    polys = [
                        _strip_polyline_en(
                            tri_sf_sats[0],
                            te,
                            a0.start,
                            a0.end,
                            8.0,
                            off_nadir_along_deg=a0.off_nadir_along_deg,
                            off_nadir_across_deg=a0.off_nadir_across_deg,
                        ),
                        _strip_polyline_en(
                            tri_sf_sats[1],
                            te,
                            a1.start,
                            a1.end,
                            8.0,
                            off_nadir_along_deg=a1.off_nadir_along_deg,
                            off_nadir_across_deg=a1.off_nadir_across_deg,
                        ),
                        _strip_polyline_en(
                            tri_sf_sats[2],
                            te,
                            a2.start,
                            a2.end,
                            8.0,
                            off_nadir_along_deg=a2.off_nadir_along_deg,
                            off_nadir_across_deg=a2.off_nadir_across_deg,
                        ),
                    ]
                    hw = [
                        d0.slant_range_m * math.tan(math.radians(tri_sat_defs[0].half_cross_track_fov_deg)),
                        d1.slant_range_m * math.tan(math.radians(tri_sat_defs[1].half_cross_track_fov_deg)),
                        d2.slant_range_m * math.tan(math.radians(tri_sat_defs[2].half_cross_track_fov_deg)),
                    ]
                    wk_tri = tuple(
                        sorted(
                            (
                                _observation_window_key(a0),
                                _observation_window_key(a1),
                                _observation_window_key(a2),
                            )
                        )
                    )
                    satellite_label, access_label = _product_seed_labels(tri_ders)
                    rng_tri = _stereo_mc_rng(
                        case_id,
                        satellite_label,
                        target_id,
                        access_label,
                        window_keys=wk_tri,
                        n_samples=100,
                        role="tri_overlap",
                    )
                    o_tri = _monte_carlo_tri_overlap(
                        tg.aoi_radius_m, polys, hw, n_samples=100, rng=rng_tri
                    )
                    pair_flags = []
                    pair_qs = []
                    for edge_idx, (ix, jx) in enumerate(((i, j), (i, k), (j, k))):
                        di, dj = ders[ix], ders[jx]
                        ai, aj = actions[obs_indices[ix]], actions[obs_indices[jx]]
                        edge_result = _evaluate_stereo_pair(
                            case_id=case_id,
                            mission=mission,
                            satellites=satellites,
                            targets=targets,
                            sf_sats=sf_sats,
                            target_ecef=target_ecef,
                            actions=actions,
                            first_index=obs_indices[ix],
                            second_index=obs_indices[jx],
                            first_derived=di,
                            second_derived=dj,
                            stereo_mode=edge_modes[edge_idx] or "unknown",
                            n_samples=80,
                            role="tri_pair_edge",
                        )
                        pair_flags.append(bool(edge_result["valid_pair"]))
                        pair_qs.append(float(edge_result["q_pair"]))
                    anchor = any(
                        ders[ix].boresight_off_nadir_deg
                        <= mission.near_nadir_anchor_max_off_nadir_deg + 1e-6
                        for ix in (i, j, k)
                    )
                    tri_ok = (
                        o_tri + 1e-6 >= mission.min_overlap_fraction
                        and sum(1 for x in pair_flags if x) >= 2
                        and anchor
                    )
                    beta = mission.tri_stereo_bonus_by_scene[tg.scene_type]
                    tri_bonus_R = _tri_bonus_R(pair_flags, anchor)
                    q_tri = _tri_quality_from_valid_pairs(
                        pair_flags,
                        pair_qs,
                        beta=beta,
                        tri_bonus_R=tri_bonus_R,
                    )
                    if tri_ok:
                        covered.add(target_id)
                        if q_tri > per_target_best[target_id]:
                            per_target_best[target_id] = q_tri

    n_targets = len(targets)
    if n_targets == 0:
        violations.append(f"case {case_id}: targets.yaml defines no targets")
        coverage_ratio = 0.0
        normalized_quality = 0.0
    else:
        coverage_ratio = len(covered) / n_targets
        normalized_quality = sum(per_target_best[tid] for tid in targets) / n_targets

    valid = len(violations) == 0

    report = VerificationReport(
        valid=valid,
        metrics={
            "valid": valid,
            "coverage_ratio": float(coverage_ratio),
            "normalized_quality": float(normalized_quality),
        },
        violations=violations,
        derived_observations=[asdict(d) for d in derived_list],
        diagnostics={
            "pair_evaluations": pair_diagnostics,
            "per_target_best_score": {k: float(v) for k, v in per_target_best.items()},
        },
    )
    return report


def verify_solution_dict(case_dir: str | Path, solution_path: str | Path) -> dict[str, Any]:
    return verify_solution(case_dir, solution_path).to_dict()
