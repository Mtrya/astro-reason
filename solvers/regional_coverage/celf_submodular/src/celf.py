"""Standalone CELF selection over fixed regional-coverage candidates."""

from __future__ import annotations

import heapq
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

import yaml

from candidates import StripCandidate


SelectionPolicy = Literal["unit_cost", "cost_benefit"]
CostMode = Literal["action_count", "imaging_time", "estimated_energy", "transition_burden"]
FeasibilityCheck = Callable[[tuple[str, ...], str], tuple[bool, str]]


@dataclass(frozen=True, slots=True)
class SelectionConfig:
    run_unit_cost: bool = True
    run_cost_benefit: bool = True
    cost_mode: CostMode = "action_count"
    budget: float | None = None
    min_marginal_gain: float = 0.0
    schedule_aware: bool = True
    compute_online_bounds: bool = True
    max_bound_order_debug: int = 50
    write_iteration_trace: bool = True
    max_iteration_debug: int = 2_000

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "run_unit_cost": self.run_unit_cost,
            "run_cost_benefit": self.run_cost_benefit,
            "cost_mode": self.cost_mode,
            "budget": self.budget,
            "min_marginal_gain": self.min_marginal_gain,
            "schedule_aware": self.schedule_aware,
            "compute_online_bounds": self.compute_online_bounds,
            "max_bound_order_debug": self.max_bound_order_debug,
            "write_iteration_trace": self.write_iteration_trace,
            "max_iteration_debug": self.max_iteration_debug,
        }


DEFAULT_SELECTION_CONFIG = SelectionConfig()


@dataclass(frozen=True, slots=True)
class SelectionStep:
    policy: SelectionPolicy
    event: str
    candidate_id: str | None
    selected_count: int
    budget_used: float
    marginal_gain: float
    priority_score: float
    cost: float
    covered_sample_count: int
    skip_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "policy": self.policy,
            "event": self.event,
            "candidate_id": self.candidate_id,
            "selected_count": self.selected_count,
            "budget_used": self.budget_used,
            "marginal_gain": self.marginal_gain,
            "priority_score": self.priority_score,
            "cost": self.cost,
            "covered_sample_count": self.covered_sample_count,
        }
        if self.skip_reason is not None:
            payload["skip_reason"] = self.skip_reason
        return payload


@dataclass(frozen=True, slots=True)
class OnlineBoundTerm:
    rank: int
    candidate_id: str
    marginal_gain: float
    cost: float
    marginal_per_cost: float
    selected_fraction: float
    cumulative_cost: float
    cumulative_bound_increment: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "candidate_id": self.candidate_id,
            "marginal_gain": self.marginal_gain,
            "cost": self.cost,
            "marginal_per_cost": self.marginal_per_cost,
            "selected_fraction": self.selected_fraction,
            "cumulative_cost": self.cumulative_cost,
            "cumulative_bound_increment": self.cumulative_bound_increment,
        }


