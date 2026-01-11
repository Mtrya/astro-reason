"""Planner-specific strip model."""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class PlannerStrip:
    """Represents a strip (polyline) target for mosaic missions."""

    id: str
    name: str
    points: List[Tuple[float, float]]
