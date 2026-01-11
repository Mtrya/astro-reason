"""
Satellite attitude and slew time calculations.
"""

import math
from datetime import datetime, timezone
from typing import Tuple, List

import os
import functools
from pathlib import Path
from skyfield.api import Loader, wgs84, Timescale

from .propagation import propagate_satellite

@functools.lru_cache(maxsize=1)
def _get_skyfield_ts() -> Timescale:
    """Lazy load Skyfield timescale with caching."""
    cache_dir = Path(os.path.expanduser("~/.cache/satellite-agent/skyfield-data"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    loader = Loader(str(cache_dir))
    return loader.timescale()

def lla_to_eci(lat_deg: float, lon_deg: float, alt_m: float, dt: datetime) -> Tuple[float, float, float]:
    """Convert LLA to ECI (GCRS) using Skyfield."""
    ts = _get_skyfield_ts()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    t = ts.from_datetime(dt)
    pos = wgs84.latlon(lat_deg, lon_deg, elevation_m=alt_m).at(t).position.m
    return (pos[0], pos[1], pos[2])


def quaternion_eci_to_ecef(
    q_eci: Tuple[float, float, float, float], dt: datetime
) -> Tuple[float, float, float, float]:
    """Transform a quaternion from ECI (GCRS) to ECEF (ITRF) frame.
    
    Args:
        q_eci: Quaternion (x, y, z, w) in ECI frame.
        dt: Time of the transformation.
        
    Returns:
        Quaternion (x, y, z, w) in ECEF frame.
    """
    ts = _get_skyfield_ts()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    t = ts.from_datetime(dt)
    
    gast_hours = t.gast
    theta = math.radians(gast_hours * 15.0)
    
    c = math.cos(theta / 2.0)
    s = math.sin(theta / 2.0)
    q_rot = (0.0, 0.0, s, c)
    
    def quat_multiply(q1, q2):
        x1, y1, z1, w1 = q1
        x2, y2, z2, w2 = q2
        return (
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        )
    
    def quat_conjugate(q):
        return (-q[0], -q[1], -q[2], q[3])
    
    q_ecef = quat_multiply(quat_conjugate(q_rot), q_eci)
    
    return q_ecef

def _normalize(v: List[float]) -> List[float]:
    n = math.sqrt(sum(x*x for x in v))
    return [0.0, 0.0, 0.0] if n == 0 else [x/n for x in v]

def _cross(a: List[float], b: List[float]) -> List[float]:
    return [a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0]]

def _dot(a: List[float], b: List[float]) -> float:
    return sum(x*y for x, y in zip(a, b))

def _look_at_quaternion(position: List[float], target: List[float], up: List[float]) -> Tuple[float, float, float, float]:
    """Calculate LookAt quaternion (Z-axis to target, Up guides orientation)."""
    forward = [target[i] - position[i] for i in range(3)]
    z_axis = _normalize(forward)
    
    if abs(_dot(z_axis, _normalize(up))) > 0.999:
        up = [up[0] + 0.1, up[1], up[2]]
        
    x_axis = _normalize(_cross(up, z_axis))
    y_axis = _cross(z_axis, x_axis)
    
    m00, m01, m02 = x_axis[0], y_axis[0], z_axis[0]
    m10, m11, m12 = x_axis[1], y_axis[1], z_axis[1]
    m20, m21, m22 = x_axis[2], y_axis[2], z_axis[2]
    
    tr = m00 + m11 + m22
    if tr > 0:
        S = math.sqrt(tr + 1.0) * 2
        return ((m21 - m12) / S, (m02 - m20) / S, (m10 - m01) / S, 0.25 * S)
    elif (m00 > m11) and (m00 > m22):
        S = math.sqrt(1.0 + m00 - m11 - m22) * 2
        return (0.25 * S, (m01 + m10) / S, (m02 + m20) / S, (m21 - m12) / S)
    elif (m11 > m22):
        S = math.sqrt(1.0 + m11 - m00 - m22) * 2
        return ((m01 + m10) / S, 0.25 * S, (m12 + m21) / S, (m02 - m20) / S)
    else:
        S = math.sqrt(1.0 + m22 - m00 - m11) * 2
        return ((m02 + m20) / S, (m12 + m21) / S, 0.25 * S, (m10 - m01) / S)

def calculate_pointing_quaternion(tle1: str, tle2: str, lat: float, lon: float, alt: float, ts_iso: str) -> Tuple[float, float, float, float]:
    """Calculate quaternion to point satellite (TLE) at target (LLA) at time (ISO)."""
    dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    if dt.tzinfo: dt = dt.astimezone(timezone.utc)
    else: dt = dt.replace(tzinfo=timezone.utc)
    
    # Propagate to the exact time
    rv_list = propagate_satellite(tle1, tle2, [dt])
    if not rv_list:
        raise ValueError(f"Failed to propagate satellite state for {dt}")
        
    sat_pos, sat_vel = rv_list[0]
    
    target_pos = lla_to_eci(lat, lon, alt, dt)
    
    return _look_at_quaternion(sat_pos, target_pos, sat_vel)

def calculate_slew_time(q1: Tuple[float, float, float, float], q2: Tuple[float, float, float, float], 
                       max_vel: float = 3.0, max_acc: float = 0.5, settling_time: float = 5.0, **kwargs) -> float:
    """Calculate slew time (Trapezoidal velocity profile)."""
    # Dot product of q1 and q2 gives cos(theta/2)
    dot = max(-1.0, min(1.0, sum(a*b for a,b in zip(q1, q2))))
    theta_deg = math.degrees(2.0 * math.acos(abs(dot)))
    
    if theta_deg < 1e-6: return 0.0
    v_max, a_max = abs(max_vel), abs(max_acc)
    if v_max == 0 or a_max == 0: return float('inf')

    t_acc = v_max / a_max
    d_acc = 0.5 * a_max * (t_acc ** 2)
    
    if 2 * d_acc > theta_deg:
        t_slew = math.sqrt(4 * theta_deg / a_max)
    else:
        t_slew = 2 * t_acc + (theta_deg - 2 * d_acc) / v_max
        
    return t_slew + settling_time


def calculate_nadir_quaternion(
    tle1: str, tle2: str, dt: datetime
) -> Tuple[float, float, float, float]:
    """Calculate nadir-pointing quaternion (Z-axis to Earth center)."""
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc)
    else:
        dt = dt.replace(tzinfo=timezone.utc)

    rv_list = propagate_satellite(tle1, tle2, [dt])
    if not rv_list:
        raise ValueError(f"Failed to propagate satellite state for {dt}")

    sat_pos, sat_vel = rv_list[0]
    earth_center = [0.0, 0.0, 0.0]

    return _look_at_quaternion(sat_pos, earth_center, sat_vel)