@dataclass(frozen=True, slots=True)
class OnlineBoundResult:
    scope: str
    policy: SelectionPolicy
    cost_mode: CostMode
    candidate_count: int
    selected_count: int
    selected_reward: float
    budget: float
    selected_cost: float
    residual_budget: float
    online_upper_bound: float
    gap: float
    gap_ratio: float | None
    bound_type: str
    ordering_key: str
    marginal_recomputations: int
    full_terms_used: int
    fractional_term_used: bool
    ordering: tuple[OnlineBoundTerm, ...]
    ordering_truncated: bool
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "policy": self.policy,
            "cost_mode": self.cost_mode,
            "candidate_count": self.candidate_count,
            "selected_count": self.selected_count,
            "selected_reward": self.selected_reward,
            "budget": self.budget,
            "selected_cost": self.selected_cost,
            "residual_budget": self.residual_budget,
            "online_upper_bound": self.online_upper_bound,
            "gap": self.gap,
            "gap_ratio": self.gap_ratio,
            "bound_type": self.bound_type,
            "ordering_key": self.ordering_key,
            "marginal_recomputations": self.marginal_recomputations,
            "full_terms_used": self.full_terms_used,
            "fractional_term_used": self.fractional_term_used,
            "ordering": [term.as_dict() for term in self.ordering],
            "ordering_truncated": self.ordering_truncated,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class SelectionResult:
    policy: SelectionPolicy
    candidate_count: int
    initial_queue_count: int
    selected_candidate_ids: tuple[str, ...]
    objective_value: float
    budget: float
    budget_used: float
    covered_sample_indices: tuple[int, ...]
    marginal_recomputations: int
    stale_pops: int
    accepted_count: int
    rejected_nonpositive_count: int
    skipped_over_budget_count: int
    skipped_infeasible_count: int
    infeasible_skip_counts: dict[str, int]
    stop_reason: str
    iterations: tuple[SelectionStep, ...]
    online_bound: OnlineBoundResult | None = None

    @property
    def covered_sample_count(self) -> int:
        return len(self.covered_sample_indices)

    def as_dict(self, *, include_iterations: bool = False) -> dict[str, Any]:
        naive_bound = naive_recomputation_bound(
            self.initial_queue_count,
            self.accepted_count,
            stop_reason=self.stop_reason,
        )
        payload = {
            "policy": self.policy,
            "candidate_count": self.candidate_count,
            "initial_queue_count": self.initial_queue_count,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "objective_value": self.objective_value,
            "budget": self.budget,
            "budget_used": self.budget_used,
            "covered_sample_count": self.covered_sample_count,
            "marginal_recomputations": self.marginal_recomputations,
            "estimated_naive_recomputations": naive_bound,
            "estimated_lazy_recomputations_saved": max(
                0, naive_bound - self.marginal_recomputations
            ),
            "lazy_recomputation_ratio": (
                self.marginal_recomputations / naive_bound if naive_bound > 0 else None
            ),
            "stale_pops": self.stale_pops,
            "accepted_count": self.accepted_count,
            "rejected_nonpositive_count": self.rejected_nonpositive_count,
            "skipped_over_budget_count": self.skipped_over_budget_count,
            "skipped_infeasible_count": self.skipped_infeasible_count,
            "infeasible_skip_counts": self.infeasible_skip_counts,
            "stop_reason": self.stop_reason,
            "online_bound": self.online_bound.as_dict() if self.online_bound else None,
        }
        if include_iterations:
            payload["iterations"] = [step.as_dict() for step in self.iterations]
        return payload


@dataclass(frozen=True, slots=True)
class CelfRunResult:
    best_policy: SelectionPolicy
    best: SelectionResult
    unit_cost: SelectionResult | None
    cost_benefit: SelectionResult | None
    cost_mode: CostMode
    candidate_count: int
    timing_seconds: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "best_policy": self.best_policy,
            "cost_mode": self.cost_mode,
            "candidate_count": self.candidate_count,
            "timing_seconds": self.timing_seconds,
            "algorithm": {
                "paper": "Leskovec et al. CELF / CEF lazy forward selection",
                "unit_cost_variant": self.unit_cost is not None,
                "cost_benefit_variant": self.cost_benefit is not None,
                "returns_higher_reward_variant": True,
                "fixed_ground_set": True,
                "reward_model": "monotone unique weighted coverage over fixed sample sets",
            },
            "best": self.best.as_dict(),
            "unit_cost": self.unit_cost.as_dict() if self.unit_cost else None,
            "cost_benefit": self.cost_benefit.as_dict() if self.cost_benefit else None,
        }


def load_selection_config(config_dir: Path | None) -> SelectionConfig:
    if config_dir is None or not config_dir:
        return SelectionConfig()
    path = config_dir / "config.yaml"
    if not path.is_file():
        return SelectionConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a mapping")
    section = raw.get("selection", {})
    if not section:
        return SelectionConfig()
    if not isinstance(section, dict):
        raise ValueError(f"{path}: selection must be a mapping")
    return SelectionConfig(
        run_unit_cost=bool(section.get("run_unit_cost", DEFAULT_SELECTION_CONFIG.run_unit_cost)),
        run_cost_benefit=bool(
            section.get("run_cost_benefit", DEFAULT_SELECTION_CONFIG.run_cost_benefit)
        ),
        cost_mode=str(section.get("cost_mode", DEFAULT_SELECTION_CONFIG.cost_mode)),
        budget=(
            float(section["budget"]) if section.get("budget") is not None else None
        ),
        min_marginal_gain=float(
            section.get("min_marginal_gain", DEFAULT_SELECTION_CONFIG.min_marginal_gain)
        ),
        schedule_aware=bool(
            section.get("schedule_aware", DEFAULT_SELECTION_CONFIG.schedule_aware)
        ),
        write_iteration_trace=bool(
            section.get(
                "write_iteration_trace", DEFAULT_SELECTION_CONFIG.write_iteration_trace
            )
        ),
        max_iteration_debug=int(
            section.get("max_iteration_debug", DEFAULT_SELECTION_CONFIG.max_iteration_debug)
        ),
        compute_online_bounds=bool(
            section.get(
                "compute_online_bounds",
                DEFAULT_SELECTION_CONFIG.compute_online_bounds,
            )
        ),
        max_bound_order_debug=int(
            section.get(
                "max_bound_order_debug",
                DEFAULT_SELECTION_CONFIG.max_bound_order_debug,
            )
        ),
    )


