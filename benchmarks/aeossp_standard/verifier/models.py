"""Data models for the aeossp_standard verifier."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


NUMERICAL_EPS = 1.0e-9


@dataclass(frozen=True)
class Mission:
    case_id: str
    horizon_start: datetime
    horizon_end: datetime
    action_time_step_s: int
    geometry_sample_step_s: int
    resource_sample_step_s: int

    @property
    def horizon_seconds(self) -> int:
        seconds = (self.horizon_end - self.horizon_start).total_seconds()
        if seconds < 0:
            raise ValueError("mission horizon_end must be after horizon_start")
        if abs(seconds - round(seconds)) > NUMERICAL_EPS:
            raise ValueError("mission horizon must be an integer number of seconds")
        return int(round(seconds))


@dataclass(frozen=True)
class Sensor:
    sensor_type: str


@dataclass(frozen=True)
class AttitudeModel:
    max_slew_velocity_deg_per_s: float
    max_slew_acceleration_deg_per_s2: float
    settling_time_s: float
    max_off_nadir_deg: float


@dataclass(frozen=True)
class ResourceModel:
    battery_capacity_wh: float
    initial_battery_wh: float
    idle_power_w: float
    imaging_power_w: float
    slew_power_w: float
    sunlit_charge_power_w: float


@dataclass(frozen=True)
class SatelliteDef:
    satellite_id: str
    norad_catalog_id: int
    tle_line1: str
    tle_line2: str
    sensor: Sensor
    attitude_model: AttitudeModel
    resource_model: ResourceModel


@dataclass(frozen=True)
class TaskDef:
    task_id: str
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    release_time: datetime
    due_time: datetime
    required_duration_s: int
    required_sensor_type: str
    weight: float
    target_ecef_m: np.ndarray


@dataclass(frozen=True)
class AeosspCase:
    case_dir: Path
    mission: Mission
    satellites: dict[str, SatelliteDef]
    tasks: dict[str, TaskDef]


@dataclass(frozen=True)
class ObservationAction:
    satellite_id: str
    task_id: str
    start_time: datetime
    end_time: datetime

    @property
    def duration_s(self) -> int:
        seconds = (self.end_time - self.start_time).total_seconds()
        if abs(seconds - round(seconds)) > NUMERICAL_EPS:
            raise ValueError("Action duration must be an integer number of seconds")
        return int(round(seconds))


@dataclass(frozen=True)
class AeosspSolution:
    actions: list[ObservationAction]


@dataclass(frozen=True)
class ActionFailure:
    action_index: int
    satellite_id: str
    task_id: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_index": self.action_index,
            "satellite_id": self.satellite_id,
            "task_id": self.task_id,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ManeuverWindow:
    satellite_id: str
    start_time: datetime
    end_time: datetime
    required_gap_s: float
    slew_angle_deg: float
    from_task_id: str | None
    to_task_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "satellite_id": self.satellite_id,
            "start_time": self.start_time.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "end_time": self.end_time.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "required_gap_s": self.required_gap_s,
            "slew_angle_deg": self.slew_angle_deg,
            "from_task_id": self.from_task_id,
            "to_task_id": self.to_task_id,
        }


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    metrics: dict[str, Any]
    violations: list[str]
    diagnostics: dict[str, Any]

