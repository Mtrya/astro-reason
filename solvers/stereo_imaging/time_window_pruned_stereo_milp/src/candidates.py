"""Deterministic candidate observation library with cheap local prechecks."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
from skyfield.api import EarthSatellite

from geometry import (
    _datetime_to_epoch,
    combined_off_nadir_deg,
    line_of_sight_clear,
    make_earth_satellite,
    off_nadir_deg,
    satellite_state_ecef_m,
    solar_elevation_deg,
    target_ecef_m,
)
from models import (
    AccessInterval,
    CandidateObservation,
    CandidateSummary,
    Mission,
    RejectionRecord,
    Satellite,
    Target,
)


def _iter_horizon(start: datetime, end: datetime, step_s: float):
    step = timedelta(seconds=step_s)
    current = start
    while current <= end:
        yield current
        current += step


def _access_predicate(
    sf_sat: EarthSatellite,
    target_ecef: np.ndarray,
    sat_def: Satellite,
    mission: Mission,
    dt: datetime,
) -> bool:
    sp, _ = satellite_state_ecef_m(sf_sat, dt)
    if not line_of_sight_clear(sp, target_ecef):
        return False
    if off_nadir_deg(sp, target_ecef) > sat_def.max_off_nadir_deg + 1e-6:
        return False
    epoch = _datetime_to_epoch(dt)
    if solar_elevation_deg(epoch, target_ecef) < mission.validity_thresholds.min_solar_elevation_deg - 1e-6:
        return False
    return True


def find_access_intervals(
    sat: Satellite,
    target: Target,
    mission: Mission,
    *,
    time_step_s: float = 60.0,
    min_interval_length_s: float = 5.0,
) -> list[AccessInterval]:
    sf_sat = make_earth_satellite(sat)
    te = target_ecef_m(target)
    raw: list[tuple[datetime, datetime]] = []
    current_start: datetime | None = None
    current_end: datetime | None = None

    for dt in _iter_horizon(mission.horizon_start, mission.horizon_end, time_step_s):
        ok = _access_predicate(sf_sat, te, sat, mission, dt)
        if ok:
            if current_start is None:
                current_start = dt
            current_end = dt
        else:
            if current_start is not None and current_end is not None:
                raw.append((current_start, current_end))
            current_start = None
            current_end = None

    if current_start is not None and current_end is not None:
        raw.append((current_start, current_end))

    intervals: list[AccessInterval] = []
    for idx, (s, e) in enumerate(raw):
        length = (e - s).total_seconds()
        if length < min_interval_length_s:
            continue
        aid = f"{sat.id}::{target.id}::{idx}"
        intervals.append(
            AccessInterval(
                sat_id=sat.id,
                target_id=target.id,
                interval_id=aid,
                start=s,
                end=e,
            )
        )
    return intervals


def _generate_steering_grid(max_off_nadir_deg: float, along_samples: int, across_samples: int) -> list[tuple[float, float]]:
    if along_samples <= 0:
        along_samples = 1
    if across_samples <= 0:
        across_samples = 1
    along_vals = np.linspace(-max_off_nadir_deg, max_off_nadir_deg, along_samples)
    across_vals = np.linspace(-max_off_nadir_deg, max_off_nadir_deg, across_samples)
    grid: list[tuple[float, float]] = []
    for a in along_vals:
        for c in across_vals:
            if combined_off_nadir_deg(float(a), float(c)) <= max_off_nadir_deg + 1e-6:
                grid.append((float(a), float(c)))
    # deterministic ordering
    grid.sort(key=lambda x: (x[0], x[1]))
    return grid


def generate_candidates(
    mission: Mission,
    satellites: dict[str, Satellite],
    targets: dict[str, Target],
    config: dict[str, Any],
) -> tuple[list[CandidateObservation], list[RejectionRecord], CandidateSummary]:
    time_step_s = float(config.get("time_step_s", 60.0))
    sample_stride_s = float(config.get("sample_stride_s", 30.0))
    max_candidates_per_interval = int(config.get("max_candidates_per_interval", 20))
    along_samples = int(config.get("steering_along_samples", 3))
    across_samples = int(config.get("steering_across_samples", 3))

    candidates: list[CandidateObservation] = []
    rejections: list[RejectionRecord] = []
    summary = CandidateSummary()

    for sat in satellites.values():
        for target in targets.values():
            intervals = find_access_intervals(
                sat, target, mission, time_step_s=time_step_s
            )
            if not intervals:
                continue
            steering_grid = _generate_steering_grid(
                sat.max_off_nadir_deg, along_samples, across_samples
            )
            for interval in intervals:
                count = 0
                start_t = interval.start
                while start_t + timedelta(seconds=sat.min_obs_duration_s) <= interval.end:
                    if count >= max_candidates_per_interval:
                        break
                    # use fixed duration = min_obs_duration_s for deterministic simplicity
                    end_t = start_t + timedelta(seconds=sat.min_obs_duration_s)
                    for along, across in steering_grid:
                        if count >= max_candidates_per_interval:
                            break
                        cand, reason = _evaluate_candidate(
                            sat, target, interval, start_t, end_t, along, across, mission
                        )
                        if cand is not None:
                            candidates.append(cand)
                            summary.record(
                                accepted=True,
                                sat_id=sat.id,
                                target_id=target.id,
                                interval_id=interval.interval_id,
                            )
                            count += 1
                        else:
                            rejections.append(
                                RejectionRecord(
                                    sat_id=sat.id,
                                    target_id=target.id,
                                    interval_id=interval.interval_id,
                                    reason=reason or "unknown",
                                    start=start_t,
                                    end=end_t,
                                )
                            )
                            summary.record(
                                accepted=False,
                                sat_id=sat.id,
                                target_id=target.id,
                                interval_id=interval.interval_id,
                                reason=reason,
                            )
                    start_t += timedelta(seconds=sample_stride_s)

    return candidates, rejections, summary


def _evaluate_candidate(
    sat: Satellite,
    target: Target,
    interval: AccessInterval,
    start: datetime,
    end: datetime,
    along: float,
    across: float,
    mission: Mission,
) -> tuple[CandidateObservation | None, str | None]:
    # horizon containment
    if start < mission.horizon_start or end > mission.horizon_end:
        return None, "horizon"

    dur = (end - start).total_seconds()
    if dur + 1e-6 < sat.min_obs_duration_s or dur - 1e-6 > sat.max_obs_duration_s:
        return None, "duration"

    comb = combined_off_nadir_deg(along, across)
    if comb - 1e-6 > sat.max_off_nadir_deg:
        return None, "off_nadir"

    # solar elevation at midpoint (cheap approximation)
    mid = start + (end - start) / 2
    te = target_ecef_m(target)
    epoch = _datetime_to_epoch(mid)
    se = solar_elevation_deg(epoch, te)
    if se < mission.validity_thresholds.min_solar_elevation_deg - 1e-6:
        return None, "solar_elevation"

    # optional: LOS at midpoint
    sf_sat = make_earth_satellite(sat)
    sp, _ = satellite_state_ecef_m(sf_sat, mid)
    if not line_of_sight_clear(sp, te):
        return None, "los"

    return CandidateObservation(
        sat_id=sat.id,
        target_id=target.id,
        access_interval_id=interval.interval_id,
        start=start,
        end=end,
        off_nadir_along_deg=along,
        off_nadir_across_deg=across,
        combined_off_nadir_deg=comb,
    ), None
