"""Candidate observation enumeration for the stereo_imaging CP/local-search solver."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

from skyfield.api import EarthSatellite

from case_io import Mission, SatelliteDef, StereoCase, TargetDef
import math

import numpy as np

from geometry import (
    _TS,
    _access_holds_over_window,
    _access_interval_sampling_step_s,
    _boresight_ground_intercept_ecef_m,
    _combined_off_nadir_deg,
    _datetime_to_epoch,
    _iso_z,
    _off_nadir_deg,
    _satellite_state_ecef_m,
    _solar_elevation_azimuth_deg,
    _target_ecef_m,
    compute_steering_angles_to_target,
    discover_access_intervals,
)


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    observation_duration_s: float = 6.0
    candidate_stride_s: float = 10.0
    access_discovery_step_s: float = 60.0
    max_candidates_per_target_per_sat: int | None = None
    debug: bool = False

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "CandidateConfig":
        payload = payload or {}
        return cls(
            observation_duration_s=float(payload.get("observation_duration_s", 6.0)),
            candidate_stride_s=float(payload.get("candidate_stride_s", 10.0)),
            access_discovery_step_s=float(payload.get("access_discovery_step_s", 60.0)),
            max_candidates_per_target_per_sat=_optional_positive_int(
                payload.get("max_candidates_per_target_per_sat")
            ),
            debug=bool(payload.get("debug", False)),
        )

    def as_status_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    satellite_id: str
    target_id: str
    start: datetime
    end: datetime
    off_nadir_along_deg: float
    off_nadir_across_deg: float
    access_interval_id: str
    effective_pixel_scale_m: float
    slant_range_m: float
    boresight_off_nadir_deg: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "satellite_id": self.satellite_id,
            "target_id": self.target_id,
            "start": self.start.isoformat().replace("+00:00", "Z"),
            "end": self.end.isoformat().replace("+00:00", "Z"),
            "off_nadir_along_deg": self.off_nadir_along_deg,
            "off_nadir_across_deg": self.off_nadir_across_deg,
            "access_interval_id": self.access_interval_id,
            "effective_pixel_scale_m": self.effective_pixel_scale_m,
            "slant_range_m": self.slant_range_m,
            "boresight_off_nadir_deg": self.boresight_off_nadir_deg,
        }


@dataclass(slots=True)
class CandidateSummary:
    candidate_count: int = 0
    per_satellite_candidate_counts: dict[str, int] = field(default_factory=dict)
    per_target_candidate_counts: dict[str, int] = field(default_factory=dict)
    per_access_interval_candidate_counts: dict[str, int] = field(default_factory=dict)
    skipped_no_access_intervals: int = 0
    skipped_outside_access_interval: int = 0
    skipped_off_nadir: int = 0
    skipped_boresight_no_intercept: int = 0
    skipped_duration_bounds: int = 0
    skipped_solar_elevation: int = 0
    skipped_cap: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": self.candidate_count,
            "per_satellite_candidate_counts": dict(sorted(self.per_satellite_candidate_counts.items())),
            "per_target_candidate_counts": dict(sorted(self.per_target_candidate_counts.items())),
            "per_access_interval_candidate_counts": dict(
                sorted(self.per_access_interval_candidate_counts.items())
            ),
            "skipped_no_access_intervals": self.skipped_no_access_intervals,
            "skipped_outside_access_interval": self.skipped_outside_access_interval,
            "skipped_off_nadir": self.skipped_off_nadir,
            "skipped_boresight_no_intercept": self.skipped_boresight_no_intercept,
            "skipped_duration_bounds": self.skipped_duration_bounds,
            "skipped_solar_elevation": self.skipped_solar_elevation,
            "skipped_cap": self.skipped_cap,
        }


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("candidate cap values must be positive integers")
    return parsed


def generate_candidates(
    case: StereoCase,
    config: CandidateConfig | None = None,
) -> tuple[list[Candidate], CandidateSummary]:
    config = config or CandidateConfig()
    summary = CandidateSummary()
    candidates: list[Candidate] = []

    # Cache EarthSatellite objects and target ECEF positions
    sf_sats: dict[str, EarthSatellite] = {}
    for sid, sd in sorted(case.satellites.items()):
        sf_sats[sid] = EarthSatellite(sd.tle_line1, sd.tle_line2, name=sid, ts=_TS)

    target_ecef: dict[str, Any] = {tid: _target_ecef_m(t) for tid, t in sorted(case.targets.items())}

    for satellite_id, sat_def in sorted(case.satellites.items()):
        sf = sf_sats[satellite_id]
        summary.per_satellite_candidate_counts.setdefault(satellite_id, 0)

        for target_id, target in sorted(case.targets.items()):
            summary.per_target_candidate_counts.setdefault(target_id, 0)
            te = target_ecef[target_id]

            access_intervals = discover_access_intervals(
                sf, sat_def, target, te, case.mission,
                discovery_step_s=config.access_discovery_step_s,
            )
            if not access_intervals:
                summary.skipped_no_access_intervals += 1
                continue

            cap = config.max_candidates_per_target_per_sat
            interval_stride = timedelta(seconds=config.candidate_stride_s)
            duration = timedelta(seconds=config.observation_duration_s)

            for interval_start, interval_end, access_interval_id in access_intervals:
                if cap is not None and summary.per_target_candidate_counts[target_id] >= cap:
                    summary.skipped_cap += 1
                    break

                # Sample start times within the interval
                start = interval_start
                while start + duration <= interval_end:
                    if cap is not None and summary.per_target_candidate_counts[target_id] >= cap:
                        summary.skipped_cap += 1
                        break

                    end = start + duration

                    # Check duration bounds
                    dur_s = (end - start).total_seconds()
                    if dur_s < sat_def.min_obs_duration_s - 1e-6 or dur_s > sat_def.max_obs_duration_s + 1e-6:
                        summary.skipped_duration_bounds += 1
                        start += interval_stride
                        continue

                    # Compute steering angles at midpoint to point at target
                    mid = start + (end - start) / 2
                    sp, sv = _satellite_state_ecef_m(sf, mid)
                    along_deg, across_deg = compute_steering_angles_to_target(sp, sv, te)

                    # Check combined off-nadir
                    comb = _combined_off_nadir_deg(along_deg, across_deg)
                    if comb > sat_def.max_off_nadir_deg + 1e-6:
                        summary.skipped_off_nadir += 1
                        start += interval_stride
                        continue

                    # Check boresight intercepts Earth
                    gp = _boresight_ground_intercept_ecef_m(sp, sv, along_deg, across_deg)
                    if gp is None:
                        summary.skipped_boresight_no_intercept += 1
                        start += interval_stride
                        continue

                    # Check solar elevation at midpoint
                    epoch = _datetime_to_epoch(mid)
                    el, _ = _solar_elevation_azimuth_deg(epoch, te)
                    if el < case.mission.min_solar_elevation_deg - 1e-6:
                        summary.skipped_solar_elevation += 1
                        start += interval_stride
                        continue

                    # Verify full window access containment
                    step_s = _access_interval_sampling_step_s(sat_def)
                    if not _access_holds_over_window(
                        sf, target, te, sat_def, case.mission, start, end, step_s=step_s
                    ):
                        summary.skipped_outside_access_interval += 1
                        start += interval_stride
                        continue

                    # Compute derived geometry
                    off = _off_nadir_deg(sp, te)
                    slant = float(np.linalg.norm(gp - sp))
                    eff_px = slant * sat_def.pixel_ifov_deg * (math.pi / 180.0)

                    candidate = Candidate(
                        candidate_id=f"{satellite_id}|{target_id}|{access_interval_id}|{_iso_z(start)}",
                        satellite_id=satellite_id,
                        target_id=target_id,
                        start=start,
                        end=end,
                        off_nadir_along_deg=along_deg,
                        off_nadir_across_deg=across_deg,
                        access_interval_id=access_interval_id,
                        effective_pixel_scale_m=float(eff_px),
                        slant_range_m=float(slant),
                        boresight_off_nadir_deg=float(off),
                    )
                    candidates.append(candidate)
                    summary.candidate_count += 1
                    summary.per_satellite_candidate_counts[satellite_id] += 1
                    summary.per_target_candidate_counts[target_id] += 1
                    summary.per_access_interval_candidate_counts[access_interval_id] = (
                        summary.per_access_interval_candidate_counts.get(access_interval_id, 0) + 1
                    )
                    start += interval_stride

    return candidates, summary



