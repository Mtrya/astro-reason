"""Action parsing and validation utilities.

This module handles the parsing of action dictionaries and validation of action feasibility.
"""

from typing import Dict, Any
from datetime import datetime, timedelta

from engines.astrox.temporal import parse_iso
from toolkits.mission_planner.scenario.models import PlannerAction, PlannerSatellite, PlannerTarget, PlannerStation, PlannerStrip, PlannerAccessWindow
from toolkits.mission_planner.scenario.helpers.data_registry import to_engine_satellite
from toolkits.mission_planner.scenario.helpers.conflict import check_time_conflicts, format_conflict_message
from toolkits.mission_planner.scenario.helpers.resource_utils import check_power_capacity, check_storage_capacity
from toolkits.mission_planner.scenario.models import ValidationError, ConflictError, ResourceViolationError


__all__ = ["parse_action", "validate_action_feasibility", "ValidationError", "ConflictError", "ResourceViolationError"]


def parse_action(
    action_dict: Dict[str, Any],
    windows: Dict[str, PlannerAccessWindow],
    staged_actions: Dict[str, PlannerAction],
    horizon_start: datetime,
    horizon_end: datetime,
) -> PlannerAction:
    """
    Parse an action dictionary into a PlannerAction object.
    
    Args:
        action_dict: Raw action data dictionary
        windows: Available access windows for window_id lookup
        staged_actions: Current staged actions for ID generation
        horizon_start: Planning horizon start time
        horizon_end: Planning horizon end time
        
    Returns:
        Parsed and validated PlannerAction object
        
    Raises:
        ValidationError: If required fields are missing or invalid
    """
    ad = action_dict.copy()

    if "window_id" in ad and ad["window_id"] in windows:
        window = windows[ad["window_id"]]
        if "start_time" not in ad:
            ad["start_time"] = window.start
        if "end_time" not in ad:
            ad["end_time"] = window.end

    required = ["type", "satellite_id", "start_time", "end_time"]
    missing = [f for f in required if f not in ad]
    if missing:
        raise ValidationError(f"Missing required fields: {missing}")

    action_type = ad["type"]
    if action_type not in ("observation", "downlink", "intersatellite_link"):
        raise ValidationError("type must be 'observation', 'downlink', or 'intersatellite_link'")

    if action_type == "observation" and not ad.get("target_id") and not ad.get("strip_id"):
        raise ValidationError("observation action requires target_id or strip_id")
    if action_type == "downlink" and not ad.get("station_id"):
        raise ValidationError("downlink action requires station_id")
    if action_type == "intersatellite_link":
        if not ad.get("peer_satellite_id"):
            raise ValidationError("intersatellite_link action requires peer_satellite_id")
        if ad.get("peer_satellite_id") == ad["satellite_id"]:
            raise ValidationError("Cannot establish ISL with self")

    start_dt = parse_iso(ad["start_time"])
    end_dt = parse_iso(ad["end_time"])

    if start_dt >= end_dt:
        raise ValidationError("start_time must be before end_time")
    if start_dt < horizon_start or end_dt > horizon_end:
        raise ValidationError("Action times must be within horizon")

    action_id = ad.get("action_id")
    if not action_id:
        max_id = -1
        for existing_id in staged_actions.keys():
            if existing_id.startswith("action_"):
                try:
                    num = int(existing_id.split("_")[1])
                    if num > max_id:
                        max_id = num
                except ValueError:
                    continue
        action_id = f"action_{max_id + 1:03d}"

    return PlannerAction(
        action_id=action_id,
        type=action_type,
        satellite_id=ad["satellite_id"],
        target_id=ad.get("target_id"),
        station_id=ad.get("station_id"),
        strip_id=ad.get("strip_id"),
        peer_satellite_id=ad.get("peer_satellite_id"),
        start_time=start_dt,
        end_time=end_dt,
    )


