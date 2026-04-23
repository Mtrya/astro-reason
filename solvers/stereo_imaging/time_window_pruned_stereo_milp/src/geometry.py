"""Standalone geometry helpers using skyfield and brahe."""

from __future__ import annotations

import math
from datetime import UTC, datetime

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


def line_of_sight_clear(sat_pos_m: np.ndarray, target_pos_m: np.ndarray) -> bool:
    """Simplified LOS check: ray from sat to target hits ellipsoid at or before target."""
    los = target_pos_m - sat_pos_m
    dist = float(np.linalg.norm(los))
    if dist < _NUMERICAL_EPS:
        return True
    d = los / dist
    ox, oy, oz = (float(sat_pos_m[i]) for i in range(3))
    dx, dy, dz = (float(d[i]) for i in range(3))
    a2 = _WGS84_A_M * _WGS84_A_M
    b2 = _WGS84_B_M * _WGS84_B_M
    inv_a2 = 1.0 / a2
    inv_b2 = 1.0 / b2
    aa = (dx * dx + dy * dy) * inv_a2 + dz * dz * inv_b2
    bb = 2.0 * ((ox * dx + oy * dy) * inv_a2 + oz * dz * inv_b2)
    cc = (ox * ox + oy * oy) * inv_a2 + oz * oz * inv_b2 - 1.0
    disc = bb * bb - 4.0 * aa * cc
    if disc < 0.0 or abs(aa) < 1.0e-30:
        return False
    sqrt_disc = math.sqrt(disc)
    t1 = (-bb - sqrt_disc) / (2.0 * aa)
    t2 = (-bb + sqrt_disc) / (2.0 * aa)
    candidates = [t for t in (t1, t2) if t > _NUMERICAL_EPS]
    if not candidates:
        return False
    t_hit = min(candidates)
    tx, ty, tz = (float(target_pos_m[i]) for i in range(3))
    q = (tx * tx + ty * ty) * inv_a2 + tz * tz * inv_b2
    if q >= 1.0 - _NUMERICAL_EPS:
        return t_hit + 1.0 >= dist
    r_target = float(np.linalg.norm(target_pos_m))
    depth_m = r_target * (1.0 / math.sqrt(q) - 1.0)
    return t_hit + depth_m + 10.0 >= dist
