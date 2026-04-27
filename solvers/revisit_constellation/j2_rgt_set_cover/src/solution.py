"""Equal-phase satellite generation and gap-aware action construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
import math

import brahe
import numpy as np

from .case_io import RevisitCase, Target
from .coverage import (
    CoverageSummary,
    VisibilityWindow,
    geometry_sample_from_state,
    group_visible_samples,
)
from .rgt import EARTH_RADIUS_M, MU_EARTH_M3_S2, brouwer_j2_state_eci
from .selection import SelectionSummary, SelectedCandidate
from .time_utils import datetime_to_epoch


NUMERICAL_EPS = 1.0e-9


@dataclass(frozen=True, slots=True)
class SchedulingConfig:
    observation_duration_sec: float = 30.0
    min_gap_improvement_sec: float = 60.0
    validation_sample_step_sec: float = 10.0
    max_actions: int = 3000

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "SchedulingConfig":
        defaults = cls()
        raw = payload.get("scheduling", payload)
        if not isinstance(raw, dict):
            raise ValueError("scheduling config must be a mapping/object")
        return cls(
            observation_duration_sec=float(
                raw.get("observation_duration_sec", defaults.observation_duration_sec)
            ),
            min_gap_improvement_sec=float(
                raw.get("min_gap_improvement_sec", defaults.min_gap_improvement_sec)
            ),
            validation_sample_step_sec=float(
                raw.get("validation_sample_step_sec", defaults.validation_sample_step_sec)
            ),
            max_actions=int(raw.get("max_actions", defaults.max_actions)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_duration_sec": self.observation_duration_sec,
            "min_gap_improvement_sec": self.min_gap_improvement_sec,
            "validation_sample_step_sec": self.validation_sample_step_sec,
            "max_actions": self.max_actions,
        }


@dataclass(frozen=True, slots=True)
class SatellitePlan:
    satellite_id: str
    candidate_id: str
    template_id: str
    phase_index: int
    phase_count: int
    phase_offset_sec: float
    mean_anomaly_deg: float
    state_eci_m_mps: tuple[float, float, float, float, float, float]

    def as_solution_dict(self) -> dict[str, Any]:
        x_m, y_m, z_m, vx_m_s, vy_m_s, vz_m_s = self.state_eci_m_mps
        return {
            "satellite_id": self.satellite_id,
            "x_m": x_m,
            "y_m": y_m,
            "z_m": z_m,
            "vx_m_s": vx_m_s,
            "vy_m_s": vy_m_s,
            "vz_m_s": vz_m_s,
        }

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "satellite_id": self.satellite_id,
            "candidate_id": self.candidate_id,
            "template_id": self.template_id,
            "phase_index": self.phase_index,
            "phase_count": self.phase_count,
            "phase_offset_sec": self.phase_offset_sec,
            "mean_anomaly_deg": self.mean_anomaly_deg,
            "state_eci_m_mps": list(self.state_eci_m_mps),
        }


@dataclass(frozen=True, slots=True)
class ObservationAction:
    action_type: str
    satellite_id: str
    target_id: str
    start: datetime
    end: datetime
    candidate_id: str
    opportunity_midpoint_offset_sec: float

    @property
    def midpoint(self) -> datetime:
        return self.start + ((self.end - self.start) / 2)

    @property
    def duration_sec(self) -> float:
        return (self.end - self.start).total_seconds()

    def as_solution_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "satellite_id": self.satellite_id,
            "target_id": self.target_id,
            "start": isoformat_z(self.start),
            "end": isoformat_z(self.end),
        }

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            **self.as_solution_dict(),
            "candidate_id": self.candidate_id,
            "midpoint": isoformat_z(self.midpoint),
            "duration_sec": self.duration_sec,
            "opportunity_midpoint_offset_sec": self.opportunity_midpoint_offset_sec,
        }


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    is_valid: bool
    errors: list[str]
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass(frozen=True, slots=True)
class SolutionBuildSummary:
    satellites: list[SatellitePlan]
    actions: list[ObservationAction]
    opportunities_considered: int
    opportunities_visibility_valid: int
    target_gap_summary: dict[str, dict[str, float]]
    validation: ValidationSummary
    config: SchedulingConfig

    def solution_json(self) -> dict[str, Any]:
        return {
            "satellites": [
                satellite.as_solution_dict() for satellite in self.satellites
            ],
            "actions": [action.as_solution_dict() for action in self.actions],
        }

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.as_dict(),
            "satellite_count": len(self.satellites),
            "action_count": len(self.actions),
            "opportunities_considered": self.opportunities_considered,
            "opportunities_visibility_valid": self.opportunities_visibility_valid,
            "satellites": [satellite.as_debug_dict() for satellite in self.satellites],
            "actions": [action.as_debug_dict() for action in self.actions],
            "target_gap_summary": self.target_gap_summary,
            "validation": self.validation.as_dict(),
        }

    def as_status_dict(self) -> dict[str, Any]:
        high_gap_targets = [
            target_id
            for target_id, item in sorted(self.target_gap_summary.items())
            if item["max_revisit_gap_hours"]
            > item["expected_revisit_period_hours"] + NUMERICAL_EPS
        ]
        return {
            "satellite_count": len(self.satellites),
            "action_count": len(self.actions),
            "opportunities_considered": self.opportunities_considered,
            "opportunities_visibility_valid": self.opportunities_visibility_valid,
            "local_validation_valid": self.validation.is_valid,
            "local_validation_error_count": len(self.validation.errors),
            "high_gap_target_count": len(high_gap_targets),
            "high_gap_target_ids": high_gap_targets,
            "config": self.config.as_dict(),
        }


def isoformat_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _phase_mean_anomaly(base_deg: float, phase_index: int, phase_count: int) -> float:
    return (base_deg + (360.0 * phase_index / phase_count)) % 360.0


def _candidate_state_with_mean_anomaly(
    selected: SelectedCandidate,
    mean_anomaly_deg: float,
    offset_sec: float,
) -> tuple[float, float, float, float, float, float]:
    candidate = selected.candidate
    return brouwer_j2_state_eci(
        candidate.semi_major_axis_m,
        candidate.inclination_deg,
        eccentricity=candidate.eccentricity,
        raan_deg=candidate.raan_deg,
        argument_of_perigee_deg=candidate.argument_of_perigee_deg,
        mean_anomaly_deg=mean_anomaly_deg,
        duration_sec=offset_sec,
    )


def generate_phased_satellites(selection: SelectionSummary) -> list[SatellitePlan]:
    satellites: list[SatellitePlan] = []
    for candidate_index, selected in enumerate(selection.selected_candidates):
        phase_count = selected.required_satellites
        if phase_count <= 0:
            continue
        for phase_index in range(phase_count):
            mean_anomaly_deg = _phase_mean_anomaly(
                selected.candidate.mean_anomaly_deg,
                phase_index,
                phase_count,
            )
            satellites.append(
                SatellitePlan(
                    satellite_id=f"sat_{candidate_index:03d}_{phase_index:02d}",
                    candidate_id=selected.candidate.candidate_id,
                    template_id=selected.candidate.template_id,
                    phase_index=phase_index,
                    phase_count=phase_count,
                    phase_offset_sec=(
                        selected.candidate.repeat_period_sec
                        * phase_index
                        / phase_count
                    ),
                    mean_anomaly_deg=mean_anomaly_deg,
                    state_eci_m_mps=_candidate_state_with_mean_anomaly(
                        selected,
                        mean_anomaly_deg,
                        0.0,
                    ),
                )
            )
    return satellites


def _sample_offsets(start: datetime, end: datetime, step_sec: float) -> list[float]:
    duration = (end - start).total_seconds()
    if duration <= 0.0:
        return [0.0]
    offsets = [0.0]
    current = 0.0
    while current + step_sec < duration:
        current += step_sec
        offsets.append(current)
    midpoint = duration / 2.0
    if all(abs(offset - midpoint) > NUMERICAL_EPS for offset in offsets):
        offsets.append(midpoint)
    return sorted(offsets)


def satellite_state_at(
    selection: SelectionSummary,
    satellite: SatellitePlan,
    offset_sec: float,
) -> tuple[float, float, float, float, float, float]:
    selected_by_candidate = {
        item.candidate.candidate_id: item for item in selection.selected_candidates
    }
    return _candidate_state_with_mean_anomaly(
        selected_by_candidate[satellite.candidate_id],
        satellite.mean_anomaly_deg,
        offset_sec,
    )


def _action_geometry_valid(
    *,
    case: RevisitCase,
    selection: SelectionSummary,
    satellite: SatellitePlan,
    target: Target,
    start: datetime,
    end: datetime,
    sample_step_sec: float,
) -> bool:
    for sample_offset in _sample_offsets(start, end, sample_step_sec):
        instant = start + timedelta(seconds=sample_offset)
        mission_offset = (instant - case.horizon_start).total_seconds()
        state = satellite_state_at(selection, satellite, mission_offset)
        sample = geometry_sample_from_state(
            case=case,
            target=target,
            state_eci_m_mps=state,
            instant=instant,
            offset_sec=mission_offset,
        )
        if not sample.visible:
            return False
    return True


def _candidate_windows_by_key(
    coverage: CoverageSummary,
) -> dict[tuple[str, str], list[VisibilityWindow]]:
    windows_by_key: dict[tuple[str, str], list[VisibilityWindow]] = {}
    for window in coverage.windows:
        windows_by_key.setdefault((window.candidate_id, window.target_id), []).append(
            window
        )
    for windows in windows_by_key.values():
        windows.sort(key=lambda item: (item.midpoint_offset_sec, item.window_id))
    return windows_by_key


def _assigned_targets_by_candidate(
    selection: SelectionSummary,
) -> dict[str, list[str]]:
    assigned: dict[str, list[str]] = {}
    for target_id, assignment in sorted(selection.target_assignments.items()):
        assigned.setdefault(assignment.candidate_id, []).append(target_id)
    return assigned


def build_opportunities(
    *,
    case: RevisitCase,
    coverage: CoverageSummary,
    selection: SelectionSummary,
    satellites: list[SatellitePlan],
    config: SchedulingConfig,
) -> tuple[list[ObservationAction], int]:
    horizon_sec = (case.horizon_end - case.horizon_start).total_seconds()
    assigned_by_candidate = _assigned_targets_by_candidate(selection)
    satellites_by_candidate: dict[str, list[SatellitePlan]] = {}
    for satellite in satellites:
        satellites_by_candidate.setdefault(satellite.candidate_id, []).append(satellite)

    opportunities: list[ObservationAction] = []
    considered = 0
    sample_step_sec = coverage.config.sample_step_sec
    sample_offsets = []
    current_offset = 0.0
    while current_offset <= horizon_sec + NUMERICAL_EPS:
        sample_offsets.append(min(current_offset, horizon_sec))
        current_offset += sample_step_sec
    if sample_offsets[-1] < horizon_sec:
        sample_offsets.append(horizon_sec)

    for candidate_id, target_ids in sorted(assigned_by_candidate.items()):
        for target_id in target_ids:
            target = case.targets[target_id]
            for satellite in satellites_by_candidate.get(candidate_id, []):
                samples = []
                for offset in sample_offsets:
                    instant = case.horizon_start + timedelta(seconds=offset)
                    state = satellite_state_at(selection, satellite, offset)
                    samples.append(
                        geometry_sample_from_state(
                            case=case,
                            target=target,
                            state_eci_m_mps=state,
                            instant=instant,
                            offset_sec=offset,
                        )
                    )
                windows = group_visible_samples(
                    candidate_id=satellite.satellite_id,
                    template_id=satellite.template_id,
                    target_id=target_id,
                    repeat_period_sec=horizon_sec,
                    sample_step_sec=sample_step_sec,
                    min_duration_sec=target.min_duration_sec,
                    samples=samples,
                    keep_samples_per_window=0,
                )
                for window in windows:
                    duration_sec = min(
                        window.duration_sec,
                        max(target.min_duration_sec, config.observation_duration_sec),
                    )
                    if duration_sec + NUMERICAL_EPS < target.min_duration_sec:
                        continue
                    best_sample = max(
                        window.samples,
                        key=lambda sample: (
                            sample.elevation_deg,
                            -sample.slant_range_m,
                            -sample.off_nadir_deg,
                        ),
                    )
                    midpoint_offset = best_sample.offset_sec
                    midpoint = case.horizon_start + timedelta(seconds=midpoint_offset)
                    start = midpoint - timedelta(seconds=duration_sec / 2.0)
                    end = midpoint + timedelta(seconds=duration_sec / 2.0)
                    considered += 1
                    if start < case.horizon_start or end > case.horizon_end:
                        continue
                    if _action_geometry_valid(
                        case=case,
                        selection=selection,
                        satellite=satellite,
                        target=target,
                        start=start,
                        end=end,
                        sample_step_sec=config.validation_sample_step_sec,
                    ):
                        opportunities.append(
                            ObservationAction(
                                action_type="observation",
                                satellite_id=satellite.satellite_id,
                                target_id=target_id,
                                start=start,
                                end=end,
                                candidate_id=candidate_id,
                                opportunity_midpoint_offset_sec=midpoint_offset,
                            )
                        )
    return (
        sorted(
            opportunities,
            key=lambda item: (
                item.midpoint,
                item.target_id,
                item.satellite_id,
                item.candidate_id,
            ),
        ),
        considered,
    )


def _max_gap_sec(case: RevisitCase, target_id: str, midpoints: list[datetime]) -> float:
    times = [case.horizon_start, *sorted(set(midpoints)), case.horizon_end]
    return max((right - left).total_seconds() for left, right in zip(times, times[1:]))


def _target_vector_eci(
    case: RevisitCase,
    selection: SelectionSummary,
    satellite: SatellitePlan,
    target_id: str,
    instant: datetime,
) -> np.ndarray:
    mission_offset = (instant - case.horizon_start).total_seconds()
    state = np.asarray(satellite_state_at(selection, satellite, mission_offset))
    target_eci = np.asarray(
        brahe.position_ecef_to_eci(
            datetime_to_epoch(instant),
            np.asarray(case.targets[target_id].ecef_position_m, dtype=float),
        ),
        dtype=float,
    )
    return target_eci - state[:3]


def _angle_between_deg(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    norm_a = float(np.linalg.norm(vector_a))
    norm_b = float(np.linalg.norm(vector_b))
    if norm_a <= NUMERICAL_EPS or norm_b <= NUMERICAL_EPS:
        return 0.0
    cosine = float(np.dot(vector_a, vector_b) / (norm_a * norm_b))
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _slew_time_sec(case: RevisitCase, angle_deg: float) -> float:
    attitude = case.satellite_model.attitude_model
    max_velocity = attitude.max_slew_velocity_deg_per_sec
    max_accel = attitude.max_slew_acceleration_deg_per_sec2
    if angle_deg <= NUMERICAL_EPS:
        return 0.0
    ramp_time = max_velocity / max_accel
    triangular_threshold = (max_velocity * max_velocity) / max_accel
    if angle_deg <= triangular_threshold:
        return 2.0 * math.sqrt(angle_deg / max_accel)
    cruise_angle = angle_deg - triangular_threshold
    return (2.0 * ramp_time) + (cruise_angle / max_velocity)


def _compatible_with_selected(
    *,
    case: RevisitCase,
    selection: SelectionSummary,
    satellites_by_id: dict[str, SatellitePlan],
    action: ObservationAction,
    selected: list[ObservationAction],
) -> bool:
    satellite = satellites_by_id[action.satellite_id]
    for existing in selected:
        if existing.satellite_id != action.satellite_id:
            continue
        if action.start < existing.end and action.end > existing.start:
            return False
        previous, current = (
            (existing, action)
            if existing.start <= action.start
            else (action, existing)
        )
        previous_vector = _target_vector_eci(
            case,
            selection,
            satellite,
            previous.target_id,
            previous.midpoint,
        )
        current_vector = _target_vector_eci(
            case,
            selection,
            satellite,
            current.target_id,
            current.midpoint,
        )
        required_gap = (
            _slew_time_sec(case, _angle_between_deg(previous_vector, current_vector))
            + case.satellite_model.attitude_model.settling_time_sec
        )
        actual_gap = (current.start - previous.end).total_seconds()
        if actual_gap + NUMERICAL_EPS < required_gap:
            return False
    return True


def select_gap_aware_actions(
    *,
    case: RevisitCase,
    selection: SelectionSummary,
    satellites: list[SatellitePlan],
    opportunities: list[ObservationAction],
    config: SchedulingConfig,
) -> list[ObservationAction]:
    selected: list[ObservationAction] = []
    used_indexes: set[int] = set()
    midpoints_by_target: dict[str, list[datetime]] = {target_id: [] for target_id in case.targets}
    satellites_by_id = {satellite.satellite_id: satellite for satellite in satellites}
    min_improvement_sec = max(0.0, config.min_gap_improvement_sec)

    while len(selected) < config.max_actions:
        best: tuple[tuple[Any, ...], int, ObservationAction] | None = None
        for index, opportunity in enumerate(opportunities):
            if index in used_indexes:
                continue
            if not _compatible_with_selected(
                case=case,
                selection=selection,
                satellites_by_id=satellites_by_id,
                action=opportunity,
                selected=selected,
            ):
                continue
            target = case.targets[opportunity.target_id]
            existing = midpoints_by_target[opportunity.target_id]
            old_gap = _max_gap_sec(case, opportunity.target_id, existing)
            new_gap = _max_gap_sec(
                case,
                opportunity.target_id,
                [*existing, opportunity.midpoint],
            )
            old_capped = max(old_gap, target.expected_revisit_period_hours * 3600.0)
            new_capped = max(new_gap, target.expected_revisit_period_hours * 3600.0)
            improvement = old_capped - new_capped
            if improvement + NUMERICAL_EPS < min_improvement_sec:
                continue
            score = (
                -improvement,
                -old_capped,
                opportunity.midpoint,
                opportunity.target_id,
                opportunity.satellite_id,
                opportunity.candidate_id,
            )
            if best is None or score < best[0]:
                best = (score, index, opportunity)
        if best is None:
            break
        _, index, action = best
        used_indexes.add(index)
        selected.append(action)
        midpoints_by_target[action.target_id].append(action.midpoint)
    return sorted(
        selected,
        key=lambda item: (item.start, item.end, item.satellite_id, item.target_id),
    )


def compute_target_gap_summary(
    case: RevisitCase,
    actions: list[ObservationAction],
) -> dict[str, dict[str, float]]:
    midpoints_by_target: dict[str, list[datetime]] = {target_id: [] for target_id in case.targets}
    for action in actions:
        midpoints_by_target.setdefault(action.target_id, []).append(action.midpoint)
    summary: dict[str, dict[str, float]] = {}
    for target_id, target in sorted(case.targets.items()):
        times = [
            case.horizon_start,
            *sorted(set(midpoints_by_target.get(target_id, []))),
            case.horizon_end,
        ]
        gaps_hours = [
            (right - left).total_seconds() / 3600.0
            for left, right in zip(times, times[1:])
        ]
        max_gap = max(gaps_hours) if gaps_hours else 0.0
        summary[target_id] = {
            "max_revisit_gap_hours": max_gap,
            "capped_max_revisit_gap_hours": max(
                max_gap,
                target.expected_revisit_period_hours,
            ),
            "observation_count": float(len(times) - 2),
            "expected_revisit_period_hours": target.expected_revisit_period_hours,
        }
    return summary


def _initial_orbit_bounds_ok(case: RevisitCase, state: np.ndarray) -> tuple[bool, str | None]:
    radius = float(np.linalg.norm(state[:3]))
    speed = float(np.linalg.norm(state[3:]))
    altitude = radius - EARTH_RADIUS_M
    if altitude < case.satellite_model.min_altitude_m - NUMERICAL_EPS:
        return False, f"initial altitude below minimum: {altitude:.3f} m"
    if altitude > case.satellite_model.max_altitude_m + NUMERICAL_EPS:
        return False, f"initial altitude above maximum: {altitude:.3f} m"
    energy = 0.5 * speed * speed - MU_EARTH_M3_S2 / radius
    if energy >= 0.0:
        return False, "initial state is not a bound orbit"
    semi_major = -MU_EARTH_M3_S2 / (2.0 * energy)
    radial_velocity = float(np.dot(state[:3], state[3:]))
    eccentricity_vector = (
        ((speed * speed) - (MU_EARTH_M3_S2 / radius)) * state[:3]
        - radial_velocity * state[3:]
    ) / MU_EARTH_M3_S2
    eccentricity = float(np.linalg.norm(eccentricity_vector))
    perigee_altitude = semi_major * (1.0 - eccentricity) - EARTH_RADIUS_M
    apogee_altitude = semi_major * (1.0 + eccentricity) - EARTH_RADIUS_M
    if perigee_altitude < case.satellite_model.min_altitude_m - NUMERICAL_EPS:
        return False, f"perigee below minimum: {perigee_altitude:.3f} m"
    if apogee_altitude > case.satellite_model.max_altitude_m + NUMERICAL_EPS:
        return False, f"apogee above maximum: {apogee_altitude:.3f} m"
    return True, None


def validate_solution_locally(
    *,
    case: RevisitCase,
    selection: SelectionSummary,
    satellites: list[SatellitePlan],
    actions: list[ObservationAction],
    config: SchedulingConfig,
) -> ValidationSummary:
    errors: list[str] = []
    warnings: list[str] = []
    satellites_by_id = {satellite.satellite_id: satellite for satellite in satellites}
    if len(satellites_by_id) != len(satellites):
        errors.append("duplicate satellite_id in generated solution")
    if len(satellites) > case.max_num_satellites:
        errors.append(
            f"solution has {len(satellites)} satellites but cap is {case.max_num_satellites}"
        )
    for satellite in satellites:
        ok, reason = _initial_orbit_bounds_ok(
            case,
            np.asarray(satellite.state_eci_m_mps, dtype=float),
        )
        if not ok:
            errors.append(f"{satellite.satellite_id}: {reason}")

    actions_by_satellite: dict[str, list[ObservationAction]] = {}
    for index, action in enumerate(actions):
        if action.satellite_id not in satellites_by_id:
            errors.append(f"action[{index}] references unknown satellite")
            continue
        if action.target_id not in case.targets:
            errors.append(f"action[{index}] references unknown target")
            continue
        if action.end <= action.start:
            errors.append(f"action[{index}] has non-positive duration")
        if action.start < case.horizon_start or action.end > case.horizon_end:
            errors.append(f"action[{index}] lies outside mission horizon")
        target = case.targets[action.target_id]
        if action.duration_sec + NUMERICAL_EPS < target.min_duration_sec:
            errors.append(f"action[{index}] is shorter than target min duration")
        satellite = satellites_by_id[action.satellite_id]
        if not _action_geometry_valid(
            case=case,
            selection=selection,
            satellite=satellite,
            target=target,
            start=action.start,
            end=action.end,
            sample_step_sec=config.validation_sample_step_sec,
        ):
            errors.append(
                f"action[{index}] fails local sampled visibility for {action.target_id}"
            )
        actions_by_satellite.setdefault(action.satellite_id, []).append(action)

    maneuver_energy_by_satellite = {satellite.satellite_id: 0.0 for satellite in satellites}
    for satellite_id, satellite_actions in actions_by_satellite.items():
        satellite_actions.sort(key=lambda item: (item.start, item.end, item.target_id))
        satellite = satellites_by_id[satellite_id]
        for previous, current in zip(satellite_actions, satellite_actions[1:]):
            if previous.end > current.start:
                errors.append(f"{satellite_id} has overlapping actions")
                continue
            previous_vector = _target_vector_eci(
                case,
                selection,
                satellite,
                previous.target_id,
                previous.midpoint,
            )
            current_vector = _target_vector_eci(
                case,
                selection,
                satellite,
                current.target_id,
                current.midpoint,
            )
            required_gap = (
                _slew_time_sec(case, _angle_between_deg(previous_vector, current_vector))
                + case.satellite_model.attitude_model.settling_time_sec
            )
            actual_gap = (current.start - previous.end).total_seconds()
            if actual_gap + NUMERICAL_EPS < required_gap:
                errors.append(
                    f"{satellite_id} needs {required_gap:.3f}s slew gap but has {actual_gap:.3f}s"
                )
            maneuver_energy_by_satellite[satellite_id] += (
                case.satellite_model.attitude_model.maneuver_discharge_rate_w
                * required_gap
                / 3600.0
            )

    horizon_hours = (case.horizon_end - case.horizon_start).total_seconds() / 3600.0
    for satellite in satellites:
        satellite_actions = actions_by_satellite.get(satellite.satellite_id, [])
        observation_wh = sum(
            case.satellite_model.sensor.obs_discharge_rate_w * action.duration_sec / 3600.0
            for action in satellite_actions
        )
        idle_wh = case.satellite_model.resource_model.idle_discharge_rate_w * horizon_hours
        no_charge_draw = (
            idle_wh
            + observation_wh
            + maneuver_energy_by_satellite.get(satellite.satellite_id, 0.0)
        )
        if (
            no_charge_draw
            > case.satellite_model.resource_model.initial_battery_wh + NUMERICAL_EPS
        ):
            errors.append(
                f"{satellite.satellite_id} has conservative no-charge battery risk"
            )

    return ValidationSummary(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
    )


def build_solution(
    *,
    case: RevisitCase,
    coverage: CoverageSummary,
    selection: SelectionSummary,
    config: SchedulingConfig,
) -> SolutionBuildSummary:
    satellites = generate_phased_satellites(selection)
    opportunities, considered = build_opportunities(
        case=case,
        coverage=coverage,
        selection=selection,
        satellites=satellites,
        config=config,
    )
    actions = select_gap_aware_actions(
        case=case,
        selection=selection,
        satellites=satellites,
        opportunities=opportunities,
        config=config,
    )
    validation = validate_solution_locally(
        case=case,
        selection=selection,
        satellites=satellites,
        actions=actions,
        config=config,
    )
    return SolutionBuildSummary(
        satellites=satellites,
        actions=actions,
        opportunities_considered=considered,
        opportunities_visibility_valid=len(opportunities),
        target_gap_summary=compute_target_gap_summary(case, actions),
        validation=validation,
        config=config,
    )
