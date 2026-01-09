"""
Strip (polyline) data structure for representing ground observation swaths.
"""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class Strip:
    """A strip target defined by a polyline of (lat, lon) points."""

    points: List[Tuple[float, float]]
