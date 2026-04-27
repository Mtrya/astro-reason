"""Link feasibility geometry checks compatible with the verifier."""

from __future__ import annotations

import brahe
import numpy as np

EARTH_RADIUS_M = float(brahe.R_EARTH)
NUMERICAL_EPS = 1e-9


def _segment_clear_of_earth(point_a_m: np.ndarray, point_b_m: np.ndarray) -> bool:
    """Return True if the segment between two points is not Earth-blocked.

    Matches verifier logic: closest point on segment to origin must be > R_EARTH + 1m.
    """
    segment = point_b_m - point_a_m
    denom = float(np.dot(segment, segment))
    if denom <= NUMERICAL_EPS:
        return float(np.linalg.norm(point_a_m)) > EARTH_RADIUS_M
    t = float(-np.dot(point_a_m, segment) / denom)
    t = max(0.0, min(1.0, t))
    closest = point_a_m + (t * segment)
    return float(np.linalg.norm(closest)) > EARTH_RADIUS_M + 1.0


def ground_link_feasible(
    endpoint_ecef_m: tuple[float, float, float],
    satellite_ecef_m: np.ndarray,
    min_elevation_deg: float,
    max_ground_range_m: float | None = None,
) -> tuple[bool, float]:
    """Check ground link feasibility. Returns (is_feasible, slant_range_m)."""
    endpoint_arr = np.array(endpoint_ecef_m, dtype=float)
    sat_arr = np.asarray(satellite_ecef_m, dtype=float)
    relative_enz = np.asarray(
        brahe.relative_position_ecef_to_enz(
            endpoint_arr,
            sat_arr,
            brahe.EllipsoidalConversionType.GEODETIC,
        ),
        dtype=float,
    )
    azel = np.asarray(
        brahe.position_enz_to_azel(relative_enz, brahe.AngleFormat.DEGREES),
        dtype=float,
    )
    elevation_deg = float(azel[1])
    slant_range_m = float(azel[2])
    if elevation_deg < min_elevation_deg:
        return False, slant_range_m
    if max_ground_range_m is not None and slant_range_m > max_ground_range_m:
        return False, slant_range_m
    return True, slant_range_m


def isl_feasible(
    position_a_ecef_m: np.ndarray,
    position_b_ecef_m: np.ndarray,
    max_isl_range_m: float,
) -> tuple[bool, float]:
    """Check ISL feasibility. Returns (is_feasible, distance_m)."""
    pos_a = np.asarray(position_a_ecef_m, dtype=float)
    pos_b = np.asarray(position_b_ecef_m, dtype=float)
    distance_m = float(np.linalg.norm(pos_b - pos_a))
    if distance_m > max_isl_range_m:
        return False, distance_m
    return _segment_clear_of_earth(pos_a, pos_b), distance_m
