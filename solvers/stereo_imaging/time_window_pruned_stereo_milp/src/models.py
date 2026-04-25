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
    max_stereo_pair_separation_s: float
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
    profiling: dict[str, Any] = field(default_factory=dict)

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
    target_id: str
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
    time_separation_s: float | None = None
    satellite_ids: tuple[str, str] | None = None
    access_interval_ids: tuple[str, str] | None = None
    pair_mode: str | None = None

    def __post_init__(self) -> None:
        time_separation_s = self.time_separation_s
        if time_separation_s is None:
            mid_i = self.candidate_i.start + (self.candidate_i.end - self.candidate_i.start) / 2
            mid_j = self.candidate_j.start + (self.candidate_j.end - self.candidate_j.start) / 2
            time_separation_s = abs((mid_j - mid_i).total_seconds())
        satellite_ids = self.satellite_ids
        if satellite_ids is None:
            satellite_ids = (self.candidate_i.sat_id, self.candidate_j.sat_id)
        access_interval_ids = self.access_interval_ids
        if access_interval_ids is None:
            access_interval_ids = (
                self.candidate_i.access_interval_id,
                self.candidate_j.access_interval_id,
            )
        pair_mode = self.pair_mode
        if pair_mode is None:
            if satellite_ids[0] == satellite_ids[1] and access_interval_ids[0] == access_interval_ids[1]:
                pair_mode = "same_satellite_same_pass"
            elif satellite_ids[0] != satellite_ids[1]:
                pair_mode = "cross_satellite"
            else:
                pair_mode = "same_satellite_other_interval"

        object.__setattr__(self, "time_separation_s", float(time_separation_s))
        object.__setattr__(self, "satellite_ids", satellite_ids)
        object.__setattr__(self, "access_interval_ids", access_interval_ids)
        object.__setattr__(self, "pair_mode", pair_mode)

    @property
    def sat_id(self) -> str:
        if self.satellite_ids[0] == self.satellite_ids[1]:
            return self.satellite_ids[0]
        return "__cross_satellite__"

    @property
    def access_interval_id(self) -> str:
        if self.access_interval_ids[0] == self.access_interval_ids[1]:
            return self.access_interval_ids[0]
        return "__multiple_intervals__"


@dataclass(frozen=True)
class TriStereoSet:
    target_id: str
    candidates: tuple[CandidateObservation, CandidateObservation, CandidateObservation]
    common_overlap_fraction: float
    pair_valid_flags: list[bool]
    pair_qs: list[float]
    has_anchor: bool
    valid: bool
    q_tri: float
    satellite_ids: tuple[str, str, str] | None = None
    access_interval_ids: tuple[str, str, str] | None = None

    def __post_init__(self) -> None:
        satellite_ids = self.satellite_ids
        if satellite_ids is None:
            satellite_ids = tuple(c.sat_id for c in self.candidates)
        access_interval_ids = self.access_interval_ids
        if access_interval_ids is None:
            access_interval_ids = tuple(c.access_interval_id for c in self.candidates)

        object.__setattr__(self, "satellite_ids", satellite_ids)
        object.__setattr__(self, "access_interval_ids", access_interval_ids)

    @property
    def sat_id(self) -> str:
        if self.satellite_ids[0] == self.satellite_ids[1] == self.satellite_ids[2]:
            return self.satellite_ids[0]
        return "__multi_satellite__"

    @property
    def access_interval_id(self) -> str:
        if self.access_interval_ids[0] == self.access_interval_ids[1] == self.access_interval_ids[2]:
            return self.access_interval_ids[0]
        return "__multiple_intervals__"


@dataclass
class ProductSummary:
    total_pairs: int = 0
    valid_pairs: int = 0
    total_tris: int = 0
    valid_tris: int = 0
    pair_mode_counts: dict[str, int] = field(default_factory=dict)
    valid_pair_mode_counts: dict[str, int] = field(default_factory=dict)
    multi_satellite_tris: int = 0
    valid_multi_satellite_tris: int = 0
    by_target: dict[str, dict[str, Any]] = field(default_factory=dict)
    approximation_flags: dict[str, Any] = field(default_factory=dict)
    profiling: dict[str, Any] = field(default_factory=dict)

    def record_pair(self, pair: StereoPair) -> None:
        self.total_pairs += 1
        self.pair_mode_counts[pair.pair_mode] = self.pair_mode_counts.get(pair.pair_mode, 0) + 1
        if pair.valid:
            self.valid_pairs += 1
            self.valid_pair_mode_counts[pair.pair_mode] = self.valid_pair_mode_counts.get(pair.pair_mode, 0) + 1
        td = self.by_target.setdefault(pair.target_id, {"pairs": 0, "valid_pairs": 0, "tris": 0, "valid_tris": 0, "best_q": 0.0})
        td["pairs"] += 1
        if pair.valid:
            td["valid_pairs"] += 1
            if pair.q_pair > td["best_q"]:
                td["best_q"] = pair.q_pair

    def record_tri(self, tri: TriStereoSet) -> None:
        self.total_tris += 1
        if len(set(tri.satellite_ids)) > 1:
            self.multi_satellite_tris += 1
        if tri.valid:
            self.valid_tris += 1
            if len(set(tri.satellite_ids)) > 1:
                self.valid_multi_satellite_tris += 1
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
            "pair_mode_counts": dict(self.pair_mode_counts),
            "valid_pair_mode_counts": dict(self.valid_pair_mode_counts),
            "multi_satellite_tris": self.multi_satellite_tris,
            "valid_multi_satellite_tris": self.valid_multi_satellite_tris,
            "by_target": dict(self.by_target),
            "approximation_flags": dict(self.approximation_flags),
        }


