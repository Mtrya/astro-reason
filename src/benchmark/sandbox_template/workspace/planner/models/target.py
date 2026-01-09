"""Planner-specific target model - engine model plus metadata"""

from dataclasses import dataclass

@dataclass(frozen=True)
class PlannerTarget:
    """Represents a target in the scenario"""

    id: str
    name: str
    country: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    population: float


