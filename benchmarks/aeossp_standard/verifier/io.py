"""Case and solution loading for the aeossp_standard verifier."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
import json

import brahe
import yaml

from .models import (
    AeosspCase,
    AeosspSolution,
    AttitudeModel,
    Mission,
    NUMERICAL_EPS,
    ObservationAction,
    ResourceModel,
    SatelliteDef,
    Sensor,
    TaskDef,
)


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_iso_utc(value: str, *, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include timezone information")
    return parsed.astimezone(UTC)


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


def _validate_positive_int(value: int, *, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _validate_non_negative(value: float, *, field_name: str) -> None:
    if value < -NUMERICAL_EPS:
        raise ValueError(f"{field_name} must be >= 0")


def _is_aligned(seconds: float, step_s: int) -> bool:
    return abs((seconds / step_s) - round(seconds / step_s)) <= 1.0e-9


def _validate_horizon_divisibility(mission: Mission) -> None:
    for field_name, step_s in (
        ("action_time_step_s", mission.action_time_step_s),
        ("geometry_sample_step_s", mission.geometry_sample_step_s),
        ("resource_sample_step_s", mission.resource_sample_step_s),
    ):
        if not _is_aligned(float(mission.horizon_seconds), step_s):
            raise ValueError(
                f"mission horizon must be exactly divisible by {field_name}"
            )


def _task_target_ecef_m(task: dict[str, Any], context: str):
    return brahe.position_geodetic_to_ecef(
        [
            _require_float(task, "longitude_deg", context),
            _require_float(task, "latitude_deg", context),
            _require_float(task, "altitude_m", context),
        ],
        brahe.AngleFormat.DEGREES,
    )


def load_case(case_dir: str | Path) -> AeosspCase:
    case_path = Path(case_dir).resolve()
    mission_doc = _require_mapping(_load_yaml(case_path / "mission.yaml"), "mission.yaml")
    satellites_doc = _require_mapping(
        _load_yaml(case_path / "satellites.yaml"), "satellites.yaml"
    )
    tasks_doc = _require_mapping(_load_yaml(case_path / "tasks.yaml"), "tasks.yaml")

    mission_raw = _require_mapping(mission_doc.get("mission"), "mission.yaml.mission")
    satellites_raw = _require_list(
        satellites_doc.get("satellites"), "satellites.yaml.satellites"
    )
    tasks_raw = _require_list(tasks_doc.get("tasks"), "tasks.yaml.tasks")

    mission = Mission(
        case_id=_require_str(mission_raw, "case_id", "mission.yaml.mission"),
        horizon_start=_parse_iso_utc(
            _require_str(mission_raw, "horizon_start", "mission.yaml.mission"),
            field_name="mission.horizon_start",
        ),
        horizon_end=_parse_iso_utc(
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
    _validate_positive_int(mission.action_time_step_s, field_name="mission.action_time_step_s")
    _validate_positive_int(
        mission.geometry_sample_step_s, field_name="mission.geometry_sample_step_s"
    )
    _validate_positive_int(
        mission.resource_sample_step_s, field_name="mission.resource_sample_step_s"
    )
    _validate_horizon_divisibility(mission)

    propagation = _require_mapping(mission_raw.get("propagation"), "mission.yaml.mission.propagation")
    if _require_str(propagation, "model", "mission.yaml.mission.propagation") != "sgp4":
        raise ValueError("mission.propagation.model must be 'sgp4'")

    satellites: dict[str, SatelliteDef] = {}
    for index, payload in enumerate(satellites_raw):
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
        sensor = Sensor(sensor_type=_require_str(sensor_raw, "sensor_type", f"{context}.sensor"))
        if sensor.sensor_type not in {"visible", "infrared"}:
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
        if resource.battery_capacity_wh <= 0:
            raise ValueError(f"{context}.resource_model.battery_capacity_wh must be > 0")
        if resource.initial_battery_wh < -NUMERICAL_EPS or (
            resource.initial_battery_wh > resource.battery_capacity_wh + NUMERICAL_EPS
        ):
            raise ValueError(
                f"{context}.resource_model.initial_battery_wh must lie within [0, battery_capacity_wh]"
            )
        for field_name, value in (
            ("max_slew_velocity_deg_per_s", attitude.max_slew_velocity_deg_per_s),
            ("max_slew_acceleration_deg_per_s2", attitude.max_slew_acceleration_deg_per_s2),
            ("settling_time_s", attitude.settling_time_s),
            ("max_off_nadir_deg", attitude.max_off_nadir_deg),
            ("idle_power_w", resource.idle_power_w),
            ("imaging_power_w", resource.imaging_power_w),
            ("slew_power_w", resource.slew_power_w),
            ("sunlit_charge_power_w", resource.sunlit_charge_power_w),
        ):
            _validate_non_negative(value, field_name=f"{context}.{field_name}")
        satellites[sat_id] = SatelliteDef(
            satellite_id=sat_id,
            norad_catalog_id=_require_int(sat_raw, "norad_catalog_id", context),
            tle_line1=tle_line1,
            tle_line2=tle_line2,
            sensor=sensor,
            attitude_model=attitude,
            resource_model=resource,
        )

    tasks: dict[str, TaskDef] = {}
    for index, payload in enumerate(tasks_raw):
        context = f"tasks.yaml.tasks[{index}]"
        task_raw = _require_mapping(payload, context)
        task_id = _require_str(task_raw, "task_id", context)
        if task_id in tasks:
            raise ValueError(f"Duplicate task_id: {task_id}")
        release_time = _parse_iso_utc(
            _require_str(task_raw, "release_time", context),
            field_name=f"{context}.release_time",
        )
        due_time = _parse_iso_utc(
            _require_str(task_raw, "due_time", context),
            field_name=f"{context}.due_time",
        )
        required_duration_s = _require_int(task_raw, "required_duration_s", context)
        weight_value = task_raw.get("weight", 1.0)
        if not isinstance(weight_value, (int, float)):
            raise ValueError(f"{context}.weight must be numeric")
        weight = float(weight_value)
        if release_time < mission.horizon_start or release_time > mission.horizon_end:
            raise ValueError(f"{context}.release_time must lie inside the mission horizon")
        if due_time < mission.horizon_start or due_time > mission.horizon_end:
            raise ValueError(f"{context}.due_time must lie inside the mission horizon")
        if due_time <= release_time:
            raise ValueError(f"{context}.due_time must be after release_time")
        if required_duration_s <= 0:
            raise ValueError(f"{context}.required_duration_s must be > 0")
        if weight <= 0.0:
            raise ValueError(f"{context}.weight must be > 0")
        for field_name, seconds in (
            (f"{context}.release_time", (release_time - mission.horizon_start).total_seconds()),
            (f"{context}.due_time", (due_time - mission.horizon_start).total_seconds()),
            (f"{context}.required_duration_s", float(required_duration_s)),
        ):
            if not _is_aligned(seconds, mission.action_time_step_s):
                raise ValueError(
                    f"{field_name} must align to the {mission.action_time_step_s}s action grid"
                )
        if required_duration_s > int((due_time - release_time).total_seconds()):
            raise ValueError(f"{context}.required_duration_s exceeds the task window length")
        sensor_type = _require_str(task_raw, "required_sensor_type", context)
        if sensor_type not in {"visible", "infrared"}:
            raise ValueError(
                f"{context}.required_sensor_type must be 'visible' or 'infrared'"
            )
        tasks[task_id] = TaskDef(
            task_id=task_id,
            name=_require_str(task_raw, "name", context),
            latitude_deg=_require_float(task_raw, "latitude_deg", context),
            longitude_deg=_require_float(task_raw, "longitude_deg", context),
            altitude_m=_require_float(task_raw, "altitude_m", context),
            release_time=release_time,
            due_time=due_time,
            required_duration_s=required_duration_s,
            required_sensor_type=sensor_type,
            weight=weight,
            target_ecef_m=brahe.position_geodetic_to_ecef(
                [
                    _require_float(task_raw, "longitude_deg", context),
                    _require_float(task_raw, "latitude_deg", context),
                    _require_float(task_raw, "altitude_m", context),
                ],
                brahe.AngleFormat.DEGREES,
            ),
        )

    return AeosspCase(
        case_dir=case_path,
        mission=mission,
        satellites=satellites,
        tasks=tasks,
    )


def load_solution(solution_path: str | Path) -> AeosspSolution:
    path = Path(solution_path).resolve()
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("solution.json must be a JSON object")
    actions_raw = payload.get("actions", [])
    if not isinstance(actions_raw, list):
        raise ValueError("solution.json.actions must be a list")
    actions: list[ObservationAction] = []
    for index, payload in enumerate(actions_raw):
        context = f"solution.json.actions[{index}]"
        action_raw = _require_mapping(payload, context)
        action_type = _require_str(action_raw, "type", context)
        if action_type != "observation":
            raise ValueError(f"{context}.type {action_type!r} is unsupported")
        actions.append(
            ObservationAction(
                satellite_id=_require_str(action_raw, "satellite_id", context),
                task_id=_require_str(action_raw, "task_id", context),
                start_time=_parse_iso_utc(
                    _require_str(action_raw, "start_time", context),
                    field_name=f"{context}.start_time",
                ),
                end_time=_parse_iso_utc(
                    _require_str(action_raw, "end_time", context),
                    field_name=f"{context}.end_time",
                ),
            )
        )
    return AeosspSolution(actions=actions)

