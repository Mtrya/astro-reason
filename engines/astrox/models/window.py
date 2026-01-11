"""
Data structures for time-based physical events.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


@dataclass(frozen=True)
class AccessAERPoint:
    """Single AER sample for an access window."""

    time: datetime
    azimuth_deg: float
    elevation_deg: float
    range_m: float


@dataclass(frozen=True)
class AccessWindow:
    """Single continuous period of access between a satellite and a target."""

    start: datetime
    end: datetime
    duration_sec: float

    max_elevation_deg: float | None = None
    max_elevation_point: AccessAERPoint | None = None
    min_range_point: AccessAERPoint | None = None
    mean_elevation_deg: float | None = None
    mean_range_m: float | None = None
    # Optional detailed AER samples across the entire access window.
    aer_samples: list[AccessAERPoint] | None = None


@dataclass(frozen=True)
class ObservationStats:
    """Per-action observation statistics derived from window AER data."""

    mean_elevation_deg: float | None = None
    max_elevation_deg: float | None = None
    min_range_km: float | None = None
    mean_range_km: float | None = None
    sample_count: int | None = None


class LightingCondition(str, Enum):
    """Enumeration for lighting conditions."""

    UMBRA = "UMBRA"
    PENUMBRA = "PENUMBRA"
    SUNLIGHT = "SUNLIGHT"


@dataclass(frozen=True)
class LightingWindow:
    """
    Represents a single continuous period of a specific lighting condition for a satellite.
    """

    start: datetime
    end: datetime
    duration_sec: float
    condition: LightingCondition
