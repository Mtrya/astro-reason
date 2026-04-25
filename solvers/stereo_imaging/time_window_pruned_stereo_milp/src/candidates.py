"""Deterministic candidate observation library with cheap local prechecks."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from multiprocessing import Pool
from typing import Any

import numpy as np
from skyfield.api import EarthSatellite
from skyfield.framelib import itrs

from geometry import (
    _TS,
    _datetime_to_epoch,
    combined_off_nadir_deg,
    line_of_sight_clear,
    make_earth_satellite,
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


@dataclass
class _SatelliteStateSeries:
    sat: Satellite
    sf_sat: EarthSatellite
    dts: list[datetime]
    epochs: list[Any]
    pos_m: np.ndarray
    vel_mps: np.ndarray
    up: np.ndarray


def _iter_horizon(start: datetime, end: datetime, step_s: float):
    step = timedelta(seconds=step_s)
    current = start
    while current <= end:
        yield current
        current += step


def _build_satellite_state_series(
    sat: Satellite,
    mission: Mission,
    time_step_s: float,
) -> _SatelliteStateSeries:
    dts = list(_iter_horizon(mission.horizon_start, mission.horizon_end, time_step_s))
    if not dts:
        return _SatelliteStateSeries(
            sat=sat,
            sf_sat=make_earth_satellite(sat),
            dts=[],
            epochs=[],
            pos_m=np.zeros((0, 3), dtype=float),
            vel_mps=np.zeros((0, 3), dtype=float),
            up=np.zeros((0, 3), dtype=float),
        )
    sf_sat = make_earth_satellite(sat)
    t = _TS.from_datetimes([dt.astimezone(UTC) for dt in dts])
    g = sf_sat.at(t)
    pos_m, vel_mps = g.frame_xyz_and_velocity(itrs)
    pos_m = np.asarray(pos_m.km, dtype=float).T * 1000.0
    vel_mps = np.asarray(vel_mps.km_per_s, dtype=float).T * 1000.0
    norms = np.linalg.norm(pos_m, axis=1).reshape(-1, 1)
    up = pos_m / norms
    return _SatelliteStateSeries(
        sat=sat,
        sf_sat=sf_sat,
        dts=dts,
        epochs=[_datetime_to_epoch(dt) for dt in dts],
        pos_m=pos_m,
        vel_mps=vel_mps,
        up=up,
    )


def _build_access_mask(
    series: _SatelliteStateSeries,
    target_ecef: np.ndarray,
    mission: Mission,
) -> tuple[list[bool], int]:
    if not series.dts:
        return [], 0

    los = target_ecef.reshape(1, 3) - series.pos_m
    dist = np.linalg.norm(los, axis=1)
    safe = dist > 1.0e-9
    los_hat = np.zeros_like(los)
    los_hat[safe] = los[safe] / dist[safe].reshape(-1, 1)

    cos_el = np.sum(los_hat * series.up, axis=1)
    los_ok = safe & (cos_el < 0.0)

    nadir = -series.up
    cos_off = np.sum(nadir * los_hat, axis=1)
    cos_off = np.clip(cos_off, -1.0, 1.0)
    off_nadir = np.degrees(np.arccos(cos_off))
    off_ok = off_nadir <= series.sat.max_off_nadir_deg + 1e-6

    mask = np.zeros(len(series.dts), dtype=bool)
    solar_checks = 0
    threshold = mission.validity_thresholds.min_solar_elevation_deg - 1e-6
    viable_indices = np.flatnonzero(los_ok & off_ok)
    for idx in viable_indices:
        solar_checks += 1
        mask[idx] = solar_elevation_deg(series.epochs[idx], target_ecef) >= threshold
    return mask.tolist(), solar_checks


def _intervals_from_mask(
    sat: Satellite,
    target: Target,
    dts: list[datetime],
    ok_list: list[bool],
    *,
    min_interval_length_s: float,
) -> list[AccessInterval]:
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
        if (e - s).total_seconds() < min_interval_length_s:
            continue
        intervals.append(
            AccessInterval(
                sat_id=sat.id,
                target_id=target.id,
                interval_id=f"{sat.id}::{target.id}::{idx}",
                start=s,
                end=e,
            )
        )
    return intervals


def find_access_intervals(
    sat: Satellite,
    target: Target,
    mission: Mission,
    *,
    time_step_s: float = 30.0,
    min_interval_length_s: float = 5.0,
) -> list[AccessInterval]:
    series = _build_satellite_state_series(sat, mission, time_step_s)
    ok_list, _ = _build_access_mask(series, target_ecef_m(target), mission)
    return _intervals_from_mask(sat, target, series.dts, ok_list, min_interval_length_s=min_interval_length_s)


def _generate_steering_grid(max_off_nadir_deg: float, along_samples: int, across_samples: int) -> list[tuple[float, float]]:
    """Legacy nadir-centered steering grid; kept for explicit grid mode."""
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


def _cached_satellite_state(
    sf_sat: EarthSatellite,
    dt: datetime,
    state_cache: dict[datetime, tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray]:
    state = state_cache.get(dt)
    if state is None:
        state = satellite_state_ecef_m(sf_sat, dt)
        state_cache[dt] = state
    return state


def _evaluate_candidate(
    sat: Satellite,
    target: Target,
    interval: AccessInterval,
    start: datetime,
    end: datetime,
    along: float,
    across: float,
    mission: Mission,
    sf_sat: EarthSatellite,
    target_ecef: np.ndarray,
    sat_state: tuple[np.ndarray, np.ndarray] | None = None,
    state_cache: dict[datetime, tuple[np.ndarray, np.ndarray]] | None = None,
    solar_cache: dict[datetime, bool] | None = None,
    los_cache: dict[datetime, bool] | None = None,
    profile: dict[str, Any] | None = None,
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
    if solar_cache is not None and mid in solar_cache:
        solar_ok = solar_cache[mid]
    else:
        if profile is not None:
            profile["solar_checks"] = profile.get("solar_checks", 0) + 1
        solar_ok = solar_elevation_deg(_datetime_to_epoch(mid), target_ecef) >= (
            mission.validity_thresholds.min_solar_elevation_deg - 1e-6
        )
        if solar_cache is not None:
            solar_cache[mid] = solar_ok
    if not solar_ok:
        return None, "solar_elevation"

    # optional: LOS at midpoint
    if los_cache is not None and mid in los_cache:
        los_ok = los_cache[mid]
    else:
        if sat_state is not None:
            sp, _ = sat_state
        elif state_cache is not None:
            sp, _ = _cached_satellite_state(sf_sat, mid, state_cache)
        else:
            sp, _ = satellite_state_ecef_m(sf_sat, mid)
        los_ok = line_of_sight_clear(sp, target_ecef)
        if los_cache is not None:
            los_cache[mid] = los_ok
    if not los_ok:
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


def _merge_candidate_summary(into: CandidateSummary, other: CandidateSummary) -> None:
    into.total_generated += other.total_generated
    into.total_accepted += other.total_accepted
    into.total_rejected += other.total_rejected
    for bucket_name in ("by_satellite", "by_target", "by_interval"):
        into_bucket = getattr(into, bucket_name)
        other_bucket = getattr(other, bucket_name)
        for ident, counts in other_bucket.items():
            dst = into_bucket.setdefault(ident, {})
            for key, value in counts.items():
                dst[key] = dst.get(key, 0) + value
    for reason, count in other.by_reason.items():
        into.by_reason[reason] = into.by_reason.get(reason, 0) + count
    for key, value in other.profiling.items():
        if isinstance(value, (int, float)):
            into.profiling[key] = into.profiling.get(key, 0) + value
        else:
            into.profiling[key] = value


def _generate_candidates_for_satellite(
    sat: Satellite,
    target_list: list[Target],
    mission: Mission,
    time_step_s: float,
    sample_stride_s: float,
    max_candidates_per_interval: int,
    along_samples: int,
    across_samples: int,
    use_target_centered: bool,
    steering_spread_deg: float,
) -> tuple[list[CandidateObservation], list[RejectionRecord], CandidateSummary]:
    worker_start = time.perf_counter()
    summary = CandidateSummary()
    profile = {
        "satellite_workers": 1,
        "state_batch_build_s": 0.0,
        "access_interval_search_s": 0.0,
        "candidate_sampling_s": 0.0,
        "solar_checks": 0,
        "candidates_emitted": 0,
    }

    series_start = time.perf_counter()
    series = _build_satellite_state_series(sat, mission, time_step_s)
    profile["state_batch_build_s"] += time.perf_counter() - series_start

    candidates: list[CandidateObservation] = []
    rejections: list[RejectionRecord] = []

    for target in target_list:
        target_ecef = target_ecef_m(target)

        access_start = time.perf_counter()
        ok_list, solar_checks = _build_access_mask(series, target_ecef, mission)
        intervals = _intervals_from_mask(sat, target, series.dts, ok_list, min_interval_length_s=5.0)
        profile["access_interval_search_s"] += time.perf_counter() - access_start
        profile["solar_checks"] += solar_checks

        if not intervals:
            continue

        state_cache: dict[datetime, tuple[np.ndarray, np.ndarray]] = {}
        solar_cache: dict[datetime, bool] = {}
        los_cache: dict[datetime, bool] = {}

        for interval in intervals:
            count = 0
            start_t = interval.start
            while start_t + timedelta(seconds=sat.min_obs_duration_s) <= interval.end:
                if count >= max_candidates_per_interval:
                    break
                end_t = start_t + timedelta(seconds=sat.min_obs_duration_s)
                mid = start_t + (end_t - start_t) / 2

                sampling_start = time.perf_counter()
                sp, sv = _cached_satellite_state(series.sf_sat, mid, state_cache)
                if use_target_centered:
                    steering_grid = _generate_target_centered_steering_grid(
                        sp,
                        sv,
                        target_ecef,
                        sat.max_off_nadir_deg,
                        along_samples,
                        across_samples,
                        steering_spread_deg,
                    )
                else:
                    steering_grid = _generate_steering_grid(sat.max_off_nadir_deg, along_samples, across_samples)

                for along, across in steering_grid:
                    if count >= max_candidates_per_interval:
                        break
                    cand, reason = _evaluate_candidate(
                        sat,
                        target,
                        interval,
                        start_t,
                        end_t,
                        along,
                        across,
                        mission,
                        series.sf_sat,
                        target_ecef,
                        sat_state=(sp, sv),
                        state_cache=state_cache,
                        solar_cache=solar_cache,
                        los_cache=los_cache,
                        profile=profile,
                    )
                    if cand is not None:
                        candidates.append(cand)
                        summary.record(True, sat.id, target.id, interval.interval_id)
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
                        summary.record(False, sat.id, target.id, interval.interval_id, reason=reason)
                profile["candidate_sampling_s"] += time.perf_counter() - sampling_start
                start_t += timedelta(seconds=sample_stride_s)

    profile["candidates_emitted"] = len(candidates)
    profile["total_s"] = time.perf_counter() - worker_start
    summary.profiling = profile
    return candidates, rejections, summary


def generate_candidates(
    mission: Mission,
    satellites: dict[str, Satellite],
    targets: dict[str, Target],
    config: dict[str, Any],
) -> tuple[list[CandidateObservation], list[RejectionRecord], CandidateSummary]:
    total_start = time.perf_counter()
    time_step_s = float(config.get("time_step_s", 30.0))
    sample_stride_s = float(config.get("sample_stride_s", 30.0))
    max_candidates_per_interval = int(config.get("max_candidates_per_interval", 20))
    along_samples = int(config.get("steering_along_samples", 1))
    across_samples = int(config.get("steering_across_samples", 1))
    use_target_centered = bool(config.get("use_target_centered_steering", True))
    steering_spread_deg = float(config.get("steering_grid_spread_deg", 2.0))
    parallel = bool(config.get("parallel_candidate_generation", True))

    ordered_satellites = [satellites[sid] for sid in sorted(satellites)]
    ordered_targets = [targets[tid] for tid in sorted(targets)]
    n_workers = max(1, os.cpu_count() or 1)

    if parallel and len(ordered_satellites) >= 2 and n_workers > 1:
        with Pool(processes=min(n_workers, len(ordered_satellites))) as pool:
            results = pool.starmap(
                _generate_candidates_for_satellite,
                [
                    (
                        sat,
                        ordered_targets,
                        mission,
                        time_step_s,
                        sample_stride_s,
                        max_candidates_per_interval,
                        along_samples,
                        across_samples,
                        use_target_centered,
                        steering_spread_deg,
                    )
                    for sat in ordered_satellites
                ],
            )
    else:
        results = [
            _generate_candidates_for_satellite(
                sat,
                ordered_targets,
                mission,
                time_step_s,
                sample_stride_s,
                max_candidates_per_interval,
                along_samples,
                across_samples,
                use_target_centered,
                steering_spread_deg,
            )
            for sat in ordered_satellites
        ]

    candidates: list[CandidateObservation] = []
    rejections: list[RejectionRecord] = []
    summary = CandidateSummary()
    for cands, rej, sm in results:
        candidates.extend(cands)
        rejections.extend(rej)
        _merge_candidate_summary(summary, sm)

    summary.profiling.setdefault("satellite_workers", len(results))
    summary.profiling["total_s"] = time.perf_counter() - total_start
    summary.profiling["candidates_emitted"] = len(candidates)
    candidates.sort(
        key=lambda c: (
            c.sat_id,
            c.target_id,
            c.access_interval_id,
            c.start,
            c.end,
            c.off_nadir_along_deg,
            c.off_nadir_across_deg,
        )
    )
    rejections.sort(
        key=lambda r: (
            r.sat_id,
            r.target_id,
            r.interval_id,
            r.start or mission.horizon_start,
            r.end or mission.horizon_start,
            r.reason,
        )
    )
    return candidates, rejections, summary
