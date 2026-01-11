"""Planner-specific window model - engine models plus metadata."""

from dataclasses import dataclass
from datetime import datetime

from engines.astrox.models import AccessWindow as EngineAccessWindow, LightingWindow as EngineLightingWindow

@dataclass(frozen=True)
class PlannerAccessWindow(EngineAccessWindow):
    """Extended AccessWindow for the planner layer.

    Includes identifiers and context not present in the pure physics engine.
    """

    window_id: str | None = None
    satellite_id: str | None = None
    target_id: str | None = None
    station_id: str | None = None
    strip_id: str | None = None
    peer_satellite_id: str | None = None

    @classmethod
    def from_engine_window(
        cls,
        engine_window: EngineAccessWindow,
        satellite_id: str,
        target_id: str | None = None,
        station_id: str | None = None,
        strip_id: str | None = None,
        peer_satellite_id: str | None = None,
    ) -> "PlannerAccessWindow":
        return cls(
            start=engine_window.start,
            end=engine_window.end,
            duration_sec=engine_window.duration_sec,
            max_elevation_deg=engine_window.max_elevation_deg,
            max_elevation_point=engine_window.max_elevation_point,
            min_range_point=engine_window.min_range_point,
            mean_elevation_deg=engine_window.mean_elevation_deg,
            mean_range_m=engine_window.mean_range_m,
            aer_samples=engine_window.aer_samples,
            satellite_id=satellite_id,
            target_id=target_id,
            station_id=station_id,
            strip_id=strip_id,
            peer_satellite_id=peer_satellite_id,
        )


@dataclass(frozen=True)
class PlannerLightingWindow:
    """Lighting window with satellite_id for planner layer."""
    
    satellite_id: str
    start: datetime
    end: datetime
    duration_sec: float
    condition: str  # "SUNLIGHT" or "PENUMBRA" or "UMBRA"

    @classmethod
    def from_engine_window(
        cls,
        engine_window: EngineLightingWindow,
        satellite_id: str,
    ) -> "PlannerLightingWindow":
        return cls(
            satellite_id=satellite_id,
            start=engine_window.start,
            end=engine_window.end,
            duration_sec=engine_window.duration_sec,
            condition=engine_window.condition.name,
        )