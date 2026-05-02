"""Equal-phase satellite generation and gap-aware action construction."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any
import math
import os
import time

import brahe
import numpy as np

from .case_io import RevisitCase, Target
from .coverage import (
    CoarseVisibilityHint,
    CoverageSummary,
    VisibilityWindow,
    geometry_sample_from_state,
)
from .rgt import (
    EARTH_RADIUS_M,
    MU_EARTH_M3_S2,
    brouwer_j2_state_eci,
    ensure_brahe_ready,
)
from .selection import (
    SelectionSummary,
    SelectedCandidate,
    TargetAssignment,
    satellites_required_for_target,
)
from .time_utils import datetime_to_epoch


NUMERICAL_EPS = 1.0e-9


@dataclass(frozen=True, slots=True)
class SchedulingConfig:
    observation_duration_sec: float = 30.0
    opportunity_sample_step_sec: float = 60.0
    min_gap_improvement_sec: float = 60.0
    validation_sample_step_sec: float = 10.0
    refinement_propagation: str = "numerical_j2"
    elevation_safety_margin_deg: float = 0.0
    range_safety_margin_m: float = 15_000.0
    off_nadir_safety_margin_deg: float = 0.5
    max_actions: int = 3000
    max_selection_repair_rounds: int = 8
    max_repair_alternates_per_target: int = 8
    numerical_repair_candidate_limit: int = 64
    opportunity_worker_count: int = 1
    repair_worker_count: int = 1

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
            opportunity_sample_step_sec=float(
                raw.get(
                    "opportunity_sample_step_sec",
                    defaults.opportunity_sample_step_sec,
                )
            ),
            min_gap_improvement_sec=float(
                raw.get("min_gap_improvement_sec", defaults.min_gap_improvement_sec)
            ),
            validation_sample_step_sec=float(
                raw.get("validation_sample_step_sec", defaults.validation_sample_step_sec)
            ),
            refinement_propagation=str(
                raw.get("refinement_propagation", defaults.refinement_propagation)
            ),
            elevation_safety_margin_deg=float(
                raw.get(
                    "elevation_safety_margin_deg",
                    defaults.elevation_safety_margin_deg,
                )
            ),
            range_safety_margin_m=float(
                raw.get("range_safety_margin_m", defaults.range_safety_margin_m)
            ),
            off_nadir_safety_margin_deg=float(
                raw.get(
                    "off_nadir_safety_margin_deg",
                    defaults.off_nadir_safety_margin_deg,
                )
            ),
            max_actions=int(raw.get("max_actions", defaults.max_actions)),
            max_selection_repair_rounds=int(
                raw.get(
                    "max_selection_repair_rounds",
                    defaults.max_selection_repair_rounds,
                )
            ),
            max_repair_alternates_per_target=int(
                raw.get(
                    "max_repair_alternates_per_target",
                    defaults.max_repair_alternates_per_target,
                )
            ),
            numerical_repair_candidate_limit=int(
                raw.get(
                    "numerical_repair_candidate_limit",
                    defaults.numerical_repair_candidate_limit,
                )
            ),
            opportunity_worker_count=int(
                raw.get("opportunity_worker_count", defaults.opportunity_worker_count)
            ),
            repair_worker_count=int(
                raw.get("repair_worker_count", defaults.repair_worker_count)
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_duration_sec": self.observation_duration_sec,
            "opportunity_sample_step_sec": self.opportunity_sample_step_sec,
            "min_gap_improvement_sec": self.min_gap_improvement_sec,
            "validation_sample_step_sec": self.validation_sample_step_sec,
            "refinement_propagation": self.refinement_propagation,
            "elevation_safety_margin_deg": self.elevation_safety_margin_deg,
            "range_safety_margin_m": self.range_safety_margin_m,
            "off_nadir_safety_margin_deg": self.off_nadir_safety_margin_deg,
            "max_actions": self.max_actions,
            "max_selection_repair_rounds": self.max_selection_repair_rounds,
            "max_repair_alternates_per_target": self.max_repair_alternates_per_target,
            "numerical_repair_candidate_limit": self.numerical_repair_candidate_limit,
            "opportunity_worker_count": self.opportunity_worker_count,
            "repair_worker_count": self.repair_worker_count,
        }

    @property
    def use_numerical_refinement(self) -> bool:
        return self.refinement_propagation.lower() in {
            "numerical",
            "numerical_j2",
            "brahe_numerical_j2",
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


class NumericalJ2StateProvider:
    """Solver-local mirror of the benchmark verifier's J2 propagation model."""

    def __init__(self, case: RevisitCase, satellites: list[SatellitePlan]) -> None:
        ensure_brahe_ready()
        start_epoch = datetime_to_epoch(case.horizon_start)
        end_epoch = datetime_to_epoch(case.horizon_end)
        force_config = brahe.ForceModelConfig(
            gravity=brahe.GravityConfiguration.spherical_harmonic(2, 0)
        )
        self._propagators: dict[str, brahe.NumericalOrbitPropagator] = {}
        for satellite in satellites:
            propagator = brahe.NumericalOrbitPropagator.from_eci(
                start_epoch,
                np.asarray(satellite.state_eci_m_mps, dtype=float),
                force_config=force_config,
            )
            propagator.propagate_to(end_epoch)
            self._propagators[satellite.satellite_id] = propagator

    def state_eci(
        self,
        satellite_id: str,
        instant: datetime,
    ) -> tuple[float, float, float, float, float, float]:
        state = np.asarray(
            self._propagators[satellite_id].state_eci(datetime_to_epoch(instant)),
            dtype=float,
        )
        return tuple(float(value) for value in state)


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
    opportunity_refinement_summary: dict[str, Any]
    target_gap_summary: dict[str, dict[str, float]]
    validation: ValidationSummary
    config: SchedulingConfig
    timing_seconds: dict[str, float]
    retry_history: list[dict[str, Any]] = field(default_factory=list)

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
            "opportunity_refinement_summary": self.opportunity_refinement_summary,
            "satellites": [satellite.as_debug_dict() for satellite in self.satellites],
            "actions": [action.as_debug_dict() for action in self.actions],
            "target_gap_summary": self.target_gap_summary,
            "validation": self.validation.as_dict(),
            "timing_seconds": self.timing_seconds,
            "retry_history": self.retry_history,
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
            "opportunity_refinement_summary": self.opportunity_refinement_summary,
            "local_validation_valid": self.validation.is_valid,
            "local_validation_error_count": len(self.validation.errors),
            "high_gap_target_count": len(high_gap_targets),
            "high_gap_target_ids": high_gap_targets,
            "config": self.config.as_dict(),
            "timing_seconds": self.timing_seconds,
            "attempt_count": len(self.retry_history),
            "retry_count": max(0, len(self.retry_history) - 1),
            "retry_history": self.retry_history,
        }


@dataclass(frozen=True, slots=True)
class PhasedOpportunityQuality:
    target_id: str
    candidate_id: str
    required_satellites: int
    opportunity_count: int
    max_gap_hours: float
    capped_max_gap_hours: float
    repeat_period_hours: float
    closure_error_m: float
    first_midpoint_offset_sec: float | None
    last_midpoint_offset_sec: float | None
    coarse_hint_count: int = 0
    refined_opportunity_count: int = 0
    rejected_hint_count: int = 0
    rejection_reasons: dict[str, int] | None = None
    refined_midpoint_offsets_sec: tuple[float, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "candidate_id": self.candidate_id,
            "required_satellites": self.required_satellites,
            "opportunity_count": self.opportunity_count,
            "max_gap_hours": self.max_gap_hours,
            "capped_max_gap_hours": self.capped_max_gap_hours,
            "repeat_period_hours": self.repeat_period_hours,
            "closure_error_m": self.closure_error_m,
            "first_midpoint_offset_sec": self.first_midpoint_offset_sec,
            "last_midpoint_offset_sec": self.last_midpoint_offset_sec,
            "coarse_hint_count": self.coarse_hint_count,
            "refined_opportunity_count": self.refined_opportunity_count,
            "rejected_hint_count": self.rejected_hint_count,
            "rejection_reasons": {} if self.rejection_reasons is None else self.rejection_reasons,
            "refined_midpoint_offsets_sec": list(self.refined_midpoint_offsets_sec),
        }


@dataclass(frozen=True, slots=True)
class SelectionRepairRound:
    round_index: int
    candidate_id: str
    improved_target_ids: tuple[str, ...]
    previous_satellite_count: int
    trial_satellite_count: int
    added_satellites: int
    estimated_worst_before_hours: float
    estimated_worst_after_hours: float
    estimated_total_improvement_hours: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "candidate_id": self.candidate_id,
            "improved_target_ids": list(self.improved_target_ids),
            "previous_satellite_count": self.previous_satellite_count,
            "trial_satellite_count": self.trial_satellite_count,
            "added_satellites": self.added_satellites,
            "estimated_worst_before_hours": self.estimated_worst_before_hours,
            "estimated_worst_after_hours": self.estimated_worst_after_hours,
            "estimated_total_improvement_hours": self.estimated_total_improvement_hours,
        }


@dataclass(frozen=True, slots=True)
class RefinedCandidateProfile:
    candidate_id: str
    required_satellites: int
    met_target_ids: tuple[str, ...]
    quality_by_target: dict[str, PhasedOpportunityQuality]
    average_max_gap_hours: float
    closure_error_m: float
    repeat_period_sec: float

    @property
    def target_count(self) -> int:
        return len(self.met_target_ids)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "required_satellites": self.required_satellites,
            "met_target_count": self.target_count,
            "met_target_ids": list(self.met_target_ids),
            "average_max_gap_hours": self.average_max_gap_hours,
            "closure_error_m": self.closure_error_m,
            "repeat_period_sec": self.repeat_period_sec,
        }


