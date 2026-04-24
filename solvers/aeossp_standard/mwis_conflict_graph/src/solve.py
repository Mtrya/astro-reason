"""Solver entrypoint: generate candidates, solve MWIS graph, and emit actions."""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from .candidates import CandidateConfig, generate_candidates
from .case_io import load_case, load_solver_config
from .graph import build_conflict_graph, connected_components
from .mwis import MwisConfig, select_weighted_independent_set
from .solution_io import write_json, write_solution
from .validation import RepairConfig, repair_candidates


@dataclass(frozen=True, slots=True)
class BudgetConfig:
    total_time_budget_s: float | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "BudgetConfig":
        payload = payload or {}
        raw_budget = payload.get("total_time_budget_s")
        if raw_budget in {None, ""}:
            return cls()
        total_time_budget_s = float(raw_budget)
        if total_time_budget_s < 0.0:
            raise ValueError("total_time_budget_s must be null or non-negative")
        return cls(total_time_budget_s=total_time_budget_s)

    def as_status_dict(self) -> dict[str, Any]:
        return asdict(self)


def _timing_with_accounting(
    stage_seconds: dict[str, float],
    total_seconds: float,
    aliases: dict[str, float] | None = None,
) -> dict[str, float]:
    accounted_total = sum(stage_seconds.values())
    return {
        **stage_seconds,
        **(aliases or {}),
        "accounted_total": accounted_total,
        "unaccounted_overhead": total_seconds - accounted_total,
        "total": total_seconds,
    }


def _remaining_budget_s(budget_config: BudgetConfig, total_start: float) -> float | None:
    if budget_config.total_time_budget_s is None:
        return None
    elapsed_s = time.perf_counter() - total_start
    return max(0.0, budget_config.total_time_budget_s - elapsed_s)


def _budget_status(
    *,
    budget_config: BudgetConfig,
    timing_seconds: dict[str, float],
    stage_order: tuple[str, ...],
    search_stage_budget_s: float | None,
    refinement_only_budget_s: float | None,
    refinement_only_budget_hit: bool,
) -> dict[str, Any]:
    configured_budget_s = budget_config.total_time_budget_s
    elapsed_total_s = timing_seconds["total"]
    budget_hit = (
        configured_budget_s is not None
        and elapsed_total_s >= configured_budget_s
    )
    stage_observed = None
    if configured_budget_s is not None:
        cumulative_s = 0.0
        for stage in stage_order:
            cumulative_s += timing_seconds.get(stage, 0.0)
            if cumulative_s >= configured_budget_s:
                stage_observed = stage
                break
    return {
        "configured": budget_config.as_status_dict(),
        "elapsed_total_s": elapsed_total_s,
        "remaining_time_s": (
            None if configured_budget_s is None else max(0.0, configured_budget_s - elapsed_total_s)
        ),
        "budget_hit": budget_hit,
        "stage_observed": stage_observed,
        "output_status": "best_effort" if budget_hit else "complete",
        "search_stage_budget_s": search_stage_budget_s,
        "search_stage_budget_hit": refinement_only_budget_hit,
        "refinement_only_time_limit_s": refinement_only_budget_s,
        "refinement_only_time_limit_hit": (
            refinement_only_budget_s is not None and refinement_only_budget_hit
        ),
        "candidate_generation_interruptible": False,
        "repair_runs_after_budget": True,
        "notes": [
            "total_time_budget_s is end-to-end accounting",
            "time_limit_s remains a refinement-only cap, not a total runtime budget",
            "candidate generation is not interruptible in this phase",
            "repair still runs to produce a locally validated solution",
        ],
    }


