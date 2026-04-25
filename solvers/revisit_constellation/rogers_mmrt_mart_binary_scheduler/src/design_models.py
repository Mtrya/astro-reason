"""Bounded Rogers-style design models over visibility timelines."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import math
from typing import Iterable

from .case_io import RevisitCase, SolverConfig
from .slot_library import OrbitSlot
from .visibility_matrix import VisibilityMatrix


@dataclass(frozen=True)
class DesignProblem:
    matrix: VisibilityMatrix
    slot_ids: tuple[str, ...]
    target_ids: tuple[str, ...]
    sample_step_sec: float
    expected_revisit_hours: tuple[float, ...]
    max_selected_slots: int
    fixed_satellite_count: int | None = None


@dataclass(frozen=True)
class TargetDesignStats:
    target_id: str
    covered_samples: int
    max_gap_samples: int
    mean_gap_samples: float
    max_gap_hours: float
    mean_gap_hours: float
    expected_revisit_hours: float
    threshold_gap_samples: int
    threshold_excess_samples: int
    gap_count: int

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "target_id": self.target_id,
            "covered_samples": self.covered_samples,
            "max_gap_samples": self.max_gap_samples,
            "mean_gap_samples": self.mean_gap_samples,
            "max_gap_hours": self.max_gap_hours,
            "mean_gap_hours": self.mean_gap_hours,
            "expected_revisit_hours": self.expected_revisit_hours,
            "threshold_gap_samples": self.threshold_gap_samples,
            "threshold_excess_samples": self.threshold_excess_samples,
            "gap_count": self.gap_count,
        }


@dataclass(frozen=True)
class DesignResult:
    mode: str
    backend: str
    fallback_reason: str | None
    selected_slot_indices: tuple[int, ...]
    selected_slot_ids: tuple[str, ...]
    objective: dict[str, float | int | bool | str]
    target_stats: tuple[TargetDesignStats, ...]
    model_size: dict[str, int]
    notes: tuple[str, ...] = ()

    def to_summary(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "backend": self.backend,
            "fallback_reason": self.fallback_reason,
            "selected_slot_indices": list(self.selected_slot_indices),
            "selected_slot_ids": list(self.selected_slot_ids),
            "objective": self.objective,
            "target_stats": [stats.to_dict() for stats in self.target_stats],
            "model_size": self.model_size,
            "notes": list(self.notes),
        }


def build_design_problem(
    case: RevisitCase,
    config: SolverConfig,
    slots: tuple[OrbitSlot, ...],
    matrix: VisibilityMatrix,
) -> DesignProblem:
    fixed_count = config.design_satellite_count
    if fixed_count is None and config.design_mode in {"mmrt", "mart"}:
        fixed_count = min(config.design_max_selected_slots, case.max_num_satellites, len(slots))
    max_selected = min(config.design_max_selected_slots, case.max_num_satellites, len(slots))
    if fixed_count is not None:
        fixed_count = min(fixed_count, case.max_num_satellites, len(slots))
        max_selected = max(max_selected, fixed_count)
    return DesignProblem(
        matrix=matrix,
        slot_ids=tuple(slot.slot_id for slot in slots),
        target_ids=tuple(target.target_id for target in case.targets),
        sample_step_sec=config.sample_step_sec,
        expected_revisit_hours=tuple(
            target.expected_revisit_period_hours for target in case.targets
        ),
        max_selected_slots=max_selected,
        fixed_satellite_count=fixed_count,
    )


def estimate_model_size(problem: DesignProblem, mode: str) -> dict[str, int]:
    time_count, slot_count, target_count = problem.matrix.shape
    y_variables = time_count * target_count
    x_variables = slot_count
    if mode == "mmrt":
        variables = x_variables + y_variables + y_variables + 1
        constraints = (2 * y_variables) + (4 * y_variables) + 1
    elif mode == "mart":
        variables = x_variables + y_variables + y_variables + y_variables + target_count
        constraints = (2 * y_variables) + (6 * y_variables) + 1
    elif mode == "threshold_first":
        variables = x_variables + y_variables + y_variables
        constraints = (2 * y_variables) + (4 * y_variables) + target_count
    else:
        variables = x_variables + y_variables
        constraints = 2 * y_variables
    return {
        "slots": slot_count,
        "time_samples": time_count,
        "targets": target_count,
        "binary_variables_estimate": variables,
        "constraints_estimate": constraints,
    }


def _covered_timelines(
    problem: DesignProblem, selected_slot_indices: Iterable[int]
) -> tuple[tuple[bool, ...], ...]:
    time_count, _, target_count = problem.matrix.shape
    selected = frozenset(selected_slot_indices)
    timelines = [[False for _ in range(time_count)] for _ in range(target_count)]
    for time_index, slot_index, target_index in problem.matrix.visible:
        if slot_index in selected:
            timelines[target_index][time_index] = True
    return tuple(tuple(target_timeline) for target_timeline in timelines)


def _uncovered_runs(timeline: tuple[bool, ...]) -> tuple[int, ...]:
    runs: list[int] = []
    current = 0
    for covered in timeline:
        if covered:
            if current:
                runs.append(current)
                current = 0
        else:
            current += 1
    if current:
        runs.append(current)
    return tuple(runs)


def evaluate_selection(
    problem: DesignProblem, selected_slot_indices: Iterable[int]
) -> tuple[dict[str, float | int | bool], tuple[TargetDesignStats, ...]]:
    timelines = _covered_timelines(problem, selected_slot_indices)
    target_stats: list[TargetDesignStats] = []
    for target_index, timeline in enumerate(timelines):
        runs = _uncovered_runs(timeline)
        max_gap_samples = max(runs) if runs else 0
        mean_gap_samples = (sum(runs) / len(runs)) if runs else 0.0
        threshold_gap_samples = max(
            1,
            math.ceil(
                (problem.expected_revisit_hours[target_index] * 3600.0)
                / problem.sample_step_sec
            ),
        )
        target_stats.append(
            TargetDesignStats(
                target_id=problem.target_ids[target_index],
                covered_samples=sum(1 for covered in timeline if covered),
                max_gap_samples=max_gap_samples,
                mean_gap_samples=mean_gap_samples,
                max_gap_hours=(max_gap_samples * problem.sample_step_sec) / 3600.0,
                mean_gap_hours=(mean_gap_samples * problem.sample_step_sec) / 3600.0,
                expected_revisit_hours=problem.expected_revisit_hours[target_index],
                threshold_gap_samples=threshold_gap_samples,
                threshold_excess_samples=max(0, max_gap_samples - threshold_gap_samples),
                gap_count=len(runs),
            )
        )

    selected_count = len(tuple(selected_slot_indices))
    max_gap_samples = max((stats.max_gap_samples for stats in target_stats), default=0)
    sum_max_gap_samples = sum(stats.max_gap_samples for stats in target_stats)
    sum_mean_gap_samples = sum(stats.mean_gap_samples for stats in target_stats)
    total_covered_samples = sum(stats.covered_samples for stats in target_stats)
    threshold_excess_samples = sum(stats.threshold_excess_samples for stats in target_stats)
    threshold_violations = sum(
        1 for stats in target_stats if stats.threshold_excess_samples > 0
    )
    worst_threshold_excess = max(
        (stats.threshold_excess_samples for stats in target_stats), default=0
    )
    objective = {
        "selected_count": selected_count,
        "max_gap_samples": max_gap_samples,
        "max_gap_hours": (max_gap_samples * problem.sample_step_sec) / 3600.0,
        "sum_max_gap_samples": sum_max_gap_samples,
        "sum_mean_gap_samples": sum_mean_gap_samples,
        "mean_gap_hours_sum": (sum_mean_gap_samples * problem.sample_step_sec) / 3600.0,
        "total_covered_samples": total_covered_samples,
        "threshold_violations": threshold_violations,
        "threshold_excess_samples": threshold_excess_samples,
        "worst_threshold_excess_samples": worst_threshold_excess,
        "threshold_satisfied": threshold_violations == 0,
    }
    return objective, tuple(target_stats)


def _objective_key(
    problem: DesignProblem,
    selected_slot_indices: tuple[int, ...],
    mode: str,
    threshold_metric: str,
) -> tuple[float | int | tuple[int, ...], ...]:
    objective, _ = evaluate_selection(problem, selected_slot_indices)
    common_tiebreak = (
        -int(objective["total_covered_samples"]),
        len(selected_slot_indices),
        selected_slot_indices,
    )
    if mode == "mmrt":
        return (
            int(objective["max_gap_samples"]),
            int(objective["sum_max_gap_samples"]),
            float(objective["sum_mean_gap_samples"]),
            *common_tiebreak,
        )
    if mode == "mart":
        return (
            float(objective["sum_mean_gap_samples"]),
            int(objective["max_gap_samples"]),
            int(objective["sum_max_gap_samples"]),
            *common_tiebreak,
        )
    if mode == "threshold_first":
        secondary = (
            int(objective["max_gap_samples"])
            if threshold_metric == "mmrt"
            else float(objective["sum_mean_gap_samples"])
        )
        return (
            int(objective["threshold_violations"]),
            int(objective["worst_threshold_excess_samples"]),
            int(objective["threshold_excess_samples"]),
            len(selected_slot_indices),
            secondary,
            *common_tiebreak,
        )
    if mode == "hybrid":
        return (
            int(objective["threshold_violations"]),
            int(objective["worst_threshold_excess_samples"]),
            int(objective["threshold_excess_samples"]),
            int(objective["max_gap_samples"]),
            float(objective["sum_mean_gap_samples"]),
            len(selected_slot_indices),
            *common_tiebreak,
        )
    raise ValueError(f"unsupported design mode: {mode}")


def _combination_count(slot_count: int, min_size: int, max_size: int) -> int:
    return sum(math.comb(slot_count, size) for size in range(min_size, max_size + 1))


def _candidate_sizes(problem: DesignProblem, mode: str) -> tuple[int, int]:
    if mode in {"mmrt", "mart"} and problem.fixed_satellite_count is not None:
        fixed = min(problem.fixed_satellite_count, len(problem.slot_ids))
        return fixed, fixed
    return 0, min(problem.max_selected_slots, len(problem.slot_ids))


def _enumerate_best(
    problem: DesignProblem,
    mode: str,
    threshold_metric: str,
    max_combinations: int,
) -> tuple[tuple[int, ...] | None, int]:
    slot_count = len(problem.slot_ids)
    min_size, max_size = _candidate_sizes(problem, mode)
    count = _combination_count(slot_count, min_size, max_size)
    if count > max_combinations:
        return None, count

    best: tuple[int, ...] | None = None
    best_key: tuple[float | int | tuple[int, ...], ...] | None = None
    for size in range(min_size, max_size + 1):
        for candidate in combinations(range(slot_count), size):
            key = _objective_key(problem, candidate, mode, threshold_metric)
            if best_key is None or key < best_key:
                best = candidate
                best_key = key
        if mode == "threshold_first" and best is not None:
            objective, _ = evaluate_selection(problem, best)
            if objective["threshold_satisfied"]:
                break
    return best, count


def _greedy_best(
    problem: DesignProblem,
    mode: str,
    threshold_metric: str,
) -> tuple[int, ...]:
    min_size, max_size = _candidate_sizes(problem, mode)
    target_size = max_size if mode not in {"threshold_first", "hybrid"} else max_size
    selected: tuple[int, ...] = ()
    remaining = set(range(len(problem.slot_ids)))

    while len(selected) < target_size and remaining:
        best_candidate: tuple[int, ...] | None = None
        best_key: tuple[float | int | tuple[int, ...], ...] | None = None
        for slot_index in sorted(remaining):
            candidate = tuple(sorted((*selected, slot_index)))
            key = _objective_key(problem, candidate, mode, threshold_metric)
            if best_key is None or key < best_key:
                best_candidate = candidate
                best_key = key
        if best_candidate is None:
            break
        selected = best_candidate
        remaining.difference_update(selected)
        objective, _ = evaluate_selection(problem, selected)
        if mode == "threshold_first" and objective["threshold_satisfied"]:
            break

    if len(selected) < min_size:
        for slot_index in sorted(remaining):
            selected = tuple(sorted((*selected, slot_index)))
            if len(selected) >= min_size:
                break
    return selected


def _bounded_for_backend(problem: DesignProblem, config: SolverConfig, mode: str) -> str | None:
    size = estimate_model_size(problem, mode)
    if size["slots"] > config.design_max_backend_slots:
        return "slot_bound_exceeded"
    if size["time_samples"] > config.design_max_backend_time_samples:
        return "time_sample_bound_exceeded"
    if size["binary_variables_estimate"] > config.design_max_backend_variables:
        return "variable_bound_exceeded"
    if size["constraints_estimate"] > config.design_max_backend_constraints:
        return "constraint_bound_exceeded"
    return None


def _try_pulp_backend(
    problem: DesignProblem,
    config: SolverConfig,
    mode: str,
    threshold_metric: str,
) -> tuple[tuple[int, ...] | None, str | None]:
    if config.design_backend == "fallback":
        return None, "backend_disabled"
    if mode == "hybrid":
        return None, "pulp_backend_not_implemented_for_hybrid"
    bound_reason = _bounded_for_backend(problem, config, mode)
    if bound_reason:
        return None, bound_reason

    try:
        import pulp  # type: ignore[import-not-found]
    except ImportError:
        return None, "pulp_not_available"

    time_count, slot_count, target_count = problem.matrix.shape
    fixed_count = (
        problem.fixed_satellite_count
        if mode in {"mmrt", "mart"} and problem.fixed_satellite_count is not None
        else None
    )
    max_selected = min(problem.max_selected_slots, slot_count)
    model = pulp.LpProblem(f"rogers_{mode}", pulp.LpMinimize)
    x = [pulp.LpVariable(f"x_{j}", cat="Binary") for j in range(slot_count)]
    y = [
        [pulp.LpVariable(f"y_{t}_{p}", cat="Binary") for p in range(target_count)]
        for t in range(time_count)
    ]

    visible_by_tp: dict[tuple[int, int], list[int]] = {
        (t, p): [] for t in range(time_count) for p in range(target_count)
    }
    for t, j, p in problem.matrix.visible:
        visible_by_tp[(t, p)].append(j)
    big_j = max(1, slot_count)
    for t in range(time_count):
        for p in range(target_count):
            visible_sum = pulp.lpSum(x[j] for j in visible_by_tp[(t, p)])
            model += y[t][p] <= visible_sum
            model += y[t][p] >= visible_sum / big_j

    if fixed_count is not None:
        model += pulp.lpSum(x) == fixed_count
    else:
        model += pulp.lpSum(x) <= max_selected

    if mode in {"mmrt", "threshold_first"} or threshold_metric == "mmrt":
        w = [
            [
                pulp.LpVariable(f"w_{t}_{p}", lowBound=0, upBound=time_count, cat="Integer")
                for p in range(target_count)
            ]
            for t in range(time_count)
        ]
        for p in range(target_count):
            model += w[0][p] == 1 - y[0][p]
            for t in range(time_count):
                model += w[t][p] <= time_count * (1 - y[t][p])
                if t > 0:
                    model += w[t][p] - w[t - 1][p] <= 1
                    model += w[t][p] - w[t - 1][p] >= 1 - (time_count * y[t][p])
    else:
        w = []

    if mode == "mmrt":
        z = pulp.LpVariable("z", lowBound=0, upBound=time_count, cat="Integer")
        for t in range(time_count):
            for p in range(target_count):
                model += w[t][p] <= z
        model += (1000 * z) + pulp.lpSum(w[t][p] for t in range(time_count) for p in range(target_count))
    elif mode == "threshold_first" and threshold_metric == "mmrt":
        for p, threshold_hours in enumerate(problem.expected_revisit_hours):
            threshold_samples = max(1, math.ceil((threshold_hours * 3600.0) / problem.sample_step_sec))
            for t in range(time_count):
                model += w[t][p] <= threshold_samples
        model += pulp.lpSum(x)
    else:
        ell = [
            [pulp.LpVariable(f"ell_{t}_{p}", cat="Binary") for p in range(target_count)]
            for t in range(time_count)
        ]
        alpha = [
            pulp.LpVariable(f"alpha_{p}", lowBound=0, upBound=time_count, cat="Continuous")
            for p in range(target_count)
        ]
        s = [
            [
                pulp.LpVariable(f"s_{t}_{p}", lowBound=0, upBound=time_count, cat="Continuous")
                for p in range(target_count)
            ]
            for t in range(time_count)
        ]
        for p in range(target_count):
            model += ell[0][p] == 1 - y[0][p]
            for t in range(time_count):
                model += ell[t][p] <= 1 - y[t][p]
                model += s[t][p] <= time_count * ell[t][p]
                model += s[t][p] <= alpha[p]
                model += s[t][p] >= alpha[p] - (time_count * (1 - ell[t][p]))
                if t > 0:
                    model += ell[t][p] >= y[t - 1][p] - (time_count * y[t][p])
                    model += ell[t][p] <= y[t - 1][p] + y[t][p]
            model += pulp.lpSum(s[t][p] for t in range(time_count)) >= (
                time_count - pulp.lpSum(y[t][p] for t in range(time_count))
            )
            if mode == "threshold_first":
                threshold_samples = max(
                    1,
                    math.ceil(
                        (problem.expected_revisit_hours[p] * 3600.0)
                        / problem.sample_step_sec
                    ),
                )
                model += alpha[p] <= threshold_samples
        if mode == "threshold_first":
            model += pulp.lpSum(x)
        else:
            model += pulp.lpSum(alpha)

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=config.design_time_limit_sec)
    status = model.solve(solver)
    status_name = pulp.LpStatus.get(status, str(status))
    if status_name not in {"Optimal", "Feasible"}:
        return None, f"pulp_status_{status_name}"
    selected = tuple(j for j, variable in enumerate(x) if (variable.value() or 0.0) >= 0.5)
    return selected, None


def select_design_slots(
    problem: DesignProblem, config: SolverConfig, mode: str | None = None
) -> DesignResult:
    selected_mode = mode or config.design_mode
    size = estimate_model_size(problem, selected_mode)
    selected, fallback_reason = _try_pulp_backend(
        problem, config, selected_mode, config.design_threshold_metric
    )
    backend = "pulp"

    if selected is None:
        backend = "fallback"
        exact, combination_count = _enumerate_best(
            problem,
            selected_mode,
            config.design_threshold_metric,
            config.fallback_exhaustive_max_combinations,
        )
        if exact is None:
            selected = _greedy_best(problem, selected_mode, config.design_threshold_metric)
            fallback_reason = (
                f"{fallback_reason or 'backend_unavailable'};"
                f"exhaustive_combinations_{combination_count}_exceeded"
            )
        else:
            selected = exact
            fallback_reason = (
                f"{fallback_reason or 'backend_unavailable'};exhaustive_fallback"
            )

    objective, target_stats = evaluate_selection(problem, selected)
    notes = (
        "MART fallback minimizes sum of per-target uncovered-run means, matching the "
        "Rogers ART proxy without carrying the full fractional MILP into large cases.",
    )
    return DesignResult(
        mode=selected_mode,
        backend=backend,
        fallback_reason=fallback_reason,
        selected_slot_indices=tuple(selected),
        selected_slot_ids=tuple(problem.slot_ids[index] for index in selected),
        objective=objective,
        target_stats=target_stats,
        model_size=size,
        notes=notes if selected_mode == "mart" else (),
    )

