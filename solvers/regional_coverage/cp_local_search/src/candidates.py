"""Deterministic strip candidate generation for regional_coverage."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import math
from typing import Any

import brahe
import numpy as np
from shapely.geometry import Polygon

from .case_io import RegionalCoverageCase, Satellite, SolverConfig, iso_z
from .coverage import CoverageIndex
from .geometry import (
    initial_bearing_deg,
)
from .time_grid import candidate_duration_s, grid_offsets, offset_to_datetime

_NUMERICAL_EPS = 1.0e-9
_WGS84_A_M = 6_378_137.0
_WGS84_B_M = 6_356_752.314_245_179
_BRAHE_EOP_INITIALIZED = False


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    satellite_id: str
    start_offset_s: int
    end_offset_s: int
    duration_s: int
    roll_deg: float
    coverage_sample_ids: frozenset[str]
    base_coverage_weight_m2: float
    estimated_energy_wh: float
    estimated_slew_in_gap_s: float
    footprint_center_latitude_deg: float
    footprint_center_longitude_deg: float
    footprint_heading_deg: float
    along_half_m: float
    cross_half_m: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "satellite_id": self.satellite_id,
            "start_offset_s": self.start_offset_s,
            "end_offset_s": self.end_offset_s,
            "duration_s": self.duration_s,
            "roll_deg": self.roll_deg,
            "coverage_sample_count": len(self.coverage_sample_ids),
            "coverage_sample_ids": sorted(self.coverage_sample_ids),
            "base_coverage_weight_m2": self.base_coverage_weight_m2,
            "estimated_energy_wh": self.estimated_energy_wh,
            "estimated_slew_in_gap_s": self.estimated_slew_in_gap_s,
            "footprint_center_latitude_deg": self.footprint_center_latitude_deg,
            "footprint_center_longitude_deg": self.footprint_center_longitude_deg,
            "footprint_heading_deg": self.footprint_heading_deg,
            "along_half_m": self.along_half_m,
            "cross_half_m": self.cross_half_m,
        }


@dataclass(slots=True)
class CandidateSummary:
    candidate_count: int = 0
    zero_coverage_candidate_count: int = 0
    positive_coverage_candidate_count: int = 0
    max_candidate_weight_m2: float = 0.0
    skipped_roll_band: int = 0
    skipped_satellite_cap: int = 0
    per_satellite_candidate_counts: dict[str, int] = field(default_factory=dict)
    per_satellite_zero_coverage_counts: dict[str, int] = field(default_factory=dict)
    per_satellite_positive_coverage_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": self.candidate_count,
            "zero_coverage_candidate_count": self.zero_coverage_candidate_count,
            "positive_coverage_candidate_count": self.positive_coverage_candidate_count,
            "max_candidate_weight_m2": self.max_candidate_weight_m2,
            "skipped_roll_band": self.skipped_roll_band,
            "skipped_satellite_cap": self.skipped_satellite_cap,
            "per_satellite_candidate_counts": dict(sorted(self.per_satellite_candidate_counts.items())),
            "per_satellite_zero_coverage_counts": dict(
                sorted(self.per_satellite_zero_coverage_counts.items())
            ),
            "per_satellite_positive_coverage_counts": dict(
                sorted(self.per_satellite_positive_coverage_counts.items())
            ),
        }


def generate_candidates(
    case: RegionalCoverageCase,
    config: SolverConfig,
    coverage_index: CoverageIndex | None = None,
) -> tuple[list[Candidate], CandidateSummary]:
    index = coverage_index or CoverageIndex.from_case(case)
    summary = CandidateSummary()
    candidates: list[Candidate] = []

    for satellite_id, satellite in sorted(case.satellites.items()):
        summary.per_satellite_candidate_counts[satellite_id] = 0
        summary.per_satellite_zero_coverage_counts[satellite_id] = 0
        summary.per_satellite_positive_coverage_counts[satellite_id] = 0
        sat_candidates = _generate_for_satellite(case, satellite, config, index, summary)
        candidates.extend(sat_candidates)

    candidates.sort(key=candidate_sort_key)
    summary.candidate_count = len(candidates)
    summary.zero_coverage_candidate_count = sum(1 for candidate in candidates if not candidate.coverage_sample_ids)
    summary.positive_coverage_candidate_count = summary.candidate_count - summary.zero_coverage_candidate_count
    summary.max_candidate_weight_m2 = max(
        (candidate.base_coverage_weight_m2 for candidate in candidates),
        default=0.0,
    )
    return candidates, summary


def roll_values_for_satellite(satellite: Satellite, samples_per_side: int) -> list[float]:
    low = satellite.sensor.min_center_roll_abs_deg
    high = satellite.sensor.max_center_roll_abs_deg
    if low > high + 1e-6:
        return []
    if samples_per_side == 1:
        magnitudes = [(low + high) / 2.0]
    else:
        step = (high - low) / max(1, samples_per_side - 1)
        magnitudes = [low + step * idx for idx in range(samples_per_side)]
    values: list[float] = []
    for magnitude in magnitudes:
        rounded = round(magnitude, 6)
        values.extend([-rounded, rounded])
    return sorted(set(values))


def candidate_sort_key(candidate: Candidate) -> tuple[str, int, float, str]:
    return (
        candidate.satellite_id,
        candidate.start_offset_s,
        candidate.roll_deg,
        candidate.candidate_id,
    )


def _generate_for_satellite(
    case: RegionalCoverageCase,
    satellite: Satellite,
    config: SolverConfig,
    index: CoverageIndex,
    summary: CandidateSummary,
) -> list[Candidate]:
    _ensure_brahe_ready()
    propagator = brahe.SGPPropagator.from_tle(
        satellite.tle_line1,
        satellite.tle_line2,
        float(case.mission.coverage_sample_step_s),
    )
    duration_s = candidate_duration_s(
        case.mission,
        satellite.sensor.min_strip_duration_s,
        satellite.sensor.max_strip_duration_s,
    )
    offsets = grid_offsets(case.mission, stride_s=config.candidate_stride_s, duration_s=duration_s)
    rolls = roll_values_for_satellite(satellite, config.roll_samples_per_side)
    out: list[Candidate] = []
    zero_kept = 0

    for start_offset_s in offsets:
        if len(out) >= config.max_candidates_per_satellite:
            summary.skipped_satellite_cap += len(offsets) * max(1, len(rolls))
            break
        for roll_deg in rolls:
            if len(out) >= config.max_candidates_per_satellite:
                summary.skipped_satellite_cap += 1
                break
            candidate = _candidate_at(
                case=case,
                satellite=satellite,
                propagator=propagator,
                start_offset_s=start_offset_s,
                duration_s=duration_s,
                roll_deg=roll_deg,
                index=index,
            )
            if not candidate.coverage_sample_ids:
                if not config.include_zero_coverage_candidates:
                    continue
                if zero_kept >= config.max_zero_coverage_candidates_per_satellite:
                    continue
                zero_kept += 1
                summary.per_satellite_zero_coverage_counts[satellite.satellite_id] += 1
            else:
                summary.per_satellite_positive_coverage_counts[satellite.satellite_id] += 1
            out.append(candidate)
            summary.per_satellite_candidate_counts[satellite.satellite_id] += 1
    return out


def _candidate_at(
    *,
    case: RegionalCoverageCase,
    satellite: Satellite,
    propagator: brahe.SGPPropagator,
    start_offset_s: int,
    duration_s: int,
    roll_deg: float,
    index: CoverageIndex,
) -> Candidate:
    start = offset_to_datetime(case.mission, start_offset_s)
    end_offset_s = start_offset_s + duration_s
    end = offset_to_datetime(case.mission, end_offset_s)
    geometry = _strip_geometry(
        propagator=propagator,
        start=start,
        end=end,
        step_s=case.mission.coverage_sample_step_s,
        roll_deg=roll_deg,
        fov_deg=satellite.sensor.cross_track_fov_deg,
    )
    sample_ids = index.samples_for_polygons(geometry.segment_polygons)
    energy_wh = (
        satellite.power.imaging_power_w * duration_s / 3600.0
        + satellite.power.idle_power_w * duration_s / 3600.0
    )
    cid = (
        f"{satellite.satellite_id}|t{start_offset_s:06d}|"
        f"d{duration_s}|r{roll_deg:+08.3f}"
    )
    return Candidate(
        candidate_id=cid,
        satellite_id=satellite.satellite_id,
        start_offset_s=start_offset_s,
        end_offset_s=end_offset_s,
        duration_s=duration_s,
        roll_deg=roll_deg,
        coverage_sample_ids=sample_ids,
        base_coverage_weight_m2=index.total_weight(sample_ids),
        estimated_energy_wh=energy_wh,
        estimated_slew_in_gap_s=satellite.agility.settling_time_s,
        footprint_center_latitude_deg=geometry.center_latitude_deg,
        footprint_center_longitude_deg=geometry.center_longitude_deg,
        footprint_heading_deg=geometry.heading_deg,
        along_half_m=0.0,
        cross_half_m=0.0,
    )


@dataclass(frozen=True, slots=True)
class _StripGeometry:
    segment_polygons: tuple[Polygon, ...]
    center_latitude_deg: float
    center_longitude_deg: float
    heading_deg: float


def _strip_geometry(
    *,
    propagator: brahe.SGPPropagator,
    start: datetime,
    end: datetime,
    step_s: int,
    roll_deg: float,
    fov_deg: float,
) -> _StripGeometry:
    times = _sample_times(start, end, step_s)
    center_lonlat: list[tuple[float, float]] = []
    edge_hits: list[tuple[np.ndarray, np.ndarray]] = []
    center_abs = abs(roll_deg)
    signed_inner = math.copysign(center_abs - (0.5 * fov_deg), roll_deg)
    signed_outer = math.copysign(center_abs + (0.5 * fov_deg), roll_deg)

    for sample_time in times:
        epoch = _datetime_to_epoch(sample_time)
        state_ecef = np.asarray(propagator.state_ecef(epoch), dtype=float).reshape(6)
        sat_pos_m = state_ecef[:3]
        sat_vel_mps = state_ecef[3:]
        center_hit = _ground_intercept_ecef_m(sat_pos_m, sat_vel_mps, roll_deg)
        inner_hit = _ground_intercept_ecef_m(sat_pos_m, sat_vel_mps, signed_inner)
        outer_hit = _ground_intercept_ecef_m(sat_pos_m, sat_vel_mps, signed_outer)
        if center_hit is None or inner_hit is None or outer_hit is None:
            return _StripGeometry((), 0.0, 0.0, 0.0)
        center_lonlat.append(_ecef_to_lonlat_deg(center_hit))
        edge_hits.append((inner_hit, outer_hit))

    polygons: list[Polygon] = []
    for (inner_a, outer_a), (inner_b, outer_b) in zip(edge_hits, edge_hits[1:]):
        polygon = Polygon(
            [
                _ecef_to_lonlat_deg(inner_a),
                _ecef_to_lonlat_deg(outer_a),
                _ecef_to_lonlat_deg(outer_b),
                _ecef_to_lonlat_deg(inner_b),
            ]
        )
        if polygon.is_empty or polygon.area <= _NUMERICAL_EPS:
            continue
        polygons.append(polygon)

    if center_lonlat:
        mid_lon, mid_lat = center_lonlat[len(center_lonlat) // 2]
        first_lon, first_lat = center_lonlat[0]
        last_lon, last_lat = center_lonlat[-1]
        heading_deg = initial_bearing_deg(first_lat, first_lon, last_lat, last_lon)
    else:
        mid_lat = 0.0
        mid_lon = 0.0
        heading_deg = 0.0
    return _StripGeometry(tuple(polygons), mid_lat, mid_lon, heading_deg)


def _ensure_brahe_ready() -> None:
    global _BRAHE_EOP_INITIALIZED
    if _BRAHE_EOP_INITIALIZED:
        return
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    _BRAHE_EOP_INITIALIZED = True


def _datetime_to_epoch(value: datetime) -> brahe.Epoch:
    value = value.astimezone(UTC)
    second = float(value.second) + (value.microsecond / 1_000_000.0)
    return brahe.Epoch.from_datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        second,
        0.0,
        brahe.TimeSystem.UTC,
    )


def _sample_times(start: datetime, end: datetime, step_s: int) -> list[datetime]:
    if end <= start:
        return [start]
    points = [start]
    current = start
    delta = timedelta(seconds=step_s)
    while current + delta < end:
        current = current + delta
        points.append(current)
    if points[-1] != end:
        points.append(end)
    return points


def _satellite_local_axes(
    sat_pos_m: np.ndarray, sat_vel_mps: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nadir = -sat_pos_m / np.linalg.norm(sat_pos_m)
    along = sat_vel_mps - float(np.dot(sat_vel_mps, nadir)) * nadir
    if float(np.linalg.norm(along)) <= _NUMERICAL_EPS:
        fallback = np.array([0.0, 0.0, 1.0])
        if abs(float(np.dot(fallback, nadir))) > 0.9:
            fallback = np.array([0.0, 1.0, 0.0])
        along = fallback - float(np.dot(fallback, nadir)) * nadir
    along = along / np.linalg.norm(along)
    across = np.cross(along, nadir)
    if float(np.linalg.norm(across)) <= _NUMERICAL_EPS:
        across = np.array([1.0, 0.0, 0.0], dtype=float)
    else:
        across = across / np.linalg.norm(across)
    return along, across, nadir


def _boresight_unit_vector(
    sat_pos_m: np.ndarray,
    sat_vel_mps: np.ndarray,
    across_track_off_nadir_deg: float,
) -> np.ndarray:
    _, across_hat, nadir_hat = _satellite_local_axes(sat_pos_m, sat_vel_mps)
    vector = nadir_hat + (
        math.tan(math.radians(float(across_track_off_nadir_deg))) * across_hat
    )
    return vector / np.linalg.norm(vector)


def _ray_ellipsoid_intersection_m(
    origin_m: np.ndarray,
    direction_unit: np.ndarray,
) -> float | None:
    ox, oy, oz = (float(origin_m[i]) for i in range(3))
    dx, dy, dz = (float(direction_unit[i]) for i in range(3))
    a2 = _WGS84_A_M * _WGS84_A_M
    b2 = _WGS84_B_M * _WGS84_B_M
    inv_a2 = 1.0 / a2
    inv_b2 = 1.0 / b2
    aa = (dx * dx + dy * dy) * inv_a2 + dz * dz * inv_b2
    bb = 2.0 * ((ox * dx + oy * dy) * inv_a2 + oz * dz * inv_b2)
    cc = (ox * ox + oy * oy) * inv_a2 + oz * oz * inv_b2 - 1.0
    disc = bb * bb - 4.0 * aa * cc
    if disc < 0.0 or abs(aa) < 1.0e-30:
        return None
    sqrt_disc = math.sqrt(disc)
    t1 = (-bb - sqrt_disc) / (2.0 * aa)
    t2 = (-bb + sqrt_disc) / (2.0 * aa)
    candidates = [value for value in (t1, t2) if value > _NUMERICAL_EPS]
    if not candidates:
        return None
    return min(candidates)


def _ground_intercept_ecef_m(
    sat_pos_m: np.ndarray,
    sat_vel_mps: np.ndarray,
    roll_deg: float,
) -> np.ndarray | None:
    direction = _boresight_unit_vector(sat_pos_m, sat_vel_mps, roll_deg)
    distance = _ray_ellipsoid_intersection_m(sat_pos_m, direction)
    if distance is None:
        return None
    return sat_pos_m + (distance * direction)


def _ecef_to_lonlat_deg(ecef_position_m: np.ndarray) -> tuple[float, float]:
    lon_deg, lat_deg, _ = brahe.position_ecef_to_geodetic(
        ecef_position_m,
        brahe.AngleFormat.DEGREES,
    )
    return float(lon_deg), float(lat_deg)
