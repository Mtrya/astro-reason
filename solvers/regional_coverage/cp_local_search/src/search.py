"""Restart/multi-start orchestration for regional coverage local search."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Any

from .candidates import Candidate
from .case_io import RegionalCoverageCase
from .coverage import CoverageIndex
from .cp_repair import CPRepairConfig
from .greedy import GreedyConfig, GreedyResult, greedy_insertion
from .local_search import (
    LocalSearchConfig,
    LocalSearchResult,
    objective_key,
    local_search,
)


@dataclass(frozen=True, slots=True)
class SearchConfig:
    restart_count: int = 1
    run_seeds: tuple[int, ...] = (0,)
    wall_time_limit_s: float | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "SearchConfig":
        payload = payload or {}
        seeds = _seed_tuple(payload.get("search_run_seeds"))
        restart_count = _positive_int(
            payload.get("search_restart_count", len(seeds) if seeds else 1),
            "search_restart_count",
        )
        if not seeds:
            base_seed = int(payload.get("search_seed", 0))
            seeds = tuple(base_seed + idx for idx in range(restart_count))
        elif len(seeds) < restart_count:
            start = seeds[-1] + 1
            seeds = seeds + tuple(start + idx for idx in range(restart_count - len(seeds)))
        elif len(seeds) > restart_count:
            seeds = seeds[:restart_count]
        return cls(
            restart_count=restart_count,
            run_seeds=seeds,
            wall_time_limit_s=_optional_positive_float(payload.get("search_wall_time_limit_s")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "restart_count": self.restart_count,
            "run_seeds": list(self.run_seeds),
            "wall_time_limit_s": self.wall_time_limit_s,
        }


@dataclass(slots=True)
class SearchRunSummary:
    run_index: int
    seed: int
    objective: dict[str, Any]
    selected_candidate_ids: list[str]
    greedy_summary: dict[str, Any]
    local_search_summary: dict[str, Any]
    elapsed_s: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_index": self.run_index,
            "seed": self.seed,
            "objective": dict(self.objective),
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "greedy_summary": dict(self.greedy_summary),
            "local_search_summary": dict(self.local_search_summary),
            "elapsed_s": self.elapsed_s,
        }


@dataclass(slots=True)
class SearchSummary:
    config: dict[str, Any]
    stop_reason: str = "not_started"
    configured_run_count: int = 0
    completed_run_count: int = 0
    best_run_index: int | None = None
    best_seed: int | None = None
    best_objective: dict[str, Any] = field(default_factory=dict)
    run_summaries: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "config": dict(self.config),
            "stop_reason": self.stop_reason,
            "configured_run_count": self.configured_run_count,
            "completed_run_count": self.completed_run_count,
            "best_run_index": self.best_run_index,
            "best_seed": self.best_seed,
            "best_objective": dict(self.best_objective),
            "run_summaries": list(self.run_summaries),
            "best_run_tie_break_order": [
                "valid solution",
                "higher unique coverage weight",
                "lower energy estimate",
                "lower slew burden",
                "fewer actions",
                "lower run index",
                "lower seed",
            ],
        }


@dataclass(slots=True)
class SearchResult:
    greedy_result: GreedyResult
    local_search_result: LocalSearchResult
    summary: SearchSummary

    def selected_in_solution_order(self) -> list[Candidate]:
        return self.local_search_result.selected_in_solution_order()


def run_search(
    case: RegionalCoverageCase,
    candidates: list[Candidate],
    *,
    coverage_index: CoverageIndex,
    search_config: SearchConfig,
    greedy_config: GreedyConfig,
    local_search_config: LocalSearchConfig,
    cp_config: CPRepairConfig,
) -> SearchResult:
    summary = SearchSummary(
        config=search_config.as_dict(),
        configured_run_count=search_config.restart_count,
    )
    started = perf_counter()
    best: tuple[tuple[Any, ...], int, int, GreedyResult, LocalSearchResult] | None = None

    for run_index, seed in enumerate(search_config.run_seeds):
        if search_config.wall_time_limit_s is not None and perf_counter() - started >= search_config.wall_time_limit_s:
            summary.stop_reason = "time_cap_reached"
            break
        run_start = perf_counter()
        run_greedy_config = replace(greedy_config, random_seed=seed)
        run_local_search_config = replace(local_search_config, random_seed=seed)
        greedy_result = greedy_insertion(
            case,
            candidates,
            coverage_index=coverage_index,
            config=run_greedy_config,
        )
        local_result = local_search(
            case,
            candidates,
            coverage_index=coverage_index,
            greedy_result=greedy_result,
            greedy_config=run_greedy_config,
            config=run_local_search_config,
            cp_config=cp_config,
        )
        final_objective = local_result.summary.final_objective
        if final_objective is None:
            raise RuntimeError("local search did not produce a final objective")
        key = objective_key(final_objective)
        run_summary = SearchRunSummary(
            run_index=run_index,
            seed=seed,
            objective=final_objective.as_dict(),
            selected_candidate_ids=[
                candidate.candidate_id
                for candidate in local_result.selected_in_solution_order()
            ],
            greedy_summary=greedy_result.summary.as_dict(),
            local_search_summary=local_result.summary.as_dict(),
            elapsed_s=perf_counter() - run_start,
        )
        summary.run_summaries.append(run_summary.as_dict())
        summary.completed_run_count += 1
        if best is None or _best_run_key(key, run_index, seed) > _best_run_key(best[0], best[1], best[2]):
            best = (key, run_index, seed, greedy_result, local_result)

    if best is None:
        raise RuntimeError("search did not complete any runs")
    _, best_run_index, best_seed, best_greedy, best_local = best
    summary.best_run_index = best_run_index
    summary.best_seed = best_seed
    summary.best_objective = (
        {}
        if best_local.summary.final_objective is None
        else best_local.summary.final_objective.as_dict()
    )
    if summary.stop_reason == "not_started":
        summary.stop_reason = "completed"
    return SearchResult(
        greedy_result=best_greedy,
        local_search_result=best_local,
        summary=summary,
    )


def _best_run_key(objective: tuple[Any, ...], run_index: int, seed: int) -> tuple[Any, ...]:
    return (*objective, -run_index, -seed)


def _seed_tuple(value: Any) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("search_run_seeds must be a sequence of integers")
    return tuple(int(item) for item in value)


def _positive_int(value: Any, field: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _optional_positive_float(value: Any) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if parsed <= 0.0:
        raise ValueError("optional float limits must be positive when set")
    return parsed