def _execution_model() -> dict[str, dict[str, str | bool]]:
    return {
        "case_load": {
            "model": "single_threaded_python",
            "bounded_by_search_budget": False,
            "notes": "loads YAML case files into solver-local data classes",
        },
        "candidate_generation": {
            "model": "single_threaded_python",
            "bounded_by_search_budget": False,
            "parallelism_scope": "none",
            "notes": "serial sweep over satellites, tasks, and grid-aligned start offsets",
        },
        "graph_build": {
            "model": "single_threaded_python",
            "bounded_by_search_budget": False,
            "notes": "builds duplicate-task, overlap, and transition conflict edges in Python",
        },
        "search": {
            "model": "single_threaded_python",
            "bounded_by_search_budget": True,
            "budget_field": "time_limit_s",
            "notes": "exact small-component search plus bounded large-component refinement",
        },
        "validation": {
            "model": "single_threaded_python",
            "bounded_by_search_budget": False,
            "notes": "solver-local validity checks are run inside bounded repair",
        },
        "repair": {
            "model": "single_threaded_python",
            "bounded_by_search_budget": False,
            "notes": "bounded removal repair after MWIS selection",
        },
        "solution_write": {
            "model": "single_threaded_python",
            "bounded_by_search_budget": False,
            "notes": "writes solution and status JSON artifacts",
        },
    }


def _build_status(
    *,
    case_dir: Path,
    config_dir: Path | None,
    solution_path: Path,
    case,
    candidate_config: CandidateConfig,
    candidate_summary,
    graph,
    mwis_config: MwisConfig,
    mwis_stats,
    repair_config: RepairConfig,
    repair_result,
    timing_seconds: dict[str, float],
    budget_status: dict[str, Any],
) -> dict:
    return {
        "status": "phase_5_reproduction_solution_generated",
        "phase": 5,
        "case_dir": str(case_dir),
        "config_dir": str(config_dir) if config_dir is not None else None,
        "solution": str(solution_path),
        "case_id": case.mission.case_id,
        "satellite_count": len(case.satellites),
        "task_count": len(case.tasks),
        "candidate_config": candidate_config.as_status_dict(),
        "mwis_config": mwis_config.as_dict(),
        "execution_model": _execution_model(),
        **candidate_summary.as_debug_dict(case),
        "graph": graph.stats.as_dict(),
        "solver": mwis_stats.as_dict(),
        "repair_config": repair_config.as_status_dict(),
        "local_validation": repair_result.as_status_dict(),
        "timing_seconds": timing_seconds,
        "budget": budget_status,
        "reproduction_summary": {
            "best_local_valid": repair_result.final_report.valid,
            "candidate_count": candidate_summary.candidate_count,
            "selected_action_count_before_repair": mwis_stats.selected_candidate_count,
            "selected_action_count_after_repair": len(repair_result.candidates),
            "repair_iteration_count": len(repair_result.removals),
            "selection_policy": mwis_stats.selection_policy,
            "incumbent_source": mwis_stats.incumbent_source,
            "local_improvement_count": mwis_stats.local_improvement_count,
            "successful_two_swap_count": mwis_stats.successful_two_swap_count,
            "recombination_attempt_count": mwis_stats.recombination_attempt_count,
            "recombination_win_count": mwis_stats.recombination_win_count,
            "search_stop_reason": mwis_stats.search_stop_reason,
            "time_limit_hit": mwis_stats.time_limit_hit,
            "runtime_seconds": timing_seconds["total"],
        },
        "tuning_summary": {
            "best_local_valid": repair_result.final_report.valid,
            "candidate_count": candidate_summary.candidate_count,
            "selected_action_count_before_repair": mwis_stats.selected_candidate_count,
            "selected_action_count_after_repair": len(repair_result.candidates),
            "repair_iteration_count": len(repair_result.removals),
            "selection_policy": mwis_stats.selection_policy,
            "runtime_seconds": timing_seconds["total"],
        },
        "paper_fidelity": {
            "reproduced_behavior": [
                "sparse infeasibility graph over candidate observations",
                "exact solving on tiny components",
                "bounded local improvement with insertions and 2-swaps",
                "deterministic recombination over a bounded population",
                "optional incumbent refinement time budget",
            ],
            "approximated_behavior": [
                "no external ReduMIS binary or kernelization rules",
                "weighted benchmark objective instead of pure collect count",
                "solver-local battery validation and repair remains outside graph edges",
            ],
        },
    }


