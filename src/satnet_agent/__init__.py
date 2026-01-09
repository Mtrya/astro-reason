"""SatNet Integration: Adapter, Planner, and Scorer for DSN Scheduling."""

from .models import (
    SatNetRequest,
    SatNetViewPeriod,
    SatNetAntennaStatus,
    SatNetTrack,
    SatNetMetrics,
    SatNetPlanStatus,
    SatNetScheduleResult,
    SatNetUnscheduleResult,
    SatNetCommitResult,
    SatNetScenarioError,
    SatNetValidationError,
    SatNetConflictError,
    SatNetNotFoundError,
)

from .scenario import SatNetScenario
from .state import SatNetState, SatNetStateFile

__all__ = [
    "SatNetRequest",
    "SatNetViewPeriod",
    "SatNetAntennaStatus",
    "SatNetTrack",
    "SatNetMetrics",
    "SatNetPlanStatus",
    "SatNetScheduleResult",
    "SatNetUnscheduleResult",
    "SatNetCommitResult",
    "SatNetScenarioError",
    "SatNetValidationError",
    "SatNetConflictError",
    "SatNetNotFoundError",
    "SatNetScenario",
    "SatNetState",
    "SatNetStateFile",
]

try:
    from .scorer import SatNetScore, score_plan
    __all__.extend(["SatNetScore", "score_plan"])
except ImportError:
    pass

