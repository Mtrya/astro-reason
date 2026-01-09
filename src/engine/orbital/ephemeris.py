"""Satellite ephemeris and ground track computation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Tuple
from skyfield.api import Loader, wgs84
from skyfield.positionlib import Geocentric
from pathlib import Path
import os

from engine.models import Satellite
from engine.orbital.propagation import propagate_satellite


def _get_skyfield_ts():
    """Lazy load Skyfield timescale with caching."""
    cache_dir = Path(os.path.expanduser("~/.cache/satellite-agent/skyfield-data"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    load = Loader(str(cache_dir))
    return load.timescale()


def _point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    """
    Check if a point is inside a polygon using ray casting algorithm.
    
    Args:
        point: (lat, lon) tuple
        polygon: List of (lat, lon) tuples defining polygon vertices
        
    Returns:
        True if point is inside polygon, False otherwise
    """
    lat, lon = point
    n = len(polygon)
    inside = False
    
    p1_lat, p1_lon = polygon[0]
    for i in range(1, n + 1):
        p2_lat, p2_lon = polygon[i % n]
        
        if lon > min(p1_lon, p2_lon):
            if lon <= max(p1_lon, p2_lon):
                if lat <= max(p1_lat, p2_lat):
                    if p1_lon != p2_lon:
                        x_intersection = (lon - p1_lon) * (p2_lat - p1_lat) / (p2_lon - p1_lon) + p1_lat
                    if p1_lat == p2_lat or lat <= x_intersection:
                        inside = not inside
        
        p1_lat, p1_lon = p2_lat, p2_lon
    
    return inside


def eci_to_lla(pos_km: List[float], dt: datetime) -> Tuple[float, float, float]:
    """
    Convert ECI (GCRS) position to Geodetic (LLA) coordinates.
    
    Args:
        pos_km: ECI position in kilometers [x, y, z]
        dt: Datetime (UTC)
        
    Returns:
        Tuple of (lat_deg, lon_deg, alt_m)
    """
    ts = _get_skyfield_ts()
    t = ts.from_datetime(dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc))
    
    # Geocentric expects position in AU, not km
    AU_KM = 149597870.700  # 1 AU in km
    pos_au = [p / AU_KM for p in pos_km]
    
    # Create a GCRS position with skyfield
    geocentric_pos = Geocentric(pos_au, t=t, center=399)  # 399 is Earth
    
    # Get geodetic coordinates
    subpoint = wgs84.subpoint_of(geocentric_pos)
    return subpoint.latitude.degrees, subpoint.longitude.degrees, subpoint.elevation.m


def compute_ground_track(
    satellite: Satellite,
    time_window: Tuple[datetime, datetime],
    step_sec: float = 60.0,
    polygon: List[Tuple[float, float]] | None = None
) -> List[Tuple[float, float, datetime]]:
    """
    Compute satellite ground track (subsatellite points).
    
    Args:
        satellite: Satellite to compute ground track for
        time_window: (start, end) datetime tuple
        step_sec: Time step in seconds between ground track points
        polygon: Optional polygon filter [(lat, lon), ...]. Only points inside polygon are returned.
        
    Returns:
        List of (lat, lon, time) tuples representing the ground track.
        Each point is the subsatellite point at that time.
    """
    start_time, end_time = time_window
    
    # Generate time points
    time_points = []
    current = start_time
    while current <= end_time:
        time_points.append(current)
        current += timedelta(seconds=step_sec)
    
    # Propagate satellite to get ECI positions
    state_vectors = propagate_satellite(
        satellite.tle_line1,
        satellite.tle_line2,
        time_points,
        step_seconds=step_sec
    )
    
    # Convert ECI to LLA using skyfield
    ground_track = []
    
    for time_point, (pos_eci, _) in zip(time_points, state_vectors):
        # pos_eci is in meters, convert to km for eci_to_lla
        pos_km = [p / 1000.0 for p in pos_eci]
        
        lat, lon, _ = eci_to_lla(pos_km, time_point)
        
        # Apply polygon filter if provided
        if polygon is None or _point_in_polygon((lat, lon), polygon):
            ground_track.append((lat, lon, time_point))
    
    return ground_track