def determine_strip_direction(
    sat_vel: List[float],
    head: Tuple[float, float],
    tail: Tuple[float, float],
    check_time: datetime,
) -> str:
    """
    Determine if the pass is Head->Tail ('forward') or Tail->Head ('backward').
    
    Uses the dot product of satellite velocity and the strip chord vector.
    """
    lat_h, lon_h = head
    lat_t, lon_t = tail
    
    # Convert Head/Tail to ECI at check time (altitude 0)
    head_eci = lla_to_eci(lat_h, lon_h, 0.0, check_time)
    tail_eci = lla_to_eci(lat_t, lon_t, 0.0, check_time)
    
    # Vector from Head to Tail
    v_ht = [tail_eci[k] - head_eci[k] for k in range(3)]
    
    # Dot product with velocity
    dot = sum(sat_vel[k] * v_ht[k] for k in range(3))
    
    if dot >= 0:
        return "forward"
    else:
        return "backward"


def _sample_polyline(points: List[Tuple[float, float]], fraction: float) -> Tuple[float, float]:
    """Sample a point along the polyline at the given fraction (0.0 to 1.0) of arc length."""
    if not points:
        raise ValueError("Empty point list")
    if len(points) == 1:
        return points[0]
    
    # Clamp fraction
    t = max(0.0, min(1.0, fraction))
    
    # Calculate segment lengths
    segment_lengths = []
    total_length = 0.0
    for i in range(len(points) - 1):
        lat1, lon1 = points[i]
        lat2, lon2 = points[i + 1]
        dist = math.sqrt((lat2 - lat1) ** 2 + (lon2 - lon1) ** 2)
        segment_lengths.append(dist)
        total_length += dist
        
    if total_length == 0:
        return points[0]
        
    target_dist = t * total_length
    
    current_dist = 0.0
    for i, seg_len in enumerate(segment_lengths):
        if current_dist + seg_len >= target_dist:
            # Found segment
            if seg_len == 0:
                return points[i]
            
            seg_t = (target_dist - current_dist) / seg_len
            lat1, lon1 = points[i]
            lat2, lon2 = points[i+1]
            lat = lat1 + seg_t * (lat2 - lat1)
            lon = lon1 + seg_t * (lon2 - lon1)
            return (lat, lon)
        current_dist += seg_len
        
    return points[-1]


