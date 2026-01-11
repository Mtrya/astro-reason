"""Planner-specific satellite model - engine model plus metadata"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlannerSatellite:
    """Represents a satellite in the scenario"""

    # Metadata
    id: str
    name: str
    norad_id: str
    constellation: str
    owner: str
    tle_epoch: str
    # Orbital elements
    tle_line1: str
    tle_line2: str
    apogee_km: float
    perigee_km: float
    period_min: float
    inclination_deg: float
    storage_capacity_mb: float
    obs_store_rate_mb_per_min: float
    downlink_release_rate_mb_per_min: float
    battery_capacity_wh: float
    charge_rate_w: float
    obs_discharge_rate_w: float
    downlink_discharge_rate_w: float
    idle_discharge_rate_w: float
    initial_storage_mb: float
    initial_battery_wh: float
    max_slew_velocity_deg_per_sec: float
    max_slew_acceleration_deg_per_sec2: float
    max_slew_jerk_deg_per_sec3: float | None
    settling_time_sec: float
    num_terminal: int
    swath_width_km: float | None = None

    