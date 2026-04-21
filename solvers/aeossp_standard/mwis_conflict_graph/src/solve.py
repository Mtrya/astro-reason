"""Solver entrypoint: generate candidates, solve MWIS graph, and emit actions."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from candidates import CandidateConfig, generate_candidates
from case_io import load_case, load_solver_config
from graph import build_conflict_graph, connected_components
from mwis import MwisConfig, select_weighted_independent_set
from solution_io import write_json, write_solution
from validation import RepairConfig, repair_candidates


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
) -> dict:
    return {
        "status": "phase_4_tuned_solution_generated",
        "phase": 4,
        "case_dir": str(case_dir),
        "config_dir": str(config_dir) if config_dir is not None else None,
        "solution": str(solution_path),
        "case_id": case.mission.case_id,
        "satellite_count": len(case.satellites),
        "task_count": len(case.tasks),
        "candidate_config": candidate_config.as_status_dict(),
        "mwis_config": mwis_config.as_dict(),
        **candidate_summary.as_debug_dict(case),
        "graph": graph.stats.as_dict(),
        "solver": mwis_stats.as_dict(),
        "repair_config": repair_config.as_status_dict(),
        "local_validation": repair_result.as_status_dict(),
        "timing_seconds": timing_seconds,
        "tuning_summary": {
            "best_local_valid": repair_result.final_report.valid,
            "candidate_count": candidate_summary.candidate_count,
            "selected_action_count_before_repair": mwis_stats.selected_candidate_count,
            "selected_action_count_after_repair": len(repair_result.candidates),
            "repair_iteration_count": len(repair_result.removals),
            "selection_policy": mwis_stats.selection_policy,
            "runtime_seconds": timing_seconds["total"],
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
        config_payload = load_solver_config(config_dir)
        candidate_config = CandidateConfig.from_mapping(config_payload)
        mwis_config = MwisConfig.from_mapping(config_payload)
        repair_config = RepairConfig.from_mapping(config_payload)
        case = load_case(case_dir)
        candidate_start = time.perf_counter()
        candidates, candidate_summary = generate_candidates(case, candidate_config)
        candidate_end = time.perf_counter()
        graph_start = time.perf_counter()
        graph = build_conflict_graph(case, candidates)
        graph_end = time.perf_counter()
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
        solution_path = write_solution(solution_dir, repair_result.candidates)
        total_end = time.perf_counter()
        timing_seconds = {
            "candidate_generation": candidate_end - candidate_start,
            "graph_build": graph_end - graph_start,
            "selection": selection_end - selection_start,
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
            graph=graph,
            mwis_config=mwis_config,
            mwis_stats=mwis_stats,
            repair_config=repair_config,
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
        solution_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            solution_dir / "status.json",
            {
                "status": "error",
                "phase": 4,
                "case_dir": str(case_dir),
                "config_dir": str(config_dir) if config_dir is not None else None,
                "error": str(exc),
            },
        )
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"phase_4_tuned_solution_generated: {case.mission.case_id} "
        f"candidates={candidate_summary.candidate_count} "
        f"selected={mwis_stats.selected_candidate_count} "
        f"after_repair={len(repair_result.candidates)} "
        f"local_valid={repair_result.final_report.valid} "
        f"policy={mwis_stats.selection_policy} -> {solution_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
