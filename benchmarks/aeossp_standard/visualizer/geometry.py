"""Visualizer-local geometry helpers for aeossp_standard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import brahe
import numpy as np
from skyfield.api import EarthSatellite, load, wgs84
from skyfield.framelib import itrs


_TS = load.timescale(builtin=True)
_NUMERICAL_EPS = 1.0e-9


@dataclass(frozen=True)
class AccessInterval:
    satellite_id: str
    start_index: int
    end_index: int
    start_time: datetime
    end_time: datetime
    duration_s: int
    midpoint_time: datetime
    min_off_nadir_deg: float
    max_off_nadir_deg: float


@dataclass(frozen=True)
class OrbitSampleGrid:
    start_time: datetime
    end_time: datetime
    step_s: int
    sample_times: tuple[datetime, ...]
    positions_ecef_m: dict[str, np.ndarray]
    longitudes_deg: dict[str, np.ndarray]
    latitudes_deg: dict[str, np.ndarray]


def parse_iso_utc(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(UTC)


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def sample_times(
    start_time: datetime,
    end_time: datetime,
    *,
    step_s: int,
) -> tuple[datetime, ...]:
    if step_s <= 0:
        raise ValueError("step_s must be > 0")
    start_time = start_time.astimezone(UTC)
    end_time = end_time.astimezone(UTC)
    if end_time < start_time:
        raise ValueError("end_time must be >= start_time")
    n_steps = int((end_time - start_time).total_seconds() // step_s)
    return tuple(start_time + timedelta(seconds=step_s * idx) for idx in range(n_steps + 1))


def build_satellite_cache(satellites: list[dict[str, Any]]) -> dict[str, EarthSatellite]:
    return {
        sat["satellite_id"]: EarthSatellite(
            sat["tle_line1"],
            sat["tle_line2"],
            name=sat["satellite_id"],
            ts=_TS,
        )
        for sat in satellites
    }


def sample_orbit_grid(
    satellites: list[dict[str, Any]],
    *,
    start_time: datetime,
    end_time: datetime,
    step_s: int,
) -> OrbitSampleGrid:
    instants = sample_times(start_time, end_time, step_s=step_s)
    ts = _TS.from_datetimes(list(instants))
    sat_cache = build_satellite_cache(satellites)

    positions_ecef_m: dict[str, np.ndarray] = {}
    longitudes_deg: dict[str, np.ndarray] = {}
    latitudes_deg: dict[str, np.ndarray] = {}
    for sat in satellites:
        sat_id = sat["satellite_id"]
        geocentric = sat_cache[sat_id].at(ts)
        pos, _vel = geocentric.frame_xyz_and_velocity(itrs)
        pos_m = np.asarray(pos.km, dtype=float).T * 1000.0
        positions_ecef_m[sat_id] = pos_m
        subpoint = wgs84.subpoint_of(geocentric)
        longitudes_deg[sat_id] = np.asarray(subpoint.longitude.degrees, dtype=float)
        latitudes_deg[sat_id] = np.asarray(subpoint.latitude.degrees, dtype=float)

    return OrbitSampleGrid(
        start_time=start_time.astimezone(UTC),
        end_time=end_time.astimezone(UTC),
        step_s=step_s,
        sample_times=instants,
        positions_ecef_m=positions_ecef_m,
        longitudes_deg=longitudes_deg,
        latitudes_deg=latitudes_deg,
    )


def task_target_ecef_m(task_like: dict[str, Any]) -> np.ndarray:
    return np.asarray(
        brahe.position_geodetic_to_ecef(
            [
                float(task_like["longitude_deg"]),
                float(task_like["latitude_deg"]),
                float(task_like.get("altitude_m", 0.0)),
            ],
            brahe.AngleFormat.DEGREES,
        ),
        dtype=float,
    ).reshape(3)


def _angle_between_deg(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    na = np.linalg.norm(a, axis=1)
    nb = np.linalg.norm(b, axis=1)
    safe = (na > _NUMERICAL_EPS) & (nb > _NUMERICAL_EPS)
    cosines = np.ones_like(na)
    cosines[safe] = np.sum(a[safe] * b[safe], axis=1) / (na[safe] * nb[safe])
    np.clip(cosines, -1.0, 1.0, out=cosines)
    return np.degrees(np.arccos(cosines))


def access_mask_for_satellite(
    task_like: dict[str, Any],
    satellite_def: dict[str, Any],
    sampled_positions_ecef_m: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if satellite_def["sensor"]["sensor_type"] != task_like["required_sensor_type"]:
        n_samples = sampled_positions_ecef_m.shape[0]
        return np.zeros(n_samples, dtype=bool), np.full(n_samples, np.inf, dtype=float)

    target_ecef_m = task_target_ecef_m(task_like)
    target_norm = float(np.linalg.norm(target_ecef_m))
    if target_norm < _NUMERICAL_EPS:
        n_samples = sampled_positions_ecef_m.shape[0]
        return np.zeros(n_samples, dtype=bool), np.full(n_samples, np.inf, dtype=float)

    los_vectors = target_ecef_m[None, :] - sampled_positions_ecef_m
    target_normal = target_ecef_m / target_norm
    above_horizon = np.einsum(
        "ij,j->i",
        sampled_positions_ecef_m - target_ecef_m[None, :],
        target_normal,
    ) > 0.0
    off_nadir_deg = _angle_between_deg(-sampled_positions_ecef_m, los_vectors)
    max_off_nadir = float(satellite_def["attitude_model"]["max_off_nadir_deg"])
    access_mask = above_horizon & (off_nadir_deg <= max_off_nadir + 1.0e-9)
    return access_mask, off_nadir_deg


def derive_task_access_intervals(
    task_like: dict[str, Any],
    satellites: list[dict[str, Any]],
    orbit_grid: OrbitSampleGrid,
    *,
    compatible_satellite_ids: set[str] | None = None,
    min_duration_s: int | None = None,
) -> list[AccessInterval]:
    required_duration_s = int(
        min_duration_s if min_duration_s is not None else task_like["required_duration_s"]
    )
    intervals: list[AccessInterval] = []
    for satellite_def in satellites:
        satellite_id = satellite_def["satellite_id"]
        if compatible_satellite_ids is not None and satellite_id not in compatible_satellite_ids:
            continue
        mask, off_nadir_deg = access_mask_for_satellite(
            task_like,
            satellite_def,
            orbit_grid.positions_ecef_m[satellite_id],
        )
        run_start: int | None = None
        for idx, is_access in enumerate(mask):
            if is_access and run_start is None:
                run_start = idx
                continue
            if is_access:
                continue
            if run_start is not None:
                run_end = idx - 1
                interval_duration_s = (run_end - run_start) * orbit_grid.step_s
                if interval_duration_s >= required_duration_s:
                    start_time = orbit_grid.sample_times[run_start]
                    end_time = orbit_grid.sample_times[run_end]
                    intervals.append(
                        AccessInterval(
                            satellite_id=satellite_id,
                            start_index=run_start,
                            end_index=run_end,
                            start_time=start_time,
                            end_time=end_time,
                            duration_s=interval_duration_s,
                            midpoint_time=start_time
                            + timedelta(seconds=interval_duration_s / 2.0),
                            min_off_nadir_deg=float(np.min(off_nadir_deg[run_start : run_end + 1])),
                            max_off_nadir_deg=float(np.max(off_nadir_deg[run_start : run_end + 1])),
                        )
                    )
                run_start = None
        if run_start is not None:
            run_end = mask.size - 1
            interval_duration_s = (run_end - run_start) * orbit_grid.step_s
            if interval_duration_s >= required_duration_s:
                start_time = orbit_grid.sample_times[run_start]
                end_time = orbit_grid.sample_times[run_end]
                intervals.append(
                    AccessInterval(
                        satellite_id=satellite_id,
                        start_index=run_start,
                        end_index=run_end,
                        start_time=start_time,
                        end_time=end_time,
                        duration_s=interval_duration_s,
                        midpoint_time=start_time + timedelta(seconds=interval_duration_s / 2.0),
                        min_off_nadir_deg=float(np.min(off_nadir_deg[run_start : run_end + 1])),
                        max_off_nadir_deg=float(np.max(off_nadir_deg[run_start : run_end + 1])),
                    )
                )
    intervals.sort(
        key=lambda interval: (
            interval.start_time,
            interval.end_time,
            interval.satellite_id,
        )
    )
    return intervals
