"""Regional-coverage CELF scaffold and fixed-candidate selection entrypoint."""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from candidates import generate_candidates, load_candidate_config
from case_io import load_case
from celf import load_selection_config, run_celf_selection, sample_weight_lookup
from coverage import build_candidate_coverage
from schedule import feasibility_summary, repair_schedule
from solution_io import (
    write_candidate_debug,
    write_celf_debug,
    write_json,
    write_repair_debug,
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


def _build_status(
    *,
    case,
    config_dir: Path | None,
    solution_path: Path,
    candidate_config,
    candidate_summary,
    coverage_summary,
    selection_config,
    celf_result,
    repair_result,
    timing_seconds: dict[str, float],
) -> dict[str, Any]:
    return {
        "status": "ok",
        "phase": "phase_3_sequence_feasibility_and_repair",
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
        "selection_config": selection_config.as_status_dict(),
        "candidate_summary": candidate_summary.as_dict(),
        "coverage_summary": coverage_summary.as_dict(),
        "celf_summary": celf_result.as_dict(),
        "feasibility_summary": feasibility_summary(repair_result),
        "repair_summary": repair_result.as_dict(),
        "output_policy": {
            "solution_actions": len(repair_result.repaired_candidate_ids),
            "empty_solution_only": len(repair_result.repaired_candidate_ids) == 0,
            "selection_deferred_to_phase": None,
            "sequence_feasibility_deferred_to_phase": None,
            "satellite_repair_enabled": True,
            "experiment_registration_enabled": False,
            "coverage_geometry": "solver-local circular-orbit approximation",
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
    selection_config = load_selection_config(config_dir)
    timings["case_loading"] = _round_seconds(time.perf_counter() - start)

    start = time.perf_counter()
    candidates, candidate_summary = generate_candidates(case, candidate_config)
    timings["candidate_generation"] = _round_seconds(time.perf_counter() - start)

    start = time.perf_counter()
    coverage_by_candidate, coverage_summary = build_candidate_coverage(case, candidates)
    timings["coverage_mapping"] = _round_seconds(time.perf_counter() - start)

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

    start = time.perf_counter()
    candidates_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    repair_result = repair_schedule(
        case,
        candidates_by_id,
        celf_result.best.selected_candidate_ids,
        coverage_by_candidate,
        sample_weights,
    )
    timings["schedule_repair"] = _round_seconds(time.perf_counter() - start)

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
    timings["output"] = _round_seconds(time.perf_counter() - start)
    timings["total"] = _round_seconds(time.perf_counter() - total_start)

    status = _build_status(
        case=case,
        config_dir=config_dir,
        solution_path=solution_path,
        candidate_config=candidate_config,
        candidate_summary=candidate_summary,
        coverage_summary=coverage_summary,
        selection_config=selection_config,
        celf_result=celf_result,
        repair_result=repair_result,
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
        print(f"regional coverage CELF scaffold failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
