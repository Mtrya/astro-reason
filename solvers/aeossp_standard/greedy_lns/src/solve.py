"""Solver entrypoint: generate candidates, build schedule via greedy insertion,
run solver-local repair, and emit a benchmark-compatible solution."""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

from candidates import CandidateConfig, generate_candidates
from case_io import load_case, load_solver_config
from components import build_component_index
from insertion import InsertionConfig, greedy_insertion
from local_search import LocalSearchConfig, local_search
from solution_io import write_json, write_solution
from validation import RepairConfig, repair_schedule, validate_schedule


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
        **candidate_summary.as_debug_dict(case),
        "insertion": insertion_result.as_dict(),
        "local_search": local_search_result.as_dict(),
        "repair": repair_result.as_status_dict(),
        "timing_seconds": timing_seconds,
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
    component_index = build_component_index(case, candidates)
    write_json(
        solution_dir / "debug" / "component_summary.json",
        {
            "case_id": case.mission.case_id,
            "component_index": component_index.as_dict(),
        },
    )

    # Validation summary: pre-repair and post-repair
    pre_repair_validation = validate_schedule(case, local_search_result.candidates)
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
        config_payload = load_solver_config(config_dir)
        candidate_config = CandidateConfig.from_mapping(config_payload)
        insertion_config = InsertionConfig.from_mapping(config_payload)
        local_search_config = LocalSearchConfig.from_mapping(config_payload)
        repair_config = RepairConfig.from_mapping(config_payload)
        case = load_case(case_dir)
        candidate_start = time.perf_counter()
        candidates, candidate_summary = generate_candidates(case, candidate_config)
        candidate_end = time.perf_counter()
        insertion_start = time.perf_counter()
        insertion_result = greedy_insertion(case, candidates, insertion_config)
        insertion_end = time.perf_counter()
        local_search_start = time.perf_counter()
        local_search_result = local_search(
            case, candidates, insertion_result.selected, config=local_search_config
        )
        local_search_end = time.perf_counter()
        repair_start = time.perf_counter()
        repair_result = repair_schedule(case, local_search_result.candidates, config=repair_config)
        repair_end = time.perf_counter()
        solution_path = write_solution(solution_dir, repair_result.candidates)
        total_end = time.perf_counter()
        timing_seconds = {
            "candidate_generation": candidate_end - candidate_start,
            "insertion": insertion_end - insertion_start,
            "local_search": local_search_end - local_search_start,
            "repair": repair_end - repair_start,
            "total": total_end - total_start,
        }
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
