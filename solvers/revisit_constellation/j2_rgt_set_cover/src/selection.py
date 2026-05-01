"""Certified satellite-cost set-cover selection for RGT candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math

from .case_io import RevisitCase, Target
from .certification import (
    CertifiedCoverage,
    CertificationSummary,
    satellites_required_for_target,
)
from .coverage import RaanCandidate


NUMERICAL_EPS = 1.0e-9


@dataclass(frozen=True, slots=True)
class TargetAssignment:
    target_id: str
    candidate_id: str
    required_satellites: int
    repeat_period_hours: float
    coverage_margin_score: float
    certification_id: str | None = None
    certified_max_gap_hours: float | None = None
    certified_capped_gap_hours: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "candidate_id": self.candidate_id,
            "required_satellites": self.required_satellites,
            "repeat_period_hours": self.repeat_period_hours,
            "coverage_margin_score": self.coverage_margin_score,
            "certification_id": self.certification_id,
            "certified_max_gap_hours": self.certified_max_gap_hours,
            "certified_capped_gap_hours": self.certified_capped_gap_hours,
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
    selected_satellite_count: int
    newly_covered_target_ids: tuple[str, ...]
    covered_target_count: int
    total_satellite_count: int
    mean_certified_capped_gap_hours: float
    worst_certified_gap_hours: float
    remaining_uncovered_target_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "selected_candidate_id": self.selected_candidate_id,
            "selected_satellite_count": self.selected_satellite_count,
            "newly_covered_target_ids": list(self.newly_covered_target_ids),
            "covered_target_count": self.covered_target_count,
            "total_satellite_count": self.total_satellite_count,
            "mean_certified_capped_gap_hours": self.mean_certified_capped_gap_hours,
            "worst_certified_gap_hours": self.worst_certified_gap_hours,
            "remaining_uncovered_target_ids": list(self.remaining_uncovered_target_ids),
        }


@dataclass(frozen=True, slots=True)
class BudgetNearMiss:
    candidate_id: str
    required_satellites: int
    newly_covered_target_ids: tuple[str, ...]
    trial_satellite_count: int
    satellite_over_budget: int
    gain: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "required_satellites": self.required_satellites,
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
    blacklisted_certification_ids: tuple[str, ...] = ()
    blacklisted_variants: tuple[tuple[str, int], ...] = ()

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
            "blacklisted_certification_ids": list(self.blacklisted_certification_ids),
            "blacklisted_variants": [
                {"candidate_id": candidate_id, "required_satellites": count}
                for candidate_id, count in self.blacklisted_variants
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


@dataclass(frozen=True, slots=True)
class CandidateVariant:
    candidate: RaanCandidate
    required_satellites: int
    records: tuple[CertifiedCoverage, ...]

    @property
    def variant_id(self) -> tuple[str, int]:
        return (self.candidate.candidate_id, self.required_satellites)

    @property
    def target_ids(self) -> tuple[str, ...]:
        return tuple(sorted({record.target_id for record in self.records}))


def _candidate_record_key(record: CertifiedCoverage) -> tuple[Any, ...]:
    return (
        record.required_satellites,
        record.capped_max_gap_hours,
        record.max_gap_hours,
        -record.claim.geometry_margin,
        record.claim.repeat_period_hours,
        record.claim.closure_error_m,
        record.candidate_id,
        record.certification_id,
    )


def _build_variants(
    certification: CertificationSummary,
    *,
    blacklisted_certification_ids: set[str],
    blacklisted_variants: set[tuple[str, int]],
) -> list[CandidateVariant]:
    by_candidate: dict[str, list[CertifiedCoverage]] = {}
    for record in certification.certified_records:
        if not record.meets_revisit:
            continue
        if record.certification_id in blacklisted_certification_ids:
            continue
        by_candidate.setdefault(record.candidate_id, []).append(record)

    variants: list[CandidateVariant] = []
    for candidate_id, records in sorted(by_candidate.items()):
        candidate = records[0].candidate
        for required_satellites in sorted({record.required_satellites for record in records}):
            if (candidate_id, required_satellites) in blacklisted_variants:
                continue
            covered_records_by_target: dict[str, CertifiedCoverage] = {}
            for record in records:
                if record.required_satellites > required_satellites:
                    continue
                current = covered_records_by_target.get(record.target_id)
                if current is None or _candidate_record_key(record) < _candidate_record_key(current):
                    covered_records_by_target[record.target_id] = record
            if covered_records_by_target:
                variants.append(
                    CandidateVariant(
                        candidate=candidate,
                        required_satellites=required_satellites,
                        records=tuple(
                            sorted(
                                covered_records_by_target.values(),
                                key=lambda item: (item.target_id, item.certification_id),
                            )
                        ),
                    )
                )
    return sorted(
        variants,
        key=lambda item: (
            item.candidate.candidate_id,
            item.required_satellites,
        ),
    )


def _assign_targets(
    case: RevisitCase,
    variants: list[CandidateVariant],
) -> dict[str, tuple[CandidateVariant, CertifiedCoverage]]:
    assignments: dict[str, tuple[CandidateVariant, CertifiedCoverage]] = {}
    for target_id in sorted(case.targets):
        covering: list[tuple[CandidateVariant, CertifiedCoverage]] = []
        for variant in variants:
            for record in variant.records:
                if record.target_id == target_id:
                    covering.append((variant, record))
        if not covering:
            continue
        assignments[target_id] = min(
            covering,
            key=lambda item: (
                item[1].capped_max_gap_hours,
                item[1].max_gap_hours,
                item[0].required_satellites,
                item[1].claim.closure_error_m,
                item[0].candidate.candidate_id,
                item[1].certification_id,
            ),
        )
    return assignments


def _selection_metrics(
    case: RevisitCase,
    variants: list[CandidateVariant],
) -> tuple[int, int, float, float, int, tuple[str, ...]]:
    assignments = _assign_targets(case, variants)
    gaps = [record.capped_max_gap_hours for _, record in assignments.values()]
    raw_gaps = [record.max_gap_hours for _, record in assignments.values()]
    return (
        len(assignments),
        sum(variant.required_satellites for variant in variants),
        sum(gaps) / len(gaps) if gaps else math.inf,
        max(raw_gaps, default=math.inf),
        len(variants),
        tuple(
            f"{variant.candidate.candidate_id}:{variant.required_satellites}"
            for variant in variants
        ),
    )


def _selection_key(
    case: RevisitCase,
    variants: list[CandidateVariant],
) -> tuple[Any, ...]:
    covered, satellites, mean_gap, worst_gap, candidate_count, ids = _selection_metrics(
        case,
        variants,
    )
    return (-covered, satellites, mean_gap, worst_gap, candidate_count, ids)


def _build_summary(
    *,
    case: RevisitCase,
    variants: list[CandidateVariant],
    rounds: list[SelectionRound],
    budget_near_misses: list[BudgetNearMiss],
    blacklisted_certification_ids: set[str],
    blacklisted_variants: set[tuple[str, int]],
) -> SelectionSummary:
    assignments_by_target = _assign_targets(case, variants)
    target_assignments: dict[str, TargetAssignment] = {}
    for target_id, (variant, record) in sorted(assignments_by_target.items()):
        target_assignments[target_id] = TargetAssignment(
            target_id=target_id,
            candidate_id=variant.candidate.candidate_id,
            required_satellites=record.required_satellites,
            repeat_period_hours=variant.candidate.repeat_period_sec / 3600.0,
            coverage_margin_score=record.claim.geometry_margin,
            certification_id=record.certification_id,
            certified_max_gap_hours=record.max_gap_hours,
            certified_capped_gap_hours=record.capped_max_gap_hours,
        )

    selected_candidates: list[SelectedCandidate] = []
    for variant in variants:
        assigned = tuple(
            target_id
            for target_id, (assigned_variant, _) in sorted(assignments_by_target.items())
            if assigned_variant.variant_id == variant.variant_id
        )
        certified_targets = variant.target_ids
        selected_candidates.append(
            SelectedCandidate(
                candidate=variant.candidate,
                assigned_target_ids=assigned,
                required_satellites=variant.required_satellites,
                covered_target_ids=certified_targets,
                redundant_target_ids=tuple(
                    target_id for target_id in certified_targets if target_id not in assigned
                ),
            )
        )

    total_required_satellites = sum(variant.required_satellites for variant in variants)
    uncovered = sorted(set(case.targets).difference(target_assignments))
    return SelectionSummary(
        selected_candidates=selected_candidates,
        target_assignments=target_assignments,
        uncovered_target_ids=uncovered,
        total_required_satellites=total_required_satellites,
        max_num_satellites=case.max_num_satellites,
        rounds=rounds,
        budget_near_misses=budget_near_misses,
        all_targets_covered=not uncovered,
        within_satellite_budget=total_required_satellites <= case.max_num_satellites,
        blacklisted_certification_ids=tuple(sorted(blacklisted_certification_ids)),
        blacklisted_variants=tuple(sorted(blacklisted_variants)),
    )


def _remove_redundant_variants(
    case: RevisitCase,
    selected: list[CandidateVariant],
) -> list[CandidateVariant]:
    current = list(selected)
    changed = True
    while changed:
        changed = False
        current_key = _selection_key(case, current)
        for variant in list(current):
            trial = [item for item in current if item.variant_id != variant.variant_id]
            trial_key = _selection_key(case, trial)
            if trial_key <= current_key:
                current = trial
                changed = True
                break
    return current


def _improve_by_replacement(
    case: RevisitCase,
    selected: list[CandidateVariant],
    variants: list[CandidateVariant],
) -> list[CandidateVariant]:
    current = list(selected)
    changed = True
    while changed:
        changed = False
        current_key = _selection_key(case, current)
        current_candidate_ids = {variant.candidate.candidate_id for variant in current}
        best = current
        best_key = current_key
        for remove in current:
            base = [item for item in current if item.variant_id != remove.variant_id]
            base_candidate_ids = {
                variant.candidate.candidate_id for variant in base
            }
            for add in variants:
                if add.candidate.candidate_id in base_candidate_ids:
                    continue
                if add.variant_id == remove.variant_id:
                    continue
                if (
                    add.candidate.candidate_id in current_candidate_ids
                    and add.candidate.candidate_id != remove.candidate.candidate_id
                ):
                    continue
                trial = sorted(
                    [*base, add],
                    key=lambda item: (item.candidate.candidate_id, item.required_satellites),
                )
                if sum(item.required_satellites for item in trial) > case.max_num_satellites:
                    continue
                trial_key = _selection_key(case, trial)
                if trial_key < best_key:
                    best = trial
                    best_key = trial_key
        if best_key < current_key:
            current = best
            changed = True
    return current


def _exact_selection(
    case: RevisitCase,
    variants: list[CandidateVariant],
) -> list[CandidateVariant]:
    target_ids = sorted(case.targets)
    target_index = {target_id: index for index, target_id in enumerate(target_ids)}
    variant_masks: list[int] = []
    for variant in variants:
        mask = 0
        for target_id in variant.target_ids:
            if target_id in target_index:
                mask |= 1 << target_index[target_id]
        variant_masks.append(mask)

    states: list[dict[int, tuple[int, ...]]] = [
        {0: ()} for _ in range(case.max_num_satellites + 1)
    ]
    for variant_index, variant in enumerate(variants):
        cost = variant.required_satellites
        if cost > case.max_num_satellites:
            continue
        mask = variant_masks[variant_index]
        if mask == 0:
            continue
        for budget in range(case.max_num_satellites - cost, -1, -1):
            for current_mask, chosen in list(states[budget].items()):
                if any(
                    variants[index].candidate.candidate_id
                    == variant.candidate.candidate_id
                    for index in chosen
                ):
                    continue
                next_budget = budget + cost
                next_mask = current_mask | mask
                next_chosen = tuple(
                    sorted(
                        (*chosen, variant_index),
                        key=lambda index: (
                            variants[index].candidate.candidate_id,
                            variants[index].required_satellites,
                        ),
                    )
                )
                current = states[next_budget].get(next_mask)
                if current is None or _exact_state_key(
                    case,
                    [variants[index] for index in next_chosen],
                ) < _exact_state_key(
                    case,
                    [variants[index] for index in current],
                ):
                    states[next_budget][next_mask] = next_chosen

    best: tuple[int, ...] = ()
    best_key = _exact_state_key(case, [])
    for budget_states in states:
        for chosen in budget_states.values():
            selected = [variants[index] for index in chosen]
            key = _exact_state_key(case, selected)
            if key < best_key:
                best = chosen
                best_key = key
    return [variants[index] for index in best]


def _exact_state_key(
    case: RevisitCase,
    selected: list[CandidateVariant],
) -> tuple[Any, ...]:
    return _selection_key(case, selected)


def _budget_near_misses(
    case: RevisitCase,
    variants: list[CandidateVariant],
) -> list[BudgetNearMiss]:
    blocked: list[BudgetNearMiss] = []
    for variant in variants:
        if variant.required_satellites <= case.max_num_satellites:
            continue
        blocked.append(
            BudgetNearMiss(
                candidate_id=variant.candidate.candidate_id,
                required_satellites=variant.required_satellites,
                newly_covered_target_ids=variant.target_ids,
                trial_satellite_count=variant.required_satellites,
                satellite_over_budget=variant.required_satellites
                - case.max_num_satellites,
                gain=len(variant.target_ids),
            )
        )
    return sorted(
        blocked,
        key=lambda item: (
            item.satellite_over_budget,
            -item.gain,
            item.required_satellites,
            item.candidate_id,
        ),
    )[:10]


def select_candidates(
    case: RevisitCase,
    certification: CertificationSummary,
    *,
    blacklisted_certification_ids: set[str] | None = None,
    blacklisted_variants: set[tuple[str, int]] | None = None,
) -> SelectionSummary:
    if not isinstance(certification, CertificationSummary):
        raise TypeError("select_candidates requires a CertificationSummary")
    blacklist_records = set() if blacklisted_certification_ids is None else set(blacklisted_certification_ids)
    blacklist_variants = set() if blacklisted_variants is None else set(blacklisted_variants)
    variants = _build_variants(
        certification,
        blacklisted_certification_ids=blacklist_records,
        blacklisted_variants=blacklist_variants,
    )
    selected = _exact_selection(case, variants)
    rounds: list[SelectionRound] = []
    budget_near_misses = [] if selected else _budget_near_misses(case, variants)
    selected = _remove_redundant_variants(case, selected)
    selected = _improve_by_replacement(case, selected, variants)
    return _build_summary(
        case=case,
        variants=selected,
        rounds=rounds,
        budget_near_misses=budget_near_misses,
        blacklisted_certification_ids=blacklist_records,
        blacklisted_variants=blacklist_variants,
    )
