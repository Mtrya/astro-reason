"""Solver-local validation and bounded repair for MWIS schedules."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import timedelta
import time
from typing import Any

import brahe

from .candidates import Candidate
from .case_io import AeosspCase, NUMERICAL_EPS, Satellite, iso_z
from .geometry import (
    PropagationContext,
    angle_between_deg,
    datetime_to_epoch,
    required_slew_settle_s,
    target_vector_eci,
)
from .transition import TransitionVectorCache, transition_result


@dataclass(frozen=True, slots=True)
class RepairConfig:
    max_repair_iterations: int = 200
    enable_incremental_repair: bool = True

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "RepairConfig":
        payload = payload or {}
        return cls(
            max_repair_iterations=max(0, int(payload.get("max_repair_iterations", 200))),
            enable_incremental_repair=_config_bool(
                payload.get("enable_incremental_repair", True)
            ),
        )

    def as_status_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    reason: str
    message: str
    candidate_ids: tuple[str, ...] = ()
    satellite_id: str | None = None
    task_id: str | None = None
    offset_s: float | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "reason": self.reason,
            "message": self.message,
            "candidate_ids": list(self.candidate_ids),
        }
        if self.satellite_id is not None:
            payload["satellite_id"] = self.satellite_id
        if self.task_id is not None:
            payload["task_id"] = self.task_id
        if self.offset_s is not None:
            payload["offset_s"] = self.offset_s
        return payload


@dataclass(slots=True)
class BatteryTrace:
    satellite_id: str
    min_battery_wh: float
    min_offset_s: float
    final_battery_wh: float
    gross_consumption_wh: float
    total_charge_wh: float
    total_imaging_time_s: float
    total_slew_time_s: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ValidationReport:
    valid: bool
    issue_count: int
    issues: list[ValidationIssue] = field(default_factory=list)
    battery: dict[str, BatteryTrace] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issue_count": self.issue_count,
            "issues": [issue.as_dict() for issue in self.issues],
            "battery": {
                satellite_id: trace.as_dict()
                for satellite_id, trace in sorted(self.battery.items())
            },
        }


@dataclass(frozen=True, slots=True)
class RepairRemoval:
    iteration: int
    candidate_id: str
    reason: str
    task_weight: float
    satellite_id: str
    task_id: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RepairValidationRun:
    iteration: int
    mode: str
    elapsed_s: float
    affected_satellite_ids: tuple[str, ...] = ()
    fallback_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "iteration": self.iteration,
            "mode": self.mode,
            "elapsed_s": self.elapsed_s,
            "affected_satellite_ids": list(self.affected_satellite_ids),
        }
        if self.fallback_reason is not None:
            payload["fallback_reason"] = self.fallback_reason
        return payload


@dataclass(slots=True)
class RepairResult:
    candidates: list[Candidate]
    reports: list[ValidationReport]
    removals: list[RepairRemoval]
    terminated_reason: str
    validation_runs: list[RepairValidationRun] = field(default_factory=list)

    @property
    def final_report(self) -> ValidationReport:
        return self.reports[-1]

    def as_status_dict(self) -> dict[str, Any]:
        objective_after_repair = _candidate_objective(self.candidates)
        objective_removed_by_repair = sum(removal.task_weight for removal in self.removals)
        objective_before_repair = objective_after_repair + objective_removed_by_repair
        initial_report = self.reports[0] if self.reports else None
        final_report = self.final_report
        validation_runs = [run.as_dict() for run in self.validation_runs]
        return {
            "attempts": len(self.reports),
            "actions_before_repair": (
                len(self.candidates) + len(self.removals)
                if self.reports
                else len(self.candidates)
            ),
            "actions_after_repair": len(self.candidates),
            "objective_before_repair": objective_before_repair,
            "objective_after_repair": objective_after_repair,
            "objective_removed_by_repair": objective_removed_by_repair,
            "battery_failure_count_before_repair": (
                _battery_failure_count(initial_report) if initial_report is not None else 0
            ),
            "battery_failure_count_after_repair": _battery_failure_count(final_report),
            "removed_action_count_by_reason": _removal_count_by_reason(self.removals),
            "validation_iterations": validation_runs,
            "validation_time_s_by_iteration": [
                run.elapsed_s for run in self.validation_runs
            ],
            "total_validation_time_s": sum(run.elapsed_s for run in self.validation_runs),
            "full_validation_count": sum(
                1 for run in self.validation_runs if run.mode == "full"
            ),
            "incremental_validation_count": sum(
                1 for run in self.validation_runs if run.mode == "incremental"
            ),
            "fallback_count": sum(
                1 for run in self.validation_runs if run.fallback_reason is not None
            ),
            "affected_satellites_by_iteration": [
                list(run.affected_satellite_ids) for run in self.validation_runs
            ],
            "removed_actions": [removal.as_dict() for removal in self.removals],
            "terminated_reason": self.terminated_reason,
            "initial_local_valid": self.reports[0].valid if self.reports else True,
            "initial_issue_count": self.reports[0].issue_count if self.reports else 0,
            "final_local_valid": final_report.valid,
            "final_issue_count": final_report.issue_count,
            "initial_report": initial_report.as_dict() if initial_report is not None else None,
            "final_report": final_report.as_dict(),
        }

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "attempts": len(self.reports),
            "terminated_reason": self.terminated_reason,
            "removed_actions": [removal.as_dict() for removal in self.removals],
            "validation_iterations": [run.as_dict() for run in self.validation_runs],
            "reports": [report.as_dict() for report in self.reports],
        }


@dataclass(frozen=True, slots=True)
class _SatelliteValidationState:
    schedule_issues: list[ValidationIssue]
    battery_issues: list[ValidationIssue]
    battery_trace: BatteryTrace


def _config_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    return bool(value)


def _candidate_objective(candidates: list[Candidate]) -> float:
    return sum(candidate.task_weight for candidate in candidates)


def _battery_failure_count(report: ValidationReport) -> int:
    return sum(1 for issue in report.issues if issue.reason == "battery_depletion")


def _removal_count_by_reason(removals: list[RepairRemoval]) -> dict[str, int]:
    return dict(sorted(Counter(removal.reason for removal in removals).items()))


def action_shape_issues(case: AeosspCase, candidates: list[Candidate]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for candidate in candidates:
        satellite = case.satellites.get(candidate.satellite_id)
        task = case.tasks.get(candidate.task_id)
        if satellite is None:
            issues.append(
                ValidationIssue(
                    reason="unknown_satellite",
                    message=f"unknown satellite_id {candidate.satellite_id}",
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                )
            )
            continue
        if task is None:
            issues.append(
                ValidationIssue(
                    reason="unknown_task",
                    message=f"unknown task_id {candidate.task_id}",
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                )
            )
            continue
        if candidate.duration_s != task.required_duration_s:
            issues.append(
                ValidationIssue(
                    reason="duration_mismatch",
                    message="candidate duration does not match task required_duration_s",
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                )
            )
        if candidate.start_offset_s % case.mission.action_time_step_s != 0:
            issues.append(
                ValidationIssue(
                    reason="off_grid_start",
                    message="candidate start is not aligned to action grid",
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                )
            )
        if candidate.end_offset_s % case.mission.action_time_step_s != 0:
            issues.append(
                ValidationIssue(
                    reason="off_grid_end",
                    message="candidate end is not aligned to action grid",
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                )
            )
        if candidate.start_offset_s < 0 or candidate.end_offset_s > case.mission.horizon_seconds:
            issues.append(
                ValidationIssue(
                    reason="out_of_horizon",
                    message="candidate lies outside the mission horizon",
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                )
            )
        release_offset = int(round((task.release_time - case.mission.horizon_start).total_seconds()))
        due_offset = int(round((task.due_time - case.mission.horizon_start).total_seconds()))
        if candidate.start_offset_s < release_offset or candidate.end_offset_s > due_offset:
            issues.append(
                ValidationIssue(
                    reason="outside_task_window",
                    message="candidate lies outside the task time window",
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                )
            )
        if satellite.sensor_type != task.required_sensor_type:
            issues.append(
                ValidationIssue(
                    reason="sensor_mismatch",
                    message="satellite sensor_type does not match task required_sensor_type",
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                )
            )
    return issues


def duplicate_task_issues(candidates: list[Candidate]) -> list[ValidationIssue]:
    by_task: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        by_task.setdefault(candidate.task_id, []).append(candidate)
    issues: list[ValidationIssue] = []
    for task_id, task_candidates in sorted(by_task.items()):
        if len(task_candidates) <= 1:
            continue
        ordered = sorted(
            task_candidates,
            key=lambda item: (item.task_weight, -item.end_offset_s, item.candidate_id),
        )
        issues.append(
            ValidationIssue(
                reason="duplicate_task",
                message=f"task {task_id} is selected more than once",
                candidate_ids=tuple(candidate.candidate_id for candidate in ordered),
                task_id=task_id,
            )
        )
    return issues


def _initial_slew_required_s(
    case: AeosspCase,
    candidate: Candidate,
    *,
    propagation: PropagationContext,
) -> float:
    satellite = case.satellites[candidate.satellite_id]
    instant = case.mission.horizon_start + timedelta(seconds=candidate.start_offset_s)
    sat_state_eci = propagation.state_eci(candidate.satellite_id, instant)
    slew_angle_deg = angle_between_deg(
        -sat_state_eci[:3],
        target_vector_eci(
            case.tasks[candidate.task_id],
            propagation,
            candidate.satellite_id,
            instant,
        ),
    )
    return required_slew_settle_s(slew_angle_deg, satellite)


def schedule_issues(
    case: AeosspCase,
    candidates: list[Candidate],
    *,
    propagation: PropagationContext,
    vector_cache: TransitionVectorCache | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    vector_cache = vector_cache or TransitionVectorCache(case, propagation)
    by_satellite: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        if candidate.satellite_id in case.satellites and candidate.task_id in case.tasks:
            by_satellite.setdefault(candidate.satellite_id, []).append(candidate)

    for satellite_id, satellite_candidates in sorted(by_satellite.items()):
        issues.extend(
            _schedule_issues_for_satellite(
                case,
                satellite_id,
                satellite_candidates,
                propagation=propagation,
                vector_cache=vector_cache,
            )
        )
    return issues


def _schedule_issues_for_satellite(
    case: AeosspCase,
    satellite_id: str,
    satellite_candidates: list[Candidate],
    *,
    propagation: PropagationContext,
    vector_cache: TransitionVectorCache,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    ordered = sorted(
        [
            candidate
            for candidate in satellite_candidates
            if candidate.satellite_id == satellite_id and candidate.task_id in case.tasks
        ],
        key=lambda item: (item.start_offset_s, item.end_offset_s, item.candidate_id),
    )
    if ordered:
        initial_required = _initial_slew_required_s(
            case,
            ordered[0],
            propagation=propagation,
        )
        if ordered[0].start_offset_s + NUMERICAL_EPS < initial_required:
            issues.append(
                ValidationIssue(
                    reason="initial_slew_gap",
                    message="first action does not leave enough time to slew from nadir",
                    candidate_ids=(ordered[0].candidate_id,),
                    satellite_id=satellite_id,
                    task_id=ordered[0].task_id,
                    offset_s=ordered[0].start_offset_s,
                )
            )
    for previous, current in zip(ordered, ordered[1:]):
        if previous.end_offset_s > current.start_offset_s:
            issues.append(
                ValidationIssue(
                    reason="overlap",
                    message="same-satellite actions overlap",
                    candidate_ids=(previous.candidate_id, current.candidate_id),
                    satellite_id=satellite_id,
                    offset_s=current.start_offset_s,
                )
            )
            continue
        result = transition_result(
            previous,
            current,
            case=case,
            vector_cache=vector_cache,
        )
        if not result.feasible:
            issues.append(
                ValidationIssue(
                    reason="transition_gap",
                    message=(
                        "same-satellite actions have insufficient transition gap "
                        f"available={result.available_gap_s:.3f}s "
                        f"required={result.required_gap_s:.3f}s"
                    ),
                    candidate_ids=(previous.candidate_id, current.candidate_id),
                    satellite_id=satellite_id,
                    offset_s=current.start_offset_s,
                )
            )
    return issues


def is_sunlit(
    propagation: PropagationContext,
    satellite_id: str,
    instant_offset_s: float,
    case: AeosspCase,
) -> bool:
    instant = case.mission.horizon_start + timedelta(seconds=instant_offset_s)
    epoch = datetime_to_epoch(instant)
    sat_state_eci = propagation.state_eci(satellite_id, instant)
    illumination = float(brahe.eclipse_cylindrical(sat_state_eci[:3], brahe.sun_position(epoch)))
    return illumination > 0.5


def _contains_offset(intervals: list[tuple[float, float, str]], offset_s: float) -> bool:
    return any(start_s <= offset_s < end_s for start_s, end_s, _ in intervals)


def _resource_time_points(
    case: AeosspCase,
    imaging_intervals: list[tuple[float, float, str]],
    slew_intervals: list[tuple[float, float, str]],
) -> list[float]:
    points: set[float] = {0.0, float(case.mission.horizon_seconds)}
    step_s = case.mission.resource_sample_step_s
    for offset_s in range(0, case.mission.horizon_seconds, step_s):
        points.add(float(offset_s))
        points.add(float(min(offset_s + step_s, case.mission.horizon_seconds)))
    for start_s, end_s, _ in imaging_intervals:
        points.add(start_s)
        points.add(end_s)
    for start_s, end_s, _ in slew_intervals:
        points.add(start_s)
        points.add(end_s)
    return sorted(points)


def _slew_intervals(
    case: AeosspCase,
    satellite_candidates: list[Candidate],
    *,
    propagation: PropagationContext,
    vector_cache: TransitionVectorCache | None = None,
) -> tuple[list[tuple[float, float, str]], list[ValidationIssue]]:
    intervals: list[tuple[float, float, str]] = []
    issues: list[ValidationIssue] = []
    ordered = sorted(
        satellite_candidates,
        key=lambda item: (item.start_offset_s, item.end_offset_s, item.candidate_id),
    )
    if not ordered:
        return intervals, issues
    first = ordered[0]
    initial_required = _initial_slew_required_s(case, first, propagation=propagation)
    initial_start = first.start_offset_s - initial_required
    if initial_start < -NUMERICAL_EPS:
        issues.append(
            ValidationIssue(
                reason="initial_slew_gap",
                message="first action requires a pre-horizon slew interval",
                candidate_ids=(first.candidate_id,),
                satellite_id=first.satellite_id,
                task_id=first.task_id,
                offset_s=first.start_offset_s,
            )
        )
    else:
        intervals.append((max(0.0, initial_start), float(first.start_offset_s), first.candidate_id))

    vector_cache = vector_cache or TransitionVectorCache(case, propagation)
    for previous, current in zip(ordered, ordered[1:]):
        result = transition_result(previous, current, case=case, vector_cache=vector_cache)
        intervals.append(
            (
                max(float(previous.end_offset_s), float(current.start_offset_s) - result.required_gap_s),
                float(current.start_offset_s),
                current.candidate_id,
            )
        )
    return intervals, issues


def battery_issues(
    case: AeosspCase,
    candidates: list[Candidate],
    *,
    propagation: PropagationContext,
    vector_cache: TransitionVectorCache | None = None,
) -> tuple[list[ValidationIssue], dict[str, BatteryTrace]]:
    issues: list[ValidationIssue] = []
    traces: dict[str, BatteryTrace] = {}
    vector_cache = vector_cache or TransitionVectorCache(case, propagation)
    by_satellite: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        if candidate.satellite_id in case.satellites:
            by_satellite.setdefault(candidate.satellite_id, []).append(candidate)

    for satellite_id in sorted(case.satellites):
        satellite_issues, trace = _battery_issues_for_satellite(
            case,
            satellite_id,
            by_satellite.get(satellite_id, []),
            propagation=propagation,
            vector_cache=vector_cache,
        )
        issues.extend(satellite_issues)
        traces[satellite_id] = trace
    return issues, traces


def _battery_issues_for_satellite(
    case: AeosspCase,
    satellite_id: str,
    satellite_candidates: list[Candidate],
    *,
    propagation: PropagationContext,
    vector_cache: TransitionVectorCache,
) -> tuple[list[ValidationIssue], BatteryTrace]:
    satellite = case.satellites[satellite_id]
    resource = satellite.resource_model
    energy_wh = resource.initial_battery_wh
    min_energy_wh = energy_wh
    min_offset_s = 0.0
    gross_consumption_wh = 0.0
    total_charge_wh = 0.0
    total_imaging_time_s = 0.0
    total_slew_time_s = 0.0
    issues: list[ValidationIssue] = []
    valid_candidates = [
        candidate
        for candidate in satellite_candidates
        if candidate.satellite_id == satellite_id and candidate.task_id in case.tasks
    ]
    imaging_intervals = [
        (float(candidate.start_offset_s), float(candidate.end_offset_s), candidate.candidate_id)
        for candidate in valid_candidates
    ]
    slew_intervals, slew_issues = _slew_intervals(
        case,
        valid_candidates,
        propagation=propagation,
        vector_cache=vector_cache,
    )
    issues.extend(slew_issues)
    time_points = _resource_time_points(case, imaging_intervals, slew_intervals)
    for start_s, end_s in zip(time_points, time_points[1:]):
        delta_s = end_s - start_s
        if delta_s <= 0.0:
            continue
        midpoint_s = start_s + (0.5 * delta_s)
        load_w = resource.idle_power_w
        if _contains_offset(imaging_intervals, midpoint_s):
            load_w += resource.imaging_power_w
            total_imaging_time_s += delta_s
        if _contains_offset(slew_intervals, midpoint_s):
            load_w += resource.slew_power_w
            total_slew_time_s += delta_s
        charge_w = (
            resource.sunlit_charge_power_w
            if is_sunlit(propagation, satellite_id, midpoint_s, case)
            else 0.0
        )
        gross_consumption_wh += load_w * (delta_s / 3600.0)
        total_charge_wh += charge_w * (delta_s / 3600.0)
        energy_wh += (charge_w - load_w) * (delta_s / 3600.0)
        if energy_wh < -NUMERICAL_EPS:
            min_energy_wh = energy_wh
            min_offset_s = end_s
            break
        energy_wh = min(resource.battery_capacity_wh, energy_wh)
        if energy_wh < min_energy_wh:
            min_energy_wh = energy_wh
            min_offset_s = end_s
    trace = BatteryTrace(
        satellite_id=satellite_id,
        min_battery_wh=min_energy_wh,
        min_offset_s=min_offset_s,
        final_battery_wh=energy_wh,
        gross_consumption_wh=gross_consumption_wh,
        total_charge_wh=total_charge_wh,
        total_imaging_time_s=total_imaging_time_s,
        total_slew_time_s=total_slew_time_s,
    )
    if min_energy_wh < -NUMERICAL_EPS:
        issues.append(
            ValidationIssue(
                reason="battery_depletion",
                message=f"local battery estimate falls below zero: {min_energy_wh:.6f} Wh",
                satellite_id=satellite_id,
                offset_s=min_offset_s,
            )
        )
    return issues, trace


def validate_candidates(
    case: AeosspCase,
    candidates: list[Candidate],
    *,
    propagation: PropagationContext | None = None,
    vector_cache: TransitionVectorCache | None = None,
) -> ValidationReport:
    stable_candidates = sorted(
        candidates,
        key=lambda item: (item.start_offset_s, item.satellite_id, item.task_id, item.candidate_id),
    )
    issues: list[ValidationIssue] = []
    issues.extend(action_shape_issues(case, stable_candidates))
    issues.extend(duplicate_task_issues(stable_candidates))

    if propagation is None:
        step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
        propagation = PropagationContext(case.satellites, step_s=step_s)
    vector_cache = vector_cache or TransitionVectorCache(case, propagation)
    issues.extend(
        schedule_issues(
            case,
            stable_candidates,
            propagation=propagation,
            vector_cache=vector_cache,
        )
    )
    battery_failure_issues, battery = battery_issues(
        case,
        stable_candidates,
        propagation=propagation,
        vector_cache=vector_cache,
    )
    issues.extend(battery_failure_issues)
    return ValidationReport(valid=not issues, issue_count=len(issues), issues=issues, battery=battery)


class _IncrementalRepairValidator:
    def __init__(self, case: AeosspCase, initial_candidates: list[Candidate]):
        self.case = case
        step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
        self.propagation = PropagationContext(case.satellites, step_s=step_s)
        self.vector_cache = TransitionVectorCache(case, self.propagation)
        self._shape_issue_cache: dict[str, list[ValidationIssue]] = {
            candidate.candidate_id: action_shape_issues(case, [candidate])
            for candidate in initial_candidates
        }
        self._satellite_states: dict[str, _SatelliteValidationState] = {}
        self._initialized = False

    @staticmethod
    def _stable(candidates: list[Candidate]) -> list[Candidate]:
        return sorted(
            candidates,
            key=lambda item: (item.start_offset_s, item.satellite_id, item.task_id, item.candidate_id),
        )

    def _candidates_by_satellite(
        self,
        candidates: list[Candidate],
    ) -> dict[str, list[Candidate]]:
        by_satellite: dict[str, list[Candidate]] = {}
        for candidate in candidates:
            if candidate.satellite_id in self.case.satellites:
                by_satellite.setdefault(candidate.satellite_id, []).append(candidate)
        return by_satellite

    def _validate_satellite(
        self,
        satellite_id: str,
        by_satellite: dict[str, list[Candidate]],
    ) -> _SatelliteValidationState:
        satellite_candidates = by_satellite.get(satellite_id, [])
        schedule = _schedule_issues_for_satellite(
            self.case,
            satellite_id,
            satellite_candidates,
            propagation=self.propagation,
            vector_cache=self.vector_cache,
        )
        battery, trace = _battery_issues_for_satellite(
            self.case,
            satellite_id,
            satellite_candidates,
            propagation=self.propagation,
            vector_cache=self.vector_cache,
        )
        return _SatelliteValidationState(
            schedule_issues=schedule,
            battery_issues=battery,
            battery_trace=trace,
        )

    def _rebuild_all(self, by_satellite: dict[str, list[Candidate]]) -> None:
        self._satellite_states = {
            satellite_id: self._validate_satellite(satellite_id, by_satellite)
            for satellite_id in sorted(self.case.satellites)
        }
        self._initialized = True

    def _compose_report(self, stable_candidates: list[Candidate]) -> ValidationReport:
        issues: list[ValidationIssue] = []
        for candidate in stable_candidates:
            cached = self._shape_issue_cache.get(candidate.candidate_id)
            if cached is None:
                cached = action_shape_issues(self.case, [candidate])
                self._shape_issue_cache[candidate.candidate_id] = cached
            issues.extend(cached)
        issues.extend(duplicate_task_issues(stable_candidates))
        for satellite_id in sorted(self.case.satellites):
            state = self._satellite_states[satellite_id]
            issues.extend(state.schedule_issues)
        battery = {
            satellite_id: self._satellite_states[satellite_id].battery_trace
            for satellite_id in sorted(self.case.satellites)
        }
        for satellite_id in sorted(self.case.satellites):
            issues.extend(self._satellite_states[satellite_id].battery_issues)
        return ValidationReport(
            valid=not issues,
            issue_count=len(issues),
            issues=issues,
            battery=battery,
        )

    def validate(
        self,
        candidates: list[Candidate],
        *,
        iteration: int,
        affected_satellite_id: str | None,
    ) -> tuple[ValidationReport, RepairValidationRun]:
        start = time.perf_counter()
        stable_candidates = self._stable(candidates)
        by_satellite = self._candidates_by_satellite(stable_candidates)
        mode = "incremental"
        affected_satellite_ids: tuple[str, ...] = ()
        fallback_reason: str | None = None
        if not self._initialized:
            mode = "full"
            self._rebuild_all(by_satellite)
        elif affected_satellite_id is None:
            mode = "full"
            fallback_reason = "missing_affected_satellite"
            self._rebuild_all(by_satellite)
        elif affected_satellite_id not in self.case.satellites:
            mode = "full"
            fallback_reason = "unknown_affected_satellite"
            self._rebuild_all(by_satellite)
        else:
            affected_satellite_ids = (affected_satellite_id,)
            self._satellite_states[affected_satellite_id] = self._validate_satellite(
                affected_satellite_id,
                by_satellite,
            )
        report = self._compose_report(stable_candidates)
        return report, RepairValidationRun(
            iteration=iteration,
            mode=mode,
            elapsed_s=time.perf_counter() - start,
            affected_satellite_ids=affected_satellite_ids,
            fallback_reason=fallback_reason,
        )


def _candidate_priority(
    candidate: Candidate,
    *,
    conflict_degrees: dict[str, int],
) -> tuple[Any, ...]:
    return (
        candidate.task_weight,
        -candidate.end_offset_s,
        -conflict_degrees.get(candidate.candidate_id, 0),
        candidate.candidate_id,
    )


def _battery_candidate_priority(
    candidate: Candidate,
    *,
    cutoff_s: float,
    conflict_degrees: dict[str, int],
) -> tuple[Any, ...]:
    return (
        candidate.task_weight,
        abs(cutoff_s - candidate.end_offset_s),
        -candidate.duration_s,
        -conflict_degrees.get(candidate.candidate_id, 0),
        -candidate.end_offset_s,
        candidate.candidate_id,
    )


def _choose_battery_removal(
    issue: ValidationIssue,
    candidates: list[Candidate],
    *,
    conflict_degrees: dict[str, int],
) -> Candidate | None:
    if issue.satellite_id is None:
        return None
    cutoff_s = issue.offset_s if issue.offset_s is not None else float("inf")
    same_satellite = [
        candidate
        for candidate in candidates
        if candidate.satellite_id == issue.satellite_id
        and candidate.start_offset_s <= cutoff_s + NUMERICAL_EPS
    ]
    if not same_satellite:
        same_satellite = [
            candidate for candidate in candidates if candidate.satellite_id == issue.satellite_id
        ]
    if not same_satellite:
        return None
    return min(
        same_satellite,
        key=lambda candidate: _battery_candidate_priority(
            candidate,
            cutoff_s=cutoff_s,
            conflict_degrees=conflict_degrees,
        ),
    )


def choose_repair_removal(
    report: ValidationReport,
    candidates: list[Candidate],
    *,
    conflict_degrees: dict[str, int] | None = None,
) -> tuple[Candidate, str] | tuple[None, None]:
    conflict_degrees = conflict_degrees or {}
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    for issue in report.issues:
        if issue.reason == "battery_depletion":
            removal = _choose_battery_removal(
                issue,
                candidates,
                conflict_degrees=conflict_degrees,
            )
            if removal is not None:
                return removal, issue.reason
            continue
        implicated = [
            candidate_by_id[candidate_id]
            for candidate_id in issue.candidate_ids
            if candidate_id in candidate_by_id
        ]
        if not implicated:
            continue
        return min(
            implicated,
            key=lambda candidate: _candidate_priority(
                candidate,
                conflict_degrees=conflict_degrees,
            ),
        ), issue.reason
    return None, None


def repair_candidates(
    case: AeosspCase,
    candidates: list[Candidate],
    *,
    config: RepairConfig | None = None,
    conflict_degrees: dict[str, int] | None = None,
) -> RepairResult:
    config = config or RepairConfig()
    current = sorted(
        candidates,
        key=lambda item: (item.start_offset_s, item.satellite_id, item.task_id, item.candidate_id),
    )
    reports: list[ValidationReport] = []
    removals: list[RepairRemoval] = []
    validation_runs: list[RepairValidationRun] = []
    terminated_reason = "max_iterations"
    affected_satellite_id: str | None = None
    incremental_validator = (
        _IncrementalRepairValidator(case, current)
        if config.enable_incremental_repair
        else None
    )

    for iteration in range(config.max_repair_iterations + 1):
        if incremental_validator is not None:
            report, validation_run = incremental_validator.validate(
                current,
                iteration=iteration,
                affected_satellite_id=affected_satellite_id,
            )
        else:
            validation_start = time.perf_counter()
            report = validate_candidates(case, current)
            validation_run = RepairValidationRun(
                iteration=iteration,
                mode="full",
                elapsed_s=time.perf_counter() - validation_start,
            )
        validation_runs.append(validation_run)
        reports.append(report)
        if report.valid:
            terminated_reason = "valid"
            break
        if iteration >= config.max_repair_iterations:
            break
        removal, reason = choose_repair_removal(
            report,
            current,
            conflict_degrees=conflict_degrees,
        )
        if removal is None or reason is None:
            terminated_reason = "no_removal_candidate"
            break
        current = [
            candidate for candidate in current if candidate.candidate_id != removal.candidate_id
        ]
        affected_satellite_id = removal.satellite_id
        removals.append(
            RepairRemoval(
                iteration=iteration,
                candidate_id=removal.candidate_id,
                reason=reason,
                task_weight=removal.task_weight,
                satellite_id=removal.satellite_id,
                task_id=removal.task_id,
            )
        )

    return RepairResult(
        candidates=current,
        reports=reports,
        removals=removals,
        terminated_reason=terminated_reason,
        validation_runs=validation_runs,
    )


def solution_payload_for_candidates(candidates: list[Candidate]) -> dict[str, Any]:
    return {
        "actions": [
            {
                "type": "observation",
                "satellite_id": candidate.satellite_id,
                "task_id": candidate.task_id,
                "start_time": candidate.start_time,
                "end_time": candidate.end_time,
            }
            for candidate in sorted(
                candidates,
                key=lambda item: (item.start_offset_s, item.satellite_id, item.task_id),
            )
        ]
    }


def expected_action_times(candidate: Candidate) -> tuple[str, str]:
    return candidate.start_time, candidate.end_time