def _graph_debug_summary(graph) -> dict:
    components = connected_components(graph.adjacency)
    largest_components = [
        {
            "size": len(component),
            "candidate_ids": component[:10],
        }
        for component in sorted(components, key=lambda item: (-len(item), item[0]))[:10]
    ]
    top_conflict_degrees = [
        {"candidate_id": candidate_id, "degree": len(neighbors)}
        for candidate_id, neighbors in sorted(
            graph.adjacency.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )[:20]
    ]
    return {
        "graph": graph.stats.as_dict(),
        "edge_counts_by_reason": {
            reason: len(edges) for reason, edges in sorted(graph.reason_edges.items())
        },
        "largest_components": largest_components,
        "top_conflict_degrees": top_conflict_degrees,
    }


def _write_debug_artifacts(
    *,
    solution_dir: Path,
    case,
    candidate_config: CandidateConfig,
    candidate_summary,
    graph,
    mwis_config: MwisConfig,
    mwis_stats,
    repair_config: RepairConfig,
    repair_result,
    timing_seconds: dict[str, float],
    candidates,
    selected_candidates,
) -> None:
    write_json(
        solution_dir / "debug" / "candidate_summary.json",
        {
            "case_id": case.mission.case_id,
            "candidate_config": candidate_config.as_status_dict(),
            "summary": candidate_summary.as_debug_dict(case),
        },
    )
    write_json(
        solution_dir / "debug" / "graph_summary.json",
        {
            "case_id": case.mission.case_id,
            **_graph_debug_summary(graph),
        },
    )
    write_json(
        solution_dir / "debug" / "solver_summary.json",
        {
            "case_id": case.mission.case_id,
            "candidate_config": candidate_config.as_status_dict(),
            "mwis_config": mwis_config.as_dict(),
            "repair_config": repair_config.as_status_dict(),
            "solver": mwis_stats.as_dict(),
            "local_validation": repair_result.as_status_dict(),
            "timing_seconds": timing_seconds,
        },
    )
    write_json(
        solution_dir / "debug" / "component_search.json",
        {
            "case_id": case.mission.case_id,
            "component_search": mwis_stats.component_search_debug(),
        },
    )
    write_json(
        solution_dir / "debug" / "repair_log.json",
        repair_result.as_debug_dict(),
    )
    write_json(
        solution_dir / "debug" / "candidates.json",
        [candidate.as_dict() for candidate in candidates],
    )
    write_json(
        solution_dir / "debug" / "selected_candidates.json",
        [candidate.as_dict() for candidate in selected_candidates],
    )
    write_json(
        solution_dir / "debug" / "repaired_candidates.json",
        [candidate.as_dict() for candidate in repair_result.candidates],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate AEOSSP MWIS candidates and write a locally validated solution."
    )
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--config-dir", default="")
    parser.add_argument("--solution-dir", required=True)
    args = parser.parse_args(argv)

    case_dir = Path(args.case_dir).resolve()
    config_dir = Path(args.config_dir).resolve() if args.config_dir else None
    solution_dir = Path(args.solution_dir).resolve()

    try:
        total_start = time.perf_counter()
        config_start = time.perf_counter()
        config_payload = load_solver_config(config_dir)
        candidate_config = CandidateConfig.from_mapping(config_payload)
        mwis_config = MwisConfig.from_mapping(config_payload)
        repair_config = RepairConfig.from_mapping(config_payload)
        budget_config = BudgetConfig.from_mapping(config_payload)
        config_end = time.perf_counter()
        case_load_start = time.perf_counter()
        case = load_case(case_dir)
        case_load_end = time.perf_counter()
        candidate_start = time.perf_counter()
        candidates, candidate_summary = generate_candidates(case, candidate_config)
        candidate_end = time.perf_counter()
        graph_start = time.perf_counter()
        graph = build_conflict_graph(case, candidates)
        graph_end = time.perf_counter()
        refinement_only_budget_s = mwis_config.time_limit_s
        remaining_search_budget_s = _remaining_budget_s(budget_config, total_start)
        effective_selection_budget_s = mwis_config.time_limit_s
        if remaining_search_budget_s is not None:
            if effective_selection_budget_s is None:
                effective_selection_budget_s = remaining_search_budget_s
            else:
                effective_selection_budget_s = min(
                    effective_selection_budget_s,
                    remaining_search_budget_s,
                )
            mwis_config = replace(mwis_config, time_limit_s=effective_selection_budget_s)
        selection_start = time.perf_counter()
        selected_candidates, mwis_stats = select_weighted_independent_set(
            candidates,
            graph,
            mwis_config,
        )
        selection_end = time.perf_counter()
        if not mwis_stats.independent_set_valid:
            raise RuntimeError("selected candidates do not form an independent set")
        conflict_degrees = {
            candidate_id: len(neighbors)
            for candidate_id, neighbors in graph.adjacency.items()
        }
        repair_start = time.perf_counter()
        repair_result = repair_candidates(
            case,
            selected_candidates,
            config=repair_config,
            conflict_degrees=conflict_degrees,
        )
        repair_end = time.perf_counter()
        solution_write_start = time.perf_counter()
        solution_path = write_solution(solution_dir, repair_result.candidates)
        solution_write_end = time.perf_counter()
        total_end = solution_write_end
        timing_seconds = _timing_with_accounting({
            "config_load": config_end - config_start,
            "case_load": case_load_end - case_load_start,
            "candidate_generation": candidate_end - candidate_start,
            "graph_build": graph_end - graph_start,
            "selection": selection_end - selection_start,
            "repair": repair_end - repair_start,
            "solution_write": solution_write_end - solution_write_start,
        }, total_end - total_start, aliases={"search": selection_end - selection_start})
        budget_status = _budget_status(
            budget_config=budget_config,
            timing_seconds=timing_seconds,
            stage_order=(
                "config_load",
                "case_load",
                "candidate_generation",
                "graph_build",
                "selection",
                "repair",
                "solution_write",
            ),
            search_stage_budget_s=effective_selection_budget_s,
            refinement_only_budget_s=refinement_only_budget_s,
            refinement_only_budget_hit=mwis_stats.time_limit_hit,
        )
        status = _build_status(
            case_dir=case_dir,
            config_dir=config_dir,
            solution_path=solution_path,
            case=case,
            candidate_config=candidate_config,
            candidate_summary=candidate_summary,
            graph=graph,
            mwis_config=mwis_config,
            mwis_stats=mwis_stats,
            repair_config=repair_config,
            repair_result=repair_result,
            timing_seconds=timing_seconds,
            budget_status=budget_status,
        )
        write_json(solution_dir / "status.json", status)
        if candidate_config.debug:
            _write_debug_artifacts(
                solution_dir=solution_dir,
                case=case,
                candidate_config=candidate_config,
                candidate_summary=candidate_summary,
                graph=graph,
                mwis_config=mwis_config,
                mwis_stats=mwis_stats,
                repair_config=repair_config,
                repair_result=repair_result,
                timing_seconds=timing_seconds,
                candidates=candidates,
                selected_candidates=selected_candidates,
            )
    except Exception as exc:
        traceback_text = traceback.format_exc()
        solution_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            solution_dir / "status.json",
            {
                "status": "error",
                "phase": 5,
                "case_dir": str(case_dir),
                "config_dir": str(config_dir) if config_dir is not None else None,
                "error": str(exc),
                "traceback": traceback_text,
            },
        )
        print(traceback_text, file=sys.stderr, end="")
        return 2

    print(
        f"phase_5_reproduction_solution_generated: {case.mission.case_id} "
        f"candidates={candidate_summary.candidate_count} "
        f"selected={mwis_stats.selected_candidate_count} "
        f"after_repair={len(repair_result.candidates)} "
        f"local_valid={repair_result.final_report.valid} "
        f"policy={mwis_stats.selection_policy} "
        f"source={mwis_stats.incumbent_source} -> {solution_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
