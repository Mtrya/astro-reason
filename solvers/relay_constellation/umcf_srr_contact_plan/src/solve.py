"""Main solver entrypoint for UMCF/SRR contact-plan scaffold."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from .case_io import load_case
from .candidate_selection import load_selection_config, select_candidates
from .dynamic_graph import build_sample_graphs, graph_summary
from .orbit_library import generate_candidates
from .solution_io import write_solution, write_status


def solve(
    case_dir: str | Path,
    solution_dir: str | Path,
    config_dir: str | Path = "",
) -> dict[str, Any]:
    """Run the solver scaffold: parse, generate candidates, build graphs, select candidates, emit solution."""
    t0 = time.perf_counter()

    # 1. Parse case
    t_parse_start = time.perf_counter()
    case = load_case(case_dir)
    t_parse = time.perf_counter() - t_parse_start

    # 2. Load config
    selection_config = load_selection_config(config_dir) if config_dir else load_selection_config(None)

    # 3. Generate candidates
    t_candidate_start = time.perf_counter()
    all_satellites = dict(case.backbone_satellites)
    candidates = generate_candidates(case.manifest)
    all_satellites.update(candidates)
    t_candidate = time.perf_counter() - t_candidate_start

    # 4. Build dynamic graphs (includes propagation + geometry)
    t_graph_start = time.perf_counter()
    sample_graphs = build_sample_graphs(case, all_satellites)
    t_graph = time.perf_counter() - t_graph_start

    # 5. Candidate selection
    t_select_start = time.perf_counter()
    selected_candidates, selection_debug = select_candidates(
        case, sample_graphs, candidates, selection_config
    )
    t_select = time.perf_counter() - t_select_start

    t_total = time.perf_counter() - t0

    # 6. Write solution
    solution_path = Path(solution_dir)
    write_solution(solution_path, selected_candidates, [])

    # 7. Write debug artifacts
    debug_dir = solution_path / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    if selection_debug:
        (debug_dir / "selected_candidates.json").write_text(
            json.dumps(
                {
                    "selected_candidate_ids": selection_debug.get("selected_candidate_ids", []),
                    "policy": selection_debug.get("policy", ""),
                    "baseline_total_weighted_service": selection_debug.get("baseline_total_weighted_service", 0.0),
                    "selected_total_weighted_service": selection_debug.get("selected_total_weighted_service", 0.0),
                    "scores_by_iteration": selection_debug.get("scores_by_iteration", []),
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        (debug_dir / "routed_potential_summary.json").write_text(
            json.dumps(selection_debug, indent=2) + "\n", encoding="utf-8"
        )

    # 8. Write status
    graph_stats = graph_summary(sample_graphs)
    status_summary = {
        "case_id": case.manifest.case_id,
        "num_backbone_satellites": len(case.backbone_satellites),
        "num_candidate_satellites": len(candidates),
        "num_ground_endpoints": len(case.ground_endpoints),
        "num_demands": len(case.demands),
        "num_routing_samples": case.manifest.total_samples,
        "graph_avg_nodes": graph_stats["avg_nodes"],
        "graph_avg_edges": graph_stats["avg_edges"],
        "graph_total_edges": graph_stats["total_edges"],
        "selected_candidate_ids": selection_debug.get("selected_candidate_ids", []),
        "selection_policy": selection_debug.get("policy", ""),
        "evaluation_sample_count": selection_debug.get("evaluation_sample_count", 0),
    }
    timing = {
        "parse": round(t_parse, 6),
        "candidate_generation": round(t_candidate, 6),
        "graph_construction": round(t_graph, 6),
        "candidate_selection": round(t_select, 6),
        "total": round(t_total, 6),
    }
    write_status(solution_path, timing, status_summary)

    return {
        "solution_dir": str(solution_path),
        "timing_s": timing,
        "summary": status_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="UMCF/SRR contact-plan solver scaffold")
    parser.add_argument("--case-dir", required=True, help="Path to benchmark case directory")
    parser.add_argument("--config-dir", default="", help="Optional config directory")
    parser.add_argument("--solution-dir", default="solution", help="Output directory for solution artifacts")
    args = parser.parse_args()

    result = solve(args.case_dir, args.solution_dir, args.config_dir)
    print(f"Solver finished. Solution written to {result['solution_dir']}")


if __name__ == "__main__":
    main()
