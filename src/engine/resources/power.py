"""
Satellite power simulation.
"""
from datetime import datetime
from ..models import ResourceEvent, LightingCondition
from ..orbital.lighting import compute_lighting_windows
from .common import simulate_resource_profile


def simulate_power(
    usage_events: list[ResourceEvent],
    satellite_model: dict,
    time_window: tuple[datetime, datetime],
    battery_params: tuple[float, float, float, float, float, float],
) -> dict[str, float | bool]:
    """
    Simulate power/battery profile including sunlight charging.

    Args:
        usage_events: List of power usage events (discharge is negative rate).
        satellite_model: Satellite model dictionary (must support what compute_lighting_windows needs).
        time_window: (start, end) of the simulation.
        battery_params: Tuple of (capacity_wh, charge_rate_w, obs_discharge_rate_w,
                       downlink_discharge_rate_w, idle_discharge_rate_w, initial_wh).
                       Note: obs/dl discharge rates are typically unused here as usage_events
                       are expected to already contain them, BUT we need charge_rate_w and idle_discharge.
                       Wait, the params tuple is what helpers.get_satellite_power_params returns.

    Returns:
        Simulation result dict from simulate_resource_profile, plus "capacity".
    """
    (
        capacity_wh,
        charge_rate_w,
        _,  # obs_discharge_rate_w (unused, assumed in usage_events or handled by caller? Actually caller just passes events)
        _,  # downlink_discharge_rate_w
        idle_discharge_rate_w,
        initial_batt_wh,
    ) = battery_params

    start_time, end_time = time_window
    events = list(usage_events)

    # 1. Idle discharge
    if idle_discharge_rate_w:
        events.append(
            ResourceEvent(
                start=start_time,
                end=end_time,
                rate_change=-(idle_discharge_rate_w / 60.0),
            )
        )

    # 2. Sunlight charging
    charge_rate_per_min = charge_rate_w / 60.0
    # Note: satellite_model might need to be cast to appropriate type for compute_lighting_windows if it expects an object.
    # Looking at existing code, compute_lighting_windows takes (sat_model, interval).
    light_windows = compute_lighting_windows(satellite_model, time_window)
    
    for w in light_windows:
        if w.condition != LightingCondition.SUNLIGHT:
            continue
        # Clamp to scenario interval
        s = max(w.start, start_time)
        e = min(w.end, end_time)
        if s >= e:
            continue
        events.append(ResourceEvent(start=s, end=e, rate_change=charge_rate_per_min))

    # 3. Simulate
    sim = simulate_resource_profile(
        events,
        initial_level=initial_batt_wh,
        capacity=capacity_wh,
        saturate=True,
    )
    sim["capacity"] = capacity_wh
    return sim
