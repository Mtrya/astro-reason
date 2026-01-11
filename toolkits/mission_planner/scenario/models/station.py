"""Planner-specific station model - engine model plus metadata"""

from dataclasses import dataclass

@dataclass(frozen=True)
class PlannerStation:
    """Represents a station in the scenario"""

    id: str
    name: str
    network_name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    
