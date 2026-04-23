"""Public case-file loading for the standalone AEOSSP greedy-LNS solver."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import json

import brahe
import yaml


NUMERICAL_EPS = 1.0e-9


@dataclass(frozen=True, slots=True)
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
        if abs(seconds - round(seconds)) > NUMERICAL_EPS:
            raise ValueError("mission horizon must be an integer number of seconds")
        return int(round(seconds))


@dataclass(frozen=True, slots=True)
class AttitudeModel:
    max_slew_velocity_deg_per_s: float
    max_slew_acceleration_deg_per_s2: float
    settling_time_s: float
    max_off_nadir_deg: float


@dataclass(frozen=True, slots=True)
class ResourceModel:
    battery_capacity_wh: float
    initial_battery_wh: float
    idle_power_w: float
    imaging_power_w: float
    slew_power_w: float
    sunlit_charge_power_w: float


@dataclass(frozen=True, slots=True)
class Satellite:
    satellite_id: str
    norad_catalog_id: int
    tle_line1: str
    tle_line2: str
    sensor_type: str
    attitude_model: AttitudeModel
    resource_model: ResourceModel


@dataclass(frozen=True, slots=True)
class Task:
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
    target_ecef_m: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class AeosspCase:
    case_dir: Path
    mission: Mission
    satellites: dict[str, Satellite]
    tasks: dict[str, Task]


def parse_iso_z(value: str, *, field_name: str = "timestamp") -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include timezone information")
    return parsed.astimezone(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _require_mapping(payload: Any, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{context} must be a mapping/object")
    return payload


def _require_list(payload: Any, context: str) -> list[Any]:
    if not isinstance(payload, list):
        raise ValueError(f"{context} must be a list/array")
    return payload


def _require_str(mapping: dict[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def _require_int(mapping: dict[str, Any], key: str, context: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{context}.{key} must be an integer")
    return value


def _require_float(mapping: dict[str, Any], key: str, context: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"{context}.{key} must be numeric")
    return float(value)


def _is_aligned(seconds: float, step_s: int) -> bool:
    return abs((seconds / step_s) - round(seconds / step_s)) <= NUMERICAL_EPS


def _validate_positive(value: float, *, field_name: str) -> None:
    if value <= 0.0:
        raise ValueError(f"{field_name} must be > 0")


def _validate_non_negative(value: float, *, field_name: str) -> None:
    if value < -NUMERICAL_EPS:
        raise ValueError(f"{field_name} must be >= 0")


def _target_ecef_m(task_raw: dict[str, Any], context: str) -> tuple[float, float, float]:
    value = brahe.position_geodetic_to_ecef(
        [
            _require_float(task_raw, "longitude_deg", context),
            _require_float(task_raw, "latitude_deg", context),
            _require_float(task_raw, "altitude_m", context),
        ],
        brahe.AngleFormat.DEGREES,
    )
    return tuple(float(item) for item in value)


def load_case(case_dir: str | Path) -> AeosspCase:
    case_path = Path(case_dir).resolve()
    mission_doc = _require_mapping(_load_yaml(case_path / "mission.yaml"), "mission.yaml")
    satellites_doc = _require_mapping(
        _load_yaml(case_path / "satellites.yaml"), "satellites.yaml"
    )
    tasks_doc = _require_mapping(_load_yaml(case_path / "tasks.yaml"), "tasks.yaml")

    mission_raw = _require_mapping(mission_doc.get("mission"), "mission.yaml.mission")
    mission = Mission(
        case_id=_require_str(mission_raw, "case_id", "mission.yaml.mission"),
        horizon_start=parse_iso_z(
            _require_str(mission_raw, "horizon_start", "mission.yaml.mission"),
            field_name="mission.horizon_start",
        ),
        horizon_end=parse_iso_z(
            _require_str(mission_raw, "horizon_end", "mission.yaml.mission"),
            field_name="mission.horizon_end",
        ),
        action_time_step_s=_require_int(
            mission_raw, "action_time_step_s", "mission.yaml.mission"
        ),
        geometry_sample_step_s=_require_int(
            mission_raw, "geometry_sample_step_s", "mission.yaml.mission"
        ),
        resource_sample_step_s=_require_int(
            mission_raw, "resource_sample_step_s", "mission.yaml.mission"
        ),
    )
    if mission.horizon_end <= mission.horizon_start:
        raise ValueError("mission.horizon_end must be after mission.horizon_start")
    for field_name, step_s in (
        ("action_time_step_s", mission.action_time_step_s),
        ("geometry_sample_step_s", mission.geometry_sample_step_s),
        ("resource_sample_step_s", mission.resource_sample_step_s),
    ):
        _validate_positive(float(step_s), field_name=f"mission.{field_name}")
        if not _is_aligned(float(mission.horizon_seconds), step_s):
            raise ValueError(f"mission horizon must be divisible by {field_name}")

    satellites: dict[str, Satellite] = {}
    for index, payload in enumerate(
        _require_list(satellites_doc.get("satellites"), "satellites.yaml.satellites")
    ):
        context = f"satellites.yaml.satellites[{index}]"
        sat_raw = _require_mapping(payload, context)
        sat_id = _require_str(sat_raw, "satellite_id", context)
        if sat_id in satellites:
            raise ValueError(f"Duplicate satellite_id: {sat_id}")
        tle_line1 = _require_str(sat_raw, "tle_line1", context)
        tle_line2 = _require_str(sat_raw, "tle_line2", context)
        if not brahe.validate_tle_lines(tle_line1, tle_line2):
            raise ValueError(f"{context} contains an invalid TLE pair")
        sensor_raw = _require_mapping(sat_raw.get("sensor"), f"{context}.sensor")
        attitude_raw = _require_mapping(sat_raw.get("attitude_model"), f"{context}.attitude_model")
        resource_raw = _require_mapping(sat_raw.get("resource_model"), f"{context}.resource_model")
        sensor_type = _require_str(sensor_raw, "sensor_type", f"{context}.sensor")
        if sensor_type not in {"visible", "infrared"}:
            raise ValueError(f"{context}.sensor.sensor_type must be 'visible' or 'infrared'")
        attitude = AttitudeModel(
            max_slew_velocity_deg_per_s=_require_float(
                attitude_raw, "max_slew_velocity_deg_per_s", f"{context}.attitude_model"
            ),
            max_slew_acceleration_deg_per_s2=_require_float(
                attitude_raw,
                "max_slew_acceleration_deg_per_s2",
                f"{context}.attitude_model",
            ),
            settling_time_s=_require_float(
                attitude_raw, "settling_time_s", f"{context}.attitude_model"
            ),
            max_off_nadir_deg=_require_float(
                attitude_raw, "max_off_nadir_deg", f"{context}.attitude_model"
            ),
        )
        resource = ResourceModel(
            battery_capacity_wh=_require_float(
                resource_raw, "battery_capacity_wh", f"{context}.resource_model"
            ),
            initial_battery_wh=_require_float(
                resource_raw, "initial_battery_wh", f"{context}.resource_model"
            ),
            idle_power_w=_require_float(resource_raw, "idle_power_w", f"{context}.resource_model"),
            imaging_power_w=_require_float(
                resource_raw, "imaging_power_w", f"{context}.resource_model"
            ),
            slew_power_w=_require_float(resource_raw, "slew_power_w", f"{context}.resource_model"),
            sunlit_charge_power_w=_require_float(
                resource_raw, "sunlit_charge_power_w", f"{context}.resource_model"
            ),
        )
        for field_name, value in (
            ("max_slew_velocity_deg_per_s", attitude.max_slew_velocity_deg_per_s),
            ("max_slew_acceleration_deg_per_s2", attitude.max_slew_acceleration_deg_per_s2),
            ("settling_time_s", attitude.settling_time_s),
            ("max_off_nadir_deg", attitude.max_off_nadir_deg),
            ("battery_capacity_wh", resource.battery_capacity_wh),
            ("initial_battery_wh", resource.initial_battery_wh),
            ("idle_power_w", resource.idle_power_w),
            ("imaging_power_w", resource.imaging_power_w),
            ("slew_power_w", resource.slew_power_w),
            ("sunlit_charge_power_w", resource.sunlit_charge_power_w),
        ):
            _validate_non_negative(value, field_name=f"{context}.{field_name}")
        _validate_positive(
            resource.battery_capacity_wh,
            field_name=f"{context}.resource_model.battery_capacity_wh",
        )
        if resource.initial_battery_wh > resource.battery_capacity_wh + NUMERICAL_EPS:
            raise ValueError(
                f"{context}.resource_model.initial_battery_wh must be <= "
                "resource_model.battery_capacity_wh"
            )
        satellites[sat_id] = Satellite(
            satellite_id=sat_id,
            norad_catalog_id=_require_int(sat_raw, "norad_catalog_id", context),
            tle_line1=tle_line1,
            tle_line2=tle_line2,
            sensor_type=sensor_type,
            attitude_model=attitude,
            resource_model=resource,
        )

    tasks: dict[str, Task] = {}
    for index, payload in enumerate(
        _require_list(tasks_doc.get("tasks"), "tasks.yaml.tasks")
    ):
        context = f"tasks.yaml.tasks[{index}]"
        task_raw = _require_mapping(payload, context)
        task_id = _require_str(task_raw, "task_id", context)
        if task_id in tasks:
            raise ValueError(f"Duplicate task_id: {task_id}")
        release_time = parse_iso_z(
            _require_str(task_raw, "release_time", context),
            field_name=f"{context}.release_time",
        )
        due_time = parse_iso_z(
            _require_str(task_raw, "due_time", context),
            field_name=f"{context}.due_time",
        )
        duration_s = _require_int(task_raw, "required_duration_s", context)
        if release_time < mission.horizon_start or due_time > mission.horizon_end:
            raise ValueError(f"{context} window must lie inside mission horizon")
        if due_time <= release_time:
            raise ValueError(f"{context}.due_time must be after release_time")
        if duration_s <= 0:
            raise ValueError(f"{context}.required_duration_s must be > 0")
        for field_name, seconds in (
            ("release_time", (release_time - mission.horizon_start).total_seconds()),
            ("due_time", (due_time - mission.horizon_start).total_seconds()),
            ("required_duration_s", float(duration_s)),
        ):
            if not _is_aligned(seconds, mission.action_time_step_s):
                raise ValueError(
                    f"{context}.{field_name} must align to the action grid"
                )
        if duration_s > int((due_time - release_time).total_seconds()):
            raise ValueError(f"{context}.required_duration_s exceeds the task window")
        sensor_type = _require_str(task_raw, "required_sensor_type", context)
        if sensor_type not in {"visible", "infrared"}:
            raise ValueError(
                f"{context}.required_sensor_type must be 'visible' or 'infrared'"
            )
        weight = float(task_raw.get("weight", 1.0))
        _validate_positive(weight, field_name=f"{context}.weight")
        tasks[task_id] = Task(
            task_id=task_id,
            name=_require_str(task_raw, "name", context),
            latitude_deg=_require_float(task_raw, "latitude_deg", context),
            longitude_deg=_require_float(task_raw, "longitude_deg", context),
            altitude_m=_require_float(task_raw, "altitude_m", context),
            release_time=release_time,
            due_time=due_time,
            required_duration_s=duration_s,
            required_sensor_type=sensor_type,
            weight=weight,
            target_ecef_m=_target_ecef_m(task_raw, context),
        )

    return AeosspCase(
        case_dir=case_path,
        mission=mission,
        satellites=satellites,
        tasks=tasks,
    )


def load_solver_config(config_dir: str | Path | None) -> dict[str, Any]:
    if not config_dir:
        return {}
    path = Path(config_dir)
    if not path.exists():
        raise FileNotFoundError(f"config path does not exist: {path}")
    if path.is_file():
        candidates = [path]
    else:
        candidates = [
            path / "config.yaml",
            path / "config.yml",
            path / "config.json",
            path / "greedy_lns.yaml",
            path / "greedy_lns.yml",
            path / "greedy_lns.json",
        ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        if candidate.suffix == ".json":
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        else:
            payload = yaml.safe_load(candidate.read_text(encoding="utf-8"))
        if payload is None:
            raise ValueError(f"{candidate} is empty")
        if not isinstance(payload, dict):
            raise ValueError(f"{candidate} must contain a mapping/object")
        return payload
    attempted = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"no supported config file found under {path}; tried: {attempted}")
