"""Greedy insertion baseline over satellite-local regional coverage sequences."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Literal

from .candidates import Candidate
from .case_io import RegionalCoverageCase
from .coverage import CoverageIndex
from .sequence import (
    InsertionResult,
    SequenceState,
    check_insertion,
    create_empty_state,
    insert_candidate,
    possible_insertion_positions,
)


GreedyPolicy = Literal[
    "best_marginal_coverage",
    "coverage_per_transition_burden",
    "coverage_per_imaging_time",
]


@dataclass(frozen=True, slots=True)
class GreedyConfig:
    policy: GreedyPolicy = "best_marginal_coverage"
    max_iterations: int | None = None
    wall_time_limit_s: float | None = None
    write_insertion_attempts: bool = False
    insertion_attempt_debug_limit: int = 2000

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "GreedyConfig":
        payload = payload or {}
        policy = payload.get("greedy_policy", "best_marginal_coverage")
        if policy not in _POLICIES:
            raise ValueError(
                "greedy_policy must be one of: " + ", ".join(sorted(_POLICIES))
            )
        return cls(
            policy=policy,
            max_iterations=_optional_positive_int(payload.get("greedy_max_iterations")),
            wall_time_limit_s=_optional_positive_float(payload.get("greedy_wall_time_limit_s")),
            write_insertion_attempts=bool(payload.get("write_insertion_attempts", False)),
            insertion_attempt_debug_limit=_non_negative_int(
                payload.get("insertion_attempt_debug_limit", 2000),
                "insertion_attempt_debug_limit",
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "max_iterations": self.max_iterations,
            "wall_time_limit_s": self.wall_time_limit_s,
            "write_insertion_attempts": self.write_insertion_attempts,
            "insertion_attempt_debug_limit": self.insertion_attempt_debug_limit,
        }


@dataclass(frozen=True, slots=True)
class InsertionEvaluation:
    candidate: Candidate
    position: int
    insertion_result: InsertionResult
    marginal_weight_m2: float
    transition_burden_s: float
    energy_estimate_wh: float
    duty_estimate_s: int

    @property
    def coverage_per_transition_burden(self) -> float:
        return self.marginal_weight_m2 / max(1.0, self.transition_burden_s)

    @property
    def coverage_per_imaging_time(self) -> float:
        return self.marginal_weight_m2 / max(1, self.duty_estimate_s)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate.candidate_id,
            "satellite_id": self.candidate.satellite_id,
            "position": self.position,
            "marginal_weight_m2": self.marginal_weight_m2,
            "transition_burden_s": self.transition_burden_s,
            "energy_estimate_wh": self.energy_estimate_wh,
            "duty_estimate_s": self.duty_estimate_s,
            "coverage_per_transition_burden": self.coverage_per_transition_burden,
            "coverage_per_imaging_time": self.coverage_per_imaging_time,
            "insertion": self.insertion_result.as_dict(),
        }


@dataclass(slots=True)
class GreedySummary:
    policy: str
    stop_reason: str = "not_started"
    iterations: int = 0
    selected_count: int = 0
    selected_weight_m2: float = 0.0
    covered_sample_count: int = 0
    attempted_insertions: int = 0
    feasible_insertions: int = 0
    rejected_insertions: int = 0
    zero_marginal_candidates: int = 0
    action_cap: int = 0
    reject_reasons: dict[str, int] = field(default_factory=dict)
    accepted_candidate_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "stop_reason": self.stop_reason,
            "iterations": self.iterations,
            "selected_count": self.selected_count,
            "selected_weight_m2": self.selected_weight_m2,
            "covered_sample_count": self.covered_sample_count,
            "attempted_insertions": self.attempted_insertions,
            "feasible_insertions": self.feasible_insertions,
            "rejected_insertions": self.rejected_insertions,
            "zero_marginal_candidates": self.zero_marginal_candidates,
            "action_cap": self.action_cap,
            "reject_reasons": dict(sorted(self.reject_reasons.items())),
            "accepted_candidate_ids": list(self.accepted_candidate_ids),
            "tie_break_order": [
                "policy score",
                "higher marginal coverage",
                "lower transition burden",
                "lower energy estimate",
                "earlier start",
                "stable candidate id",
                "lower insertion position",
            ],
        }


@dataclass(slots=True)
class GreedyResult:
    state: SequenceState
    selected_candidates: list[Candidate]
    covered_sample_ids: set[str]
    summary: GreedySummary
    accepted_evaluations: list[InsertionEvaluation]
    attempt_debug: list[dict[str, Any]]

    def selected_in_solution_order(self) -> list[Candidate]:
        out: list[Candidate] = []
        for satellite_id in sorted(self.state.sequences):
            out.extend(self.state.sequences[satellite_id].candidates)
        return sorted(
            out,
            key=lambda item: (item.start_offset_s, item.satellite_id, item.candidate_id),
        )


_POLICIES = frozenset(
    {
        "best_marginal_coverage",
        "coverage_per_transition_burden",
        "coverage_per_imaging_time",
    }
)


def greedy_insertion(
    case: RegionalCoverageCase,
    candidates: list[Candidate],
    *,
    coverage_index: CoverageIndex,
    config: GreedyConfig,
) -> GreedyResult:
    state = create_empty_state(case)
    covered_sample_ids: set[str] = set()
    selected_ids: set[str] = set()
    selected_candidates: list[Candidate] = []
    accepted_evaluations: list[InsertionEvaluation] = []
    attempt_debug: list[dict[str, Any]] = []
    action_cap = case.mission.max_actions_total
    summary = GreedySummary(policy=config.policy, action_cap=action_cap)
    started = perf_counter()

    while True:
        if len(selected_candidates) >= action_cap:
            summary.stop_reason = "action_cap_reached"
            break
        if config.max_iterations is not None and summary.iterations >= config.max_iterations:
            summary.stop_reason = "iteration_cap_reached"
            break
        if config.wall_time_limit_s is not None and perf_counter() - started >= config.wall_time_limit_s:
            summary.stop_reason = "time_cap_reached"
            break

        best = _best_feasible_evaluation(
            case,
            candidates,
            selected_ids=selected_ids,
            covered_sample_ids=covered_sample_ids,
            state=state,
            coverage_index=coverage_index,
            policy=config.policy,
            summary=summary,
            attempt_debug=attempt_debug,
            attempt_debug_limit=config.insertion_attempt_debug_limit,
        )
        if best is None:
            summary.stop_reason = "no_positive_feasible_insertion"
            break

        sequence = state.sequences[best.candidate.satellite_id]
        result = insert_candidate(case, sequence, best.candidate, best.position)
        if not result.success:
            raise RuntimeError(
                f"candidate {best.candidate.candidate_id} became infeasible before insertion"
            )

        selected_ids.add(best.candidate.candidate_id)
        selected_candidates.append(best.candidate)
        accepted_evaluations.append(best)
        covered_sample_ids.update(best.candidate.coverage_sample_ids)
        summary.iterations += 1
        summary.selected_count = len(selected_candidates)
        summary.selected_weight_m2 = coverage_index.total_weight(covered_sample_ids)
        summary.covered_sample_count = len(covered_sample_ids)
        summary.accepted_candidate_ids.append(best.candidate.candidate_id)

    return GreedyResult(
        state=state,
        selected_candidates=selected_candidates,
        covered_sample_ids=covered_sample_ids,
        summary=summary,
        accepted_evaluations=accepted_evaluations,
        attempt_debug=attempt_debug,
    )


def _best_feasible_evaluation(
    case: RegionalCoverageCase,
    candidates: list[Candidate],
    *,
    selected_ids: set[str],
    covered_sample_ids: set[str],
    state: SequenceState,
    coverage_index: CoverageIndex,
    policy: GreedyPolicy,
    summary: GreedySummary,
    attempt_debug: list[dict[str, Any]],
    attempt_debug_limit: int,
) -> InsertionEvaluation | None:
    best: InsertionEvaluation | None = None
    zero_marginal_seen = 0

    for candidate in candidates:
        if candidate.candidate_id in selected_ids:
            continue
        marginal_ids = candidate.coverage_sample_ids - covered_sample_ids
        marginal_weight_m2 = coverage_index.total_weight(marginal_ids)
        if marginal_weight_m2 <= 0.0:
            zero_marginal_seen += 1
            continue
        sequence = state.sequences[candidate.satellite_id]
        candidate_best = _best_position_for_candidate(
            case,
            candidate,
            sequence=sequence,
            marginal_weight_m2=marginal_weight_m2,
            policy=policy,
            summary=summary,
        )
        if candidate_best is None:
            summary.rejected_insertions += 1
            _record_rejection_reasons(case, candidate, sequence, summary)
            if len(attempt_debug) < attempt_debug_limit:
                attempt_debug.append(
                    {
                        "candidate_id": candidate.candidate_id,
                        "satellite_id": candidate.satellite_id,
                        "marginal_weight_m2": marginal_weight_m2,
                        "accepted": False,
                        "reason": "no_feasible_position",
                    }
                )
            continue

        summary.feasible_insertions += 1
        if len(attempt_debug) < attempt_debug_limit:
            attempt_debug.append({**candidate_best.as_dict(), "accepted": False})
        if best is None or _evaluation_key(candidate_best, policy) < _evaluation_key(best, policy):
            best = candidate_best

    summary.zero_marginal_candidates += zero_marginal_seen
    if best is not None and len(attempt_debug) < attempt_debug_limit:
        attempt_debug.append({**best.as_dict(), "accepted": True})
    return best


def _best_position_for_candidate(
    case: RegionalCoverageCase,
    candidate: Candidate,
    *,
    sequence,
    marginal_weight_m2: float,
    policy: GreedyPolicy,
    summary: GreedySummary,
) -> InsertionEvaluation | None:
    best: InsertionEvaluation | None = None
    for position in possible_insertion_positions(sequence, candidate):
        summary.attempted_insertions += 1
        result = check_insertion(case, sequence, candidate, position)
        if not result.success:
            continue
        transition_burden_s = sum(item.required_gap_s for item in result.transition_checks)
        evaluation = InsertionEvaluation(
            candidate=candidate,
            position=position,
            insertion_result=result,
            marginal_weight_m2=marginal_weight_m2,
            transition_burden_s=transition_burden_s,
            energy_estimate_wh=candidate.estimated_energy_wh,
            duty_estimate_s=candidate.duration_s,
        )
        if best is None or _evaluation_key(evaluation, policy) < _evaluation_key(best, policy):
            best = evaluation
    return best


def _evaluation_key(evaluation: InsertionEvaluation, policy: GreedyPolicy) -> tuple[Any, ...]:
    if policy == "coverage_per_transition_burden":
        policy_score = evaluation.coverage_per_transition_burden
    elif policy == "coverage_per_imaging_time":
        policy_score = evaluation.coverage_per_imaging_time
    else:
        policy_score = evaluation.marginal_weight_m2
    candidate = evaluation.candidate
    return (
        -policy_score,
        -evaluation.marginal_weight_m2,
        evaluation.transition_burden_s,
        evaluation.energy_estimate_wh,
        candidate.start_offset_s,
        candidate.candidate_id,
        evaluation.position,
    )


def _record_rejection_reasons(
    case: RegionalCoverageCase,
    candidate: Candidate,
    sequence,
    summary: GreedySummary,
) -> None:
    positions = possible_insertion_positions(sequence, candidate)
    if not positions:
        summary.reject_reasons["no_chronological_position"] = (
            summary.reject_reasons.get("no_chronological_position", 0) + 1
        )
        return
    seen = False
    for position in positions:
        result = check_insertion(case, sequence, candidate, position)
        for reason in result.reject_reasons:
            seen = True
            summary.reject_reasons[reason] = summary.reject_reasons.get(reason, 0) + 1
    if not seen:
        summary.reject_reasons["unknown_rejection"] = summary.reject_reasons.get("unknown_rejection", 0) + 1


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("optional integer limits must be positive when set")
    return parsed


def _optional_positive_float(value: Any) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if parsed <= 0.0:
        raise ValueError("optional float limits must be positive when set")
    return parsed


def _non_negative_int(value: Any, field: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative")
    return parsed