@dataclass
class PruningSummary:
    enabled: bool
    cluster_gap_s: float
    lambda_cap: int
    pre_candidates: int = 0
    post_candidates: int = 0
    pre_pairs: int = 0
    post_pairs: int = 0
    pre_tris: int = 0
    post_tris: int = 0
    by_target: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_cluster: list[dict[str, Any]] = field(default_factory=list)
    preservation_forced: int = 0
    rejected_by_capacity: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "cluster_gap_s": self.cluster_gap_s,
            "lambda_cap": self.lambda_cap,
            "pre_candidates": self.pre_candidates,
            "post_candidates": self.post_candidates,
            "pre_pairs": self.pre_pairs,
            "post_pairs": self.post_pairs,
            "pre_tris": self.pre_tris,
            "post_tris": self.post_tris,
            "by_target": dict(self.by_target),
            "by_cluster": list(self.by_cluster),
            "preservation_forced": self.preservation_forced,
            "rejected_by_capacity": self.rejected_by_capacity,
        }


@dataclass
class SolveSummary:
    backend_used: str
    n_obs_vars: int = 0
    n_pair_vars: int = 0
    n_tri_vars: int = 0
    n_conflict_constraints: int = 0
    n_coverage_constraints: int = 0
    selected_observations: int = 0
    selected_pairs: int = 0
    selected_tris: int = 0
    covered_targets: int = 0
    coverage_ratio: float = 0.0
    objective_coverage: int = 0
    objective_quality: float = 0.0
    best_target_quality_sum: float = 0.0
    normalized_quality: float = 0.0
    per_target_best_score: dict[str, float] = field(default_factory=dict)
    solve_time_s: float = 0.0
    timeout_reached: bool = False
    profiling: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "backend_used": self.backend_used,
            "n_obs_vars": self.n_obs_vars,
            "n_pair_vars": self.n_pair_vars,
            "n_tri_vars": self.n_tri_vars,
            "n_conflict_constraints": self.n_conflict_constraints,
            "n_coverage_constraints": self.n_coverage_constraints,
            "selected_observations": self.selected_observations,
            "selected_pairs": self.selected_pairs,
            "selected_tris": self.selected_tris,
            "covered_targets": self.covered_targets,
            "coverage_ratio": self.coverage_ratio,
            "objective_coverage": self.objective_coverage,
            "objective_quality": self.objective_quality,
            "best_target_quality_sum": self.best_target_quality_sum,
            "normalized_quality": self.normalized_quality,
            "per_target_best_score": dict(self.per_target_best_score),
            "solve_time_s": self.solve_time_s,
            "timeout_reached": self.timeout_reached,
        }


@dataclass
class RepairLog:
    removed_observations: list[dict[str, Any]] = field(default_factory=list)
    pre_repair_obs_count: int = 0
    post_repair_obs_count: int = 0
    pre_repair_pairs: int = 0
    post_repair_pairs: int = 0
    pre_repair_tris: int = 0
    post_repair_tris: int = 0
    pre_repair_covered_targets: int = 0
    post_repair_covered_targets: int = 0
    pre_repair_best_target_quality_sum: float = 0.0
    post_repair_best_target_quality_sum: float = 0.0
    pre_repair_normalized_quality: float = 0.0
    post_repair_normalized_quality: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "removed_observations": list(self.removed_observations),
            "pre_repair_obs_count": self.pre_repair_obs_count,
            "post_repair_obs_count": self.post_repair_obs_count,
            "pre_repair_pairs": self.pre_repair_pairs,
            "post_repair_pairs": self.post_repair_pairs,
            "pre_repair_tris": self.pre_repair_tris,
            "post_repair_tris": self.post_repair_tris,
            "pre_repair_covered_targets": self.pre_repair_covered_targets,
            "post_repair_covered_targets": self.post_repair_covered_targets,
            "pre_repair_best_target_quality_sum": self.pre_repair_best_target_quality_sum,
            "post_repair_best_target_quality_sum": self.post_repair_best_target_quality_sum,
            "pre_repair_normalized_quality": self.pre_repair_normalized_quality,
            "post_repair_normalized_quality": self.post_repair_normalized_quality,
        }
