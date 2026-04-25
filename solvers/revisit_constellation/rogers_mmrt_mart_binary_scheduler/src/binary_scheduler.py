"""Binary observation-window scheduler with bounded fallbacks."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
from itertools import combinations
import math

import brahe
import numpy as np

from .case_io import RevisitCase, SolverConfig, iso_z
from .observation_windows import (
    ObservationWindow,
    WindowEnumerationResult,
    _angle_between_deg,
)
from .propagation import datetime_to_epoch, ensure_brahe_ready, force_model_config
from .slot_library import OrbitSlot


NUMERICAL_EPS = 1.0e-9


@dataclass(frozen=True)
class TargetScheduleStats:
    target_id: str
    observation_count: int
    max_revisit_gap_hours: float
    mean_revisit_gap_hours: float
    expected_revisit_hours: float
    threshold_excess_hours: float

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "target_id": self.target_id,
            "observation_count": self.observation_count,
            "max_revisit_gap_hours": self.max_revisit_gap_hours,
            "mean_revisit_gap_hours": self.mean_revisit_gap_hours,
            "expected_revisit_hours": self.expected_revisit_hours,
            "threshold_excess_hours": self.threshold_excess_hours,
        }


@dataclass(frozen=True)
class ScheduleEvaluation:
    capped_max_revisit_gap_hours: float
    max_revisit_gap_hours: float
    sum_mean_revisit_gap_hours: float
    threshold_excess_hours: float
    threshold_violations: int
    total_observations: int
    target_stats: tuple[TargetScheduleStats, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "capped_max_revisit_gap_hours": self.capped_max_revisit_gap_hours,
            "max_revisit_gap_hours": self.max_revisit_gap_hours,
            "sum_mean_revisit_gap_hours": self.sum_mean_revisit_gap_hours,
            "threshold_excess_hours": self.threshold_excess_hours,
            "threshold_violations": self.threshold_violations,
            "total_observations": self.total_observations,
            "target_stats": [stats.to_dict() for stats in self.target_stats],
        }


@dataclass(frozen=True)
class BinaryScheduleResult:
    backend: str
    fallback_reason: str | None
    selected_window_ids: tuple[str, ...]
    selected_window_indices: tuple[int, ...]
    selected_windows: tuple[ObservationWindow, ...]
    evaluation: ScheduleEvaluation
    conflict_edge_count: int
    transition_conflict_edge_count: int
    model_size: dict[str, int]
    rounding_summary: dict[str, object]
    backend_status: dict[str, object] = field(default_factory=dict)
    constraint_summary: dict[str, object] = field(default_factory=dict)

    def to_summary(self) -> dict[str, object]:
        backend_report = (
            self.backend_status
            if self.backend_status
            else _scheduler_backend_report(self.backend, self.fallback_reason)
        )
        return {
            "backend": self.backend,
            "fallback_reason": self.fallback_reason,
            "backend_report": backend_report,
            "selected_window_ids": list(self.selected_window_ids),
            "selected_window_indices": list(self.selected_window_indices),
            "selected_count": len(self.selected_windows),
            "evaluation": self.evaluation.to_dict(),
            "conflict_edge_count": self.conflict_edge_count,
            "transition_conflict_edge_count": self.transition_conflict_edge_count,
            "model_size": self.model_size,
            "constraint_summary": self.constraint_summary,
            "rounding_summary": self.rounding_summary,
        }


@dataclass(frozen=True)
class ResourcePrefixConstraint:
    satellite_id: str
    checkpoint_index: int
    checkpoint_window_id: str
    prefix_costs_wh: tuple[tuple[int, float], ...]
    idle_energy_wh: float
    available_wh: float

    def to_summary(self) -> dict[str, object]:
        return {
            "satellite_id": self.satellite_id,
            "checkpoint_window_id": self.checkpoint_window_id,
            "checkpoint_index": self.checkpoint_index,
            "prefix_window_count": len(self.prefix_costs_wh),
            "idle_energy_wh": self.idle_energy_wh,
            "selected_window_energy_wh": sum(cost for _index, cost in self.prefix_costs_wh),
            "available_wh": self.available_wh,
        }


@dataclass(frozen=True)
class SchedulerConstraintModel:
    edges: frozenset[tuple[int, int]]
    transition_edge_count: int
    edge_count_by_family: dict[str, int]
    resource_prefix_constraints: tuple[ResourcePrefixConstraint, ...]
    summary: dict[str, object]


def _scheduler_backend_report(backend: str, fallback_reason: str | None) -> dict[str, object]:
    reason = fallback_reason or ""
    return {
        "backend_name": "pulp_cbc" if backend in {"pulp_binary", "relaxed_rounding"} else backend,
        "requested_backend": backend,
        "exact_required": backend == "pulp_binary",
        "pulp_available": importlib.util.find_spec("pulp") is not None,
        "available": None if backend in {"exact_fallback", "greedy_fallback", "none"} else "pulp_not_available" not in reason,
        "attempted": backend in {"pulp_binary", "relaxed_rounding"} and "pulp_not_available" not in reason,
        "solved": backend == "pulp_binary" and not fallback_reason,
        "solver_status": None,
        "failure_reason": fallback_reason,
        "solved_with_binary_milp": backend == "pulp_binary" and not fallback_reason,
        "used_exact_fallback": backend == "exact_fallback" or "exact_fallback" in reason,
        "used_relaxed_rounding": backend == "relaxed_rounding"
        or "relaxed_rounding" in reason,
        "used_greedy_fallback": backend == "greedy_fallback"
        or "greedy_fallback" in reason,
        "fallback_reason": fallback_reason,
    }


def _scheduler_backend_status(
    *,
    requested_backend: str,
    active_backend: str,
    available: bool | None,
    attempted: bool,
    solved: bool,
    failure_reason: str | None,
    solver_status: str | None = None,
) -> dict[str, object]:
    reason = failure_reason or ""
    return {
        "backend_name": "pulp_cbc",
        "requested_backend": requested_backend,
        "active_backend": active_backend,
        "exact_required": requested_backend == "pulp_binary",
        "pulp_available": importlib.util.find_spec("pulp") is not None,
        "available": available,
        "attempted": attempted,
        "solved": solved,
        "solver_status": solver_status,
        "failure_reason": failure_reason,
        "solved_with_binary_milp": active_backend == "pulp_binary" and solved,
        "used_exact_fallback": active_backend == "exact_fallback" or "exact_fallback" in reason,
        "used_relaxed_rounding": active_backend == "relaxed_rounding"
        or "relaxed_rounding" in reason,
        "used_greedy_fallback": active_backend == "greedy_fallback"
        or "greedy_fallback" in reason,
        "fallback_reason": failure_reason,
    }


def _window_profit(window: ObservationWindow) -> float:
    return (
        1000.0 * window.estimated_max_gap_reduction_hours
        + window.estimated_mean_gap_reduction_hours
    )


def _overlap(left: ObservationWindow, right: ObservationWindow) -> bool:
    return left.start < right.end and right.start < left.end


def build_conflict_edges(
    windows: tuple[ObservationWindow, ...], min_transition_gap_sec: float
) -> tuple[frozenset[tuple[int, int]], int]:
    id_to_index = {window.window_id: index for index, window in enumerate(windows)}
    edges: set[tuple[int, int]] = set()
    transition_edges = 0

    for left_index, window in enumerate(windows):
        for conflict_id in window.conflict_ids:
            right_index = id_to_index.get(conflict_id)
            if right_index is None or right_index == left_index:
                continue
            edges.add(tuple(sorted((left_index, right_index))))

    if min_transition_gap_sec > 0.0:
        for left_index, left in enumerate(windows):
            for right_index in range(left_index + 1, len(windows)):
                right = windows[right_index]
                if left.satellite_id != right.satellite_id:
                    continue
                if _overlap(left, right):
                    continue
                gap_sec = min(
                    abs((right.start - left.end).total_seconds()),
                    abs((left.start - right.end).total_seconds()),
                )
                if gap_sec < min_transition_gap_sec:
                    edge = (left_index, right_index)
                    if edge not in edges:
                        transition_edges += 1
                    edges.add(edge)
    return frozenset(edges), transition_edges


def _slew_time_sec(angle_deg: float, max_velocity: float, max_accel: float) -> float:
    angle_deg = max(0.0, angle_deg)
    if angle_deg <= NUMERICAL_EPS:
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


def _propagators_by_satellite(
    case: RevisitCase,
    slots: tuple[OrbitSlot, ...],
    windows: tuple[ObservationWindow, ...],
) -> dict[str, brahe.NumericalOrbitPropagator]:
    ensure_brahe_ready()
    start_epoch = datetime_to_epoch(case.horizon_start)
    end_epoch = datetime_to_epoch(case.horizon_end)
    force_config = force_model_config()
    propagators: dict[str, brahe.NumericalOrbitPropagator] = {}
    for window in windows:
        if window.satellite_id in propagators:
            continue
        if window.slot_index < 0 or window.slot_index >= len(slots):
            continue
        slot = slots[window.slot_index]
        propagator = brahe.NumericalOrbitPropagator.from_eci(
            start_epoch,
            np.asarray(slot.state_eci_m_mps, dtype=float),
            force_config=force_config,
        )
        propagator.propagate_to(end_epoch)
        propagators[window.satellite_id] = propagator
    return propagators


def _add_edge(
    edges: set[tuple[int, int]],
    counts: dict[str, int],
    left_index: int,
    right_index: int,
    family: str,
) -> None:
    if left_index == right_index:
        return
    edge = tuple(sorted((left_index, right_index)))
    counts[family] = counts.get(family, 0) + 1
    edges.add(edge)


def _resource_cost_wh(case: RevisitCase, window: ObservationWindow) -> float:
    sensor = case.satellite_model.sensor
    attitude = case.satellite_model.attitude_model
    observation_wh = (sensor.obs_discharge_rate_w * window.duration_sec) / 3600.0
    maneuver_guard_wh = (
        attitude.maneuver_discharge_rate_w * attitude.settling_time_sec
    ) / 3600.0
    return observation_wh + maneuver_guard_wh


def _build_resource_prefix_constraints(
    case: RevisitCase,
    config: SolverConfig,
    windows: tuple[ObservationWindow, ...],
) -> tuple[ResourcePrefixConstraint, ...]:
    resource = case.satellite_model.resource_model
    available_wh = resource.initial_battery_wh - config.scheduler_resource_margin_wh
    if available_wh < 0.0:
        available_wh = 0.0
    by_satellite: dict[str, list[tuple[int, ObservationWindow]]] = {}
    for index, window in enumerate(windows):
        by_satellite.setdefault(window.satellite_id, []).append((index, window))

    constraints: list[ResourcePrefixConstraint] = []
    for satellite_id, indexed_windows in sorted(by_satellite.items()):
        ordered = sorted(indexed_windows, key=lambda item: (item[1].end, item[1].window_id))
        for checkpoint_index, checkpoint in ordered:
            prefix_costs = tuple(
                (index, _resource_cost_wh(case, window))
                for index, window in ordered
                if window.end <= checkpoint.end
            )
            idle_energy_wh = (
                resource.idle_discharge_rate_w
                * max(0.0, (checkpoint.end - case.horizon_start).total_seconds())
            ) / 3600.0
            constraints.append(
                ResourcePrefixConstraint(
                    satellite_id=satellite_id,
                    checkpoint_index=checkpoint_index,
                    checkpoint_window_id=checkpoint.window_id,
                    prefix_costs_wh=prefix_costs,
                    idle_energy_wh=idle_energy_wh,
                    available_wh=available_wh,
                )
            )
    return tuple(constraints)


def build_scheduler_constraint_model(
    case: RevisitCase,
    config: SolverConfig,
    windows: tuple[ObservationWindow, ...],
    slots: tuple[OrbitSlot, ...] = (),
) -> SchedulerConstraintModel:
    id_to_index = {window.window_id: index for index, window in enumerate(windows)}
    edges: set[tuple[int, int]] = set()
    counts: dict[str, int] = {
        "same_satellite_overlap": 0,
        "duplicate_target_overlap": 0,
        "transition_gap": 0,
        "slew_gap": 0,
    }

    for left_index, window in enumerate(windows):
        for conflict_id in window.conflict_ids:
            right_index = id_to_index.get(conflict_id)
            if right_index is None or right_index <= left_index:
                continue
            right = windows[right_index]
            if window.satellite_id == right.satellite_id and _overlap(window, right):
                family = "same_satellite_overlap"
            elif window.target_id == right.target_id and _overlap(window, right):
                family = "duplicate_target_overlap"
            else:
                family = "enumerated_conflict"
            _add_edge(edges, counts, left_index, right_index, family)

    transition_edges = 0
    for left_index, left in enumerate(windows):
        for right_index in range(left_index + 1, len(windows)):
            right = windows[right_index]
            if left.satellite_id != right.satellite_id or _overlap(left, right):
                continue
            if config.scheduler_min_transition_gap_sec > 0.0:
                gap_sec = min(
                    abs((right.start - left.end).total_seconds()),
                    abs((left.start - right.end).total_seconds()),
                )
                if gap_sec < config.scheduler_min_transition_gap_sec:
                    before = len(edges)
                    _add_edge(edges, counts, left_index, right_index, "transition_gap")
                    if len(edges) > before:
                        transition_edges += 1

    slew_omission_reason: str | None = None
    slew_pair_checks = 0
    if config.scheduler_enable_slew_constraints:
        if not slots:
            slew_omission_reason = "slots_not_provided"
        else:
            target_by_id = {target.target_id: target for target in case.targets}
            propagators = _propagators_by_satellite(case, slots, windows)
            attitude = case.satellite_model.attitude_model
            max_required_gap = (
                _slew_time_sec(
                    180.0,
                    attitude.max_slew_velocity_deg_per_sec,
                    attitude.max_slew_acceleration_deg_per_sec2,
                )
                + attitude.settling_time_sec
            )
            for left_index, left in enumerate(windows):
                for right_index in range(left_index + 1, len(windows)):
                    right = windows[right_index]
                    if left.satellite_id != right.satellite_id or _overlap(left, right):
                        continue
                    earlier, later = (left, right) if left.start <= right.start else (right, left)
                    actual_gap = (later.start - earlier.end).total_seconds()
                    if actual_gap + NUMERICAL_EPS >= max_required_gap:
                        continue
                    propagator = propagators.get(earlier.satellite_id)
                    earlier_target = target_by_id.get(earlier.target_id)
                    later_target = target_by_id.get(later.target_id)
                    if propagator is None or earlier_target is None or later_target is None:
                        continue
                    slew_pair_checks += 1
                    earlier_vector = _target_vector_eci(
                        earlier_target.ecef_position_m, propagator, earlier.midpoint
                    )
                    later_vector = _target_vector_eci(
                        later_target.ecef_position_m, propagator, later.midpoint
                    )
                    angle = _angle_between_deg(earlier_vector, later_vector)
                    required_gap = _slew_time_sec(
                        angle,
                        attitude.max_slew_velocity_deg_per_sec,
                        attitude.max_slew_acceleration_deg_per_sec2,
                    ) + attitude.settling_time_sec
                    if actual_gap + NUMERICAL_EPS < required_gap:
                        _add_edge(edges, counts, left_index, right_index, "slew_gap")

    resource_constraints: tuple[ResourcePrefixConstraint, ...] = ()
    resource_omission_reason: str | None = None
    if config.scheduler_enable_resource_constraints:
        resource_constraints = _build_resource_prefix_constraints(case, config, windows)
    else:
        resource_omission_reason = "disabled_by_config"

    summary = {
        "adaptation": (
            "Scheduler constraints are conservative benchmark-local approximations. "
            "Slew conflicts use target vectors at observation midpoints; resource "
            "prefix constraints ignore sunlight credit and add a fixed settling "
            "maneuver-energy guard per selected window."
        ),
        "constraint_families": {
            "same_satellite_overlap": {
                "active": True,
                "edge_count": counts.get("same_satellite_overlap", 0),
            },
            "duplicate_target_overlap": {
                "active": True,
                "edge_count": counts.get("duplicate_target_overlap", 0),
            },
            "transition_gap": {
                "active": config.scheduler_min_transition_gap_sec > 0.0,
                "edge_count": counts.get("transition_gap", 0),
                "min_transition_gap_sec": config.scheduler_min_transition_gap_sec,
            },
            "slew_gap": {
                "active": config.scheduler_enable_slew_constraints and slew_omission_reason is None,
                "edge_count": counts.get("slew_gap", 0),
                "pair_checks": slew_pair_checks,
                "omission_reason": slew_omission_reason,
            },
            "resource_prefix": {
                "active": config.scheduler_enable_resource_constraints,
                "constraint_count": len(resource_constraints),
                "margin_wh": config.scheduler_resource_margin_wh,
                "omission_reason": resource_omission_reason,
            },
        },
        "edge_count_by_family": dict(sorted(counts.items())),
        "total_conflict_edges": len(edges),
        "resource_prefix_constraint_count": len(resource_constraints),
        "resource_prefix_constraints_preview": [
            constraint.to_summary() for constraint in resource_constraints[:10]
        ],
        "bounded_omissions": [
            reason
            for reason in (slew_omission_reason, resource_omission_reason)
            if reason is not None
        ],
    }
    return SchedulerConstraintModel(
        edges=frozenset(edges),
        transition_edge_count=transition_edges,
        edge_count_by_family=dict(sorted(counts.items())),
        resource_prefix_constraints=resource_constraints,
        summary=summary,
    )


def evaluate_schedule(
    case: RevisitCase,
    windows: tuple[ObservationWindow, ...],
    selected_indices: tuple[int, ...],
) -> ScheduleEvaluation:
    midpoints_by_target = {target.target_id: [] for target in case.targets}
    for index in selected_indices:
        window = windows[index]
        midpoints_by_target[window.target_id].append(window.midpoint)

    target_stats: list[TargetScheduleStats] = []
    capped_gaps: list[float] = []
    max_gaps: list[float] = []
    mean_gaps: list[float] = []
    threshold_excess = 0.0
    threshold_violations = 0

    for target in case.targets:
        midpoints = sorted(set(midpoints_by_target[target.target_id]))
        times = [case.horizon_start, *midpoints, case.horizon_end]
        gaps = [
            (right - left).total_seconds() / 3600.0
            for left, right in zip(times, times[1:])
        ]
        max_gap = max(gaps) if gaps else 0.0
        mean_gap = (sum(gaps) / len(gaps)) if gaps else 0.0
        excess = max(0.0, max_gap - target.expected_revisit_period_hours)
        if excess > 0.0:
            threshold_violations += 1
        threshold_excess += excess
        capped_gaps.append(max(max_gap, target.expected_revisit_period_hours))
        max_gaps.append(max_gap)
        mean_gaps.append(mean_gap)
        target_stats.append(
            TargetScheduleStats(
                target_id=target.target_id,
                observation_count=len(midpoints),
                max_revisit_gap_hours=max_gap,
                mean_revisit_gap_hours=mean_gap,
                expected_revisit_hours=target.expected_revisit_period_hours,
                threshold_excess_hours=excess,
            )
        )

    return ScheduleEvaluation(
        capped_max_revisit_gap_hours=max(capped_gaps) if capped_gaps else 0.0,
        max_revisit_gap_hours=max(max_gaps) if max_gaps else 0.0,
        sum_mean_revisit_gap_hours=sum(mean_gaps),
        threshold_excess_hours=threshold_excess,
        threshold_violations=threshold_violations,
        total_observations=len(selected_indices),
        target_stats=tuple(target_stats),
    )


def _schedule_key(
    case: RevisitCase,
    windows: tuple[ObservationWindow, ...],
    selected_indices: tuple[int, ...],
) -> tuple[float | int | tuple[int, ...], ...]:
    evaluation = evaluate_schedule(case, windows, selected_indices)
    return (
        evaluation.max_revisit_gap_hours,
        evaluation.capped_max_revisit_gap_hours,
        evaluation.sum_mean_revisit_gap_hours,
        evaluation.threshold_excess_hours,
        -evaluation.total_observations,
        selected_indices,
    )


def _independent(candidate: tuple[int, ...], edges: frozenset[tuple[int, int]]) -> bool:
    selected = set(candidate)
    return not any(left in selected and right in selected for left, right in edges)


def _resource_prefix_feasible(
    candidate: tuple[int, ...],
    constraints: tuple[ResourcePrefixConstraint, ...],
) -> bool:
    selected = set(candidate)
    for constraint in constraints:
        if constraint.checkpoint_index not in selected:
            continue
        energy_wh = constraint.idle_energy_wh + sum(
            cost for index, cost in constraint.prefix_costs_wh if index in selected
        )
        if energy_wh > constraint.available_wh + NUMERICAL_EPS:
            return False
    return True


def _resource_constraint_big_m(
    constraints: tuple[ResourcePrefixConstraint, ...],
) -> float:
    if not constraints:
        return 0.0
    largest_activity = max(
        constraint.idle_energy_wh
        + sum(cost for _index, cost in constraint.prefix_costs_wh)
        + max(0.0, constraint.available_wh)
        for constraint in constraints
    )
    return max(1.0, largest_activity)


def _constraint_feasible(
    candidate: tuple[int, ...],
    constraint_model: SchedulerConstraintModel,
) -> bool:
    return _independent(candidate, constraint_model.edges) and _resource_prefix_feasible(
        candidate,
        constraint_model.resource_prefix_constraints,
    )


def _combination_count(window_count: int, max_selected: int) -> int:
    return sum(math.comb(window_count, size) for size in range(0, max_selected + 1))


def _exact_schedule(
    case: RevisitCase,
    windows: tuple[ObservationWindow, ...],
    constraint_model: SchedulerConstraintModel,
    max_selected: int,
    max_combinations: int,
) -> tuple[tuple[int, ...] | None, int]:
    window_count = len(windows)
    count = _combination_count(window_count, min(max_selected, window_count))
    if count > max_combinations:
        return None, count

    best: tuple[int, ...] = ()
    best_key = _schedule_key(case, windows, best)
    for size in range(1, min(max_selected, window_count) + 1):
        for candidate in combinations(range(window_count), size):
            if not _constraint_feasible(candidate, constraint_model):
                continue
            key = _schedule_key(case, windows, candidate)
            if key < best_key:
                best = candidate
                best_key = key
    return best, count


def _greedy_schedule(
    case: RevisitCase,
    windows: tuple[ObservationWindow, ...],
    constraint_model: SchedulerConstraintModel,
    max_selected: int,
    seed_order: tuple[int, ...] | None = None,
) -> tuple[int, ...]:
    selected: tuple[int, ...] = ()
    remaining = list(seed_order if seed_order is not None else range(len(windows)))
    edge_lookup = {index: set() for index in range(len(windows))}
    for left, right in constraint_model.edges:
        edge_lookup[left].add(right)
        edge_lookup[right].add(left)

    while remaining and len(selected) < max_selected:
        current_key = _schedule_key(case, windows, selected)
        best_index: int | None = None
        best_key: tuple[float | int | tuple[int, ...], ...] | None = None
        for index in sorted(remaining):
            if any(index in edge_lookup[selected_index] for selected_index in selected):
                continue
            candidate = tuple(sorted((*selected, index)))
            if not _resource_prefix_feasible(
                candidate,
                constraint_model.resource_prefix_constraints,
            ):
                continue
            key = _schedule_key(case, windows, candidate)
            if key >= current_key:
                continue
            tie_key = (*key, -_window_profit(windows[index]), windows[index].window_id)
            if best_key is None or tie_key < best_key:
                best_index = index
                best_key = tie_key
        if best_index is None:
            break
        selected = tuple(sorted((*selected, best_index)))
        remaining = [
            index
            for index in remaining
            if index != best_index and index not in edge_lookup[best_index]
        ]
    return selected


def _try_pulp_binary(
    windows: tuple[ObservationWindow, ...],
    constraint_model: SchedulerConstraintModel,
    config: SolverConfig,
) -> tuple[tuple[int, ...] | None, str | None, dict[str, object]]:
    if config.scheduler_backend not in {"auto", "pulp_binary"}:
        reason = "binary_backend_disabled"
        return None, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="pulp_binary",
            available=None,
            attempted=False,
            solved=False,
            failure_reason=reason,
        )
    if len(windows) > config.scheduler_max_backend_windows:
        reason = "window_bound_exceeded"
        return None, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="pulp_binary",
            available=None,
            attempted=False,
            solved=False,
            failure_reason=reason,
        )
    if len(constraint_model.edges) > config.scheduler_max_backend_conflicts:
        reason = "conflict_bound_exceeded"
        return None, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="pulp_binary",
            available=None,
            attempted=False,
            solved=False,
            failure_reason=reason,
        )
    try:
        import pulp  # type: ignore[import-not-found]
    except ImportError:
        reason = "pulp_not_available"
        return None, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="pulp_binary",
            available=False,
            attempted=False,
            solved=False,
            failure_reason=reason,
        )

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=config.scheduler_time_limit_sec)
    if not solver.available():
        reason = "pulp_cbc_not_available"
        return None, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="pulp_binary",
            available=False,
            attempted=False,
            solved=False,
            failure_reason=reason,
        )

    model = pulp.LpProblem("rogers_binary_scheduler", pulp.LpMaximize)
    x = [pulp.LpVariable(f"z_{index}", cat="Binary") for index in range(len(windows))]
    for left, right in constraint_model.edges:
        model += x[left] + x[right] <= 1
    big_m = _resource_constraint_big_m(constraint_model.resource_prefix_constraints)
    for constraint in constraint_model.resource_prefix_constraints:
        model += (
            pulp.lpSum(cost * x[index] for index, cost in constraint.prefix_costs_wh)
            + (constraint.idle_energy_wh * x[constraint.checkpoint_index])
            <= constraint.available_wh + (big_m * (1 - x[constraint.checkpoint_index]))
        )
    model += pulp.lpSum(x) <= config.scheduler_max_selected_windows
    model += pulp.lpSum(_window_profit(window) * x[index] for index, window in enumerate(windows))
    try:
        status = model.solve(solver)
    except Exception as exc:  # pragma: no cover - depends on external solver failure mode
        reason = f"pulp_error_{type(exc).__name__}"
        return None, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="pulp_binary",
            available=True,
            attempted=True,
            solved=False,
            failure_reason=reason,
        )
    status_name = pulp.LpStatus.get(status, str(status))
    if status_name not in {"Optimal", "Feasible"}:
        reason = f"pulp_status_{status_name}"
        return None, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="pulp_binary",
            available=True,
            attempted=True,
            solved=False,
            failure_reason=reason,
            solver_status=status_name,
        )
    selected = tuple(index for index, variable in enumerate(x) if (variable.value() or 0.0) >= 0.5)
    return selected, None, _scheduler_backend_status(
        requested_backend=config.scheduler_backend,
        active_backend="pulp_binary",
        available=True,
        attempted=True,
        solved=True,
        failure_reason=None,
        solver_status=status_name,
    )


def _try_pulp_relaxed(
    windows: tuple[ObservationWindow, ...],
    constraint_model: SchedulerConstraintModel,
    config: SolverConfig,
) -> tuple[tuple[int, ...] | None, dict[str, object], str | None, dict[str, object]]:
    if config.scheduler_backend not in {"auto", "pulp_relaxed"}:
        reason = "relaxed_backend_disabled"
        return None, {}, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="relaxed_rounding",
            available=None,
            attempted=False,
            solved=False,
            failure_reason=reason,
        )
    if len(windows) > config.scheduler_max_backend_windows:
        reason = "window_bound_exceeded"
        return None, {}, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="relaxed_rounding",
            available=None,
            attempted=False,
            solved=False,
            failure_reason=reason,
        )
    if len(constraint_model.edges) > config.scheduler_max_backend_conflicts:
        reason = "conflict_bound_exceeded"
        return None, {}, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="relaxed_rounding",
            available=None,
            attempted=False,
            solved=False,
            failure_reason=reason,
        )
    try:
        import pulp  # type: ignore[import-not-found]
    except ImportError:
        reason = "pulp_not_available"
        return None, {}, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="relaxed_rounding",
            available=False,
            attempted=False,
            solved=False,
            failure_reason=reason,
        )

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=config.scheduler_time_limit_sec)
    if not solver.available():
        reason = "pulp_cbc_not_available"
        return None, {}, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="relaxed_rounding",
            available=False,
            attempted=False,
            solved=False,
            failure_reason=reason,
        )

    model = pulp.LpProblem("rogers_relaxed_scheduler", pulp.LpMaximize)
    x = [
        pulp.LpVariable(f"z_{index}", lowBound=0.0, upBound=1.0, cat="Continuous")
        for index in range(len(windows))
    ]
    for left, right in constraint_model.edges:
        model += x[left] + x[right] <= 1.0
    big_m = _resource_constraint_big_m(constraint_model.resource_prefix_constraints)
    for constraint in constraint_model.resource_prefix_constraints:
        model += (
            pulp.lpSum(cost * x[index] for index, cost in constraint.prefix_costs_wh)
            + (constraint.idle_energy_wh * x[constraint.checkpoint_index])
            <= constraint.available_wh + (big_m * (1.0 - x[constraint.checkpoint_index]))
        )
    model += pulp.lpSum(x) <= config.scheduler_max_selected_windows
    model += pulp.lpSum(_window_profit(window) * x[index] for index, window in enumerate(windows))
    try:
        status = model.solve(solver)
    except Exception as exc:  # pragma: no cover - depends on external solver failure mode
        reason = f"pulp_error_{type(exc).__name__}"
        return None, {}, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="relaxed_rounding",
            available=True,
            attempted=True,
            solved=False,
            failure_reason=reason,
        )
    status_name = pulp.LpStatus.get(status, str(status))
    if status_name not in {"Optimal", "Feasible"}:
        reason = f"pulp_relaxed_status_{status_name}"
        return None, {}, reason, _scheduler_backend_status(
            requested_backend=config.scheduler_backend,
            active_backend="relaxed_rounding",
            available=True,
            attempted=True,
            solved=False,
            failure_reason=reason,
            solver_status=status_name,
        )
    values = tuple(float(variable.value() or 0.0) for variable in x)
    order = tuple(
        index
        for index, _ in sorted(
            enumerate(values),
            key=lambda item: (-item[1], -_window_profit(windows[item[0]]), windows[item[0]].window_id),
        )
    )
    return order, {"relaxed_values": list(values), "status": status_name}, None, _scheduler_backend_status(
        requested_backend=config.scheduler_backend,
        active_backend="relaxed_rounding",
        available=True,
        attempted=True,
        solved=True,
        failure_reason=None,
        solver_status=status_name,
    )


def schedule_observation_windows(
    case: RevisitCase,
    config: SolverConfig,
    window_result: WindowEnumerationResult,
    slots: tuple[OrbitSlot, ...] = (),
) -> BinaryScheduleResult:
    windows = window_result.windows
    max_selected = min(config.scheduler_max_selected_windows, len(windows))
    constraint_model = build_scheduler_constraint_model(
        case,
        config,
        windows,
        slots,
    )
    model_size = {
        "windows": len(windows),
        "binary_variables": len(windows),
        "conflict_constraints": len(constraint_model.edges),
        "resource_prefix_constraints": len(constraint_model.resource_prefix_constraints),
        "max_selected_windows": max_selected,
    }

    selected: tuple[int, ...] | None = None
    fallback_reason: str | None = None
    backend = "pulp_binary"
    rounding_summary: dict[str, object] = {}
    backend_status: dict[str, object] = {}

    selected, fallback_reason, backend_status = _try_pulp_binary(
        windows,
        constraint_model,
        config,
    )
    if selected is None:
        if config.scheduler_backend == "pulp_binary":
            raise RuntimeError(
                "required scheduler_backend=pulp_binary failed: "
                f"{fallback_reason or 'unknown_failure'}"
            )
        exact: tuple[int, ...] | None = None
        combination_count = 0
        if config.scheduler_backend != "pulp_relaxed":
            exact, combination_count = _exact_schedule(
                case,
                windows,
                constraint_model,
                max_selected,
                config.scheduler_max_exact_combinations,
            )
        if exact is not None:
            selected = exact
            backend = "exact_fallback"
            fallback_reason = f"{fallback_reason or 'binary_backend_unavailable'};exact_fallback"
            rounding_summary = {"exact_combinations": combination_count}
            backend_status = _scheduler_backend_status(
                requested_backend=config.scheduler_backend,
                active_backend=backend,
                available=backend_status.get("available") if backend_status else None,
                attempted=bool(backend_status.get("attempted")) if backend_status else False,
                solved=False,
                failure_reason=fallback_reason,
                solver_status=(
                    str(backend_status.get("solver_status"))
                    if backend_status.get("solver_status") is not None
                    else None
                ),
            )
        else:
            relaxed_order, relaxed_summary, relaxed_reason, relaxed_status = _try_pulp_relaxed(
                windows,
                constraint_model,
                config,
            )
            if relaxed_order is not None:
                backend = "relaxed_rounding"
                selected = _greedy_schedule(
                    case,
                    windows,
                    constraint_model,
                    max_selected,
                    seed_order=relaxed_order,
                )
                fallback_reason = (
                    f"{fallback_reason or 'binary_backend_unavailable'};"
                    f"exact_combinations_{combination_count}_exceeded;relaxed_rounding"
                )
                rounding_summary = relaxed_summary
                backend_status = _scheduler_backend_status(
                    requested_backend=config.scheduler_backend,
                    active_backend=backend,
                    available=relaxed_status.get("available") if relaxed_status else None,
                    attempted=bool(relaxed_status.get("attempted")) if relaxed_status else False,
                    solved=False,
                    failure_reason=fallback_reason,
                    solver_status=(
                        str(relaxed_status.get("solver_status"))
                        if relaxed_status.get("solver_status") is not None
                        else None
                    ),
                )
            else:
                if config.scheduler_backend == "pulp_relaxed":
                    raise RuntimeError(
                        "required scheduler_backend=pulp_relaxed failed: "
                        f"{relaxed_reason or 'unknown_failure'}"
                    )
                backend = "greedy_fallback"
                selected = _greedy_schedule(case, windows, constraint_model, max_selected)
                fallback_reason = (
                    f"{fallback_reason or 'binary_backend_unavailable'};"
                    f"exact_combinations_{combination_count}_exceeded;"
                    f"{relaxed_reason or 'relaxed_unavailable'};greedy_fallback"
                )
                rounding_summary = {"exact_combinations": combination_count}
                backend_status = _scheduler_backend_status(
                    requested_backend=config.scheduler_backend,
                    active_backend=backend,
                    available=relaxed_status.get("available") if relaxed_status else None,
                    attempted=bool(relaxed_status.get("attempted")) if relaxed_status else False,
                    solved=False,
                    failure_reason=fallback_reason,
                    solver_status=(
                        str(relaxed_status.get("solver_status"))
                        if relaxed_status.get("solver_status") is not None
                        else None
                    ),
                )

    selected = tuple(sorted(selected or ()))
    selected_windows = tuple(windows[index] for index in selected)
    evaluation = evaluate_schedule(case, windows, selected)
    return BinaryScheduleResult(
        backend=backend,
        fallback_reason=fallback_reason,
        selected_window_ids=tuple(window.window_id for window in selected_windows),
        selected_window_indices=selected,
        selected_windows=selected_windows,
        evaluation=evaluation,
        conflict_edge_count=len(constraint_model.edges),
        transition_conflict_edge_count=constraint_model.transition_edge_count,
        model_size=model_size,
        rounding_summary=rounding_summary
        | {"constraint_summary": constraint_model.summary},
        backend_status=backend_status,
        constraint_summary=constraint_model.summary,
    )


def _comparison_record(
    label: str,
    backend: str,
    fallback_reason: str | None,
    case: RevisitCase,
    windows: tuple[ObservationWindow, ...],
    selected_indices: tuple[int, ...] | None,
    *,
    exact_combinations: int | None = None,
) -> dict[str, object]:
    if selected_indices is None:
        return {
            "label": label,
            "backend": backend,
            "fallback_reason": fallback_reason,
            "backend_report": _scheduler_backend_report(backend, fallback_reason),
            "available": False,
            "exact_combinations": exact_combinations,
        }
    selected_indices = tuple(sorted(selected_indices))
    evaluation = evaluate_schedule(case, windows, selected_indices)
    return {
        "label": label,
        "backend": backend,
        "fallback_reason": fallback_reason,
        "backend_report": _scheduler_backend_report(backend, fallback_reason),
        "available": True,
        "exact_combinations": exact_combinations,
        "selected_count": len(selected_indices),
        "selected_window_ids": [windows[index].window_id for index in selected_indices],
        "evaluation": evaluation.to_dict(),
    }


def compare_scheduler_modes(
    case: RevisitCase,
    config: SolverConfig,
    window_result: WindowEnumerationResult,
    current_result: BinaryScheduleResult,
    slots: tuple[OrbitSlot, ...] = (),
) -> tuple[dict[str, object], ...]:
    windows = window_result.windows
    max_selected = min(config.scheduler_max_selected_windows, len(windows))
    constraint_model = build_scheduler_constraint_model(case, config, windows, slots)
    exact, exact_count = _exact_schedule(
        case,
        windows,
        constraint_model,
        max_selected,
        config.scheduler_max_exact_combinations,
    )
    greedy = _greedy_schedule(case, windows, constraint_model, max_selected)
    records = [
        _comparison_record(
            "baseline_no_observations",
            "none",
            None,
            case,
            windows,
            (),
        ),
        _comparison_record(
            "current",
            current_result.backend,
            current_result.fallback_reason,
            case,
            windows,
            current_result.selected_window_indices,
            exact_combinations=exact_count,
        ),
        _comparison_record(
            "bounded_exact_fallback",
            "exact_fallback",
            (
                None
                if exact is not None
                else f"exact_combinations_{exact_count}_exceeded"
            ),
            case,
            windows,
            exact,
            exact_combinations=exact_count,
        ),
        _comparison_record(
            "greedy_fallback",
            "greedy_fallback",
            None,
            case,
            windows,
            greedy,
            exact_combinations=exact_count,
        ),
    ]
    return tuple(records)


def selected_windows_to_actions(
    selected_windows: tuple[ObservationWindow, ...]
) -> list[dict[str, str]]:
    return [
        {
            "action_type": "observation",
            "satellite_id": window.satellite_id,
            "target_id": window.target_id,
            "start": iso_z(window.start),
            "end": iso_z(window.end),
        }
        for window in sorted(
            selected_windows,
            key=lambda item: (item.start, item.satellite_id, item.target_id, item.window_id),
        )
    ]
