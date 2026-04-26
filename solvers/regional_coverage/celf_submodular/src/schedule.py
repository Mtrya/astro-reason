"""Solver-local schedule validation and deterministic repair."""

from __future__ import annotations

import math
import multiprocessing
import os
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


@dataclass(frozen=True, slots=True)
class LocalImprovementMove:
    move_type: str
    inserted_candidate_id: str
    removed_candidate_id: str | None
    objective_before: float
    objective_after: float
    objective_delta: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "move_type": self.move_type,
            "inserted_candidate_id": self.inserted_candidate_id,
            "removed_candidate_id": self.removed_candidate_id,
            "objective_before": self.objective_before,
            "objective_after": self.objective_after,
            "objective_delta": self.objective_delta,
        }


@dataclass(frozen=True, slots=True)
class LocalImprovementResult:
    enabled: bool
    original_candidate_ids: tuple[str, ...]
    improved_candidate_ids: tuple[str, ...]
    objective_before: float
    objective_after: float
    objective_delta: float
    accepted_moves: tuple[LocalImprovementMove, ...]
    candidate_checks: int
    rejected_infeasible_count: int
    rejected_over_budget_count: int
    rejected_non_improving_count: int
    stop_reason: str
    budget: float | None = None
    cost_before: float | None = None
    cost_after: float | None = None
    execution_mode: str = "serial"
    worker_count: int = 1
    chunk_size: int = 0
    chunk_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "original_candidate_ids": list(self.original_candidate_ids),
            "improved_candidate_ids": list(self.improved_candidate_ids),
            "objective_before": self.objective_before,
            "objective_after": self.objective_after,
            "objective_delta": self.objective_delta,
            "accepted_moves": [move.as_dict() for move in self.accepted_moves],
            "candidate_checks": self.candidate_checks,
            "rejected_infeasible_count": self.rejected_infeasible_count,
            "rejected_over_budget_count": self.rejected_over_budget_count,
            "rejected_non_improving_count": self.rejected_non_improving_count,
            "stop_reason": self.stop_reason,
            "budget": self.budget,
            "cost_before": self.cost_before,
            "cost_after": self.cost_after,
            "execution_mode": self.execution_mode,
            "worker_count": self.worker_count,
            "chunk_size": self.chunk_size,
            "chunk_count": self.chunk_count,
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


def _coverage_objective(
    candidate_ids: tuple[str, ...],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
) -> float:
    covered: set[int] = set()
    for candidate_id in candidate_ids:
        covered.update(coverage_by_candidate.get(candidate_id, ()))
    return sum(sample_weights[index] for index in covered)


def _standalone_reward(
    candidate_id: str,
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
) -> float:
    return sum(
        sample_weights[index] for index in coverage_by_candidate.get(candidate_id, ())
    )


def _coverage_counts(
    candidate_ids: tuple[str, ...],
    coverage_by_candidate: dict[str, tuple[int, ...]],
) -> Counter[int]:
    counts: Counter[int] = Counter()
    for candidate_id in candidate_ids:
        for sample_index in coverage_by_candidate.get(candidate_id, ()):
            counts[sample_index] += 1
    return counts


def _coverage_objective_from_counts(
    counts: Counter[int],
    sample_weights: dict[int, float],
) -> float:
    return sum(sample_weights[index] for index, count in counts.items() if count > 0)


def _coverage_loss_from_counts(
    candidate_id: str,
    counts: Counter[int],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
) -> float:
    return sum(
        sample_weights[index]
        for index in coverage_by_candidate.get(candidate_id, ())
        if counts[index] == 1
    )


def _insert_delta_from_counts(
    candidate_id: str,
    counts: Counter[int],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
) -> float:
    return sum(
        sample_weights[index]
        for index in coverage_by_candidate.get(candidate_id, ())
        if counts[index] <= 0
    )


def _swap_delta_from_counts(
    insert_id: str,
    remove_id: str,
    counts: Counter[int],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
) -> float:
    removed = set(coverage_by_candidate.get(remove_id, ()))
    delta = 0.0
    for index in removed:
        if counts[index] == 1:
            delta -= sample_weights[index]
    for index in coverage_by_candidate.get(insert_id, ()):
        if counts[index] <= 0 or (index in removed and counts[index] == 1):
            delta += sample_weights[index]
    return delta


def _cost_sum(
    candidate_ids: tuple[str, ...],
    cost_by_candidate: dict[str, float] | None,
) -> float | None:
    if cost_by_candidate is None:
        return None
    return sum(cost_by_candidate.get(candidate_id, 1.0) for candidate_id in candidate_ids)


