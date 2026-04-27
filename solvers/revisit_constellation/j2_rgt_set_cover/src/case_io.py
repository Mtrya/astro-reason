"""Case and config loading for the standalone J2 RGT solver."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import json

import yaml

from .time_utils import parse_iso_z


@dataclass(frozen=True, slots=True)
class SatelliteModel:
    min_altitude_m: float
    max_altitude_m: float


@dataclass(frozen=True, slots=True)
class Target:
    target_id: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    expected_revisit_period_hours: float


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
    satellite_model = SatelliteModel(
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

    targets: dict[str, Target] = {}
    for index, target_raw in enumerate(
        _require_list(mission.get("targets"), "mission.json.targets")
    ):
        target_map = _require_mapping(target_raw, f"mission.json.targets[{index}]")
        target = Target(
            target_id=_require_str(target_map, "id", f"mission.json.targets[{index}]"),
            latitude_deg=_require_float(
                target_map, "latitude_deg", f"mission.json.targets[{index}]"
            ),
            longitude_deg=_require_float(
                target_map, "longitude_deg", f"mission.json.targets[{index}]"
            ),
            altitude_m=_require_float(
                target_map, "altitude_m", f"mission.json.targets[{index}]"
            ),
            expected_revisit_period_hours=_require_float(
                target_map,
                "expected_revisit_period_hours",
                f"mission.json.targets[{index}]",
            ),
        )
        if target.target_id in targets:
            raise ValueError(f"duplicate target id: {target.target_id}")
        targets[target.target_id] = target

    return RevisitCase(
        case_dir=case_path,
        horizon_start=parse_iso_z(_require_str(mission, "horizon_start", "mission.json")),
        horizon_end=parse_iso_z(_require_str(mission, "horizon_end", "mission.json")),
        satellite_model=satellite_model,
        max_num_satellites=_require_int(assets, "max_num_satellites", "assets.json"),
        targets=targets,
    )
