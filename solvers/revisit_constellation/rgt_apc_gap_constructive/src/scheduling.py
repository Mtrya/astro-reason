"""Constructive freshness-aware observation scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
import math

import brahe
import numpy as np

from .case_io import RevisitCase, Target
from .gaps import GapImprovement, GapScore, gap_improvement, score_observation_timelines
from .orbit_library import OrbitCandidate
from .propagation import PropagationCache, datetime_to_epoch
from .time_grid import iso_z
from .visibility import VisibilityWindow, _geometry_sample, angle_between_deg


NUMERICAL_EPS = 1.0e-9


@dataclass(frozen=True, slots=True)
class SchedulingConfig:
    max_actions: int | None = None
    max_actions_per_target: int | None = None
    observation_margin_sec: float = 0.0
    transition_gap_sec: float | None = None
    require_positive_gap_improvement: bool = True
    enforce_simple_energy_budget: bool = True
    enable_repair: bool = True
    repair_max_iterations: int = 3

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "SchedulingConfig":
        raw = payload.get("scheduling", payload)
        if not isinstance(raw, dict):
            raise ValueError("scheduling config must be a mapping/object")
        max_actions = raw.get("max_actions")
        max_actions_per_target = raw.get("max_actions_per_target")
        transition_gap_sec = raw.get("transition_gap_sec")
        return cls(
            max_actions=(None if max_actions is None else int(max_actions)),
            max_actions_per_target=(
                None if max_actions_per_target is None else int(max_actions_per_target)
            ),
            observation_margin_sec=float(raw.get("observation_margin_sec", 0.0)),
            transition_gap_sec=(
                None if transition_gap_sec is None else float(transition_gap_sec)
            ),
            require_positive_gap_improvement=bool(
                raw.get("require_positive_gap_improvement", True)
            ),
            enforce_simple_energy_budget=bool(raw.get("enforce_simple_energy_budget", True)),
            enable_repair=bool(raw.get("enable_repair", True)),
            repair_max_iterations=int(raw.get("repair_max_iterations", 3)),
        )

    def selected_action_limit(self, option_count: int) -> int:
        configured = option_count if self.max_actions is None else self.max_actions
        return max(0, min(configured, option_count))

    def transition_gap_for_case(self, case: RevisitCase) -> float:
        if self.transition_gap_sec is not None:
            return max(0.0, self.transition_gap_sec)
        sensor = case.satellite_model.sensor
        attitude = case.satellite_model.attitude_model
        conservative_angle_deg = min(180.0, 2.0 * sensor.max_off_nadir_angle_deg)
        return _slew_time_sec(conservative_angle_deg, attitude) + attitude.settling_time_sec

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "max_actions": self.max_actions,
            "max_actions_per_target": self.max_actions_per_target,
            "observation_margin_sec": self.observation_margin_sec,
            "transition_gap_sec": self.transition_gap_sec,
            "require_positive_gap_improvement": self.require_positive_gap_improvement,
            "enforce_simple_energy_budget": self.enforce_simple_energy_budget,
            "enable_repair": self.enable_repair,
            "repair_max_iterations": self.repair_max_iterations,
        }


@dataclass(frozen=True, slots=True)
class ObservationOption:
    option_id: str
    window_id: str
    satellite_id: str
    target_id: str
    start: datetime
    end: datetime
    midpoint: datetime
    quality_score: float
    window: VisibilityWindow

    def as_dict(self) -> dict[str, Any]:
        return {
            "option_id": self.option_id,
            "window_id": self.window_id,
            "satellite_id": self.satellite_id,
            "target_id": self.target_id,
            "start": iso_z(self.start),
            "end": iso_z(self.end),
            "midpoint": iso_z(self.midpoint),
            "quality_score": self.quality_score,
        }


@dataclass(frozen=True, slots=True)
class ScheduledObservation:
    option_id: str
    window_id: str
    satellite_id: str
    target_id: str
    start: datetime
    end: datetime
    midpoint: datetime
    quality_score: float

    def as_action_dict(self) -> dict[str, str]:
        return {
            "action_type": "observation",
            "satellite_id": self.satellite_id,
            "target_id": self.target_id,
            "start": iso_z(self.start),
            "end": iso_z(self.end),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "option_id": self.option_id,
            "window_id": self.window_id,
            "satellite_id": self.satellite_id,
            "target_id": self.target_id,
            "start": iso_z(self.start),
            "end": iso_z(self.end),
            "midpoint": iso_z(self.midpoint),
            "quality_score": self.quality_score,
        }


@dataclass(frozen=True, slots=True)
class SchedulingDecision:
    round_index: int
    selected_option: ScheduledObservation
    target_freshness_hours: float
    target_flexibility: int
    opportunity_cost: float
    score_before: GapScore
    score_after: GapScore
    improvement: GapImprovement

    def as_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "selected_option": self.selected_option.as_dict(),
            "target_freshness_hours": self.target_freshness_hours,
            "target_flexibility": self.target_flexibility,
            "opportunity_cost": self.opportunity_cost,
            "score_before": self.score_before.as_dict(),
            "score_after": self.score_after.as_dict(),
            "improvement": self.improvement.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class SchedulingResult:
    actions: list[dict[str, str]]
    scheduled_observations: list[ScheduledObservation]
    initial_score: GapScore
    final_score: GapScore
    decisions: list[SchedulingDecision]
    rejected_options: list[dict[str, Any]]
    validation_report: "LocalValidationReport"
    repair_steps: list["RepairStep"]
    caps: dict[str, Any]

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "action_count": len(self.actions),
            "initial_score": self.initial_score.as_dict(),
            "final_score": self.final_score.as_dict(),
            "decision_count": len(self.decisions),
            "rejected_option_count": len(self.rejected_options),
            "validation": self.validation_report.as_dict(),
            "repair_step_count": len(self.repair_steps),
            "caps": self.caps,
        }


@dataclass(frozen=True, slots=True)
class LocalValidationIssue:
    reason: str
    message: str
    satellite_id: str | None = None
    target_id: str | None = None
    option_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "message": self.message,
            "satellite_id": self.satellite_id,
            "target_id": self.target_id,
            "option_ids": list(self.option_ids),
        }


@dataclass(frozen=True, slots=True)
class LocalValidationReport:
    is_valid: bool
    issues: list[LocalValidationIssue]
    score: GapScore
    high_gap_target_ids: list[str]
    battery_risk_by_satellite: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "issue_count": len(self.issues),
            "issues": [issue.as_dict() for issue in self.issues],
            "score": self.score.as_dict(),
            "high_gap_target_ids": self.high_gap_target_ids,
            "battery_risk_by_satellite": self.battery_risk_by_satellite,
        }


@dataclass(frozen=True, slots=True)
class RepairStep:
    action: str
    reason: str
    score_before: GapScore
    score_after: GapScore
    removed_observation: ScheduledObservation | None = None
    inserted_observation: ScheduledObservation | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "score_before": self.score_before.as_dict(),
            "score_after": self.score_after.as_dict(),
            "removed_observation": (
                None
                if self.removed_observation is None
                else self.removed_observation.as_dict()
            ),
            "inserted_observation": (
                None
                if self.inserted_observation is None
                else self.inserted_observation.as_dict()
            ),
        }


def _slew_time_sec(angle_deg: float, attitude_model: Any) -> float:
    angle_deg = max(0.0, angle_deg)
    if angle_deg <= NUMERICAL_EPS:
        return 0.0
    max_velocity = attitude_model.max_slew_velocity_deg_per_sec
    max_accel = attitude_model.max_slew_acceleration_deg_per_sec2
    if max_velocity <= 0.0 or max_accel <= 0.0:
        return math.inf
    ramp_time = max_velocity / max_accel
    triangular_threshold = (max_velocity * max_velocity) / max_accel
    if angle_deg <= triangular_threshold:
        return 2.0 * math.sqrt(angle_deg / max_accel)
    cruise_angle = angle_deg - triangular_threshold
    return (2.0 * ramp_time) + (cruise_angle / max_velocity)


def _option_interval(
    horizon_start: datetime,
    window: VisibilityWindow,
    target: Target,
    margin_sec: float,
) -> tuple[datetime, datetime] | None:
    available_start = window.start + timedelta(seconds=margin_sec)
    available_end = window.end - timedelta(seconds=margin_sec)
    duration = timedelta(seconds=target.min_duration_sec)
    if available_end - available_start + timedelta(seconds=NUMERICAL_EPS) < duration:
        return None
    if window.samples:
        best_sample = min(
            window.samples,
            key=lambda sample: (
                sample.off_nadir_deg,
                sample.slant_range_m,
                -sample.elevation_deg,
                sample.offset_sec,
            ),
        )
        anchor = horizon_start + timedelta(seconds=best_sample.offset_sec)
    else:
        anchor = window.midpoint
    start = anchor - (duration / 2)
    end = start + duration
    if start < available_start:
        start = available_start
        end = start + duration
    if end > available_end:
        end = available_end
        start = end - duration
    if start < window.start or end > window.end or end <= start:
        return None
    return start, end


def _action_sample_times(start: datetime, end: datetime, step_sec: float = 10.0) -> list[datetime]:
    if end <= start:
        return [start]
    points = [start]
    current = start
    delta = timedelta(seconds=step_sec)
    while current + delta < end:
        current = current + delta
        points.append(current)
    return points


def _geometry_interval_visible(
    *,
    case: RevisitCase,
    option: ObservationOption,
    propagation: PropagationCache,
) -> bool:
    target = case.targets[option.target_id]
    return all(
        _geometry_sample(
            case=case,
            target=target,
            propagation=propagation,
            candidate_id=option.satellite_id,
            instant=instant,
        ).visible
        for instant in _action_sample_times(option.start, option.end)
    )


def _target_vector_eci(
    *,
    case: RevisitCase,
    observation: ObservationOption | ScheduledObservation,
    propagation: PropagationCache,
) -> np.ndarray:
    epoch = datetime_to_epoch(observation.midpoint)
    satellite_state_eci = propagation.state_eci(observation.satellite_id, observation.midpoint)
    target = case.targets[observation.target_id]
    target_eci = np.asarray(
        brahe.position_ecef_to_eci(epoch, target.ecef_position_m),
        dtype=float,
    )
    return target_eci - satellite_state_eci[:3]


def _required_transition_gap_sec(
    *,
    case: RevisitCase,
    previous: ObservationOption | ScheduledObservation,
    current: ObservationOption | ScheduledObservation,
    propagation: PropagationCache | None,
    fallback_transition_gap_sec: float,
) -> float:
    if propagation is None:
        return fallback_transition_gap_sec
    previous_vector = _target_vector_eci(
        case=case,
        observation=previous,
        propagation=propagation,
    )
    current_vector = _target_vector_eci(
        case=case,
        observation=current,
        propagation=propagation,
    )
    slew_angle_deg = angle_between_deg(previous_vector, current_vector)
    return (
        _slew_time_sec(slew_angle_deg, case.satellite_model.attitude_model)
        + case.satellite_model.attitude_model.settling_time_sec
    )


def _quality_score(window: VisibilityWindow) -> float:
    off_nadir_quality = 1.0 / (1.0 + max(0.0, window.min_off_nadir_deg))
    range_quality = 1.0 / (1.0 + (max(0.0, window.min_slant_range_m) / 1.0e7))
    elevation_quality = 1.0 + (max(0.0, window.max_elevation_deg) / 180.0)
    return off_nadir_quality * range_quality * elevation_quality


def build_observation_options(
    *,
    case: RevisitCase,
    selected_candidate_ids: set[str],
    selected_candidates: list[OrbitCandidate] | None,
    windows: list[VisibilityWindow],
    config: SchedulingConfig,
) -> tuple[list[ObservationOption], list[dict[str, Any]]]:
    options: list[ObservationOption] = []
    rejected: list[dict[str, Any]] = []
    propagation = (
        None
        if selected_candidates is None
        else PropagationCache(selected_candidates, case.horizon_start, case.horizon_end)
    )
    for window in windows:
        if window.candidate_id not in selected_candidate_ids:
            continue
        target = case.targets[window.target_id]
        interval = _option_interval(
            case.horizon_start,
            window,
            target,
            config.observation_margin_sec,
        )
        if interval is None:
            rejected.append(
                {
                    "window_id": window.window_id,
                    "satellite_id": window.candidate_id,
                    "target_id": window.target_id,
                    "reason": "window_shorter_than_required_observation_duration",
                }
            )
            continue
        start, end = interval
        option = ObservationOption(
            option_id=window.window_id,
            window_id=window.window_id,
            satellite_id=window.candidate_id,
            target_id=window.target_id,
            start=start,
            end=end,
            midpoint=start + ((end - start) / 2),
            quality_score=_quality_score(window),
            window=window,
        )
        if propagation is not None and not _geometry_interval_visible(
            case=case,
            option=option,
            propagation=propagation,
        ):
            rejected.append(
                {
                    **option.as_dict(),
                    "reason": "geometry_infeasible_at_10s_samples",
                }
            )
            continue
        options.append(option)
    options.sort(
        key=lambda option: (
            option.start,
            option.satellite_id,
            option.target_id,
            option.window_id,
        )
    )
    return options, rejected


def _timelines_from_schedule(
    scheduled: list[ScheduledObservation],
) -> dict[str, list[datetime]]:
    timelines: dict[str, list[datetime]] = {}
    for observation in scheduled:
        timelines.setdefault(observation.target_id, []).append(observation.midpoint)
    return timelines


def _target_counts(scheduled: list[ScheduledObservation]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for observation in scheduled:
        counts[observation.target_id] = counts.get(observation.target_id, 0) + 1
    return counts


def _intervals_conflict(
    left: ObservationOption | ScheduledObservation,
    right: ObservationOption | ScheduledObservation,
    transition_gap_sec: float,
) -> bool:
    if left.satellite_id != right.satellite_id:
        return False
    transition_gap = timedelta(seconds=transition_gap_sec)
    if left.end <= right.start:
        return left.end + transition_gap > right.start
    if right.end <= left.start:
        return right.end + transition_gap > left.start
    return True


def _timing_conflict_issue(
    *,
    case: RevisitCase,
    left: ObservationOption | ScheduledObservation,
    right: ObservationOption | ScheduledObservation,
    propagation: PropagationCache | None,
    fallback_transition_gap_sec: float,
) -> LocalValidationIssue | None:
    if left.satellite_id != right.satellite_id:
        return None
    previous, current = (left, right) if left.start <= right.start else (right, left)
    if previous.end > current.start:
        return LocalValidationIssue(
            reason="overlap",
            message="same-satellite observations overlap",
            satellite_id=previous.satellite_id,
            option_ids=(previous.option_id, current.option_id),
        )
    required_gap_sec = _required_transition_gap_sec(
        case=case,
        previous=previous,
        current=current,
        propagation=propagation,
        fallback_transition_gap_sec=fallback_transition_gap_sec,
    )
    actual_gap_sec = (current.start - previous.end).total_seconds()
    if actual_gap_sec + NUMERICAL_EPS < required_gap_sec:
        return LocalValidationIssue(
            reason="slew_gap",
            message=(
                "same-satellite observations have insufficient slew/settle gap "
                f"available={actual_gap_sec:.3f}s required={required_gap_sec:.3f}s"
            ),
            satellite_id=previous.satellite_id,
            option_ids=(previous.option_id, current.option_id),
        )
    return None


def _simple_energy_feasible(
    *,
    case: RevisitCase,
    candidate: ObservationOption,
    scheduled: list[ScheduledObservation],
    transition_gap_sec: float,
) -> bool:
    resource = case.satellite_model.resource_model
    sensor = case.satellite_model.sensor
    attitude = case.satellite_model.attitude_model
    horizon_hours = case.horizon_duration_sec / 3600.0
    satellite_observations = [
        observation
        for observation in scheduled
        if observation.satellite_id == candidate.satellite_id
    ]
    total_observation_sec = sum(
        (observation.end - observation.start).total_seconds()
        for observation in satellite_observations
    ) + (candidate.end - candidate.start).total_seconds()
    action_count = len(satellite_observations) + 1
    maneuver_sec = max(0, action_count - 1) * transition_gap_sec
    required_wh = (
        resource.idle_discharge_rate_w * horizon_hours
        + sensor.obs_discharge_rate_w * (total_observation_sec / 3600.0)
        + attitude.maneuver_discharge_rate_w * (maneuver_sec / 3600.0)
    )
    return required_wh <= resource.initial_battery_wh + NUMERICAL_EPS


def _simple_energy_margin_wh(
    *,
    case: RevisitCase,
    satellite_id: str,
    scheduled: list[ScheduledObservation],
    transition_gap_sec: float,
) -> float:
    resource = case.satellite_model.resource_model
    sensor = case.satellite_model.sensor
    attitude = case.satellite_model.attitude_model
    horizon_hours = case.horizon_duration_sec / 3600.0
    satellite_observations = [
        observation
        for observation in scheduled
        if observation.satellite_id == satellite_id
    ]
    total_observation_sec = sum(
        (observation.end - observation.start).total_seconds()
        for observation in satellite_observations
    )
    maneuver_sec = max(0, len(satellite_observations) - 1) * transition_gap_sec
    required_wh = (
        resource.idle_discharge_rate_w * horizon_hours
        + sensor.obs_discharge_rate_w * (total_observation_sec / 3600.0)
        + attitude.maneuver_discharge_rate_w * (maneuver_sec / 3600.0)
    )
    return resource.initial_battery_wh - required_wh


def _base_feasible(
    *,
    case: RevisitCase,
    option: ObservationOption,
    scheduled: list[ScheduledObservation],
    config: SchedulingConfig,
    transition_gap_sec: float,
    propagation: PropagationCache | None = None,
) -> tuple[bool, str | None]:
    for observation in scheduled:
        issue = _timing_conflict_issue(
            case=case,
            left=option,
            right=observation,
            propagation=propagation,
            fallback_transition_gap_sec=transition_gap_sec,
        )
        if issue is not None:
            return False, issue.reason
    target_counts = _target_counts(scheduled)
    if (
        config.max_actions_per_target is not None
        and target_counts.get(option.target_id, 0) >= config.max_actions_per_target
    ):
        return False, "target_action_cap_reached"
    if config.enforce_simple_energy_budget and not _simple_energy_feasible(
        case=case,
        candidate=option,
        scheduled=scheduled,
        transition_gap_sec=transition_gap_sec,
    ):
        return False, "simple_energy_budget_exceeded"
    return True, None


def _score_with_option(
    case: RevisitCase,
    scheduled: list[ScheduledObservation],
    option: ObservationOption,
) -> tuple[GapScore, GapImprovement]:
    before = score_observation_timelines(case, _timelines_from_schedule(scheduled))
    after_timelines = _timelines_from_schedule(
        [
            *scheduled,
            ScheduledObservation(
                option_id=option.option_id,
                window_id=option.window_id,
                satellite_id=option.satellite_id,
                target_id=option.target_id,
                start=option.start,
                end=option.end,
                midpoint=option.midpoint,
                quality_score=option.quality_score,
            ),
        ]
    )
    after = score_observation_timelines(case, after_timelines)
    return after, gap_improvement(before, after)


def _option_profit(
    option: ObservationOption,
    score: GapScore,
    horizon_hours: float,
) -> float:
    target_score = score.target_gap_summary[option.target_id]
    freshness = target_score.max_revisit_gap_hours / max(horizon_hours, NUMERICAL_EPS)
    return option.quality_score * freshness


def _opportunity_cost(
    *,
    option: ObservationOption,
    remaining_options: list[ObservationOption],
    score: GapScore,
    horizon_hours: float,
    transition_gap_sec: float,
) -> float:
    cost = 0.0
    for other in remaining_options:
        if other.option_id == option.option_id:
            continue
        if _intervals_conflict(option, other, transition_gap_sec):
            cost += _option_profit(other, score, horizon_hours)
    return cost


def _as_scheduled(option: ObservationOption) -> ScheduledObservation:
    return ScheduledObservation(
        option_id=option.option_id,
        window_id=option.window_id,
        satellite_id=option.satellite_id,
        target_id=option.target_id,
        start=option.start,
        end=option.end,
        midpoint=option.midpoint,
        quality_score=option.quality_score,
    )


def validate_schedule_local(
    *,
    case: RevisitCase,
    scheduled: list[ScheduledObservation],
    selected_candidate_ids: list[str],
    transition_gap_sec: float,
    propagation: PropagationCache | None = None,
    check_geometry: bool = True,
) -> LocalValidationReport:
    issues: list[LocalValidationIssue] = []
    selected_id_set = set(selected_candidate_ids)

    for observation in scheduled:
        if observation.satellite_id not in selected_id_set:
            issues.append(
                LocalValidationIssue(
                    reason="unknown_satellite",
                    message="observation references a satellite not selected by the solver",
                    satellite_id=observation.satellite_id,
                    target_id=observation.target_id,
                    option_ids=(observation.option_id,),
                )
            )
        if observation.target_id not in case.targets:
            issues.append(
                LocalValidationIssue(
                    reason="unknown_target",
                    message="observation references an unknown target",
                    satellite_id=observation.satellite_id,
                    target_id=observation.target_id,
                    option_ids=(observation.option_id,),
                )
            )
            continue
        target = case.targets[observation.target_id]
        duration_sec = (observation.end - observation.start).total_seconds()
        if observation.end <= observation.start:
            issues.append(
                LocalValidationIssue(
                    reason="timing",
                    message="observation end must be after start",
                    satellite_id=observation.satellite_id,
                    target_id=observation.target_id,
                    option_ids=(observation.option_id,),
                )
            )
        if duration_sec + NUMERICAL_EPS < target.min_duration_sec:
            issues.append(
                LocalValidationIssue(
                    reason="duration",
                    message=(
                        "observation is shorter than target minimum duration "
                        f"duration={duration_sec:.3f}s required={target.min_duration_sec:.3f}s"
                    ),
                    satellite_id=observation.satellite_id,
                    target_id=observation.target_id,
                    option_ids=(observation.option_id,),
                )
            )
        if (
            check_geometry
            and propagation is not None
            and not _geometry_interval_visible(
                case=case,
                option=ObservationOption(
                    option_id=observation.option_id,
                    window_id=observation.window_id,
                    satellite_id=observation.satellite_id,
                    target_id=observation.target_id,
                    start=observation.start,
                    end=observation.end,
                    midpoint=observation.midpoint,
                    quality_score=observation.quality_score,
                    window=VisibilityWindow(
                        window_id=observation.window_id,
                        candidate_id=observation.satellite_id,
                        target_id=observation.target_id,
                        start=observation.start,
                        end=observation.end,
                        midpoint=observation.midpoint,
                        duration_sec=duration_sec,
                        max_elevation_deg=0.0,
                        min_slant_range_m=0.0,
                        min_off_nadir_deg=0.0,
                        sample_count=0,
                        samples=(),
                    ),
                ),
                propagation=propagation,
            )
        ):
            issues.append(
                LocalValidationIssue(
                    reason="geometry",
                    message="observation is not visible at all 10-second local samples",
                    satellite_id=observation.satellite_id,
                    target_id=observation.target_id,
                    option_ids=(observation.option_id,),
                )
            )

    for satellite_id in sorted({observation.satellite_id for observation in scheduled}):
        satellite_observations = sorted(
            [
                observation
                for observation in scheduled
                if observation.satellite_id == satellite_id
            ],
            key=lambda item: (item.start, item.end, item.target_id, item.option_id),
        )
        for previous, current in zip(satellite_observations, satellite_observations[1:]):
            issue = _timing_conflict_issue(
                case=case,
                left=previous,
                right=current,
                propagation=propagation,
                fallback_transition_gap_sec=transition_gap_sec,
            )
            if issue is not None:
                issues.append(issue)

    battery_risk_by_satellite = {
        satellite_id: margin
        for satellite_id in sorted({*selected_id_set, *(item.satellite_id for item in scheduled)})
        if (
            margin := _simple_energy_margin_wh(
                case=case,
                satellite_id=satellite_id,
                scheduled=scheduled,
                transition_gap_sec=transition_gap_sec,
            )
        )
        < -NUMERICAL_EPS
    }
    for satellite_id, margin in battery_risk_by_satellite.items():
        issues.append(
            LocalValidationIssue(
                reason="battery_risk",
                message=f"simple energy budget is negative by {-margin:.3f} Wh",
                satellite_id=satellite_id,
            )
        )

    score = score_observation_timelines(case, _timelines_from_schedule(scheduled))
    high_gap_target_ids = [
        target_id
        for target_id, target_score in sorted(score.target_gap_summary.items())
        if target_score.max_revisit_gap_hours
        > target_score.expected_revisit_period_hours + NUMERICAL_EPS
    ]
    hard_issue_reasons = {
        "unknown_satellite",
        "unknown_target",
        "timing",
        "duration",
        "geometry",
        "overlap",
        "slew_gap",
        "battery_risk",
    }
    return LocalValidationReport(
        is_valid=not any(issue.reason in hard_issue_reasons for issue in issues),
        issues=issues,
        score=score,
        high_gap_target_ids=high_gap_target_ids,
        battery_risk_by_satellite=battery_risk_by_satellite,
    )


def _removal_key(
    case: RevisitCase,
    scheduled: list[ScheduledObservation],
    observation: ScheduledObservation,
) -> tuple[int, float, float, datetime, str, str, str]:
    before = score_observation_timelines(case, _timelines_from_schedule(scheduled))
    after = score_observation_timelines(
        case,
        _timelines_from_schedule([item for item in scheduled if item is not observation]),
    )
    damage = gap_improvement(after, before)
    return (
        damage.threshold_violation_reduction,
        damage.capped_max_revisit_gap_reduction_hours,
        damage.mean_revisit_gap_reduction_hours,
        observation.start,
        observation.satellite_id,
        observation.target_id,
        observation.option_id,
    )


def _choose_removal_for_issues(
    case: RevisitCase,
    scheduled: list[ScheduledObservation],
    report: LocalValidationReport,
) -> tuple[ScheduledObservation, str] | None:
    by_option_id = {observation.option_id: observation for observation in scheduled}
    candidates: list[tuple[tuple[int, float, float, datetime, str, str, str], ScheduledObservation, str]] = []
    for issue in report.issues:
        if issue.reason not in {"overlap", "slew_gap", "battery_risk", "geometry", "duration"}:
            continue
        issue_observations = [
            by_option_id[option_id]
            for option_id in issue.option_ids
            if option_id in by_option_id
        ]
        if not issue_observations and issue.satellite_id:
            issue_observations = [
                observation
                for observation in scheduled
                if observation.satellite_id == issue.satellite_id
            ]
        for observation in issue_observations:
            candidates.append(
                (
                    _removal_key(case, scheduled, observation),
                    observation,
                    issue.reason,
                )
            )
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1], candidates[0][2]


def _insert_high_gap_observation(
    *,
    case: RevisitCase,
    scheduled: list[ScheduledObservation],
    options: list[ObservationOption],
    consumed_option_ids: set[str],
    report: LocalValidationReport,
    config: SchedulingConfig,
    transition_gap_sec: float,
    propagation: PropagationCache | None,
) -> tuple[ScheduledObservation, GapScore, GapScore] | None:
    score_before = report.score
    ranked_targets = sorted(
        report.high_gap_target_ids,
        key=lambda target_id: (
            -score_before.target_gap_summary[target_id].max_revisit_gap_hours,
            target_id,
        ),
    )
    for target_id in ranked_targets:
        candidate_options = [
            option
            for option in options
            if option.target_id == target_id and option.option_id not in consumed_option_ids
        ]
        ranked_options: list[
            tuple[tuple[int, float, float, float, datetime, str, str], ObservationOption, GapScore]
        ] = []
        for option in candidate_options:
            feasible, _ = _base_feasible(
                case=case,
                option=option,
                scheduled=scheduled,
                config=config,
                transition_gap_sec=transition_gap_sec,
                propagation=propagation,
            )
            if not feasible:
                continue
            inserted = _as_scheduled(option)
            score_after = score_observation_timelines(
                case,
                _timelines_from_schedule([*scheduled, inserted]),
            )
            improvement = gap_improvement(score_before, score_after)
            if not improvement.is_positive:
                continue
            ranked_options.append(
                (
                    (
                        -improvement.threshold_violation_reduction,
                        -improvement.capped_max_revisit_gap_reduction_hours,
                        -improvement.max_revisit_gap_reduction_hours,
                        -improvement.mean_revisit_gap_reduction_hours,
                        option.start,
                        option.satellite_id,
                        option.window_id,
                    ),
                    option,
                    score_after,
                )
            )
        if ranked_options:
            ranked_options.sort(key=lambda item: item[0])
            selected_option = ranked_options[0][1]
            return _as_scheduled(selected_option), score_before, ranked_options[0][2]
    return None


def repair_schedule_deterministic(
    *,
    case: RevisitCase,
    scheduled: list[ScheduledObservation],
    options: list[ObservationOption],
    selected_candidate_ids: list[str],
    config: SchedulingConfig,
    transition_gap_sec: float,
    propagation: PropagationCache | None,
) -> tuple[list[ScheduledObservation], list[RepairStep], LocalValidationReport]:
    repaired = list(scheduled)
    consumed_option_ids = {observation.option_id for observation in repaired}
    repair_steps: list[RepairStep] = []

    for _ in range(max(0, config.repair_max_iterations)):
        report = validate_schedule_local(
            case=case,
            scheduled=repaired,
            selected_candidate_ids=selected_candidate_ids,
            transition_gap_sec=transition_gap_sec,
            propagation=propagation,
        )
        removal = _choose_removal_for_issues(case, repaired, report)
        if removal is not None:
            removed_observation, reason = removal
            score_before = report.score
            repaired = [
                observation
                for observation in repaired
                if observation is not removed_observation
            ]
            score_after = score_observation_timelines(
                case,
                _timelines_from_schedule(repaired),
            )
            repair_steps.append(
                RepairStep(
                    action="remove",
                    reason=reason,
                    score_before=score_before,
                    score_after=score_after,
                    removed_observation=removed_observation,
                )
            )
            continue

        if len(repaired) >= config.selected_action_limit(len(options)):
            return repaired, repair_steps, report
        insertion = _insert_high_gap_observation(
            case=case,
            scheduled=repaired,
            options=options,
            consumed_option_ids=consumed_option_ids,
            report=report,
            config=config,
            transition_gap_sec=transition_gap_sec,
            propagation=propagation,
        )
        if insertion is None:
            return repaired, repair_steps, report
        inserted_observation, score_before, score_after = insertion
        repaired.append(inserted_observation)
        repaired.sort(key=lambda item: (item.start, item.satellite_id, item.target_id))
        consumed_option_ids.add(inserted_observation.option_id)
        repair_steps.append(
            RepairStep(
                action="insert",
                reason="high_gap_target",
                score_before=score_before,
                score_after=score_after,
                inserted_observation=inserted_observation,
            )
        )

    final_report = validate_schedule_local(
        case=case,
        scheduled=repaired,
        selected_candidate_ids=selected_candidate_ids,
        transition_gap_sec=transition_gap_sec,
        propagation=propagation,
    )
    return repaired, repair_steps, final_report


def schedule_observations(
    *,
    case: RevisitCase,
    selected_candidate_ids: list[str],
    selected_candidates: list[OrbitCandidate] | None = None,
    windows: list[VisibilityWindow],
    config: SchedulingConfig,
) -> SchedulingResult:
    options, rejected = build_observation_options(
        case=case,
        selected_candidate_ids=set(selected_candidate_ids),
        selected_candidates=selected_candidates,
        windows=windows,
        config=config,
    )
    propagation = (
        None
        if selected_candidates is None
        else PropagationCache(selected_candidates, case.horizon_start, case.horizon_end)
    )
    transition_gap_sec = config.transition_gap_for_case(case)
    action_limit = config.selected_action_limit(len(options))
    scheduled: list[ScheduledObservation] = []
    consumed_option_ids: set[str] = set()
    decisions: list[SchedulingDecision] = []
    initial_score = score_observation_timelines(case, {})
    horizon_hours = case.horizon_duration_sec / 3600.0

    while len(scheduled) < action_limit:
        current_score = score_observation_timelines(case, _timelines_from_schedule(scheduled))
        remaining_options = [
            option for option in options if option.option_id not in consumed_option_ids
        ]
        feasible_by_target: dict[str, list[ObservationOption]] = {}
        for option in remaining_options:
            feasible, reason = _base_feasible(
                case=case,
                option=option,
                scheduled=scheduled,
                config=config,
                transition_gap_sec=transition_gap_sec,
                propagation=propagation,
            )
            if not feasible:
                rejected.append(
                    {
                        **option.as_dict(),
                        "reason": reason or "infeasible",
                        "round_index": len(decisions),
                    }
                )
                consumed_option_ids.add(option.option_id)
                continue
            _, improvement = _score_with_option(case, scheduled, option)
            if config.require_positive_gap_improvement and not improvement.is_positive:
                rejected.append(
                    {
                        **option.as_dict(),
                        "reason": "non_positive_gap_improvement",
                        "round_index": len(decisions),
                    }
                )
                consumed_option_ids.add(option.option_id)
                continue
            feasible_by_target.setdefault(option.target_id, []).append(option)

        if not feasible_by_target:
            break

        target_id = min(
            feasible_by_target,
            key=lambda candidate_target: (
                -current_score.target_gap_summary[
                    candidate_target
                ].max_revisit_gap_hours,
                len(feasible_by_target[candidate_target]),
                candidate_target,
            ),
        )
        target_options = feasible_by_target[target_id]
        target_freshness = current_score.target_gap_summary[
            target_id
        ].max_revisit_gap_hours
        target_flexibility = len(target_options)

        ranked_options: list[
            tuple[
                tuple[float, int, float, float, float, datetime, str, str, str],
                ObservationOption,
                GapScore,
                GapImprovement,
                float,
            ]
        ] = []
        for option in target_options:
            after_score, improvement = _score_with_option(case, scheduled, option)
            opportunity_cost = _opportunity_cost(
                option=option,
                remaining_options=remaining_options,
                score=current_score,
                horizon_hours=horizon_hours,
                transition_gap_sec=transition_gap_sec,
            )
            key = (
                opportunity_cost,
                -improvement.threshold_violation_reduction,
                -improvement.capped_max_revisit_gap_reduction_hours,
                -improvement.max_revisit_gap_reduction_hours,
                -improvement.mean_revisit_gap_reduction_hours,
                option.start,
                option.satellite_id,
                option.target_id,
                option.window_id,
            )
            ranked_options.append((key, option, after_score, improvement, opportunity_cost))

        ranked_options.sort(key=lambda item: item[0])
        _, selected_option, after_score, improvement, opportunity_cost = ranked_options[0]
        selected = _as_scheduled(selected_option)
        scheduled.append(selected)
        scheduled.sort(key=lambda item: (item.start, item.satellite_id, item.target_id))
        consumed_option_ids.add(selected_option.option_id)
        decisions.append(
            SchedulingDecision(
                round_index=len(decisions),
                selected_option=selected,
                target_freshness_hours=target_freshness,
                target_flexibility=target_flexibility,
                opportunity_cost=opportunity_cost,
                score_before=current_score,
                score_after=after_score,
                improvement=improvement,
            )
        )

    final_score = score_observation_timelines(case, _timelines_from_schedule(scheduled))
    validation_report = validate_schedule_local(
        case=case,
        scheduled=scheduled,
        selected_candidate_ids=selected_candidate_ids,
        transition_gap_sec=transition_gap_sec,
        propagation=propagation,
    )
    repair_steps: list[RepairStep] = []
    if config.enable_repair:
        scheduled, repair_steps, validation_report = repair_schedule_deterministic(
            case=case,
            scheduled=scheduled,
            options=options,
            selected_candidate_ids=selected_candidate_ids,
            config=config,
            transition_gap_sec=transition_gap_sec,
            propagation=propagation,
        )
        final_score = score_observation_timelines(
            case,
            _timelines_from_schedule(scheduled),
        )
    actions = [
        observation.as_action_dict()
        for observation in sorted(
            scheduled,
            key=lambda item: (item.start, item.satellite_id, item.target_id),
        )
    ]
    return SchedulingResult(
        actions=actions,
        scheduled_observations=scheduled,
        initial_score=initial_score,
        final_score=final_score,
        decisions=decisions,
        rejected_options=rejected,
        validation_report=validation_report,
        repair_steps=repair_steps,
        caps={
            **config.as_status_dict(),
            "action_limit": action_limit,
            "option_count": len(options),
            "selected_candidate_count": len(selected_candidate_ids),
            "transition_gap_sec": transition_gap_sec,
            "stopped_by_action_limit": len(scheduled) >= action_limit,
            "stopped_by_no_eligible_option": len(scheduled) < action_limit,
        },
    )