def _effective_worker_count(worker_count: int | str, item_count: int) -> int:
    if item_count <= 0:
        return 1
    if worker_count == "auto":
        return max(1, min(os.cpu_count() or 1, item_count))
    return max(1, min(int(worker_count), item_count))


def _chunk_ranges(item_count: int, chunk_size: int) -> tuple[tuple[int, int], ...]:
    if item_count <= 0:
        return ()
    size = max(1, int(chunk_size))
    return tuple(
        (start, min(item_count, start + size))
        for start in range(0, item_count, size)
    )


def _candidate_valid_in_schedule(
    case: RegionalCoverageCase,
    candidates_by_id: dict[str, StripCandidate],
    candidate_ids: tuple[str, ...],
    *,
    affected_satellite_ids: set[str] | None = None,
) -> bool:
    if (
        case.manifest.max_actions_total is not None
        and len(candidate_ids) > case.manifest.max_actions_total
    ):
        return False
    known_ids = tuple(
        candidate_id for candidate_id in candidate_ids if candidate_id in candidates_by_id
    )
    grouped = _by_satellite(known_ids, candidates_by_id)
    if affected_satellite_ids is not None:
        grouped = {
            satellite_id: sequence
            for satellite_id, sequence in grouped.items()
            if satellite_id in affected_satellite_ids
        }
    if _sequence_issues(case, grouped):
        return False
    battery_issues, _ = _battery_and_duty_issues(case, grouped)
    return not battery_issues


def _local_move_key(
    move: LocalImprovementMove,
) -> tuple[float, tuple[int, str, str]]:
    tie = (
        (0, "", move.inserted_candidate_id)
        if move.move_type == "insert"
        else (1, move.removed_candidate_id or "", move.inserted_candidate_id)
    )
    return (move.objective_delta, tie)


def _better_local_move(
    left: tuple[tuple[str, ...], LocalImprovementMove] | None,
    right: tuple[tuple[str, ...], LocalImprovementMove] | None,
) -> tuple[tuple[str, ...], LocalImprovementMove] | None:
    if left is None:
        return right
    if right is None:
        return left
    if _local_move_key(right[1]) > _local_move_key(left[1]):
        return right
    return left


def _removal_key(
    candidate_id: str,
    counts: Counter[int],
    candidates_by_id: dict[str, StripCandidate],
    case: RegionalCoverageCase,
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
) -> tuple[float, float, int, int, str]:
    candidate = candidates_by_id[candidate_id]
    satellite = case.satellites[candidate.satellite_id]
    return (
        _coverage_loss_from_counts(candidate_id, counts, coverage_by_candidate, sample_weights),
        -candidate_energy_burden_wh(candidate, satellite),
        -candidate.duration_s,
        -candidate.start_offset_s,
        candidate.candidate_id,
    )


def _candidate_order_key(candidate: StripCandidate) -> tuple[int, int, float, str]:
    return (
        candidate.start_offset_s,
        candidate.duration_s,
        abs(candidate.roll_deg),
        candidate.candidate_id,
    )


_LOCAL_CASE: RegionalCoverageCase | None = None
_LOCAL_CANDIDATES_BY_ID: dict[str, StripCandidate] | None = None
_LOCAL_CANDIDATE_IDS: tuple[str, ...] = ()
_LOCAL_ACTIVE: tuple[str, ...] = ()
_LOCAL_ACTIVE_SET: set[str] = set()
_LOCAL_COUNTS: Counter[int] | None = None
_LOCAL_COVERAGE_BY_CANDIDATE: dict[str, tuple[int, ...]] | None = None
_LOCAL_SAMPLE_WEIGHTS: dict[int, float] | None = None
_LOCAL_LOSS_BY_ACTIVE: dict[str, float] = {}
_LOCAL_CURRENT_OBJECTIVE: float = 0.0
_LOCAL_MIN_OBJECTIVE_DELTA: float = 0.0
_LOCAL_COST_BY_CANDIDATE: dict[str, float] | None = None
_LOCAL_BUDGET: float | None = None
_LOCAL_ACTIVE_COST: float | None = None