def sample_weight_lookup(sample_weights: tuple[float, ...] | dict[int, float]) -> dict[int, float]:
    if isinstance(sample_weights, dict):
        return dict(sample_weights)
    return {index: float(weight) for index, weight in enumerate(sample_weights)}


def marginal_gain(
    candidate_id: str,
    coverage_by_candidate: dict[str, tuple[int, ...]],
    covered_samples: set[int],
    sample_weights: dict[int, float],
) -> float:
    return sum(
        sample_weights[index]
        for index in coverage_by_candidate.get(candidate_id, ())
        if index not in covered_samples
    )


def coverage_objective(
    candidate_ids: tuple[str, ...],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
) -> float:
    covered: set[int] = set()
    for candidate_id in candidate_ids:
        covered.update(coverage_by_candidate.get(candidate_id, ()))
    return sum(sample_weights[index] for index in covered)


def naive_recomputation_bound(
    initial_queue_count: int, accepted_count: int, *, stop_reason: str
) -> int:
    rounds = accepted_count
    if stop_reason in {"no_positive_gain", "candidate_queue_exhausted"}:
        rounds += 1
    total = 0
    for index in range(rounds):
        remaining = initial_queue_count - index
        if remaining <= 0:
            break
        total += remaining
    return total


def candidate_cost(candidate: StripCandidate, cost_mode: CostMode) -> float:
    if cost_mode == "action_count":
        return 1.0
    if cost_mode == "imaging_time":
        return float(candidate.duration_s)
    if cost_mode == "estimated_energy":
        # The solve path can pass a satellite-aware energy cost map. This
        # fallback keeps the selector usable as a standalone fixed-set engine.
        return float(candidate.duration_s)
    if cost_mode == "transition_burden":
        return 1.0 + abs(candidate.roll_deg) / 90.0
    raise ValueError(f"unknown cost mode {cost_mode!r}")


def _priority_tuple(
    *,
    policy: SelectionPolicy,
    marginal: float,
    cost: float,
    candidate: StripCandidate,
) -> tuple[float, float, float, int, float, str]:
    score = marginal if policy == "unit_cost" else marginal / cost
    return (
        -score,
        -marginal,
        cost,
        candidate.start_offset_s,
        abs(candidate.roll_deg),
        candidate.candidate_id,
    )


def _score(policy: SelectionPolicy, marginal: float, cost: float) -> float:
    return marginal if policy == "unit_cost" else marginal / cost


def _default_feasibility_check(
    selected_candidate_ids: tuple[str, ...], candidate_id: str
) -> tuple[bool, str]:
    return (True, "feasible")


