"""Case and solution loading for the revisit_constellation verifier."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import json

import brahe
import numpy as np

from .models import (
    Action,
    AttitudeModel,
    GroundStation,
    Instance,
    ResourceModel,
    SatelliteDefinition,
    SatelliteModel,
    SensorModel,
    Solution,
    Target,
    TerminalModel,
)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_iso8601_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Expected ISO 8601 timestamp string, got {type(value).__name__}")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include timezone information: {value!r}")
    return parsed.astimezone(UTC)


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


def _require_float(mapping: dict[str, Any], key: str, context: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"{context}.{key} must be numeric")
    return float(value)


def _require_int(mapping: dict[str, Any], key: str, context: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{context}.{key} must be an integer")
    return value


def _geodetic_to_ecef(longitude_deg: float, latitude_deg: float, altitude_m: float) -> np.ndarray:
    return np.asarray(
        brahe.position_geodetic_to_ecef(
            [longitude_deg, latitude_deg, altitude_m],
            brahe.AngleFormat.DEGREES,
        ),
        dtype=float,
    )


def _parse_ground_station(payload: dict[str, Any], index: int) -> GroundStation:
    context = f"assets.json.ground_stations[{index}]"
    return GroundStation(
        station_id=_require_str(payload, "id", context),
        name=_require_str(payload, "name", context),
        latitude_deg=_require_float(payload, "latitude_deg", context),
        longitude_deg=_require_float(payload, "longitude_deg", context),
        altitude_m=_require_float(payload, "altitude_m", context),
        min_elevation_deg=_require_float(payload, "min_elevation_deg", context),
        min_duration_sec=_require_float(payload, "min_duration_sec", context),
        ecef_position_m=_geodetic_to_ecef(
            _require_float(payload, "longitude_deg", context),
            _require_float(payload, "latitude_deg", context),
            _require_float(payload, "altitude_m", context),
        ),
    )


def _parse_target(payload: dict[str, Any], index: int) -> Target:
    context = f"mission.json.targets[{index}]"
    return Target(
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
        ecef_position_m=_geodetic_to_ecef(
            _require_float(payload, "longitude_deg", context),
            _require_float(payload, "latitude_deg", context),
            _require_float(payload, "altitude_m", context),
        ),
    )


def _parse_satellite_model(payload: dict[str, Any]) -> SatelliteModel:
    context = "assets.json.satellite_model"
    sensor_payload = _require_mapping(payload.get("sensor"), f"{context}.sensor")
    terminals_payload = _require_list(payload.get("terminals"), f"{context}.terminals")
    resource_payload = _require_mapping(
        payload.get("resource_model"), f"{context}.resource_model"
    )
    attitude_payload = _require_mapping(
        payload.get("attitude_model"), f"{context}.attitude_model"
    )

    terminals = tuple(
        TerminalModel(
            downlink_release_rate_mbps=_require_float(
                _require_mapping(item, f"{context}.terminals[{index}]"),
                "downlink_release_rate_mbps",
                f"{context}.terminals[{index}]",
            ),
            downlink_discharge_rate_w=_require_float(
                _require_mapping(item, f"{context}.terminals[{index}]"),
                "downlink_discharge_rate_w",
                f"{context}.terminals[{index}]",
            ),
        )
        for index, item in enumerate(terminals_payload)
    )
    if not terminals:
        raise ValueError(f"{context}.terminals must contain at least one terminal")

    first_terminal = terminals[0]
    for terminal in terminals[1:]:
        if terminal != first_terminal:
            raise ValueError(
                "assets.json.satellite_model.terminals must use identical terminal "
                "profiles in phase 1 because actions do not identify a terminal"
            )

    return SatelliteModel(
        model_name=_require_str(payload, "model_name", context),
        sensor=SensorModel(
            field_of_view_half_angle_deg=_require_float(
                sensor_payload, "field_of_view_half_angle_deg", f"{context}.sensor"
            ),
            max_range_m=_require_float(
                sensor_payload, "max_range_m", f"{context}.sensor"
            ),
            obs_discharge_rate_w=_require_float(
                sensor_payload, "obs_discharge_rate_w", f"{context}.sensor"
            ),
            obs_store_rate_mbps=_require_float(
                sensor_payload, "obs_store_rate_mbps", f"{context}.sensor"
            ),
        ),
        terminals=terminals,
        resource_model=ResourceModel(
            battery_capacity_wh=_require_float(
                resource_payload, "battery_capacity_wh", f"{context}.resource_model"
            ),
            storage_capacity_mb=_require_float(
                resource_payload, "storage_capacity_mb", f"{context}.resource_model"
            ),
            initial_battery_wh=_require_float(
                resource_payload, "initial_battery_wh", f"{context}.resource_model"
            ),
            initial_storage_mb=_require_float(
                resource_payload, "initial_storage_mb", f"{context}.resource_model"
            ),
            idle_discharge_rate_w=_require_float(
                resource_payload, "idle_discharge_rate_w", f"{context}.resource_model"
            ),
            sunlight_charge_rate_w=_require_float(
                resource_payload, "sunlight_charge_rate_w", f"{context}.resource_model"
            ),
        ),
        attitude_model=AttitudeModel(
            max_slew_velocity_deg_per_sec=_require_float(
                attitude_payload,
                "max_slew_velocity_deg_per_sec",
                f"{context}.attitude_model",
            ),
            max_slew_acceleration_deg_per_sec2=_require_float(
                attitude_payload,
                "max_slew_acceleration_deg_per_sec2",
                f"{context}.attitude_model",
            ),
            settling_time_sec=_require_float(
                attitude_payload, "settling_time_sec", f"{context}.attitude_model"
            ),
            maneuver_discharge_rate_w=_require_float(
                attitude_payload,
                "maneuver_discharge_rate_w",
                f"{context}.attitude_model",
            ),
        ),
        min_altitude_m=_require_float(payload, "min_altitude_m", context),
        max_altitude_m=_require_float(payload, "max_altitude_m", context),
    )


def load_case(case_dir: str | Path) -> Instance:
    case_path = Path(case_dir)
    assets_path = case_path / "assets.json"
    mission_path = case_path / "mission.json"

    if not case_path.exists():
        raise FileNotFoundError(f"Case directory not found: {case_path}")
    if not assets_path.exists():
        raise FileNotFoundError(f"Missing case file: {assets_path}")
    if not mission_path.exists():
        raise FileNotFoundError(f"Missing case file: {mission_path}")

    assets_payload = _require_mapping(_load_json(assets_path), "assets.json")
    mission_payload = _require_mapping(_load_json(mission_path), "mission.json")

    satellite_model = _parse_satellite_model(
        _require_mapping(assets_payload.get("satellite_model"), "assets.json.satellite_model")
    )
    max_num_satellites = _require_int(assets_payload, "max_num_satellites", "assets.json")
    if max_num_satellites < 0:
        raise ValueError("assets.json.max_num_satellites must be non-negative")

    ground_stations_list = _require_list(
        assets_payload.get("ground_stations"), "assets.json.ground_stations"
    )
    targets_list = _require_list(mission_payload.get("targets"), "mission.json.targets")

    ground_stations = {
        station.station_id: station
        for station in (
            _parse_ground_station(
                _require_mapping(item, f"assets.json.ground_stations[{index}]"), index
            )
            for index, item in enumerate(ground_stations_list)
        )
    }
    if len(ground_stations) != len(ground_stations_list):
        raise ValueError("Ground station IDs must be unique within a case")

    targets = {
        target.target_id: target
        for target in (
            _parse_target(_require_mapping(item, f"mission.json.targets[{index}]"), index)
            for index, item in enumerate(targets_list)
        )
    }
    if len(targets) != len(targets_list):
        raise ValueError("Target IDs must be unique within a case")

    horizon_start = _parse_iso8601_utc(
        _require_str(mission_payload, "horizon_start", "mission.json")
    )
    horizon_end = _parse_iso8601_utc(
        _require_str(mission_payload, "horizon_end", "mission.json")
    )
    if horizon_end <= horizon_start:
        raise ValueError("mission.json horizon_end must be after horizon_start")

    return Instance(
        case_dir=case_path,
        assets_path=assets_path,
        mission_path=mission_path,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        satellite_model=satellite_model,
        max_num_satellites=max_num_satellites,
        ground_stations=ground_stations,
        targets=targets,
    )


def _parse_satellite_definition(payload: dict[str, Any], index: int) -> SatelliteDefinition:
    context = f"solution.json.satellites[{index}]"
    return SatelliteDefinition(
        satellite_id=_require_str(payload, "satellite_id", context),
        state_eci_m_mps=np.asarray(
            [
                _require_float(payload, "x_m", context),
                _require_float(payload, "y_m", context),
                _require_float(payload, "z_m", context),
                _require_float(payload, "vx_m_s", context),
                _require_float(payload, "vy_m_s", context),
                _require_float(payload, "vz_m_s", context),
            ],
            dtype=float,
        ),
    )


def _parse_action(payload: dict[str, Any], index: int) -> Action:
    context = f"solution.json.actions[{index}]"
    action_type = _require_str(payload, "action_type", context)
    satellite_id = _require_str(payload, "satellite_id", context)
    start = _parse_iso8601_utc(_require_str(payload, "start", context))
    end = _parse_iso8601_utc(_require_str(payload, "end", context))
    target_id = payload.get("target_id")
    station_id = payload.get("station_id")

    if target_id is not None and not isinstance(target_id, str):
        raise ValueError(f"{context}.target_id must be a string when present")
    if station_id is not None and not isinstance(station_id, str):
        raise ValueError(f"{context}.station_id must be a string when present")

    return Action(
        action_type=action_type,
        satellite_id=satellite_id,
        start=start,
        end=end,
        target_id=target_id,
        station_id=station_id,
    )


def load_solution(solution_path: str | Path) -> Solution:
    payload = _require_mapping(_load_json(Path(solution_path)), "solution.json")
    satellites_payload = _require_list(payload.get("satellites"), "solution.json.satellites")
    actions_payload = _require_list(payload.get("actions"), "solution.json.actions")

    satellites: dict[str, SatelliteDefinition] = {}
    for index, item in enumerate(satellites_payload):
        satellite = _parse_satellite_definition(
            _require_mapping(item, f"solution.json.satellites[{index}]"), index
        )
        if satellite.satellite_id in satellites:
            raise ValueError(f"Duplicate satellite_id in solution: {satellite.satellite_id}")
        satellites[satellite.satellite_id] = satellite

    actions = [
        _parse_action(_require_mapping(item, f"solution.json.actions[{index}]"), index)
        for index, item in enumerate(actions_payload)
    ]
    return Solution(satellites=satellites, actions=actions)
