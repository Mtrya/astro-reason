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


@dataclass(frozen=True)
class ActionFailure:
    action_index: int
    action_type: str
    reason: str
    node_a: str | None
    node_b: str | None
    sample_index: int | None
    time: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_index": self.action_index,
            "action_type": self.action_type,
            "reason": self.reason,
            "node_a": self.node_a,
            "node_b": self.node_b,
            "sample_index": self.sample_index,
            "time": self.time.isoformat().replace("+00:00", "Z")
            if self.time is not None
            else None,
        }


@dataclass(frozen=True)
class SampleRouteAssignment:
    demand_id: str
    nodes: tuple[str, ...]
    edge_ids: tuple[str, ...]
    total_distance_m: float
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "demand_id": self.demand_id,
            "nodes": list(self.nodes),
            "edge_ids": list(self.edge_ids),
            "total_distance_m": self.total_distance_m,
            "latency_ms": self.latency_ms,
        }


@dataclass(frozen=True)
class SampleAllocation:
    sample_index: int
    time: datetime
    active_demand_ids: tuple[str, ...]
    served_routes: tuple[SampleRouteAssignment, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_index": self.sample_index,
            "time": self.time.isoformat().replace("+00:00", "Z"),
            "active_demand_ids": list(self.active_demand_ids),
            "served_routes": [route.to_dict() for route in self.served_routes],
        }


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


@dataclass(frozen=True)
class SolutionAnalysis:
    case: RelayCase
    solution: RelaySolution
    result: VerificationResult
    propagation_sample_indices: tuple[int, ...]
    demand_sample_indices_by_id: dict[str, tuple[int, ...]]
    sample_lookup: dict[int, int]
    positions_ecef_by_satellite: dict[str, np.ndarray] = field(repr=False)
    validated_actions: tuple[ValidatedAction, ...]
    action_failures: tuple[ActionFailure, ...]
    sample_allocations: tuple[SampleAllocation, ...]
