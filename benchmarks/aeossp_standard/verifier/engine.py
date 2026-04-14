"""Core verification logic for the aeossp_standard benchmark."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
import math
from pathlib import Path
from typing import Any

import brahe
import numpy as np

from .io import load_case, load_solution
from .models import (
    AeosspCase,
    AeosspSolution,
    ActionFailure,
    BatteryTraceSegment,
    ManeuverWindow,
    Mission,
    NUMERICAL_EPS,
    ObservationAction,
    SolutionAnalysis,
    TaskDef,
    TaskOutcome,
    TimelineEvent,
    ValidatedAction,
    VerificationResult,
)


_BRAHE_EOP_INITIALIZED = False


class _PropagationContext:
    def __init__(self, case: AeosspCase):
        self.case = case
        step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
        self.propagators = {
            sat_id: brahe.SGPPropagator.from_tle(sat.tle_line1, sat.tle_line2, step_s)
            for sat_id, sat in case.satellites.items()
        }
        self._eci_cache: dict[tuple[str, datetime], np.ndarray] = {}
        self._ecef_cache: dict[tuple[str, datetime], np.ndarray] = {}

    def state_eci(self, satellite_id: str, instant: datetime) -> np.ndarray:
        key = (satellite_id, instant.astimezone(UTC))
        state = self._eci_cache.get(key)
        if state is None:
            epoch = _datetime_to_epoch(key[1])
            state = np.asarray(self.propagators[satellite_id].state_eci(epoch), dtype=float).reshape(6)
            self._eci_cache[key] = state
        return state

    def state_ecef(self, satellite_id: str, instant: datetime) -> np.ndarray:
        key = (satellite_id, instant.astimezone(UTC))
        state = self._ecef_cache.get(key)
        if state is None:
            epoch = _datetime_to_epoch(key[1])
            state = np.asarray(self.propagators[satellite_id].state_ecef(epoch), dtype=float).reshape(6)
            self._ecef_cache[key] = state
        return state


def _ensure_brahe_ready() -> None:
    global _BRAHE_EOP_INITIALIZED
    if _BRAHE_EOP_INITIALIZED:
        return
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    _BRAHE_EOP_INITIALIZED = True


def _datetime_to_epoch(value: datetime) -> brahe.Epoch:
    value = value.astimezone(UTC)
    second = float(value.second) + (value.microsecond / 1_000_000.0)
    return brahe.Epoch.from_datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        second,
        0.0,
        brahe.TimeSystem.UTC,
    )


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _default_metrics() -> dict[str, Any]:
    return {"CR": 0.0, "WCR": 0.0, "TAT": None, "PC": 0.0}


def _invalid_result(
    violations: list[str], diagnostics: dict[str, Any] | None = None
) -> VerificationResult:
    return VerificationResult(
        valid=False,
        metrics=_default_metrics(),
        violations=violations,
        diagnostics=diagnostics or {},
    )


def _is_aligned(seconds: float, step_s: int) -> bool:
    return abs((seconds / step_s) - round(seconds / step_s)) <= 1.0e-9


def _action_sample_times(
    start_time: datetime,
    end_time: datetime,
    *,
    step_s: int,
) -> list[datetime]:
    if end_time <= start_time:
        return [start_time]
    points = [start_time]
    current = start_time
    delta = timedelta(seconds=step_s)
    while current + delta < end_time:
        current = current + delta
        points.append(current)
    if points[-1] != end_time:
        points.append(end_time)
    return points


def _angle_between_deg(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    norm_a = float(np.linalg.norm(vector_a))
    norm_b = float(np.linalg.norm(vector_b))
    if norm_a <= NUMERICAL_EPS or norm_b <= NUMERICAL_EPS:
        return 0.0
    cosine = float(np.dot(vector_a, vector_b) / (norm_a * norm_b))
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _off_nadir_deg(satellite_position_ecef_m: np.ndarray, target_ecef_m: np.ndarray) -> float:
    return _angle_between_deg(
        -satellite_position_ecef_m,
        target_ecef_m - satellite_position_ecef_m,
    )


def _target_visible(
    satellite_position_ecef_m: np.ndarray,
    target_ecef_m: np.ndarray,
) -> bool:
    target_norm = float(np.linalg.norm(target_ecef_m))
    if target_norm <= NUMERICAL_EPS:
        return False
    target_normal = target_ecef_m / target_norm
    return float(np.dot(satellite_position_ecef_m - target_ecef_m, target_normal)) > 0.0


def _target_vector_eci(
    task: TaskDef,
    propagation: _PropagationContext,
    satellite_id: str,
    instant: datetime,
) -> np.ndarray:
    epoch = _datetime_to_epoch(instant)
    target_eci = np.asarray(
        brahe.position_ecef_to_eci(epoch, np.asarray(task.target_ecef_m, dtype=float)),
        dtype=float,
    ).reshape(3)
    sat_state_eci = propagation.state_eci(satellite_id, instant)
    return target_eci - sat_state_eci[:3]


def _is_sunlit(position_eci_m: np.ndarray, epoch: brahe.Epoch) -> bool:
    sun_position = np.asarray(brahe.sun_position(epoch), dtype=float)
    sun_hat = sun_position / np.linalg.norm(sun_position)
    projection = float(np.dot(position_eci_m, sun_hat))
    perpendicular = np.linalg.norm(position_eci_m - (projection * sun_hat))
    return not (projection < 0.0 and perpendicular < brahe.R_EARTH)


def _slew_time_s(
    delta_angle_deg: float,
    max_velocity_deg_per_s: float,
    max_acceleration_deg_per_s2: float,
) -> float:
    delta_angle_deg = max(0.0, delta_angle_deg)
    if delta_angle_deg <= NUMERICAL_EPS:
        return 0.0
    if max_velocity_deg_per_s <= 0.0 or max_acceleration_deg_per_s2 <= 0.0:
        return math.inf
    ramp_time = max_velocity_deg_per_s / max_acceleration_deg_per_s2
    triangular_threshold = (
        max_velocity_deg_per_s * max_velocity_deg_per_s / max_acceleration_deg_per_s2
    )
    if delta_angle_deg <= triangular_threshold:
        return 2.0 * math.sqrt(delta_angle_deg / max_acceleration_deg_per_s2)
    cruise_angle = delta_angle_deg - triangular_threshold
    return (2.0 * ramp_time) + (cruise_angle / max_velocity_deg_per_s)


def _make_failure(
    *,
    action_index: int,
    satellite_id: str,
    task_id: str,
    reason: str,
    stage: str,
    time: datetime | None = None,
) -> ActionFailure:
    return ActionFailure(
        action_index=action_index,
        satellite_id=satellite_id,
        task_id=task_id,
        reason=reason,
        stage=stage,
        time=time.astimezone(UTC) if time is not None else None,
    )


def _validate_action_structure(
    case: AeosspCase,
    solution: AeosspSolution,
) -> tuple[list[ValidatedAction], list[ActionFailure], list[str]]:
    validated: list[ValidatedAction] = []
    failures: list[ActionFailure] = []
    violations: list[str] = []
    for index, action in enumerate(solution.actions):
        prefix = f"actions[{index}]"
        if action.satellite_id not in case.satellites:
            failures.append(
                _make_failure(
                    action_index=index,
                    satellite_id=action.satellite_id,
                    task_id=action.task_id,
                    reason="unknown satellite_id",
                    stage="structure",
                    time=action.start_time,
                )
            )
            violations.append(f"{prefix}: unknown satellite_id {action.satellite_id!r}")
            continue
        if action.task_id not in case.tasks:
            failures.append(
                _make_failure(
                    action_index=index,
                    satellite_id=action.satellite_id,
                    task_id=action.task_id,
                    reason="unknown task_id",
                    stage="structure",
                    time=action.start_time,
                )
            )
            violations.append(f"{prefix}: unknown task_id {action.task_id!r}")
            continue
        task = case.tasks[action.task_id]
        if action.end_time <= action.start_time:
            reason = "end_time must be after start_time"
            failures.append(
                _make_failure(
                    action_index=index,
                    satellite_id=action.satellite_id,
                    task_id=action.task_id,
                    reason=reason,
                    stage="structure",
                    time=action.start_time,
                )
            )
            violations.append(f"{prefix}: {reason}")
            continue
        if action.start_time < case.mission.horizon_start or action.end_time > case.mission.horizon_end:
            reason = "action lies outside the mission horizon"
            failures.append(
                _make_failure(
                    action_index=index,
                    satellite_id=action.satellite_id,
                    task_id=action.task_id,
                    reason=reason,
                    stage="structure",
                    time=action.start_time,
                )
            )
            violations.append(f"{prefix}: {reason}")
            continue
        misaligned = False
        for field_name, instant in (("start_time", action.start_time), ("end_time", action.end_time)):
            seconds = (instant - case.mission.horizon_start).total_seconds()
            if not _is_aligned(seconds, case.mission.action_time_step_s):
                reason = f"{field_name} must align to the {case.mission.action_time_step_s}s action grid"
                failures.append(
                    _make_failure(
                        action_index=index,
                        satellite_id=action.satellite_id,
                        task_id=action.task_id,
                        reason=reason,
                        stage="structure",
                        time=instant,
                    )
                )
                violations.append(f"{prefix}: {reason}")
                misaligned = True
                break
        if misaligned:
            continue
        if action.start_time < task.release_time or action.end_time > task.due_time:
            reason = "action lies outside the task window"
            failures.append(
                _make_failure(
                    action_index=index,
                    satellite_id=action.satellite_id,
                    task_id=action.task_id,
                    reason=reason,
                    stage="structure",
                    time=action.start_time,
                )
            )
            violations.append(f"{prefix}: {reason}")
            continue
        if action.duration_s != task.required_duration_s:
            reason = (
                f"action duration must equal required_duration_s "
                f"({task.required_duration_s}s)"
            )
            failures.append(
                _make_failure(
                    action_index=index,
                    satellite_id=action.satellite_id,
                    task_id=action.task_id,
                    reason=reason,
                    stage="structure",
                    time=action.start_time,
                )
            )
            violations.append(f"{prefix}: {reason}")
            continue
        satellite = case.satellites[action.satellite_id]
        if satellite.sensor.sensor_type != task.required_sensor_type:
            reason = "satellite sensor_type does not match task required_sensor_type"
            failures.append(
                _make_failure(
                    action_index=index,
                    satellite_id=action.satellite_id,
                    task_id=action.task_id,
                    reason=reason,
                    stage="structure",
                    time=action.start_time,
                )
            )
            violations.append(f"{prefix}: {reason}")
            continue
        validated.append(
            ValidatedAction(
                action_index=index,
                satellite_id=action.satellite_id,
                task_id=action.task_id,
                start_time=action.start_time,
                end_time=action.end_time,
            )
        )
    return validated, failures, violations


def _validate_observation_geometry(
    case: AeosspCase,
    propagation: _PropagationContext,
    validated_actions: list[ValidatedAction],
    failures: list[ActionFailure],
    violations: list[str],
) -> list[ValidatedAction]:
    accepted: list[ValidatedAction] = []
    for item in validated_actions:
        satellite = case.satellites[item.satellite_id]
        task = case.tasks[item.task_id]
        sample_times = _action_sample_times(
            item.start_time,
            item.end_time,
            step_s=case.mission.geometry_sample_step_s,
        )
        bad_reason: str | None = None
        bad_time: datetime | None = None
        for sample_time in sample_times:
            state_ecef = propagation.state_ecef(item.satellite_id, sample_time)
            sat_pos_ecef = state_ecef[:3]
            if not _target_visible(sat_pos_ecef, np.asarray(task.target_ecef_m, dtype=float)):
                bad_reason = "target is not continuously visible"
                bad_time = sample_time
                break
            off_nadir_deg = _off_nadir_deg(sat_pos_ecef, np.asarray(task.target_ecef_m, dtype=float))
            if off_nadir_deg > satellite.attitude_model.max_off_nadir_deg + 1.0e-6:
                bad_reason = "required pointing exceeds max_off_nadir_deg"
                bad_time = sample_time
                break
        if bad_reason is not None:
            failure_text = f"{bad_reason} at {_iso_z(bad_time)}" if bad_time is not None else bad_reason
            failures.append(
                _make_failure(
                    action_index=item.action_index,
                    satellite_id=item.satellite_id,
                    task_id=item.task_id,
                    reason=failure_text,
                    stage="geometry",
                    time=bad_time,
                )
            )
            violations.append(f"actions[{item.action_index}]: {failure_text}")
            continue
        accepted.append(item)
    return accepted


def _validate_slew_and_build_maneuver_windows(
    case: AeosspCase,
    propagation: _PropagationContext,
    actions_by_satellite: dict[str, list[ValidatedAction]],
    failures: list[ActionFailure],
    violations: list[str],
) -> tuple[dict[str, list[ValidatedAction]], dict[str, list[ManeuverWindow]]]:
    accepted_actions_by_satellite: dict[str, list[ValidatedAction]] = defaultdict(list)
    maneuver_windows: dict[str, list[ManeuverWindow]] = defaultdict(list)
    for satellite_id, actions in actions_by_satellite.items():
        satellite = case.satellites[satellite_id]
        actions.sort(key=lambda item: (item.start_time, item.end_time, item.action_index))
        previous: ValidatedAction | None = None
        for current in actions:
            if previous is not None and previous.end_time > current.start_time:
                reason = "observation actions overlap on the same satellite"
                failures.append(
                    _make_failure(
                        action_index=current.action_index,
                        satellite_id=satellite_id,
                        task_id=current.task_id,
                        reason=reason,
                        stage="slew",
                        time=current.start_time,
                    )
                )
                violations.append(f"actions[{current.action_index}]: {reason}")
                continue
            current_task = case.tasks[current.task_id]
            current_start_vec = _target_vector_eci(
                current_task, propagation, satellite_id, current.start_time
            )
            if previous is None:
                sat_state_eci = propagation.state_eci(satellite_id, current.start_time)
                from_vector = -sat_state_eci[:3]
                available_gap_s = (
                    current.start_time - case.mission.horizon_start
                ).total_seconds()
                from_task_id = None
                from_action_index = None
            else:
                previous_task = case.tasks[previous.task_id]
                from_vector = _target_vector_eci(
                    previous_task, propagation, satellite_id, previous.end_time
                )
                available_gap_s = (
                    current.start_time - previous.end_time
                ).total_seconds()
                from_task_id = previous.task_id
                from_action_index = previous.action_index
            slew_angle_deg = _angle_between_deg(from_vector, current_start_vec)
            slew_time_s = _slew_time_s(
                slew_angle_deg,
                satellite.attitude_model.max_slew_velocity_deg_per_s,
                satellite.attitude_model.max_slew_acceleration_deg_per_s2,
            )
            required_gap_s = slew_time_s + satellite.attitude_model.settling_time_s
            if available_gap_s + NUMERICAL_EPS < required_gap_s:
                reason = (
                    f"insufficient slew/settle time before observation "
                    f"(need {required_gap_s:.3f}s, have {available_gap_s:.3f}s)"
                )
                failures.append(
                    _make_failure(
                        action_index=current.action_index,
                        satellite_id=satellite_id,
                        task_id=current.task_id,
                        reason=reason,
                        stage="slew",
                        time=current.start_time,
                    )
                )
                violations.append(f"actions[{current.action_index}]: {reason}")
                continue
            if required_gap_s > NUMERICAL_EPS:
                window_start = current.start_time - timedelta(seconds=required_gap_s)
                maneuver_windows[satellite_id].append(
                    ManeuverWindow(
                        action_index=current.action_index,
                        satellite_id=satellite_id,
                        start_time=window_start,
                        end_time=current.start_time,
                        required_gap_s=required_gap_s,
                        slew_angle_deg=slew_angle_deg,
                        from_action_index=from_action_index,
                        from_task_id=from_task_id,
                        to_task_id=current.task_id,
                    )
                )
            accepted_actions_by_satellite[satellite_id].append(current)
            previous = current
    return accepted_actions_by_satellite, maneuver_windows


def _interval_contains(instant: datetime, start: datetime, end: datetime) -> bool:
    return start <= instant < end


def _resource_time_points(
    mission: Mission,
    actions: list[ValidatedAction],
    maneuver_windows: list[ManeuverWindow],
) -> list[datetime]:
    points: set[datetime] = {mission.horizon_start, mission.horizon_end}
    current = mission.horizon_start
    delta = timedelta(seconds=mission.resource_sample_step_s)
    while current < mission.horizon_end:
        points.add(current)
        current = min(current + delta, mission.horizon_end)
    points.add(mission.horizon_end)
    for item in actions:
        points.add(item.start_time)
        points.add(item.end_time)
    for window in maneuver_windows:
        points.add(window.start_time)
        points.add(window.end_time)
    return sorted(points)


def _segment_mode(
    active_observation: ValidatedAction | None,
    active_maneuver: ManeuverWindow | None,
) -> str:
    if active_observation is not None and active_maneuver is not None:
        return "observation+slew"
    if active_observation is not None:
        return "observation"
    if active_maneuver is not None:
        return "slew"
    return "idle"


def _simulate_battery_and_power(
    case: AeosspCase,
    propagation: _PropagationContext,
    actions_by_satellite: dict[str, list[ValidatedAction]],
    maneuver_windows: dict[str, list[ManeuverWindow]],
    failures: list[ActionFailure],
    violations: list[str],
) -> tuple[float, dict[str, Any], dict[str, tuple[BatteryTraceSegment, ...]]]:
    total_pc_wh = 0.0
    summaries: dict[str, Any] = {}
    traces: dict[str, tuple[BatteryTraceSegment, ...]] = {}
    for satellite_id, satellite in case.satellites.items():
        actions = sorted(
            actions_by_satellite.get(satellite_id, []),
            key=lambda item: (item.start_time, item.end_time, item.action_index),
        )
        windows = maneuver_windows.get(satellite_id, [])
        time_points = _resource_time_points(case.mission, actions, windows)
        battery_wh = satellite.resource_model.initial_battery_wh
        min_battery_wh = battery_wh
        min_battery_time = case.mission.horizon_start
        gross_consumption_wh = 0.0
        total_charge_wh = 0.0
        total_imaging_time_s = 0.0
        total_slew_time_s = 0.0
        failed = False
        trace_segments: list[BatteryTraceSegment] = []
        for start_time, end_time in zip(time_points, time_points[1:]):
            duration_s = (end_time - start_time).total_seconds()
            if duration_s <= 0.0:
                continue
            midpoint = start_time + ((end_time - start_time) / 2)
            active_observation = next(
                (
                    item
                    for item in actions
                    if _interval_contains(midpoint, item.start_time, item.end_time)
                ),
                None,
            )
            active_maneuver = next(
                (
                    window
                    for window in windows
                    if _interval_contains(midpoint, window.start_time, window.end_time)
                ),
                None,
            )
            load_power_w = satellite.resource_model.idle_power_w
            if active_observation is not None:
                load_power_w += satellite.resource_model.imaging_power_w
                total_imaging_time_s += duration_s
            if active_maneuver is not None:
                load_power_w += satellite.resource_model.slew_power_w
                total_slew_time_s += duration_s
            epoch = _datetime_to_epoch(midpoint)
            state_eci = propagation.state_eci(satellite_id, midpoint)
            charge_power_w = (
                satellite.resource_model.sunlit_charge_power_w
                if _is_sunlit(state_eci[:3], epoch)
                else 0.0
            )
            battery_start_wh = battery_wh
            gross_consumption_wh += (load_power_w * duration_s) / 3600.0
            total_charge_wh += (charge_power_w * duration_s) / 3600.0
            battery_wh += ((charge_power_w - load_power_w) * duration_s) / 3600.0
            if battery_wh < -NUMERICAL_EPS:
                reason = f"battery depletes below zero around {_iso_z(midpoint)}"
                failing_index = active_observation.action_index if active_observation else -1
                failing_task = active_observation.task_id if active_observation else ""
                failures.append(
                    _make_failure(
                        action_index=failing_index,
                        satellite_id=satellite_id,
                        task_id=failing_task,
                        reason=reason,
                        stage="battery",
                        time=midpoint,
                    )
                )
                violations.append(f"Satellite {satellite_id}: {reason}")
                failed = True
                battery_end_wh = battery_wh
            else:
                battery_wh = min(satellite.resource_model.battery_capacity_wh, battery_wh)
                battery_end_wh = battery_wh
                if battery_wh < min_battery_wh:
                    min_battery_wh = battery_wh
                    min_battery_time = end_time
            trace_segments.append(
                BatteryTraceSegment(
                    satellite_id=satellite_id,
                    start_time=start_time,
                    end_time=end_time,
                    battery_start_wh=battery_start_wh,
                    battery_end_wh=battery_end_wh,
                    load_power_w=load_power_w,
                    charge_power_w=charge_power_w,
                    mode=_segment_mode(active_observation, active_maneuver),
                    active_action_index=active_observation.action_index if active_observation else None,
                    active_task_id=active_observation.task_id if active_observation else None,
                    active_maneuver_to_action_index=active_maneuver.action_index if active_maneuver else None,
                )
            )
            if failed:
                break
        summaries[satellite_id] = {
            "initial_battery_wh": satellite.resource_model.initial_battery_wh,
            "minimum_battery_wh": min_battery_wh,
            "minimum_battery_time": _iso_z(min_battery_time),
            "final_battery_wh": battery_wh,
            "gross_consumption_wh": gross_consumption_wh,
            "total_charge_wh": total_charge_wh,
            "total_imaging_time_s": total_imaging_time_s,
            "total_slew_time_s": total_slew_time_s,
            "failed": failed,
        }
        traces[satellite_id] = tuple(trace_segments)
        if not failed:
            total_pc_wh += gross_consumption_wh
    return total_pc_wh, summaries, traces


def _compute_task_outcomes(
    case: AeosspCase,
    validated_actions: list[ValidatedAction],
) -> dict[str, TaskOutcome]:
    completed_by_task: dict[str, ValidatedAction] = {}
    for item in sorted(
        validated_actions,
        key=lambda item: (item.end_time, item.start_time, item.action_index),
    ):
        current = completed_by_task.get(item.task_id)
        if current is None or item.end_time < current.end_time:
            completed_by_task[item.task_id] = item
    outcomes: dict[str, TaskOutcome] = {}
    for task_id, task in case.tasks.items():
        completion = completed_by_task.get(task_id)
        outcomes[task_id] = TaskOutcome(
            task_id=task_id,
            completed=completion is not None,
            completion_time=completion.end_time if completion is not None else None,
            completed_by_action_index=completion.action_index if completion is not None else None,
            weight=task.weight,
        )
    return outcomes


def _compute_metrics(
    case: AeosspCase,
    task_outcomes: dict[str, TaskOutcome],
    total_pc_wh: float,
) -> dict[str, Any]:
    total_tasks = len(case.tasks)
    completed = [outcome for outcome in task_outcomes.values() if outcome.completed]
    total_weight = sum(task.weight for task in case.tasks.values())
    completed_weight = sum(outcome.weight for outcome in completed)
    tat_values_s = [
        (
            outcome.completion_time - case.tasks[outcome.task_id].release_time
        ).total_seconds()
        for outcome in completed
        if outcome.completion_time is not None
    ]
    return {
        "CR": len(completed) / total_tasks if total_tasks else 0.0,
        "WCR": completed_weight / total_weight if total_weight > 0.0 else 0.0,
        "TAT": (sum(tat_values_s) / len(tat_values_s)) if tat_values_s else None,
        "PC": total_pc_wh,
    }


def _build_timeline_events(
    validated_actions: list[ValidatedAction],
    maneuver_windows: tuple[ManeuverWindow, ...],
    failures: list[ActionFailure],
) -> tuple[TimelineEvent, ...]:
    events: list[TimelineEvent] = []
    for action in validated_actions:
        events.append(
            TimelineEvent(
                time=action.start_time,
                satellite_id=action.satellite_id,
                kind="action_start",
                action_index=action.action_index,
                task_id=action.task_id,
            )
        )
        events.append(
            TimelineEvent(
                time=action.end_time,
                satellite_id=action.satellite_id,
                kind="action_end",
                action_index=action.action_index,
                task_id=action.task_id,
            )
        )
    for window in maneuver_windows:
        events.append(
            TimelineEvent(
                time=window.start_time,
                satellite_id=window.satellite_id,
                kind="maneuver_start",
                action_index=window.action_index,
                task_id=window.to_task_id,
            )
        )
        events.append(
            TimelineEvent(
                time=window.end_time,
                satellite_id=window.satellite_id,
                kind="maneuver_end",
                action_index=window.action_index,
                task_id=window.to_task_id,
            )
        )
    for failure in failures:
        if failure.time is None:
            continue
        events.append(
            TimelineEvent(
                time=failure.time,
                satellite_id=failure.satellite_id,
                kind="failure",
                action_index=failure.action_index if failure.action_index >= 0 else None,
                task_id=failure.task_id or None,
                detail=failure.reason,
            )
        )
    events.sort(key=lambda item: (item.time, item.satellite_id, item.kind, item.action_index or -1))
    return tuple(events)


def _build_snapshot_candidates(
    validated_actions: list[ValidatedAction],
    failures: list[ActionFailure],
    resource_summary: dict[str, Any],
) -> tuple[datetime, ...]:
    candidates: list[datetime] = []
    for action in validated_actions:
        candidates.extend((action.start_time, action.end_time))
    for failure in failures:
        if failure.time is not None:
            candidates.append(failure.time)
    for summary in resource_summary.values():
        minimum_battery_time = summary.get("minimum_battery_time")
        if isinstance(minimum_battery_time, str):
            candidates.append(datetime.fromisoformat(minimum_battery_time.replace("Z", "+00:00")).astimezone(UTC))
    unique = sorted({candidate.astimezone(UTC) for candidate in candidates})
    return tuple(unique)


def _build_diagnostics(
    task_outcomes: dict[str, TaskOutcome],
    failures: list[ActionFailure],
    maneuver_windows: tuple[ManeuverWindow, ...],
    resource_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "action_failures": [failure.as_dict() for failure in failures],
        "maneuver_windows": [window.as_dict() for window in maneuver_windows],
        "per_task": {
            task_id: outcome.as_dict()
            for task_id, outcome in task_outcomes.items()
        },
        "per_satellite_resource_summary": resource_summary,
    }


def analyze(case: AeosspCase, solution: AeosspSolution) -> SolutionAnalysis:
    _ensure_brahe_ready()
    propagation = _PropagationContext(case)

    validated_actions, failures, violations = _validate_action_structure(case, solution)
    validated_actions = _validate_observation_geometry(
        case, propagation, validated_actions, failures, violations
    )

    actions_by_satellite: dict[str, list[ValidatedAction]] = defaultdict(list)
    for item in validated_actions:
        actions_by_satellite[item.satellite_id].append(item)

    accepted_actions_by_satellite, maneuver_windows_by_satellite = _validate_slew_and_build_maneuver_windows(
        case, propagation, actions_by_satellite, failures, violations
    )
    accepted_actions = [
        item
        for satellite_id in sorted(accepted_actions_by_satellite)
        for item in accepted_actions_by_satellite[satellite_id]
    ]
    maneuver_windows = tuple(
        window
        for satellite_id in sorted(maneuver_windows_by_satellite)
        for window in maneuver_windows_by_satellite[satellite_id]
    )

    total_pc_wh = 0.0
    resource_summary: dict[str, Any] = {}
    battery_traces: dict[str, tuple[BatteryTraceSegment, ...]] = {
        sat_id: tuple() for sat_id in case.satellites
    }
    total_pc_wh, resource_summary, battery_traces = _simulate_battery_and_power(
        case,
        propagation,
        accepted_actions_by_satellite,
        maneuver_windows_by_satellite,
        failures,
        violations,
    )

    task_outcomes = _compute_task_outcomes(case, accepted_actions)
    diagnostics = _build_diagnostics(task_outcomes, failures, maneuver_windows, resource_summary)
    timeline_events = _build_timeline_events(accepted_actions, maneuver_windows, failures)
    snapshot_candidates = _build_snapshot_candidates(accepted_actions, failures, resource_summary)

    if violations:
        result = VerificationResult(
            valid=False,
            metrics=_default_metrics(),
            violations=violations,
            diagnostics=diagnostics,
        )
    else:
        result = VerificationResult(
            valid=True,
            metrics=_compute_metrics(case, task_outcomes, total_pc_wh),
            violations=[],
            diagnostics=diagnostics,
        )

    return SolutionAnalysis(
        case=case,
        solution=solution,
        result=result,
        validated_actions=tuple(
            sorted(accepted_actions, key=lambda item: (item.start_time, item.end_time, item.action_index))
        ),
        action_failures=tuple(failures),
        maneuver_windows=maneuver_windows,
        task_outcomes=task_outcomes,
        battery_traces=battery_traces,
        per_satellite_resource_summary=resource_summary,
        timeline_events=timeline_events,
        snapshot_candidates=snapshot_candidates,
    )


def analyze_solution(case_dir: str | Path, solution_path: str | Path) -> SolutionAnalysis:
    case = load_case(case_dir)
    solution = load_solution(solution_path)
    return analyze(case, solution)


def verify(case: AeosspCase, solution: AeosspSolution) -> VerificationResult:
    return analyze(case, solution).result


def verify_solution(case_dir: str | Path, solution_path: str | Path) -> VerificationResult:
    try:
        return analyze_solution(case_dir, solution_path).result
    except (FileNotFoundError, ValueError) as exc:
        return _invalid_result([str(exc)], diagnostics={})
