"""Shared data models for the revisit_constellation verifier."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import json

import numpy as np


DEFAULT_DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"
ACTION_SAMPLE_STEP_SEC = 10.0
RESOURCE_STEP_SEC = 30.0
NUMERICAL_EPS = 1e-9


@dataclass(frozen=True)
class SensorModel:
    max_off_nadir_angle_deg: float
    max_range_m: float
    obs_discharge_rate_w: float
    obs_store_rate_mb_per_s: float


@dataclass(frozen=True)
class TerminalModel:
    downlink_release_rate_mb_per_s: float
    downlink_discharge_rate_w: float


@dataclass(frozen=True)
class ResourceModel:
    battery_capacity_wh: float
    storage_capacity_mb: float
    initial_battery_wh: float
    initial_storage_mb: float
    idle_discharge_rate_w: float
    sunlight_charge_rate_w: float


@dataclass(frozen=True)
class AttitudeModel:
    max_slew_velocity_deg_per_sec: float
    max_slew_acceleration_deg_per_sec2: float
    settling_time_sec: float
    maneuver_discharge_rate_w: float


@dataclass(frozen=True)
class SatelliteModel:
    model_name: str
    sensor: SensorModel
    terminal: TerminalModel
    resource_model: ResourceModel
    attitude_model: AttitudeModel
    min_altitude_m: float
    max_altitude_m: float


@dataclass(frozen=True)
class GroundStation:
    station_id: str
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    min_elevation_deg: float
    min_duration_sec: float
    ecef_position_m: np.ndarray = field(repr=False)


@dataclass(frozen=True)
class Target:
    target_id: str
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    expected_revisit_period_hours: float
    min_elevation_deg: float
    max_slant_range_m: float
    min_duration_sec: float
    ecef_position_m: np.ndarray = field(repr=False)


@dataclass(frozen=True)
class Instance:
    case_dir: Path
    assets_path: Path
    mission_path: Path
    horizon_start: datetime
    horizon_end: datetime
    satellite_model: SatelliteModel
    max_num_satellites: int
    ground_stations: dict[str, GroundStation]
    targets: dict[str, Target]

    @property
    def horizon_duration_sec(self) -> float:
        return (self.horizon_end - self.horizon_start).total_seconds()


@dataclass(frozen=True)
class SatelliteDefinition:
    satellite_id: str
    state_eci_m_mps: np.ndarray = field(repr=False)


@dataclass(frozen=True)
class Action:
    action_type: str
    satellite_id: str
    start: datetime
    end: datetime
    target_id: str | None = None
    station_id: str | None = None

    @property
    def duration_sec(self) -> float:
        return (self.end - self.start).total_seconds()


@dataclass(frozen=True)
class Solution:
    satellites: dict[str, SatelliteDefinition]
    actions: list[Action]


@dataclass(frozen=True)
class ObservationRecord:
    satellite_id: str
    target_id: str
    start: datetime
    end: datetime
    midpoint: datetime


@dataclass(frozen=True)
class ManeuverWindow:
    satellite_id: str
    start: datetime
    end: datetime


@dataclass
class VerificationResult:
    is_valid: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "metrics": self.metrics,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def __str__(self) -> str:  # pragma: no cover - formatting helper
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)
