"""Standalone case parsing for relay_constellation. No benchmark imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import json

import numpy as np


NUMERICAL_EPS = 1e-9


@dataclass(frozen=True)
class Manifest:
    case_id: str
    epoch: datetime
    horizon_start: datetime
    horizon_end: datetime
    routing_step_s: int
    max_added_satellites: int
    min_altitude_m: float
    max_altitude_m: float
    max_eccentricity: float | None
    min_inclination_deg: float | None
    max_inclination_deg: float | None
    max_isl_range_m: float
    max_links_per_satellite: int
    max_links_per_endpoint: int
    max_ground_range_m: float | None

    @property
    def total_samples(self) -> int:
        horizon_seconds = (self.horizon_end - self.horizon_start).total_seconds()
        quotient = horizon_seconds / self.routing_step_s
        if not quotient.is_integer():
            raise ValueError("horizon must be exactly divisible by routing_step_s")
        return int(quotient)


@dataclass(frozen=True)
class Satellite:
    satellite_id: str
    state_eci_m_mps: np.ndarray = field(repr=False)


@dataclass(frozen=True)
class Endpoint:
    endpoint_id: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    min_elevation_deg: float
    ecef_position_m: np.ndarray = field(repr=False)


@dataclass(frozen=True)
class Demand:
    demand_id: str
    source_endpoint_id: str
    destination_endpoint_id: str
    start_time: datetime
    end_time: datetime
    weight: float


@dataclass(frozen=True)
class Case:
    case_dir: Path
    manifest: Manifest
    backbone_satellites: dict[str, Satellite]
    ground_endpoints: dict[str, Endpoint]
    demands: list[Demand]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_iso_utc(value: str, *, field: str) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError(f"{field}: empty timestamp")
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"{field}: timezone-aware timestamp required")
    return parsed.astimezone(UTC)


def _require_mapping(payload: Any, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{context} must be a JSON object")
    return payload


def _require_list(payload: Any, context: str) -> list[Any]:
    if not isinstance(payload, list):
        raise ValueError(f"{context} must be a JSON array")
    return payload


def _require_str(payload: dict[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def _require_float(payload: dict[str, Any], key: str, context: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"{context}.{key} must be numeric")
    return float(value)


def _require_int(payload: dict[str, Any], key: str, context: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{context}.{key} must be an integer")
    return value


def load_case(case_dir: str | Path) -> Case:
    case_path = Path(case_dir).resolve()
    manifest_path = case_path / "manifest.json"
    network_path = case_path / "network.json"
    demands_path = case_path / "demands.json"

    if not case_path.is_dir():
        raise FileNotFoundError(f"Case directory not found: {case_path}")
    for p in (manifest_path, network_path, demands_path):
        if not p.is_file():
            raise FileNotFoundError(f"Missing case file: {p}")

    manifest_payload = _require_mapping(_load_json(manifest_path), "manifest.json")
    network_payload = _require_mapping(_load_json(network_path), "network.json")
    demands_payload = _require_mapping(_load_json(demands_path), "demands.json")
    constraints = _require_mapping(manifest_payload.get("constraints"), "manifest.json.constraints")

    manifest = Manifest(
        case_id=_require_str(manifest_payload, "case_id", "manifest.json"),
        epoch=_parse_iso_utc(_require_str(manifest_payload, "epoch", "manifest.json"), field="manifest.json.epoch"),
        horizon_start=_parse_iso_utc(
            _require_str(manifest_payload, "horizon_start", "manifest.json"),
            field="manifest.json.horizon_start",
        ),
        horizon_end=_parse_iso_utc(
            _require_str(manifest_payload, "horizon_end", "manifest.json"),
            field="manifest.json.horizon_end",
        ),
        routing_step_s=_require_int(manifest_payload, "routing_step_s", "manifest.json"),
        max_added_satellites=_require_int(constraints, "max_added_satellites", "manifest.json.constraints"),
        min_altitude_m=_require_float(constraints, "min_altitude_m", "manifest.json.constraints"),
        max_altitude_m=_require_float(constraints, "max_altitude_m", "manifest.json.constraints"),
        max_eccentricity=_require_float(constraints, "max_eccentricity", "manifest.json.constraints")
        if "max_eccentricity" in constraints
        else None,
        min_inclination_deg=_require_float(constraints, "min_inclination_deg", "manifest.json.constraints")
        if "min_inclination_deg" in constraints
        else None,
        max_inclination_deg=_require_float(constraints, "max_inclination_deg", "manifest.json.constraints")
        if "max_inclination_deg" in constraints
        else None,
        max_isl_range_m=_require_float(constraints, "max_isl_range_m", "manifest.json.constraints"),
        max_links_per_satellite=_require_int(constraints, "max_links_per_satellite", "manifest.json.constraints"),
        max_links_per_endpoint=_require_int(constraints, "max_links_per_endpoint", "manifest.json.constraints"),
        max_ground_range_m=_require_float(constraints, "max_ground_range_m", "manifest.json.constraints")
        if "max_ground_range_m" in constraints
        else None,
    )
    if manifest.horizon_end <= manifest.horizon_start:
        raise ValueError("manifest.json.horizon_end must be after horizon_start")
    if manifest.routing_step_s <= 0:
        raise ValueError("manifest.json.routing_step_s must be positive")
    _ = manifest.total_samples

    backbone_satellites: dict[str, Satellite] = {}
    for index, row in enumerate(_require_list(network_payload.get("backbone_satellites"), "network.json.backbone_satellites")):
        payload = _require_mapping(row, f"network.json.backbone_satellites[{index}]")
        satellite_id = _require_str(payload, "satellite_id", f"network.json.backbone_satellites[{index}]")
        if satellite_id in backbone_satellites:
            raise ValueError(f"Duplicate backbone satellite_id: {satellite_id}")
        backbone_satellites[satellite_id] = Satellite(
            satellite_id=satellite_id,
            state_eci_m_mps=np.asarray(
                [
                    _require_float(payload, "x_m", f"network.json.backbone_satellites[{index}]"),
                    _require_float(payload, "y_m", f"network.json.backbone_satellites[{index}]"),
                    _require_float(payload, "z_m", f"network.json.backbone_satellites[{index}]"),
                    _require_float(payload, "vx_m_s", f"network.json.backbone_satellites[{index}]"),
                    _require_float(payload, "vy_m_s", f"network.json.backbone_satellites[{index}]"),
                    _require_float(payload, "vz_m_s", f"network.json.backbone_satellites[{index}]"),
                ],
                dtype=float,
            ),
        )

    # We need brahe for geodetic->ECEF. Import locally to keep dependencies clear.
    import brahe

    ground_endpoints: dict[str, Endpoint] = {}
    for index, row in enumerate(_require_list(network_payload.get("ground_endpoints"), "network.json.ground_endpoints")):
        payload = _require_mapping(row, f"network.json.ground_endpoints[{index}]")
        endpoint_id = _require_str(payload, "endpoint_id", f"network.json.ground_endpoints[{index}]")
        if endpoint_id in ground_endpoints:
            raise ValueError(f"Duplicate endpoint_id: {endpoint_id}")
        longitude_deg = _require_float(payload, "longitude_deg", f"network.json.ground_endpoints[{index}]")
        latitude_deg = _require_float(payload, "latitude_deg", f"network.json.ground_endpoints[{index}]")
        altitude_m = _require_float(payload, "altitude_m", f"network.json.ground_endpoints[{index}]")
        ecef_position_m = np.asarray(
            brahe.position_geodetic_to_ecef(
                [longitude_deg, latitude_deg, altitude_m],
                brahe.AngleFormat.DEGREES,
            ),
            dtype=float,
        )
        ground_endpoints[endpoint_id] = Endpoint(
            endpoint_id=endpoint_id,
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            altitude_m=altitude_m,
            min_elevation_deg=_require_float(payload, "min_elevation_deg", f"network.json.ground_endpoints[{index}]"),
            ecef_position_m=ecef_position_m,
        )

    demands: list[Demand] = []
    seen_demand_ids: set[str] = set()
    for index, row in enumerate(_require_list(demands_payload.get("demanded_windows"), "demands.json.demanded_windows")):
        payload = _require_mapping(row, f"demands.json.demanded_windows[{index}]")
        demand_id = _require_str(payload, "demand_id", f"demands.json.demanded_windows[{index}]")
        source_endpoint_id = _require_str(payload, "source_endpoint_id", f"demands.json.demanded_windows[{index}]")
        destination_endpoint_id = _require_str(payload, "destination_endpoint_id", f"demands.json.demanded_windows[{index}]")
        if demand_id in seen_demand_ids:
            raise ValueError(f"Duplicate demand_id: {demand_id}")
        seen_demand_ids.add(demand_id)
        if source_endpoint_id not in ground_endpoints:
            raise ValueError(f"Unknown demand source endpoint: {source_endpoint_id}")
        if destination_endpoint_id not in ground_endpoints:
            raise ValueError(f"Unknown demand destination endpoint: {destination_endpoint_id}")
        start_time = _parse_iso_utc(_require_str(payload, "start_time", f"demands.json.demanded_windows[{index}]"), field=f"demands.json.demanded_windows[{index}].start_time")
        end_time = _parse_iso_utc(_require_str(payload, "end_time", f"demands.json.demanded_windows[{index}]"), field=f"demands.json.demanded_windows[{index}].end_time")
        if end_time <= start_time:
            raise ValueError(f"Demand {demand_id} must have end_time after start_time")
        weight = _require_float(payload, "weight", f"demands.json.demanded_windows[{index}]") if "weight" in payload else 1.0
        demands.append(
            Demand(
                demand_id=demand_id,
                source_endpoint_id=source_endpoint_id,
                destination_endpoint_id=destination_endpoint_id,
                start_time=start_time,
                end_time=end_time,
                weight=weight,
            )
        )

    demands.sort(key=lambda row: (row.start_time, row.end_time, row.demand_id))
    return Case(
        case_dir=case_path,
        manifest=manifest,
        backbone_satellites=backbone_satellites,
        ground_endpoints=ground_endpoints,
        demands=demands,
    )
