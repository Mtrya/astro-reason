"""Solver-local approximate strip geometry for Phase 1 coverage indexing.

This module intentionally does not reproduce verifier internals. It builds a
deterministic circular-orbit ground-track approximation from public TLE fields
and uses it only to map candidates to coverage-grid sample indices for later
selection scaffolding.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from case_io import Manifest, Satellite
from candidates import StripCandidate

EARTH_RADIUS_M = 6_378_137.0
EARTH_ROTATION_RAD_PER_S = 7.2921159e-5
MU_EARTH_M3_PER_S2 = 3.986004418e14


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
    manifest: Manifest, satellite: Satellite, candidate: StripCandidate
) -> tuple[tuple[float, float], ...]:
    start = manifest.horizon_start + timedelta(seconds=candidate.start_offset_s)
    sample_step_s = max(1, manifest.coverage_sample_step_s)
    offsets = list(range(0, candidate.duration_s + 1, sample_step_s))
    if offsets[-1] != candidate.duration_s:
        offsets.append(candidate.duration_s)
    ground_points = [
        _subpoint_from_circular_tle(satellite, start + timedelta(seconds=offset_s))
        for offset_s in offsets
    ]
    centerline: list[tuple[float, float]] = []
    for index, (lon, lat, altitude_m) in enumerate(ground_points):
        if len(ground_points) == 1:
            heading = 0.0
        elif index == len(ground_points) - 1:
            prev_lon, prev_lat, _ = ground_points[index - 1]
            heading = bearing_deg(prev_lon, prev_lat, lon, lat)
        else:
            next_lon, next_lat, _ = ground_points[index + 1]
            heading = bearing_deg(lon, lat, next_lon, next_lat)
        look_bearing = heading + (90.0 if candidate.roll_deg >= 0.0 else -90.0)
        center_offset_m = altitude_m * math.tan(_rad(abs(candidate.roll_deg)))
        centerline.append(destination_point(lon, lat, look_bearing, center_offset_m))
    return tuple(centerline)


def approximate_half_width_m(satellite: Satellite, candidate: StripCandidate) -> float:
    # Use mean altitude over the action start as a stable local scale estimate.
    _, _, altitude_m = _subpoint_from_circular_tle(
        satellite, satellite.tle_epoch
    )
    inner = math.tan(_rad(candidate.theta_inner_deg))
    outer = math.tan(_rad(candidate.theta_outer_deg))
    return max(1.0, 0.5 * altitude_m * max(0.0, outer - inner))
