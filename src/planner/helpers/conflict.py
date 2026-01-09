"""Temporal conflict detection utilities."""

from typing import Dict, List, Optional, Tuple
from planner.models import PlannerAction, PlannerSatellite, PlannerTarget, PlannerStrip, PlannerStation
from engine.orbital.attitude import calculate_slew_time


def check_time_conflicts(
    candidate: PlannerAction,
    other_actions: Dict[str, PlannerAction],
    planner_satellite: PlannerSatellite,
    exclude_self: str | None = None,
    satellites: Dict[str, PlannerSatellite] | None = None,
    targets: Dict[str, PlannerTarget] | None = None,
    strips: Dict[str, PlannerStrip] | None = None,
    stations: Dict[str, PlannerStation] | None = None,
    quaternion_cache: Dict[str, Tuple[Tuple[float, float, float, float], Tuple[float, float, float, float]]] | None = None,
) -> List[str]:
    """
    Check for conflicts with other actions on the same satellite.

    Rules:
    1. Observation vs Observation:
       - No time overlap.
       - Gap >= SlewTime(end1, start2) + SettlingTime.
    2. Link vs Link (downlink, intersatellite_link):
       - Limit concurrent links to satellite.num_terminal.
    3. Observation vs Link:
       - Allowed to overlap (separate systems/resources).
    """
    # Filter for actions on same satellite
    sat_actions = [
        a for mid, a in other_actions.items()
        if a.satellite_id == candidate.satellite_id
        and mid != candidate.action_id
        and (exclude_self is None or mid != exclude_self)
    ]

    if candidate.type == "observation":
        return _check_observation_conflicts(
            candidate, sat_actions, planner_satellite,
            satellites, targets, strips, stations, quaternion_cache
        )
    elif candidate.type in ("downlink", "intersatellite_link"):
        return _check_link_conflicts(
            candidate, sat_actions, planner_satellite, other_actions, satellites
        )

    return []


def _check_observation_conflicts(
    candidate: PlannerAction,
    sat_actions: List[PlannerAction],
    satellite: PlannerSatellite,
    satellites: Dict[str, PlannerSatellite] | None = None,
    targets: Dict[str, PlannerTarget] | None = None,
    strips: Dict[str, PlannerStrip] | None = None,
    stations: Dict[str, PlannerStation] | None = None,
    quaternion_cache: Dict[str, Tuple] | None = None,
) -> List[str]:
    conflicts = []
    for other in sat_actions:
        if other.type != "observation":
            continue

        # 1. Strict overlap check
        latest_start = max(candidate.start_time, other.start_time)
        earliest_end = min(candidate.end_time, other.end_time)

        if latest_start < earliest_end:
            conflicts.append(other.action_id)
            continue

        # 2. Slew time check
        if _has_insufficient_slew_time(
            candidate, other, satellite,
            satellites, targets, strips, stations, quaternion_cache
        ):
            conflicts.append(other.action_id)

    return conflicts


def _has_insufficient_slew_time(
    candidate: PlannerAction,
    other: PlannerAction,
    satellite: PlannerSatellite,
    satellites: Dict[str, PlannerSatellite] | None,
    targets: Dict[str, PlannerTarget] | None,
    strips: Dict[str, PlannerStrip] | None,
    stations: Dict[str, PlannerStation] | None,
    quaternion_cache: Dict[str, Tuple] | None,
) -> bool:
    """Check if there is enough time to slew between two actions."""
    if not satellites or not targets or not strips or not stations:
        return False
    
    from .attitude import get_or_compute_quaternions
    
    first, second = (candidate, other) if candidate.start_time < other.start_time else (other, candidate)
    
    gap_sec = (second.start_time - first.end_time).total_seconds()
    if gap_sec < 0:
        return True
    
    q_first_pair = get_or_compute_quaternions(first, satellites, targets, strips, stations, quaternion_cache)
    q_second_pair = get_or_compute_quaternions(second, satellites, targets, strips, stations, quaternion_cache)
    
    if not q_first_pair or not q_second_pair:
        return False
    
    q_first_end = q_first_pair[1]
    q_second_start = q_second_pair[0]
    
    required_slew = calculate_slew_time(
        q_first_end, q_second_start,
        max_vel=satellite.max_slew_velocity_deg_per_sec,
        max_acc=satellite.max_slew_acceleration_deg_per_sec2,
        settling_time=satellite.settling_time_sec
    )
    
    return gap_sec < required_slew


def _check_link_conflicts(
    candidate: PlannerAction,
    sat_actions: List[PlannerAction],
    satellite: PlannerSatellite,
    all_actions: Dict[str, PlannerAction],
    satellites: Dict[str, PlannerSatellite] | None = None,
) -> List[str]:
    """Check terminal capacity constraint for link actions (downlink, ISL)."""
    overlapping_links = []

    for other in sat_actions:
        if other.type not in ("downlink", "intersatellite_link"):
            continue

        latest_start = max(candidate.start_time, other.start_time)
        earliest_end = min(candidate.end_time, other.end_time)

        if latest_start < earliest_end:
            overlapping_links.append(other.action_id)

    # Check primary satellite terminal constraint
    if len(overlapping_links) + 1 > satellite.num_terminal:
        return overlapping_links

    # For ISL, also check peer satellite terminal constraint
    if candidate.type == "intersatellite_link" and satellites:
        peer_sat_id = candidate.peer_satellite_id
        peer_sat = satellites.get(peer_sat_id)
        if peer_sat:
            peer_overlapping = []
            for action_id, action in all_actions.items():
                if action_id == candidate.action_id:
                    continue
                if action.satellite_id != peer_sat_id:
                    continue
                if action.type not in ("downlink", "intersatellite_link"):
                    continue

                latest_start = max(candidate.start_time, action.start_time)
                earliest_end = min(candidate.end_time, action.end_time)

                if latest_start < earliest_end:
                    peer_overlapping.append(action_id)

            # Check peer terminal capacity
            if len(peer_overlapping) + 1 > peer_sat.num_terminal:
                return overlapping_links + peer_overlapping

    return []


def format_conflict_message(
    action: PlannerAction,
    conflicts: List[str],
    staged_actions: Dict[str, PlannerAction],
    additional_actions: Dict[str, PlannerAction] | None = None,
) -> Dict[str, any]:
    """
    Generate detailed conflict message with suggestions.

    Args:
        action: The action that has conflicts
        conflicts: List of conflicting action_ids
        staged_actions: Current staged actions
        additional_actions: Optional batch-staged actions (for batch staging)

    Returns:
        Dict with 'reason' and 'suggestions' keys
    """
    conflict_id = conflicts[0]
    conflict_action = None

    if conflict_id in staged_actions:
        conflict_action = staged_actions[conflict_id]
    elif additional_actions and conflict_id in additional_actions:
        conflict_action = additional_actions[conflict_id]

    if not conflict_action:
        return {
            "reason": f"Conflict with action {conflict_id}",
            "suggestions": [f"Cancel action {conflict_id} first"],
        }

    reason = f"Conflict detected with action {conflict_id} ({conflict_action.type}). "

    if action.type == "observation" and conflict_action.type == "observation":
        reason += "Overlaps in time or insufficient slew/settling time."
    elif action.type in ("downlink", "intersatellite_link") and conflict_action.type in ("downlink", "intersatellite_link"):
        reason += "Exceeds terminal capacity."

    target_hint = action.target_id or action.station_id or "this action"
    suggestions = [
        f"Cancel action {conflict_id}",
        f"Choose a different window for {target_hint}",
    ]

    return {"reason": reason, "suggestions": suggestions}