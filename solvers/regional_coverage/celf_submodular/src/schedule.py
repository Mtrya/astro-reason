"""Solver-local schedule validation and deterministic repair."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from candidates import StripCandidate
from case_io import RegionalCoverageCase, Satellite


@dataclass(frozen=True, slots=True)
class ScheduleIssue:
    issue_type: str
    candidate_ids: tuple[str, ...]
    satellite_id: str | None
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "issue_type": self.issue_type,
            "candidate_ids": list(self.candidate_ids),
            "satellite_id": self.satellite_id,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    valid: bool
    issue_count: int
    issues: tuple[ScheduleIssue, ...]
    selected_count: int
    per_satellite_counts: dict[str, int]
    min_estimated_battery_wh: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issue_count": self.issue_count,
            "issues": [issue.as_dict() for issue in self.issues],
            "selected_count": self.selected_count,
            "per_satellite_counts": self.per_satellite_counts,
            "min_estimated_battery_wh": self.min_estimated_battery_wh,
        }


@dataclass(frozen=True, slots=True)
class RepairEvent:
    removed_candidate_id: str
    reason: str
    triggering_issue: dict[str, Any]
    estimated_unique_loss: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "removed_candidate_id": self.removed_candidate_id,
            "reason": self.reason,
            "triggering_issue": self.triggering_issue,
            "estimated_unique_loss": self.estimated_unique_loss,
        }


@dataclass(frozen=True, slots=True)
class RepairResult:
    original_candidate_ids: tuple[str, ...]
    repaired_candidate_ids: tuple[str, ...]
    removed_candidate_ids: tuple[str, ...]
    before: ValidationReport
    after: ValidationReport
    repair_log: tuple[RepairEvent, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "original_candidate_ids": list(self.original_candidate_ids),
            "repaired_candidate_ids": list(self.repaired_candidate_ids),
            "removed_candidate_ids": list(self.removed_candidate_ids),
            "before": self.before.as_dict(),
            "after": self.after.as_dict(),
            "repair_log": [event.as_dict() for event in self.repair_log],
        }


def candidate_end_offset_s(candidate: StripCandidate) -> int:
    return candidate.start_offset_s + candidate.duration_s


def slew_time_s(delta_roll_deg: float, satellite: Satellite) -> float:
    delta = abs(delta_roll_deg)
    if delta <= 0.0:
        return 0.0
    omega = satellite.agility.max_roll_rate_deg_per_s
    alpha = satellite.agility.max_roll_acceleration_deg_per_s2
    if omega <= 0.0 or alpha <= 0.0:
        return float("inf")
    d_tri = omega * omega / alpha
    if delta <= d_tri:
        return 2.0 * math.sqrt(delta / alpha)
    return delta / omega + omega / alpha


def required_gap_s(previous: StripCandidate, current: StripCandidate, satellite: Satellite) -> float:
    return (
        slew_time_s(current.roll_deg - previous.roll_deg, satellite)
        + satellite.agility.settling_time_s
    )


def candidate_energy_burden_wh(candidate: StripCandidate, satellite: Satellite) -> float:
    return candidate.duration_s * satellite.power.imaging_power_w / 3600.0


def _tle_mean_motion_rev_per_day(line2: str) -> float | None:
    try:
        return float(line2[52:63])
    except ValueError:
        return None


def _issue_counts(issues: tuple[ScheduleIssue, ...]) -> dict[str, int]:
    return dict(sorted(Counter(issue.issue_type for issue in issues).items()))


def _coverage_loss(
    candidate_id: str,
    active_ids: tuple[str, ...],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
) -> float:
    counts: Counter[int] = Counter()
    for active_id in active_ids:
        for sample_index in coverage_by_candidate.get(active_id, ()):
            counts[sample_index] += 1
    return sum(
        sample_weights[index]
        for index in coverage_by_candidate.get(candidate_id, ())
        if counts[index] == 1
    )


def _removal_key(
    candidate_id: str,
    active_ids: tuple[str, ...],
    candidates_by_id: dict[str, StripCandidate],
    case: RegionalCoverageCase,
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
) -> tuple[float, float, int, int, str]:
    candidate = candidates_by_id[candidate_id]
    satellite = case.satellites[candidate.satellite_id]
    return (
        _coverage_loss(candidate_id, active_ids, coverage_by_candidate, sample_weights),
        -candidate_energy_burden_wh(candidate, satellite),
        -candidate.duration_s,
        -candidate.start_offset_s,
        candidate.candidate_id,
    )


def _candidate_shape_issues(
    case: RegionalCoverageCase,
    candidate: StripCandidate,
) -> list[ScheduleIssue]:
    issues: list[ScheduleIssue] = []
    satellite = case.satellites.get(candidate.satellite_id)
    if satellite is None:
        return [
            ScheduleIssue(
                "unknown_satellite",
                (candidate.candidate_id,),
                candidate.satellite_id,
                f"{candidate.candidate_id}: unknown satellite_id {candidate.satellite_id}",
            )
        ]
    if candidate.start_offset_s < 0 or candidate.start_offset_s >= case.manifest.horizon_seconds:
        issues.append(
            ScheduleIssue(
                "start_outside_horizon",
                (candidate.candidate_id,),
                candidate.satellite_id,
                f"{candidate.candidate_id}: start offset outside horizon",
            )
        )
    if candidate.start_offset_s % case.manifest.time_step_s != 0:
        issues.append(
            ScheduleIssue(
                "start_grid_misaligned",
                (candidate.candidate_id,),
                candidate.satellite_id,
                f"{candidate.candidate_id}: start offset is not aligned to time_step_s",
            )
        )
    if candidate.duration_s <= 0:
        issues.append(
            ScheduleIssue(
                "nonpositive_duration",
                (candidate.candidate_id,),
                candidate.satellite_id,
                f"{candidate.candidate_id}: duration_s must be positive",
            )
        )
    elif candidate.duration_s % case.manifest.time_step_s != 0:
        issues.append(
            ScheduleIssue(
                "duration_grid_misaligned",
                (candidate.candidate_id,),
                candidate.satellite_id,
                f"{candidate.candidate_id}: duration_s is not a multiple of time_step_s",
            )
        )
    if candidate_end_offset_s(candidate) > case.manifest.horizon_seconds:
        issues.append(
            ScheduleIssue(
                "end_outside_horizon",
                (candidate.candidate_id,),
                candidate.satellite_id,
                f"{candidate.candidate_id}: action end exceeds horizon",
            )
        )
    if candidate.duration_s < satellite.sensor.min_strip_duration_s - 1.0e-6:
        issues.append(
            ScheduleIssue(
                "duration_below_min",
                (candidate.candidate_id,),
                candidate.satellite_id,
                f"{candidate.candidate_id}: duration below min_strip_duration_s",
            )
        )
    if candidate.duration_s > satellite.sensor.max_strip_duration_s + 1.0e-6:
        issues.append(
            ScheduleIssue(
                "duration_above_max",
                (candidate.candidate_id,),
                candidate.satellite_id,
                f"{candidate.candidate_id}: duration above max_strip_duration_s",
            )
        )
    half_fov = 0.5 * satellite.sensor.cross_track_fov_deg
    theta_inner = abs(candidate.roll_deg) - half_fov
    theta_outer = abs(candidate.roll_deg) + half_fov
    if theta_inner < satellite.sensor.min_edge_off_nadir_deg - 1.0e-6:
        issues.append(
            ScheduleIssue(
                "edge_band",
                (candidate.candidate_id,),
                candidate.satellite_id,
                f"{candidate.candidate_id}: inner edge violates sensor off-nadir band",
            )
        )
    if theta_outer > satellite.sensor.max_edge_off_nadir_deg + 1.0e-6:
        issues.append(
            ScheduleIssue(
                "edge_band",
                (candidate.candidate_id,),
                candidate.satellite_id,
                f"{candidate.candidate_id}: outer edge violates sensor off-nadir band",
            )
        )
    return issues


def _by_satellite(
    candidate_ids: tuple[str, ...],
    candidates_by_id: dict[str, StripCandidate],
) -> dict[str, list[StripCandidate]]:
    grouped: dict[str, list[StripCandidate]] = defaultdict(list)
    for candidate_id in candidate_ids:
        candidate = candidates_by_id[candidate_id]
        grouped[candidate.satellite_id].append(candidate)
    for satellite_id in grouped:
        grouped[satellite_id].sort(
            key=lambda c: (c.start_offset_s, candidate_end_offset_s(c), c.candidate_id)
        )
    return dict(sorted(grouped.items()))


def _sequence_issues(
    case: RegionalCoverageCase,
    grouped: dict[str, list[StripCandidate]],
) -> list[ScheduleIssue]:
    issues: list[ScheduleIssue] = []
    for satellite_id, sequence in grouped.items():
        satellite = case.satellites.get(satellite_id)
        if satellite is None:
            continue
        for previous, current in zip(sequence, sequence[1:]):
            previous_end = candidate_end_offset_s(previous)
            if current.start_offset_s < previous_end:
                issues.append(
                    ScheduleIssue(
                        "overlap",
                        (previous.candidate_id, current.candidate_id),
                        satellite_id,
                        (
                            f"{satellite_id}: overlapping strip observations "
                            f"{previous.candidate_id} and {current.candidate_id}"
                        ),
                    )
                )
                continue
            gap_s = current.start_offset_s - previous_end
            required_s = required_gap_s(previous, current, satellite)
            if gap_s + 1.0e-6 < required_s:
                issues.append(
                    ScheduleIssue(
                        "slew_gap",
                        (previous.candidate_id, current.candidate_id),
                        satellite_id,
                        (
                            f"{satellite_id}: insufficient slew/settle time between "
                            f"{previous.candidate_id} and {current.candidate_id}"
                        ),
                    )
                )
    return issues


def _battery_and_duty_issues(
    case: RegionalCoverageCase,
    grouped: dict[str, list[StripCandidate]],
) -> tuple[list[ScheduleIssue], dict[str, float]]:
    issues: list[ScheduleIssue] = []
    min_battery_by_satellite: dict[str, float] = {}
    for satellite_id, sequence in grouped.items():
        satellite = case.satellites[satellite_id]
        battery = satellite.power.initial_battery_wh
        min_battery = battery
        previous: StripCandidate | None = None
        for candidate in sequence:
            if previous is not None:
                slew_s = required_gap_s(previous, candidate, satellite)
                battery -= slew_s * satellite.power.slew_power_w / 3600.0
                min_battery = min(min_battery, battery)
            battery -= candidate.duration_s * satellite.power.imaging_power_w / 3600.0
            min_battery = min(min_battery, battery)
            if battery < -1.0e-9:
                issues.append(
                    ScheduleIssue(
                        "battery_risk",
                        (candidate.candidate_id,),
                        satellite_id,
                        f"{satellite_id}: approximate battery depletes below zero",
                    )
                )
            previous = candidate
        min_battery_by_satellite[satellite_id] = min_battery

        duty_limit = satellite.power.imaging_duty_limit_s_per_orbit
        mean_motion = _tle_mean_motion_rev_per_day(satellite.tle_line2)
        if duty_limit is None or mean_motion is None or mean_motion <= 0.0:
            continue
        orbit_period_s = 86400.0 / mean_motion
        intervals = [
            (candidate.start_offset_s, candidate_end_offset_s(candidate), candidate)
            for candidate in sequence
        ]
        for start_s, end_s, candidate in intervals:
            window_start = end_s - orbit_period_s
            total = 0.0
            for other_start, other_end, _ in intervals:
                total += max(0.0, min(end_s, other_end) - max(window_start, other_start))
            if total > duty_limit + 1.0e-6:
                issues.append(
                    ScheduleIssue(
                        "duty_risk",
                        (candidate.candidate_id,),
                        satellite_id,
                        f"{satellite_id}: approximate imaging duty exceeds per-orbit limit",
                    )
                )
    return issues, min_battery_by_satellite


def validate_schedule(
    case: RegionalCoverageCase,
    candidates_by_id: dict[str, StripCandidate],
    candidate_ids: tuple[str, ...],
) -> ValidationReport:
    issues: list[ScheduleIssue] = []
    if case.manifest.max_actions_total is not None and len(candidate_ids) > case.manifest.max_actions_total:
        issues.append(
            ScheduleIssue(
                "action_cap",
                candidate_ids,
                None,
                f"selected action count exceeds max_actions_total={case.manifest.max_actions_total}",
            )
        )
    seen: set[str] = set()
    for candidate_id in candidate_ids:
        if candidate_id in seen:
            issues.append(
                ScheduleIssue(
                    "duplicate_candidate",
                    (candidate_id,),
                    None,
                    f"{candidate_id}: duplicate selected candidate",
                )
            )
            continue
        seen.add(candidate_id)
        candidate = candidates_by_id.get(candidate_id)
        if candidate is None:
            issues.append(
                ScheduleIssue(
                    "unknown_candidate",
                    (candidate_id,),
                    None,
                    f"{candidate_id}: candidate id is not in generated library",
                )
            )
            continue
        issues.extend(_candidate_shape_issues(case, candidate))
    known_ids = tuple(
        candidate_id for candidate_id in candidate_ids if candidate_id in candidates_by_id
    )
    grouped = _by_satellite(known_ids, candidates_by_id)
    issues.extend(_sequence_issues(case, grouped))
    energy_issues, min_battery = _battery_and_duty_issues(case, grouped)
    issues.extend(energy_issues)
    per_satellite = Counter(
        candidates_by_id[candidate_id].satellite_id
        for candidate_id in known_ids
    )
    return ValidationReport(
        valid=not issues,
        issue_count=len(issues),
        issues=tuple(issues),
        selected_count=len(candidate_ids),
        per_satellite_counts=dict(sorted(per_satellite.items())),
        min_estimated_battery_wh={k: round(v, 6) for k, v in sorted(min_battery.items())},
    )


def repair_schedule(
    case: RegionalCoverageCase,
    candidates_by_id: dict[str, StripCandidate],
    selected_candidate_ids: tuple[str, ...],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
) -> RepairResult:
    active = tuple(dict.fromkeys(selected_candidate_ids))
    before = validate_schedule(case, candidates_by_id, active)
    repair_log: list[RepairEvent] = []
    max_iterations = len(active) + 5
    for _ in range(max_iterations):
        report = validate_schedule(case, candidates_by_id, active)
        if report.valid:
            break
        issue = report.issues[0]
        if issue.issue_type == "action_cap" and case.manifest.max_actions_total is not None:
            candidates = active
        elif issue.issue_type in {"overlap", "slew_gap"}:
            candidates = issue.candidate_ids
        else:
            candidates = issue.candidate_ids or active
        candidates = tuple(candidate_id for candidate_id in candidates if candidate_id in active)
        if not candidates:
            break
        remove_id = min(
            candidates,
            key=lambda cid: _removal_key(
                cid, active, candidates_by_id, case, coverage_by_candidate, sample_weights
            ),
        )
        loss = _coverage_loss(remove_id, active, coverage_by_candidate, sample_weights)
        repair_log.append(
            RepairEvent(
                removed_candidate_id=remove_id,
                reason=issue.issue_type,
                triggering_issue=issue.as_dict(),
                estimated_unique_loss=loss,
            )
        )
        active = tuple(candidate_id for candidate_id in active if candidate_id != remove_id)
    after = validate_schedule(case, candidates_by_id, active)
    removed = tuple(event.removed_candidate_id for event in repair_log)
    return RepairResult(
        original_candidate_ids=tuple(selected_candidate_ids),
        repaired_candidate_ids=active,
        removed_candidate_ids=removed,
        before=before,
        after=after,
        repair_log=tuple(repair_log),
    )


def feasibility_summary(repair_result: RepairResult) -> dict[str, Any]:
    return {
        "before_valid": repair_result.before.valid,
        "after_valid": repair_result.after.valid,
        "before_issue_counts": _issue_counts(repair_result.before.issues),
        "after_issue_counts": _issue_counts(repair_result.after.issues),
        "original_count": len(repair_result.original_candidate_ids),
        "repaired_count": len(repair_result.repaired_candidate_ids),
        "removed_count": len(repair_result.removed_candidate_ids),
    }
