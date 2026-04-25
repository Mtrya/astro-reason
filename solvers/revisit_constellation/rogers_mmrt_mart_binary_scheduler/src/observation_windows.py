"""Feasible observation-window enumeration for selected design slots."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import math

import brahe
import numpy as np

from .case_io import RevisitCase, SolverConfig, Target, iso_z
from .design_models import DesignResult
from .propagation import datetime_to_epoch, ensure_brahe_ready, force_model_config
from .slot_library import OrbitSlot


NUMERICAL_EPS = 1.0e-9


@dataclass(frozen=True)
class ObservationWindow:
    window_id: str
    satellite_id: str
    slot_id: str
    slot_index: int
    target_id: str
    target_index: int
    start: datetime
    end: datetime
    midpoint: datetime
    duration_sec: float
    estimated_max_gap_reduction_hours: float
    estimated_mean_gap_reduction_hours: float
    conflict_ids: tuple[str, ...] = ()

    def to_record(self) -> dict[str, object]:
        return {
            "window_id": self.window_id,
            "satellite_id": self.satellite_id,
            "slot_id": self.slot_id,
            "slot_index": self.slot_index,
            "target_id": self.target_id,
            "target_index": self.target_index,
            "start": iso_z(self.start),
            "end": iso_z(self.end),
            "midpoint": iso_z(self.midpoint),
            "duration_sec": self.duration_sec,
            "estimated_max_gap_reduction_hours": self.estimated_max_gap_reduction_hours,
            "estimated_mean_gap_reduction_hours": self.estimated_mean_gap_reduction_hours,
            "conflict_ids": list(self.conflict_ids),
        }


@dataclass(frozen=True)
class WindowEnumerationResult:
    windows: tuple[ObservationWindow, ...]
    candidate_count_by_satellite: dict[str, int]
    candidate_count_by_target: dict[str, int]
    candidate_count_by_satellite_target: dict[str, int]
    zero_window_targets: tuple[str, ...]
    zero_window_satellites: tuple[str, ...]
    conflict_edge_count: int
    capped: bool
    caps: dict[str, int | float | bool]
    execution: dict[str, object] = field(default_factory=dict)

    def to_summary(self) -> dict[str, object]:
        return {
            "window_count": len(self.windows),
            "candidate_count_by_satellite": self.candidate_count_by_satellite,
            "candidate_count_by_target": self.candidate_count_by_target,
            "candidate_count_by_satellite_target": self.candidate_count_by_satellite_target,
            "zero_window_targets": list(self.zero_window_targets),
            "zero_window_satellites": list(self.zero_window_satellites),
            "conflict_edge_count": self.conflict_edge_count,
            "capped": self.capped,
            "caps": self.caps,
            "execution": self.execution,
        }


def action_sample_times(start: datetime, end: datetime, step_sec: float) -> tuple[datetime, ...]:
    if end <= start:
        return (start,)
    samples = [start]
    current = start
    delta = timedelta(seconds=step_sec)
    while current + delta < end:
        current += delta
        samples.append(current)
    return tuple(samples)


def _angle_between_deg(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    norm_a = np.linalg.norm(vector_a)
    norm_b = np.linalg.norm(vector_b)
    if norm_a < NUMERICAL_EPS or norm_b < NUMERICAL_EPS:
        return 0.0
    cosine = float(np.dot(vector_a, vector_b) / (norm_a * norm_b))
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def observation_geometry_ok(
    case: RevisitCase,
    target: Target,
    state_eci_m_mps: np.ndarray,
    state_ecef_m_mps: np.ndarray,
    epoch: brahe.Epoch,
) -> bool:
    sensor = case.satellite_model.sensor
    target_ecef_m = np.asarray(target.ecef_position_m, dtype=float)
    relative_enz = np.asarray(
        brahe.relative_position_ecef_to_enz(
            target_ecef_m,
            state_ecef_m_mps[:3],
            brahe.EllipsoidalConversionType.GEODETIC,
        ),
        dtype=float,
    )
    azelr = np.asarray(
        brahe.position_enz_to_azel(relative_enz, brahe.AngleFormat.DEGREES),
        dtype=float,
    )
    elevation_deg = float(azelr[1])
    slant_range_m = float(azelr[2])
    if elevation_deg < target.min_elevation_deg - NUMERICAL_EPS:
        return False
    if slant_range_m > target.max_slant_range_m + NUMERICAL_EPS:
        return False
    if slant_range_m > sensor.max_range_m + NUMERICAL_EPS:
        return False

    target_eci_m = np.asarray(brahe.position_ecef_to_eci(epoch, target_ecef_m), dtype=float)
    line_of_sight = target_eci_m - state_eci_m_mps[:3]
    nadir = -state_eci_m_mps[:3]
    off_nadir_deg = _angle_between_deg(nadir, line_of_sight)
    return off_nadir_deg <= sensor.max_off_nadir_angle_deg + NUMERICAL_EPS


def window_geometry_ok(
    case: RevisitCase,
    target: Target,
    propagator: brahe.NumericalOrbitPropagator,
    start: datetime,
    end: datetime,
    sample_step_sec: float,
) -> bool:
    for sample in action_sample_times(start, end, sample_step_sec):
        epoch = datetime_to_epoch(sample)
        state_eci = np.asarray(propagator.state_eci(epoch), dtype=float)
        state_ecef = np.asarray(propagator.state_ecef(epoch), dtype=float)
        if not observation_geometry_ok(case, target, state_eci, state_ecef, epoch):
            return False
    return True


def _neutral_gap_reduction_hours(
    case: RevisitCase, midpoint: datetime
) -> tuple[float, float]:
    horizon_hours = case.horizon_duration_sec / 3600.0
    left_hours = (midpoint - case.horizon_start).total_seconds() / 3600.0
    right_hours = (case.horizon_end - midpoint).total_seconds() / 3600.0
    max_gap_after = max(left_hours, right_hours)
    mean_gap_after = (left_hours + right_hours) / 2.0
    return (
        max(0.0, horizon_hours - max_gap_after),
        max(0.0, horizon_hours - mean_gap_after),
    )


def _candidate_start_times(
    horizon_start: datetime,
    horizon_end: datetime,
    duration_sec: float,
    stride_sec: float,
) -> tuple[datetime, ...]:
    if duration_sec <= 0.0:
        return ()
    latest_start = horizon_end - timedelta(seconds=duration_sec)
    if latest_start < horizon_start:
        return ()
    starts: list[datetime] = []
    current = horizon_start
    stride = timedelta(seconds=stride_sec)
    while current <= latest_start:
        starts.append(current)
        current += stride
    return tuple(starts)


def _window_id(satellite_id: str, target_id: str, start: datetime) -> str:
    compact_time = iso_z(start).replace("-", "").replace(":", "").replace("Z", "Z")
    return f"win_{satellite_id}_{target_id}_{compact_time}"


def _overlap(left: ObservationWindow, right: ObservationWindow) -> bool:
    return left.start < right.end and right.start < left.end


def _with_conflicts(windows: tuple[ObservationWindow, ...]) -> tuple[tuple[ObservationWindow, ...], int]:
    conflict_sets: list[set[str]] = [set() for _ in windows]
    edge_count = 0
    for left_index, left in enumerate(windows):
        for right_index in range(left_index + 1, len(windows)):
            right = windows[right_index]
            if not _overlap(left, right):
                continue
            same_satellite = left.satellite_id == right.satellite_id
            duplicate_target_time = left.target_id == right.target_id
            if same_satellite or duplicate_target_time:
                conflict_sets[left_index].add(right.window_id)
                conflict_sets[right_index].add(left.window_id)
                edge_count += 1
    return (
        tuple(
            replace(window, conflict_ids=tuple(sorted(conflict_sets[index])))
            for index, window in enumerate(windows)
        ),
        edge_count,
    )


def enumerate_observation_windows(
    case: RevisitCase,
    config: SolverConfig,
    slots: tuple[OrbitSlot, ...],
    design_result: DesignResult,
) -> WindowEnumerationResult:
    worker_count = config.geometry_worker_count
    if worker_count <= 0:
        raise ValueError("geometry_worker_count must be positive")
    tasks = tuple(
        (case, config, slots[slot_index], slot_index, satellite_number)
        for satellite_number, slot_index in enumerate(
            design_result.selected_slot_indices, start=1
        )
    )
    task_count = len(tasks)
    actual_workers = min(worker_count, task_count) if task_count else 1
    parallel = worker_count > 1 and task_count > 1
    if parallel:
        with ProcessPoolExecutor(max_workers=actual_workers) as executor:
            pair_results = tuple(executor.map(_windows_for_satellite, tasks))
    else:
        pair_results = tuple(_windows_for_satellite(task) for task in tasks)

    windows = [
        window
        for pair_windows, _pair_capped in pair_results
        for window in pair_windows
    ]
    windows.sort(key=lambda item: (item.start, item.satellite_id, item.target_id, item.window_id))
    pair_capped = any(capped for _pair_windows, capped in pair_results)
    global_capped = len(windows) > config.max_observation_windows
    if global_capped:
        windows = windows[: config.max_observation_windows]
    capped = pair_capped or global_capped
    windows_with_conflicts, edge_count = _with_conflicts(tuple(windows))

    by_satellite: dict[str, int] = {
        f"sat_{number:03d}": 0
        for number in range(1, len(design_result.selected_slot_indices) + 1)
    }
    by_target: dict[str, int] = {target.target_id: 0 for target in case.targets}
    by_pair: dict[str, int] = {}
    for window in windows_with_conflicts:
        by_satellite[window.satellite_id] += 1
        by_target[window.target_id] += 1
        pair_key = f"{window.satellite_id}|{window.target_id}"
        by_pair[pair_key] = by_pair.get(pair_key, 0) + 1

    execution = {
        "mode": "parallel" if parallel else "serial",
        "configured_worker_count": worker_count,
        "actual_worker_count": actual_workers if parallel else 1,
        "task_count": task_count,
    }
    return WindowEnumerationResult(
        windows=windows_with_conflicts,
        candidate_count_by_satellite=dict(sorted(by_satellite.items())),
        candidate_count_by_target=dict(sorted(by_target.items())),
        candidate_count_by_satellite_target=dict(sorted(by_pair.items())),
        zero_window_targets=tuple(
            target_id for target_id, count in sorted(by_target.items()) if count == 0
        ),
        zero_window_satellites=tuple(
            satellite_id for satellite_id, count in sorted(by_satellite.items()) if count == 0
        ),
        conflict_edge_count=edge_count,
        capped=capped,
        caps={
            "window_stride_sec": config.window_stride_sec,
            "window_geometry_sample_step_sec": config.window_geometry_sample_step_sec,
            "max_observation_windows": config.max_observation_windows,
            "max_windows_per_satellite_target": config.max_windows_per_satellite_target,
            "write_observation_windows": config.write_observation_windows,
            "geometry_worker_count": config.geometry_worker_count,
        },
        execution=execution,
    )


def _windows_for_satellite(
    task: tuple[
        RevisitCase,
        SolverConfig,
        OrbitSlot,
        int,
        int,
    ],
) -> tuple[tuple[ObservationWindow, ...], bool]:
    case, config, slot, slot_index, satellite_number = task
    ensure_brahe_ready()
    start_epoch = datetime_to_epoch(case.horizon_start)
    end_epoch = datetime_to_epoch(case.horizon_end)
    force_config = force_model_config()
    windows: list[ObservationWindow] = []
    capped = False
    satellite_id = f"sat_{satellite_number:03d}"
    propagator = brahe.NumericalOrbitPropagator.from_eci(
        start_epoch,
        np.asarray(slot.state_eci_m_mps, dtype=float),
        force_config=force_config,
    )
    propagator.propagate_to(end_epoch)
    for target_index, target in enumerate(case.targets):
        pair_count = 0
        starts = _candidate_start_times(
            case.horizon_start,
            case.horizon_end,
            target.min_duration_sec,
            config.window_stride_sec,
        )
        for start in starts:
            if pair_count >= config.max_windows_per_satellite_target:
                capped = True
                break
            end = start + timedelta(seconds=target.min_duration_sec)
            if not window_geometry_ok(
                case,
                target,
                propagator,
                start,
                end,
                config.window_geometry_sample_step_sec,
            ):
                continue
            midpoint = start + ((end - start) / 2)
            max_reduction, mean_reduction = _neutral_gap_reduction_hours(case, midpoint)
            windows.append(
                ObservationWindow(
                    window_id=_window_id(satellite_id, target.target_id, start),
                    satellite_id=satellite_id,
                    slot_id=slot.slot_id,
                    slot_index=slot_index,
                    target_id=target.target_id,
                    target_index=target_index,
                    start=start,
                    end=end,
                    midpoint=midpoint,
                    duration_sec=target.min_duration_sec,
                    estimated_max_gap_reduction_hours=max_reduction,
                    estimated_mean_gap_reduction_hours=mean_reduction,
                )
            )
            pair_count += 1

    return tuple(sorted(windows, key=lambda item: (item.start, item.satellite_id, item.target_id, item.window_id))), capped
