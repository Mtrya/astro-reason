"""Main solver entrypoint for UMCF/SRR contact-plan scaffold."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from .action_generation import (
    compact_actions,
    extract_edge_samples,
    filter_infeasible_edges,
    repair_degree_caps,
    actions_to_json,
)
from .case_io import load_case
from .candidate_selection import load_selection_config, select_candidates
from .dynamic_graph import build_sample_graphs, graph_summary
from .orbit_library import generate_candidates
from .propagation import propagate_all_to_samples
from .solution_io import write_solution, write_status
from .srr import SRRConfig, run_srr_oracle
from .umcf import build_umcf_instances, instance_summary


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
    positions_ecef = propagate_all_to_samples(case.manifest, all_satellites)
    sample_graphs = build_sample_graphs(case, all_satellites, positions_ecef)
    t_graph = time.perf_counter() - t_graph_start

    # 5. Candidate selection
    t_select_start = time.perf_counter()
    selected_candidates, selection_debug = select_candidates(
        case, sample_graphs, candidates, selection_config
    )
    t_select = time.perf_counter() - t_select_start

    # Rebuild graphs with selected satellites only to prevent routing
    # through unselected candidates during action generation.
    selected_satellites = dict(case.backbone_satellites)
    selected_satellites.update(selected_candidates)
    sample_graphs_selected = build_sample_graphs(
        case, selected_satellites, positions_ecef
    )

    # 6. Build UMCF instances and run SRR oracle on selected-only graphs
    t_umcf_start = time.perf_counter()
    umcf_instances = build_umcf_instances(case, sample_graphs_selected)
    t_umcf = time.perf_counter() - t_umcf_start

    srr_config = SRRConfig()
    t_srr_start = time.perf_counter()
    srr_result = run_srr_oracle(umcf_instances, srr_config)
    t_srr = time.perf_counter() - t_srr_start

    # 7. Generate actions from SRR paths
    t_action_start = time.perf_counter()
    edge_samples = extract_edge_samples(umcf_instances, srr_result.sample_assignments)
    endpoint_ids = set(case.ground_endpoints)

    # Tighten ground-link edges against exact verifier geometry
    edge_samples, geometry_summary = filter_infeasible_edges(
        edge_samples,
        positions_ecef,
        case.ground_endpoints,
        case.manifest,
    )

    repaired, repair_summary = repair_degree_caps(
        edge_samples,
        umcf_instances,
        srr_result.sample_assignments,
        case.manifest.max_links_per_satellite,
        case.manifest.max_links_per_endpoint,
        endpoint_ids,
    )
    actions, compaction_summary = compact_actions(repaired, endpoint_ids, case.manifest)
    action_json = actions_to_json(actions)
    t_action = time.perf_counter() - t_action_start

    t_total = time.perf_counter() - t0

    # 8. Write solution
    solution_path = Path(solution_dir)
    write_solution(solution_path, selected_candidates, action_json)

    # 9. Write debug artifacts
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

    # UMCF/SRR debug artifacts
    umcf_summary = instance_summary(umcf_instances)
    (debug_dir / "umcf_instances.json").write_text(
        json.dumps(umcf_summary, indent=2) + "\n", encoding="utf-8"
    )
    total_served = sum(len(a) for a in srr_result.sample_assignments)
    total_dropped = sum(len(d) for d in srr_result.dropped_by_sample)
    (debug_dir / "srr_summary.json").write_text(
        json.dumps(
            {
                "served_commodities": total_served,
                "dropped_commodities": total_dropped,
                "path_changes": srr_result.path_changes,
                "seed": srr_result.seed,
                "deterministic": srr_result.deterministic,
                "execution_time_s": round(srr_result.execution_time_s, 6),
                "timing_breakdown": srr_result.timing_breakdown,
                "approximation_disclosure": {
                    "lp_relaxation": "MISSING (heuristic probabilities used instead of LP fractional flows)",
                    "path_set_restriction": "IMPLEMENTED (k-shortest simple paths, k=4 default)",
                    "srr_control_flow": "IMPLEMENTED (sequential, demand-sorted, capacity-tracking)",
                    "dynamic_path_change_penalty": "ADAPTED (per-sample instead of per-block)",
                    "node_degree_modeling": "PARTIAL (approximated as node capacities, not consumed in rounding)",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Action generation debug
    (debug_dir / "action_summary.json").write_text(
        json.dumps(
            {
                "repair": repair_summary,
                "compaction": compaction_summary,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # 10. Write status
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
        "srr_served_commodities": total_served,
        "srr_dropped_commodities": total_dropped,
        "srr_path_changes": srr_result.path_changes,
        "srr_execution_time_s": round(srr_result.execution_time_s, 6),
        "srr_seed": srr_result.seed,
        "srr_deterministic": srr_result.deterministic,
        "num_actions": compaction_summary["num_actions"],
        "repair_dropped_edges": repair_summary["total_dropped_edges"],
        "repair_samples_repaired": repair_summary["samples_repaired"],
    }
    timing = {
        "parse": round(t_parse, 6),
        "candidate_generation": round(t_candidate, 6),
        "graph_construction": round(t_graph, 6),
        "candidate_selection": round(t_select, 6),
        "umcf_build": round(t_umcf, 6),
        "srr_rounding": round(t_srr, 6),
        "action_generation": round(t_action, 6),
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
