"""Solver-local schedule validation and conservative repair."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
import math

import brahe
import numpy as np

from .binary_scheduler import BinaryScheduleResult, evaluate_schedule
from .case_io import RevisitCase, SolverConfig, iso_z
from .observation_windows import (
    ObservationWindow,
    _angle_between_deg,
    window_geometry_ok,
)
from .propagation import datetime_to_epoch, ensure_brahe_ready, force_model_config
from .slot_library import OrbitSlot


@dataclass(frozen=True)
class LocalValidationIssue:
    issue_type: str
    window_id: str
    reason: str
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return {
            "issue_type": self.issue_type,
            "window_id": self.window_id,
            "reason": self.reason,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class LocalValidationResult:
    original_window_count: int
    repaired_windows: tuple[ObservationWindow, ...]
    dropped_window_ids: tuple[str, ...]
    issues: tuple[LocalValidationIssue, ...]
    repair_enabled: bool
    estimated_metrics: dict[str, object]

    def to_summary(self) -> dict[str, object]:
        return {
            "original_window_count": self.original_window_count,
            "repaired_window_count": len(self.repaired_windows),
            "dropped_window_ids": list(self.dropped_window_ids),
            "issues": [issue.to_dict() for issue in self.issues],
            "repair_enabled": self.repair_enabled,
            "estimated_metrics": self.estimated_metrics,
        }


def _window_profit(window: ObservationWindow) -> tuple[float, float, str]:
    return (
        window.estimated_max_gap_reduction_hours,
        window.estimated_mean_gap_reduction_hours,
        window.window_id,
    )


def _slew_time_sec(angle_deg: float, max_velocity: float, max_accel: float) -> float:
    angle_deg = max(0.0, angle_deg)
    if angle_deg <= 1.0e-9:
        return 0.0
    if max_velocity <= 0.0 or max_accel <= 0.0:
        return math.inf
    ramp_time = max_velocity / max_accel
    triangular_threshold = (max_velocity * max_velocity) / max_accel
    if angle_deg <= triangular_threshold:
        return 2.0 * math.sqrt(angle_deg / max_accel)
    return (2.0 * ramp_time) + ((angle_deg - triangular_threshold) / max_velocity)


def _target_vector_eci(
    target_ecef_m: tuple[float, float, float],
    propagator: brahe.NumericalOrbitPropagator,
    instant,
) -> np.ndarray:
    epoch = datetime_to_epoch(instant)
    satellite_state = np.asarray(propagator.state_eci(epoch), dtype=float)
    target_eci = np.asarray(
        brahe.position_ecef_to_eci(epoch, np.asarray(target_ecef_m, dtype=float)),
        dtype=float,
    )
    return target_eci - satellite_state[:3]


def _is_sunlit(position_eci_m: np.ndarray, epoch: brahe.Epoch) -> bool:
    sun_position = np.asarray(brahe.sun_position(epoch), dtype=float)
    sun_hat = sun_position / np.linalg.norm(sun_position)
    projection = float(np.dot(position_eci_m, sun_hat))
    perpendicular = np.linalg.norm(position_eci_m - (projection * sun_hat))
    return not (projection < 0.0 and perpendicular < brahe.R_EARTH)


def _overlap(left: ObservationWindow, right: ObservationWindow) -> bool:
    return left.start < right.end and right.start < left.end


def _propagators_by_satellite(
    case: RevisitCase,
    slots: tuple[OrbitSlot, ...],
    windows: tuple[ObservationWindow, ...],
) -> dict[str, brahe.NumericalOrbitPropagator]:
    ensure_brahe_ready()
    start_epoch = datetime_to_epoch(case.horizon_start)
    end_epoch = datetime_to_epoch(case.horizon_end)
    config = force_model_config()
    propagators: dict[str, brahe.NumericalOrbitPropagator] = {}
    for window in windows:
        if window.satellite_id in propagators:
            continue
        slot = slots[window.slot_index]
        propagator = brahe.NumericalOrbitPropagator.from_eci(
            start_epoch,
            np.asarray(slot.state_eci_m_mps, dtype=float),
            force_config=config,
        )
        propagator.propagate_to(end_epoch)
        propagators[window.satellite_id] = propagator
    return propagators


def _find_issues(
    case: RevisitCase,
    config: SolverConfig,
    slots: tuple[OrbitSlot, ...],
    windows: tuple[ObservationWindow, ...],
) -> tuple[LocalValidationIssue, ...]:
    issues: list[LocalValidationIssue] = []
    target_by_id = {target.target_id: target for target in case.targets}
    propagators = _propagators_by_satellite(case, slots, windows)

    for window in windows:
        if window.target_id not in target_by_id:
            issues.append(
                LocalValidationIssue(
                    "unknown_target",
                    window.window_id,
                    f"unknown target_id {window.target_id}",
                )
            )
            continue
        if window.start < case.horizon_start or window.end > case.horizon_end:
            issues.append(
                LocalValidationIssue(
                    "horizon",
                    window.window_id,
                    f"{iso_z(window.start)}-{iso_z(window.end)} outside horizon",
                )
            )
        target = target_by_id[window.target_id]
        if window.duration_sec + 1.0e-9 < target.min_duration_sec:
            issues.append(
                LocalValidationIssue(
                    "duration",
                    window.window_id,
                    f"{window.duration_sec:.3f}s below {target.min_duration_sec:.3f}s",
                )
            )
        propagator = propagators.get(window.satellite_id)
        if propagator is None:
            issues.append(
                LocalValidationIssue(
                    "unknown_satellite",
                    window.window_id,
                    f"unknown satellite_id {window.satellite_id}",
                )
            )
            continue
        if not window_geometry_ok(
            case,
            target,
            propagator,
            window.start,
            window.end,
            config.local_validation_geometry_sample_step_sec,
        ):
            issues.append(
                LocalValidationIssue(
                    "geometry",
                    window.window_id,
                    "window fails local sampled geometry check",
                )
            )

    by_satellite: defaultdict[str, list[ObservationWindow]] = defaultdict(list)
    for window in windows:
        by_satellite[window.satellite_id].append(window)
    attitude = case.satellite_model.attitude_model
    for satellite_id, satellite_windows in by_satellite.items():
        ordered = sorted(satellite_windows, key=lambda item: (item.start, item.window_id))
        propagator = propagators.get(satellite_id)
        if propagator is None:
            continue
        for previous, current in zip(ordered, ordered[1:]):
            if _overlap(previous, current):
                lower_profit = min((previous, current), key=_window_profit)
                issues.append(
                    LocalValidationIssue(
                        "overlap",
                        lower_profit.window_id,
                        f"{previous.window_id} overlaps {current.window_id}",
                    )
                )
                continue
            previous_target = target_by_id.get(previous.target_id)
            current_target = target_by_id.get(current.target_id)
            if previous_target is None or current_target is None:
                continue
            previous_vector = _target_vector_eci(
                previous_target.ecef_position_m, propagator, previous.midpoint
            )
            current_vector = _target_vector_eci(
                current_target.ecef_position_m, propagator, current.midpoint
            )
            angle = _angle_between_deg(previous_vector, current_vector)
            required_gap = _slew_time_sec(
                angle,
                attitude.max_slew_velocity_deg_per_sec,
                attitude.max_slew_acceleration_deg_per_sec2,
            ) + attitude.settling_time_sec
            actual_gap = (current.start - previous.end).total_seconds()
            if actual_gap + 1.0e-9 < required_gap:
                lower_profit = min((previous, current), key=_window_profit)
                issues.append(
                    LocalValidationIssue(
                        "slew",
                        lower_profit.window_id,
                        (
                            f"{previous.window_id}->{current.window_id} has "
                            f"{actual_gap:.3f}s gap but needs {required_gap:.3f}s"
                        ),
                    )
                )

    resource = case.satellite_model.resource_model
    sensor = case.satellite_model.sensor
    for satellite_id, satellite_windows in by_satellite.items():
        propagator = propagators.get(satellite_id)
        if propagator is None:
            continue
        battery_wh = resource.initial_battery_wh
        current = case.horizon_start
        for window in sorted(satellite_windows, key=lambda item: (item.start, item.window_id)):
            idle_hours = max(0.0, (window.start - current).total_seconds()) / 3600.0
            if idle_hours:
                epoch = datetime_to_epoch(current + ((window.start - current) / 2))
                state = np.asarray(propagator.state_eci(epoch), dtype=float)
                charge = resource.sunlight_charge_rate_w if _is_sunlit(state[:3], epoch) else 0.0
                battery_wh += (charge - resource.idle_discharge_rate_w) * idle_hours
                battery_wh = min(resource.battery_capacity_wh, battery_wh)
            obs_hours = window.duration_sec / 3600.0
            battery_wh -= (
                resource.idle_discharge_rate_w + sensor.obs_discharge_rate_w
            ) * obs_hours
            current = max(current, window.end)
            if battery_wh < config.local_battery_margin_wh:
                issues.append(
                    LocalValidationIssue(
                        "battery",
                        window.window_id,
                        f"estimated battery {battery_wh:.3f} Wh below margin",
                    )
                )
                break

    return tuple(issues)


def validate_and_repair_schedule(
    case: RevisitCase,
    config: SolverConfig,
    slots: tuple[OrbitSlot, ...],
    schedule_result: BinaryScheduleResult,
) -> LocalValidationResult:
    windows = tuple(schedule_result.selected_windows)
    dropped: list[str] = []
    all_issues: list[LocalValidationIssue] = []
    if not config.local_repair_enabled:
        issues = _find_issues(case, config, slots, windows)
        evaluation = evaluate_schedule(case, windows, tuple(range(len(windows))))
        return LocalValidationResult(
            original_window_count=len(windows),
            repaired_windows=windows,
            dropped_window_ids=(),
            issues=issues,
            repair_enabled=False,
            estimated_metrics=evaluation.to_dict(),
        )

    remaining = list(windows)
    while True:
        issues = _find_issues(case, config, slots, tuple(remaining))
        if not issues:
            break
        all_issues.extend(issues)
        issue_window_ids = {issue.window_id for issue in issues}
        candidates = [window for window in remaining if window.window_id in issue_window_ids]
        if not candidates:
            break
        drop = min(candidates, key=_window_profit)
        dropped.append(drop.window_id)
        remaining = [window for window in remaining if window.window_id != drop.window_id]

    repaired_windows = tuple(
        sorted(remaining, key=lambda item: (item.start, item.satellite_id, item.target_id))
    )
    evaluation = evaluate_schedule(case, repaired_windows, tuple(range(len(repaired_windows))))
    return LocalValidationResult(
        original_window_count=len(windows),
        repaired_windows=repaired_windows,
        dropped_window_ids=tuple(dropped),
        issues=tuple(all_issues),
        repair_enabled=True,
        estimated_metrics=evaluation.to_dict(),
    )