def fixed_set_online_bound(
    candidates: list[StripCandidate],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
    *,
    selected_candidate_ids: tuple[str, ...],
    budget: float,
    policy: SelectionPolicy,
    cost_mode: CostMode = "action_count",
    cost_by_candidate: dict[str, float] | None = None,
    max_order_debug: int = 50,
) -> OnlineBoundResult:
    costs = cost_by_candidate or {
        candidate.candidate_id: candidate_cost(candidate, cost_mode) for candidate in candidates
    }
    selected_set = set(selected_candidate_ids)
    selected_cost = sum(costs[candidate_id] for candidate_id in selected_candidate_ids)
    selected_reward = coverage_objective(
        selected_candidate_ids,
        coverage_by_candidate,
        sample_weights,
    )
    residual_budget = max(0.0, budget - selected_cost)
    covered_samples: set[int] = set()
    for candidate_id in selected_candidate_ids:
        covered_samples.update(coverage_by_candidate.get(candidate_id, ()))

    ordered: list[tuple[float, float, float, int, float, str, float]] = []
    recomputations = 0
    for candidate in candidates:
        candidate_id = candidate.candidate_id
        if candidate_id in selected_set:
            continue
        cost = costs[candidate_id]
        if cost <= 0.0:
            raise ValueError(f"{candidate_id}: candidate cost must be positive")
        marginal = marginal_gain(
            candidate_id,
            coverage_by_candidate,
            covered_samples,
            sample_weights,
        )
        recomputations += 1
        ratio = marginal / cost
        ordered.append(
            (
                -ratio,
                -marginal,
                cost,
                candidate.start_offset_s,
                abs(candidate.roll_deg),
                candidate_id,
                marginal,
            )
        )
    ordered.sort()

    bound_increment = 0.0
    consumed = 0.0
    full_terms = 0
    fractional_term = False
    debug_terms: list[OnlineBoundTerm] = []
    for rank, row in enumerate(ordered, start=1):
        _, _, cost, _, _, candidate_id, marginal = row
        if marginal <= 0.0:
            break
        if residual_budget <= 1.0e-9:
            break
        remaining = residual_budget - consumed
        if remaining <= 1.0e-9:
            break
        fraction = min(1.0, remaining / cost)
        if fraction >= 1.0 - 1.0e-12:
            fraction = 1.0
            full_terms += 1
        else:
            fractional_term = True
        consumed += cost * fraction
        bound_increment += marginal * fraction
        if len(debug_terms) < max(0, max_order_debug):
            debug_terms.append(
                OnlineBoundTerm(
                    rank=rank,
                    candidate_id=candidate_id,
                    marginal_gain=marginal,
                    cost=cost,
                    marginal_per_cost=marginal / cost,
                    selected_fraction=fraction,
                    cumulative_cost=consumed,
                    cumulative_bound_increment=bound_increment,
                )
            )
        if fraction < 1.0:
            break

    upper_bound = selected_reward + bound_increment
    gap = max(0.0, upper_bound - selected_reward)
    used_term_count = full_terms + (1 if fractional_term else 0)
    return OnlineBoundResult(
        scope="fixed_candidate_set_only",
        policy=policy,
        cost_mode=cost_mode,
        candidate_count=len(candidates),
        selected_count=len(selected_candidate_ids),
        selected_reward=selected_reward,
        budget=budget,
        selected_cost=selected_cost,
        residual_budget=residual_budget,
        online_upper_bound=upper_bound,
        gap=gap,
        gap_ratio=(gap / upper_bound if upper_bound > 0.0 else None),
        bound_type=("unit_cost" if cost_mode == "action_count" else "nonuniform_cost"),
        ordering_key="marginal_gain_per_cost_desc_then_marginal_desc_then_candidate_order",
        marginal_recomputations=recomputations,
        full_terms_used=full_terms,
        fractional_term_used=fractional_term,
        ordering=tuple(debug_terms),
        ordering_truncated=len(debug_terms) < used_term_count,
        notes=(
            "Leskovec Section 3.2 online bound evaluated after CELF over the fixed benchmark-adapted candidate set.",
            "This certificate does not bound continuous satellite schedules or post-repair verifier score.",
        ),
    )


def _result_better(left: SelectionResult, right: SelectionResult) -> bool:
    return (
        left.objective_value,
        -left.budget_used,
        -left.accepted_count,
        left.policy == "unit_cost",
    ) > (
        right.objective_value,
        -right.budget_used,
        -right.accepted_count,
        right.policy == "unit_cost",
    )


