"""Satellite-cost set-cover selection for RAAN-phased RGT candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math

from .case_io import RevisitCase, Target
from .coverage import CoverageSummary, RaanCandidate, VisibilityWindow


@dataclass(frozen=True, slots=True)
class TargetAssignment:
    target_id: str
    candidate_id: str
    required_satellites: int
    repeat_period_hours: float
    coverage_margin_score: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "candidate_id": self.candidate_id,
            "required_satellites": self.required_satellites,
            "repeat_period_hours": self.repeat_period_hours,
            "coverage_margin_score": self.coverage_margin_score,
        }


@dataclass(frozen=True, slots=True)
class SelectedCandidate:
    candidate: RaanCandidate
    assigned_target_ids: tuple[str, ...]
    required_satellites: int
    covered_target_ids: tuple[str, ...]
    redundant_target_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate.candidate_id,
            "template_id": self.candidate.template_id,
            "raan_deg": self.candidate.raan_deg,
            "repeat_period_hours": self.candidate.repeat_period_sec / 3600.0,
            "required_satellites": self.required_satellites,
            "assigned_target_ids": list(self.assigned_target_ids),
            "covered_target_ids": list(self.covered_target_ids),
            "redundant_target_ids": list(self.redundant_target_ids),
            "template_closure_error_m": self.candidate.template_closure_error_m,
        }


@dataclass(frozen=True, slots=True)
class SelectionRound:
    round_index: int
    selected_candidate_id: str
    newly_covered_target_ids: tuple[str, ...]
    gain: int
    previous_satellite_count: int
    trial_satellite_count: int
    incremental_satellite_cost: int
    gain_per_cost: float
    difficult_target_score: float
    coverage_margin_score: float
    closure_error_m: float
    repeat_period_sec: float
    remaining_uncovered_target_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "selected_candidate_id": self.selected_candidate_id,
            "newly_covered_target_ids": list(self.newly_covered_target_ids),
            "gain": self.gain,
            "previous_satellite_count": self.previous_satellite_count,
            "trial_satellite_count": self.trial_satellite_count,
            "incremental_satellite_cost": self.incremental_satellite_cost,
            "gain_per_cost": self.gain_per_cost,
            "difficult_target_score": self.difficult_target_score,
            "coverage_margin_score": self.coverage_margin_score,
            "closure_error_m": self.closure_error_m,
            "repeat_period_sec": self.repeat_period_sec,
            "remaining_uncovered_target_ids": list(
                self.remaining_uncovered_target_ids
            ),
        }


@dataclass(frozen=True, slots=True)
class BudgetNearMiss:
    candidate_id: str
    newly_covered_target_ids: tuple[str, ...]
    trial_satellite_count: int
    satellite_over_budget: int
    gain: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "newly_covered_target_ids": list(self.newly_covered_target_ids),
            "trial_satellite_count": self.trial_satellite_count,
            "satellite_over_budget": self.satellite_over_budget,
            "gain": self.gain,
        }


@dataclass(frozen=True, slots=True)
class SelectionSummary:
    selected_candidates: list[SelectedCandidate]
    target_assignments: dict[str, TargetAssignment]
    uncovered_target_ids: list[str]
    total_required_satellites: int
    max_num_satellites: int
    rounds: list[SelectionRound]
    budget_near_misses: list[BudgetNearMiss]
    all_targets_covered: bool
    within_satellite_budget: bool

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "all_targets_covered": self.all_targets_covered,
            "within_satellite_budget": self.within_satellite_budget,
            "total_required_satellites": self.total_required_satellites,
            "max_num_satellites": self.max_num_satellites,
            "uncovered_target_ids": self.uncovered_target_ids,
            "selected_candidates": [
                candidate.as_dict() for candidate in self.selected_candidates
            ],
            "target_assignments": {
                target_id: assignment.as_dict()
                for target_id, assignment in sorted(self.target_assignments.items())
            },
            "rounds": [round_item.as_dict() for round_item in self.rounds],
            "budget_near_misses": [
                near_miss.as_dict() for near_miss in self.budget_near_misses
            ],
        }

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "selected_candidate_count": len(self.selected_candidates),
            "assigned_target_count": len(self.target_assignments),
            "uncovered_target_count": len(self.uncovered_target_ids),
            "uncovered_target_ids": self.uncovered_target_ids,
            "total_required_satellites": self.total_required_satellites,
            "max_num_satellites": self.max_num_satellites,
            "all_targets_covered": self.all_targets_covered,
            "within_satellite_budget": self.within_satellite_budget,
        }


def satellites_required_for_target(
    candidate: RaanCandidate,
    target: Target,
) -> int:
    revisit_hours = target.expected_revisit_period_hours
    if revisit_hours <= 0.0:
        raise ValueError(f"{target.target_id}.expected_revisit_period_hours must be > 0")
    repeat_period_hours = candidate.repeat_period_sec / 3600.0
    return max(1, int(math.ceil(repeat_period_hours / revisit_hours)))


def _candidate_map(summary: CoverageSummary) -> dict[str, RaanCandidate]:
    return {candidate.candidate_id: candidate for candidate in summary.candidates}


def _coverage_margin_by_pair(
    case: RevisitCase,
    windows: list[VisibilityWindow],
) -> dict[tuple[str, str], float]:
    margins: dict[tuple[str, str], float] = {}
    for window in windows:
        target = case.targets[window.target_id]
        range_limit = min(
            target.max_slant_range_m,
            case.satellite_model.sensor.max_range_m,
        )
        margin = min(
            window.max_elevation_deg - target.min_elevation_deg,
            range_limit - window.min_slant_range_m,
            case.satellite_model.sensor.max_off_nadir_angle_deg
            - window.min_off_nadir_deg,
        )
        key = (window.candidate_id, window.target_id)
        margins[key] = max(margins.get(key, -math.inf), float(margin))
    return margins


def _assignment_key(
    *,
    candidate: RaanCandidate,
    target: Target,
    margin_by_pair: dict[tuple[str, str], float],
) -> tuple[float, float, float, float, str]:
    return (
        satellites_required_for_target(candidate, target),
        candidate.repeat_period_sec,
        -margin_by_pair.get((candidate.candidate_id, target.target_id), 0.0),
        candidate.template_closure_error_m,
        candidate.candidate_id,
    )


def _assign_targets(
    *,
    case: RevisitCase,
    summary: CoverageSummary,
    selected_candidate_ids: list[str],
    margin_by_pair: dict[tuple[str, str], float],
) -> dict[str, TargetAssignment]:
    candidates = _candidate_map(summary)
    selected = set(selected_candidate_ids)
    assignments: dict[str, TargetAssignment] = {}
    for target_id in sorted(case.targets):
        target = case.targets[target_id]
        covering = [
            candidate_id
            for candidate_id in summary.target_to_candidates.get(target_id, [])
            if candidate_id in selected
        ]
        if not covering:
            continue
        candidate = min(
            (candidates[candidate_id] for candidate_id in covering),
            key=lambda item: _assignment_key(
                candidate=item,
                target=target,
                margin_by_pair=margin_by_pair,
            ),
        )
        assignments[target_id] = TargetAssignment(
            target_id=target_id,
            candidate_id=candidate.candidate_id,
            required_satellites=satellites_required_for_target(candidate, target),
            repeat_period_hours=candidate.repeat_period_sec / 3600.0,
            coverage_margin_score=margin_by_pair.get(
                (candidate.candidate_id, target_id),
                0.0,
            ),
        )
    return assignments


def _selected_satellite_count(
    selected_candidate_ids: list[str],
    assignments: dict[str, TargetAssignment],
) -> int:
    total = 0
    for candidate_id in selected_candidate_ids:
        assigned_costs = [
            assignment.required_satellites
            for assignment in assignments.values()
            if assignment.candidate_id == candidate_id
        ]
        if assigned_costs:
            total += max(assigned_costs)
    return total


def _candidate_round_metrics(
    *,
    summary: CoverageSummary,
    candidate: RaanCandidate,
    uncovered: set[str],
    margin_by_pair: dict[tuple[str, str], float],
) -> tuple[list[str], float, float]:
    newly_covered = sorted(
        target_id
        for target_id in summary.candidate_to_targets.get(candidate.candidate_id, [])
        if target_id in uncovered
    )
    difficult_target_score = sum(
        1.0 / max(1, len(summary.target_to_candidates.get(target_id, [])))
        for target_id in newly_covered
    )
    coverage_margin_score = sum(
        margin_by_pair.get((candidate.candidate_id, target_id), 0.0)
        for target_id in newly_covered
    )
    return newly_covered, difficult_target_score, coverage_margin_score


def _build_selected_candidates(
    *,
    summary: CoverageSummary,
    selected_candidate_ids: list[str],
    assignments: dict[str, TargetAssignment],
) -> list[SelectedCandidate]:
    candidates = _candidate_map(summary)
    selected_items: list[SelectedCandidate] = []
    for candidate_id in selected_candidate_ids:
        assigned = tuple(
            target_id
            for target_id, assignment in sorted(assignments.items())
            if assignment.candidate_id == candidate_id
        )
        assigned_costs = [
            assignments[target_id].required_satellites for target_id in assigned
        ]
        covered = tuple(summary.candidate_to_targets.get(candidate_id, []))
        redundant = tuple(target_id for target_id in covered if target_id not in assigned)
        selected_items.append(
            SelectedCandidate(
                candidate=candidates[candidate_id],
                assigned_target_ids=assigned,
                required_satellites=max(assigned_costs, default=0),
                covered_target_ids=covered,
                redundant_target_ids=redundant,
            )
        )
    return selected_items


def _remove_redundant_candidates(
    *,
    case: RevisitCase,
    summary: CoverageSummary,
    selected_candidate_ids: list[str],
    margin_by_pair: dict[tuple[str, str], float],
) -> list[str]:
    current = list(selected_candidate_ids)
    changed = True
    while changed:
        changed = False
        current_assignments = _assign_targets(
            case=case,
            summary=summary,
            selected_candidate_ids=current,
            margin_by_pair=margin_by_pair,
        )
        current_total = _selected_satellite_count(current, current_assignments)
        for candidate_id in list(current):
            trial = [item for item in current if item != candidate_id]
            trial_assignments = _assign_targets(
                case=case,
                summary=summary,
                selected_candidate_ids=trial,
                margin_by_pair=margin_by_pair,
            )
            if set(trial_assignments) != set(current_assignments):
                continue
            trial_total = _selected_satellite_count(trial, trial_assignments)
            if trial_total <= current_total:
                current = trial
                changed = True
                break
    return current


def select_candidates(
    case: RevisitCase,
    summary: CoverageSummary,
) -> SelectionSummary:
    candidates = _candidate_map(summary)
    margin_by_pair = _coverage_margin_by_pair(case, summary.windows)
    selected_candidate_ids: list[str] = []
    rounds: list[SelectionRound] = []
    target_ids = set(case.targets)
    assignments: dict[str, TargetAssignment] = {}
    total_required_satellites = 0
    uncovered = set(target_ids)
    budget_near_misses: list[BudgetNearMiss] = []

    while uncovered:
        feasible_options: list[tuple[tuple[Any, ...], SelectionRound]] = []
        budget_blocked_options: list[BudgetNearMiss] = []
        for candidate_id in sorted(candidates):
            if candidate_id in selected_candidate_ids:
                continue
            candidate = candidates[candidate_id]
            newly_covered, difficult_score, margin_score = _candidate_round_metrics(
                summary=summary,
                candidate=candidate,
                uncovered=uncovered,
                margin_by_pair=margin_by_pair,
            )
            if not newly_covered:
                continue
            trial_ids = selected_candidate_ids + [candidate_id]
            trial_assignments = _assign_targets(
                case=case,
                summary=summary,
                selected_candidate_ids=trial_ids,
                margin_by_pair=margin_by_pair,
            )
            trial_total = _selected_satellite_count(trial_ids, trial_assignments)
            incremental_cost = max(0, trial_total - total_required_satellites)
            gain = len(newly_covered)
            gain_per_cost = math.inf if incremental_cost == 0 else gain / incremental_cost
            round_item = SelectionRound(
                round_index=len(rounds),
                selected_candidate_id=candidate_id,
                newly_covered_target_ids=tuple(newly_covered),
                gain=gain,
                previous_satellite_count=total_required_satellites,
                trial_satellite_count=trial_total,
                incremental_satellite_cost=incremental_cost,
                gain_per_cost=gain_per_cost,
                difficult_target_score=difficult_score,
                coverage_margin_score=margin_score,
                closure_error_m=candidate.template_closure_error_m,
                repeat_period_sec=candidate.repeat_period_sec,
                remaining_uncovered_target_ids=tuple(
                    sorted(uncovered.difference(newly_covered))
                ),
            )
            if trial_total > case.max_num_satellites:
                budget_blocked_options.append(
                    BudgetNearMiss(
                        candidate_id=candidate_id,
                        newly_covered_target_ids=tuple(newly_covered),
                        trial_satellite_count=trial_total,
                        satellite_over_budget=trial_total - case.max_num_satellites,
                        gain=gain,
                    )
                )
                continue
            tie_key = (
                -gain_per_cost,
                -difficult_score,
                candidate.template_closure_error_m,
                candidate.repeat_period_sec,
                -margin_score,
                candidate.candidate_id,
            )
            feasible_options.append((tie_key, round_item))

        if not feasible_options:
            budget_near_misses = sorted(
                budget_blocked_options,
                key=lambda item: (
                    item.satellite_over_budget,
                    -item.gain,
                    item.candidate_id,
                ),
            )[:10]
            break

        _, chosen = min(feasible_options, key=lambda item: item[0])
        selected_candidate_ids.append(chosen.selected_candidate_id)
        rounds.append(chosen)
        assignments = _assign_targets(
            case=case,
            summary=summary,
            selected_candidate_ids=selected_candidate_ids,
            margin_by_pair=margin_by_pair,
        )
        total_required_satellites = _selected_satellite_count(
            selected_candidate_ids,
            assignments,
        )
        uncovered = target_ids.difference(assignments)

    selected_candidate_ids = _remove_redundant_candidates(
        case=case,
        summary=summary,
        selected_candidate_ids=selected_candidate_ids,
        margin_by_pair=margin_by_pair,
    )
    assignments = _assign_targets(
        case=case,
        summary=summary,
        selected_candidate_ids=selected_candidate_ids,
        margin_by_pair=margin_by_pair,
    )
    total_required_satellites = _selected_satellite_count(
        selected_candidate_ids,
        assignments,
    )
    uncovered_ids = sorted(target_ids.difference(assignments))
    return SelectionSummary(
        selected_candidates=_build_selected_candidates(
            summary=summary,
            selected_candidate_ids=selected_candidate_ids,
            assignments=assignments,
        ),
        target_assignments=assignments,
        uncovered_target_ids=uncovered_ids,
        total_required_satellites=total_required_satellites,
        max_num_satellites=case.max_num_satellites,
        rounds=rounds,
        budget_near_misses=budget_near_misses,
        all_targets_covered=not uncovered_ids,
        within_satellite_budget=total_required_satellites <= case.max_num_satellites,
    )
