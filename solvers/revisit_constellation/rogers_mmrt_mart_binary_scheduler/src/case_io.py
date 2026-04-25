"""Public case parsing for the revisit constellation solver."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import json

import brahe
import numpy as np
import yaml


@dataclass(frozen=True)
class SensorModel:
    max_off_nadir_angle_deg: float
    max_range_m: float
    obs_discharge_rate_w: float


@dataclass(frozen=True)
class ResourceModel:
    battery_capacity_wh: float
    initial_battery_wh: float
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
    resource_model: ResourceModel
    attitude_model: AttitudeModel
    min_altitude_m: float
    max_altitude_m: float


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
    ecef_position_m: tuple[float, float, float]


@dataclass(frozen=True)
class RevisitCase:
    case_dir: Path
    assets_path: Path
    mission_path: Path
    horizon_start: datetime
    horizon_end: datetime
    satellite_model: SatelliteModel
    max_num_satellites: int
    targets: tuple[Target, ...]

    @property
    def horizon_duration_sec(self) -> float:
        return (self.horizon_end - self.horizon_start).total_seconds()


@dataclass(frozen=True)
class SolverConfig:
    sample_step_sec: float = 7200.0
    altitude_count: int = 1
    inclination_deg: tuple[float, ...] = (55.0, 97.6)
    raan_count: int = 4
    phase_count: int = 2
    max_slots: int = 16
    write_visibility_matrix: bool = True
    design_mode: str = "mmrt"
    design_backend: str = "auto"
    design_threshold_metric: str = "mmrt"
    design_satellite_count: int | None = None
    design_max_selected_slots: int = 4
    design_time_limit_sec: float = 10.0
    design_max_backend_slots: int = 40
    design_max_backend_time_samples: int = 200
    design_max_backend_variables: int = 20000
    design_max_backend_constraints: int = 50000
    fallback_exhaustive_max_combinations: int = 20000
    window_stride_sec: float = 600.0
    window_geometry_sample_step_sec: float = 10.0
    max_observation_windows: int = 5000
    max_windows_per_satellite_target: int = 100
    write_observation_windows: bool = False
    scheduler_backend: str = "auto"
    scheduler_time_limit_sec: float = 10.0
    scheduler_max_backend_windows: int = 3000
    scheduler_max_backend_conflicts: int = 25000
    scheduler_max_exact_combinations: int = 20000
    scheduler_max_selected_windows: int = 200
    scheduler_min_transition_gap_sec: float = 0.0
    local_repair_enabled: bool = True
    local_validation_geometry_sample_step_sec: float = 10.0
    local_battery_margin_wh: float = 0.0
    debug: bool = False


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_iso_z(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"expected ISO 8601 string, got {type(value).__name__}")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value!r}")
    return parsed.astimezone(UTC)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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
    if not isinstance(value, int | float):
        raise ValueError(f"{context}.{key} must be numeric")
    return float(value)


def _require_int(mapping: dict[str, Any], key: str, context: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{context}.{key} must be an integer")
    return value


def _target_ecef(longitude_deg: float, latitude_deg: float, altitude_m: float) -> tuple[float, float, float]:
    position = np.asarray(
        brahe.position_geodetic_to_ecef(
            [longitude_deg, latitude_deg, altitude_m],
            brahe.AngleFormat.DEGREES,
        ),
        dtype=float,
    )
    return tuple(float(item) for item in position)


def _parse_target(payload: dict[str, Any], index: int) -> Target:
    context = f"mission.json.targets[{index}]"
    longitude_deg = _require_float(payload, "longitude_deg", context)
    latitude_deg = _require_float(payload, "latitude_deg", context)
    altitude_m = _require_float(payload, "altitude_m", context)
    return Target(
        target_id=_require_str(payload, "id", context),
        name=_require_str(payload, "name", context),
        latitude_deg=latitude_deg,
        longitude_deg=longitude_deg,
        altitude_m=altitude_m,
        expected_revisit_period_hours=_require_float(
            payload, "expected_revisit_period_hours", context
        ),
        min_elevation_deg=_require_float(payload, "min_elevation_deg", context),
        max_slant_range_m=_require_float(payload, "max_slant_range_m", context),
        min_duration_sec=_require_float(payload, "min_duration_sec", context),
        ecef_position_m=_target_ecef(longitude_deg, latitude_deg, altitude_m),
    )


def _parse_satellite_model(payload: dict[str, Any]) -> SatelliteModel:
    context = "assets.json.satellite_model"
    sensor_payload = _require_mapping(payload.get("sensor"), f"{context}.sensor")
    resource_payload = _require_mapping(
        payload.get("resource_model"), f"{context}.resource_model"
    )
    attitude_payload = _require_mapping(
        payload.get("attitude_model"), f"{context}.attitude_model"
    )
    return SatelliteModel(
        model_name=_require_str(payload, "model_name", context),
        sensor=SensorModel(
            max_off_nadir_angle_deg=_require_float(
                sensor_payload, "max_off_nadir_angle_deg", f"{context}.sensor"
            ),
            max_range_m=_require_float(sensor_payload, "max_range_m", f"{context}.sensor"),
            obs_discharge_rate_w=_require_float(
                sensor_payload, "obs_discharge_rate_w", f"{context}.sensor"
            ),
        ),
        resource_model=ResourceModel(
            battery_capacity_wh=_require_float(
                resource_payload, "battery_capacity_wh", f"{context}.resource_model"
            ),
            initial_battery_wh=_require_float(
                resource_payload, "initial_battery_wh", f"{context}.resource_model"
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


def load_case(case_dir: str | Path) -> RevisitCase:
    case_path = Path(case_dir)
    assets_path = case_path / "assets.json"
    mission_path = case_path / "mission.json"
    if not case_path.exists():
        raise FileNotFoundError(f"case directory not found: {case_path}")
    if not assets_path.exists():
        raise FileNotFoundError(f"missing case file: {assets_path}")
    if not mission_path.exists():
        raise FileNotFoundError(f"missing case file: {mission_path}")

    assets = _require_mapping(load_json(assets_path), "assets.json")
    mission = _require_mapping(load_json(mission_path), "mission.json")
    satellite_model = _parse_satellite_model(
        _require_mapping(assets.get("satellite_model"), "assets.json.satellite_model")
    )
    max_num_satellites = _require_int(assets, "max_num_satellites", "assets.json")
    if max_num_satellites < 0:
        raise ValueError("assets.json.max_num_satellites must be non-negative")

    target_payloads = _require_list(mission.get("targets"), "mission.json.targets")
    targets = tuple(
        _parse_target(_require_mapping(item, f"mission.json.targets[{index}]"), index)
        for index, item in enumerate(target_payloads)
    )
    if len({target.target_id for target in targets}) != len(targets):
        raise ValueError("target IDs must be unique within a case")

    horizon_start = parse_iso_z(_require_str(mission, "horizon_start", "mission.json"))
    horizon_end = parse_iso_z(_require_str(mission, "horizon_end", "mission.json"))
    if horizon_end <= horizon_start:
        raise ValueError("mission.json horizon_end must be after horizon_start")

    return RevisitCase(
        case_dir=case_path,
        assets_path=assets_path,
        mission_path=mission_path,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        satellite_model=satellite_model,
        max_num_satellites=max_num_satellites,
        targets=targets,
    )


def _load_config_payload(config_dir: str | Path | None) -> dict[str, Any]:
    if not config_dir:
        return {}
    directory = Path(config_dir)
    if not directory.exists():
        return {}
    for filename in (
        "config.yaml",
        "config.yml",
        "config.json",
        "rogers_mmrt_mart_binary_scheduler.yaml",
        "rogers_mmrt_mart_binary_scheduler.yml",
        "rogers_mmrt_mart_binary_scheduler.json",
    ):
        path = directory / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            if path.suffix == ".json":
                payload = json.load(handle)
            else:
                payload = yaml.safe_load(handle) or {}
        return _require_mapping(payload, str(path))
    return {}


def load_solver_config(config_dir: str | Path | None) -> SolverConfig:
    payload = _load_config_payload(config_dir)
    raw_inclinations = payload.get("inclination_deg", SolverConfig.inclination_deg)
    if isinstance(raw_inclinations, int | float):
        inclinations = (float(raw_inclinations),)
    elif isinstance(raw_inclinations, list | tuple):
        inclinations = tuple(float(item) for item in raw_inclinations)
    else:
        raise ValueError("inclination_deg must be numeric or a list of numbers")
    config = SolverConfig(
        sample_step_sec=float(payload.get("sample_step_sec", SolverConfig.sample_step_sec)),
        altitude_count=int(payload.get("altitude_count", SolverConfig.altitude_count)),
        inclination_deg=inclinations,
        raan_count=int(payload.get("raan_count", SolverConfig.raan_count)),
        phase_count=int(payload.get("phase_count", SolverConfig.phase_count)),
        max_slots=int(payload.get("max_slots", SolverConfig.max_slots)),
        write_visibility_matrix=bool(
            payload.get("write_visibility_matrix", SolverConfig.write_visibility_matrix)
        ),
        design_mode=str(payload.get("design_mode", SolverConfig.design_mode)),
        design_backend=str(payload.get("design_backend", SolverConfig.design_backend)),
        design_threshold_metric=str(
            payload.get("design_threshold_metric", SolverConfig.design_threshold_metric)
        ),
        design_satellite_count=(
            None
            if payload.get("design_satellite_count") is None
            else int(payload["design_satellite_count"])
        ),
        design_max_selected_slots=int(
            payload.get("design_max_selected_slots", SolverConfig.design_max_selected_slots)
        ),
        design_time_limit_sec=float(
            payload.get("design_time_limit_sec", SolverConfig.design_time_limit_sec)
        ),
        design_max_backend_slots=int(
            payload.get("design_max_backend_slots", SolverConfig.design_max_backend_slots)
        ),
        design_max_backend_time_samples=int(
            payload.get(
                "design_max_backend_time_samples",
                SolverConfig.design_max_backend_time_samples,
            )
        ),
        design_max_backend_variables=int(
            payload.get(
                "design_max_backend_variables",
                SolverConfig.design_max_backend_variables,
            )
        ),
        design_max_backend_constraints=int(
            payload.get(
                "design_max_backend_constraints",
                SolverConfig.design_max_backend_constraints,
            )
        ),
        fallback_exhaustive_max_combinations=int(
            payload.get(
                "fallback_exhaustive_max_combinations",
                SolverConfig.fallback_exhaustive_max_combinations,
            )
        ),
        window_stride_sec=float(
            payload.get("window_stride_sec", SolverConfig.window_stride_sec)
        ),
        window_geometry_sample_step_sec=float(
            payload.get(
                "window_geometry_sample_step_sec",
                SolverConfig.window_geometry_sample_step_sec,
            )
        ),
        max_observation_windows=int(
            payload.get("max_observation_windows", SolverConfig.max_observation_windows)
        ),
        max_windows_per_satellite_target=int(
            payload.get(
                "max_windows_per_satellite_target",
                SolverConfig.max_windows_per_satellite_target,
            )
        ),
        write_observation_windows=bool(
            payload.get(
                "write_observation_windows",
                SolverConfig.write_observation_windows,
            )
        ),
        scheduler_backend=str(
            payload.get("scheduler_backend", SolverConfig.scheduler_backend)
        ),
        scheduler_time_limit_sec=float(
            payload.get("scheduler_time_limit_sec", SolverConfig.scheduler_time_limit_sec)
        ),
        scheduler_max_backend_windows=int(
            payload.get(
                "scheduler_max_backend_windows",
                SolverConfig.scheduler_max_backend_windows,
            )
        ),
        scheduler_max_backend_conflicts=int(
            payload.get(
                "scheduler_max_backend_conflicts",
                SolverConfig.scheduler_max_backend_conflicts,
            )
        ),
        scheduler_max_exact_combinations=int(
            payload.get(
                "scheduler_max_exact_combinations",
                SolverConfig.scheduler_max_exact_combinations,
            )
        ),
        scheduler_max_selected_windows=int(
            payload.get(
                "scheduler_max_selected_windows",
                SolverConfig.scheduler_max_selected_windows,
            )
        ),
        scheduler_min_transition_gap_sec=float(
            payload.get(
                "scheduler_min_transition_gap_sec",
                SolverConfig.scheduler_min_transition_gap_sec,
            )
        ),
        local_repair_enabled=bool(
            payload.get("local_repair_enabled", SolverConfig.local_repair_enabled)
        ),
        local_validation_geometry_sample_step_sec=float(
            payload.get(
                "local_validation_geometry_sample_step_sec",
                SolverConfig.local_validation_geometry_sample_step_sec,
            )
        ),
        local_battery_margin_wh=float(
            payload.get("local_battery_margin_wh", SolverConfig.local_battery_margin_wh)
        ),
        debug=bool(payload.get("debug", SolverConfig.debug)),
    )
    if config.sample_step_sec <= 0.0:
        raise ValueError("sample_step_sec must be positive")
    if config.altitude_count <= 0:
        raise ValueError("altitude_count must be positive")
    if config.raan_count <= 0 or config.phase_count <= 0:
        raise ValueError("raan_count and phase_count must be positive")
    if config.max_slots <= 0:
        raise ValueError("max_slots must be positive")
    if not config.inclination_deg:
        raise ValueError("at least one inclination is required")
    if config.design_mode not in {"mmrt", "mart", "threshold_first", "hybrid"}:
        raise ValueError("design_mode must be one of mmrt, mart, threshold_first, hybrid")
    if config.design_backend not in {"auto", "pulp", "fallback"}:
        raise ValueError("design_backend must be one of auto, pulp, fallback")
    if config.design_threshold_metric not in {"mmrt", "mart"}:
        raise ValueError("design_threshold_metric must be one of mmrt, mart")
    if config.design_satellite_count is not None and config.design_satellite_count < 0:
        raise ValueError("design_satellite_count must be non-negative when set")
    if config.design_max_selected_slots < 0:
        raise ValueError("design_max_selected_slots must be non-negative")
    if config.design_time_limit_sec <= 0.0:
        raise ValueError("design_time_limit_sec must be positive")
    if config.design_max_backend_slots <= 0:
        raise ValueError("design_max_backend_slots must be positive")
    if config.design_max_backend_time_samples <= 0:
        raise ValueError("design_max_backend_time_samples must be positive")
    if config.design_max_backend_variables <= 0:
        raise ValueError("design_max_backend_variables must be positive")
    if config.design_max_backend_constraints <= 0:
        raise ValueError("design_max_backend_constraints must be positive")
    if config.fallback_exhaustive_max_combinations <= 0:
        raise ValueError("fallback_exhaustive_max_combinations must be positive")
    if config.window_stride_sec <= 0.0:
        raise ValueError("window_stride_sec must be positive")
    if config.window_geometry_sample_step_sec <= 0.0:
        raise ValueError("window_geometry_sample_step_sec must be positive")
    if config.max_observation_windows <= 0:
        raise ValueError("max_observation_windows must be positive")
    if config.max_windows_per_satellite_target <= 0:
        raise ValueError("max_windows_per_satellite_target must be positive")
    if config.scheduler_backend not in {"auto", "pulp_binary", "pulp_relaxed", "fallback"}:
        raise ValueError(
            "scheduler_backend must be one of auto, pulp_binary, pulp_relaxed, fallback"
        )
    if config.scheduler_time_limit_sec <= 0.0:
        raise ValueError("scheduler_time_limit_sec must be positive")
    if config.scheduler_max_backend_windows <= 0:
        raise ValueError("scheduler_max_backend_windows must be positive")
    if config.scheduler_max_backend_conflicts < 0:
        raise ValueError("scheduler_max_backend_conflicts must be non-negative")
    if config.scheduler_max_exact_combinations <= 0:
        raise ValueError("scheduler_max_exact_combinations must be positive")
    if config.scheduler_max_selected_windows <= 0:
        raise ValueError("scheduler_max_selected_windows must be positive")
    if config.scheduler_min_transition_gap_sec < 0.0:
        raise ValueError("scheduler_min_transition_gap_sec must be non-negative")
    if config.local_validation_geometry_sample_step_sec <= 0.0:
        raise ValueError("local_validation_geometry_sample_step_sec must be positive")
    if config.local_battery_margin_wh < 0.0:
        raise ValueError("local_battery_margin_wh must be non-negative")
    return config
