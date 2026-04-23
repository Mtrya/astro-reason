"""Candidate observation enumeration for the stereo_imaging CP/local-search solver.

Phase 7b changes:
- Optional parallel generation across satellites via ProcessPoolExecutor.
  EarthSatellite is reconstructed inside each worker from TLE strings because
  the underlying Satrec object is not pickleable.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
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
    parallel_workers: int | None = None  # None = auto (CPU count), 0 = disable

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
            parallel_workers=_optional_non_negative_int(
                payload.get("parallel_workers")
            ),
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


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    if parsed < 0:
        raise ValueError("parallel_workers must be a non-negative integer")
    return parsed


# ---------------------------------------------------------------------------
# Worker payload and function for parallel candidate generation
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _SatWorkerPayload:
    satellite_id: str
    sat_def: SatelliteDef
    targets: dict[str, TargetDef]
    target_ecef: dict[str, Any]
    mission: Mission
    config: CandidateConfig


def _generate_for_satellite(payload: _SatWorkerPayload) -> tuple[list[Candidate], CandidateSummary]:
    """Generate candidates for a single satellite.  Reconstructs EarthSatellite locally."""
    satellite_id = payload.satellite_id
    sat_def = payload.sat_def
    targets = payload.targets
    target_ecef = payload.target_ecef
    mission = payload.mission
    config = payload.config

    # Reconstruct EarthSatellite from TLE strings (Satrec is not pickleable)
    sf = EarthSatellite(sat_def.tle_line1, sat_def.tle_line2, name=satellite_id, ts=_TS)

    summary = CandidateSummary()
    summary.per_satellite_candidate_counts.setdefault(satellite_id, 0)
    candidates: list[Candidate] = []

    cap = config.max_candidates_per_target_per_sat
    interval_stride = timedelta(seconds=config.candidate_stride_s)
    duration = timedelta(seconds=config.observation_duration_s)

    for target_id, target in sorted(targets.items()):
        summary.per_target_candidate_counts.setdefault(target_id, 0)
        te = target_ecef[target_id]

        access_intervals = discover_access_intervals(
            sf, sat_def, target, te, mission,
            discovery_step_s=config.access_discovery_step_s,
        )
        if not access_intervals:
            summary.skipped_no_access_intervals += 1
            continue

        for interval_start, interval_end, access_interval_id in access_intervals:
            if cap is not None and summary.per_target_candidate_counts[target_id] >= cap:
                summary.skipped_cap += 1
                break

            start = interval_start
            while start + duration <= interval_end:
                if cap is not None and summary.per_target_candidate_counts[target_id] >= cap:
                    summary.skipped_cap += 1
                    break

                end = start + duration

                dur_s = (end - start).total_seconds()
                if dur_s < sat_def.min_obs_duration_s - 1e-6 or dur_s > sat_def.max_obs_duration_s + 1e-6:
                    summary.skipped_duration_bounds += 1
                    start += interval_stride
                    continue

                mid = start + (end - start) / 2
                sp, sv = _satellite_state_ecef_m(sf, mid)
                along_deg, across_deg = compute_steering_angles_to_target(sp, sv, te)

                comb = _combined_off_nadir_deg(along_deg, across_deg)
                if comb > sat_def.max_off_nadir_deg + 1e-6:
                    summary.skipped_off_nadir += 1
                    start += interval_stride
                    continue

                gp = _boresight_ground_intercept_ecef_m(sp, sv, along_deg, across_deg)
                if gp is None:
                    summary.skipped_boresight_no_intercept += 1
                    start += interval_stride
                    continue

                epoch = _datetime_to_epoch(mid)
                el, _ = _solar_elevation_azimuth_deg(epoch, te)
                if el < mission.min_solar_elevation_deg - 1e-6:
                    summary.skipped_solar_elevation += 1
                    start += interval_stride
                    continue

                step_s = _access_interval_sampling_step_s(sat_def)
                if not _access_holds_over_window(
                    sf, target, te, sat_def, mission, start, end, step_s=step_s
                ):
                    summary.skipped_outside_access_interval += 1
                    start += interval_stride
                    continue

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


def generate_candidates(
    case: StereoCase,
    config: CandidateConfig | None = None,
) -> tuple[list[Candidate], CandidateSummary]:
    config = config or CandidateConfig()
    summary = CandidateSummary()
    all_candidates: list[Candidate] = []

    target_ecef: dict[str, Any] = {tid: _target_ecef_m(t) for tid, t in sorted(case.targets.items())}

    workers = config.parallel_workers
    use_parallel = workers != 0

    if use_parallel:
        payloads = []
        for satellite_id, sat_def in sorted(case.satellites.items()):
            payloads.append(
                _SatWorkerPayload(
                    satellite_id=satellite_id,
                    sat_def=sat_def,
                    targets=dict(case.targets),
                    target_ecef=target_ecef,
                    mission=case.mission,
                    config=config,
                )
            )

        max_workers = workers if workers is not None else min(os.cpu_count() or 1, len(payloads))
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_generate_for_satellite, payload): payload.satellite_id
                for payload in payloads
            }
            results: dict[str, tuple[list[Candidate], CandidateSummary]] = {}
            for future in futures:
                sat_id = futures[future]
                results[sat_id] = future.result()

        # Combine in deterministic satellite order
        for satellite_id, _ in sorted(case.satellites.items()):
            sat_candidates, sat_summary = results[satellite_id]
            all_candidates.extend(sat_candidates)
            summary.candidate_count += sat_summary.candidate_count
            summary.per_satellite_candidate_counts[satellite_id] = (
                summary.per_satellite_candidate_counts.get(satellite_id, 0)
                + sat_summary.per_satellite_candidate_counts.get(satellite_id, 0)
            )
            for tid, count in sat_summary.per_target_candidate_counts.items():
                summary.per_target_candidate_counts[tid] = (
                    summary.per_target_candidate_counts.get(tid, 0) + count
                )
            for aid, count in sat_summary.per_access_interval_candidate_counts.items():
                summary.per_access_interval_candidate_counts[aid] = (
                    summary.per_access_interval_candidate_counts.get(aid, 0) + count
                )
            summary.skipped_no_access_intervals += sat_summary.skipped_no_access_intervals
            summary.skipped_outside_access_interval += sat_summary.skipped_outside_access_interval
            summary.skipped_off_nadir += sat_summary.skipped_off_nadir
            summary.skipped_boresight_no_intercept += sat_summary.skipped_boresight_no_intercept
            summary.skipped_duration_bounds += sat_summary.skipped_duration_bounds
            summary.skipped_solar_elevation += sat_summary.skipped_solar_elevation
            summary.skipped_cap += sat_summary.skipped_cap
    else:
        # Sequential fallback (original behavior)
        sf_sats: dict[str, EarthSatellite] = {}
        for sid, sd in sorted(case.satellites.items()):
            sf_sats[sid] = EarthSatellite(sd.tle_line1, sd.tle_line2, name=sid, ts=_TS)

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

                    start = interval_start
                    while start + duration <= interval_end:
                        if cap is not None and summary.per_target_candidate_counts[target_id] >= cap:
                            summary.skipped_cap += 1
                            break

                        end = start + duration

                        dur_s = (end - start).total_seconds()
                        if dur_s < sat_def.min_obs_duration_s - 1e-6 or dur_s > sat_def.max_obs_duration_s + 1e-6:
                            summary.skipped_duration_bounds += 1
                            start += interval_stride
                            continue

                        mid = start + (end - start) / 2
                        sp, sv = _satellite_state_ecef_m(sf, mid)
                        along_deg, across_deg = compute_steering_angles_to_target(sp, sv, te)

                        comb = _combined_off_nadir_deg(along_deg, across_deg)
                        if comb > sat_def.max_off_nadir_deg + 1e-6:
                            summary.skipped_off_nadir += 1
                            start += interval_stride
                            continue

                        gp = _boresight_ground_intercept_ecef_m(sp, sv, along_deg, across_deg)
                        if gp is None:
                            summary.skipped_boresight_no_intercept += 1
                            start += interval_stride
                            continue

                        epoch = _datetime_to_epoch(mid)
                        el, _ = _solar_elevation_azimuth_deg(epoch, te)
                        if el < case.mission.min_solar_elevation_deg - 1e-6:
                            summary.skipped_solar_elevation += 1
                            start += interval_stride
                            continue

                        step_s = _access_interval_sampling_step_s(sat_def)
                        if not _access_holds_over_window(
                            sf, target, te, sat_def, case.mission, start, end, step_s=step_s
                        ):
                            summary.skipped_outside_access_interval += 1
                            start += interval_stride
                            continue

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
                        all_candidates.append(candidate)
                        summary.candidate_count += 1
                        summary.per_satellite_candidate_counts[satellite_id] += 1
                        summary.per_target_candidate_counts[target_id] += 1
                        summary.per_access_interval_candidate_counts[access_interval_id] = (
                            summary.per_access_interval_candidate_counts.get(access_interval_id, 0) + 1
                        )
                        start += interval_stride

    return all_candidates, summary
