"""Solver-local approximate strip geometry for coverage indexing.

This module intentionally does not reproduce verifier internals. It builds a
deterministic circular-orbit ground-track approximation from public TLE fields
and uses it only to map candidates to coverage-grid sample indices for later
CELF selection.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import brahe
import numpy as np

from case_io import Manifest, Satellite
from candidates import StripCandidate

EARTH_RADIUS_M = 6_378_137.0
EARTH_ROTATION_RAD_PER_S = 7.2921159e-5
MU_EARTH_M3_PER_S2 = 3.986004418e14
WGS84_A_M = 6_378_137.0
WGS84_B_M = 6_356_752.314245179
NUMERICAL_EPS = 1.0e-12
_BRAHE_READY = False


class PropagationContext:
    def __init__(self, satellites: dict[str, Satellite], step_s: float):
        ensure_brahe_ready()
        self.propagators = {
            satellite_id: brahe.SGPPropagator.from_tle(
                satellite.tle_line1,
                satellite.tle_line2,
                step_s,
            )
            for satellite_id, satellite in satellites.items()
        }
        self._state_ecef_cache: dict[tuple[str, datetime], np.ndarray] = {}
        self._ground_intercept_lonlat_cache: dict[
            tuple[str, datetime, float], tuple[float, float] | None
        ] = {}

    def state_ecef(self, satellite_id: str, instant: datetime) -> np.ndarray:
        key = (satellite_id, instant.astimezone(UTC))
        cached = self._state_ecef_cache.get(key)
        if cached is not None:
            return cached
        state = np.asarray(
            self.propagators[satellite_id].state_ecef(datetime_to_epoch(key[1])),
            dtype=float,
        ).reshape(6)
        self._state_ecef_cache[key] = state
        return state

    def ground_intercept_lonlat(
        self,
        satellite_id: str,
        instant: datetime,
        roll_deg: float,
    ) -> tuple[float, float] | None:
        key = (
            satellite_id,
            instant.astimezone(UTC),
            round(float(roll_deg), 9),
        )
        if key in self._ground_intercept_lonlat_cache:
            return self._ground_intercept_lonlat_cache[key]
        state_ecef = self.state_ecef(satellite_id, key[1])
        hit = _ground_intercept_ecef_m(state_ecef[:3], state_ecef[3:], roll_deg)
        lonlat = None if hit is None else _ecef_to_lonlat_deg(hit)
        self._ground_intercept_lonlat_cache[key] = lonlat
        return lonlat


def ensure_brahe_ready() -> None:
    global _BRAHE_READY
    if _BRAHE_READY:
        return
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    _BRAHE_READY = True


def datetime_to_epoch(value: datetime) -> brahe.Epoch:
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


def _deg(value: float) -> float:
    return math.degrees(value)


def _rad(value: float) -> float:
    return math.radians(value)


def wrap_longitude_deg(value: float) -> float:
    wrapped = (value + 180.0) % 360.0 - 180.0
    return 180.0 if wrapped == -180.0 else wrapped


def destination_point(
    lon_deg: float, lat_deg: float, bearing_deg: float, distance_m: float
) -> tuple[float, float]:
    angular = distance_m / EARTH_RADIUS_M
    lat1 = _rad(lat_deg)
    lon1 = _rad(lon_deg)
    bearing = _rad(bearing_deg)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular)
        + math.cos(lat1) * math.sin(angular) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    return (wrap_longitude_deg(_deg(lon2)), _deg(lat2))


def haversine_m(lon_a: float, lat_a: float, lon_b: float, lat_b: float) -> float:
    d_lat = _rad(lat_b - lat_a)
    d_lon = _rad(wrap_longitude_deg(lon_b - lon_a))
    lat1 = _rad(lat_a)
    lat2 = _rad(lat_b)
    h = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def bearing_deg(lon_a: float, lat_a: float, lon_b: float, lat_b: float) -> float:
    lat1 = _rad(lat_a)
    lat2 = _rad(lat_b)
    d_lon = _rad(wrap_longitude_deg(lon_b - lon_a))
    y = math.sin(d_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    return (_deg(math.atan2(y, x)) + 360.0) % 360.0


def _satellite_local_axes(
    sat_pos_m: np.ndarray, sat_vel_mps: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nadir = -sat_pos_m / np.linalg.norm(sat_pos_m)
    along = sat_vel_mps - float(np.dot(sat_vel_mps, nadir)) * nadir
    if float(np.linalg.norm(along)) <= NUMERICAL_EPS:
        fallback = np.array([0.0, 0.0, 1.0])
        if abs(float(np.dot(fallback, nadir))) > 0.9:
            fallback = np.array([0.0, 1.0, 0.0])
        along = fallback - float(np.dot(fallback, nadir)) * nadir
    along = along / np.linalg.norm(along)
    across = np.cross(along, nadir)
    if float(np.linalg.norm(across)) <= NUMERICAL_EPS:
        across = np.array([1.0, 0.0, 0.0], dtype=float)
    else:
        across = across / np.linalg.norm(across)
    return along, across, nadir


def _boresight_unit_vector(
    sat_pos_m: np.ndarray, sat_vel_mps: np.ndarray, roll_deg: float
) -> np.ndarray:
    _, across_hat, nadir_hat = _satellite_local_axes(sat_pos_m, sat_vel_mps)
    vector = nadir_hat + (math.tan(_rad(float(roll_deg))) * across_hat)
    return vector / np.linalg.norm(vector)


def _ray_ellipsoid_intersection_m(
    origin_m: np.ndarray, direction_unit: np.ndarray
) -> float | None:
    ox, oy, oz = (float(origin_m[index]) for index in range(3))
    dx, dy, dz = (float(direction_unit[index]) for index in range(3))
    inv_a2 = 1.0 / (WGS84_A_M * WGS84_A_M)
    inv_b2 = 1.0 / (WGS84_B_M * WGS84_B_M)
    aa = ((dx * dx) + (dy * dy)) * inv_a2 + (dz * dz) * inv_b2
    bb = 2.0 * (((ox * dx) + (oy * dy)) * inv_a2 + (oz * dz) * inv_b2)
    cc = ((ox * ox) + (oy * oy)) * inv_a2 + (oz * oz) * inv_b2 - 1.0
    disc = (bb * bb) - (4.0 * aa * cc)
    if disc < 0.0 or abs(aa) < 1.0e-30:
        return None
    sqrt_disc = math.sqrt(disc)
    roots = (
        (-bb - sqrt_disc) / (2.0 * aa),
        (-bb + sqrt_disc) / (2.0 * aa),
    )
    positive_roots = [root for root in roots if root > NUMERICAL_EPS]
    if not positive_roots:
        return None
    return min(positive_roots)


def _ground_intercept_ecef_m(
    sat_pos_m: np.ndarray, sat_vel_mps: np.ndarray, roll_deg: float
) -> np.ndarray | None:
    direction = _boresight_unit_vector(sat_pos_m, sat_vel_mps, roll_deg)
    distance_m = _ray_ellipsoid_intersection_m(sat_pos_m, direction)
    if distance_m is None:
        return None
    return sat_pos_m + (distance_m * direction)


def _ecef_to_lonlat_deg(ecef_position_m: np.ndarray) -> tuple[float, float]:
    lon_deg, lat_deg, _ = brahe.position_ecef_to_geodetic(
        ecef_position_m,
        brahe.AngleFormat.DEGREES,
    )
    return (float(lon_deg), float(lat_deg))


def _tle_line2_elements(line2: str) -> tuple[float, float, float, float, float]:
    inclination_deg = float(line2[8:16])
    raan_deg = float(line2[17:25])
    arg_perigee_deg = float(line2[34:42])
    mean_anomaly_deg = float(line2[43:51])
    mean_motion_rev_per_day = float(line2[52:63])
    return (
        inclination_deg,
        raan_deg,
        arg_perigee_deg,
        mean_anomaly_deg,
        mean_motion_rev_per_day,
    )


def _subpoint_from_circular_tle(
    satellite: Satellite, at_time: datetime
) -> tuple[float, float, float]:
    inc_deg, raan_deg, argp_deg, mean_anomaly_deg, mean_motion = _tle_line2_elements(
        satellite.tle_line2
    )
    n_rad_s = mean_motion * 2.0 * math.pi / 86400.0
    semi_major_m = (MU_EARTH_M3_PER_S2 / (n_rad_s * n_rad_s)) ** (1.0 / 3.0)
    altitude_m = max(100_000.0, semi_major_m - EARTH_RADIUS_M)
    elapsed_s = (at_time - satellite.tle_epoch).total_seconds()
    u = _rad(argp_deg + mean_anomaly_deg) + n_rad_s * elapsed_s
    inc = _rad(inc_deg)
    raan = _rad(raan_deg)
    x = math.cos(raan) * math.cos(u) - math.sin(raan) * math.sin(u) * math.cos(inc)
    y = math.sin(raan) * math.cos(u) + math.cos(raan) * math.sin(u) * math.cos(inc)
    z = math.sin(u) * math.sin(inc)
    lon = _deg(math.atan2(y, x) - EARTH_ROTATION_RAD_PER_S * elapsed_s)
    lat = _deg(math.asin(max(-1.0, min(1.0, z))))
    return (wrap_longitude_deg(lon), lat, altitude_m)


def strip_centerline_lon_lat(
    manifest: Manifest,
    satellite: Satellite,
    candidate: StripCandidate,
    context: PropagationContext | None = None,
) -> tuple[tuple[float, float], ...]:
    centerline, _ = strip_centerline_and_half_width_m(
        manifest,
        satellite,
        candidate,
        context=context,
    )
    return centerline


def strip_centerline_and_half_width_m(
    manifest: Manifest,
    satellite: Satellite,
    candidate: StripCandidate,
    context: PropagationContext | None = None,
) -> tuple[tuple[tuple[float, float], ...], float]:
    start = manifest.horizon_start + timedelta(seconds=candidate.start_offset_s)
    sample_step_s = max(1, manifest.coverage_sample_step_s)
    offsets = list(range(0, candidate.duration_s + 1, sample_step_s))
    if offsets[-1] != candidate.duration_s:
        offsets.append(candidate.duration_s)
    if context is None:
        context = PropagationContext(
            {candidate.satellite_id: satellite},
            step_s=float(sample_step_s),
        )
    signed_inner = math.copysign(candidate.theta_inner_deg, candidate.roll_deg)
    signed_outer = math.copysign(candidate.theta_outer_deg, candidate.roll_deg)
    centerline: list[tuple[float, float]] = []
    half_widths_m: list[float] = []
    for offset_s in offsets:
        instant = start + timedelta(seconds=offset_s)
        center_lonlat = context.ground_intercept_lonlat(
            candidate.satellite_id,
            instant,
            candidate.roll_deg,
        )
        inner_lonlat = context.ground_intercept_lonlat(
            candidate.satellite_id,
            instant,
            signed_inner,
        )
        outer_lonlat = context.ground_intercept_lonlat(
            candidate.satellite_id,
            instant,
            signed_outer,
        )
        if center_lonlat is None or inner_lonlat is None or outer_lonlat is None:
            return ((), 0.0)
        centerline.append(center_lonlat)
        inner_lon, inner_lat = inner_lonlat
        outer_lon, outer_lat = outer_lonlat
        half_widths_m.append(
            0.5 * haversine_m(inner_lon, inner_lat, outer_lon, outer_lat)
        )
    return (tuple(centerline), max(half_widths_m) if half_widths_m else 0.0)


def approximate_half_width_m(
    satellite: Satellite,
    candidate: StripCandidate,
    manifest: Manifest | None = None,
    context: PropagationContext | None = None,
) -> float:
    if manifest is not None:
        _, half_width_m = strip_centerline_and_half_width_m(
            manifest,
            satellite,
            candidate,
            context=context,
        )
        return max(1.0, half_width_m)
    _, _, altitude_m = _subpoint_from_circular_tle(
        satellite,
        satellite.tle_epoch,
    )
    inner = math.tan(_rad(candidate.theta_inner_deg))
    outer = math.tan(_rad(candidate.theta_outer_deg))
    return max(1.0, 0.5 * altitude_m * max(0.0, outer - inner))