def _set_local_improvement_globals(
    *,
    case: RegionalCoverageCase,
    candidates_by_id: dict[str, StripCandidate],
    candidate_ids: tuple[str, ...],
    active: tuple[str, ...],
    counts: Counter[int],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
    loss_by_active: dict[str, float],
    current_objective: float,
    min_objective_delta: float,
    cost_by_candidate: dict[str, float] | None,
    budget: float | None,
) -> None:
    global _LOCAL_CASE
    global _LOCAL_CANDIDATES_BY_ID
    global _LOCAL_CANDIDATE_IDS
    global _LOCAL_ACTIVE
    global _LOCAL_ACTIVE_SET
    global _LOCAL_COUNTS
    global _LOCAL_COVERAGE_BY_CANDIDATE
    global _LOCAL_SAMPLE_WEIGHTS
    global _LOCAL_LOSS_BY_ACTIVE
    global _LOCAL_CURRENT_OBJECTIVE
    global _LOCAL_MIN_OBJECTIVE_DELTA
    global _LOCAL_COST_BY_CANDIDATE
    global _LOCAL_BUDGET
    global _LOCAL_ACTIVE_COST
    _LOCAL_CASE = case
    _LOCAL_CANDIDATES_BY_ID = candidates_by_id
    _LOCAL_CANDIDATE_IDS = candidate_ids
    _LOCAL_ACTIVE = active
    _LOCAL_ACTIVE_SET = set(active)
    _LOCAL_COUNTS = counts
    _LOCAL_COVERAGE_BY_CANDIDATE = coverage_by_candidate
    _LOCAL_SAMPLE_WEIGHTS = sample_weights
    _LOCAL_LOSS_BY_ACTIVE = loss_by_active
    _LOCAL_CURRENT_OBJECTIVE = current_objective
    _LOCAL_MIN_OBJECTIVE_DELTA = min_objective_delta
    _LOCAL_COST_BY_CANDIDATE = cost_by_candidate
    _LOCAL_BUDGET = budget
    _LOCAL_ACTIVE_COST = _cost_sum(active, cost_by_candidate)


def _evaluate_local_improvement_range(
    bounds: tuple[int, int],
) -> tuple[
    int,
    tuple[tuple[str, ...], LocalImprovementMove] | None,
    int,
    int,
    int,
    int,
]:
    case = _LOCAL_CASE
    candidates_by_id = _LOCAL_CANDIDATES_BY_ID
    counts = _LOCAL_COUNTS
    coverage_by_candidate = _LOCAL_COVERAGE_BY_CANDIDATE
    sample_weights = _LOCAL_SAMPLE_WEIGHTS
    if (
        case is None
        or candidates_by_id is None
        or counts is None
        or coverage_by_candidate is None
        or sample_weights is None
    ):
        raise RuntimeError("local-improvement worker was not initialized")

    start_index, end_index = bounds
    best_move: tuple[tuple[str, ...], LocalImprovementMove] | None = None
    candidate_checks = 0
    rejected_infeasible = 0
    rejected_over_budget = 0
    rejected_non_improving = 0
    active = _LOCAL_ACTIVE
    active_set = _LOCAL_ACTIVE_SET
    current_objective = _LOCAL_CURRENT_OBJECTIVE
    cost_by_candidate = _LOCAL_COST_BY_CANDIDATE
    budget = _LOCAL_BUDGET
    active_cost = _LOCAL_ACTIVE_COST

    for candidate_id in _LOCAL_CANDIDATE_IDS[start_index:end_index]:
        candidate_checks += 1
        candidate_cost = (
            cost_by_candidate.get(candidate_id, 1.0)
            if cost_by_candidate is not None
            else 1.0
        )
        insert_over_budget = (
            budget is not None
            and active_cost is not None
            and active_cost + candidate_cost > budget + 1.0e-9
        )
        insert_trial = (*active, candidate_id)
        insert_report = validate_schedule(case, candidates_by_id, insert_trial)
        if insert_report.valid and not insert_over_budget:
            delta = _insert_delta_from_counts(
                candidate_id,
                counts,
                coverage_by_candidate,
                sample_weights,
            )
            if delta > _LOCAL_MIN_OBJECTIVE_DELTA:
                move = LocalImprovementMove(
                    move_type="insert",
                    inserted_candidate_id=candidate_id,
                    removed_candidate_id=None,
                    objective_before=current_objective,
                    objective_after=current_objective + delta,
                    objective_delta=delta,
                )
                best_move = _better_local_move(best_move, (insert_trial, move))
            else:
                rejected_non_improving += 1
            continue

        removal_candidates: set[str] = set()
        if insert_over_budget:
            removal_candidates.update(active)
        for issue in insert_report.issues:
            if issue.issue_type == "action_cap":
                removal_candidates.update(active)
            elif candidate_id in issue.candidate_ids:
                removal_candidates.update(
                    other_id for other_id in issue.candidate_ids if other_id in active_set
                )
        if not removal_candidates:
            rejected_infeasible += 1
            continue

        inserted_satellite_id = candidates_by_id[candidate_id].satellite_id
        for remove_id in sorted(
            removal_candidates,
            key=lambda remove_id: (
                _LOCAL_LOSS_BY_ACTIVE[remove_id],
                _candidate_order_key(candidates_by_id[remove_id]),
            ),
        ):
            if budget is not None and active_cost is not None and cost_by_candidate is not None:
                swap_cost = (
                    active_cost
                    - cost_by_candidate.get(remove_id, 1.0)
                    + candidate_cost
                )
                if swap_cost > budget + 1.0e-9:
                    rejected_over_budget += 1
                    continue
            swap_trial = tuple(
                active_id for active_id in active if active_id != remove_id
            ) + (candidate_id,)
            affected = {
                inserted_satellite_id,
                candidates_by_id[remove_id].satellite_id,
            }
            if not _candidate_valid_in_schedule(
                case,
                candidates_by_id,
                swap_trial,
                affected_satellite_ids=affected,
            ):
                rejected_infeasible += 1
                continue
            delta = _swap_delta_from_counts(
                candidate_id,
                remove_id,
                counts,
                coverage_by_candidate,
                sample_weights,
            )
            if delta <= _LOCAL_MIN_OBJECTIVE_DELTA:
                rejected_non_improving += 1
                continue
            move = LocalImprovementMove(
                move_type="swap",
                inserted_candidate_id=candidate_id,
                removed_candidate_id=remove_id,
                objective_before=current_objective,
                objective_after=current_objective + delta,
                objective_delta=delta,
            )
            best_move = _better_local_move(best_move, (swap_trial, move))

    return (
        start_index,
        best_move,
        candidate_checks,
        rejected_infeasible,
        rejected_over_budget,
        rejected_non_improving,
    )


