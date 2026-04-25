"""Regional-coverage CELF fixed-candidate selection entrypoint."""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from candidates import generate_candidates, load_candidate_config
from case_io import load_case
from celf import (
    coverage_objective,
    load_selection_config,
    run_celf_selection,
    sample_weight_lookup,
)
from coverage import (
    build_candidate_coverage_with_runtime,
    build_coverage_diagnostics,
    build_coverage_sample_index,
    load_coverage_mapping_config,
)
from schedule import feasibility_summary, repair_schedule
from solution_io import (
    write_candidate_debug,
    write_celf_debug,
    write_coverage_diagnostics,
    write_json,
    write_repair_debug,
    write_reproduction_debug,
    write_solution_from_candidates,
)


def _selection_costs(case, candidates, cost_mode: str) -> dict[str, float] | None:
    if cost_mode != "estimated_energy":
        return None
    costs: dict[str, float] = {}
    for candidate in candidates:
        satellite = case.satellites[candidate.satellite_id]
        costs[candidate.candidate_id] = (
            candidate.duration_s * satellite.power.imaging_power_w / 3600.0
        )
    return costs


def _config_dir(value: str) -> Path | None:
    if not value:
        return None
    return Path(value)


def _round_seconds(value: float) -> float:
    return round(value, 6)


def _reproduction_summary(
    *,
    celf_result,
    repair_result,
    repair_objective_summary: dict[str, Any],
) -> dict[str, Any]:
    best_bound = celf_result.best.online_bound
    return {
        "source": {
            "primary_reference": "Leskovec et al. 2007, Sections 3 and 4",
            "issue": "https://github.com/Mtrya/astro-reason/issues/82",
        },
        "paper_faithful_elements": {
            "fixed_ground_set": "candidate strip observations are fixed before selection",
            "reward": "R(A) is unique weighted coverage over fixed coverage-grid samples",
            "unit_cost_greedy": "LazyForward UC maximizes marginal gain",
            "cost_benefit_greedy": "LazyForward CB maximizes marginal gain divided by candidate cost",
            "celf_lazy_updates": "stale marginal gains are recomputed only when a candidate reaches the queue head",
            "cef_comparison": "unit-cost and cost-benefit variants are both run when configured, then the higher-reward result is kept",
            "online_bound": "Leskovec Section 3.2 online bound is computed from marginal gains over the same fixed candidate set",
        },
        "benchmark_adaptations": {
            "node_mapping": "paper sensor/node -> timed regional-coverage strip candidate",
            "scenario_mapping": "paper scenario/covered item -> coverage_grid sample index",
            "budget_mapping": "paper budget B -> max_actions_total or configured selection budget",
            "cost_modes": [
                "action_count",
                "imaging_time",
                "estimated_energy",
                "transition_burden",
            ],
            "candidate_geometry": "solver-local Brahe SGP4/WGS84 strip approximation; official geometry remains benchmark-owned",
            "schedule_repair": "same-satellite overlap, slew, action-cap, battery, and duty checks are deterministic benchmark adaptations after fixed-set CELF selection",
            "official_validation": "experiments/main_solver runs the benchmark verifier through CLI/file contracts",
        },
        "known_fidelity_limits": {
            "online_bound_scope": "the online bound certifies only the fixed benchmark-adapted candidate set used by CELF, not the continuous satellite scheduling problem",
            "geometry_drift_risk": "solver-local coverage mapping may differ from verifier-derived WGS84 strip geometry",
            "repair_breaks_pure_set_selection": "post-selection repair can remove candidates and therefore is reported separately from paper-faithful CELF",
            "battery_duty_are_approximate": "solver-local battery and duty checks are conservative approximations, not a proof of verifier feasibility",
        },
        "selection_audit": {
            "best_policy": celf_result.best_policy,
            "best_objective_value": celf_result.best.objective_value,
            "best_selected_before_repair": celf_result.best.accepted_count,
            "repaired_selected_count": len(repair_result.repaired_candidate_ids),
            "removed_by_repair": len(repair_result.removed_candidate_ids),
            "repaired_objective_value": repair_objective_summary["repaired_objective_value"],
            "repair_objective_loss": repair_objective_summary["repair_objective_loss"],
            "repair_objective_loss_ratio": repair_objective_summary[
                "repair_objective_loss_ratio"
            ],
            "fixed_set_online_upper_bound": (
                best_bound.online_upper_bound if best_bound is not None else None
            ),
            "fixed_set_online_gap_ratio": (
                best_bound.gap_ratio if best_bound is not None else None
            ),
            "unit_cost_lazy_recomputation_ratio": (
                celf_result.unit_cost.as_dict().get("lazy_recomputation_ratio")
                if celf_result.unit_cost
                else None
            ),
            "cost_benefit_lazy_recomputation_ratio": (
                celf_result.cost_benefit.as_dict().get("lazy_recomputation_ratio")
                if celf_result.cost_benefit
                else None
            ),
        },
    }


