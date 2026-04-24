"""Solver entrypoint: generate candidates, build schedule via greedy insertion,
run solver-local repair, and emit a benchmark-compatible solution."""

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
from .components import build_component_index
from .geometry import PropagationContext
from .insertion import InsertionConfig, greedy_insertion
from .local_search import LocalSearchConfig, local_search
from .solution_io import write_json, write_solution
from .transition import TransitionVectorCache
from .validation import RepairConfig, repair_schedule, validate_schedule


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
        "candidate_generation_interruptible": False,
        "repair_runs_after_budget": True,
        "notes": [
            "total_time_budget_s is end-to-end accounting",
            "candidate generation is not interruptible in this phase",
            "repair still runs to produce a locally validated solution",
        ],
    }


def _candidate_generation_execution_model(
    candidate_config: CandidateConfig,
    *,
    satellite_count: int,
) -> dict[str, Any]:
    effective_workers = (
        min(candidate_config.candidate_workers, satellite_count)
        if candidate_config.candidate_workers > 1 and satellite_count > 1
        else 1
    )
    if effective_workers > 1:
        return {
            "model": "process_pool_python",
            "bounded_by_search_budget": False,
            "parallelism_scope": "satellite",
            "configured_workers": candidate_config.candidate_workers,
            "effective_workers": effective_workers,
            "notes": "satellite-level process pool with deterministic parent-side merge",
        }
    return {
        "model": "single_threaded_python",
        "bounded_by_search_budget": False,
        "parallelism_scope": "none",
        "configured_workers": candidate_config.candidate_workers,
        "effective_workers": 1,
        "notes": "serial sweep over satellites, tasks, and grid-aligned start offsets",
    }


