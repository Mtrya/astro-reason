"""Small standalone geometry helpers for deterministic strip candidates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from skyfield.api import EarthSatellite, load, wgs84


EARTH_RADIUS_M = 6_371_000.0
_TS = load.timescale()


@dataclass(frozen=True, slots=True)
class GroundPoint:
    latitude_deg: float
    longitude_deg: float
    altitude_m: float


def satellite_subpoint(satellite: EarthSatellite, instant: datetime) -> GroundPoint:
    geocentric = satellite.at(_TS.from_datetime(instant))
    subpoint = wgs84.subpoint(geocentric)
    return GroundPoint(
        latitude_deg=float(subpoint.latitude.degrees),
        longitude_deg=wrap_lon_deg(float(subpoint.longitude.degrees)),
        altitude_m=float(subpoint.elevation.m),
    )


def initial_bearing_deg(
    lat1_deg: float,
    lon1_deg: float,
    lat2_deg: float,
    lon2_deg: float,
) -> float:
    lat1 = math.radians(lat1_deg)
    lat2 = math.radians(lat2_deg)
    dlon = math.radians(lon2_deg - lon1_deg)
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def haversine_m(
    lat1_deg: float,
    lon1_deg: float,
    lat2_deg: float,
    lon2_deg: float,
) -> float:
    lat1 = math.radians(lat1_deg)
    lat2 = math.radians(lat2_deg)
    dlat = lat2 - lat1
    dlon = math.radians(lon2_deg - lon1_deg)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def destination_point(
    lat_deg: float,
    lon_deg: float,
    bearing_deg: float,
    distance_m: float,
) -> tuple[float, float]:
    lat1 = math.radians(lat_deg)
    lon1 = math.radians(lon_deg)
    bearing = math.radians(bearing_deg)
    angular = distance_m / EARTH_RADIUS_M
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular)
        + math.cos(lat1) * math.sin(angular) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), wrap_lon_deg(math.degrees(lon2))


def local_tangent_offsets_m(
    origin_lat_deg: float,
    origin_lon_deg: float,
    sample_lat_deg: float,
    sample_lon_deg: float,
) -> tuple[float, float]:
    lat0 = math.radians(origin_lat_deg)
    north_m = math.radians(sample_lat_deg - origin_lat_deg) * EARTH_RADIUS_M
    east_m = math.radians(sample_lon_deg - origin_lon_deg) * EARTH_RADIUS_M * math.cos(lat0)
    return east_m, north_m


def oriented_offsets_m(
    origin_lat_deg: float,
    origin_lon_deg: float,
    sample_lat_deg: float,
    sample_lon_deg: float,
    heading_deg: float,
) -> tuple[float, float]:
    east_m, north_m = local_tangent_offsets_m(origin_lat_deg, origin_lon_deg, sample_lat_deg, sample_lon_deg)
    heading_rad = math.radians(heading_deg)
    along_unit_e = math.sin(heading_rad)
    along_unit_n = math.cos(heading_rad)
    cross_unit_e = math.sin(heading_rad + math.pi / 2.0)
    cross_unit_n = math.cos(heading_rad + math.pi / 2.0)
    along_m = east_m * along_unit_e + north_m * along_unit_n
    cross_m = east_m * cross_unit_e + north_m * cross_unit_n
    return along_m, cross_m


def roll_ground_range_m(altitude_m: float, roll_abs_deg: float) -> float:
    return max(0.0, altitude_m) * math.tan(math.radians(roll_abs_deg))


def swath_width_m(altitude_m: float, roll_abs_deg: float, fov_deg: float) -> float:
    inner = max(0.0, roll_abs_deg - 0.5 * fov_deg)
    outer = roll_abs_deg + 0.5 * fov_deg
    return max(0.0, altitude_m) * (
        math.tan(math.radians(outer)) - math.tan(math.radians(inner))
    )


def wrap_lon_deg(value: float) -> float:
    return ((value + 180.0) % 360.0) - 180.0