def _build_status(
    *,
    case,
    config_dir: Path | None,
    solution_path: Path,
    candidate_config,
    candidate_summary,
    coverage_mapping_config,
    coverage_summary,
    coverage_diagnostics,
    coverage_runtime_summary,
    selection_config,
    celf_result,
    repair_result,
    repair_objective_summary,
    timing_seconds: dict[str, float],
) -> dict[str, Any]:
    reproduction_summary = _reproduction_summary(
        celf_result=celf_result,
        repair_result=repair_result,
        repair_objective_summary=repair_objective_summary,
    )
    return {
        "status": "ok",
        "phase": "phase_5_validation_tuning_and_reproduction_fidelity",
        "case_dir": str(case.case_dir),
        "config_dir": str(config_dir) if config_dir is not None else None,
        "solution": str(solution_path),
        "case": {
            "case_id": case.manifest.case_id,
            "benchmark": case.manifest.benchmark,
            "spec_version": case.manifest.spec_version,
            "horizon_start": case.manifest.horizon_start.isoformat(),
            "horizon_end": case.manifest.horizon_end.isoformat(),
            "horizon_seconds": case.manifest.horizon_seconds,
            "time_step_s": case.manifest.time_step_s,
            "coverage_sample_step_s": case.manifest.coverage_sample_step_s,
            "max_actions_total": case.manifest.max_actions_total,
        },
        "parsed_counts": {
            "satellite_count": len(case.satellites),
            "region_count": len(case.regions),
            "sample_count": len(case.coverage_grid.samples),
        },
        "candidate_config": candidate_config.as_status_dict(),
        "coverage_mapping_config": coverage_mapping_config.as_status_dict(),
        "selection_config": selection_config.as_status_dict(),
        "candidate_summary": candidate_summary.as_dict(),
        "coverage_summary": coverage_summary.as_dict(),
        "coverage_diagnostics": coverage_diagnostics,
        "coverage_runtime_summary": coverage_runtime_summary.as_dict(),
        "celf_summary": celf_result.as_dict(),
        "feasibility_summary": feasibility_summary(repair_result),
        "repair_summary": repair_result.as_dict(),
        "repair_objective_summary": repair_objective_summary,
        "reproduction_summary": reproduction_summary,
        "output_policy": {
            "solution_actions": len(repair_result.repaired_candidate_ids),
            "empty_solution_only": len(repair_result.repaired_candidate_ids) == 0,
            "selection_deferred_to_phase": None,
            "sequence_feasibility_deferred_to_phase": None,
            "satellite_repair_enabled": True,
            "experiment_registration_enabled": True,
            "coverage_geometry": "solver-local Brahe SGP4/WGS84 strip approximation",
            "battery_and_duty_checks": "approximate_solver_local",
        },
        "timing_seconds": timing_seconds,
    }


