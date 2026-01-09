"""
Target data structure containing only physical attributes.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0