def lazy_forward_selection(
    candidates: list[StripCandidate],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
    *,
    budget: float,
    policy: SelectionPolicy,
    cost_mode: CostMode = "action_count",
    cost_by_candidate: dict[str, float] | None = None,
    min_marginal_gain: float = 0.0,
    max_iteration_debug: int = 2_000,
    compute_online_bound: bool = True,
    max_bound_order_debug: int = 50,
    feasibility_check: FeasibilityCheck | None = None,
) -> SelectionResult:
    if budget <= 0.0:
        return SelectionResult(
            policy=policy,
            candidate_count=len(candidates),
            initial_queue_count=0,
            selected_candidate_ids=(),
            objective_value=0.0,
            budget=budget,
            budget_used=0.0,
            covered_sample_indices=(),
            marginal_recomputations=0,
            stale_pops=0,
            accepted_count=0,
            rejected_nonpositive_count=0,
            skipped_over_budget_count=0,
            skipped_infeasible_count=0,
            infeasible_skip_counts={},
            stop_reason="zero_budget",
            iterations=(),
        )

    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    costs = cost_by_candidate or {
        candidate.candidate_id: candidate_cost(candidate, cost_mode) for candidate in candidates
    }
    heap: list[tuple[float, float, float, int, float, str, int, float]] = []
    skipped_over_budget = 0
    skipped_infeasible = 0
    infeasible_skip_counts: Counter[str] = Counter()
    for candidate in candidates:
        cost = costs[candidate.candidate_id]
        if cost <= 0.0:
            raise ValueError(f"{candidate.candidate_id}: candidate cost must be positive")
        if cost > budget:
            skipped_over_budget += 1
            continue
        heapq.heappush(
            heap,
            (
                float("-inf"),
                float("-inf"),
                cost,
                candidate.start_offset_s,
                abs(candidate.roll_deg),
                candidate.candidate_id,
                -1,
                float("inf"),
            ),
        )
    initial_queue_count = len(heap)

    selected_ids: list[str] = []
    selected_id_set: set[str] = set()
    covered_samples: set[int] = set()
    objective_value = 0.0
    budget_used = 0.0
    recomputations = 0
    stale_pops = 0
    rejected_nonpositive = 0
    iterations: list[SelectionStep] = []
    stop_reason = "candidate_queue_exhausted"
    check_feasible = feasibility_check or _default_feasibility_check

    while heap:
        entry = heapq.heappop(heap)
        candidate_id = entry[5]
        candidate = candidate_by_id[candidate_id]
        if candidate_id in selected_id_set:
            continue
        cost = costs[candidate_id]
        if budget_used + cost > budget + 1.0e-9:
            skipped_over_budget += 1
            continue
        current_round = len(selected_ids)
        if entry[6] == current_round:
            marginal = entry[7]
            if marginal <= min_marginal_gain:
                stop_reason = "no_positive_gain"
                break
            feasible, infeasible_reason = check_feasible(tuple(selected_ids), candidate_id)
            if not feasible:
                skipped_infeasible += 1
                infeasible_skip_counts[infeasible_reason] += 1
                if len(iterations) < max_iteration_debug:
                    iterations.append(
                        SelectionStep(
                            policy=policy,
                            event="skip_infeasible",
                            candidate_id=candidate_id,
                            selected_count=len(selected_ids),
                            budget_used=budget_used,
                            marginal_gain=marginal,
                            priority_score=_score(policy, marginal, cost),
                            cost=cost,
                            covered_sample_count=len(covered_samples),
                            skip_reason=infeasible_reason,
                        )
                    )
                continue
            selected_ids.append(candidate_id)
            selected_id_set.add(candidate_id)
            budget_used += cost
            objective_value += marginal
            covered_samples.update(coverage_by_candidate.get(candidate_id, ()))
            if len(iterations) < max_iteration_debug:
                iterations.append(
                    SelectionStep(
                        policy=policy,
                        event="accept",
                        candidate_id=candidate_id,
                        selected_count=len(selected_ids),
                        budget_used=budget_used,
                        marginal_gain=marginal,
                        priority_score=_score(policy, marginal, cost),
                        cost=cost,
                        covered_sample_count=len(covered_samples),
                    )
                )
            if budget_used >= budget - 1.0e-9:
                stop_reason = "budget_exhausted"
                break
            continue

        stale_pops += 1
        recomputations += 1
        marginal = marginal_gain(
            candidate_id, coverage_by_candidate, covered_samples, sample_weights
        )
        if marginal <= min_marginal_gain:
            rejected_nonpositive += 1
            if len(iterations) < max_iteration_debug:
                iterations.append(
                    SelectionStep(
                        policy=policy,
                        event="reject_nonpositive",
                        candidate_id=candidate_id,
                        selected_count=len(selected_ids),
                        budget_used=budget_used,
                        marginal_gain=marginal,
                        priority_score=_score(policy, marginal, cost),
                        cost=cost,
                        covered_sample_count=len(covered_samples),
                    )
                )
            continue
        heapq.heappush(
            heap,
            (
                *_priority_tuple(
                    policy=policy,
                    marginal=marginal,
                    cost=cost,
                    candidate=candidate,
                ),
                current_round,
                marginal,
            ),
        )
        if len(iterations) < max_iteration_debug:
            iterations.append(
                SelectionStep(
                    policy=policy,
                    event="recompute",
                    candidate_id=candidate_id,
                    selected_count=len(selected_ids),
                    budget_used=budget_used,
                    marginal_gain=marginal,
                    priority_score=_score(policy, marginal, cost),
                    cost=cost,
                    covered_sample_count=len(covered_samples),
                )
            )

    selected_tuple = tuple(selected_ids)
    online_bound = None
    if compute_online_bound:
        online_bound = fixed_set_online_bound(
            candidates,
            coverage_by_candidate,
            sample_weights,
            selected_candidate_ids=selected_tuple,
            budget=budget,
            policy=policy,
            cost_mode=cost_mode,
            cost_by_candidate=cost_by_candidate,
            max_order_debug=max_bound_order_debug,
        )

    return SelectionResult(
        policy=policy,
        candidate_count=len(candidates),
        initial_queue_count=initial_queue_count,
        selected_candidate_ids=selected_tuple,
        objective_value=objective_value,
        budget=budget,
        budget_used=budget_used,
        covered_sample_indices=tuple(sorted(covered_samples)),
        marginal_recomputations=recomputations,
        stale_pops=stale_pops,
        accepted_count=len(selected_ids),
        rejected_nonpositive_count=rejected_nonpositive,
        skipped_over_budget_count=skipped_over_budget,
        skipped_infeasible_count=skipped_infeasible,
        infeasible_skip_counts=dict(sorted(infeasible_skip_counts.items())),
        stop_reason=stop_reason,
        iterations=tuple(iterations),
        online_bound=online_bound,
    )


