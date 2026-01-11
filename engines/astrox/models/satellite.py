"""
Satellite data structure containing only physical attributes.
"""

from dataclasses import dataclass
from typing import Optional, Union


@dataclass(frozen=True)
class Satellite:

    # Real data from celestrak, relevant for orbital mechanics
    tle_line1: str
    tle_line2: str
    apogee_km: float
    perigee_km: float
    period_min: float
    inclination_deg: float
    # Fake data (real data not accessible) for observation/power/storage/kinematic simulation
    storage_capacity_mb: Optional[float] = None
    obs_store_rate_mb_per_min: Optional[float] = None
    downlink_release_rate_mb_per_min: Optional[float] = None
    battery_capacity_wh: Optional[float] = None
    charge_rate_w: Optional[float] = None
    obs_discharge_rate_w: Optional[float] = None
    downlink_discharge_rate_w: Optional[float] = None
    idle_discharge_rate_w: Optional[float] = None
    initial_storage_mb: Optional[float] = None
    initial_battery_wh: Optional[float] = None
    max_slew_velocity_deg_per_sec: Optional[float] = None
    max_slew_acceleration_deg_per_sec2: Optional[float] = None
    max_slew_jerk_deg_per_sec3: Optional[float] = None
    settling_time_sec: Optional[float] = None
    num_terminal: Optional[int] = None
