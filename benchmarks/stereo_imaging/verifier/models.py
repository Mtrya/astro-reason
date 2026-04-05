"""Typed structures for the stereo_imaging v3 verifier."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Mission:
    horizon_start: datetime
    horizon_end: datetime
    allow_cross_satellite_stereo: bool
    allow_cross_date_stereo: bool
    min_overlap_fraction: float
    min_convergence_deg: float
    max_convergence_deg: float
    max_pixel_scale_ratio: float
    min_solar_elevation_deg: float
    near_nadir_anchor_max_off_nadir_deg: float
    pair_weights: dict[str, float]
    tri_stereo_bonus_by_scene: dict[str, float]


@dataclass(frozen=True)
class SatelliteDef:
    sat_id: str
    norad_catalog_id: int
    tle_line1: str
    tle_line2: str
    pixel_ifov_deg: float
    cross_track_pixels: int
    max_off_nadir_deg: float
    max_slew_velocity_deg_per_s: float
    max_slew_acceleration_deg_per_s2: float
    settling_time_s: float
    min_obs_duration_s: float
    max_obs_duration_s: float

    @property
    def cross_track_fov_deg(self) -> float:
        return float(self.cross_track_pixels) * self.pixel_ifov_deg

    @property
    def half_cross_track_fov_deg(self) -> float:
        return 0.5 * self.cross_track_fov_deg


@dataclass(frozen=True)
class TargetDef:
    target_id: str
    latitude_deg: float
    longitude_deg: float
    aoi_radius_m: float
    elevation_ref_m: float
    scene_type: str


@dataclass(frozen=True)
class ObservationAction:
    satellite_id: str
    target_id: str
    start: datetime
    end: datetime
    off_nadir_along_deg: float
    off_nadir_across_deg: float


@dataclass
class DerivedObservation:
    satellite_id: str
    target_id: str
    start_time: str
    end_time: str
    midpoint_time: str
    sat_position_ecef_m: list[float]
    sat_velocity_ecef_mps: list[float]
    boresight_off_nadir_deg: float
    boresight_azimuth_deg: float
    solar_elevation_deg: float
    solar_azimuth_deg: float
    effective_pixel_scale_m: float
    access_interval_id: str
    slant_range_m: float


@dataclass
class VerificationReport:
    valid: bool
    metrics: dict[str, Any]
    violations: list[str] = field(default_factory=list)
    derived_observations: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "metrics": self.metrics,
            "violations": self.violations,
            "derived_observations": self.derived_observations,
            "diagnostics": self.diagnostics,
        }
