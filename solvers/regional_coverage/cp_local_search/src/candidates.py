"""Deterministic strip candidate generation for regional_coverage."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from skyfield.api import EarthSatellite

from .case_io import RegionalCoverageCase, Satellite, SolverConfig, iso_z
from .coverage import CoverageFootprint, CoverageIndex
from .geometry import (
    _TS,
    destination_point,
    haversine_m,
    initial_bearing_deg,
    roll_ground_range_m,
    satellite_subpoint,
    swath_width_m,
)
from .time_grid import candidate_duration_s, grid_offsets, offset_to_datetime


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
    skipped_roll_band: int = 0
    skipped_satellite_cap: int = 0
    per_satellite_candidate_counts: dict[str, int] = field(default_factory=dict)
    per_satellite_zero_coverage_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": self.candidate_count,
            "zero_coverage_candidate_count": self.zero_coverage_candidate_count,
            "skipped_roll_band": self.skipped_roll_band,
            "skipped_satellite_cap": self.skipped_satellite_cap,
            "per_satellite_candidate_counts": dict(sorted(self.per_satellite_candidate_counts.items())),
            "per_satellite_zero_coverage_counts": dict(
                sorted(self.per_satellite_zero_coverage_counts.items())
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
        sat_candidates = _generate_for_satellite(case, satellite, config, index, summary)
        candidates.extend(sat_candidates)

    candidates.sort(key=candidate_sort_key)
    summary.candidate_count = len(candidates)
    summary.zero_coverage_candidate_count = sum(1 for candidate in candidates if not candidate.coverage_sample_ids)
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
    sf_sat = EarthSatellite(
        satellite.tle_line1,
        satellite.tle_line2,
        name=satellite.satellite_id,
        ts=_TS,
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
                sf_sat=sf_sat,
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
            out.append(candidate)
            summary.per_satellite_candidate_counts[satellite.satellite_id] += 1
    return out


def _candidate_at(
    *,
    case: RegionalCoverageCase,
    satellite: Satellite,
    sf_sat: EarthSatellite,
    start_offset_s: int,
    duration_s: int,
    roll_deg: float,
    index: CoverageIndex,
) -> Candidate:
    start = offset_to_datetime(case.mission, start_offset_s)
    end_offset_s = start_offset_s + duration_s
    end = offset_to_datetime(case.mission, end_offset_s)
    mid = start + timedelta(seconds=duration_s / 2.0)
    before = start
    after = end

    sp_before = satellite_subpoint(sf_sat, before)
    sp_mid = satellite_subpoint(sf_sat, mid)
    sp_after = satellite_subpoint(sf_sat, after)
    heading_deg = initial_bearing_deg(
        sp_before.latitude_deg,
        sp_before.longitude_deg,
        sp_after.latitude_deg,
        sp_after.longitude_deg,
    )
    cross_bearing_deg = (heading_deg + (90.0 if roll_deg >= 0.0 else -90.0)) % 360.0
    roll_abs = abs(roll_deg)
    center_shift_m = roll_ground_range_m(sp_mid.altitude_m, roll_abs)
    center_lat, center_lon = destination_point(
        sp_mid.latitude_deg,
        sp_mid.longitude_deg,
        cross_bearing_deg,
        center_shift_m,
    )
    ground_track_m = haversine_m(
        sp_before.latitude_deg,
        sp_before.longitude_deg,
        sp_after.latitude_deg,
        sp_after.longitude_deg,
    )
    sample_spacing_m = _sample_spacing_m(case)
    cross_half_m = max(sample_spacing_m, 0.5 * swath_width_m(
        sp_mid.altitude_m,
        roll_abs,
        satellite.sensor.cross_track_fov_deg,
    ))
    along_half_m = max(sample_spacing_m, 0.5 * ground_track_m + sample_spacing_m)
    footprint = CoverageFootprint(
        center_latitude_deg=center_lat,
        center_longitude_deg=center_lon,
        heading_deg=heading_deg,
        along_half_m=along_half_m,
        cross_half_m=cross_half_m,
    )
    sample_ids = index.samples_for_footprint(footprint)
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
        footprint_center_latitude_deg=center_lat,
        footprint_center_longitude_deg=center_lon,
        footprint_heading_deg=heading_deg,
        along_half_m=along_half_m,
        cross_half_m=cross_half_m,
    )


def _sample_spacing_m(case: RegionalCoverageCase) -> float:
    manifest_path = case.case_dir / "manifest.json"
    # The parsed case intentionally keeps only solver-needed fields. Re-reading
    # this public value here avoids threading a rarely used grid detail through
    # every core data structure.
    try:
        import json

        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        return float(raw.get("grid_parameters", {}).get("sample_spacing_m", 5000.0))
    except (OSError, ValueError, TypeError):
        return 5000.0

