"""Metric dataclasses for plan status reporting."""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class SatelliteMetrics:
    """Per-satellite resource and action metrics with time-series data."""

    satellite_id: str
    obs_count: int
    downlink_count: int
    isl_count: int
    power_violated: bool
    storage_violated: bool
    power_curve: List[float] = field(default_factory=list)
    storage_curve: List[float] = field(default_factory=list)
    quaternions: List[Tuple[float, float, float, float]] = field(default_factory=list)


@dataclass
class PlanMetrics:
    """Aggregate metrics for the entire plan."""

    satellites: Dict[str, SatelliteMetrics] = field(default_factory=dict)
    total_actions: int = 0
    total_observations: int = 0
    total_downlinks: int = 0
    total_isls: int = 0
