"""Bounded CP-style exact sequence repair for tiny local neighborhoods.

The project does not currently depend on a public CP backend such as OR-Tools.
This module is therefore an explicitly labeled fallback: exhaustive bounded
subset search for fixed-start TSPTW-style neighborhood subproblems.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from time import perf_counter
from typing import Any, Iterable

from .candidates import Candidate
from .case_io import RegionalCoverageCase
from .coverage import CoverageIndex
from .sequence import create_empty_state, insert_candidate, is_consistent
from .transition import transition_result


@dataclass(frozen=True, slots=True)
class CPRepairConfig:
    enabled: bool = True
    backend: str = "tiny_exact_fallback"
    max_calls: int = 32
    max_candidates: int = 10
    max_subsets: int = 2048
    time_limit_s: float = 0.25
    min_improvement_weight_m2: float = 1.0e-6

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "CPRepairConfig":
        payload = payload or {}
        backend = str(payload.get("cp_backend", "tiny_exact_fallback"))
        if backend != "tiny_exact_fallback":
            raise ValueError(
                "cp_backend must be 'tiny_exact_fallback'; no public CP backend is configured in pyproject.toml"
            )
        return cls(
            enabled=bool(payload.get("cp_enabled", True)),
            backend=backend,
            max_calls=_non_negative_int(payload.get("cp_max_calls", 32), "cp_max_calls"),
            max_candidates=_positive_int(payload.get("cp_max_candidates", 10), "cp_max_candidates"),
            max_subsets=_positive_int(payload.get("cp_max_subsets", 2048), "cp_max_subsets"),
            time_limit_s=_positive_float(payload.get("cp_time_limit_s", 0.25), "cp_time_limit_s"),
            min_improvement_weight_m2=_non_negative_float(
                payload.get("cp_min_improvement_weight_m2", 1.0e-6),
                "cp_min_improvement_weight_m2",
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "backend": self.backend,
            "max_calls": self.max_calls,
            "max_candidates": self.max_candidates,
            "max_subsets": self.max_subsets,
            "time_limit_s": self.time_limit_s,
            "min_improvement_weight_m2": self.min_improvement_weight_m2,
        }


@dataclass(slots=True)
class CPMetrics:
    backend: str = "tiny_exact_fallback"
    calls: int = 0
    feasible_solutions: int = 0
    improving_solutions: int = 0
    skipped_disabled: int = 0
    skipped_call_limit: int = 0
    skipped_size_limit: int = 0
    timeout_stops: int = 0
    subset_limit_stops: int = 0
    model_build_time_s: float = 0.0
    solve_time_s: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        skipped_calls = self.skipped_disabled + self.skipped_call_limit + self.skipped_size_limit
        call_success_rate = 0.0 if self.calls == 0 else self.feasible_solutions / self.calls
        improving_success_rate = 0.0 if self.calls == 0 else self.improving_solutions / self.calls
        return {
            "backend": self.backend,
            "backend_note": "solver-local bounded exact fallback for fixed-start TSPTW-style neighborhoods",
            "calls": self.calls,
            "successful_calls": self.feasible_solutions,
            "call_success_rate": call_success_rate,
            "feasible_solutions": self.feasible_solutions,
            "improving_solutions": self.improving_solutions,
            "improving_success_rate": improving_success_rate,
            "skipped_calls": skipped_calls,
            "skipped_disabled": self.skipped_disabled,
            "skipped_call_limit": self.skipped_call_limit,
            "skipped_size_limit": self.skipped_size_limit,
            "timeout_stops": self.timeout_stops,
            "subset_limit_stops": self.subset_limit_stops,
            "model_build_time_s": self.model_build_time_s,
            "solve_time_s": self.solve_time_s,
        }


@dataclass(frozen=True, slots=True)
class CPRepairResult:
    attempted: bool
    backend: str
    selected_candidate_ids: tuple[str, ...]
    feasible: bool
    improving: bool
    stop_reason: str
    objective_key: tuple[Any, ...] | None
    subsets_evaluated: int
    model_build_time_s: float
    solve_time_s: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "backend": self.backend,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "feasible": self.feasible,
            "improving": self.improving,
            "stop_reason": self.stop_reason,
            "objective_key": list(self.objective_key) if self.objective_key is not None else None,
            "subsets_evaluated": self.subsets_evaluated,
            "model_build_time_s": self.model_build_time_s,
            "solve_time_s": self.solve_time_s,
        }


def exact_repair(
    case: RegionalCoverageCase,
    *,
    kept_candidates: list[Candidate],
    neighborhood_candidates: list[Candidate],
    coverage_index: CoverageIndex,
    before_key: tuple[Any, ...],
    config: CPRepairConfig,
    metrics: CPMetrics,
) -> CPRepairResult:
    if not config.enabled:
        metrics.skipped_disabled += 1
        return _not_attempted(config, "disabled")
    if metrics.calls >= config.max_calls:
        metrics.skipped_call_limit += 1
        return _not_attempted(config, "call_limit")
    if len(neighborhood_candidates) > config.max_candidates:
        metrics.skipped_size_limit += 1
        return _not_attempted(config, "size_limit")

    build_start = perf_counter()
    pool = sorted(
        {candidate.candidate_id: candidate for candidate in neighborhood_candidates}.values(),
        key=_candidate_key,
    )
    kept = sorted(kept_candidates, key=_candidate_key)
    build_elapsed = perf_counter() - build_start
    metrics.model_build_time_s += build_elapsed
    metrics.calls += 1

    solve_start = perf_counter()
    best_subset: tuple[Candidate, ...] = ()
    best_key: tuple[Any, ...] | None = None
    subsets_evaluated = 0
    stop_reason = "exhausted"

    for subset_size in range(len(pool) + 1):
        for subset in combinations(pool, subset_size):
            if perf_counter() - solve_start > config.time_limit_s:
                stop_reason = "time_limit"
                metrics.timeout_stops += 1
                solve_elapsed = perf_counter() - solve_start
                metrics.solve_time_s += solve_elapsed
                return _finish_result(
                    config,
                    metrics,
                    best_subset,
                    best_key,
                    before_key,
                    subsets_evaluated,
                    build_elapsed,
                    solve_elapsed,
                    stop_reason,
                )
            subsets_evaluated += 1
            if subsets_evaluated > config.max_subsets:
                stop_reason = "subset_limit"
                metrics.subset_limit_stops += 1
                solve_elapsed = perf_counter() - solve_start
                metrics.solve_time_s += solve_elapsed
                return _finish_result(
                    config,
                    metrics,
                    best_subset,
                    best_key,
                    before_key,
                    subsets_evaluated,
                    build_elapsed,
                    solve_elapsed,
                    stop_reason,
                )
            schedule = list(kept) + list(subset)
            if not _schedule_valid(case, schedule):
                continue
            key = _objective_key(case, schedule, coverage_index)
            if best_key is None or key > best_key:
                best_key = key
                best_subset = tuple(subset)

    solve_elapsed = perf_counter() - solve_start
    metrics.solve_time_s += solve_elapsed
    return _finish_result(
        config,
        metrics,
        best_subset,
        best_key,
        before_key,
        subsets_evaluated,
        build_elapsed,
        solve_elapsed,
        stop_reason,
    )


def _finish_result(
    config: CPRepairConfig,
    metrics: CPMetrics,
    best_subset: tuple[Candidate, ...],
    best_key: tuple[Any, ...] | None,
    before_key: tuple[Any, ...],
    subsets_evaluated: int,
    build_elapsed: float,
    solve_elapsed: float,
    stop_reason: str,
) -> CPRepairResult:
    feasible = best_key is not None
    improving = feasible and _objective_key_strictly_better(
        best_key,
        before_key,
        min_improvement_weight_m2=config.min_improvement_weight_m2,
    )
    if feasible:
        metrics.feasible_solutions += 1
    if improving:
        metrics.improving_solutions += 1
    return CPRepairResult(
        attempted=True,
        backend=config.backend,
        selected_candidate_ids=tuple(candidate.candidate_id for candidate in best_subset),
        feasible=feasible,
        improving=improving,
        stop_reason=stop_reason if feasible else "infeasible",
        objective_key=best_key,
        subsets_evaluated=subsets_evaluated,
        model_build_time_s=build_elapsed,
        solve_time_s=solve_elapsed,
    )


def _not_attempted(config: CPRepairConfig, reason: str) -> CPRepairResult:
    return CPRepairResult(
        attempted=False,
        backend=config.backend,
        selected_candidate_ids=(),
        feasible=False,
        improving=False,
        stop_reason=reason,
        objective_key=None,
        subsets_evaluated=0,
        model_build_time_s=0.0,
        solve_time_s=0.0,
    )


def _objective_key_strictly_better(
    candidate_key: tuple[Any, ...] | None,
    before_key: tuple[Any, ...],
    *,
    min_improvement_weight_m2: float,
) -> bool:
    if candidate_key is None:
        return False
    if candidate_key[0] != before_key[0]:
        return candidate_key[0] > before_key[0]
    coverage_delta = float(candidate_key[1]) - float(before_key[1])
    if coverage_delta > min_improvement_weight_m2:
        return True
    if abs(coverage_delta) > min_improvement_weight_m2:
        return False
    return candidate_key[2:] > before_key[2:]


def _schedule_valid(case: RegionalCoverageCase, candidates: Iterable[Candidate]) -> bool:
    try:
        state = create_empty_state(case)
        for candidate in sorted(candidates, key=_candidate_key):
            result = insert_candidate(case, state.sequences[candidate.satellite_id], candidate)
            if not result.success:
                return False
        return all(is_consistent(case, sequence)[0] for sequence in state.sequences.values())
    except (KeyError, ValueError):
        return False


def _objective_key(
    case: RegionalCoverageCase,
    candidates: Iterable[Candidate],
    coverage_index: CoverageIndex,
) -> tuple[Any, ...]:
    schedule = list(candidates)
    covered: set[str] = set()
    for candidate in schedule:
        covered.update(candidate.coverage_sample_ids)
    return (
        1,
        coverage_index.total_weight(covered),
        -sum(candidate.estimated_energy_wh for candidate in schedule),
        -_slew_burden_s(case, schedule),
        -len(schedule),
    )


def _slew_burden_s(case: RegionalCoverageCase, candidates: list[Candidate]) -> float:
    by_satellite: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        by_satellite.setdefault(candidate.satellite_id, []).append(candidate)
    burden = 0.0
    for satellite_id, items in by_satellite.items():
        satellite = case.satellites[satellite_id]
        for previous, current in zip(sorted(items, key=_candidate_key), sorted(items, key=_candidate_key)[1:]):
            burden += transition_result(previous, current, satellite=satellite).required_gap_s
    return burden


def _candidate_key(candidate: Candidate) -> tuple[int, int, str]:
    return (candidate.start_offset_s, candidate.end_offset_s, candidate.candidate_id)


def _positive_int(value: Any, field: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _non_negative_int(value: Any, field: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative")
    return parsed


def _positive_float(value: Any, field: str) -> float:
    parsed = float(value)
    if parsed <= 0.0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _non_negative_float(value: Any, field: str) -> float:
    parsed = float(value)
    if parsed < 0.0:
        raise ValueError(f"{field} must be non-negative")
    return parsed
