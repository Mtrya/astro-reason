"""
Satellite orbit propagation and state vector interpolation.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Optional
import requests
import bisect

# TODO: Move to a configuration file
ASTROX_HOST = "http://astrox.cn:8765"


class PropagationError(Exception):
    """Custom exception for propagation errors."""
    pass


def _hermite_interpolate(
    t_norm: float,
    h: float,
    p0: List[float],
    v0: List[float],
    p1: List[float],
    v1: List[float]
) -> Tuple[List[float], List[float]]:
    """
    Perform Cubic Hermite interpolation for Position and Velocity.
    
    Args:
        t_norm: Normalized time [0, 1].
        h: Time step in seconds (t1 - t0).
        p0: Position vector at t0.
        v0: Velocity vector at t0.
        p1: Position vector at t1.
        v1: Velocity vector at t1.
        
    Returns:
        Tuple of (Interpolated Position, Interpolated Velocity).
    """
    t = t_norm
    t2 = t * t
    t3 = t2 * t
    
    # Basis functions for position
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    
    # Interpolated Position
    pos = [
        h00 * p0[i] + h10 * h * v0[i] + h01 * p1[i] + h11 * h * v1[i]
        for i in range(3)
    ]
    
    # Derivatives of basis functions for velocity (scaled by 1/h later)
    # d/dt(h00) = 6t^2 - 6t
    dh00 = 6 * t2 - 6 * t
    # d/dt(h10) = 3t^2 - 4t + 1
    dh10 = 3 * t2 - 4 * t + 1
    # d/dt(h01) = -6t^2 + 6t
    dh01 = -6 * t2 + 6 * t
    # d/dt(h11) = 3t^2 - 2t
    dh11 = 3 * t2 - 2 * t
    
    # Interpolated Velocity (d/dTime = (1/h) * d/dt)
    vel = [
        (dh00 * p0[i] + dh10 * h * v0[i] + dh01 * p1[i] + dh11 * h * v1[i]) / h
        for i in range(3)
    ]
    
    return pos, vel


def propagate_satellite(
    tle_line1: str,
    tle_line2: str,
    time_points: List[datetime],
    step_seconds: float = 60.0
) -> List[Tuple[List[float], List[float]]]:
    """
    Propagate satellite orbit to specific time points using Astrox SGP4 and Hermite interpolation.
    
    Args:
        tle_line1: First line of TLE.
        tle_line2: Second line of TLE.
        time_points: List of datetime objects (UTC) to compute state for.
        step_seconds: Step size for the SGP4 integrator grid in seconds.
        
    Returns:
        List of (position, velocity) tuples corresponding to time_points.
        Position is in meters (GCRS), Velocity is in meters/second (GCRS).
    """
    if not time_points:
        return []

    # Ensure all time_points are UTC
    utc_points = []
    for t in time_points:
        if t.tzinfo is None:
            utc_points.append(t.replace(tzinfo=timezone.utc))
        else:
            utc_points.append(t.astimezone(timezone.utc))
            
    sorted_points = sorted(utc_points)
    min_time = sorted_points[0]
    max_time = sorted_points[-1]
    
    # Pad the window slightly to ensure we have coverage for interpolation
    # if the requested point is exactly at the edge or slightly off due to precision
    start_buffer = min_time - timedelta(seconds=step_seconds)
    stop_buffer = max_time + timedelta(seconds=step_seconds)
    
    payload = {
        "SatelliteNumber": "00000", # Dummy, TLE is used
        "Start": start_buffer.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "Stop": stop_buffer.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "Step": step_seconds,
        "TLEs": [f"{tle_line1}", f"{tle_line2}"]
    }
    
    try:
        resp = requests.post(f"{ASTROX_HOST}/Propagator/Sgp4", json=payload, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise PropagationError(f"Astrox SGP4 request failed: {e}")
        
    data = resp.json()
    
    # Map t_offset -> (position, velocity)
    # Stride is 7: [Time, px, py, pz, vx, vy, vz]

    if "Position" not in data:
        raise PropagationError(f"Unexpected API response: {data.keys()}")
        
    pos_data = data["Position"]
    # API returns combined state in cartesianVelocity: [t, x, y, z, vx, vy, vz, ...]
    state_vector = pos_data.get("cartesianVelocity")
    epoch_str = pos_data.get("epoch")
    
    if not state_vector:
        raise PropagationError("Missing state vector (cartesianVelocity) in response.")
        
    # Parse Epoch
    try:
        epoch = datetime.fromisoformat(epoch_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise PropagationError(f"Invalid or missing epoch: {epoch_str}")

    # Map t_offset -> (position, velocity)
    # Stride is 7: [Time, px, py, pz, vx, vy, vz]
    pos_map: Dict[float, List[float]] = {}
    vel_map: Dict[float, List[float]] = {}
    
    stride = 7
    if len(state_vector) % stride != 0:
        raise PropagationError(f"State vector length {len(state_vector)} is not a multiple of {stride}.")
    
    for i in range(0, len(state_vector), stride):
        t = state_vector[i]
        pos_map[t] = state_vector[i+1 : i+4]
        vel_map[t] = state_vector[i+4 : i+7]
        
    # Sorted available times
    available_offsets = sorted(pos_map.keys())
    
    results = []
    
    for pt in time_points:
        # Calculate offset from epoch in seconds
        delta = (pt - epoch).total_seconds()
        
        # Check bounds
        if delta < available_offsets[0] or delta > available_offsets[-1]:
            # If slightly out of bounds due to float precision, clamp if very close
            if abs(delta - available_offsets[0]) < 1e-3:
                delta = available_offsets[0]
            elif abs(delta - available_offsets[-1]) < 1e-3:
                delta = available_offsets[-1]
            else:
                raise PropagationError(f"Time point {pt} (offset {delta}) is out of propagated bounds [{available_offsets[0]}, {available_offsets[-1]}].")
            
        # Find interval
        idx = bisect.bisect_right(available_offsets, delta)
        
        if idx == 0:
            t0 = available_offsets[0]
            results.append((pos_map[t0], vel_map[t0]))
            continue
        if idx == len(available_offsets):
            t0 = available_offsets[-1]
            if abs(delta - t0) < 1e-6:
                results.append((pos_map[t0], vel_map[t0]))
                continue
                 
        t0 = available_offsets[idx-1]
        t1 = available_offsets[idx]
        
        if abs(delta - t0) < 1e-6:
            results.append((pos_map[t0], vel_map[t0]))
            continue
        if abs(delta - t1) < 1e-6:
            results.append((pos_map[t1], vel_map[t1]))
            continue
            
        # Interpolate
        h = t1 - t0
        t_norm = (delta - t0) / h
        
        p, v = _hermite_interpolate(
            t_norm, h,
            pos_map[t0], vel_map[t0],
            pos_map[t1], vel_map[t1]
        )
        results.append((p, v))
        
    return results
