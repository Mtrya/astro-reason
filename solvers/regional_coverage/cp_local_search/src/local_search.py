"""Bounded local-search neighborhoods with greedy rebuild."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from .candidates import Candidate
from .case_io import RegionalCoverageCase
from .coverage import CoverageIndex
from .cp_repair import CPRepairConfig, CPMetrics, CPRepairResult, exact_repair
from .greedy import GreedyConfig, GreedyResult, _best_feasible_evaluation
from .sequence import (
    SequenceState,
    create_empty_state,
    insert_candidate,
    is_consistent,
)
from .transition import transition_result


NeighborhoodKind = Literal["satellite_time_component", "sample_competition"]


@dataclass(frozen=True, slots=True)
class LocalSearchConfig:
    enabled: bool = True
    max_iterations: int = 2
    component_gap_s: int = 3600
    time_padding_s: int = 1200
    max_neighborhoods_per_iteration: int = 24
    max_neighborhood_candidates: int = 40
    write_move_log: bool = False
    move_debug_limit: int = 1000

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "LocalSearchConfig":
        payload = payload or {}
        return cls(
            enabled=bool(payload.get("local_search_enabled", True)),
            max_iterations=_positive_int(payload.get("local_search_max_iterations", 2), "local_search_max_iterations"),
            component_gap_s=_positive_int(payload.get("local_search_component_gap_s", 3600), "local_search_component_gap_s"),
            time_padding_s=_non_negative_int(payload.get("local_search_time_padding_s", 1200), "local_search_time_padding_s"),
            max_neighborhoods_per_iteration=_positive_int(
                payload.get("local_search_max_neighborhoods_per_iteration", 24),
                "local_search_max_neighborhoods_per_iteration",
            ),
            max_neighborhood_candidates=_positive_int(
                payload.get("local_search_max_neighborhood_candidates", 40),
                "local_search_max_neighborhood_candidates",
            ),
            write_move_log=bool(payload.get("write_local_search_moves", False)),
            move_debug_limit=_non_negative_int(payload.get("local_search_move_debug_limit", 1000), "local_search_move_debug_limit"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "max_iterations": self.max_iterations,
            "component_gap_s": self.component_gap_s,
            "time_padding_s": self.time_padding_s,
            "max_neighborhoods_per_iteration": self.max_neighborhoods_per_iteration,
            "max_neighborhood_candidates": self.max_neighborhood_candidates,
            "write_move_log": self.write_move_log,
            "move_debug_limit": self.move_debug_limit,
        }


@dataclass(frozen=True, slots=True)
class ScheduleObjective:
    valid: bool
    coverage_weight_m2: float
    estimated_energy_wh: float
    slew_burden_s: float
    action_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "coverage_weight_m2": self.coverage_weight_m2,
            "estimated_energy_wh": self.estimated_energy_wh,
            "slew_burden_s": self.slew_burden_s,
            "action_count": self.action_count,
        }


@dataclass(frozen=True, slots=True)
class Neighborhood:
    neighborhood_id: str
    kind: NeighborhoodKind
    satellite_id: str
    start_offset_s: int
    end_offset_s: int
    remove_candidate_ids: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "neighborhood_id": self.neighborhood_id,
            "kind": self.kind,
            "satellite_id": self.satellite_id,
            "start_offset_s": self.start_offset_s,
            "end_offset_s": self.end_offset_s,
            "remove_candidate_ids": list(self.remove_candidate_ids),
            "candidate_ids": list(self.candidate_ids),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class MoveResult:
    neighborhood: Neighborhood
    accepted: bool
    before: ScheduleObjective
    after: ScheduleObjective
    inserted_candidate_ids: tuple[str, ...]
    removed_candidate_ids: tuple[str, ...]
    stop_reason: str
    cp_repair: CPRepairResult | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "neighborhood": self.neighborhood.as_dict(),
            "accepted": self.accepted,
            "before": self.before.as_dict(),
            "after": self.after.as_dict(),
            "inserted_candidate_ids": list(self.inserted_candidate_ids),
            "removed_candidate_ids": list(self.removed_candidate_ids),
            "stop_reason": self.stop_reason,
            "cp_repair": None if self.cp_repair is None else self.cp_repair.as_dict(),
        }


@dataclass(slots=True)
class LocalSearchSummary:
    enabled: bool
    stop_reason: str = "not_started"
    iterations: int = 0
    attempted_moves: int = 0
    accepted_moves: int = 0
    generated_neighborhoods: int = 0
    initial_objective: ScheduleObjective | None = None
    final_objective: ScheduleObjective | None = None
    cp_metrics: dict[str, Any] = field(default_factory=dict)
    incumbent_progression: list[dict[str, Any]] = field(default_factory=list)
    objective_delta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "stop_reason": self.stop_reason,
            "iterations": self.iterations,
            "attempted_moves": self.attempted_moves,
            "accepted_moves": self.accepted_moves,
            "generated_neighborhoods": self.generated_neighborhoods,
            "initial_objective": None if self.initial_objective is None else self.initial_objective.as_dict(),
            "final_objective": None if self.final_objective is None else self.final_objective.as_dict(),
            "objective_delta": dict(self.objective_delta),
            "cp_metrics": dict(self.cp_metrics),
            "incumbent_progression": list(self.incumbent_progression),
        }


@dataclass(slots=True)
class LocalSearchResult:
    state: SequenceState
    selected_candidates: list[Candidate]
    covered_sample_ids: set[str]
    summary: LocalSearchSummary
    moves: list[MoveResult]

    def selected_in_solution_order(self) -> list[Candidate]:
        return _solution_order(self.selected_candidates)


def local_search(
    case: RegionalCoverageCase,
    candidates: list[Candidate],
    *,
    coverage_index: CoverageIndex,
    greedy_result: GreedyResult,
    greedy_config: GreedyConfig,
    config: LocalSearchConfig,
    cp_config: CPRepairConfig | None = None,
) -> LocalSearchResult:
    cp_config = cp_config or CPRepairConfig(enabled=False)
    cp_metrics = CPMetrics(backend=cp_config.backend)
    incumbent = _solution_order(greedy_result.selected_candidates)
    incumbent_state = state_from_candidates(case, incumbent)
    incumbent_coverage = covered_sample_ids(incumbent)
    incumbent_objective = schedule_objective(case, incumbent, coverage_index)
    summary = LocalSearchSummary(
        enabled=config.enabled,
        initial_objective=incumbent_objective,
        final_objective=incumbent_objective,
        cp_metrics=cp_metrics.as_dict(),
    )
    moves: list[MoveResult] = []
    if not config.enabled:
        summary.stop_reason = "disabled"
        summary.objective_delta = _objective_delta(summary.initial_objective, summary.final_objective)
        return LocalSearchResult(incumbent_state, incumbent, incumbent_coverage, summary, moves)
    if not incumbent:
        summary.stop_reason = "empty_incumbent"
        summary.objective_delta = _objective_delta(summary.initial_objective, summary.final_objective)
        return LocalSearchResult(incumbent_state, incumbent, incumbent_coverage, summary, moves)

    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    accepted_this_run = 0
    for iteration in range(config.max_iterations):
        neighborhoods = build_neighborhoods(
            candidates,
            incumbent,
            config=config,
        )
        summary.generated_neighborhoods += len(neighborhoods)
        accepted_in_iteration = False
        for neighborhood in neighborhoods:
            summary.attempted_moves += 1
            move = rebuild_neighborhood(
                case,
                incumbent,
                neighborhood,
                candidate_by_id=candidate_by_id,
                coverage_index=coverage_index,
                greedy_config=greedy_config,
                cp_config=cp_config,
                cp_metrics=cp_metrics,
            )
            if len(moves) < config.move_debug_limit:
                moves.append(move)
            if not move.accepted:
                continue
            removed = set(neighborhood.remove_candidate_ids)
            rebuilt_ids = set(move.inserted_candidate_ids)
            incumbent = _solution_order(
                [
                    candidate
                    for candidate in incumbent
                    if candidate.candidate_id not in removed
                ]
                + [candidate_by_id[cid] for cid in rebuilt_ids]
            )
            incumbent_state = state_from_candidates(case, incumbent)
            incumbent_coverage = covered_sample_ids(incumbent)
            incumbent_objective = move.after
            summary.accepted_moves += 1
            accepted_this_run += 1
            summary.incumbent_progression.append(
                {
                    "iteration": iteration + 1,
                    "move": move.neighborhood.neighborhood_id,
                    "objective": incumbent_objective.as_dict(),
                }
            )
            accepted_in_iteration = True
            break
        summary.cp_metrics = cp_metrics.as_dict()
        summary.iterations = iteration + 1
        if not accepted_in_iteration:
            summary.stop_reason = "local_minimum"
            break
    else:
        summary.stop_reason = "iteration_cap_reached"

    if accepted_this_run == 0 and summary.stop_reason == "not_started":
        summary.stop_reason = "local_minimum"
    summary.final_objective = incumbent_objective
    summary.objective_delta = _objective_delta(summary.initial_objective, summary.final_objective)
    summary.cp_metrics = cp_metrics.as_dict()
    return LocalSearchResult(
        state=incumbent_state,
        selected_candidates=incumbent,
        covered_sample_ids=incumbent_coverage,
        summary=summary,
        moves=moves,
    )


def build_neighborhoods(
    candidates: list[Candidate],
    selected_candidates: list[Candidate],
    *,
    config: LocalSearchConfig,
) -> list[Neighborhood]:
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    neighborhoods = _time_component_neighborhoods(candidates, selected_candidates, config=config)
    neighborhoods.extend(
        _sample_competition_neighborhoods(candidates, selected_candidates, config=config)
    )
    cleaned: list[Neighborhood] = []
    seen: set[str] = set()
    for neighborhood in neighborhoods:
        remove_ids = tuple(cid for cid in neighborhood.remove_candidate_ids if cid in by_id)
        candidate_ids = tuple(cid for cid in neighborhood.candidate_ids if cid in by_id)
        if not remove_ids or not candidate_ids:
            continue
        key = (
            neighborhood.kind,
            neighborhood.satellite_id,
            neighborhood.start_offset_s,
            neighborhood.end_offset_s,
            remove_ids,
            candidate_ids,
        )
        stable = repr(key)
        if stable in seen:
            continue
        seen.add(stable)
        cleaned.append(
            Neighborhood(
                neighborhood_id=f"n{len(cleaned) + 1:04d}_{neighborhood.kind}_{neighborhood.satellite_id}",
                kind=neighborhood.kind,
                satellite_id=neighborhood.satellite_id,
                start_offset_s=neighborhood.start_offset_s,
                end_offset_s=neighborhood.end_offset_s,
                remove_candidate_ids=remove_ids,
                candidate_ids=candidate_ids,
                reason=neighborhood.reason,
            )
        )
        if len(cleaned) >= config.max_neighborhoods_per_iteration:
            break
    return cleaned


def rebuild_neighborhood(
    case: RegionalCoverageCase,
    incumbent: list[Candidate],
    neighborhood: Neighborhood,
    *,
    candidate_by_id: dict[str, Candidate],
    coverage_index: CoverageIndex,
    greedy_config: GreedyConfig,
    cp_config: CPRepairConfig | None = None,
    cp_metrics: CPMetrics | None = None,
) -> MoveResult:
    before = schedule_objective(case, incumbent, coverage_index)
    removed_ids = set(neighborhood.remove_candidate_ids)
    kept = [candidate for candidate in incumbent if candidate.candidate_id not in removed_ids]
    kept_ids = {candidate.candidate_id for candidate in kept}
    state = state_from_candidates(case, kept)
    covered = covered_sample_ids(kept)
    selected_ids = set(kept_ids)
    inserted: list[Candidate] = []
    attempts: list[dict[str, Any]] = []

    pool = [
        candidate_by_id[cid]
        for cid in neighborhood.candidate_ids
        if cid in candidate_by_id and cid not in kept_ids
    ]
    while len(kept) + len(inserted) < case.mission.max_actions_total:
        best = _best_feasible_evaluation(
            case,
            pool,
            selected_ids=selected_ids,
            covered_sample_ids=covered,
            state=state,
            coverage_index=coverage_index,
            policy=greedy_config.policy,
            summary=_NullGreedySummary(greedy_config.policy, case.mission.max_actions_total),
            attempt_debug=attempts,
            attempt_debug_limit=0,
        )
        if best is None:
            break
        result = insert_candidate(case, state.sequences[best.candidate.satellite_id], best.candidate, best.position)
        if not result.success:
            break
        inserted.append(best.candidate)
        selected_ids.add(best.candidate.candidate_id)
        covered.update(best.candidate.coverage_sample_ids)

    rebuilt = _solution_order(kept + inserted)
    after = schedule_objective(case, rebuilt, coverage_index)
    accepted = objective_strictly_better(after, before)
    if accepted:
        return MoveResult(
            neighborhood=neighborhood,
            accepted=True,
            before=before,
            after=after,
            inserted_candidate_ids=tuple(candidate.candidate_id for candidate in inserted),
            removed_candidate_ids=neighborhood.remove_candidate_ids,
            stop_reason="greedy_strict_improvement",
        )

    cp_result = None
    if cp_config is not None and cp_metrics is not None:
        cp_result = exact_repair(
            case,
            kept_candidates=kept,
            neighborhood_candidates=pool,
            coverage_index=coverage_index,
            before_key=objective_key(before),
            config=cp_config,
            metrics=cp_metrics,
        )
        if cp_result.improving:
            cp_selected = [candidate_by_id[cid] for cid in cp_result.selected_candidate_ids]
            cp_after = schedule_objective(case, _solution_order(kept + cp_selected), coverage_index)
            if not objective_strictly_better(cp_after, before):
                return MoveResult(
                    neighborhood=neighborhood,
                    accepted=False,
                    before=before,
                    after=cp_after,
                    inserted_candidate_ids=cp_result.selected_candidate_ids,
                    removed_candidate_ids=neighborhood.remove_candidate_ids,
                    stop_reason="cp_not_improving",
                    cp_repair=cp_result,
                )
            return MoveResult(
                neighborhood=neighborhood,
                accepted=True,
                before=before,
                after=cp_after,
                inserted_candidate_ids=cp_result.selected_candidate_ids,
                removed_candidate_ids=neighborhood.remove_candidate_ids,
                stop_reason="cp_strict_improvement",
                cp_repair=cp_result,
            )

    return MoveResult(
        neighborhood=neighborhood,
        accepted=False,
        before=before,
        after=after,
        inserted_candidate_ids=tuple(candidate.candidate_id for candidate in inserted),
        removed_candidate_ids=neighborhood.remove_candidate_ids,
        stop_reason="not_improving" if cp_result is None else f"cp_{cp_result.stop_reason}",
        cp_repair=cp_result,
    )


def schedule_objective(
    case: RegionalCoverageCase,
    selected_candidates: list[Candidate],
    coverage_index: CoverageIndex,
) -> ScheduleObjective:
    state = state_from_candidates(case, selected_candidates)
    valid = all(is_consistent(case, sequence)[0] for sequence in state.sequences.values())
    coverage = covered_sample_ids(selected_candidates)
    return ScheduleObjective(
        valid=valid,
        coverage_weight_m2=coverage_index.total_weight(coverage),
        estimated_energy_wh=sum(candidate.estimated_energy_wh for candidate in selected_candidates),
        slew_burden_s=_slew_burden_s(case, state),
        action_count=len(selected_candidates),
    )


def objective_key(objective: ScheduleObjective) -> tuple[Any, ...]:
    return (
        1 if objective.valid else 0,
        objective.coverage_weight_m2,
        -objective.estimated_energy_wh,
        -objective.slew_burden_s,
        -objective.action_count,
    )


def objective_strictly_better(
    candidate: ScheduleObjective,
    incumbent: ScheduleObjective,
    *,
    min_coverage_delta_m2: float = 1.0e-6,
) -> bool:
    if candidate.valid != incumbent.valid:
        return candidate.valid and not incumbent.valid
    coverage_delta = candidate.coverage_weight_m2 - incumbent.coverage_weight_m2
    if coverage_delta > min_coverage_delta_m2:
        return True
    if coverage_delta < -min_coverage_delta_m2:
        return False
    return (
        -candidate.estimated_energy_wh,
        -candidate.slew_burden_s,
        -candidate.action_count,
    ) > (
        -incumbent.estimated_energy_wh,
        -incumbent.slew_burden_s,
        -incumbent.action_count,
    )


def _objective_delta(
    initial: ScheduleObjective | None,
    final: ScheduleObjective | None,
) -> dict[str, Any]:
    if initial is None or final is None:
        return {}
    return {
        "coverage_weight_m2": final.coverage_weight_m2 - initial.coverage_weight_m2,
        "estimated_energy_wh": final.estimated_energy_wh - initial.estimated_energy_wh,
        "slew_burden_s": final.slew_burden_s - initial.slew_burden_s,
        "action_count": final.action_count - initial.action_count,
        "valid_changed": final.valid != initial.valid,
    }


def state_from_candidates(case: RegionalCoverageCase, candidates: Iterable[Candidate]) -> SequenceState:
    state = create_empty_state(case)
    for candidate in _solution_order(list(candidates)):
        result = insert_candidate(case, state.sequences[candidate.satellite_id], candidate)
        if not result.success:
            raise ValueError(f"candidate {candidate.candidate_id} cannot be inserted into rebuilt state")
    return state


def covered_sample_ids(candidates: Iterable[Candidate]) -> set[str]:
    covered: set[str] = set()
    for candidate in candidates:
        covered.update(candidate.coverage_sample_ids)
    return covered


def _time_component_neighborhoods(
    candidates: list[Candidate],
    selected_candidates: list[Candidate],
    *,
    config: LocalSearchConfig,
) -> list[Neighborhood]:
    selected_by_satellite: dict[str, list[Candidate]] = {}
    for candidate in selected_candidates:
        selected_by_satellite.setdefault(candidate.satellite_id, []).append(candidate)

    out: list[Neighborhood] = []
    for satellite_id, selected in sorted(selected_by_satellite.items()):
        selected = sorted(selected, key=_candidate_time_key)
        components: list[list[Candidate]] = []
        current: list[Candidate] = []
        for candidate in selected:
            if current and candidate.start_offset_s - current[-1].end_offset_s > config.component_gap_s:
                components.append(current)
                current = []
            current.append(candidate)
        if current:
            components.append(current)
        for component_index, component in enumerate(components, start=1):
            start = max(0, min(candidate.start_offset_s for candidate in component) - config.time_padding_s)
            end = max(candidate.end_offset_s for candidate in component) + config.time_padding_s
            pool = _bounded_pool(
                [
                    candidate
                    for candidate in candidates
                    if candidate.satellite_id == satellite_id
                    and candidate.start_offset_s < end
                    and candidate.end_offset_s > start
                ],
                required_ids={candidate.candidate_id for candidate in component},
                limit=config.max_neighborhood_candidates,
            )
            out.append(
                Neighborhood(
                    neighborhood_id="pending",
                    kind="satellite_time_component",
                    satellite_id=satellite_id,
                    start_offset_s=start,
                    end_offset_s=end,
                    remove_candidate_ids=tuple(candidate.candidate_id for candidate in component),
                    candidate_ids=tuple(candidate.candidate_id for candidate in pool),
                    reason=f"paper temporal component {component_index} for one satellite",
                )
            )
    return out


def _sample_competition_neighborhoods(
    candidates: list[Candidate],
    selected_candidates: list[Candidate],
    *,
    config: LocalSearchConfig,
) -> list[Neighborhood]:
    out: list[Neighborhood] = []
    for selected in sorted(selected_candidates, key=lambda item: (-item.base_coverage_weight_m2, item.candidate_id)):
        if not selected.coverage_sample_ids:
            continue
        competitors = [
            candidate
            for candidate in candidates
            if candidate.satellite_id == selected.satellite_id
            and candidate.candidate_id != selected.candidate_id
            and bool(candidate.coverage_sample_ids & selected.coverage_sample_ids)
        ]
        if not competitors:
            continue
        pool = _bounded_pool(
            competitors + [selected],
            required_ids={selected.candidate_id},
            limit=config.max_neighborhood_candidates,
        )
        out.append(
            Neighborhood(
                neighborhood_id="pending",
                kind="sample_competition",
                satellite_id=selected.satellite_id,
                start_offset_s=min(candidate.start_offset_s for candidate in pool),
                end_offset_s=max(candidate.end_offset_s for candidate in pool),
                remove_candidate_ids=(selected.candidate_id,),
                candidate_ids=tuple(candidate.candidate_id for candidate in pool),
                reason="benchmark unique-coverage competition for selected samples",
            )
        )
    return out


def _bounded_pool(
    candidates: list[Candidate],
    *,
    required_ids: set[str],
    limit: int,
) -> list[Candidate]:
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    required = [by_id[cid] for cid in sorted(required_ids) if cid in by_id]
    ranked = sorted(
        by_id.values(),
        key=lambda item: (
            item.candidate_id not in required_ids,
            -item.base_coverage_weight_m2,
            item.start_offset_s,
            item.candidate_id,
        ),
    )
    out: list[Candidate] = []
    seen: set[str] = set()
    for candidate in required + ranked:
        if candidate.candidate_id in seen:
            continue
        seen.add(candidate.candidate_id)
        out.append(candidate)
        if len(out) >= limit:
            break
    return sorted(out, key=_candidate_time_key)


def _slew_burden_s(case: RegionalCoverageCase, state: SequenceState) -> float:
    burden = 0.0
    for satellite_id, sequence in state.sequences.items():
        satellite = case.satellites[satellite_id]
        for previous, current in zip(sequence.candidates, sequence.candidates[1:]):
            burden += transition_result(previous, current, satellite=satellite).required_gap_s
    return burden


def _solution_order(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(candidates, key=lambda item: (item.start_offset_s, item.satellite_id, item.candidate_id))


def _candidate_time_key(candidate: Candidate) -> tuple[int, int, str]:
    return (candidate.start_offset_s, candidate.end_offset_s, candidate.candidate_id)


class _NullGreedySummary:
    def __init__(self, policy: str, action_cap: int):
        self.policy = policy
        self.action_cap = action_cap
        self.attempted_insertions = 0
        self.feasible_insertions = 0
        self.rejected_insertions = 0
        self.zero_marginal_candidates = 0
        self.reject_reasons: dict[str, int] = {}


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
