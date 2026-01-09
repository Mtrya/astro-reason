"""
Ground station data structure.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Station:
    """Represents a fixed ground station location."""

    latitude_deg: float
    longitude_deg: float
    altitude_m: float