def calculate_quaternion_series(
    tle1: str,
    tle2: str,
    target_obs_actions: List[Tuple[datetime, datetime, float, float, float]],
    strip_obs_actions: List[Tuple[datetime, datetime, List[Tuple[float, float]]]],
    time_points: List[datetime],
) -> List[Tuple[float, float, float, float]]:
    """
    Calculate pointing quaternions at each time point based on actions in ECI frame.

    Uses batched propagation for efficiency.

    Args:
        tle1, tle2: TLE lines for the satellite.
        target_obs_actions: List of (start, end, lat_deg, lon_deg, alt_m) for point observations.
        strip_obs_actions: List of (start, end, points) for strip observations.
        time_points: List of datetime objects at which to sample attitude.

    Returns:
        List of quaternions (one per time_point).
        - Before any observation: nadir-pointing.
        - During observation: pointing at target.
        - After observation (idle/downlink): persist last observation's end quaternion.
    """
    if not time_points:
        return []

    utc_points = []
    for tp in time_points:
        if tp.tzinfo is None:
            utc_points.append(tp.replace(tzinfo=timezone.utc))
        else:
            utc_points.append(tp.astimezone(timezone.utc))

    # 1. Propagate for all output time points
    rv_list = propagate_satellite(tle1, tle2, utc_points)
    if len(rv_list) != len(utc_points):
        raise ValueError(f"Propagation returned {len(rv_list)} states for {len(utc_points)} time points")

    # 2. Determine direction for strip actions
    # We need to know if each strip action is Head->Tail or Tail->Head.
    strip_directions = {} # action_index -> "forward" or "backward"
    
    if strip_obs_actions:
        strip_start_times = [action[0] for action in strip_obs_actions]
        # Ensure UTC
        strip_check_times = []
        for tp in strip_start_times:
            if tp.tzinfo is None:
                strip_check_times.append(tp.replace(tzinfo=timezone.utc))
            else:
                strip_check_times.append(tp.astimezone(timezone.utc))
                
        strip_rvs = propagate_satellite(tle1, tle2, strip_check_times)
        
        for i, (sat_pos, sat_vel) in enumerate(strip_rvs):
            start, end, points = strip_obs_actions[i]
            if len(points) < 2:
                strip_directions[i] = "forward"
                continue
                
            strip_directions[i] = determine_strip_direction(
                sat_vel, points[0], points[-1], strip_check_times[i]
            )

    # 3. Merge and sort actions
    # Structure: (start, end, type, data, direction)
    # type 0: point, data: (lat, lon, alt)
    # type 1: strip, data: (points, original_index)
    
    combined_actions = []
    for s, e, lat, lon, alt in target_obs_actions:
        combined_actions.append((s, e, 0, (lat, lon, alt), None))
        
    for i, (s, e, points) in enumerate(strip_obs_actions):
        combined_actions.append((s, e, 1, (points, i), strip_directions[i]))
        
    sorted_actions = sorted(combined_actions, key=lambda a: a[0])

    result: List[Tuple[float, float, float, float]] = []
    last_quat: Tuple[float, float, float, float] | None = None
    earth_center = [0.0, 0.0, 0.0]

    for i, tp in enumerate(utc_points):
        sat_pos, sat_vel = rv_list[i]

        active_action = None
        for item in sorted_actions:
            start, end, atype, data, direction = item
            if start <= tp <= end:
                active_action = item
                break

        if active_action:
            start, end, atype, data, direction = active_action
            
            if atype == 0: # Point
                lat, lon, alt = data
                target_pos = lla_to_eci(lat, lon, alt, tp)
                quat = _look_at_quaternion(sat_pos, target_pos, sat_vel)
            else: # Strip
                points, idx = data
                # Calculate proportion of time
                total_duration = (end - start).total_seconds()
                elapsed = (tp - start).total_seconds()
                
                if total_duration <= 0:
                    fraction = 0.0
                else:
                    fraction = elapsed / total_duration
                    
                # If backward, invert fraction (look at Tail at start, Head at end) 
                if direction == "backward":
                    target_fraction = 1.0 - fraction
                else:
                    target_fraction = fraction
                    
                target_lat, target_lon = _sample_polyline(points, target_fraction)
                target_pos = lla_to_eci(target_lat, target_lon, 0.0, tp)
                quat = _look_at_quaternion(sat_pos, target_pos, sat_vel)

            last_quat = quat
            result.append(quat)
        elif last_quat is not None:
            result.append(last_quat)
        else:
            quat = _look_at_quaternion(sat_pos, earth_center, sat_vel)
            result.append(quat)

    return result

