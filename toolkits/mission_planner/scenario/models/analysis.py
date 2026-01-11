from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Optional

@dataclass
class ObservationInfo:
    action_id: str
    time: datetime
    satellite_id: str
    azimuth_deg: float
    elevation_deg: float

@dataclass
class RevisitAnalysis:
    target_id: str
    observation_times: List[datetime]
    gaps_seconds: List[float]
    max_gap_seconds: float
    mean_gap_seconds: float
    coverage_count: int

@dataclass
class StereoAnalysis:
    target_id: str
    observations: List[ObservationInfo]
    has_stereo: bool
    best_pair_azimuth_diff_deg: float | None
    stereo_pairs: List[Tuple[str, str]]

@dataclass
class GridCell:
    lat: float
    lon: float
    is_covered: bool

@dataclass
class PolygonCoverageAnalysis:
    total_area_km2: float
    covered_area_km2: float
    coverage_ratio: float
    coverage_grid: List[GridCell]

@dataclass
class GroundTrackPoint:
    lat: float
    lon: float
    time: datetime