def naive_forward_selection(
    candidates: list[StripCandidate],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
    *,
    budget: float,
    policy: SelectionPolicy,
    cost_mode: CostMode = "action_count",
    cost_by_candidate: dict[str, float] | None = None,
    min_marginal_gain: float = 0.0,
    compute_online_bound: bool = False,
    max_bound_order_debug: int = 50,
) -> SelectionResult:
    selected_ids: list[str] = []
    remaining = {candidate.candidate_id for candidate in candidates}
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    costs = cost_by_candidate or {
        candidate.candidate_id: candidate_cost(candidate, cost_mode) for candidate in candidates
    }
    initial_queue_count = sum(1 for cost in costs.values() if cost <= budget + 1.0e-9)
    covered_samples: set[int] = set()
    budget_used = 0.0
    objective_value = 0.0
    recomputations = 0
    skipped_over_budget = 0
    iterations: list[SelectionStep] = []
    stop_reason = "candidate_queue_exhausted"

    while remaining:
        best: tuple[tuple[float, float, float, int, float, str], str, float] | None = None
        over_budget_this_round = 0
        for candidate_id in sorted(remaining):
            candidate = candidate_by_id[candidate_id]
            cost = costs[candidate_id]
            if cost <= 0.0:
                raise ValueError(f"{candidate_id}: candidate cost must be positive")
            if budget_used + cost > budget + 1.0e-9:
                over_budget_this_round += 1
                continue
            recomputations += 1
            marginal = marginal_gain(
                candidate_id, coverage_by_candidate, covered_samples, sample_weights
            )
            priority = _priority_tuple(
                policy=policy, marginal=marginal, cost=cost, candidate=candidate
            )
            if best is None or priority < best[0]:
                best = (priority, candidate_id, marginal)
        skipped_over_budget += over_budget_this_round
        if best is None:
            stop_reason = "budget_exhausted"
            break
        _, candidate_id, marginal = best
        candidate = candidate_by_id[candidate_id]
        cost = costs[candidate_id]
        if marginal <= min_marginal_gain:
            stop_reason = "no_positive_gain"
            break
        remaining.remove(candidate_id)
        selected_ids.append(candidate_id)
        budget_used += cost
        objective_value += marginal
        covered_samples.update(coverage_by_candidate.get(candidate_id, ()))
        iterations.append(
            SelectionStep(
                policy=policy,
                event="accept",
                candidate_id=candidate_id,
                selected_count=len(selected_ids),
                budget_used=budget_used,
                marginal_gain=marginal,
                priority_score=_score(policy, marginal, cost),
                cost=cost,
                covered_sample_count=len(covered_samples),
            )
        )
        if budget_used >= budget - 1.0e-9:
            stop_reason = "budget_exhausted"
            break

    selected_tuple = tuple(selected_ids)
    online_bound = None
    if compute_online_bound:
        online_bound = fixed_set_online_bound(
            candidates,
            coverage_by_candidate,
            sample_weights,
            selected_candidate_ids=selected_tuple,
            budget=budget,
            policy=policy,
            cost_mode=cost_mode,
            cost_by_candidate=cost_by_candidate,
            max_order_debug=max_bound_order_debug,
        )

    return SelectionResult(
        policy=policy,
        candidate_count=len(candidates),
        initial_queue_count=initial_queue_count,
        selected_candidate_ids=selected_tuple,
        objective_value=objective_value,
        budget=budget,
        budget_used=budget_used,
        covered_sample_indices=tuple(sorted(covered_samples)),
        marginal_recomputations=recomputations,
        stale_pops=0,
        accepted_count=len(selected_ids),
        rejected_nonpositive_count=0,
        skipped_over_budget_count=skipped_over_budget,
        skipped_infeasible_count=0,
        infeasible_skip_counts={},
        stop_reason=stop_reason,
        iterations=tuple(iterations),
        online_bound=online_bound,
    )


