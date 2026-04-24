"""Parse public relay_constellation case files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import json


def _parse_iso8601_z(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


@dataclass(frozen=True)
class Constraints:
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


@dataclass(frozen=True)
class Manifest:
    benchmark: str
    case_id: str
    constraints: Constraints
    epoch: datetime
    horizon_end: datetime
    horizon_start: datetime
    routing_step_s: int
    seed: int


@dataclass(frozen=True)
class BackboneSatellite:
    satellite_id: str
    x_m: float
    y_m: float
    z_m: float
    vx_m_s: float
    vy_m_s: float
    vz_m_s: float

    @property
    def state_eci_m_mps(self) -> tuple[float, float, float, float, float, float]:
        return (self.x_m, self.y_m, self.z_m, self.vx_m_s, self.vy_m_s, self.vz_m_s)


@dataclass(frozen=True)
class GroundEndpoint:
    endpoint_id: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    min_elevation_deg: float


@dataclass(frozen=True)
class DemandWindow:
    demand_id: str
    source_endpoint_id: str
    destination_endpoint_id: str
    start_time: datetime
    end_time: datetime
    weight: float


@dataclass(frozen=True)
class Network:
    backbone_satellites: tuple[BackboneSatellite, ...]
    ground_endpoints: tuple[GroundEndpoint, ...]


@dataclass(frozen=True)
class Demands:
    demanded_windows: tuple[DemandWindow, ...]


@dataclass(frozen=True)
class Case:
    manifest: Manifest
    network: Network
    demands: Demands


def _load_constraints(data: dict[str, Any]) -> Constraints:
    return Constraints(
        max_added_satellites=int(data["max_added_satellites"]),
        min_altitude_m=float(data["min_altitude_m"]),
        max_altitude_m=float(data["max_altitude_m"]),
        max_eccentricity=float(data["max_eccentricity"]) if data.get("max_eccentricity") is not None else None,
        min_inclination_deg=float(data["min_inclination_deg"]) if data.get("min_inclination_deg") is not None else None,
        max_inclination_deg=float(data["max_inclination_deg"]) if data.get("max_inclination_deg") is not None else None,
        max_isl_range_m=float(data["max_isl_range_m"]),
        max_links_per_satellite=int(data["max_links_per_satellite"]),
        max_links_per_endpoint=int(data["max_links_per_endpoint"]),
        max_ground_range_m=float(data["max_ground_range_m"]) if data.get("max_ground_range_m") is not None else None,
    )


def load_manifest(path: Path) -> Manifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Manifest(
        benchmark=str(data["benchmark"]),
        case_id=str(data["case_id"]),
        constraints=_load_constraints(data["constraints"]),
        epoch=_parse_iso8601_z(str(data["epoch"])),
        horizon_end=_parse_iso8601_z(str(data["horizon_end"])),
        horizon_start=_parse_iso8601_z(str(data["horizon_start"])),
        routing_step_s=int(data["routing_step_s"]),
        seed=int(data["seed"]),
    )


def load_network(path: Path) -> Network:
    data = json.loads(path.read_text(encoding="utf-8"))
    satellites = tuple(
        BackboneSatellite(
            satellite_id=str(s["satellite_id"]),
            x_m=float(s["x_m"]),
            y_m=float(s["y_m"]),
            z_m=float(s["z_m"]),
            vx_m_s=float(s["vx_m_s"]),
            vy_m_s=float(s["vy_m_s"]),
            vz_m_s=float(s["vz_m_s"]),
        )
        for s in data["backbone_satellites"]
    )
    endpoints = tuple(
        GroundEndpoint(
            endpoint_id=str(e["endpoint_id"]),
            latitude_deg=float(e["latitude_deg"]),
            longitude_deg=float(e["longitude_deg"]),
            altitude_m=float(e["altitude_m"]),
            min_elevation_deg=float(e["min_elevation_deg"]),
        )
        for e in data["ground_endpoints"]
    )
    return Network(backbone_satellites=satellites, ground_endpoints=endpoints)


def load_demands(path: Path) -> Demands:
    data = json.loads(path.read_text(encoding="utf-8"))
    windows = tuple(
        DemandWindow(
            demand_id=str(w["demand_id"]),
            source_endpoint_id=str(w["source_endpoint_id"]),
            destination_endpoint_id=str(w["destination_endpoint_id"]),
            start_time=_parse_iso8601_z(str(w["start_time"])),
            end_time=_parse_iso8601_z(str(w["end_time"])),
            weight=float(w["weight"]),
        )
        for w in data["demanded_windows"]
    )
    return Demands(demanded_windows=windows)


def load_case(case_dir: Path) -> Case:
    case_dir = Path(case_dir)
    manifest = load_manifest(case_dir / "manifest.json")
    network = load_network(case_dir / "network.json")
    demands = load_demands(case_dir / "demands.json")
    return Case(manifest=manifest, network=network, demands=demands)
