"""Computes satellite-to-target access windows using the Astrox API."""

from __future__ import annotations

import requests
from datetime import datetime
from typing import Iterable, List, Dict, Any, Optional, Union

from ..models import (
    Satellite,
    Target,
    Station,
    AccessWindow,
    AccessAERPoint,
    RangeConstraint,
    ElevationAngleConstraint,
)

ASTROX_API_URL = "http://astrox.cn:8765"


class AstroxAPIError(Exception):
    """Custom exception for Astrox API errors."""

    pass


Constraint = Union[RangeConstraint, ElevationAngleConstraint]
TargetLike = Union[Target, Station, Satellite]
StripPoints = List[tuple[float, float]]


def _serialize_constraint(constraint: Constraint) -> Dict[str, Any]:
    """Convert an engine constraint object into an Astrox IContraint JSON object."""

    if isinstance(constraint, RangeConstraint):
        return {
            "$type": "Range",
            "Text": None,
            "MinimumValue": constraint.minimum_km if constraint.minimum_km is not None else 0.0,
            "MaximumValue": constraint.maximum_km if constraint.maximum_km is not None else 1.0e20,
            "IsMaximumEnabled": constraint.enable_maximum,
        }
    if isinstance(constraint, ElevationAngleConstraint):
        return {
            "$type": "ElevationAngle",
            "Text": None,
            "MinimumValue": constraint.minimum_deg if constraint.minimum_deg is not None else 0.0,
            "MaximumValue": constraint.maximum_deg if constraint.maximum_deg is not None else 90.0,
            "IsMaximumEnabled": constraint.enable_maximum,
        }
    raise TypeError(f"Unsupported constraint type: {type(constraint)!r}")


def _build_access_payload(
    satellite: Satellite,
    target: TargetLike,
    start_time: str,
    end_time: str,
    constraints: Optional[Iterable[Constraint]] = None,
    compute_aer: bool = True,
) -> Dict[str, Any]:
    """Construct the JSON payload for the Astrox AccessComputeV2 endpoint."""

    if isinstance(target, Satellite):
        from_object: Dict[str, Any] = {
            "Name": "from_sat",
            "Position": {
                "$type": "SGP4",
                "TLEs": [target.tle_line1, target.tle_line2],
            },
        }
    else:
        from_object = {
            "Name": "from_site",
            "Position": {
                "$type": "SitePosition",
                "cartographicDegrees": [
                    target.longitude_deg,
                    target.latitude_deg,
                    target.altitude_m,
                ],
            },
        }

    payload: Dict[str, Any] = {
        "Start": start_time,
        "Stop": end_time,
        "FromObjectPath": from_object,
        "ToObjectPath": {
            "Name": "to_sat",
            "Position": {
                "$type": "SGP4",
                "TLEs": [satellite.tle_line1, satellite.tle_line2],
            },
        },
        "ComputeAER": compute_aer,
    }

    if constraints:
        from_object["Constraints"] = [
            _serialize_constraint(c) for c in constraints
        ]

    return payload


def _parse_aer_point(raw: Optional[Dict[str, Any]]) -> Optional[AccessAERPoint]:
    if not raw:
        return None
    time_str = raw.get("Time")
    if not time_str:
        return None
    time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
    return AccessAERPoint(
        time=time,
        azimuth_deg=raw["Azimuth"],
        elevation_deg=raw["Elevation"],
        range_m=raw["Range"],
    )


