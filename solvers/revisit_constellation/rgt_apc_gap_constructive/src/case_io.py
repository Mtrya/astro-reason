"""Public case-file loading for the standalone revisit solver."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

import brahe
import yaml

from .time_grid import horizon_seconds, parse_iso_z


@dataclass(frozen=True, slots=True)
class SensorModel:
    max_off_nadir_angle_deg: float
    max_range_m: float
    obs_discharge_rate_w: float


@dataclass(frozen=True, slots=True)
class ResourceModel:
    battery_capacity_wh: float
    initial_battery_wh: float
    idle_discharge_rate_w: float
    sunlight_charge_rate_w: float


@dataclass(frozen=True, slots=True)
class AttitudeModel:
    max_slew_velocity_deg_per_sec: float
    max_slew_acceleration_deg_per_sec2: float
    settling_time_sec: float
    maneuver_discharge_rate_w: float


@dataclass(frozen=True, slots=True)
class SatelliteModel:
    model_name: str
    sensor: SensorModel
    resource_model: ResourceModel
    attitude_model: AttitudeModel
    min_altitude_m: float
    max_altitude_m: float


@dataclass(frozen=True, slots=True)
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
    ecef_position_m: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class RevisitCase:
    case_dir: Path
    horizon_start: object
    horizon_end: object
    satellite_model: SatelliteModel
    max_num_satellites: int
    targets: dict[str, Target]

    @property
    def case_id(self) -> str:
        return self.case_dir.name

    @property
    def horizon_duration_sec(self) -> int:
        return horizon_seconds(self.horizon_start, self.horizon_end)


def load_solver_config(config_dir: str | Path | None) -> dict[str, Any]:
    if not config_dir:
        return {}
    config_path = Path(config_dir)
    if not config_path.exists():
        return {}
    for name in ("config.yaml", "config.yml"):
        path = config_path / name
        if path.exists():
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(payload, dict):
                raise ValueError(f"{path} must contain a mapping/object")
            return payload
    return {}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_mapping(payload: Any, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{context} must be a JSON object")
    return payload


def _require_list(payload: Any, context: str) -> list[Any]:
    if not isinstance(payload, list):
        raise ValueError(f"{context} must be a JSON array")
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


def _validate_positive(value: float, *, field_name: str) -> None:
    if value <= 0.0:
        raise ValueError(f"{field_name} must be > 0")


def _validate_non_negative(value: float, *, field_name: str) -> None:
    if value < 0.0:
        raise ValueError(f"{field_name} must be >= 0")


def _target_ecef_m(target_raw: dict[str, Any], context: str) -> tuple[float, float, float]:
    value = brahe.position_geodetic_to_ecef(
        [
            _require_float(target_raw, "longitude_deg", context),
            _require_float(target_raw, "latitude_deg", context),
            _require_float(target_raw, "altitude_m", context),
        ],
        brahe.AngleFormat.DEGREES,
    )
    return tuple(float(item) for item in value)


def _parse_satellite_model(payload: dict[str, Any]) -> SatelliteModel:
    context = "assets.json.satellite_model"
    sensor_raw = _require_mapping(payload.get("sensor"), f"{context}.sensor")
    resource_raw = _require_mapping(payload.get("resource_model"), f"{context}.resource_model")
    attitude_raw = _require_mapping(payload.get("attitude_model"), f"{context}.attitude_model")

    sensor = SensorModel(
        max_off_nadir_angle_deg=_require_float(
            sensor_raw, "max_off_nadir_angle_deg", f"{context}.sensor"
        ),
        max_range_m=_require_float(sensor_raw, "max_range_m", f"{context}.sensor"),
        obs_discharge_rate_w=_require_float(
            sensor_raw, "obs_discharge_rate_w", f"{context}.sensor"
        ),
    )
    resource = ResourceModel(
        battery_capacity_wh=_require_float(
            resource_raw, "battery_capacity_wh", f"{context}.resource_model"
        ),
        initial_battery_wh=_require_float(
            resource_raw, "initial_battery_wh", f"{context}.resource_model"
        ),
        idle_discharge_rate_w=_require_float(
            resource_raw, "idle_discharge_rate_w", f"{context}.resource_model"
        ),
        sunlight_charge_rate_w=_require_float(
            resource_raw, "sunlight_charge_rate_w", f"{context}.resource_model"
        ),
    )
    attitude = AttitudeModel(
        max_slew_velocity_deg_per_sec=_require_float(
            attitude_raw, "max_slew_velocity_deg_per_sec", f"{context}.attitude_model"
        ),
        max_slew_acceleration_deg_per_sec2=_require_float(
            attitude_raw,
            "max_slew_acceleration_deg_per_sec2",
            f"{context}.attitude_model",
        ),
        settling_time_sec=_require_float(
            attitude_raw, "settling_time_sec", f"{context}.attitude_model"
        ),
        maneuver_discharge_rate_w=_require_float(
            attitude_raw, "maneuver_discharge_rate_w", f"{context}.attitude_model"
        ),
    )
    for field_name, value in (
        ("sensor.max_off_nadir_angle_deg", sensor.max_off_nadir_angle_deg),
        ("sensor.max_range_m", sensor.max_range_m),
        ("sensor.obs_discharge_rate_w", sensor.obs_discharge_rate_w),
        ("resource_model.battery_capacity_wh", resource.battery_capacity_wh),
        ("resource_model.initial_battery_wh", resource.initial_battery_wh),
        ("resource_model.idle_discharge_rate_w", resource.idle_discharge_rate_w),
        ("resource_model.sunlight_charge_rate_w", resource.sunlight_charge_rate_w),
        ("attitude_model.max_slew_velocity_deg_per_sec", attitude.max_slew_velocity_deg_per_sec),
        (
            "attitude_model.max_slew_acceleration_deg_per_sec2",
            attitude.max_slew_acceleration_deg_per_sec2,
        ),
        ("attitude_model.settling_time_sec", attitude.settling_time_sec),
        ("attitude_model.maneuver_discharge_rate_w", attitude.maneuver_discharge_rate_w),
    ):
        _validate_non_negative(value, field_name=f"{context}.{field_name}")
    min_altitude_m = _require_float(payload, "min_altitude_m", context)
    max_altitude_m = _require_float(payload, "max_altitude_m", context)
    _validate_positive(min_altitude_m, field_name=f"{context}.min_altitude_m")
    if max_altitude_m < min_altitude_m:
        raise ValueError(f"{context}.max_altitude_m must be >= min_altitude_m")
    return SatelliteModel(
        model_name=_require_str(payload, "model_name", context),
        sensor=sensor,
        resource_model=resource,
        attitude_model=attitude,
        min_altitude_m=min_altitude_m,
        max_altitude_m=max_altitude_m,
    )


def _parse_target(payload: dict[str, Any], index: int) -> Target:
    context = f"mission.json.targets[{index}]"
    target = Target(
        target_id=_require_str(payload, "id", context),
        name=_require_str(payload, "name", context),
        latitude_deg=_require_float(payload, "latitude_deg", context),
        longitude_deg=_require_float(payload, "longitude_deg", context),
        altitude_m=_require_float(payload, "altitude_m", context),
        expected_revisit_period_hours=_require_float(
            payload, "expected_revisit_period_hours", context
        ),
        min_elevation_deg=_require_float(payload, "min_elevation_deg", context),
        max_slant_range_m=_require_float(payload, "max_slant_range_m", context),
        min_duration_sec=_require_float(payload, "min_duration_sec", context),
        ecef_position_m=_target_ecef_m(payload, context),
    )
    _validate_positive(
        target.expected_revisit_period_hours,
        field_name=f"{context}.expected_revisit_period_hours",
    )
    _validate_positive(target.max_slant_range_m, field_name=f"{context}.max_slant_range_m")
    _validate_positive(target.min_duration_sec, field_name=f"{context}.min_duration_sec")
    return target


def load_case(case_dir: str | Path) -> RevisitCase:
    case_path = Path(case_dir).resolve()
    assets_path = case_path / "assets.json"
    mission_path = case_path / "mission.json"
    if not case_path.exists():
        raise FileNotFoundError(f"Case directory not found: {case_path}")
    if not assets_path.exists():
        raise FileNotFoundError(f"Missing case file: {assets_path}")
    if not mission_path.exists():
        raise FileNotFoundError(f"Missing case file: {mission_path}")

    assets = _require_mapping(_load_json(assets_path), "assets.json")
    mission = _require_mapping(_load_json(mission_path), "mission.json")
    satellite_model = _parse_satellite_model(
        _require_mapping(assets.get("satellite_model"), "assets.json.satellite_model")
    )
    max_num_satellites = _require_int(assets, "max_num_satellites", "assets.json")
    if max_num_satellites < 0:
        raise ValueError("assets.json.max_num_satellites must be >= 0")

    targets_list = _require_list(mission.get("targets"), "mission.json.targets")
    targets: dict[str, Target] = {}
    for index, item in enumerate(targets_list):
        target = _parse_target(_require_mapping(item, f"mission.json.targets[{index}]"), index)
        if target.target_id in targets:
            raise ValueError(f"Duplicate target id: {target.target_id}")
        targets[target.target_id] = target

    horizon_start = parse_iso_z(
        _require_str(mission, "horizon_start", "mission.json"),
        field_name="mission.json.horizon_start",
    )
    horizon_end = parse_iso_z(
        _require_str(mission, "horizon_end", "mission.json"),
        field_name="mission.json.horizon_end",
    )
    horizon_seconds(horizon_start, horizon_end)
    return RevisitCase(
        case_dir=case_path,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        satellite_model=satellite_model,
        max_num_satellites=max_num_satellites,
        targets=targets,
    )

