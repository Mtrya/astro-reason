"""Case loading helpers for the relay_constellation visualizer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import brahe
import numpy as np


@dataclass(frozen=True)
class RelayManifest:
    case_id: str
    epoch: datetime
    horizon_start: datetime
    horizon_end: datetime
    routing_step_s: int
    max_isl_range_m: float
    max_ground_range_m: float | None


@dataclass(frozen=True)
class RelaySatellite:
    satellite_id: str
    state_eci_m_mps: np.ndarray


@dataclass(frozen=True)
class RelayEndpoint:
    endpoint_id: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    min_elevation_deg: float
    ecef_position_m: np.ndarray


@dataclass(frozen=True)
class RelayDemand:
    demand_id: str
    source_endpoint_id: str
    destination_endpoint_id: str
    start_time: datetime
    end_time: datetime
    weight: float


@dataclass(frozen=True)
class RelayCase:
    manifest: RelayManifest
    backbone_satellites: dict[str, RelaySatellite]
    ground_endpoints: dict[str, RelayEndpoint]
    demands: list[RelayDemand]
    case_dir: Path


def _read_json(path: Path) -> dict[str, Any]:
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


def _require_float(payload: dict[str, Any], key: str, context: str) -> float:
    if key not in payload:
        raise ValueError(f"{context}: missing {key}")
    return float(payload[key])


def _require_str(payload: dict[str, Any], key: str, context: str) -> str:
    if key not in payload:
        raise ValueError(f"{context}: missing {key}")
    value = payload[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}: {key} must be a non-empty string")
    return value


def load_case(case_dir: Path | str) -> RelayCase:
    case_dir = Path(case_dir).resolve()
    manifest_payload = _read_json(case_dir / "manifest.json")
    network_payload = _read_json(case_dir / "network.json")
    demands_payload = _read_json(case_dir / "demands.json")

    constraints = manifest_payload.get("constraints", {})
    manifest = RelayManifest(
        case_id=_require_str(manifest_payload, "case_id", "manifest"),
        epoch=_parse_iso_utc(_require_str(manifest_payload, "epoch", "manifest"), field="manifest.epoch"),
        horizon_start=_parse_iso_utc(
            _require_str(manifest_payload, "horizon_start", "manifest"),
            field="manifest.horizon_start",
        ),
        horizon_end=_parse_iso_utc(
            _require_str(manifest_payload, "horizon_end", "manifest"),
            field="manifest.horizon_end",
        ),
        routing_step_s=int(manifest_payload["routing_step_s"]),
        max_isl_range_m=float(constraints["max_isl_range_m"]),
        max_ground_range_m=(
            float(constraints["max_ground_range_m"])
            if "max_ground_range_m" in constraints
            else None
        ),
    )
    if manifest.horizon_end <= manifest.horizon_start:
        raise ValueError("manifest.horizon_end must be after horizon_start")
    if manifest.routing_step_s <= 0:
        raise ValueError("manifest.routing_step_s must be > 0")

    satellites: dict[str, RelaySatellite] = {}
    for index, row in enumerate(network_payload.get("backbone_satellites", [])):
        context = f"network.backbone_satellites[{index}]"
        satellite_id = _require_str(row, "satellite_id", context)
        satellites[satellite_id] = RelaySatellite(
            satellite_id=satellite_id,
            state_eci_m_mps=np.asarray(
                [
                    _require_float(row, "x_m", context),
                    _require_float(row, "y_m", context),
                    _require_float(row, "z_m", context),
                    _require_float(row, "vx_m_s", context),
                    _require_float(row, "vy_m_s", context),
                    _require_float(row, "vz_m_s", context),
                ],
                dtype=float,
            ),
        )

    endpoints: dict[str, RelayEndpoint] = {}
    for index, row in enumerate(network_payload.get("ground_endpoints", [])):
        context = f"network.ground_endpoints[{index}]"
        endpoint_id = _require_str(row, "endpoint_id", context)
        longitude_deg = _require_float(row, "longitude_deg", context)
        latitude_deg = _require_float(row, "latitude_deg", context)
        altitude_m = _require_float(row, "altitude_m", context)
        endpoints[endpoint_id] = RelayEndpoint(
            endpoint_id=endpoint_id,
            longitude_deg=longitude_deg,
            latitude_deg=latitude_deg,
            altitude_m=altitude_m,
            min_elevation_deg=_require_float(row, "min_elevation_deg", context),
            ecef_position_m=np.asarray(
                brahe.position_geodetic_to_ecef(
                    [longitude_deg, latitude_deg, altitude_m],
                    brahe.AngleFormat.DEGREES,
                ),
                dtype=float,
            ),
        )

    demands: list[RelayDemand] = []
    for index, row in enumerate(demands_payload.get("demanded_windows", [])):
        context = f"demands.demanded_windows[{index}]"
        demands.append(
            RelayDemand(
                demand_id=_require_str(row, "demand_id", context),
                source_endpoint_id=_require_str(row, "source_endpoint_id", context),
                destination_endpoint_id=_require_str(row, "destination_endpoint_id", context),
                start_time=_parse_iso_utc(
                    _require_str(row, "start_time", context),
                    field=f"{context}.start_time",
                ),
                end_time=_parse_iso_utc(
                    _require_str(row, "end_time", context),
                    field=f"{context}.end_time",
                ),
                weight=float(row.get("weight", 1.0)),
            )
        )

    demands.sort(key=lambda row: (row.start_time, row.end_time, row.demand_id))
    return RelayCase(
        manifest=manifest,
        backbone_satellites=satellites,
        ground_endpoints=endpoints,
        demands=demands,
        case_dir=case_dir,
    )