def _execution_model(
    candidate_config: CandidateConfig,
    *,
    satellite_count: int,
) -> dict[str, dict[str, Any]]:
    return {
        "case_load": {
            "model": "single_threaded_python",
            "bounded_by_search_budget": False,
            "notes": "loads YAML case files and builds solver-local propagation/cache objects",
        },
        "candidate_generation": _candidate_generation_execution_model(
            candidate_config,
            satellite_count=satellite_count,
        ),
        "insertion": {
            "model": "single_threaded_python",
            "bounded_by_search_budget": False,
            "notes": "deterministic greedy insertion in Python control flow",
        },
        "search": {
            "model": "single_threaded_python",
            "bounded_by_search_budget": True,
            "budget_field": "max_local_search_time_s",
            "notes": "connected-component local search; budget applies only to this stage when configured",
        },
        "validation": {
            "model": "single_threaded_python",
            "bounded_by_search_budget": False,
            "notes": "solver-local validity checks are run inside bounded repair",
        },
        "repair": {
            "model": "single_threaded_python",
            "bounded_by_search_budget": False,
            "notes": "bounded removal repair after local search",
        },
        "solution_write": {
            "model": "single_threaded_python",
            "bounded_by_search_budget": False,
            "notes": "writes solution and status JSON artifacts",
        },
        "graph_build": {
            "model": "not_applicable",
            "bounded_by_search_budget": False,
            "notes": "greedy_lns does not build an MWIS conflict graph",
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
    insertion_result,
    local_search_result,
    repair_result,
    timing_seconds: dict[str, float],
    budget_status: dict[str, Any],
) -> dict:
    return {
        "status": "solution_generated",
        "case_dir": str(case_dir),
        "config_dir": str(config_dir) if config_dir is not None else None,
        "solution": str(solution_path),
        "case_id": case.mission.case_id,
        "satellite_count": len(case.satellites),
        "task_count": len(case.tasks),
        "candidate_config": candidate_config.as_status_dict(),
        "utility_policy": "weight_over_duration",
        "execution_model": _execution_model(
            candidate_config,
            satellite_count=len(case.satellites),
        ),
        **candidate_summary.as_debug_dict(case),
        "insertion": insertion_result.as_dict(),
        "local_search": local_search_result.as_dict(),
        "repair": repair_result.as_status_dict(),
        "timing_seconds": timing_seconds,
        "budget": budget_status,
        "reproduction_notes": {
            "method_reference": "Antuori, Wojtowicz, and Hebrard, CP 2025",
            "components_reproduced": {
                "greedy_initial_construction": True,
                "connected_component_local_search": True,
                "marginal_profit_recomputation": True,
            },
            "components_omitted": {
                "tempo_cp_sat_tsptw_fallback": "omitted — proprietary dependency",
                "download_memory_planning": "omitted — benchmark is observation-only",
            },
            "adaptations": {
                "battery_handling": "solver-local simulation + bounded repair",
                "action_grid_alignment": "benchmark-mandated fixed times",
                "weighted_objective": "maximize task weight (proxy for WCR)",
            },
            "known_limitations": [
                "No CP-SAT exact subproblem fallback (Tempo omitted)",
                "Candidates use fixed grid-aligned times; no continuous sliding within windows",
                "Battery model is solver-local approximation, not benchmark verifier",
                "No download or memory scheduling (benchmark is observation-only)",
            ],
        },
    }


def _write_debug_artifacts(
    *,
    solution_dir: Path,
    case,
    candidate_config: CandidateConfig,
    candidate_summary,
    candidates,
    insertion_result,
    local_search_result,
    repair_result,
    timing_seconds: dict[str, float],
    propagation: PropagationContext,
    vector_cache: TransitionVectorCache,
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
        solution_dir / "debug" / "candidates.json",
        [candidate.as_dict() for candidate in candidates],
    )
    write_json(
        solution_dir / "debug" / "insertion_stats.json",
        {
            "case_id": case.mission.case_id,
            "insertion": insertion_result.as_dict(),
            "selected_candidates": [candidate.as_dict() for candidate in insertion_result.selected],
        },
    )
    write_json(
        solution_dir / "debug" / "local_search_stats.json",
        {
            "case_id": case.mission.case_id,
            "local_search": local_search_result.as_dict(),
            "post_local_search_candidates": [candidate.as_dict() for candidate in local_search_result.candidates],
        },
    )

    # Build component summary from all candidates
    component_index = build_component_index(
        case,
        candidates,
        propagation=propagation,
        vector_cache=vector_cache,
    )
    write_json(
        solution_dir / "debug" / "component_summary.json",
        {
            "case_id": case.mission.case_id,
            "component_index": component_index.as_dict(),
        },
    )

    # Validation summary: pre-repair and post-repair
    pre_repair_validation = validate_schedule(
        case,
        local_search_result.candidates,
        propagation=propagation,
        vector_cache=vector_cache,
    )
    post_repair_validation = repair_result.final_report
    write_json(
        solution_dir / "debug" / "validation_summary.json",
        {
            "case_id": case.mission.case_id,
            "pre_repair": pre_repair_validation.as_dict(),
            "post_repair": post_repair_validation.as_dict(),
        },
    )

    write_json(
        solution_dir / "debug" / "repair_log.json",
        repair_result.as_debug_dict(),
    )
    write_json(
        solution_dir / "debug" / "repaired_candidates.json",
        [candidate.as_dict() for candidate in repair_result.candidates],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate AEOSSP greedy-LNS candidates, build a schedule via greedy insertion, "
        "run solver-local repair, and write a benchmark-compatible solution."
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
        insertion_config = InsertionConfig.from_mapping(config_payload)
        local_search_config = LocalSearchConfig.from_mapping(config_payload)
        repair_config = RepairConfig.from_mapping(config_payload)
        budget_config = BudgetConfig.from_mapping(config_payload)
        config_end = time.perf_counter()
        case_load_start = time.perf_counter()
        case = load_case(case_dir)
        step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
        propagation = PropagationContext(case.satellites, step_s=step_s)
        vector_cache = TransitionVectorCache(case, propagation)
        case_load_end = time.perf_counter()
        candidate_start = time.perf_counter()
        candidates, candidate_summary = generate_candidates(
            case,
            candidate_config,
            propagation=propagation,
        )
        candidate_end = time.perf_counter()
        insertion_start = time.perf_counter()
        insertion_result = greedy_insertion(
            case,
            candidates,
            insertion_config,
            propagation=propagation,
            vector_cache=vector_cache,
        )
        insertion_end = time.perf_counter()
        remaining_search_budget_s = _remaining_budget_s(budget_config, total_start)
        effective_local_search_budget_s = local_search_config.max_local_search_time_s
        if remaining_search_budget_s is not None:
            if effective_local_search_budget_s is None:
                effective_local_search_budget_s = remaining_search_budget_s
            else:
                effective_local_search_budget_s = min(
                    effective_local_search_budget_s,
                    remaining_search_budget_s,
                )
            local_search_config = replace(
                local_search_config,
                max_local_search_time_s=effective_local_search_budget_s,
            )
        local_search_start = time.perf_counter()
        local_search_result = local_search(
            case,
            candidates,
            insertion_result.selected,
            config=local_search_config,
            propagation=propagation,
            vector_cache=vector_cache,
        )
        local_search_end = time.perf_counter()
        repair_start = time.perf_counter()
        repair_result = repair_schedule(
            case,
            local_search_result.candidates,
            config=repair_config,
            propagation=propagation,
            vector_cache=vector_cache,
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
            "insertion": insertion_end - insertion_start,
            "local_search": local_search_end - local_search_start,
            "repair": repair_end - repair_start,
            "solution_write": solution_write_end - solution_write_start,
        }, total_end - total_start, aliases={"search": local_search_end - local_search_start})
        budget_status = _budget_status(
            budget_config=budget_config,
            timing_seconds=timing_seconds,
            stage_order=(
                "config_load",
                "case_load",
                "candidate_generation",
                "insertion",
                "local_search",
                "repair",
                "solution_write",
            ),
            search_stage_budget_s=effective_local_search_budget_s,
        )
        status = _build_status(
            case_dir=case_dir,
            config_dir=config_dir,
            solution_path=solution_path,
            case=case,
            candidate_config=candidate_config,
            candidate_summary=candidate_summary,
            insertion_result=insertion_result,
            local_search_result=local_search_result,
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
                candidates=candidates,
                insertion_result=insertion_result,
                local_search_result=local_search_result,
                repair_result=repair_result,
                timing_seconds=timing_seconds,
                propagation=propagation,
                vector_cache=vector_cache,
            )
    except Exception as exc:
        traceback_text = traceback.format_exc()
        solution_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            solution_dir / "status.json",
            {
                "status": "error",
                "case_dir": str(case_dir),
                "config_dir": str(config_dir) if config_dir is not None else None,
                "error": str(exc),
                "traceback": traceback_text,
            },
        )
        print(traceback_text, file=sys.stderr, end="")
        return 2

    print(
        f"solution_generated: {case.mission.case_id} "
        f"candidates={candidate_summary.candidate_count} "
        f"inserted={insertion_result.stats.candidates_inserted} "
        f"ls_accepted={local_search_result.stats.moves_accepted} "
        f"ls_stop={local_search_result.stats.stop_reason} "
        f"after_repair={len(repair_result.candidates)} "
        f"local_valid={repair_result.final_report.valid} "
        f"repair_removals={len(repair_result.removals)} -> {solution_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
