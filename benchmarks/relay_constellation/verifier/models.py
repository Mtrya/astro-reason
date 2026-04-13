"""Shared data models for the relay_constellation verifier."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import json

import numpy as np


DEFAULT_DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"
LIGHT_SPEED_M_S = 299_792_458.0
NUMERICAL_EPS = 1e-9


@dataclass(frozen=True)
class RelayManifest:
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
        return int(round(horizon_seconds / self.routing_step_s))


@dataclass(frozen=True)
class RelaySatellite:
    satellite_id: str
    state_eci_m_mps: np.ndarray = field(repr=False)


@dataclass(frozen=True)
class RelayEndpoint:
    endpoint_id: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    min_elevation_deg: float
    ecef_position_m: np.ndarray = field(repr=False)


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
    case_dir: Path
    manifest: RelayManifest
    backbone_satellites: dict[str, RelaySatellite]
    ground_endpoints: dict[str, RelayEndpoint]
    demands: list[RelayDemand]


@dataclass(frozen=True)
class RelayAction:
    action_type: str
    start_time: datetime
    end_time: datetime
    endpoint_id: str | None = None
    satellite_id: str | None = None
    satellite_id_1: str | None = None
    satellite_id_2: str | None = None


@dataclass(frozen=True)
class RelaySolution:
    added_satellites: dict[str, RelaySatellite]
    actions: list[RelayAction]


@dataclass(frozen=True)
class OrbitSummary:
    satellite_id: str
    semi_major_axis_m: float
    eccentricity: float
    inclination_deg: float
    perigee_altitude_m: float
    apogee_altitude_m: float

    def to_dict(self) -> dict[str, float | str]:
        return {
            "satellite_id": self.satellite_id,
            "semi_major_axis_m": self.semi_major_axis_m,
            "eccentricity": self.eccentricity,
            "inclination_deg": self.inclination_deg,
            "perigee_altitude_m": self.perigee_altitude_m,
            "apogee_altitude_m": self.apogee_altitude_m,
        }


@dataclass(frozen=True)
class ValidatedAction:
    action_index: int
    action_type: str
    node_a: str
    node_b: str
    link_key: tuple[str, ...]
    sample_indices: tuple[int, ...]
    distances_m_by_sample: dict[int, float] = field(repr=False)

    @property
    def action_id(self) -> str:
        return f"action_{self.action_index:04d}"


@dataclass(frozen=True)
class PathCandidate:
    nodes: tuple[str, ...]
    edge_ids: tuple[str, ...]
    total_distance_m: float


@dataclass
class VerificationResult:
    valid: bool
    metrics: dict[str, Any]
    violations: list[str]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "metrics": self.metrics,
            "violations": self.violations,
            "diagnostics": self.diagnostics,
        }

    def __str__(self) -> str:  # pragma: no cover - formatting helper
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)