def run(case_dir: Path, config_dir: Path | None, solution_dir: Path) -> int:
    total_start = time.perf_counter()
    solution_dir.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}

    start = time.perf_counter()
    case = load_case(case_dir)
    candidate_config = load_candidate_config(config_dir)
    coverage_mapping_config = load_coverage_mapping_config(config_dir)
    selection_config = load_selection_config(config_dir)
    timings["case_loading"] = _round_seconds(time.perf_counter() - start)

    start = time.perf_counter()
    candidates, candidate_summary = generate_candidates(case, candidate_config)
    timings["candidate_generation"] = _round_seconds(time.perf_counter() - start)

    start = time.perf_counter()
    sample_index = build_coverage_sample_index(case, coverage_mapping_config)
    timings["coverage_index_construction"] = _round_seconds(time.perf_counter() - start)

    start = time.perf_counter()
    (
        coverage_by_candidate,
        coverage_summary,
        coverage_runtime_summary,
    ) = build_candidate_coverage_with_runtime(
        case,
        candidates,
        config=coverage_mapping_config,
        sample_index=sample_index,
    )
    timings["candidate_coverage_mapping"] = _round_seconds(time.perf_counter() - start)

    start = time.perf_counter()
    coverage_diagnostics = build_coverage_diagnostics(
        case,
        candidates,
        coverage_by_candidate,
        limit=candidate_config.debug_candidate_limit,
    )
    timings["coverage_diagnostics"] = _round_seconds(time.perf_counter() - start)
    timings["coverage_mapping"] = _round_seconds(
        timings["coverage_index_construction"]
        + timings["candidate_coverage_mapping"]
        + timings["coverage_diagnostics"]
    )

    start = time.perf_counter()
    sample_weights = sample_weight_lookup(
        tuple(sample.weight_m2 for sample in case.coverage_grid.samples)
    )
    celf_result = run_celf_selection(
        candidates,
        coverage_by_candidate,
        sample_weights,
        max_actions_total=case.manifest.max_actions_total,
        config=selection_config,
        cost_by_candidate=_selection_costs(case, candidates, selection_config.cost_mode),
    )
    timings["celf_selection"] = _round_seconds(time.perf_counter() - start)
    timings["celf_unit_cost_selection"] = celf_result.timing_seconds.get(
        "unit_cost_selection",
        0.0,
    )
    timings["celf_cost_benefit_selection"] = celf_result.timing_seconds.get(
        "cost_benefit_selection",
        0.0,
    )

    start = time.perf_counter()
    candidates_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    repair_result = repair_schedule(
        case,
        candidates_by_id,
        celf_result.best.selected_candidate_ids,
        coverage_by_candidate,
        sample_weights,
    )
    timings["schedule_validation_and_repair"] = _round_seconds(time.perf_counter() - start)
    timings["schedule_repair"] = timings["schedule_validation_and_repair"]
    repaired_objective = coverage_objective(
        repair_result.repaired_candidate_ids,
        coverage_by_candidate,
        sample_weights,
    )
    pre_repair_objective = celf_result.best.objective_value
    repair_loss = max(0.0, pre_repair_objective - repaired_objective)
    repair_objective_summary = {
        "scope": "solver_local_fixed_sample_objective",
        "pre_repair_objective_value": pre_repair_objective,
        "repaired_objective_value": repaired_objective,
        "repair_objective_loss": repair_loss,
        "repair_objective_loss_ratio": (
            repair_loss / pre_repair_objective if pre_repair_objective > 0.0 else None
        ),
        "pre_repair_selected_count": len(celf_result.best.selected_candidate_ids),
        "repaired_selected_count": len(repair_result.repaired_candidate_ids),
        "removed_by_repair": len(repair_result.removed_candidate_ids),
        "notes": [
            "Repair happens after paper-faithful fixed-set CELF selection.",
            "Official verifier score is benchmark-owned and may differ from this solver-local sample objective.",
        ],
    }

    start = time.perf_counter()
    solution_path = write_solution_from_candidates(
        solution_dir, candidates_by_id, repair_result.repaired_candidate_ids
    )
    write_candidate_debug(
        solution_dir,
        candidates,
        coverage_by_candidate,
        limit=candidate_config.debug_candidate_limit,
    )
    selected_candidates = [
        {
            **candidates_by_id[candidate_id].as_dict(),
            "covered_sample_indices": list(coverage_by_candidate.get(candidate_id, ())),
            "covered_sample_count": len(coverage_by_candidate.get(candidate_id, ())),
        }
        for candidate_id in celf_result.best.selected_candidate_ids
    ]
    repaired_candidates = [
        {
            **candidates_by_id[candidate_id].as_dict(),
            "covered_sample_indices": list(coverage_by_candidate.get(candidate_id, ())),
            "covered_sample_count": len(coverage_by_candidate.get(candidate_id, ())),
        }
        for candidate_id in repair_result.repaired_candidate_ids
    ]
    iteration_rows = []
    for result in (celf_result.unit_cost, celf_result.cost_benefit):
        if result is not None:
            iteration_rows.extend(step.as_dict() for step in result.iterations)
    write_celf_debug(
        solution_dir,
        candidate_summary=candidate_summary.as_dict(),
        celf_summary=celf_result.as_dict(),
        iteration_rows=iteration_rows,
        selected_candidates=selected_candidates,
        write_iterations=selection_config.write_iteration_trace,
    )
    write_repair_debug(
        solution_dir,
        feasibility_summary=feasibility_summary(repair_result),
        repair_log=[event.as_dict() for event in repair_result.repair_log],
        repaired_candidates=repaired_candidates,
    )
    write_coverage_diagnostics(solution_dir, coverage_diagnostics)
    write_json(
        solution_dir / "debug" / "coverage_runtime_summary.json",
        coverage_runtime_summary.as_dict(),
    )
    write_json(
        solution_dir / "debug" / "repair_objective_summary.json",
        repair_objective_summary,
    )
    reproduction_summary = _reproduction_summary(
        celf_result=celf_result,
        repair_result=repair_result,
        repair_objective_summary=repair_objective_summary,
    )
    write_reproduction_debug(solution_dir, reproduction_summary)
    timings["output"] = _round_seconds(time.perf_counter() - start)
    timings["total"] = _round_seconds(time.perf_counter() - total_start)

    status = _build_status(
        case=case,
        config_dir=config_dir,
        solution_path=solution_path,
        candidate_config=candidate_config,
        candidate_summary=candidate_summary,
        coverage_mapping_config=coverage_mapping_config,
        coverage_summary=coverage_summary,
        coverage_diagnostics=coverage_diagnostics,
        coverage_runtime_summary=coverage_runtime_summary,
        selection_config=selection_config,
        celf_result=celf_result,
        repair_result=repair_result,
        repair_objective_summary=repair_objective_summary,
        timing_seconds=timings,
    )
    write_json(solution_dir / "status.json", status)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", required=True, type=Path)
    parser.add_argument("--config-dir", default="", type=str)
    parser.add_argument("--solution-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        return run(args.case_dir, _config_dir(args.config_dir), args.solution_dir)
    except Exception as exc:
        args.solution_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            args.solution_dir / "status.json",
            {
                "status": "error",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        print(f"regional coverage CELF solver failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
