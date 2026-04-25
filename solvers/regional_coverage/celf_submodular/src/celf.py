"""Standalone CELF selection over fixed regional-coverage candidates."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from candidates import StripCandidate


SelectionPolicy = Literal["unit_cost", "cost_benefit"]
CostMode = Literal["action_count", "imaging_time", "estimated_energy", "transition_burden"]


@dataclass(frozen=True, slots=True)
class SelectionConfig:
    run_unit_cost: bool = True
    run_cost_benefit: bool = True
    cost_mode: CostMode = "action_count"
    budget: float | None = None
    min_marginal_gain: float = 0.0
    write_iteration_trace: bool = True
    max_iteration_debug: int = 2_000

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "run_unit_cost": self.run_unit_cost,
            "run_cost_benefit": self.run_cost_benefit,
            "cost_mode": self.cost_mode,
            "budget": self.budget,
            "min_marginal_gain": self.min_marginal_gain,
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

    def as_dict(self) -> dict[str, Any]:
        return {
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
    stop_reason: str
    iterations: tuple[SelectionStep, ...]

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
            "stop_reason": self.stop_reason,
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "best_policy": self.best_policy,
            "cost_mode": self.cost_mode,
            "candidate_count": self.candidate_count,
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
        write_iteration_trace=bool(
            section.get(
                "write_iteration_trace", DEFAULT_SELECTION_CONFIG.write_iteration_trace
            )
        ),
        max_iteration_debug=int(
            section.get("max_iteration_debug", DEFAULT_SELECTION_CONFIG.max_iteration_debug)
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
            stop_reason="zero_budget",
            iterations=(),
        )

    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    costs = cost_by_candidate or {
        candidate.candidate_id: candidate_cost(candidate, cost_mode) for candidate in candidates
    }
    heap: list[tuple[float, float, float, int, float, str, int, float]] = []
    skipped_over_budget = 0
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

    return SelectionResult(
        policy=policy,
        candidate_count=len(candidates),
        initial_queue_count=initial_queue_count,
        selected_candidate_ids=tuple(selected_ids),
        objective_value=objective_value,
        budget=budget,
        budget_used=budget_used,
        covered_sample_indices=tuple(sorted(covered_samples)),
        marginal_recomputations=recomputations,
        stale_pops=stale_pops,
        accepted_count=len(selected_ids),
        rejected_nonpositive_count=rejected_nonpositive,
        skipped_over_budget_count=skipped_over_budget,
        stop_reason=stop_reason,
        iterations=tuple(iterations),
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

    return SelectionResult(
        policy=policy,
        candidate_count=len(candidates),
        initial_queue_count=initial_queue_count,
        selected_candidate_ids=tuple(selected_ids),
        objective_value=objective_value,
        budget=budget,
        budget_used=budget_used,
        covered_sample_indices=tuple(sorted(covered_samples)),
        marginal_recomputations=recomputations,
        stale_pops=0,
        accepted_count=len(selected_ids),
        rejected_nonpositive_count=0,
        skipped_over_budget_count=skipped_over_budget,
        stop_reason=stop_reason,
        iterations=tuple(iterations),
    )


def run_celf_selection(
    candidates: list[StripCandidate],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    sample_weights: dict[int, float],
    *,
    max_actions_total: int | None,
    config: SelectionConfig,
    cost_by_candidate: dict[str, float] | None = None,
) -> CelfRunResult:
    budget = config.budget
    if budget is None:
        budget = float(max_actions_total if max_actions_total is not None else len(candidates))
    results: list[SelectionResult] = []
    unit = None
    cost_benefit = None
    if config.run_unit_cost:
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
        )
        results.append(unit)
    if config.run_cost_benefit:
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
        )
        results.append(cost_benefit)
    if not results:
        raise ValueError("selection config disables both unit-cost and cost-benefit CELF")
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
    )
