"""Case and config loading for the standalone J2 RGT solver."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import json

import brahe
import yaml

from .time_utils import parse_iso_z


@dataclass(frozen=True, slots=True)
class SensorModel:
    max_off_nadir_angle_deg: float
    max_range_m: float
    obs_discharge_rate_w: float


@dataclass(frozen=True, slots=True)
class SatelliteModel:
    sensor: SensorModel
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
    horizon_start: datetime
    horizon_end: datetime
    satellite_model: SatelliteModel
    max_num_satellites: int
    targets: dict[str, Target]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_mapping(payload: Any, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{context} must be an object")
    return payload


def _require_list(payload: Any, context: str) -> list[Any]:
    if not isinstance(payload, list):
        raise ValueError(f"{context} must be an array")
    return payload


def _require_str(mapping: dict[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def _require_int(mapping: dict[str, Any], key: str, context: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context}.{key} must be an integer")
    return value


def _require_float(mapping: dict[str, Any], key: str, context: str) -> float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context}.{key} must be numeric")
    return float(value)


def _target_ecef_m(mapping: dict[str, Any], context: str) -> tuple[float, float, float]:
    position = brahe.position_geodetic_to_ecef(
        [
            _require_float(mapping, "longitude_deg", context),
            _require_float(mapping, "latitude_deg", context),
            _require_float(mapping, "altitude_m", context),
        ],
        brahe.AngleFormat.DEGREES,
    )
    return tuple(float(value) for value in position)


def load_solver_config(config_dir: str | Path | None) -> dict[str, Any]:
    if not config_dir:
        return {}
    config_path = Path(config_dir)
    if not config_path.exists():
        raise FileNotFoundError(f"config_dir does not exist: {config_path}")
    for name in ("config.yaml", "config.yml"):
        path = config_path / name
        if path.exists():
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(payload, dict):
                raise ValueError(f"{path} must contain a mapping/object")
            return payload
    raise FileNotFoundError(f"no config.yaml or config.yml found in {config_path}")


def load_case(case_dir: str | Path) -> RevisitCase:
    case_path = Path(case_dir).resolve()
    assets = _require_mapping(_load_json(case_path / "assets.json"), "assets.json")
    mission = _require_mapping(_load_json(case_path / "mission.json"), "mission.json")
    satellite_raw = _require_mapping(
        assets.get("satellite_model"), "assets.json.satellite_model"
    )
    sensor_raw = _require_mapping(
        satellite_raw.get("sensor"), "assets.json.satellite_model.sensor"
    )
    satellite_model = SatelliteModel(
        sensor=SensorModel(
            max_off_nadir_angle_deg=_require_float(
                sensor_raw,
                "max_off_nadir_angle_deg",
                "assets.json.satellite_model.sensor",
            ),
            max_range_m=_require_float(
                sensor_raw,
                "max_range_m",
                "assets.json.satellite_model.sensor",
            ),
            obs_discharge_rate_w=_require_float(
                sensor_raw,
                "obs_discharge_rate_w",
                "assets.json.satellite_model.sensor",
            ),
        ),
        min_altitude_m=_require_float(
            satellite_raw, "min_altitude_m", "assets.json.satellite_model"
        ),
        max_altitude_m=_require_float(
            satellite_raw, "max_altitude_m", "assets.json.satellite_model"
        ),
    )
    if satellite_model.min_altitude_m <= 0:
        raise ValueError("assets.json.satellite_model.min_altitude_m must be > 0")
    if satellite_model.max_altitude_m < satellite_model.min_altitude_m:
        raise ValueError("assets.json.satellite_model.max_altitude_m must be >= min")
    if satellite_model.sensor.max_range_m <= 0:
        raise ValueError("assets.json.satellite_model.sensor.max_range_m must be > 0")

    targets: dict[str, Target] = {}
    for index, target_raw in enumerate(
        _require_list(mission.get("targets"), "mission.json.targets")
    ):
        target_context = f"mission.json.targets[{index}]"
        target_map = _require_mapping(target_raw, target_context)
        target = Target(
            target_id=_require_str(target_map, "id", target_context),
            name=_require_str(target_map, "name", target_context),
            latitude_deg=_require_float(
                target_map, "latitude_deg", target_context
            ),
            longitude_deg=_require_float(
                target_map, "longitude_deg", target_context
            ),
            altitude_m=_require_float(
                target_map, "altitude_m", target_context
            ),
            expected_revisit_period_hours=_require_float(
                target_map,
                "expected_revisit_period_hours",
                target_context,
            ),
            min_elevation_deg=_require_float(
                target_map, "min_elevation_deg", target_context
            ),
            max_slant_range_m=_require_float(
                target_map, "max_slant_range_m", target_context
            ),
            min_duration_sec=_require_float(
                target_map, "min_duration_sec", target_context
            ),
            ecef_position_m=_target_ecef_m(target_map, target_context),
        )
        if target.target_id in targets:
            raise ValueError(f"duplicate target id: {target.target_id}")
        if target.max_slant_range_m <= 0:
            raise ValueError(f"{target_context}.max_slant_range_m must be > 0")
        if target.min_duration_sec <= 0:
            raise ValueError(f"{target_context}.min_duration_sec must be > 0")
        targets[target.target_id] = target

    return RevisitCase(
        case_dir=case_path,
        horizon_start=parse_iso_z(_require_str(mission, "horizon_start", "mission.json")),
        horizon_end=parse_iso_z(_require_str(mission, "horizon_end", "mission.json")),
        satellite_model=satellite_model,
        max_num_satellites=_require_int(assets, "max_num_satellites", "assets.json"),
        targets=targets,
    )
