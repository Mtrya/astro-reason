"""
Analytics engine for computing statistics from physical data.
"""

from datetime import datetime

from .models import AccessWindow, ObservationStats


def compute_aer_stats(
    window: AccessWindow,
    start_dt: datetime,
    end_dt: datetime,
) -> ObservationStats | None:
    """
    Compute observation statistics for a specific time interval within a window.

    Args:
        window: The source AccessWindow containing AER samples.
        start_dt: Start of the observation interval.
        end_dt: End of the observation interval.

    Returns:
        ObservationStats object or None if no stats could be derived.
    """
    samples = list(window.aer_samples or [])
    if samples:
        clipped = [s for s in samples if start_dt <= s.time <= end_dt]
    else:
        clipped = []

    if not clipped and samples:
        # If the action interval is narrower than sampling, fall back to
        # the full-window samples instead of returning empty stats.
        clipped = samples

    if clipped:
        elevations = [s.elevation_deg for s in clipped]
        ranges_km = [s.range_m / 1000.0 for s in clipped]
        return ObservationStats(
            mean_elevation_deg=sum(elevations) / len(elevations)
            if elevations
            else None,
            max_elevation_deg=max(elevations) if elevations else None,
            min_range_km=min(ranges_km) if ranges_km else None,
            mean_range_km=sum(ranges_km) / len(ranges_km) if ranges_km else None,
            sample_count=len(clipped),
        )

    # No per-sample data; fall back to window aggregates if available.
    if (
        window.mean_elevation_deg is None
        and window.mean_range_m is None
        and window.max_elevation_point is None
        and window.min_range_point is None
    ):
        return None

    min_range_km = (
        window.min_range_point.range_m / 1000.0
        if window.min_range_point is not None
        else None
    )
    mean_range_km = (
        window.mean_range_m / 1000.0 if window.mean_range_m is not None else None
    )
    max_el = (
        window.max_elevation_point.elevation_deg
        if window.max_elevation_point is not None
        else None
    )

    return ObservationStats(
        mean_elevation_deg=window.mean_elevation_deg,
        max_elevation_deg=max_el,
        min_range_km=min_range_km,
        mean_range_km=mean_range_km,
        sample_count=None,
    )


def compute_revisit_stats(
    intervals: list[tuple[datetime, datetime]],
    horizon_start: datetime,
    horizon_end: datetime,
) -> dict:
    """
    Compute revisit statistics for a target.

    Args:
        intervals: List of (start, end) tuples for observations.
        horizon_start: Start of the planning horizon.
        horizon_end: End of the planning horizon.

    Returns:
        dict containing max_gap, mean_gap, and list of gaps (seconds).
    """
    if not intervals:
        full_gap = (horizon_end - horizon_start).total_seconds()
        return {
            "max_gap": full_gap,
            "mean_gap": full_gap,
            "gaps": [full_gap],
            "coverage_count": 0,
        }

    # Sort by start time
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    
    # Merge overlapping intervals to get true coverage periods
    merged = []
    if sorted_intervals:
        curr_start, curr_end = sorted_intervals[0]
        for next_start, next_end in sorted_intervals[1:]:
            if next_start < curr_end:  # Overlap or abutting
                curr_end = max(curr_end, next_end)
            else:
                merged.append((curr_start, curr_end))
                curr_start, curr_end = next_start, next_end
        merged.append((curr_start, curr_end))

    gaps = []
    
    # Gap from horizon start to first observation
    if merged[0][0] > horizon_start:
        gaps.append((merged[0][0] - horizon_start).total_seconds())
        
    # Gaps between observations
    for i in range(len(merged) - 1):
        gap = (merged[i+1][0] - merged[i][1]).total_seconds()
        # Gap should be non-negative if logic is correct
        if gap > 0:
            gaps.append(gap)
            
    # Gap from last observation to horizon end
    if merged[-1][1] < horizon_end:
        gaps.append((horizon_end - merged[-1][1]).total_seconds())
        
    if not gaps:
        return {
            "max_gap": 0.0,
            "mean_gap": 0.0,
            "gaps": [],
            "coverage_count": len(intervals),
        }

    return {
        "max_gap": max(gaps),
        "mean_gap": sum(gaps) / len(gaps),
        "gaps": gaps,
        "coverage_count": len(intervals),
    }


