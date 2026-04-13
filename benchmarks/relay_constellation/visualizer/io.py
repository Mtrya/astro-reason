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
    """
    Read UTF-8 text from the given Path and parse it as JSON.
    
    Parameters:
        path (Path): Path to the JSON file to read.
    
    Returns:
        dict[str, Any]: Parsed JSON object.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_iso_utc(value: str, *, field: str) -> datetime:
    """
    Parse an ISO-8601 timestamp string and return it as an aware UTC datetime.
    
    Whitespace is trimmed and timestamps ending with 'Z' or 'z' are treated as UTC. The function requires the input to include a timezone; otherwise it raises an error.
    
    Parameters:
        value (str): The timestamp string to parse.
        field (str): Context name used in error messages when raising ValueError.
    
    Returns:
        datetime: An aware datetime normalized to UTC.
    
    Raises:
        ValueError: If the trimmed timestamp is empty ("{field}: empty timestamp").
        ValueError: If the parsed timestamp has no timezone information ("{field}: timezone-aware timestamp required").
    """
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
    """
    Require and convert a numeric field from a payload dictionary.
    
    Parameters:
        payload (dict[str, Any]): Dictionary containing the field.
        key (str): Key name to retrieve from the payload.
        context (str): Context string used as a prefix in error messages.
    
    Returns:
        float: The value converted to float.
    
    Raises:
        ValueError: If `key` is not present in `payload`.
    """
    if key not in payload:
        raise ValueError(f"{context}: missing {key}")
    return float(payload[key])


def _require_str(payload: dict[str, Any], key: str, context: str) -> str:
    """
    Validate that the mapping contains a non-empty string under the given key and return it.
    
    Parameters:
    	payload (dict[str, Any]): Mapping to read the value from.
    	key (str): Key to look up in the mapping.
    	context (str): Context string used to format error messages.
    
    Returns:
    	str: The value associated with `key` as a non-empty string.
    
    Raises:
    	ValueError: If `key` is missing from `payload` or the associated value is not a non-empty string.
    """
    if key not in payload:
        raise ValueError(f"{context}: missing {key}")
    value = payload[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}: {key} must be a non-empty string")
    return value


def load_case(case_dir: Path | str) -> RelayCase:
    """
    Load and validate a relay visualization case from a directory containing manifest.json, network.json, and demands.json.
    
    Parameters:
        case_dir (Path | str): Path to a case directory that must contain `manifest.json`, `network.json`, and `demands.json`.
    
    Returns:
        RelayCase: Parsed and validated case containing a RelayManifest, backbone_satellites (mapping of satellite_id to RelaySatellite), ground_endpoints (mapping of endpoint_id to RelayEndpoint), sorted demands (list[RelayDemand]), and the resolved `case_dir` Path.
    
    Raises:
        ValueError: If required fields are missing or have invalid formats (including timestamp parsing and required string/number validations).
        KeyError: If required constraint keys (e.g., `max_isl_range_m`) are absent in the manifest constraints.
        OSError, json.JSONDecodeError, or other exceptions from underlying I/O, JSON parsing, numeric conversions, or coordinate conversion operations may also propagate.
    """
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
