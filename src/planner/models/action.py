"""Planner-specific action model."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PlannerAction:
    """Represents a planned action in the scenario."""

    action_id: str
    type: str
    satellite_id: str
    target_id: str | None
    station_id: str | None
    start_time: datetime
    end_time: datetime
    strip_id: str | None = None
    peer_satellite_id: str | None = None