@dataclass(frozen=True, slots=True)
class SelectionRepairResult:
    selection: SelectionSummary
    initial_selection: SelectionSummary
    initial_high_gap_target_ids: tuple[str, ...]
    rounds: tuple[SelectionRepairRound, ...]
    target_diagnostics: dict[str, dict[str, Any]]
    blocker: str | None
    config: SchedulingConfig
    refined_repacking_summary: dict[str, Any] | None = None

    @property
    def changed(self) -> bool:
        return self.selection != self.initial_selection

    def as_debug_dict(
        self,
        *,
        final_gap_summary: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, Any]:
        diagnostics = {
            target_id: dict(payload)
            for target_id, payload in sorted(self.target_diagnostics.items())
        }
        remaining_high_gap_target_ids: list[str] = []
        effective_blocker = self.blocker
        if final_gap_summary is not None:
            for target_id, item in sorted(final_gap_summary.items()):
                final_high_gap = (
                    item["max_revisit_gap_hours"]
                    > item["expected_revisit_period_hours"] + NUMERICAL_EPS
                )
                if final_high_gap:
                    remaining_high_gap_target_ids.append(target_id)
                diagnostics.setdefault(
                    target_id,
                    {
                        "initial_assignment": None,
                        "initial_actual_max_gap_hours": None,
                        "expected_revisit_period_hours": item[
                            "expected_revisit_period_hours"
                        ],
                        "best_alternates": [],
                        "final_estimated_max_gap_hours": math.inf,
                        "final_assignment": None,
                    },
                )
                diagnostics[target_id]["final_actual_max_gap_hours"] = item[
                    "max_revisit_gap_hours"
                ]
                diagnostics[target_id]["final_actual_observation_count"] = item[
                    "observation_count"
                ]
                final_estimated = diagnostics[target_id].get(
                    "final_estimated_max_gap_hours",
                    math.inf,
                )
                best_alternates = diagnostics[target_id].get("best_alternates", [])
                best_refined = best_alternates[0] if best_alternates else None
                if final_high_gap and final_estimated <= (
                    item["expected_revisit_period_hours"] + NUMERICAL_EPS
                ):
                    diagnostics[target_id]["remaining_blocker"] = "scheduling_failure"
                elif final_high_gap and not best_alternates:
                    diagnostics[target_id]["remaining_blocker"] = (
                        "candidate_pool_failure"
                    )
                elif final_high_gap and all(
                    alternate.get("refined_opportunity_count", 0) <= 0
                    for alternate in best_alternates
                ):
                    diagnostics[target_id]["remaining_blocker"] = (
                        "refinement_failure"
                    )
                elif (
                    final_high_gap
                    and best_refined is not None
                    and best_refined.get("max_gap_hours", math.inf)
                    <= item["expected_revisit_period_hours"] + NUMERICAL_EPS
                    and self.selection.total_required_satellites
                    >= self.selection.max_num_satellites
                ):
                    diagnostics[target_id]["remaining_blocker"] = "budget_failure"
                elif final_high_gap:
                    diagnostics[target_id]["remaining_blocker"] = (
                        "candidate_pool_failure"
                    )
                else:
                    diagnostics[target_id]["remaining_blocker"] = None
            if remaining_high_gap_target_ids:
                blocker_classes = sorted(
                    {
                        diagnostics[target_id].get("remaining_blocker")
                        for target_id in remaining_high_gap_target_ids
                        if diagnostics.get(target_id, {}).get("remaining_blocker")
                    }
                )
                effective_blocker = (
                    "+".join(blocker_classes)
                    if blocker_classes
                    else "unclassified_high_gap_failure"
                )
        return {
            "changed": self.changed,
            "blocker": effective_blocker,
            "initial_high_gap_target_ids": list(self.initial_high_gap_target_ids),
            "remaining_high_gap_target_ids": remaining_high_gap_target_ids,
            "initial_satellite_count": self.initial_selection.total_required_satellites,
            "final_satellite_count": self.selection.total_required_satellites,
            "max_num_satellites": self.selection.max_num_satellites,
            "rounds": [round_item.as_dict() for round_item in self.rounds],
            "target_diagnostics": diagnostics,
            "refined_repacking_summary": (
                {} if self.refined_repacking_summary is None else self.refined_repacking_summary
            ),
            "config": {
                "max_selection_repair_rounds": self.config.max_selection_repair_rounds,
                "max_repair_alternates_per_target": (
                    self.config.max_repair_alternates_per_target
                ),
                "numerical_repair_candidate_limit": (
                    self.config.numerical_repair_candidate_limit
                ),
                "repair_worker_count": self.config.repair_worker_count,
            },
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


def _ground_track_phased_state(
    selected: SelectedCandidate,
    *,
    mission_start: datetime,
    mission_offset_sec: float,
    phase_offset_sec: float,
) -> tuple[float, float, float, float, float, float]:
    """Return a state whose Earth-fixed ground track is shifted in time.

    Equal revisit phasing is a repeat-cycle phase in the rotating frame, not an
    equal true/mean anomaly train in one inertial plane.  We therefore sample
    the base candidate at ``t + phase_offset`` in ECI, convert that state into
    ECEF at its own epoch, then reinterpret the same rotating-frame state at
    epoch ``t``.
    """

    ensure_brahe_ready()
    source_offset = mission_offset_sec + phase_offset_sec
    source_epoch = datetime_to_epoch(mission_start + timedelta(seconds=source_offset))
    target_epoch = datetime_to_epoch(mission_start + timedelta(seconds=mission_offset_sec))
    source_state_eci = np.asarray(
        _candidate_state_with_mean_anomaly(
            selected,
            selected.candidate.mean_anomaly_deg,
            source_offset,
        ),
        dtype=float,
    )
    source_state_ecef = np.asarray(
        brahe.state_eci_to_ecef(source_epoch, source_state_eci),
        dtype=float,
    )
    target_state_eci = np.asarray(
        brahe.state_ecef_to_eci(target_epoch, source_state_ecef),
        dtype=float,
    )
    return tuple(float(value) for value in target_state_eci)


def generate_phased_satellites(
    case: RevisitCase,
    selection: SelectionSummary,
) -> list[SatellitePlan]:
    satellites: list[SatellitePlan] = []
    for candidate_index, selected in enumerate(selection.selected_candidates):
        phase_count = selected.required_satellites
        if phase_count <= 0:
            continue
        for phase_index in range(phase_count):
            phase_offset_sec = (
                selected.candidate.repeat_period_sec * phase_index / phase_count
            )
            satellites.append(
                SatellitePlan(
                    satellite_id=f"sat_{candidate_index:03d}_{phase_index:02d}",
                    candidate_id=selected.candidate.candidate_id,
                    template_id=selected.candidate.template_id,
                    phase_index=phase_index,
                    phase_count=phase_count,
                    phase_offset_sec=phase_offset_sec,
                    mean_anomaly_deg=_phase_mean_anomaly(
                        selected.candidate.mean_anomaly_deg,
                        phase_index,
                        phase_count,
                    ),
                    state_eci_m_mps=_ground_track_phased_state(
                        selected,
                        mission_start=case.horizon_start,
                        mission_offset_sec=0.0,
                        phase_offset_sec=phase_offset_sec,
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
    case: RevisitCase,
    selection: SelectionSummary,
    satellite: SatellitePlan,
    offset_sec: float,
    state_provider: NumericalJ2StateProvider | None = None,
) -> tuple[float, float, float, float, float, float]:
    if state_provider is not None:
        return state_provider.state_eci(
            satellite.satellite_id,
            case.horizon_start + timedelta(seconds=offset_sec),
        )
    selected_by_candidate = {
        item.candidate.candidate_id: item for item in selection.selected_candidates
    }
    return _ground_track_phased_state(
        selected_by_candidate[satellite.candidate_id],
        mission_start=case.horizon_start,
        mission_offset_sec=offset_sec,
        phase_offset_sec=satellite.phase_offset_sec,
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
    elevation_safety_margin_deg: float = 0.0,
    range_safety_margin_m: float = 0.0,
    off_nadir_safety_margin_deg: float = 0.0,
    state_provider: NumericalJ2StateProvider | None = None,
) -> bool:
    for sample_offset in _sample_offsets(start, end, sample_step_sec):
        instant = start + timedelta(seconds=sample_offset)
        mission_offset = (instant - case.horizon_start).total_seconds()
        state = satellite_state_at(
            case,
            selection,
            satellite,
            mission_offset,
            state_provider=state_provider,
        )
        sample = geometry_sample_from_state(
            case=case,
            target=target,
            state_eci_m_mps=state,
            instant=instant,
            offset_sec=mission_offset,
        )
        if not sample.visible:
            return False
        max_allowed_range_m = min(
            target.max_slant_range_m,
            case.satellite_model.sensor.max_range_m,
        )
        if (
            sample.elevation_deg
            < target.min_elevation_deg + elevation_safety_margin_deg
        ):
            return False
        if (
            sample.slant_range_m
            > max_allowed_range_m - range_safety_margin_m
        ):
            return False
        if (
            sample.off_nadir_deg
            > case.satellite_model.sensor.max_off_nadir_angle_deg
            - off_nadir_safety_margin_deg
        ):
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


def _legacy_hint_from_window(
    *,
    case: RevisitCase,
    window: VisibilityWindow,
    repeat_period_sec: float,
) -> CoarseVisibilityHint:
    target = case.targets[window.target_id]
    range_limit = min(
        target.max_slant_range_m,
        case.satellite_model.sensor.max_range_m,
    )
    elevation_margin = window.max_elevation_deg - target.min_elevation_deg
    range_margin = range_limit - window.min_slant_range_m
    off_nadir_margin = (
        case.satellite_model.sensor.max_off_nadir_angle_deg
        - window.min_off_nadir_deg
    )
    return CoarseVisibilityHint(
        hint_id=f"{window.window_id}__legacy_hint",
        candidate_id=window.candidate_id,
        template_id=window.template_id,
        target_id=window.target_id,
        offset_sec=window.midpoint_offset_sec,
        repeat_period_sec=repeat_period_sec,
        sample_step_sec=max(window.duration_sec, 1.0),
        elevation_deg=window.max_elevation_deg,
        slant_range_m=window.min_slant_range_m,
        off_nadir_deg=window.min_off_nadir_deg,
        elevation_margin_deg=elevation_margin,
        range_margin_m=range_margin,
        off_nadir_margin_deg=off_nadir_margin,
        min_margin=min(elevation_margin, range_margin, off_nadir_margin),
        source="legacy_coarse_window_midpoint",
    )


def _coarse_hints_by_key(
    *,
    case: RevisitCase,
    coverage: CoverageSummary,
) -> dict[tuple[str, str], list[CoarseVisibilityHint]]:
    hints_by_key: dict[tuple[str, str], list[CoarseVisibilityHint]] = {}
    candidates = _candidate_map(coverage)
    for hint in coverage.hints:
        hints_by_key.setdefault((hint.candidate_id, hint.target_id), []).append(hint)
    if not coverage.hints:
        for window in coverage.windows:
            repeat_period_sec = candidates[window.candidate_id].repeat_period_sec
            hints_by_key.setdefault((window.candidate_id, window.target_id), []).append(
                _legacy_hint_from_window(
                    case=case,
                    window=window,
                    repeat_period_sec=repeat_period_sec,
                )
            )
    for hints in hints_by_key.values():
        hints.sort(
            key=lambda item: (
                item.offset_sec,
                -item.min_margin,
                item.hint_id,
            )
        )
    return hints_by_key


def _resolved_worker_count(configured: int, work_item_count: int) -> int:
    if work_item_count <= 0:
        return 0
    if configured <= 1:
        return 1
    return max(1, min(configured, work_item_count, os.cpu_count() or 1))


def _candidate_map(coverage: CoverageSummary) -> dict[str, Any]:
    return {candidate.candidate_id: candidate for candidate in coverage.candidates}


def _coverage_margin_for_windows(
    *,
    case: RevisitCase,
    target_id: str,
    windows: list[VisibilityWindow],
) -> float:
    if not windows:
        return 0.0
    target = case.targets[target_id]
    range_limit = min(
        target.max_slant_range_m,
        case.satellite_model.sensor.max_range_m,
    )
    return max(
        min(
            window.max_elevation_deg - target.min_elevation_deg,
            range_limit - window.min_slant_range_m,
            case.satellite_model.sensor.max_off_nadir_angle_deg
            - window.min_off_nadir_deg,
        )
        for window in windows
    )


def _build_selection_from_target_assignments(
    *,
    case: RevisitCase,
    coverage: CoverageSummary,
    original: SelectionSummary,
    selected_candidate_ids: list[str],
    target_to_candidate: dict[str, str],
) -> SelectionSummary:
    candidates = _candidate_map(coverage)
    windows_by_key = _candidate_windows_by_key(coverage)
    assignments: dict[str, TargetAssignment] = {}
    for target_id, candidate_id in sorted(target_to_candidate.items()):
        if candidate_id not in candidates:
            continue
        candidate = candidates[candidate_id]
        target = case.targets[target_id]
        assignments[target_id] = TargetAssignment(
            target_id=target_id,
            candidate_id=candidate_id,
            required_satellites=satellites_required_for_target(candidate, target),
            repeat_period_hours=candidate.repeat_period_sec / 3600.0,
            coverage_margin_score=_coverage_margin_for_windows(
                case=case,
                target_id=target_id,
                windows=windows_by_key.get((candidate_id, target_id), []),
            ),
        )

    selected_items: list[SelectedCandidate] = []
    total_required_satellites = 0
    for candidate_id in selected_candidate_ids:
        assigned = tuple(
            target_id
            for target_id, assignment in sorted(assignments.items())
            if assignment.candidate_id == candidate_id
        )
        if not assigned:
            continue
        assigned_costs = [
            assignments[target_id].required_satellites for target_id in assigned
        ]
        required_satellites = max(assigned_costs, default=0)
        total_required_satellites += required_satellites
        covered = tuple(coverage.candidate_to_targets.get(candidate_id, []))
        selected_items.append(
            SelectedCandidate(
                candidate=candidates[candidate_id],
                assigned_target_ids=assigned,
                required_satellites=required_satellites,
                covered_target_ids=covered,
                redundant_target_ids=tuple(
                    target_id for target_id in covered if target_id not in assigned
                ),
            )
        )

    selected_ids_with_assignments = {
        item.candidate.candidate_id for item in selected_items
    }
    uncovered = sorted(set(case.targets).difference(assignments))
    return SelectionSummary(
        selected_candidates=selected_items,
        target_assignments=assignments,
        uncovered_target_ids=uncovered,
        total_required_satellites=total_required_satellites,
        max_num_satellites=case.max_num_satellites,
        rounds=original.rounds,
        budget_near_misses=original.budget_near_misses,
        all_targets_covered=not uncovered,
        within_satellite_budget=total_required_satellites <= case.max_num_satellites
        and selected_ids_with_assignments == set(
            item.candidate.candidate_id for item in selected_items
        ),
    )


def _offset_max_gap_sec(
    *,
    horizon_sec: float,
    midpoint_offsets_sec: list[float],
) -> float:
    times = [0.0, *sorted(set(midpoint_offsets_sec)), horizon_sec]
    return max(right - left for left, right in zip(times, times[1:]))


def _single_candidate_selection(
    *,
    case: RevisitCase,
    coverage: CoverageSummary,
    candidate_id: str,
    target_ids: list[str],
) -> SelectionSummary:
    candidates = _candidate_map(coverage)
    candidate = candidates[candidate_id]
    assignments: dict[str, TargetAssignment] = {}
    for target_id in sorted(target_ids):
        target = case.targets[target_id]
        assignments[target_id] = TargetAssignment(
            target_id=target_id,
            candidate_id=candidate_id,
            required_satellites=satellites_required_for_target(candidate, target),
            repeat_period_hours=candidate.repeat_period_sec / 3600.0,
            coverage_margin_score=0.0,
        )
    required_satellites = max(
        (assignment.required_satellites for assignment in assignments.values()),
        default=0,
    )
    selected = SelectedCandidate(
        candidate=candidate,
        assigned_target_ids=tuple(sorted(target_ids)),
        required_satellites=required_satellites,
        covered_target_ids=tuple(coverage.candidate_to_targets.get(candidate_id, [])),
        redundant_target_ids=tuple(
            target_id
            for target_id in coverage.candidate_to_targets.get(candidate_id, [])
            if target_id not in assignments
        ),
    )
    return SelectionSummary(
        selected_candidates=[selected] if required_satellites else [],
        target_assignments=assignments,
        uncovered_target_ids=sorted(set(case.targets).difference(assignments)),
        total_required_satellites=required_satellites,
        max_num_satellites=case.max_num_satellites,
        rounds=[],
        budget_near_misses=[],
        all_targets_covered=set(assignments) == set(case.targets),
        within_satellite_budget=required_satellites <= case.max_num_satellites,
    )


def _candidate_realization_offsets(
    *,
    hint_offset_sec: float,
    phase_offset_sec: float,
    repeat_period_sec: float,
    horizon_sec: float,
    radius_sec: float,
) -> list[float]:
    if repeat_period_sec <= 0.0:
        repeat_period_sec = horizon_sec
    offset = hint_offset_sec - phase_offset_sec
    while offset < -radius_sec:
        offset += repeat_period_sec
    values: list[float] = []
    while offset <= horizon_sec + radius_sec + NUMERICAL_EPS:
        if -radius_sec <= offset <= horizon_sec + radius_sec:
            values.append(float(offset))
        offset += repeat_period_sec
    return values


def _refine_action_near_offset(
    *,
    case: RevisitCase,
    selection: SelectionSummary,
    satellite: SatellitePlan,
    target: Target,
    nominal_offset_sec: float,
    radius_sec: float,
    config: SchedulingConfig,
    state_provider: NumericalJ2StateProvider | None = None,
) -> tuple[ObservationAction | None, str]:
    horizon_sec = (case.horizon_end - case.horizon_start).total_seconds()
    duration_sec = target.min_duration_sec
    half_duration = duration_sec / 2.0
    if nominal_offset_sec < -radius_sec or nominal_offset_sec > horizon_sec + radius_sec:
        return None, "outside_horizon"
    low = max(half_duration, nominal_offset_sec - radius_sec)
    high = min(horizon_sec - half_duration, nominal_offset_sec + radius_sec)
    if high + NUMERICAL_EPS < low:
        return None, "insufficient_horizon_room"
    step_sec = max(1.0, min(config.opportunity_sample_step_sec, radius_sec * 0.5))
    midpoint_offsets = {round(min(max(nominal_offset_sec, low), high), 6)}
    current = low
    while current <= high + NUMERICAL_EPS:
        midpoint_offsets.add(round(min(max(current, low), high), 6))
        current += step_sec
    ordered_offsets = sorted(
        midpoint_offsets,
        key=lambda item: (abs(item - nominal_offset_sec), item),
    )
    for midpoint_offset in ordered_offsets:
        midpoint = case.horizon_start + timedelta(seconds=midpoint_offset)
        start = midpoint - timedelta(seconds=half_duration)
        end = midpoint + timedelta(seconds=half_duration)
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
            elevation_safety_margin_deg=config.elevation_safety_margin_deg,
            range_safety_margin_m=config.range_safety_margin_m,
            off_nadir_safety_margin_deg=config.off_nadir_safety_margin_deg,
            state_provider=state_provider,
        ):
            return (
                ObservationAction(
                    action_type="observation",
                    satellite_id=satellite.satellite_id,
                    target_id=target.target_id,
                    start=start,
                    end=end,
                    candidate_id=satellite.candidate_id,
                    opportunity_midpoint_offset_sec=midpoint_offset,
                ),
                "refined",
            )
    return None, "no_valid_interval"


def _refined_opportunities_for_satellite_target(
    *,
    case: RevisitCase,
    selection: SelectionSummary,
    satellite: SatellitePlan,
    target_id: str,
    hints: list[CoarseVisibilityHint],
    config: SchedulingConfig,
    state_provider: NumericalJ2StateProvider | None = None,
) -> tuple[list[ObservationAction], int, dict[str, int], list[dict[str, Any]]]:
    target = case.targets[target_id]
    horizon_sec = (case.horizon_end - case.horizon_start).total_seconds()
    opportunities_by_key: dict[tuple[str, str, float], ObservationAction] = {}
    rejection_reasons: dict[str, int] = {}
    attempts: list[dict[str, Any]] = []
    for hint in hints:
        repeat_period_sec = hint.repeat_period_sec
        if repeat_period_sec <= 0.0:
            repeat_period_sec = max(horizon_sec, satellite.phase_count * satellite.phase_offset_sec)
        radius_sec = max(
            target.min_duration_sec,
            hint.sample_step_sec / 2.0,
            config.validation_sample_step_sec,
        )
        for nominal_offset in _candidate_realization_offsets(
            hint_offset_sec=hint.offset_sec,
            phase_offset_sec=satellite.phase_offset_sec,
            repeat_period_sec=repeat_period_sec,
            horizon_sec=horizon_sec,
            radius_sec=radius_sec,
        ):
            action, reason = _refine_action_near_offset(
                case=case,
                selection=selection,
                satellite=satellite,
                target=target,
                nominal_offset_sec=nominal_offset,
                radius_sec=radius_sec,
                config=config,
                state_provider=state_provider,
            )
            attempts.append(
                {
                    "hint_id": hint.hint_id,
                    "hint_offset_sec": hint.offset_sec,
                    "satellite_id": satellite.satellite_id,
                    "phase_index": satellite.phase_index,
                    "phase_offset_sec": satellite.phase_offset_sec,
                    "nominal_offset_sec": nominal_offset,
                    "result": reason,
                    "refined_midpoint_offset_sec": (
                        None if action is None else action.opportunity_midpoint_offset_sec
                    ),
                }
            )
            if action is None:
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                continue
            key = (
                action.satellite_id,
                action.target_id,
                round(action.opportunity_midpoint_offset_sec, 6),
            )
            opportunities_by_key[key] = action
    return (
        sorted(
            opportunities_by_key.values(),
            key=lambda item: (
                item.midpoint,
                item.target_id,
                item.satellite_id,
                item.candidate_id,
            ),
        ),
        len(attempts),
        rejection_reasons,
        attempts,
    )


def _refined_candidate_target_quality(
    *,
    case: RevisitCase,
    coverage: CoverageSummary,
    candidate_id: str,
    target_id: str,
    hints: list[CoarseVisibilityHint],
    config: SchedulingConfig,
) -> PhasedOpportunityQuality:
    candidate = _candidate_map(coverage)[candidate_id]
    target = case.targets[target_id]
    selection = _single_candidate_selection(
        case=case,
        coverage=coverage,
        candidate_id=candidate_id,
        target_ids=[target_id],
    )
    satellites = generate_phased_satellites(case, selection)
    state_provider = (
        NumericalJ2StateProvider(case, satellites)
        if config.use_numerical_refinement
        else None
    )
    return _refined_candidate_target_quality_for_satellites(
        case=case,
        candidate=candidate,
        selection=selection,
        satellites=satellites,
        target_id=target_id,
        hints=hints,
        config=config,
        state_provider=state_provider,
    )


def _refined_candidate_target_quality_for_satellites(
    *,
    case: RevisitCase,
    candidate: Any,
    selection: SelectionSummary,
    satellites: list[SatellitePlan],
    target_id: str,
    hints: list[CoarseVisibilityHint],
    config: SchedulingConfig,
    state_provider: NumericalJ2StateProvider | None,
) -> PhasedOpportunityQuality:
    target = case.targets[target_id]
    opportunities: list[ObservationAction] = []
    rejection_reasons: dict[str, int] = {}
    attempts = 0
    for satellite in satellites:
        satellite_opportunities, satellite_attempts, satellite_rejections, _ = (
            _refined_opportunities_for_satellite_target(
                case=case,
                selection=selection,
                satellite=satellite,
                target_id=target_id,
                hints=hints,
                config=config,
                state_provider=state_provider,
            )
        )
        opportunities.extend(satellite_opportunities)
        attempts += satellite_attempts
        for reason, count in satellite_rejections.items():
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + count
    midpoint_offsets = sorted(
        {
            round(
                (opportunity.midpoint - case.horizon_start).total_seconds(),
                6,
            )
            for opportunity in opportunities
        }
    )
    horizon_sec = (case.horizon_end - case.horizon_start).total_seconds()
    if midpoint_offsets:
        max_gap_sec = _offset_max_gap_sec(
            horizon_sec=horizon_sec,
            midpoint_offsets_sec=midpoint_offsets,
        )
        first_midpoint = midpoint_offsets[0]
        last_midpoint = midpoint_offsets[-1]
    else:
        max_gap_sec = horizon_sec
        first_midpoint = None
        last_midpoint = None
    max_gap_hours = max_gap_sec / 3600.0
    return PhasedOpportunityQuality(
        target_id=target_id,
        candidate_id=candidate.candidate_id,
        required_satellites=satellites_required_for_target(candidate, target),
        opportunity_count=len(midpoint_offsets),
        max_gap_hours=max_gap_hours,
        capped_max_gap_hours=max(max_gap_hours, target.expected_revisit_period_hours),
        repeat_period_hours=candidate.repeat_period_sec / 3600.0,
        closure_error_m=candidate.template_closure_error_m,
        first_midpoint_offset_sec=first_midpoint,
        last_midpoint_offset_sec=last_midpoint,
        coarse_hint_count=len(hints),
        refined_opportunity_count=len(midpoint_offsets),
        rejected_hint_count=max(0, attempts - len(midpoint_offsets)),
        rejection_reasons=rejection_reasons,
        refined_midpoint_offsets_sec=tuple(midpoint_offsets[:24]),
    )


def _phased_midpoint_offsets(
    *,
    candidate_repeat_sec: float,
    phase_count: int,
    horizon_sec: float,
    windows: list[VisibilityWindow],
) -> list[float]:
    offsets: set[float] = set()
    for window in windows:
        base_midpoint = window.midpoint_offset_sec
        for phase_index in range(phase_count):
            phase_offset = candidate_repeat_sec * phase_index / phase_count
            shifted = base_midpoint - phase_offset
            while shifted < -NUMERICAL_EPS:
                shifted += candidate_repeat_sec
            while shifted <= horizon_sec + NUMERICAL_EPS:
                bounded = min(max(0.0, shifted), horizon_sec)
                offsets.add(round(bounded, 6))
                shifted += candidate_repeat_sec
    return sorted(offsets)


def evaluate_phased_candidate_target_quality(
    *,
    case: RevisitCase,
    coverage: CoverageSummary,
    candidate_id: str,
    target_id: str,
) -> PhasedOpportunityQuality:
    if candidate_id not in _candidate_map(coverage):
        raise ValueError(f"unknown candidate_id: {candidate_id}")
    if target_id not in case.targets:
        raise ValueError(f"unknown target_id: {target_id}")
    hints = _coarse_hints_by_key(case=case, coverage=coverage).get(
        (candidate_id, target_id),
        [],
    )
    return _refined_candidate_target_quality(
        case=case,
        coverage=coverage,
        candidate_id=candidate_id,
        target_id=target_id,
        hints=hints,
        config=SchedulingConfig(),
    )


def _phased_quality_from_windows(
    *,
    horizon_sec: float,
    target: Target,
    candidate: Any,
    windows: list[VisibilityWindow],
) -> PhasedOpportunityQuality:
    required_satellites = satellites_required_for_target(candidate, target)
    midpoint_offsets = _phased_midpoint_offsets(
        candidate_repeat_sec=candidate.repeat_period_sec,
        phase_count=required_satellites,
        horizon_sec=horizon_sec,
        windows=windows,
    )
    if midpoint_offsets:
        max_gap_sec = _offset_max_gap_sec(
            horizon_sec=horizon_sec,
            midpoint_offsets_sec=midpoint_offsets,
        )
        first_midpoint = midpoint_offsets[0]
        last_midpoint = midpoint_offsets[-1]
    else:
        max_gap_sec = horizon_sec
        first_midpoint = None
        last_midpoint = None
    max_gap_hours = max_gap_sec / 3600.0
    return PhasedOpportunityQuality(
        target_id=target.target_id,
        candidate_id=candidate.candidate_id,
        required_satellites=required_satellites,
        opportunity_count=len(midpoint_offsets),
        max_gap_hours=max_gap_hours,
        capped_max_gap_hours=max(max_gap_hours, target.expected_revisit_period_hours),
        repeat_period_hours=candidate.repeat_period_sec / 3600.0,
        closure_error_m=candidate.template_closure_error_m,
        first_midpoint_offset_sec=first_midpoint,
        last_midpoint_offset_sec=last_midpoint,
    )


def _quality_worker(
    args: tuple[
        RevisitCase,
        CoverageSummary,
        str,
        str,
        list[CoarseVisibilityHint],
        SchedulingConfig,
    ],
) -> PhasedOpportunityQuality:
    case, coverage, candidate_id, target_id, hints, config = args
    return _refined_candidate_target_quality(
        case=case,
        coverage=coverage,
        candidate_id=candidate_id,
        target_id=target_id,
        hints=hints,
        config=config,
    )


def _quality_candidate_worker(
    args: tuple[
        RevisitCase,
        CoverageSummary,
        str,
        list[str],
        dict[str, list[CoarseVisibilityHint]],
        SchedulingConfig,
    ],
) -> list[PhasedOpportunityQuality]:
    case, coverage, candidate_id, target_ids, hints_by_target, config = args
    candidate = _candidate_map(coverage)[candidate_id]
    targets_by_required_satellites: dict[int, list[str]] = {}
    for target_id in target_ids:
        required_satellites = satellites_required_for_target(
            candidate,
            case.targets[target_id],
        )
        targets_by_required_satellites.setdefault(required_satellites, []).append(
            target_id
        )
    qualities: list[PhasedOpportunityQuality] = []
    for grouped_target_ids in targets_by_required_satellites.values():
        selection = _single_candidate_selection(
            case=case,
            coverage=coverage,
            candidate_id=candidate_id,
            target_ids=sorted(grouped_target_ids),
        )
        satellites = generate_phased_satellites(case, selection)
        state_provider = (
            NumericalJ2StateProvider(case, satellites)
            if config.use_numerical_refinement
            else None
        )
        for target_id in sorted(grouped_target_ids):
            qualities.append(
                _refined_candidate_target_quality_for_satellites(
                    case=case,
                    candidate=candidate,
                    selection=selection,
                    satellites=satellites,
                    target_id=target_id,
                    hints=hints_by_target.get(target_id, []),
                    config=config,
                    state_provider=state_provider,
                )
            )
    return qualities


def _initial_high_gap_targets(
    initial_gap_summary: dict[str, dict[str, float]],
) -> list[str]:
    return [
        target_id
        for target_id, item in sorted(initial_gap_summary.items())
        if item["max_revisit_gap_hours"]
        > item["expected_revisit_period_hours"] + NUMERICAL_EPS
    ]


def _candidate_quality_cache(
    *,
    case: RevisitCase,
    coverage: CoverageSummary,
    target_ids: list[str],
    config: SchedulingConfig,
    candidate_id_filter: set[str] | None = None,
) -> dict[tuple[str, str], PhasedOpportunityQuality]:
    if config.use_numerical_refinement and candidate_id_filter is None:
        analytical_config = replace(config, refinement_propagation="analytical_j2")
        analytical_cache = _candidate_quality_cache(
            case=case,
            coverage=coverage,
            target_ids=target_ids,
            config=analytical_config,
        )
        analytical_profiles = _refined_candidate_profiles(
            case=case,
            coverage=coverage,
            quality_by_pair=analytical_cache,
        )
        frontier_ids: set[str] = set()
        for target_id in sorted(target_ids):
            target_qualities = [
                quality
                for (candidate_id, quality_target_id), quality in analytical_cache.items()
                if quality_target_id == target_id
            ]
            for alternate in sorted(
                target_qualities,
                key=lambda item: (
                    item.capped_max_gap_hours,
                    item.max_gap_hours,
                    item.required_satellites,
                    item.closure_error_m,
                    item.repeat_period_hours,
                    item.candidate_id,
                ),
            )[: config.max_repair_alternates_per_target]:
                frontier_ids.add(alternate.candidate_id)
        ranked_frontier = sorted(
            frontier_ids,
            key=lambda candidate_id: (
                -analytical_profiles[candidate_id].target_count
                if candidate_id in analytical_profiles
                else 0,
                analytical_profiles[candidate_id].required_satellites
                if candidate_id in analytical_profiles
                else math.inf,
                analytical_profiles[candidate_id].average_max_gap_hours
                if candidate_id in analytical_profiles
                else math.inf,
                analytical_profiles[candidate_id].closure_error_m
                if candidate_id in analytical_profiles
                else math.inf,
                candidate_id,
            ),
        )
        limited_frontier = set(
            ranked_frontier[: max(1, config.numerical_repair_candidate_limit)]
        )
        return _candidate_quality_cache(
            case=case,
            coverage=coverage,
            target_ids=target_ids,
            config=config,
            candidate_id_filter=limited_frontier,
        )

    hints_by_key = _coarse_hints_by_key(case=case, coverage=coverage)
    target_filter = set(target_ids)
    work_items: list[
        tuple[
            RevisitCase,
            CoverageSummary,
            str,
            list[str],
            dict[str, list[CoarseVisibilityHint]],
            SchedulingConfig,
        ]
    ] = []
    for candidate_id in sorted(candidate.candidate_id for candidate in coverage.candidates):
        if candidate_id_filter is not None and candidate_id not in candidate_id_filter:
            continue
        candidate_target_ids = [
            target_id
            for target_id in coverage.candidate_to_targets.get(candidate_id, [])
            if target_id in target_filter
        ]
        if not candidate_target_ids:
            continue
        work_items.append(
            (
                case,
                coverage,
                candidate_id,
                sorted(candidate_target_ids),
                {
                    target_id: hints_by_key.get((candidate_id, target_id), [])
                    for target_id in candidate_target_ids
                },
                config,
            )
        )
    resolved_worker_count = _resolved_worker_count(
        config.repair_worker_count,
        len(work_items),
    )
    if resolved_worker_count > 1:
        with ProcessPoolExecutor(max_workers=resolved_worker_count) as executor:
            nested_qualities = list(executor.map(_quality_candidate_worker, work_items))
    else:
        nested_qualities = [_quality_candidate_worker(item) for item in work_items]
    qualities = [
        quality
        for candidate_qualities in nested_qualities
        for quality in candidate_qualities
    ]
    return {
        (quality.candidate_id, quality.target_id): quality
        for quality in sorted(
            qualities,
            key=lambda item: (item.target_id, item.candidate_id),
        )
    }


def _top_alternates(
    qualities: list[PhasedOpportunityQuality],
    limit: int,
) -> list[dict[str, Any]]:
    ordered = sorted(
        qualities,
        key=lambda item: (
            item.capped_max_gap_hours,
            item.max_gap_hours,
            item.required_satellites,
            item.closure_error_m,
            item.repeat_period_hours,
            item.candidate_id,
        ),
    )
    return [item.as_dict() for item in ordered[: max(0, limit)]]


def _quality_meets_revisit(
    case: RevisitCase,
    quality: PhasedOpportunityQuality,
) -> bool:
    target = case.targets[quality.target_id]
    return (
        quality.opportunity_count > 0
        and quality.max_gap_hours
        <= target.expected_revisit_period_hours + NUMERICAL_EPS
    )


def _refined_candidate_profiles(
    *,
    case: RevisitCase,
    coverage: CoverageSummary,
    quality_by_pair: dict[tuple[str, str], PhasedOpportunityQuality],
) -> dict[str, RefinedCandidateProfile]:
    candidates = _candidate_map(coverage)
    by_candidate: dict[str, dict[str, PhasedOpportunityQuality]] = {}
    for (candidate_id, target_id), quality in quality_by_pair.items():
        if candidate_id not in candidates:
            continue
        if not _quality_meets_revisit(case, quality):
            continue
        by_candidate.setdefault(candidate_id, {})[target_id] = quality

    profiles: dict[str, RefinedCandidateProfile] = {}
    for candidate_id, qualities in sorted(by_candidate.items()):
        candidate = candidates[candidate_id]
        met_target_ids = tuple(sorted(qualities))
        if not met_target_ids:
            continue
        required_satellites = max(
            qualities[target_id].required_satellites
            for target_id in met_target_ids
        )
        profiles[candidate_id] = RefinedCandidateProfile(
            candidate_id=candidate_id,
            required_satellites=required_satellites,
            met_target_ids=met_target_ids,
            quality_by_target=qualities,
            average_max_gap_hours=(
                sum(quality.max_gap_hours for quality in qualities.values())
                / len(qualities)
            ),
            closure_error_m=candidate.template_closure_error_m,
            repeat_period_sec=candidate.repeat_period_sec,
        )
    return profiles


def _selection_from_refined_profiles(
    *,
    case: RevisitCase,
    coverage: CoverageSummary,
    original: SelectionSummary,
    selected_candidate_ids: list[str],
    profiles: dict[str, RefinedCandidateProfile],
) -> SelectionSummary:
    target_to_candidate: dict[str, str] = {}
    for target_id in sorted(case.targets):
        covering = [
            profiles[candidate_id]
            for candidate_id in selected_candidate_ids
            if candidate_id in profiles
            and target_id in profiles[candidate_id].quality_by_target
        ]
        if not covering:
            continue
        chosen = min(
            covering,
            key=lambda profile: (
                profile.quality_by_target[target_id].max_gap_hours,
                profile.required_satellites,
                profile.closure_error_m,
                profile.repeat_period_sec,
                profile.candidate_id,
            ),
        )
        target_to_candidate[target_id] = chosen.candidate_id
    return _build_selection_from_target_assignments(
        case=case,
        coverage=coverage,
        original=original,
        selected_candidate_ids=selected_candidate_ids,
        target_to_candidate=target_to_candidate,
    )


def _repack_selection_with_refined_profiles(
    *,
    case: RevisitCase,
    coverage: CoverageSummary,
    original: SelectionSummary,
    profiles: dict[str, RefinedCandidateProfile],
    quality_by_pair: dict[tuple[str, str], PhasedOpportunityQuality],
) -> tuple[SelectionSummary, dict[str, Any]]:
    target_ids = sorted(case.targets)
    target_bit = {target_id: 1 << index for index, target_id in enumerate(target_ids)}
    full_mask = (1 << len(target_ids)) - 1
    profile_items = sorted(
        profiles.values(),
        key=lambda profile: (
            -profile.target_count,
            profile.required_satellites,
            profile.average_max_gap_hours,
            profile.closure_error_m,
            profile.repeat_period_sec,
            profile.candidate_id,
        ),
    )
    candidate_masks = {
        profile.candidate_id: sum(target_bit[target_id] for target_id in profile.met_target_ids)
        for profile in profile_items
    }
    profile_by_id = {profile.candidate_id: profile for profile in profile_items}

    def selection_quality(candidate_ids: tuple[str, ...]) -> float:
        return sum(
            profile_by_id[candidate_id].average_max_gap_hours
            * profile_by_id[candidate_id].target_count
            for candidate_id in candidate_ids
        )

    def selection_mask(candidate_ids: tuple[str, ...]) -> int:
        mask = 0
        for candidate_id in candidate_ids:
            mask |= candidate_masks[candidate_id]
        return mask

    def partial_gap_by_target(candidate_ids: tuple[str, ...]) -> dict[str, float]:
        fallback_gap_hours = (
            case.horizon_end - case.horizon_start
        ).total_seconds() / 3600.0
        result: dict[str, float] = {}
        for target_id in target_ids:
            target_qualities = [
                quality_by_pair[(candidate_id, target_id)].max_gap_hours
                for candidate_id in candidate_ids
                if (candidate_id, target_id) in quality_by_pair
            ]
            result[target_id] = (
                min(target_qualities) if target_qualities else fallback_gap_hours
            )
        return result

    def selection_partial_quality(candidate_ids: tuple[str, ...]) -> tuple[float, float]:
        gaps = partial_gap_by_target(candidate_ids)
        return max(gaps.values(), default=0.0), sum(gaps.values())

    def selection_cost(candidate_ids: tuple[str, ...]) -> int:
        return sum(
            profile_by_id[candidate_id].required_satellites
            for candidate_id in candidate_ids
        )

    def selection_key(
        candidate_ids: tuple[str, ...]
    ) -> tuple[int, float, float, int, float, tuple[str, ...]]:
        mask = selection_mask(candidate_ids)
        partial_worst_gap, partial_total_gap = selection_partial_quality(candidate_ids)
        return (
            -mask.bit_count(),
            partial_worst_gap,
            partial_total_gap,
            selection_cost(candidate_ids),
            selection_quality(candidate_ids),
            candidate_ids,
        )

    selected_ids: tuple[str, ...] = ()
    selected_mask = 0
    selected_cost = 0
    greedy_rounds: list[dict[str, Any]] = []
    while selected_mask != full_mask:
        options: list[tuple[tuple[Any, ...], RefinedCandidateProfile, int]] = []
        for profile in profile_items:
            if profile.candidate_id in selected_ids:
                continue
            if selected_cost + profile.required_satellites > case.max_num_satellites:
                continue
            gain_mask = candidate_masks[profile.candidate_id] & ~selected_mask
            gain = gain_mask.bit_count()
            if gain <= 0:
                continue
            score = (
                -(gain / profile.required_satellites),
                -gain,
                profile.required_satellites,
                profile.average_max_gap_hours,
                profile.closure_error_m,
                profile.repeat_period_sec,
                profile.candidate_id,
            )
            options.append((score, profile, gain))
        if not options:
            break
        _, chosen, gain = min(options, key=lambda item: item[0])
        selected_ids = tuple(sorted((*selected_ids, chosen.candidate_id)))
        selected_mask |= candidate_masks[chosen.candidate_id]
        selected_cost += chosen.required_satellites
        greedy_rounds.append(
            {
                "candidate_id": chosen.candidate_id,
                "gain": gain,
                "selected_satellite_count": selected_cost,
                "covered_target_count": selected_mask.bit_count(),
            }
        )

    replacement_rounds: list[dict[str, Any]] = []
    changed = True
    while changed:
        changed = False
        current_key = selection_key(selected_ids)
        best_ids = selected_ids
        best_replacement: dict[str, Any] | None = None
        selected_set = set(selected_ids)
        for remove_id in selected_ids:
            base_ids = tuple(
                candidate_id
                for candidate_id in selected_ids
                if candidate_id != remove_id
            )
            base_cost = selection_cost(base_ids)
            for add_profile in profile_items:
                add_id = add_profile.candidate_id
                if add_id in selected_set:
                    continue
                if base_cost + add_profile.required_satellites > case.max_num_satellites:
                    continue
                trial_ids = tuple(sorted((*base_ids, add_id)))
                trial_key = selection_key(trial_ids)
                if trial_key < current_key and trial_key < selection_key(best_ids):
                    best_ids = trial_ids
                    best_replacement = {
                        "removed_candidate_id": remove_id,
                        "added_candidate_id": add_id,
                        "covered_target_count": -trial_key[0],
                        "selected_satellite_count": selection_cost(trial_ids),
                    }
        if best_ids != selected_ids:
            selected_ids = best_ids
            replacement_rounds.append(best_replacement or {})
            changed = True

    selected_candidate_ids = list(selected_ids)
    best_mask = selection_mask(selected_ids)
    best_cost = selection_cost(selected_ids)
    best_quality = selection_quality(selected_ids)
    best_partial_gaps = partial_gap_by_target(selected_ids)
    best_partial_worst_gap, best_partial_total_gap = selection_partial_quality(
        selected_ids
    )
    selection = _selection_from_refined_profiles(
        case=case,
        coverage=coverage,
        original=original,
        selected_candidate_ids=selected_candidate_ids,
        profiles=profiles,
    )
    covered_targets = [
        target_id for target_id in target_ids if best_mask & target_bit[target_id]
    ]
    summary = {
        "strategy": "refined_max_coverage_repack",
        "profile_count": len(profiles),
        "selected_candidate_ids": selected_candidate_ids,
        "selected_candidate_count": len(selected_candidate_ids),
        "selected_satellite_count": best_cost,
        "covered_target_count": len(covered_targets),
        "covered_target_ids": covered_targets,
        "uncovered_target_ids": [
            target_id for target_id in target_ids if not best_mask & target_bit[target_id]
        ],
        "full_coverage_possible": best_mask == full_mask,
        "quality_sum_hours": best_quality,
        "partial_worst_gap_hours": best_partial_worst_gap,
        "partial_total_gap_hours": best_partial_total_gap,
        "partial_gap_by_target": best_partial_gaps,
        "greedy_rounds": greedy_rounds,
        "replacement_rounds": replacement_rounds,
        "selected_profiles": [
            profiles[candidate_id].as_dict()
            for candidate_id in selected_candidate_ids
            if candidate_id in profiles
        ],
        "top_profiles": [
            profile.as_dict()
            for profile in profile_items[: min(20, len(profile_items))]
        ],
    }
    return selection, summary


def repair_selection_with_phased_opportunities(
    *,
    case: RevisitCase,
    coverage: CoverageSummary,
    selection: SelectionSummary,
    initial_gap_summary: dict[str, dict[str, float]],
    config: SchedulingConfig,
) -> SelectionRepairResult:
    high_gap_targets = _initial_high_gap_targets(initial_gap_summary)
    if not high_gap_targets:
        return SelectionRepairResult(
            selection=selection,
            initial_selection=selection,
            initial_high_gap_target_ids=(),
            rounds=(),
            target_diagnostics={},
            blocker=None,
            config=config,
            refined_repacking_summary={},
        )

    quality_by_pair = _candidate_quality_cache(
        case=case,
        coverage=coverage,
        target_ids=sorted(case.targets),
        config=config,
    )
    profiles = _refined_candidate_profiles(
        case=case,
        coverage=coverage,
        quality_by_pair=quality_by_pair,
    )
    repacked_selection, repacking_summary = _repack_selection_with_refined_profiles(
        case=case,
        coverage=coverage,
        original=selection,
        profiles=profiles,
        quality_by_pair=quality_by_pair,
    )
    diagnostics: dict[str, dict[str, Any]] = {}
    for target_id in high_gap_targets:
        assignment = selection.target_assignments.get(target_id)
        qualities = [
            quality
            for (candidate_id, quality_target_id), quality in quality_by_pair.items()
            if quality_target_id == target_id
        ]
        final_assignment = repacked_selection.target_assignments.get(target_id)
        final_quality = (
            None
            if final_assignment is None
            else quality_by_pair.get((final_assignment.candidate_id, target_id))
        )
        diagnostics[target_id] = {
            "initial_assignment": None if assignment is None else assignment.as_dict(),
            "initial_actual_max_gap_hours": initial_gap_summary[target_id][
                "max_revisit_gap_hours"
            ],
            "expected_revisit_period_hours": initial_gap_summary[target_id][
                "expected_revisit_period_hours"
            ],
            "best_alternates": _top_alternates(
                qualities,
                config.max_repair_alternates_per_target,
            ),
            "chosen_candidate_id": (
                None if final_assignment is None else final_assignment.candidate_id
            ),
            "chosen_estimated_quality": (
                None if final_quality is None else final_quality.as_dict()
            ),
        }

    final_estimated_gap = {
        target_id: (
            quality_by_pair[
                (
                    repacked_selection.target_assignments[target_id].candidate_id,
                    target_id,
                )
            ].max_gap_hours
            if target_id in repacked_selection.target_assignments
            and (
                repacked_selection.target_assignments[target_id].candidate_id,
                target_id,
            )
            in quality_by_pair
            else initial_gap_summary[target_id]["max_revisit_gap_hours"]
        )
        for target_id in high_gap_targets
    }
    rounds: list[SelectionRepairRound] = []
    improved_targets = [
        target_id
        for target_id in high_gap_targets
        if final_estimated_gap[target_id] + NUMERICAL_EPS
        < initial_gap_summary[target_id]["max_revisit_gap_hours"]
    ]
    coverage_reduced = (
        len(repacked_selection.target_assignments) < len(selection.target_assignments)
    )
    high_gap_worsened = any(
        final_estimated_gap[target_id]
        > initial_gap_summary[target_id]["max_revisit_gap_hours"] + NUMERICAL_EPS
        for target_id in high_gap_targets
    )
    use_repacked = (
        repacked_selection != selection
        and bool(improved_targets)
        and not coverage_reduced
        and not high_gap_worsened
        and repacked_selection.within_satellite_budget
    )
    final_selection = repacked_selection if use_repacked else selection

    if use_repacked:
        rounds.append(
            SelectionRepairRound(
                round_index=0,
                candidate_id="__refined_set_repack__",
                improved_target_ids=tuple(sorted(improved_targets)),
                previous_satellite_count=selection.total_required_satellites,
                trial_satellite_count=repacked_selection.total_required_satellites,
                added_satellites=(
                    repacked_selection.total_required_satellites
                    - selection.total_required_satellites
                ),
                estimated_worst_before_hours=max(
                    initial_gap_summary[target_id]["max_revisit_gap_hours"]
                    for target_id in high_gap_targets
                ),
                estimated_worst_after_hours=max(
                    final_estimated_gap[target_id] for target_id in high_gap_targets
                ),
                estimated_total_improvement_hours=sum(
                    initial_gap_summary[target_id]["max_revisit_gap_hours"]
                    - final_estimated_gap[target_id]
                    for target_id in improved_targets
                ),
            )
        )
    unresolved = [
        target_id
        for target_id in high_gap_targets
        if final_estimated_gap[target_id]
        > case.targets[target_id].expected_revisit_period_hours + NUMERICAL_EPS
    ]
    if use_repacked:
        blocker = None if not unresolved else "refined_repack_incomplete"
    elif coverage_reduced:
        blocker = "refined_repack_would_reduce_assignment_coverage"
    elif high_gap_worsened:
        blocker = "refined_repack_would_worsen_high_gap_targets"
    elif repacked_selection != selection and not improved_targets:
        blocker = "refined_repack_not_improving"
    else:
        blocker = None if not unresolved else "refined_repack_incomplete"
    if not rounds and blocker is None:
        blocker = "no_repair_needed"

    for target_id in high_gap_targets:
        diagnostics[target_id]["final_estimated_max_gap_hours"] = (
            final_estimated_gap[target_id]
            if use_repacked
            else initial_gap_summary[target_id]["max_revisit_gap_hours"]
        )
        diagnostics[target_id]["final_assignment"] = (
            final_selection.target_assignments[target_id].as_dict()
            if target_id in final_selection.target_assignments
            else None
        )

    repacking_summary = {
        **repacking_summary,
        "accepted": use_repacked,
        "rejected_reason": None if use_repacked else blocker,
        "original_assigned_target_count": len(selection.target_assignments),
        "repacked_assigned_target_count": len(repacked_selection.target_assignments),
        "returned_candidate_ids": [
            item.candidate.candidate_id for item in final_selection.selected_candidates
        ],
    }
    return SelectionRepairResult(
        selection=final_selection,
        initial_selection=selection,
        initial_high_gap_target_ids=tuple(high_gap_targets),
        rounds=tuple(rounds),
        target_diagnostics=diagnostics,
        blocker=blocker,
        config=config,
        refined_repacking_summary=repacking_summary,
    )


def _assigned_targets_by_candidate(
    selection: SelectionSummary,
) -> dict[str, list[str]]:
    assigned: dict[str, list[str]] = {}
    for target_id, assignment in sorted(selection.target_assignments.items()):
        assigned.setdefault(assignment.candidate_id, []).append(target_id)
    return assigned


def _opportunity_targets_by_candidate(
    *,
    coverage: CoverageSummary,
    selection: SelectionSummary,
    include_opportunistic: bool = False,
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    assigned_by_candidate = _assigned_targets_by_candidate(selection)
    target_ids_by_candidate: dict[str, list[str]] = {}
    opportunistic_pairs: list[tuple[str, str]] = []

    for selected in sorted(
        selection.selected_candidates,
        key=lambda item: item.candidate.candidate_id,
    ):
        candidate_id = selected.candidate.candidate_id
        assigned_targets = set(assigned_by_candidate.get(candidate_id, []))
        target_ids = sorted(assigned_targets)
        target_ids_by_candidate[candidate_id] = target_ids
        _ = include_opportunistic

    return target_ids_by_candidate, {
        "assigned_pair_count": sum(
            len(target_ids) for target_ids in assigned_by_candidate.values()
        ),
        "opportunistic_pair_count": len(opportunistic_pairs),
        "opportunistic_target_ids": sorted(
            {target_id for _, target_id in opportunistic_pairs}
        ),
        "opportunistic_pairs": [
            {"candidate_id": candidate_id, "target_id": target_id}
            for candidate_id, target_id in opportunistic_pairs[:50]
        ],
        "opportunistic_pair_debug_limit": 50,
        "target_ids_by_candidate": {
            candidate_id: target_ids
            for candidate_id, target_ids in sorted(target_ids_by_candidate.items())
        },
        "include_opportunistic": False,
    }


def _build_satellite_opportunity_worker(
    args: tuple[
        RevisitCase,
        SelectionSummary,
        SatellitePlan,
        list[tuple[str, list[CoarseVisibilityHint]]],
        SchedulingConfig,
        bool,
    ],
) -> tuple[list[ObservationAction], int, dict[str, int]]:
    case, selection, satellite, target_hint_items, config, use_numerical = args
    state_provider = (
        NumericalJ2StateProvider(case, [satellite]) if use_numerical else None
    )
    opportunities: list[ObservationAction] = []
    considered = 0
    rejection_reasons: dict[str, int] = {}
    for target_id, hints in target_hint_items:
        target_opportunities, target_considered, target_rejections, _ = (
            _refined_opportunities_for_satellite_target(
                case=case,
                selection=selection,
                satellite=satellite,
                target_id=target_id,
                hints=hints,
                config=config,
                state_provider=state_provider,
            )
        )
        opportunities.extend(target_opportunities)
        considered += target_considered
        for reason, count in target_rejections.items():
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + count
    return opportunities, considered, rejection_reasons


def build_opportunities(
    *,
    case: RevisitCase,
    coverage: CoverageSummary,
    selection: SelectionSummary,
    satellites: list[SatellitePlan],
    config: SchedulingConfig,
    include_opportunistic: bool = False,
) -> tuple[list[ObservationAction], int, dict[str, Any]]:
    horizon_sec = (case.horizon_end - case.horizon_start).total_seconds()
    target_ids_by_candidate, opportunity_target_summary = (
        _opportunity_targets_by_candidate(
            coverage=coverage,
            selection=selection,
            include_opportunistic=include_opportunistic,
        )
    )
    hints_by_key = _coarse_hints_by_key(case=case, coverage=coverage)
    satellites_by_candidate: dict[str, list[SatellitePlan]] = {}
    for satellite in satellites:
        satellites_by_candidate.setdefault(satellite.candidate_id, []).append(satellite)

    opportunities: list[ObservationAction] = []
    considered = 0
    rejection_reasons: dict[str, int] = {}
    _ = horizon_sec

    work_items: list[
        tuple[
            RevisitCase,
            SelectionSummary,
            SatellitePlan,
            list[tuple[str, list[CoarseVisibilityHint]]],
            SchedulingConfig,
            bool,
        ]
    ] = []
    for candidate_id, target_ids in sorted(target_ids_by_candidate.items()):
        target_hint_items = [
            (target_id, hints_by_key.get((candidate_id, target_id), []))
            for target_id in target_ids
        ]
        for satellite in satellites_by_candidate.get(candidate_id, []):
            work_items.append(
                (
                    case,
                    selection,
                    satellite,
                    target_hint_items,
                    config,
                    config.use_numerical_refinement,
                )
            )
    worker_count = _resolved_worker_count(
        config.opportunity_worker_count,
        len(work_items),
    )
    if worker_count > 1:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            results = list(executor.map(_build_satellite_opportunity_worker, work_items))
    else:
        results = [_build_satellite_opportunity_worker(item) for item in work_items]
    for worker_opportunities, worker_considered, worker_rejections in results:
        opportunities.extend(worker_opportunities)
        considered += worker_considered
        for reason, count in worker_rejections.items():
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + count
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
        {
            "work_item_count": len(work_items),
            "worker_count": worker_count,
            "coarse_hint_realizations_tried": considered,
            "refined_opportunity_count": len(opportunities),
            "rejection_reasons": rejection_reasons,
            "opportunity_target_summary": opportunity_target_summary,
        },
    )


def _max_gap_sec(case: RevisitCase, target_id: str, midpoints: list[datetime]) -> float:
    times = [case.horizon_start, *sorted(set(midpoints)), case.horizon_end]
    return max((right - left).total_seconds() for left, right in zip(times, times[1:]))


def _gap_profile_sec(case: RevisitCase, midpoints: list[datetime]) -> tuple[float, ...]:
    times = [case.horizon_start, *sorted(set(midpoints)), case.horizon_end]
    gaps = [
        (right - left).total_seconds()
        for left, right in zip(times, times[1:])
    ]
    return tuple(sorted(gaps, reverse=True))


def _target_vector_eci(
    case: RevisitCase,
    selection: SelectionSummary,
    satellite: SatellitePlan,
    target_id: str,
    instant: datetime,
    state_provider: NumericalJ2StateProvider | None = None,
) -> np.ndarray:
    mission_offset = (instant - case.horizon_start).total_seconds()
    state = np.asarray(
        satellite_state_at(
            case,
            selection,
            satellite,
            mission_offset,
            state_provider=state_provider,
        )
    )
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
    state_provider: NumericalJ2StateProvider | None = None,
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
            state_provider=state_provider,
        )
        current_vector = _target_vector_eci(
            case,
            selection,
            satellite,
            current.target_id,
            current.midpoint,
            state_provider=state_provider,
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
    initial_selected: list[ObservationAction] | None = None,
    allowed_target_ids: set[str] | None = None,
    state_provider: NumericalJ2StateProvider | None = None,
) -> list[ObservationAction]:
    selected: list[ObservationAction] = [] if initial_selected is None else list(initial_selected)
    used_indexes: set[int] = set()
    midpoints_by_target: dict[str, list[datetime]] = {target_id: [] for target_id in case.targets}
    for action in selected:
        midpoints_by_target.setdefault(action.target_id, []).append(action.midpoint)
    satellites_by_id = {satellite.satellite_id: satellite for satellite in satellites}
    min_improvement_sec = max(0.0, config.min_gap_improvement_sec)

    while len(selected) < config.max_actions:
        best: tuple[tuple[Any, ...], int, ObservationAction] | None = None
        for index, opportunity in enumerate(opportunities):
            if index in used_indexes:
                continue
            if (
                allowed_target_ids is not None
                and opportunity.target_id not in allowed_target_ids
            ):
                continue
            if not _compatible_with_selected(
                case=case,
                selection=selection,
                satellites_by_id=satellites_by_id,
                action=opportunity,
                selected=selected,
                state_provider=state_provider,
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


def _target_revisit_satisfied(
    case: RevisitCase,
    target_id: str,
    midpoints: list[datetime],
) -> bool:
    threshold_sec = case.targets[target_id].expected_revisit_period_hours * 3600.0
    return _max_gap_sec(case, target_id, midpoints) <= threshold_sec + NUMERICAL_EPS


def _select_assigned_target_actions(
    *,
    case: RevisitCase,
    selection: SelectionSummary,
    satellites_by_id: dict[str, SatellitePlan],
    target_id: str,
    opportunities: list[ObservationAction],
    selected: list[ObservationAction],
    used_indexes: set[int],
    config: SchedulingConfig,
    state_provider: NumericalJ2StateProvider | None = None,
) -> tuple[list[ObservationAction], dict[str, Any]]:
    chosen_for_target: list[ObservationAction] = [
        action for action in selected if action.target_id == target_id
    ]
    target = case.targets[target_id]
    iterations = 0
    while (
        len(selected) < config.max_actions
        and not _target_revisit_satisfied(case, target_id, [a.midpoint for a in chosen_for_target])
    ):
        existing_midpoints = [action.midpoint for action in chosen_for_target]
        old_profile = _gap_profile_sec(case, existing_midpoints)
        best: tuple[tuple[Any, ...], int, ObservationAction] | None = None
        for index, opportunity in enumerate(opportunities):
            if index in used_indexes or opportunity.target_id != target_id:
                continue
            if not _compatible_with_selected(
                case=case,
                selection=selection,
                satellites_by_id=satellites_by_id,
                action=opportunity,
                selected=selected,
                state_provider=state_provider,
            ):
                continue
            new_profile = _gap_profile_sec(
                case,
                [*existing_midpoints, opportunity.midpoint],
            )
            if new_profile >= old_profile:
                continue
            score = (
                new_profile,
                opportunity.midpoint,
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
        chosen_for_target.append(action)
        iterations += 1

    midpoints = [action.midpoint for action in chosen_for_target]
    final_gap_sec = _max_gap_sec(case, target_id, midpoints)
    return chosen_for_target, {
        "target_id": target_id,
        "selected_action_count": len(chosen_for_target),
        "final_max_gap_hours": final_gap_sec / 3600.0,
        "expected_revisit_period_hours": target.expected_revisit_period_hours,
        "revisit_satisfied": _target_revisit_satisfied(case, target_id, midpoints),
        "iterations": iterations,
    }


def select_assigned_first_actions(
    *,
    case: RevisitCase,
    selection: SelectionSummary,
    satellites: list[SatellitePlan],
    opportunities: list[ObservationAction],
    config: SchedulingConfig,
    state_provider: NumericalJ2StateProvider | None = None,
) -> tuple[list[ObservationAction], dict[str, Any]]:
    satellites_by_id = {satellite.satellite_id: satellite for satellite in satellites}
    assigned_opportunities_by_target: dict[str, list[ObservationAction]] = {}
    for opportunity in opportunities:
        assignment = selection.target_assignments.get(opportunity.target_id)
        if assignment is None or assignment.candidate_id != opportunity.candidate_id:
            continue
        assigned_opportunities_by_target.setdefault(
            opportunity.target_id,
            [],
        ).append(opportunity)

    target_order = sorted(
        selection.target_assignments,
        key=lambda target_id: (
            len(assigned_opportunities_by_target.get(target_id, [])),
            case.targets[target_id].expected_revisit_period_hours,
            target_id,
        ),
    )
    selected: list[ObservationAction] = []
    used_indexes: set[int] = set()
    target_summaries: dict[str, Any] = {}
    for target_id in target_order:
        target_opportunities = assigned_opportunities_by_target.get(target_id, [])
        if not target_opportunities:
            target_summaries[target_id] = {
                "target_id": target_id,
                "selected_action_count": 0,
                "available_opportunity_count": 0,
                "final_max_gap_hours": (
                    case.horizon_end - case.horizon_start
                ).total_seconds()
                / 3600.0,
                "expected_revisit_period_hours": case.targets[
                    target_id
                ].expected_revisit_period_hours,
                "revisit_satisfied": False,
                "iterations": 0,
            }
            continue
        before = len(selected)
        _, summary = _select_assigned_target_actions(
            case=case,
            selection=selection,
            satellites_by_id=satellites_by_id,
            target_id=target_id,
            opportunities=opportunities,
            selected=selected,
            used_indexes=used_indexes,
            config=config,
            state_provider=state_provider,
        )
        summary["available_opportunity_count"] = len(target_opportunities)
        summary["added_action_count"] = len(selected) - before
        target_summaries[target_id] = summary

    assigned_action_count = len(selected)
    failed_assigned = sorted(
        target_id
        for target_id, summary in target_summaries.items()
        if not summary["revisit_satisfied"]
    )
    return (
        sorted(
            selected,
            key=lambda item: (item.start, item.end, item.satellite_id, item.target_id),
        ),
        {
            "strategy": "selected_certified_assignments_only",
            "assigned_target_count": len(target_order),
            "assigned_action_count": assigned_action_count,
            "opportunistic_target_ids": [],
            "opportunistic_action_count": 0,
            "failed_assigned_target_ids": failed_assigned,
            "target_summaries": target_summaries,
        },
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
    state_provider: NumericalJ2StateProvider | None = None,
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
            elevation_safety_margin_deg=config.elevation_safety_margin_deg,
            range_safety_margin_m=config.range_safety_margin_m,
            off_nadir_safety_margin_deg=config.off_nadir_safety_margin_deg,
            state_provider=state_provider,
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
                state_provider=state_provider,
            )
            current_vector = _target_vector_eci(
                case,
                selection,
                satellite,
                current.target_id,
                current.midpoint,
                state_provider=state_provider,
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
    start_time = time.perf_counter()
    stage_start = start_time
    satellites = generate_phased_satellites(case, selection)
    satellite_generation_sec = time.perf_counter() - stage_start
    stage_start = time.perf_counter()
    state_provider = (
        NumericalJ2StateProvider(case, satellites)
        if config.use_numerical_refinement
        else None
    )
    state_provider_sec = time.perf_counter() - stage_start
    stage_start = time.perf_counter()
    opportunities, considered, opportunity_refinement_summary = build_opportunities(
        case=case,
        coverage=coverage,
        selection=selection,
        satellites=satellites,
        config=config,
        include_opportunistic=False,
    )
    opportunity_generation_sec = time.perf_counter() - stage_start
    stage_start = time.perf_counter()
    actions, action_selection_summary = select_assigned_first_actions(
        case=case,
        selection=selection,
        satellites=satellites,
        opportunities=opportunities,
        config=config,
        state_provider=state_provider,
    )
    action_selection_sec = time.perf_counter() - stage_start
    stage_start = time.perf_counter()
    validation = validate_solution_locally(
        case=case,
        selection=selection,
        satellites=satellites,
        actions=actions,
        config=config,
        state_provider=state_provider,
    )
    validation_sec = time.perf_counter() - stage_start
    target_gap_summary = compute_target_gap_summary(case, actions)
    total_sec = time.perf_counter() - start_time
    return SolutionBuildSummary(
        satellites=satellites,
        actions=actions,
        opportunities_considered=considered,
        opportunities_visibility_valid=len(opportunities),
        opportunity_refinement_summary={
            **opportunity_refinement_summary,
            "action_selection_summary": action_selection_summary,
        },
        target_gap_summary=target_gap_summary,
        validation=validation,
        config=config,
        timing_seconds={
            "satellite_generation": satellite_generation_sec,
            "numerical_state_provider": state_provider_sec,
            "opportunity_generation": opportunity_generation_sec,
            "action_selection": action_selection_sec,
            "local_validation": validation_sec,
            "total": total_sec,
        },
    )