def improve_schedule_locally(
    case: RegionalCoverageCase,
    candidates_by_id: dict[str, StripCandidate],
    candidate_order: tuple[str, ...],
    selected_candidate_ids: tuple[str, ...],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
    *,
    enabled: bool,
    max_passes: int = 4,
    max_candidate_checks: int = 1_000,
    min_objective_delta: float = 1.0e-9,
    worker_count: int | str = 1,
    chunk_size: int = 128,
    cost_by_candidate: dict[str, float] | None = None,
    budget: float | None = None,
) -> LocalImprovementResult:
    """Try deterministic fixed-candidate insertions and one-for-one swaps.

    This is a benchmark-adaptation stage after CELF. It never creates new
    candidates and accepts only moves that preserve solver-local schedule
    validity and improve the fixed-sample coverage objective.
    """

    active = tuple(dict.fromkeys(selected_candidate_ids))
    before = _coverage_objective(active, coverage_by_candidate, sample_weights)
    cost_before = _cost_sum(active, cost_by_candidate)
    if not enabled:
        return LocalImprovementResult(
            enabled=False,
            original_candidate_ids=active,
            improved_candidate_ids=active,
            objective_before=before,
            objective_after=before,
            objective_delta=0.0,
            accepted_moves=(),
            candidate_checks=0,
            rejected_infeasible_count=0,
            rejected_over_budget_count=0,
            rejected_non_improving_count=0,
            stop_reason="disabled",
            budget=budget,
            cost_before=cost_before,
            cost_after=cost_before,
            execution_mode="disabled",
            worker_count=1,
            chunk_size=max(0, int(chunk_size)),
            chunk_count=0,
        )

    moves: list[LocalImprovementMove] = []
    candidate_checks = 0
    rejected_infeasible = 0
    rejected_over_budget = 0
    rejected_non_improving = 0
    stop_reason = "no_improving_move"
    effective_min_objective_delta = max(min_objective_delta, 1.0e-6)
    order_index = {candidate_id: index for index, candidate_id in enumerate(candidate_order)}
    standalone_rewards = {
        candidate_id: _standalone_reward(
            candidate_id, coverage_by_candidate, sample_weights
        )
        for candidate_id in candidate_order
    }
    ranked_positive_candidates = tuple(
        sorted(
            (
                candidate_id
                for candidate_id in candidate_order
                if standalone_rewards[candidate_id] > 0.0
            ),
            key=lambda candidate_id: (
                -standalone_rewards[candidate_id],
                order_index[candidate_id],
                candidate_id,
            ),
        )
    )
    execution_mode = "serial"
    effective_workers = 1
    total_chunk_count = 0

    for _ in range(max(0, max_passes)):
        active_set = set(active)
        counts = _coverage_counts(active, coverage_by_candidate)
        current_objective = _coverage_objective_from_counts(counts, sample_weights)
        loss_by_active = {
            candidate_id: _coverage_loss_from_counts(
                candidate_id,
                counts,
                coverage_by_candidate,
                sample_weights,
            )
            for candidate_id in active
        }
        candidate_ids_to_check = tuple(
            candidate_id
            for candidate_id in ranked_positive_candidates
            if candidate_id not in active_set
        )[: max(0, max_candidate_checks)]
        ranges = _chunk_ranges(len(candidate_ids_to_check), chunk_size)
        total_chunk_count += len(ranges)
        effective_workers = _effective_worker_count(worker_count, len(ranges))
        _set_local_improvement_globals(
            case=case,
            candidates_by_id=candidates_by_id,
            candidate_ids=candidate_ids_to_check,
            active=active,
            counts=counts,
            coverage_by_candidate=coverage_by_candidate,
            sample_weights=sample_weights,
            loss_by_active=loss_by_active,
            current_objective=current_objective,
            min_objective_delta=effective_min_objective_delta,
            cost_by_candidate=cost_by_candidate,
            budget=budget,
        )

        best_move: tuple[tuple[str, ...], LocalImprovementMove] | None = None
        range_results: list[
            tuple[
                int,
                tuple[tuple[str, ...], LocalImprovementMove] | None,
                int,
                int,
                int,
                int,
            ]
        ] = []
        if effective_workers <= 1 or not ranges:
            for bounds in ranges:
                range_results.append(_evaluate_local_improvement_range(bounds))
        else:
            try:
                fork_context = multiprocessing.get_context("fork")
            except ValueError:
                execution_mode = "serial_no_fork"
                effective_workers = 1
                for bounds in ranges:
                    range_results.append(_evaluate_local_improvement_range(bounds))
            else:
                execution_mode = "parallel_fork"
                with fork_context.Pool(processes=effective_workers) as pool:
                    range_results.extend(
                        pool.imap_unordered(_evaluate_local_improvement_range, ranges)
                    )

        for _, candidate_best, checks, infeasible, over_budget, non_improving in sorted(
            range_results, key=lambda row: row[0]
        ):
            best_move = _better_local_move(best_move, candidate_best)
            candidate_checks += checks
            rejected_infeasible += infeasible
            rejected_over_budget += over_budget
            rejected_non_improving += non_improving

        if best_move is None:
            break
        active, move = best_move
        moves.append(move)
        stop_reason = "max_passes" if len(moves) >= max(0, max_passes) else "improved"

    after = _coverage_objective(active, coverage_by_candidate, sample_weights)
    cost_after = _cost_sum(active, cost_by_candidate)
    if moves and len(moves) < max(0, max_passes):
        stop_reason = "no_improving_move"
    return LocalImprovementResult(
        enabled=True,
        original_candidate_ids=tuple(dict.fromkeys(selected_candidate_ids)),
        improved_candidate_ids=active,
        objective_before=before,
        objective_after=after,
        objective_delta=after - before,
        accepted_moves=tuple(moves),
        candidate_checks=candidate_checks,
        rejected_infeasible_count=rejected_infeasible,
        rejected_over_budget_count=rejected_over_budget,
        rejected_non_improving_count=rejected_non_improving,
        stop_reason=stop_reason,
        budget=budget,
        cost_before=cost_before,
        cost_after=cost_after,
        execution_mode=execution_mode,
        worker_count=effective_workers,
        chunk_size=max(0, int(chunk_size)),
        chunk_count=total_chunk_count,
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
        active_start = 0
        active_duration = 0.0
        for end_index, (start_s, end_s, candidate) in enumerate(intervals):
            active_duration += end_s - start_s
            window_start = end_s - orbit_period_s
            while (
                active_start <= end_index
                and intervals[active_start][1] <= window_start
            ):
                expired_start, expired_end, _ = intervals[active_start]
                active_duration -= expired_end - expired_start
                active_start += 1
            total = active_duration
            if active_start <= end_index and intervals[active_start][0] < window_start:
                total -= window_start - intervals[active_start][0]
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
        counts = _coverage_counts(active, coverage_by_candidate)
        remove_id = min(
            candidates,
            key=lambda cid: _removal_key(
                cid, counts, candidates_by_id, case, coverage_by_candidate, sample_weights
            ),
        )
        loss = _coverage_loss_from_counts(
            remove_id,
            counts,
            coverage_by_candidate,
            sample_weights,
        )
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
