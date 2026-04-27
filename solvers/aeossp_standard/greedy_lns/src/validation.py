"""Solver-local schedule validation and bounded repair for greedy-LNS."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

import brahe

from .candidates import Candidate
from .case_io import AeosspCase, NUMERICAL_EPS, Satellite, _is_aligned, iso_z
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

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "RepairConfig":
        payload = payload or {}
        return cls(max_repair_iterations=max(0, int(payload.get("max_repair_iterations", 200))))

    def as_status_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BatteryGuardConfig:
    enable_battery_guardrails: bool = False
    battery_guard_min_wh: float = 0.0

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "BatteryGuardConfig":
        payload = payload or {}
        return cls(
            enable_battery_guardrails=bool(payload.get("enable_battery_guardrails", False)),
            battery_guard_min_wh=float(payload.get("battery_guard_min_wh", 0.0)),
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
        payload: dict[str, Any] = {
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
class BatteryGuardDecision:
    allowed: bool
    affected_satellites: tuple[str, ...]
    before_min_battery_wh: float | None
    after_min_battery_wh: float | None
    before_battery_failure_count: int
    after_battery_failure_count: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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


@dataclass(slots=True)
class RepairResult:
    candidates: list[Candidate]
    reports: list[ValidationReport]
    removals: list[RepairRemoval]
    terminated_reason: str

    @property
    def final_report(self) -> ValidationReport:
        return self.reports[-1]

    def as_status_dict(self) -> dict[str, Any]:
        objective_after_repair = _candidate_objective(self.candidates)
        objective_removed_by_repair = sum(removal.task_weight for removal in self.removals)
        objective_before_repair = objective_after_repair + objective_removed_by_repair
        initial_report = self.reports[0] if self.reports else None
        final_report = self.final_report
        return {
            "attempts": len(self.reports),
            "actions_before_repair": (
                len(self.candidates) + len(self.removals) if self.reports else len(self.candidates)
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
            "reports": [report.as_dict() for report in self.reports],
        }


def _candidate_objective(candidates: list[Candidate]) -> float:
    return sum(candidate.task_weight for candidate in candidates)


def _battery_failure_count(report: ValidationReport) -> int:
    return sum(1 for issue in report.issues if issue.reason == "battery_depletion")


def _removal_count_by_reason(removals: list[RepairRemoval]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for removal in removals:
        counts[removal.reason] = counts.get(removal.reason, 0) + 1
    return dict(sorted(counts.items()))


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
    if vector_cache is None:
        vector_cache = TransitionVectorCache(case, propagation)
    by_satellite: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        if candidate.satellite_id in case.satellites and candidate.task_id in case.tasks:
            by_satellite.setdefault(candidate.satellite_id, []).append(candidate)

    for satellite_id, satellite_candidates in sorted(by_satellite.items()):
        ordered = sorted(
            satellite_candidates,
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
    vector_cache: TransitionVectorCache,
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
    satellite_ids: set[str] | tuple[str, ...] | list[str] | None = None,
) -> tuple[list[ValidationIssue], dict[str, BatteryTrace]]:
    issues: list[ValidationIssue] = []
    traces: dict[str, BatteryTrace] = {}
    if vector_cache is None:
        vector_cache = TransitionVectorCache(case, propagation)
    selected_satellite_ids = (
        set(satellite_ids) if satellite_ids is not None else set(case.satellites)
    )
    by_satellite: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        if (
            candidate.satellite_id in case.satellites
            and candidate.satellite_id in selected_satellite_ids
        ):
            by_satellite.setdefault(candidate.satellite_id, []).append(candidate)

    for satellite_id in sorted(selected_satellite_ids & set(case.satellites)):
        satellite = case.satellites[satellite_id]
        resource = satellite.resource_model
        energy_wh = resource.initial_battery_wh
        min_energy_wh = energy_wh
        min_offset_s = 0.0
        gross_consumption_wh = 0.0
        total_charge_wh = 0.0
        total_imaging_time_s = 0.0
        total_slew_time_s = 0.0
        satellite_candidates = by_satellite.get(satellite_id, [])
        imaging_intervals = [
            (float(candidate.start_offset_s), float(candidate.end_offset_s), candidate.candidate_id)
            for candidate in satellite_candidates
        ]
        slew_intervals, slew_issues = _slew_intervals(
            case,
            satellite_candidates,
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
        traces[satellite_id] = BatteryTrace(
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
    return issues, traces


def _battery_failure_count_for_satellites(
    issues: list[ValidationIssue],
    affected_satellites: set[str],
) -> int:
    return sum(
        1
        for issue in issues
        if issue.reason == "battery_depletion"
        and issue.satellite_id in affected_satellites
    )


def _min_battery_for_satellites(
    traces: dict[str, BatteryTrace],
    affected_satellites: set[str],
) -> float | None:
    values = [
        trace.min_battery_wh
        for satellite_id, trace in traces.items()
        if satellite_id in affected_satellites
    ]
    if not values:
        return None
    return min(values)


def evaluate_battery_guard(
    case: AeosspCase,
    before_candidates: list[Candidate],
    after_candidates: list[Candidate],
    *,
    affected_satellite_ids: set[str] | tuple[str, ...] | list[str],
    config: BatteryGuardConfig,
    propagation: PropagationContext,
    vector_cache: TransitionVectorCache,
) -> BatteryGuardDecision:
    affected_satellites = set(affected_satellite_ids)
    if not config.enable_battery_guardrails or not affected_satellites:
        return BatteryGuardDecision(
            allowed=True,
            affected_satellites=tuple(sorted(affected_satellites)),
            before_min_battery_wh=None,
            after_min_battery_wh=None,
            before_battery_failure_count=0,
            after_battery_failure_count=0,
            reason="disabled" if not config.enable_battery_guardrails else "no_affected_satellites",
        )

    before_issues, before_traces = battery_issues(
        case,
        before_candidates,
        propagation=propagation,
        vector_cache=vector_cache,
        satellite_ids=affected_satellites,
    )
    after_issues, after_traces = battery_issues(
        case,
        after_candidates,
        propagation=propagation,
        vector_cache=vector_cache,
        satellite_ids=affected_satellites,
    )
    before_min = _min_battery_for_satellites(before_traces, affected_satellites)
    after_min = _min_battery_for_satellites(after_traces, affected_satellites)
    before_failure_count = _battery_failure_count_for_satellites(
        before_issues, affected_satellites
    )
    after_failure_count = _battery_failure_count_for_satellites(
        after_issues, affected_satellites
    )

    before_floor = before_min if before_min is not None else float("inf")
    after_floor = after_min if after_min is not None else float("inf")
    worsens_below_floor = (
        after_floor < config.battery_guard_min_wh - NUMERICAL_EPS
        and after_floor < before_floor - NUMERICAL_EPS
    )
    adds_failure = after_failure_count > before_failure_count
    allowed = not (worsens_below_floor or adds_failure)
    return BatteryGuardDecision(
        allowed=allowed,
        affected_satellites=tuple(sorted(affected_satellites)),
        before_min_battery_wh=before_min,
        after_min_battery_wh=after_min,
        before_battery_failure_count=before_failure_count,
        after_battery_failure_count=after_failure_count,
        reason="accepted" if allowed else "battery_worsened",
    )


def candidate_shape_issues(case: AeosspCase, candidates: list[Candidate]) -> list[ValidationIssue]:
    """Check that each selected candidate conforms to case-level constraints."""
    issues: list[ValidationIssue] = []
    for candidate in candidates:
        if candidate.satellite_id not in case.satellites:
            issues.append(
                ValidationIssue(
                    reason="unknown_satellite",
                    message=f"satellite_id {candidate.satellite_id!r} not in case",
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                )
            )
            continue
        if candidate.task_id not in case.tasks:
            issues.append(
                ValidationIssue(
                    reason="unknown_task",
                    message=f"task_id {candidate.task_id!r} not in case",
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                )
            )
            continue

        satellite = case.satellites[candidate.satellite_id]
        task = case.tasks[candidate.task_id]

        if candidate.duration_s != task.required_duration_s:
            issues.append(
                ValidationIssue(
                    reason="duration_mismatch",
                    message=(
                        f"duration {candidate.duration_s}s != required {task.required_duration_s}s"
                    ),
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                    offset_s=candidate.start_offset_s,
                )
            )

        if not _is_aligned(candidate.start_offset_s, case.mission.action_time_step_s):
            issues.append(
                ValidationIssue(
                    reason="grid_misalignment",
                    message=(
                        f"start_offset_s={candidate.start_offset_s} is not aligned to "
                        f"action_time_step_s={case.mission.action_time_step_s}"
                    ),
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                    offset_s=candidate.start_offset_s,
                )
            )

        release_offset_s = (task.release_time - case.mission.horizon_start).total_seconds()
        due_offset_s = (task.due_time - case.mission.horizon_start).total_seconds()
        if candidate.start_offset_s + NUMERICAL_EPS < release_offset_s:
            issues.append(
                ValidationIssue(
                    reason="window_violation",
                    message=(
                        f"start {candidate.start_offset_s}s is before task release "
                        f"{release_offset_s}s"
                    ),
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                    offset_s=candidate.start_offset_s,
                )
            )
        if candidate.end_offset_s > due_offset_s + NUMERICAL_EPS:
            issues.append(
                ValidationIssue(
                    reason="window_violation",
                    message=(
                        f"end {candidate.end_offset_s}s is after task due "
                        f"{due_offset_s}s"
                    ),
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                    offset_s=candidate.end_offset_s,
                )
            )

        if task.required_sensor_type != satellite.sensor_type:
            issues.append(
                ValidationIssue(
                    reason="sensor_mismatch",
                    message=(
                        f"task sensor {task.required_sensor_type!r} != "
                        f"satellite sensor {satellite.sensor_type!r}"
                    ),
                    candidate_ids=(candidate.candidate_id,),
                    satellite_id=candidate.satellite_id,
                    task_id=candidate.task_id,
                )
            )

    return issues


def validate_schedule(
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
    issues.extend(candidate_shape_issues(case, stable_candidates))
    issues.extend(duplicate_task_issues(stable_candidates))

    if propagation is None:
        step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
        propagation = PropagationContext(case.satellites, step_s=step_s)
    if vector_cache is None:
        vector_cache = TransitionVectorCache(case, propagation)
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


def _candidate_priority(candidate: Candidate) -> tuple[Any, ...]:
    """Lower priority = more likely to be removed."""
    return (candidate.utility, candidate.utility_tie_break)


def _choose_removal(
    issue: ValidationIssue,
    candidates: list[Candidate],
) -> Candidate | None:
    if issue.reason == "battery_depletion":
        if issue.satellite_id is None:
            return None
        # Remove lowest-utility candidate on the failing satellite that starts
        # at or before the depletion point.
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
        return min(same_satellite, key=_candidate_priority)

    # For non-battery issues, remove the lowest-utility implicated candidate.
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    implicated = [
        candidate_by_id[candidate_id]
        for candidate_id in issue.candidate_ids
        if candidate_id in candidate_by_id
    ]
    if not implicated:
        return None
    return min(implicated, key=_candidate_priority)


def repair_schedule(
    case: AeosspCase,
    candidates: list[Candidate],
    *,
    config: RepairConfig | None = None,
    propagation: PropagationContext | None = None,
    vector_cache: TransitionVectorCache | None = None,
) -> RepairResult:
    config = config or RepairConfig()
    current = sorted(
        candidates,
        key=lambda item: (item.start_offset_s, item.satellite_id, item.task_id, item.candidate_id),
    )
    reports: list[ValidationReport] = []
    removals: list[RepairRemoval] = []
    terminated_reason = "max_iterations"

    for iteration in range(config.max_repair_iterations + 1):
        report = validate_schedule(
            case,
            current,
            propagation=propagation,
            vector_cache=vector_cache,
        )
        reports.append(report)
        if report.valid:
            terminated_reason = "valid"
            break
        if iteration >= config.max_repair_iterations:
            break
        removal = None
        for issue in report.issues:
            removal = _choose_removal(issue, current)
            if removal is not None:
                break
        if removal is None:
            terminated_reason = "no_removal_candidate"
            break
        current = [
            candidate for candidate in current if candidate.candidate_id != removal.candidate_id
        ]
        removals.append(
            RepairRemoval(
                iteration=iteration,
                candidate_id=removal.candidate_id,
                reason=issue.reason,
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
    )