def compute_accessibility(
    satellite: Satellite,
    target: TargetLike,
    time_window: tuple[str, str],
    constraints: Optional[Iterable[Constraint]] = None,
) -> List[AccessWindow]:
    """
    Computes all access windows between a satellite and a target for a given time window.

    Args:
        satellite: The observing satellite with TLE data.
        target: The target object (Target, Station, or Satellite for ISL).
        time_window: A tuple containing the start and end time strings (ISO format with Z).

    Returns:
        A list of AccessWindow objects, each representing a period of visibility.
        For Satellite targets, only start/end/duration are populated (others None).

    Raises:
        AstroxAPIError: If the API call fails or returns an error.
        ValueError: If satellite and target are the same satellite (self-access).
    """
    is_satellite_target = isinstance(target, Satellite)

    if is_satellite_target:
        # TLE string comparison is brittle (whitespace, checksums can differ).
        # A more robust approach would compare orbital elements if possible.
        if satellite.tle_line1 == target.tle_line1 and satellite.tle_line2 == target.tle_line2:
            raise ValueError("Cannot compute self-access: satellite and target are the same")

    start_time, end_time = time_window
    payload = _build_access_payload(
        satellite,
        target,
        start_time,
        end_time,
        constraints=constraints,
        compute_aer=not is_satellite_target,
    )

    try:
        response = requests.post(
            f"{ASTROX_API_URL}/access/AccessComputeV2", json=payload, timeout=60
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise AstroxAPIError(f"Astrox API request failed: {e}") from e

    data = response.json()

    if not data.get("IsSuccess"):
        error_message = data.get("Message", "Unknown error")
        raise AstroxAPIError(f"Astrox API returned an error: {error_message}")

    windows: List[AccessWindow] = []
    for pass_data in data.get("Passes", []):
        start = datetime.fromisoformat(pass_data["AccessStart"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(pass_data["AccessStop"].replace("Z", "+00:00"))

        if is_satellite_target:
            windows.append(
                AccessWindow(
                    start=start,
                    end=end,
                    duration_sec=pass_data["Duration"],
                    max_elevation_deg=None,
                    max_elevation_point=None,
                    min_range_point=None,
                    mean_elevation_deg=None,
                    mean_range_m=None,
                    aer_samples=None,
                )
            )
        else:
            max_elevation = pass_data.get("MaxElevationData", {}).get("Elevation")
            max_el_point = _parse_aer_point(pass_data.get("MaxElevationData"))
            min_range_point = _parse_aer_point(pass_data.get("MinRangeData"))

            all_datas = pass_data.get("AllDatas") or []
            samples: list[AccessAERPoint] = []
            mean_elevation_deg: Optional[float] = None
            mean_range_m: Optional[float] = None

            if all_datas:
                for p in all_datas:
                    pt = _parse_aer_point(p)
                    if pt is not None:
                        samples.append(pt)

                if samples:
                    elevations = [float(p.elevation_deg) for p in samples]
                    ranges_m = [float(p.range_m) for p in samples]
                    mean_elevation_deg = sum(elevations) / len(elevations)
                    mean_range_m = sum(ranges_m) / len(ranges_m)

            windows.append(
                AccessWindow(
                    start=start,
                    end=end,
                    duration_sec=pass_data["Duration"],
                    max_elevation_deg=max_elevation,
                    max_elevation_point=max_el_point,
                    min_range_point=min_range_point,
                    mean_elevation_deg=mean_elevation_deg,
                    mean_range_m=mean_range_m,
                    aer_samples=samples or None,
                )
            )

    return windows


def _interpolate_polyline(points: StripPoints, num_samples: int) -> StripPoints:
    """
    Interpolate a polyline into evenly-spaced sample points along its arc-length.
    Uses simple linear interpolation (good enough for geodesic approximation at km scale).
    """
    import math

    if num_samples < 2:
        return points
    if len(points) < 2:
        return points

    segment_lengths = []
    for i in range(len(points) - 1):
        lat1, lon1 = points[i]
        lat2, lon2 = points[i + 1]
        dist = math.sqrt((lat2 - lat1) ** 2 + (lon2 - lon1) ** 2)
        segment_lengths.append(dist)

    total_length = sum(segment_lengths)
    if total_length == 0:
        return [points[0]] * num_samples

    cumulative = [0.0]
    for seg_len in segment_lengths:
        cumulative.append(cumulative[-1] + seg_len)

    samples: StripPoints = []
    for i in range(num_samples):
        t = i / (num_samples - 1)
        target_dist = t * total_length

        seg_idx = 0
        for j in range(len(cumulative) - 1):
            if cumulative[j] <= target_dist <= cumulative[j + 1]:
                seg_idx = j
                break

        seg_start_dist = cumulative[seg_idx]
        seg_len = segment_lengths[seg_idx]
        if seg_len > 0:
            seg_t = (target_dist - seg_start_dist) / seg_len
        else:
            seg_t = 0.0

        lat1, lon1 = points[seg_idx]
        lat2, lon2 = points[seg_idx + 1]
        lat = lat1 + seg_t * (lat2 - lat1)
        lon = lon1 + seg_t * (lon2 - lon1)
        samples.append((lat, lon))

    return samples


def _find_candidate_passes(
    head_windows: List[AccessWindow],
    tail_windows: List[AccessWindow],
    max_gap_seconds: float = 600.0,
) -> List[tuple[AccessWindow, AccessWindow, str]]:
    """
    Match head/tail windows that belong to the same satellite pass.
    Returns list of (head_window, tail_window, direction).
    Direction is 'forward' if head is visible before tail, 'backward' otherwise.
    """
    from datetime import timedelta

    candidates: List[tuple[AccessWindow, AccessWindow, str]] = []
    max_gap = timedelta(seconds=max_gap_seconds)

    for hw in head_windows:
        for tw in tail_windows:
            overlap_start = max(hw.start, tw.start)
            overlap_end = min(hw.end, tw.end)

            if overlap_start <= overlap_end:
                if hw.start <= tw.start:
                    candidates.append((hw, tw, "forward"))
                else:
                    candidates.append((hw, tw, "backward"))
            else:
                gap = overlap_start - overlap_end
                if gap <= max_gap:
                    if hw.start <= tw.start:
                        candidates.append((hw, tw, "forward"))
                    else:
                        candidates.append((hw, tw, "backward"))

    return candidates


def _validate_sweep(
    sample_windows: List[List[AccessWindow]],
    direction: str,
) -> AccessWindow | None:
    """
    Check if a monotonic sweep exists across all sample points.
    Returns an AccessWindow if valid, None otherwise.
    """
    K = len(sample_windows)
    if K < 2:
        return None

    if direction == "backward":
        sample_windows = sample_windows[::-1]

    first_windows = []
    for ws in sample_windows:
        if not ws:
            return None
        first_windows.append(ws[0])

    first_visible = [w.start for w in first_windows]
    last_visible = [w.end for w in first_windows]

    strip_start = first_visible[0]
    strip_end = last_visible[-1]

    if strip_start >= strip_end:
        return None

    for i in range(K):
        t_i = strip_start + (i / (K - 1)) * (strip_end - strip_start)
        if not (first_visible[i] <= t_i <= last_visible[i]):
            return None

    return AccessWindow(
        start=strip_start,
        end=strip_end,
        duration_sec=(strip_end - strip_start).total_seconds(),
        max_elevation_deg=None,
        max_elevation_point=None,
        min_range_point=None,
        mean_elevation_deg=None,
        mean_range_m=None,
        aer_samples=None,
    )


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points on the earth."""
    from math import radians, sin, cos, sqrt, atan2

    R = 6371.0  # Earth radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c


def compute_strip_accessibility(
    satellite: Satellite,
    strip_points: StripPoints,
    time_window: tuple[str, str],
    num_samples: Optional[int] = None,
    constraints: Optional[Iterable[Constraint]] = None,
) -> List[AccessWindow]:
    """
    Compute access windows for a strip target (polyline).

    A valid strip window means the satellite can continuously "sweep" along the strip:
    at window.start, the strip head is visible; at window.end, the strip tail is visible;
    and all intermediate points are visible at their proportional times.

    Algorithm:
      1. Compute windows for strip head and tail
      2. Identify candidate passes (head/tail windows that overlap or are close)
      3. For each candidate, sample intermediate points and validate the sweep

    Args:
        satellite: The observing satellite.
        strip_points: List of (lat, lon) points defining the strip.
        time_window: (start_iso, end_iso) tuple.
        num_samples: Number of points to sample along the strip. 
                     If None, calculated as length_km / 75.0 (min 2).
        constraints: Optional constraints (range, elevation).
    
    Returns:
        List of AccessWindow objects.
    """
    if len(strip_points) < 2:
        raise ValueError("Strip must have at least 2 points")

    head = Target(latitude_deg=strip_points[0][0], longitude_deg=strip_points[0][1])
    tail = Target(latitude_deg=strip_points[-1][0], longitude_deg=strip_points[-1][1])

    head_windows = compute_accessibility(satellite, head, time_window, constraints)
    tail_windows = compute_accessibility(satellite, tail, time_window, constraints)

    if not head_windows or not tail_windows:
        return []

    candidates = _find_candidate_passes(head_windows, tail_windows)
    if not candidates:
        return []

    # Calculate num_samples based on distance if not provided
    if num_samples is None:
        total_dist_km = 0.0
        for i in range(len(strip_points) - 1):
            p1 = strip_points[i]
            p2 = strip_points[i + 1]
            total_dist_km += _haversine_distance_km(p1[0], p1[1], p2[0], p2[1])
        
        # 1 sample per 500km, but at least 2 points (start/end)
        # Note: _interpolate_polyline treats samples as total points including ends
        num_samples = int(total_dist_km / 500.0)
        if num_samples < 2:
            num_samples = 2

    samples = _interpolate_polyline(strip_points, num_samples)

    valid_strip_windows: List[AccessWindow] = []
    for head_win, tail_win, direction in candidates:
        pass_start = min(head_win.start, tail_win.start)
        pass_end = max(head_win.end, tail_win.end)
        pass_time_window = (
            pass_start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            pass_end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        )

        sample_windows: List[List[AccessWindow]] = []
        for lat, lon in samples:
            t = Target(latitude_deg=lat, longitude_deg=lon)
            ws = compute_accessibility(satellite, t, pass_time_window, constraints)
            sample_windows.append(ws)

        strip_window = _validate_sweep(sample_windows, direction)
        if strip_window:
            valid_strip_windows.append(strip_window)

    return valid_strip_windows