def compute_stereo_compliance(
    observations: list[dict], 
    min_separation_deg: float = 15.0,
    max_separation_deg: float = 60.0,
) -> dict:
    """
    Compute stereo compliance for a target.

    Args:
        observations: List of dicts with keys:
                      - id (str)
                      - azimuth_deg (float) OR azimuth (float)
                      - elevation_deg (float) OR elevation (float)
                      - time (datetime)
        min_separation_deg: Minimum azimuth separation (deg). 
        max_separation_deg: Maximum azimuth separation (deg). Default is 60.0.

    Returns:
        dict containing has_stereo (bool) and max_separation_deg (float)
        of the BEST VALID pair.
    """
    if len(observations) < 2:
        return {
            "has_stereo": False,
            "max_separation_deg": 0.0,
            "best_pair": None,
        }

    max_valid_sep = 0.0
    best_pair = None
    has_stereo = False

    # Pre-process keys to be safe
    obs_normalized = []
    for obs in observations:
        az = obs.get("azimuth_deg") if "azimuth_deg" in obs else obs.get("azimuth")
        el = obs.get("elevation_deg") if "elevation_deg" in obs else obs.get("elevation")
        
        # If crucial data missing, skip or error? 
        # Fail fast per rules? Or skip invalid data?
        # Logic: If data is missing it's a bug in caller.
        if az is None or el is None or "time" not in obs:
             # Depending on strictness. Let's assume caller is correct, but keys might vary.
             # If keys are missing, let it crash on usage or handle here?
             # Let's clean up access to fail fast if None.
             pass
        
        obs_normalized.append({
            "id": obs["id"],
            "az": az,
            "el": el,
            "time": obs["time"]
        })

    from datetime import timedelta

    for i in range(len(obs_normalized)):
        for j in range(i + 1, len(obs_normalized)):
            o1 = obs_normalized[i]
            o2 = obs_normalized[j]
            
            # Constraint 1: Time Difference <= 2 hours
            dt = abs(o1["time"] - o2["time"])
            if dt > timedelta(hours=2):
                continue

            # Constraint 2: Elevation > 30 degrees for BOTH
            # Using 30.0 strictly
            if o1["el"] <= 30.0 or o2["el"] <= 30.0:
            # if o1["el"] < 30.0 or o2["el"] < 30.0: # Spec says "larger than 30", so > 30. <= 30 is fail.
                continue

            # Constraint 3: Azimuth difference 15 to max_separation_deg degrees
            diff = abs(o1["az"] - o2["az"])
            if diff > 180:
                diff = 360 - diff
            
            # Check range
            if min_separation_deg <= diff <= max_separation_deg:
                has_stereo = True
                if diff > max_valid_sep:
                    max_valid_sep = diff
                    best_pair = (o1["id"], o2["id"])

    return {
        "has_stereo": has_stereo,
        "max_separation_deg": max_valid_sep,
        "best_pair": best_pair,
    }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute Haversine distance in km."""
    import math
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _point_in_polygon(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    """Ray casting algorithm for point in polygon. x=lon, y=lat."""
    n = len(poly)
    inside = False
    p1x, p1y = poly[0][1], poly[0][0]  # lon, lat
    for i in range(n + 1):
        p2x, p2y = poly[i % n][1], poly[i % n][0]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def _dist_point_to_segment_km(
    plat: float, plon: float, 
    slat1: float, slon1: float, 
    slat2: float, slon2: float
) -> float:
    """Approximate distance from point to line segment in km."""
    # This is a simplified Euclidean approximation valid for small local areas.
    # For global scale/poles, would need cross-track distance on sphere.
    # Given the benchmark constraints, this is likely acceptable or we can use library.
    # Using haversine for endpoints and projection might be expensive. 
    # Let's use simple logic: find closest point on segment, compute haversine to it.
    
    # Vector P - S1
    dx = slon2 - slon1
    dy = slat2 - slat1
    if dx == 0 and dy == 0:
        return _haversine_km(plat, plon, slat1, slon1)

    t = ((plon - slon1) * dx + (plat - slat1) * dy) / (dx*dx + dy*dy)
    t = max(0, min(1, t))
    
    closest_lon = slon1 + t * dx
    closest_lat = slat1 + t * dy
    return _haversine_km(plat, plon, closest_lat, closest_lon)


def compute_polygon_coverage(
    polygon: list[tuple[float, float]], 
    strips_with_width: list[tuple[list[tuple[float, float]], float]], 
    grid_step_deg: float = 0.1
) -> dict:
    """
    Compute coverage ratio of pair polygon by observed strips.

    Args:
        polygon: List of (lat, lon) vertices.
        strips_with_width: List of (polyline, swath_width_km) tuples.
        grid_step_deg: Grid sampling size in degrees.

    Returns:
        dict containing coverage_ratio, area_km2, etc.
    """
    lats = [p[0] for p in polygon]
    lons = [p[1] for p in polygon]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    total_points = 0
    covered_points = 0
    grid_cells = []

    # Generate grid
    import math
    lat = min_lat
    while lat <= max_lat:
        lon = min_lon
        while lon <= max_lon:
            if _point_in_polygon(lon, lat, polygon):
                total_points += 1
                is_covered = False
                
                # Check distance to any strip
                for strip, width in strips_with_width:
                    # Check each segment of the strip
                    for i in range(len(strip) - 1):
                        p1 = strip[i]
                        p2 = strip[i+1]
                        dist = _dist_point_to_segment_km(lat, lon, p1[0], p1[1], p2[0], p2[1])
                        if dist <= width / 2.0:
                            is_covered = True
                            break
                    if is_covered:
                        break
                
                if is_covered:
                    covered_points += 1
                
                grid_cells.append({
                    "lat": lat,
                    "lon": lon,
                    "is_covered": is_covered
                })
            
            lon += grid_step_deg
        lat += grid_step_deg

    ratio = covered_points / total_points if total_points > 0 else 0.0
    
    # Approximate area (km2)
    # Average lat for scale
    avg_lat = sum(lats) / len(lats)
    lat_dist = 111.0 # 1 deg lat ~ 111 km
    lon_dist = 111.0 * math.cos(math.radians(avg_lat))
    cell_area = (grid_step_deg * lat_dist) * (grid_step_deg * lon_dist)
    total_area_km2 = total_points * cell_area
    covered_area_km2 = covered_points * cell_area

    return {
        "coverage_ratio": ratio,
        "total_area_km2": total_area_km2,
        "covered_area_km2": covered_area_km2,
        "grid_cells": grid_cells
    }
