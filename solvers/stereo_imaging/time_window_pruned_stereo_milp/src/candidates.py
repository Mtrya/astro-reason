"""Deterministic candidate observation library with cheap local prechecks."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from multiprocessing import Pool
from typing import Any

import numpy as np
from skyfield.api import EarthSatellite, load
from skyfield.framelib import itrs

from geometry import (
    _TS,
    _datetime_to_epoch,
    combined_off_nadir_deg,
    line_of_sight_clear,
    make_earth_satellite,
    off_nadir_deg,
    required_steering_angles,
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


def _batch_access_predicate(
    sf_sat: EarthSatellite,
    te: np.ndarray,
    sat: Satellite,
    mission: Mission,
    dts: list[datetime],
) -> list[bool]:
    """Vectorized access check over a list of datetimes using a single skyfield Times batch."""
    if not dts:
        return []
    ts = _TS
    t = ts.from_datetimes([dt.astimezone(UTC) for dt in dts])
    g = sf_sat.at(t)
    pos_m, vel_mps = g.frame_xyz_and_velocity(itrs)
    pos_m = np.asarray(pos_m.km, dtype=float).T * 1000.0  # shape (N, 3)
    # Vectorized LOS clear
    los = te.reshape(1, 3) - pos_m  # shape (N, 3)
    dist = np.linalg.norm(los, axis=1)
    los_hat = los / dist.reshape(-1, 1)
    # Ray-ellipsoid intersection (simplified: check if target is above horizon)
    # For speed, use dot product with local up vector
    up = pos_m / np.linalg.norm(pos_m, axis=1).reshape(-1, 1)
    # up points from Earth center to satellite; target is visible when dot(los_hat, -up) > 0
    cos_el = np.sum(los_hat * up, axis=1)
    los_ok = cos_el < 0.0
    # Vectorized off-nadir
    nadir = -up
    cos_off = np.sum(nadir * los_hat, axis=1)
    cos_off = np.clip(cos_off, -1.0, 1.0)
    off_nadir = np.degrees(np.arccos(cos_off))
    off_ok = off_nadir <= sat.max_off_nadir_deg + 1e-6
    # Solar elevation (not easily vectorized with brahe; loop over epochs)
    results = []
    for i, dt in enumerate(dts):
        if not (los_ok[i] and off_ok[i]):
            results.append(False)
            continue
        epoch = _datetime_to_epoch(dt)
        se = solar_elevation_deg(epoch, te)
        results.append(se >= mission.validity_thresholds.min_solar_elevation_deg - 1e-6)
    return results


def find_access_intervals(
    sat: Satellite,
    target: Target,
    mission: Mission,
    *,
    time_step_s: float = 30.0,
    min_interval_length_s: float = 5.0,
) -> list[AccessInterval]:
    sf_sat = make_earth_satellite(sat)
    te = target_ecef_m(target)
    dts = list(_iter_horizon(mission.horizon_start, mission.horizon_end, time_step_s))
    ok_list = _batch_access_predicate(sf_sat, te, sat, mission, dts)

    raw: list[tuple[datetime, datetime]] = []
    current_start: datetime | None = None
    current_end: datetime | None = None

    for dt, ok in zip(dts, ok_list):
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
    """Legacy nadir-centered steering grid; kept for fallback mode."""
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


def _generate_target_centered_steering_grid(
    sat_pos_m: np.ndarray,
    sat_vel_mps: np.ndarray,
    target_ecef: np.ndarray,
    max_off_nadir_deg: float,
    along_samples: int,
    across_samples: int,
    spread_deg: float = 2.0,
) -> list[tuple[float, float]]:
    """Compute steering angles centered on the target, with a small grid around the exact pointing."""
    along_req, across_req = required_steering_angles(sat_pos_m, sat_vel_mps, target_ecef)
    if along_samples <= 0:
        along_samples = 1
    if across_samples <= 0:
        across_samples = 1
    if along_samples == 1:
        along_vals = [along_req]
    else:
        half = spread_deg * (along_samples - 1) / 2
        along_vals = np.linspace(along_req - half, along_req + half, along_samples)
    if across_samples == 1:
        across_vals = [across_req]
    else:
        half = spread_deg * (across_samples - 1) / 2
        across_vals = np.linspace(across_req - half, across_req + half, across_samples)
    grid: list[tuple[float, float]] = []
    for a in along_vals:
        for c in across_vals:
            if combined_off_nadir_deg(float(a), float(c)) <= max_off_nadir_deg + 1e-6:
                grid.append((float(a), float(c)))
    # deterministic ordering
    grid.sort(key=lambda x: (x[0], x[1]))
    return grid


def _generate_candidates_for_pair(
    sat: Satellite,
    target: Target,
    mission: Mission,
    time_step_s: float,
    sample_stride_s: float,
    max_candidates_per_interval: int,
    along_samples: int,
    across_samples: int,
    use_target_centered: bool,
    steering_spread_deg: float,
) -> tuple[list[CandidateObservation], list[RejectionRecord], CandidateSummary]:
    """Worker: generate candidates for a single (satellite, target) pair."""
    intervals = find_access_intervals(sat, target, mission, time_step_s=time_step_s)
    if not intervals:
        return [], [], CandidateSummary()

    sf_sat = make_earth_satellite(sat)
    te = target_ecef_m(target)
    candidates: list[CandidateObservation] = []
    rejections: list[RejectionRecord] = []
    summary = CandidateSummary()

    for interval in intervals:
        count = 0
        start_t = interval.start
        while start_t + timedelta(seconds=sat.min_obs_duration_s) <= interval.end:
            if count >= max_candidates_per_interval:
                break
            end_t = start_t + timedelta(seconds=sat.min_obs_duration_s)
            mid = start_t + (end_t - start_t) / 2
            sp, sv = satellite_state_ecef_m(sf_sat, mid)
            if use_target_centered:
                steering_grid = _generate_target_centered_steering_grid(
                    sp, sv, te, sat.max_off_nadir_deg,
                    along_samples, across_samples, steering_spread_deg,
                )
            else:
                steering_grid = _generate_steering_grid(
                    sat.max_off_nadir_deg, along_samples, across_samples
                )
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


def generate_candidates(
    mission: Mission,
    satellites: dict[str, Satellite],
    targets: dict[str, Target],
    config: dict[str, Any],
) -> tuple[list[CandidateObservation], list[RejectionRecord], CandidateSummary]:
    time_step_s = float(config.get("time_step_s", 30.0))
    sample_stride_s = float(config.get("sample_stride_s", 30.0))
    max_candidates_per_interval = int(config.get("max_candidates_per_interval", 20))
    along_samples = int(config.get("steering_along_samples", 1))
    across_samples = int(config.get("steering_across_samples", 1))

    use_target_centered = bool(config.get("use_target_centered_steering", True))
    steering_spread_deg = float(config.get("steering_grid_spread_deg", 2.0))
    parallel = bool(config.get("parallel_candidate_generation", True))

    pairs = [(sat, target) for sat in satellites.values() for target in targets.values()]
    n_workers = max(1, os.cpu_count() or 1)

    if parallel and len(pairs) >= 4 and n_workers > 1:
        with Pool(processes=n_workers) as pool:
            results = pool.starmap(
                _generate_candidates_for_pair,
                [
                    (
                        sat, target, mission, time_step_s, sample_stride_s,
                        max_candidates_per_interval, along_samples, across_samples,
                        use_target_centered, steering_spread_deg,
                    )
                    for sat, target in pairs
                ],
            )
        candidates: list[CandidateObservation] = []
        rejections: list[RejectionRecord] = []
        summary = CandidateSummary()
        for cands, rej, sm in results:
            candidates.extend(cands)
            rejections.extend(rej)
            # Merge summary
            summary.total_generated += sm.total_generated
            summary.total_accepted += sm.total_accepted
            summary.total_rejected += sm.total_rejected
            summary.by_satellite.update(sm.by_satellite)
            summary.by_target.update(sm.by_target)
            summary.by_interval.update(sm.by_interval)
            for reason, count in sm.by_reason.items():
                summary.by_reason[reason] = summary.by_reason.get(reason, 0) + count
        return candidates, rejections, summary

    # Sequential fallback
    candidates = []
    rejections = []
    summary = CandidateSummary()
    for sat, target in pairs:
        cands, rej, sm = _generate_candidates_for_pair(
            sat, target, mission, time_step_s, sample_stride_s,
            max_candidates_per_interval, along_samples, across_samples,
            use_target_centered, steering_spread_deg,
        )
        candidates.extend(cands)
        rejections.extend(rej)
        summary.total_generated += sm.total_generated
        summary.total_accepted += sm.total_accepted
        summary.total_rejected += sm.total_rejected
        summary.by_satellite.update(sm.by_satellite)
        summary.by_target.update(sm.by_target)
        summary.by_interval.update(sm.by_interval)
        for reason, count in sm.by_reason.items():
            summary.by_reason[reason] = summary.by_reason.get(reason, 0) + count
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