def run_celf_selection(
    candidates: list[StripCandidate],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
    *,
    max_actions_total: int | None,
    config: SelectionConfig,
    cost_by_candidate: dict[str, float] | None = None,
    feasibility_check: FeasibilityCheck | None = None,
) -> CelfRunResult:
    budget = config.budget
    if budget is None:
        budget = float(max_actions_total if max_actions_total is not None else len(candidates))
    results: list[SelectionResult] = []
    unit = None
    cost_benefit = None
    timings: dict[str, float] = {}
    if config.run_unit_cost:
        start = time.perf_counter()
        unit = lazy_forward_selection(
            candidates,
            coverage_by_candidate,
            sample_weights,
            budget=budget,
            policy="unit_cost",
            cost_mode="action_count",
            cost_by_candidate=None,
            min_marginal_gain=config.min_marginal_gain,
            max_iteration_debug=config.max_iteration_debug,
            compute_online_bound=config.compute_online_bounds,
            max_bound_order_debug=config.max_bound_order_debug,
            feasibility_check=feasibility_check if config.schedule_aware else None,
        )
        timings["unit_cost_selection"] = round(time.perf_counter() - start, 6)
        results.append(unit)
    if config.run_cost_benefit:
        start = time.perf_counter()
        cost_benefit = lazy_forward_selection(
            candidates,
            coverage_by_candidate,
            sample_weights,
            budget=budget,
            policy="cost_benefit",
            cost_mode=config.cost_mode,
            cost_by_candidate=cost_by_candidate,
            min_marginal_gain=config.min_marginal_gain,
            max_iteration_debug=config.max_iteration_debug,
            compute_online_bound=config.compute_online_bounds,
            max_bound_order_debug=config.max_bound_order_debug,
            feasibility_check=feasibility_check if config.schedule_aware else None,
        )
        timings["cost_benefit_selection"] = round(time.perf_counter() - start, 6)
        results.append(cost_benefit)
    if not results:
        raise ValueError("selection config disables both unit-cost and cost-benefit CELF")
    timings["total_selection"] = round(sum(timings.values()), 6)
    best = results[0]
    for result in results[1:]:
        if _result_better(result, best):
            best = result
    return CelfRunResult(
        best_policy=best.policy,
        best=best,
        unit_cost=unit,
        cost_benefit=cost_benefit,
        cost_mode=config.cost_mode,
        candidate_count=len(candidates),
        timing_seconds=timings,
    )
