"""Planner data models and exceptions."""


class ScenarioError(Exception):
    """Base exception for scenario operations."""
    pass


class ValidationError(ScenarioError):
    """Raised when action validation fails."""
    pass


class ConflictError(ScenarioError):
    """Raised when time/resource conflicts are detected."""
    pass


class ResourceViolationError(ScenarioError):
    """Raised when power or storage constraints are violated."""
    pass


from .action import PlannerAction
from .satellite import PlannerSatellite
from .station import PlannerStation
from .target import PlannerTarget
from .strip import PlannerStrip
from .window import PlannerAccessWindow, PlannerLightingWindow
from .metrics import SatelliteMetrics, PlanMetrics
from .results import Violation, PlanStatus, StageResult, UnstageResult, CommitResult
from .analysis import (
    GroundTrackPoint,
    RevisitAnalysis,
    StereoAnalysis,
    PolygonCoverageAnalysis,
    ObservationInfo,
    GridCell
)

__all__ = [
    "ScenarioError",
    "ValidationError",
    "ConflictError",
    "ResourceViolationError",
    "PlannerAction",
    "PlannerSatellite",
    "PlannerStation",
    "PlannerTarget",
    "PlannerStrip",
    "PlannerAccessWindow",
    "PlannerLightingWindow",
    "SatelliteMetrics",
    "PlanMetrics",
    "Violation",
    "PlanStatus",
    "StageResult",
    "UnstageResult",
    "CommitResult",
    "GroundTrackPoint",
    "RevisitAnalysis",
    "StereoAnalysis",
    "PolygonCoverageAnalysis",
    "ObservationInfo",
    "GridCell",
]
