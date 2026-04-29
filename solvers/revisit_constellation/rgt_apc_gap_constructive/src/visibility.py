"""Visibility access-profile and opportunity construction."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
import math
import os

import brahe
import numpy as np

from .case_io import RevisitCase, Target
from .orbit_library import OrbitCandidate
from .propagation import (
    CandidateStateGrid,
    PropagationCache,
    datetime_to_epoch,
    ensure_brahe_ready,
)
from .time_grid import horizon_sample_times, iso_z


NUMERICAL_EPS = 1.0e-9


@dataclass(frozen=True, slots=True)
class VisibilityConfig:
    sample_step_sec: float = 120.0
    max_windows: int | None = None
    keep_samples_per_window: int = 6
    worker_count: int | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "VisibilityConfig":
        raw = payload.get("visibility", payload)
        if not isinstance(raw, dict):
            raise ValueError("visibility config must be a mapping/object")
        max_windows = raw.get("max_windows")
        worker_count = raw.get("worker_count")
        return cls(
            sample_step_sec=float(raw.get("sample_step_sec", 120.0)),
            max_windows=(None if max_windows is None else int(max_windows)),
            keep_samples_per_window=int(raw.get("keep_samples_per_window", 6)),
            worker_count=(None if worker_count is None else int(worker_count)),
        )

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "sample_step_sec": self.sample_step_sec,
            "max_windows": self.max_windows,
            "keep_samples_per_window": self.keep_samples_per_window,
            "worker_count": self.worker_count,
        }


@dataclass(frozen=True, slots=True)
class VisibilitySample:
    offset_sec: float
    elevation_deg: float
    slant_range_m: float
    off_nadir_deg: float
    visible: bool

    def as_dict(self) -> dict[str, float | bool]:
        return {
            "offset_sec": self.offset_sec,
            "elevation_deg": self.elevation_deg,
            "slant_range_m": self.slant_range_m,
            "off_nadir_deg": self.off_nadir_deg,
            "visible": self.visible,
        }


@dataclass(frozen=True, slots=True)
class VisibilityWindow:
    window_id: str
    candidate_id: str
    target_id: str
    start: datetime
    end: datetime
    midpoint: datetime
    duration_sec: float
    max_elevation_deg: float
    min_slant_range_m: float
    min_off_nadir_deg: float
    sample_count: int
    samples: tuple[VisibilitySample, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "candidate_id": self.candidate_id,
            "target_id": self.target_id,
            "start": iso_z(self.start),
            "end": iso_z(self.end),
            "midpoint": iso_z(self.midpoint),
            "duration_sec": self.duration_sec,
            "max_elevation_deg": self.max_elevation_deg,
            "min_slant_range_m": self.min_slant_range_m,
            "min_off_nadir_deg": self.min_off_nadir_deg,
            "sample_count": self.sample_count,
            "samples": [sample.as_dict() for sample in self.samples],
        }


@dataclass(frozen=True, slots=True)
class VisibilityLibrary:
    windows: list[VisibilityWindow]
    sample_count: int
    pair_count: int
    caps: dict[str, Any]

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "visibility_window_count": len(self.windows),
            "visibility_sample_count": self.sample_count,
            "candidate_target_pair_count": self.pair_count,
            "caps": self.caps,
        }


def angle_between_deg(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    norm_a = float(np.linalg.norm(vector_a))
    norm_b = float(np.linalg.norm(vector_b))
    if norm_a <= NUMERICAL_EPS or norm_b <= NUMERICAL_EPS:
        return 0.0
    cosine = float(np.dot(vector_a, vector_b) / (norm_a * norm_b))
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _geometry_sample_from_states(
    *,
    case: RevisitCase,
    target: Target,
    state_eci: np.ndarray,
    state_ecef: np.ndarray,
    instant: datetime,
) -> VisibilitySample:
    target_ecef = np.asarray(target.ecef_position_m, dtype=float)
    relative_enz = np.asarray(
        brahe.relative_position_ecef_to_enz(
            target_ecef,
            state_ecef[:3],
            brahe.EllipsoidalConversionType.GEODETIC,
        ),
        dtype=float,
    )
    azimuth_elevation_range = np.asarray(
        brahe.position_enz_to_azel(relative_enz, brahe.AngleFormat.DEGREES),
        dtype=float,
    )
    elevation_deg = float(azimuth_elevation_range[1])
    slant_range_m = float(azimuth_elevation_range[2])
    epoch = datetime_to_epoch(instant)
    target_eci = np.asarray(brahe.position_ecef_to_eci(epoch, target_ecef), dtype=float)
    off_nadir_deg = angle_between_deg(-state_eci[:3], target_eci - state_eci[:3])
    max_allowed_range_m = min(target.max_slant_range_m, case.satellite_model.sensor.max_range_m)
    visible = (
        elevation_deg + NUMERICAL_EPS >= target.min_elevation_deg
        and slant_range_m <= max_allowed_range_m + NUMERICAL_EPS
        and off_nadir_deg <= case.satellite_model.sensor.max_off_nadir_angle_deg + NUMERICAL_EPS
    )
    return VisibilitySample(
        offset_sec=(instant - case.horizon_start).total_seconds(),
        elevation_deg=elevation_deg,
        slant_range_m=slant_range_m,
        off_nadir_deg=off_nadir_deg,
        visible=visible,
    )


def _geometry_sample(
    *,
    case: RevisitCase,
    target: Target,
    propagation: PropagationCache,
    candidate_id: str,
    instant: datetime,
) -> VisibilitySample:
    state_eci = propagation.state_eci(candidate_id, instant)
    state_ecef = propagation.state_ecef(candidate_id, instant)
    return _geometry_sample_from_states(
        case=case,
        target=target,
        state_eci=state_eci,
        state_ecef=state_ecef,
        instant=instant,
    )


def _thin_samples(samples: list[VisibilitySample], keep: int) -> tuple[VisibilitySample, ...]:
    if keep <= 0 or len(samples) <= keep:
        return tuple(samples)
    if keep == 1:
        return (samples[len(samples) // 2],)
    indexes = {
        round(index * (len(samples) - 1) / (keep - 1))
        for index in range(keep)
    }
    return tuple(samples[index] for index in sorted(indexes))


def group_visible_samples(
    *,
    candidate_id: str,
    target_id: str,
    horizon_start: datetime,
    horizon_end: datetime,
    sample_step_sec: float,
    min_duration_sec: float,
    samples: list[VisibilitySample],
    keep_samples_per_window: int = 6,
) -> list[VisibilityWindow]:
    windows: list[VisibilityWindow] = []
    current: list[VisibilitySample] = []

    def flush() -> None:
        if not current:
            return
        start = horizon_start + timedelta(seconds=current[0].offset_sec)
        end = min(
            horizon_end,
            horizon_start + timedelta(seconds=current[-1].offset_sec + sample_step_sec),
        )
        duration_sec = (end - start).total_seconds()
        if duration_sec + NUMERICAL_EPS < min_duration_sec:
            return
        midpoint = start + ((end - start) / 2)
        window_index = len(windows)
        windows.append(
            VisibilityWindow(
                window_id=f"{candidate_id}__{target_id}__win{window_index:04d}",
                candidate_id=candidate_id,
                target_id=target_id,
                start=start,
                end=end,
                midpoint=midpoint,
                duration_sec=duration_sec,
                max_elevation_deg=max(sample.elevation_deg for sample in current),
                min_slant_range_m=min(sample.slant_range_m for sample in current),
                min_off_nadir_deg=min(sample.off_nadir_deg for sample in current),
                sample_count=len(current),
                samples=_thin_samples(current, keep_samples_per_window),
            )
        )

    for sample in samples:
        if sample.visible:
            current.append(sample)
            continue
        flush()
        current = []
    flush()
    return windows


def _resolved_worker_count(config: VisibilityConfig, candidate_count: int) -> int:
    if candidate_count <= 0:
        return 0
    if config.worker_count is not None:
        return max(1, min(int(config.worker_count), candidate_count))
    return max(1, min(8, os.cpu_count() or 1, candidate_count))


def _candidate_visibility_windows(
    args: tuple[
        RevisitCase,
        CandidateStateGrid,
        tuple[Target, ...],
        float,
        int,
    ],
) -> list[VisibilityWindow]:
    case, state_grid, targets, sample_step_sec, keep_samples_per_window = args
    ensure_brahe_ready()
    windows: list[VisibilityWindow] = []
    for target in targets:
        samples = [
            _geometry_sample_from_states(
                case=case,
                target=target,
                state_eci=state_grid.eci_states[index],
                state_ecef=state_grid.ecef_states[index],
                instant=instant,
            )
            for index, instant in enumerate(state_grid.sample_times)
        ]
        windows.extend(
            group_visible_samples(
                candidate_id=state_grid.candidate_id,
                target_id=target.target_id,
                horizon_start=case.horizon_start,
                horizon_end=case.horizon_end,
                sample_step_sec=sample_step_sec,
                min_duration_sec=target.min_duration_sec,
                samples=samples,
                keep_samples_per_window=keep_samples_per_window,
            )
        )
    return windows


def _sort_windows(windows: list[VisibilityWindow]) -> list[VisibilityWindow]:
    return sorted(
        windows,
        key=lambda item: (item.candidate_id, item.target_id, item.start, item.window_id),
    )


def _visibility_group_diagnostics(
    candidates: list[OrbitCandidate],
    windows: list[VisibilityWindow],
) -> dict[str, Any]:
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    window_counts_by_candidate_target: dict[tuple[str, str], int] = {}
    for window in windows:
        key = (window.candidate_id, window.target_id)
        window_counts_by_candidate_target[key] = (
            window_counts_by_candidate_target.get(key, 0) + 1
        )

    by_shell: dict[str, dict[str, Any]] = {}
    by_shell_raan: dict[tuple[str, int], dict[str, Any]] = {}
    by_shell_phase: dict[tuple[str, int], dict[str, Any]] = {}
    candidate_target_rows: list[dict[str, Any]] = []
    for (candidate_id, target_id), window_count in sorted(
        window_counts_by_candidate_target.items()
    ):
        candidate = candidate_by_id.get(candidate_id)
        if candidate is None:
            raise ValueError(
                "visibility window references unknown candidate_id "
                f"{candidate_id!r} for target_id {target_id!r} "
                f"with {window_count} window(s)"
            )
        shell_id = candidate.rgt_shell_id or candidate.source
        shell_row = by_shell.setdefault(
            shell_id,
            {
                "shell_id": shell_id,
                "candidate_ids": set(),
                "target_ids": set(),
                "visibility_window_count": 0,
            },
        )
        shell_row["candidate_ids"].add(candidate_id)
        shell_row["target_ids"].add(target_id)
        shell_row["visibility_window_count"] += window_count

        raan_key = (shell_id, candidate.raan_slot_index)
        raan_row = by_shell_raan.setdefault(
            raan_key,
            {
                "shell_id": shell_id,
                "raan_slot_index": candidate.raan_slot_index,
                "raan_deg": candidate.raan_deg,
                "candidate_ids": set(),
                "target_ids": set(),
                "visibility_window_count": 0,
            },
        )
        raan_row["candidate_ids"].add(candidate_id)
        raan_row["target_ids"].add(target_id)
        raan_row["visibility_window_count"] += window_count

        phase_key = (shell_id, candidate.phase_slot_index)
        phase_row = by_shell_phase.setdefault(
            phase_key,
            {
                "shell_id": shell_id,
                "phase_slot_index": candidate.phase_slot_index,
                "mean_anomaly_deg": candidate.mean_anomaly_deg,
                "candidate_ids": set(),
                "target_ids": set(),
                "visibility_window_count": 0,
            },
        )
        phase_row["candidate_ids"].add(candidate_id)
        phase_row["target_ids"].add(target_id)
        phase_row["visibility_window_count"] += window_count

        candidate_target_rows.append(
            {
                "candidate_id": candidate_id,
                "target_id": target_id,
                "shell_id": shell_id,
                "raan_slot_index": candidate.raan_slot_index,
                "raan_deg": candidate.raan_deg,
                "phase_slot_index": candidate.phase_slot_index,
                "mean_anomaly_deg": candidate.mean_anomaly_deg,
                "visibility_window_count": window_count,
                "analytical_shell_closure_m": candidate.rgt_analytical_closure_m,
            }
        )

    def normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for row in rows:
            next_row = dict(row)
            candidate_ids = next_row.pop("candidate_ids", set())
            target_ids = next_row.pop("target_ids", set())
            next_row["candidate_count"] = len(candidate_ids)
            next_row["target_count"] = len(target_ids)
            next_row["candidate_ids"] = sorted(candidate_ids)[:10]
            next_row["target_ids"] = sorted(target_ids)[:10]
            normalized.append(next_row)
        return normalized

    return {
        "by_shell": normalize_rows(
            sorted(by_shell.values(), key=lambda row: row["shell_id"])
        ),
        "by_shell_raan": normalize_rows(
            sorted(
                by_shell_raan.values(),
                key=lambda row: (row["shell_id"], row["raan_slot_index"]),
            )
        ),
        "by_shell_phase": normalize_rows(
            sorted(
                by_shell_phase.values(),
                key=lambda row: (row["shell_id"], row["phase_slot_index"]),
            )
        ),
        "candidate_target_groups": candidate_target_rows,
    }


def build_visibility_library(
    case: RevisitCase,
    candidates: list[OrbitCandidate],
    config: VisibilityConfig,
) -> VisibilityLibrary:
    if config.sample_step_sec <= 0.0:
        raise ValueError("visibility.sample_step_sec must be > 0")
    sample_times = horizon_sample_times(
        case.horizon_start,
        case.horizon_end,
        config.sample_step_sec,
    )
    propagation = PropagationCache(candidates, case.horizon_start, case.horizon_end)
    state_grids = propagation.state_grids(sample_times)
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    targets = tuple(case.targets.values())
    worker_count = _resolved_worker_count(config, len(candidates))
    worker_args = [
        (
            case,
            state_grids[candidate_id],
            targets,
            config.sample_step_sec,
            config.keep_samples_per_window,
        )
        for candidate_id in candidate_ids
    ]
    windows: list[VisibilityWindow] = []
    if worker_count > 1 and worker_args:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            for candidate_windows in executor.map(_candidate_visibility_windows, worker_args):
                windows.extend(candidate_windows)
    else:
        for item in worker_args:
            windows.extend(_candidate_visibility_windows(item))
    windows = _sort_windows(windows)
    uncapped_window_count = len(windows)
    max_windows = config.max_windows
    if max_windows is not None and len(windows) >= max_windows:
        windows = windows[:max_windows]
    return VisibilityLibrary(
        windows=windows,
        sample_count=len(candidates) * len(case.targets) * len(sample_times),
        pair_count=len(candidates) * len(case.targets),
        caps={
            **config.as_status_dict(),
            "window_count_capped": (
                max_windows is not None and uncapped_window_count >= max_windows
            ),
            "uncapped_visibility_window_count": uncapped_window_count,
            "worker_count_configured": config.worker_count,
            "worker_count_used": worker_count,
            "parallel_strategy": "candidate_state_grid",
            "coverage_groups": _visibility_group_diagnostics(candidates, windows),
            "state_cache": {
                "cached_candidate_count": len(state_grids),
                "sample_time_count": len(sample_times),
                "state_frames": ["eci", "ecef"],
            },
        },
    )