def validate_action_feasibility(
    action: PlannerAction,
    against_actions: Dict[str, PlannerAction],
    satellites: Dict[str, PlannerSatellite],
    targets: Dict[str, PlannerTarget],
    stations: Dict[str, PlannerStation],
    strips: Dict[str, PlannerStrip],
    windows: Dict[str, PlannerAccessWindow],
    quaternion_cache: Dict[str, Any],
    horizon_start: datetime,
    horizon_end: datetime,
) -> None:
    """
    Validate if an action is feasible against existing actions.
    
    Checks for:
    - Time conflicts with other actions
    - Strip window timing alignment
    - Power capacity violations
    - Storage capacity violations
    
    Args:
        action: The action to validate
        against_actions: Existing actions to check against
        satellites: Available satellites dictionary
        targets: Available targets dictionary
        stations: Available stations dictionary
        strips: Available strips dictionary
        windows: Registered access windows
        quaternion_cache: Cache for quaternion calculations
        horizon_start: Planning horizon start
        horizon_end: Planning horizon end
        
    Raises:
        ValidationError: If basic validation fails
        ConflictError: If time conflicts are detected
        ResourceViolationError: If power or storage violations occur
    """
    sat = satellites[action.satellite_id]
    conflicts = check_time_conflicts(
        action,
        against_actions,
        planner_satellite=sat,
        exclude_self=action.action_id,
        satellites=satellites,
        targets=targets,
        strips=strips,
        stations=stations,
        quaternion_cache=quaternion_cache,
    )
    if conflicts:
        msg = format_conflict_message(action, conflicts, against_actions)
        raise ConflictError(msg.get("reason", "Time conflict detected"))

    if action.strip_id:
        matching_windows = [
            w for w in windows.values()
            if w.strip_id == action.strip_id and w.satellite_id == action.satellite_id
        ]
        if not matching_windows:
            raise ValidationError(
                f"No registered windows found for strip '{action.strip_id}' / satellite '{action.satellite_id}'. "
                f"Compute strip windows first with compute_strip_windows()."
            )
        threshold = timedelta(seconds=5)
        timing_valid = False
        for window in matching_windows:
            start_diff = abs(action.start_time - window.start)
            end_diff = abs(action.end_time - window.end)
            if start_diff <= threshold and end_diff <= threshold:
                timing_valid = True
                break
        if not timing_valid:
            raise ValidationError(
                f"Strip observation must match window timing precisely (within 5s). "
                f"No matching window found for strip '{action.strip_id}' with the specified timing."
            )

    if action.peer_satellite_id:
        matching_windows = [
            w for w in windows.values()
            if w.peer_satellite_id == action.peer_satellite_id 
            and w.satellite_id == action.satellite_id
        ]
        if not matching_windows:
            raise ValidationError(
                f"No registered windows found for ISL between '{action.satellite_id}' "
                f"and '{action.peer_satellite_id}'. Compute ISL windows first."
            )
        
        timing_valid = False
        for window in matching_windows:
            if action.start_time >= window.start and action.end_time <= window.end:
                timing_valid = True
                break
        
        if not timing_valid:
            raise ValidationError(
                f"ISL action timing must fall within a registered window."
            )

    engine_sat = to_engine_satellite(sat)
    sat_actions = [a for a in against_actions.values() if a.satellite_id == action.satellite_id]

    power_issues = check_power_capacity(
        action, sat_actions, sat, engine_sat, (horizon_start, horizon_end)
    )
    if power_issues:
        reason = f"Battery violation for {action.satellite_id}: "
        if "under" in power_issues:
            reason += f"would drop below 0 by {power_issues['under']:.1f} Wh. "
        if "over" in power_issues:
            reason += f"would exceed capacity by {power_issues['over']:.1f} Wh."
        raise ResourceViolationError(reason.strip())

    if action.type == "intersatellite_link":
        peer_sat = satellites[action.peer_satellite_id]
        peer_engine_sat = to_engine_satellite(peer_sat)
        peer_sat_actions = [a for a in against_actions.values() 
                            if a.satellite_id == action.peer_satellite_id]
        
        peer_power_issues = check_power_capacity(
            action, peer_sat_actions, peer_sat, peer_engine_sat, 
            (horizon_start, horizon_end)
        )
        if peer_power_issues:
            reason = f"Battery violation for peer satellite {action.peer_satellite_id}: "
            if "under" in peer_power_issues:
                reason += f"would drop below 0 by {peer_power_issues['under']:.1f} Wh."
            if "over" in peer_power_issues:
                reason += f"would exceed capacity by {peer_power_issues['over']:.1f} Wh."
            raise ResourceViolationError(reason.strip())

    storage_issues = check_storage_capacity(action, sat_actions, sat)
    if storage_issues:
        over_mb = list(storage_issues.values())[0]
        raise ResourceViolationError(
            f"Storage exceeded for {action.satellite_id}: over by {over_mb:.1f} MB"
        )
