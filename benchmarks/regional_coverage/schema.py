"""Tracked Phase 1 schema scaffold for the regional_coverage benchmark.

This module freezes public field names early in the rebuild so later generator
and verifier phases can implement against a concrete schema contract.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SensorDef:
    min_edge_off_nadir_deg: float
    max_edge_off_nadir_deg: float
    cross_track_fov_deg: float
    min_strip_duration_s: float
    max_strip_duration_s: float


@dataclass(frozen=True)
class AgilityDef:
    max_roll_rate_deg_per_s: float
    max_roll_acceleration_deg_per_s2: float
    settling_time_s: float


@dataclass(frozen=True)
class PowerDef:
    battery_capacity_wh: float
    initial_battery_wh: float
    idle_power_w: float
    imaging_power_w: float
    slew_power_w: float
    sunlit_charge_power_w: float
    imaging_duty_limit_s_per_orbit: float | None = None


@dataclass(frozen=True)
class SatelliteDef:
    satellite_id: str
    tle_line1: str
    tle_line2: str
    tle_epoch: str
    sensor: SensorDef
    agility: AgilityDef
    power: PowerDef


@dataclass(frozen=True)
class GridSample:
    sample_id: str
    longitude_deg: float
    latitude_deg: float
    weight_m2: float


@dataclass(frozen=True)
class RegionCoverageGrid:
    region_id: str
    total_weight_m2: float
    samples: tuple[GridSample, ...]


@dataclass(frozen=True)
class StripObservationAction:
    satellite_id: str
    start_time: str
    duration_s: int
    roll_deg: float
    type: str = "strip_observation"
