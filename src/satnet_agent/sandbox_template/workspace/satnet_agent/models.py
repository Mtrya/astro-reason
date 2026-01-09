"""Typed models for SatNet scheduling domain."""

from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass(frozen=True)
class SatNetRequest:
    """A scheduling request (track)."""
    request_id: str
    mission_id: int
    total_required_hours: float
    remaining_hours: float
    min_duration_hours: float
    setup_seconds: int
    teardown_seconds: int


@dataclass(frozen=True)
class SatNetViewPeriod:
    """An available scheduling slot."""
    antenna: str
    start_seconds: int
    end_seconds: int
    duration_hours: float


@dataclass
class SatNetAntennaStatus:
    """Antenna availability status."""
    antenna: str
    hours_available: float
    blocked_ranges: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class SatNetTrack:
    """A scheduled track."""
    action_id: str
    request_id: str
    mission_id: int
    antenna: str
    trx_on: int
    trx_off: int
    setup_start: int
    teardown_end: int
    duration_hours: float


@dataclass
class SatNetMetrics:
    """Plan scoring metrics."""
    total_allocated_hours: float
    requests_satisfied: int
    requests_unsatisfied: int
    u_max: float
    u_rms: float


@dataclass
class SatNetPlanStatus:
    """Current plan state."""
    tracks: Dict[str, SatNetTrack] = field(default_factory=dict)
    metrics: SatNetMetrics | None = None


@dataclass
class SatNetScheduleResult:
    """Result of schedule_track operation."""
    action_id: str
    track: SatNetTrack


@dataclass
class SatNetUnscheduleResult:
    """Result of unschedule_track operation."""
    action_id: str


@dataclass
class SatNetCommitResult:
    """Result of commit_plan operation."""
    metrics: SatNetMetrics
    plan_json_path: str | None = None


class SatNetScenarioError(Exception):
    """Base exception for SatNet scenario operations."""
    pass


class SatNetValidationError(SatNetScenarioError):
    """Raised when track validation fails."""
    pass


class SatNetConflictError(SatNetScenarioError):
    """Raised when scheduling conflicts detected."""
    pass


class SatNetNotFoundError(SatNetScenarioError):
    """Raised when a referenced entity is not found."""
    pass
