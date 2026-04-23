"""Standalone data models for the stereo MILP solver."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Satellite:
    id: str
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
        return self.cross_track_pixels * self.pixel_ifov_deg

    @property
    def half_cross_track_fov_deg(self) -> float:
        return 0.5 * self.cross_track_fov_deg


@dataclass(frozen=True)
class Target:
    id: str
    latitude_deg: float
    longitude_deg: float
    aoi_radius_m: float
    elevation_ref_m: float
    scene_type: str


@dataclass(frozen=True)
class ValidityThresholds:
    min_overlap_fraction: float
    min_convergence_deg: float
    max_convergence_deg: float
    max_pixel_scale_ratio: float
    min_solar_elevation_deg: float
    near_nadir_anchor_max_off_nadir_deg: float

    @classmethod
    def from_mapping(cls, m: dict[str, Any]) -> ValidityThresholds:
        return cls(
            min_overlap_fraction=float(m["min_overlap_fraction"]),
            min_convergence_deg=float(m["min_convergence_deg"]),
            max_convergence_deg=float(m["max_convergence_deg"]),
            max_pixel_scale_ratio=float(m["max_pixel_scale_ratio"]),
            min_solar_elevation_deg=float(m["min_solar_elevation_deg"]),
            near_nadir_anchor_max_off_nadir_deg=float(m["near_nadir_anchor_max_off_nadir_deg"]),
        )


@dataclass(frozen=True)
class QualityModel:
    pair_weights: dict[str, float]
    tri_stereo_bonus_by_scene: dict[str, float]

    @classmethod
    def from_mapping(cls, m: dict[str, Any]) -> QualityModel:
        return cls(
            pair_weights=dict(m["pair_weights"]),
            tri_stereo_bonus_by_scene=dict(m["tri_stereo_bonus_by_scene"]),
        )


@dataclass(frozen=True)
class Mission:
    horizon_start: datetime
    horizon_end: datetime
    allow_cross_satellite_stereo: bool
    allow_cross_date_stereo: bool
    validity_thresholds: ValidityThresholds
    quality_model: QualityModel


@dataclass(frozen=True)
class AccessInterval:
    sat_id: str
    target_id: str
    interval_id: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class CandidateObservation:
    sat_id: str
    target_id: str
    access_interval_id: str
    start: datetime
    end: datetime
    off_nadir_along_deg: float
    off_nadir_across_deg: float
    combined_off_nadir_deg: float


@dataclass(frozen=True)
class RejectionRecord:
    sat_id: str
    target_id: str
    interval_id: str
    reason: str
    start: datetime | None = None
    end: datetime | None = None


@dataclass
class CandidateSummary:
    total_generated: int = 0
    total_accepted: int = 0
    total_rejected: int = 0
    by_satellite: dict[str, dict[str, int]] = field(default_factory=dict)
    by_target: dict[str, dict[str, int]] = field(default_factory=dict)
    by_interval: dict[str, dict[str, int]] = field(default_factory=dict)
    by_reason: dict[str, int] = field(default_factory=dict)

    def record(self, accepted: bool, sat_id: str, target_id: str, interval_id: str, reason: str | None = None) -> None:
        self.total_generated += 1
        if accepted:
            self.total_accepted += 1
            key = "accepted"
        else:
            self.total_rejected += 1
            key = reason or "unknown"
            if reason:
                self.by_reason[reason] = self.by_reason.get(reason, 0) + 1

        for bucket, ident in (
            (self.by_satellite, sat_id),
            (self.by_target, target_id),
            (self.by_interval, interval_id),
        ):
            if ident not in bucket:
                bucket[ident] = {}
            bucket[ident][key] = bucket[ident].get(key, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_generated": self.total_generated,
            "total_accepted": self.total_accepted,
            "total_rejected": self.total_rejected,
            "by_satellite": dict(self.by_satellite),
            "by_target": dict(self.by_target),
            "by_interval": dict(self.by_interval),
            "by_reason": dict(self.by_reason),
        }


@dataclass(frozen=True)
class StereoPair:
    sat_id: str
    target_id: str
    access_interval_id: str
    candidate_i: CandidateObservation
    candidate_j: CandidateObservation
    convergence_deg: float
    overlap_fraction: float
    pixel_scale_ratio: float
    valid: bool
    q_geom: float
    q_overlap: float
    q_res: float
    q_pair: float


@dataclass(frozen=True)
class TriStereoSet:
    sat_id: str
    target_id: str
    access_interval_id: str
    candidates: tuple[CandidateObservation, CandidateObservation, CandidateObservation]
    common_overlap_fraction: float
    pair_valid_flags: list[bool]
    pair_qs: list[float]
    has_anchor: bool
    valid: bool
    q_tri: float


@dataclass
class ProductSummary:
    total_pairs: int = 0
    valid_pairs: int = 0
    total_tris: int = 0
    valid_tris: int = 0
    by_target: dict[str, dict[str, Any]] = field(default_factory=dict)
    approximation_flags: dict[str, Any] = field(default_factory=dict)

    def record_pair(self, pair: StereoPair) -> None:
        self.total_pairs += 1
        if pair.valid:
            self.valid_pairs += 1
        td = self.by_target.setdefault(pair.target_id, {"pairs": 0, "valid_pairs": 0, "tris": 0, "valid_tris": 0, "best_q": 0.0})
        td["pairs"] += 1
        if pair.valid:
            td["valid_pairs"] += 1
            if pair.q_pair > td["best_q"]:
                td["best_q"] = pair.q_pair

    def record_tri(self, tri: TriStereoSet) -> None:
        self.total_tris += 1
        if tri.valid:
            self.valid_tris += 1
        td = self.by_target.setdefault(tri.target_id, {"pairs": 0, "valid_pairs": 0, "tris": 0, "valid_tris": 0, "best_q": 0.0})
        td["tris"] += 1
        if tri.valid:
            td["valid_tris"] += 1
            if tri.q_tri > td["best_q"]:
                td["best_q"] = tri.q_tri

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_pairs": self.total_pairs,
            "valid_pairs": self.valid_pairs,
            "total_tris": self.total_tris,
            "valid_tris": self.valid_tris,
            "by_target": dict(self.by_target),
            "approximation_flags": dict(self.approximation_flags),
        }
