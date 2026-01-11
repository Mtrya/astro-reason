from datetime import timedelta
from typing import Tuple, Dict
from engines.astrox.orbital.attitude import calculate_pointing_quaternion
from engines.astrox.temporal import format_for_astrox, parse_iso
from engines.astrox.orbital.access import compute_accessibility
from toolkits.mission_planner.scenario.helpers.data_registry import to_engine_satellite
from toolkits.mission_planner.scenario.models import PlannerAction, PlannerSatellite, PlannerTarget, PlannerStation, PlannerStrip


def get_or_compute_quaternions(
    action: PlannerAction,
    satellites: Dict[str, PlannerSatellite],
    targets: Dict[str, PlannerTarget],
    strips: Dict[str, PlannerStrip],
    stations: Dict[str, PlannerStation],
    cache: Dict[str, Tuple[Tuple[float, float, float, float], Tuple[float, float, float, float]]] | None = None,
) -> Tuple[Tuple[float, float, float, float], Tuple[float, float, float, float]] | None:
    """Get quaternions from cache or compute lazily."""
    if cache and action.action_id in cache:
        return cache[action.action_id]
    
    satellite = satellites[action.satellite_id]
    target = targets.get(action.target_id) if action.target_id else None
    strip = strips.get(action.strip_id) if action.strip_id else None
    station = stations.get(action.station_id) if action.station_id else None
    
    quats = compute_action_quaternions(action, satellite, target, strip, station)
    
    if cache is not None and quats:
        cache[action.action_id] = quats
    
    return quats


def compute_action_quaternions(
    action: PlannerAction,
    satellite: PlannerSatellite,
    target: PlannerTarget | None = None,
    strip: PlannerStrip | None = None,
    station: PlannerStation | None = None,
) -> Tuple[Tuple[float, float, float, float], Tuple[float, float, float, float]] | None:
    """
    Calculate start and end quaternions for an action.
    
    Args:
        action: The action to calculate quaternions for.
        satellite: The satellite performing the action.
        target: The target object (if observation of a point target).
        strip: The strip object (if observation of a strip).
        station: The station object (if downlink).
        
    Returns:
        Tuple of (start_quaternion, end_quaternion) or None if applicable.
    """
    if action.type == "observation":
        if target:
            lat, lon, alt = target.latitude_deg, target.longitude_deg, target.altitude_m
            q_start = calculate_pointing_quaternion(
                satellite.tle_line1, satellite.tle_line2, lat, lon, alt, action.start_time.isoformat()
            )
            q_end = calculate_pointing_quaternion(
                satellite.tle_line1, satellite.tle_line2, lat, lon, alt, action.end_time.isoformat()
            )
            return q_start, q_end

        elif strip and strip.points:
            # Strip observation direction detection
            # Use geometric check via propagate_satellite and determine_strip_direction
            
            p_head = strip.points[0]
            p_tail = strip.points[-1]
            
            # Propagate to action start time
            # We need to import propagate_satellite here or at top level
            from engines.astrox.orbital.propagation import propagate_satellite
            from engines.astrox.orbital.attitude import determine_strip_direction
            
            # Ensure UTC
            chk_time = action.start_time
            if chk_time.tzinfo is None:
                chk_time = chk_time.replace(tzinfo=timezone.utc)
            else:
                chk_time = chk_time.astimezone(timezone.utc)
                
            rv_list = propagate_satellite(satellite.tle_line1, satellite.tle_line2, [chk_time])
            if not rv_list:
                # Fallback to forward if propagation fails (unlikely)
                direction = "forward"
            else:
                sat_pos, sat_vel = rv_list[0]
                direction = determine_strip_direction(sat_vel, p_head, p_tail, chk_time)
            
            is_reversed = (direction == "backward")
            
            start_pt = p_tail if is_reversed else p_head
            end_pt = p_head if is_reversed else p_tail
            
            q_start = calculate_pointing_quaternion(
                satellite.tle_line1, satellite.tle_line2, start_pt[0], start_pt[1], start_pt[2], action.start_time.isoformat()
            )
            q_end = calculate_pointing_quaternion(
                satellite.tle_line1, satellite.tle_line2, end_pt[0], end_pt[1], end_pt[2], action.end_time.isoformat()
            )
            return q_start, q_end

    elif action.type == "downlink":
        if station:
            q_start = calculate_pointing_quaternion(
                satellite.tle_line1, satellite.tle_line2, station.latitude_deg, station.longitude_deg, station.elevation_m, action.start_time.isoformat()
            )
            q_end = calculate_pointing_quaternion(
                satellite.tle_line1, satellite.tle_line2, station.latitude_deg, station.longitude_deg, station.elevation_m, action.end_time.isoformat()
            )
            return q_start, q_end

    return None
