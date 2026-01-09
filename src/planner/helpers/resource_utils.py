"""Resource (power/storage) simulation utilities."""

from typing import Dict, List, Tuple
from datetime import datetime

from engine.models import ResourceEvent, Satellite
from engine.resources.power import simulate_power
from engine.resources.storage import simulate_storage
from planner.models import PlannerAction, PlannerSatellite


def get_storage_params(satellite: PlannerSatellite) -> Tuple[float, float, float, float]:
    """
    Extract storage parameters from a PlannerSatellite.

    Returns:
        (capacity_mb, obs_rate_mb_per_min, downlink_rate_mb_per_min, initial_mb)
    """
    return (
        satellite.storage_capacity_mb,
        satellite.obs_store_rate_mb_per_min,
        satellite.downlink_release_rate_mb_per_min,
        satellite.initial_storage_mb,
    )


def get_power_params(
    satellite: PlannerSatellite,
) -> Tuple[float, float, float, float, float, float]:
    """
    Extract power/battery parameters from a PlannerSatellite.

    Returns:
        (capacity_wh, charge_rate_w, obs_discharge_w, downlink_discharge_w, idle_discharge_w, initial_wh)
    """
    return (
        satellite.battery_capacity_wh,
        satellite.charge_rate_w,
        satellite.obs_discharge_rate_w,
        satellite.downlink_discharge_rate_w,
        satellite.idle_discharge_rate_w,
        satellite.initial_battery_wh,
    )


def convert_to_power_events(
    actions: List[PlannerAction],
    subject_sat_id: str,
    satellites: Dict[str, PlannerSatellite],
) -> List[ResourceEvent]:
    """Convert actions to power usage events for a specific SUBJECT satellite."""
    events = []
    subject_sat = satellites[subject_sat_id]
    _, _, obs_w, link_w, _, _ = get_power_params(subject_sat)

    for act in actions:
        # Action only affects power if this satellite is the primary or the peer
        if act.satellite_id != subject_sat_id and act.peer_satellite_id != subject_sat_id:
            continue

        if act.type == "observation":
            rate = -(obs_w / 60.0)
        elif act.type in ("downlink", "intersatellite_link"):
            rate = -(link_w / 60.0)
        else:
            continue
            
        events.append(
            ResourceEvent(start=act.start_time, end=act.end_time, rate_change=rate)
        )
    return events


def convert_to_storage_events(
    actions: List[PlannerAction],
    subject_sat_id: str,
    satellites: Dict[str, PlannerSatellite],
) -> List[ResourceEvent]:
    """Convert actions to storage usage events for a specific SUBJECT satellite."""
    events = []
    subject_sat = satellites[subject_sat_id]
    _, obs_rate, link_rate, _ = get_storage_params(subject_sat)

    for act in actions:
        if act.satellite_id != subject_sat_id:
            continue
            
        rate = obs_rate if act.type == "observation" else -link_rate
        events.append(
            ResourceEvent(start=act.start_time, end=act.end_time, rate_change=rate)
        )
    return events


def check_power_capacity(
    candidate: PlannerAction,
    existing_actions: List[PlannerAction],
    satellite: PlannerSatellite,
    engine_satellite: Satellite,
    time_window: Tuple[datetime, datetime],
) -> Dict[str, float]:
    """
    Check if adding candidate would violate battery bounds.

    Args:
        candidate: Action to check
        existing_actions: Already staged actions for this satellite
        satellite: PlannerSatellite for params
        engine_satellite: Engine Satellite for simulation
        time_window: (start, end) of scenario

    Returns:
        Dict with 'under' and/or 'over' keys if violations found, empty otherwise
    """
    all_actions = list(existing_actions) + [candidate]
    satellites = {satellite.id: satellite}
    events = convert_to_power_events(all_actions, satellite.id, satellites)
    params = get_power_params(satellite)

    stats = simulate_power(
        usage_events=events,
        satellite_model=engine_satellite,
        time_window=time_window,
        battery_params=params,
    )

    issues: Dict[str, float] = {}
    if stats.get("violated_low"):
        issues["under"] = -stats["min"] if stats["min"] < 0 else 0.0
    if stats.get("violated_high"):
        issues["over"] = stats["max"] - stats.get("capacity", stats["max"])
    return issues


def check_storage_capacity(
    candidate: PlannerAction,
    existing_actions: List[PlannerAction],
    satellite: PlannerSatellite,
) -> Dict[str, float]:
    """
    Check if adding candidate would exceed storage for its satellite.

    Returns:
        Dict with satellite_id -> overflow_mb if exceeded, empty otherwise
    """
    all_actions = list(existing_actions) + [candidate]
    satellites = {satellite.id: satellite}
    events = convert_to_storage_events(all_actions, satellite.id, satellites)

    cap, _, _, initial = get_storage_params(satellite)
    stats = simulate_storage(usage_events=events, capacity=cap, initial=initial)

    if stats["peak"] > stats["capacity"]:
        return {candidate.satellite_id: stats["peak"] - stats["capacity"]}
    return {}