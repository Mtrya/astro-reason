"""Main solver entrypoint for UMCF/SRR contact-plan solver."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import yaml

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


def _load_srr_config(config_dir: str | Path | None) -> SRRConfig:
    """Load SRR config from config_dir/config.yaml if present."""
    if not config_dir:
        return SRRConfig()
    config_path = Path(config_dir) / "config.yaml"
    if not config_path.is_file():
        return SRRConfig()
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return SRRConfig()
    srr = raw.get("srr", {})
    return SRRConfig(
        seed=srr.get("seed", 42),
        deterministic=srr.get("deterministic", False),
        k_paths=srr.get("k_paths", 4),
        path_change_penalty=srr.get("path_change_penalty", 1.0),
        multi_run_count=srr.get("multi_run_count", 1),
        max_path_hops=srr.get("max_path_hops", 10),
    )


def solve(
    case_dir: str | Path,
    solution_dir: str | Path,
    config_dir: str | Path = "",
) -> dict[str, Any]:
    """Run the solver: parse, generate candidates, build graphs, select candidates, emit solution."""
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

    srr_config = _load_srr_config(config_dir)
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

    # Rounded path log — one entry per (sample, demand) with chosen path
    rounded_path_log: list[dict[str, Any]] = []
    for instance, assignments in zip(umcf_instances, srr_result.sample_assignments):
        for demand_id, path in assignments.items():
            rounded_path_log.append({
                "sample_index": instance.sample_index,
                "demand_id": demand_id,
                "nodes": list(path.nodes),
                "edges": [list(e) for e in path.edges],
                "hop_count": path.hop_count,
                "total_distance_m": round(path.total_distance_m, 3),
            })
    (debug_dir / "rounded_paths.json").write_text(
        json.dumps(rounded_path_log, indent=2) + "\n", encoding="utf-8"
    )

    # Active link summary — per-sample edge counts before/after repair
    active_link_summary: list[dict[str, Any]] = []
    for instance in umcf_instances:
        idx = instance.sample_index
        pre_count = sum(1 for samples in edge_samples.values() if idx in samples)
        post_count = sum(1 for samples in repaired.values() if idx in samples)
        active_link_summary.append({
            "sample_index": idx,
            "active_edges_before_repair": pre_count,
            "active_edges_after_repair": post_count,
        })
    (debug_dir / "active_link_summary.json").write_text(
        json.dumps(active_link_summary, indent=2) + "\n", encoding="utf-8"
    )

    # Reproduction summary — explicit paper-component mapping
    reproduction_summary = {
        "sources": [
            {"paper": "Grislain et al. 2024", "title": "Rethinking LEO Constellations Routing"},
            {"paper": "Lamothe et al. 2023", "title": "Dynamic Unsplittable Flows with Path-Change Penalties"},
        ],
        "components": {
            "umcf_commodities_and_capacities": {
                "status": "ADAPTED",
                "note": "Commodities derived from benchmark demand windows. Edge capacities fixed to 1 (unit edge-disjoint) matching verifier allocation, not flow-based capacities from Grislain.",
            },
            "unsplittable_one_path_per_commodity": {
                "status": "IMPLEMENTED",
                "note": "SRR assigns exactly one path per commodity per sample. Matches Grislain Algorithm 1 and Lamothe integer constraints.",
            },
            "lp_relaxation_for_fractional_flows": {
                "status": "MISSING",
                "note": "No LP solver (Gurobi/SCIP) is used. Heuristic uniform probabilities plus path-change boost replace LP-derived fractional flows.",
            },
            "srr_sequential_rounding": {
                "status": "IMPLEMENTED",
                "note": "Commodities processed in decreasing-weight order. Edge capacities updated after each fixation. Matches Grislain Algorithm 1 lines 1-10.",
            },
            "randomized_rounding_from_lp_solution": {
                "status": "ADAPTED",
                "note": "Probabilities are heuristic (uniform base + exp(boost) for previous path) instead of sampled from LP relaxation x_p^k values.",
            },
            "k_shortest_path_restriction": {
                "status": "IMPLEMENTED",
                "note": "k=4 shortest simple paths by hop count then distance, matching Lamothe Appendix C parameter setting.",
            },
            "dynamic_path_change_penalty": {
                "status": "ADAPTED",
                "note": "Per-sample boost to previous path (exp(penalty_alpha)) instead of Lamothe per-block MILP objective term P * sum(1 - x_k).",
            },
            "k_nearest_first_last_hop": {
                "status": "MISSING",
                "note": "Solver uses all ground-visible satellites; no k-nearest restriction on ingress/egress hops as studied in Grislain Section 4.",
            },
            "path_sequence_formulation": {
                "status": "MISSING",
                "note": "Lamothe Section 3.1 path-sequence MILP with column generation not implemented.",
            },
            "extended_arc_path_formulation": {
                "status": "MISSING",
                "note": "Lamothe Section 3.2 compact MILP not implemented.",
            },
            "aggregated_arc_node_formulation": {
                "status": "MISSING",
                "note": "Lamothe Section 3.4 super-commodity LP relaxation not implemented.",
            },
            "column_generation_pricing": {
                "status": "MISSING",
                "note": "No column generation or pricing schemes (Lamothe Sections 4.1-4.3) are used.",
            },
            "srr_recomputation_threshold_theta": {
                "status": "MISSING",
                "note": "LP is never recomputed because no LP is solved. Threshold theta (Lamothe Appendix C) irrelevant.",
            },
            "flow_penalization_epsilon": {
                "status": "MISSING",
                "note": "Lamotte Appendix C hop-based cost epsilon=1e-4 not used. Paths sorted by hop count then distance instead.",
            },
            "multi_time_step_methods": {
                "status": "MISSING",
                "note": "Solver processes each sample independently (one time step at a time). No path-sequence or rolling-horizon optimization.",
            },
            "candidate_orbit_library": {
                "status": "IMPLEMENTED",
                "note": "Deterministic Walker-delta orbit library generated from manifest constraints. Not from Grislain/Lamothe.",
            },
            "greedy_marginal_candidate_selection": {
                "status": "IMPLEMENTED",
                "note": "Union-Find reachability proxy with per-candidate marginal scoring. Solver-local heuristic, not from papers.",
            },
            "geometry_pre_validation": {
                "status": "IMPLEMENTED",
                "note": "Exact brahe elevation filter removes boundary-mismatch samples before compaction. Benchmark adaptation.",
            },
            "degree_cap_repair": {
                "status": "IMPLEMENTED",
                "note": "Importance-based deterministic dropping enforces per-sample degree caps. Benchmark adaptation.",
            },
            "interval_compaction": {
                "status": "IMPLEMENTED",
                "note": "Consecutive sample runs merged into grid-aligned interval actions. Benchmark adaptation.",
            },
        },
        "drift_notes": {
            "oracle_vs_verifier_service": "Internal SRR serves commodities on per-sample graphs; verifier re-allocates routes from compacted intervals. Drift arises because: (1) verifier uses edge-disjoint shortest-path allocation per sample, not SRR paths; (2) repair drops edges that SRR selected; (3) compaction creates intervals where some interior samples may lack verifier-feasible geometry.",
            "latency_drift": "SRR paths optimize hop count then distance; verifier uses shortest-path by distance. UMCF may prefer longer paths for load balancing, increasing mean latency vs verifier's optimal routing.",
            "action_count_drift": "SRR path changes create many short intervals. Path-change penalty reduces churn but cannot eliminate it because the underlying graph changes dynamically.",
        },
    }
    (debug_dir / "reproduction_summary.json").write_text(
        json.dumps(reproduction_summary, indent=2) + "\n", encoding="utf-8"
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
    parser = argparse.ArgumentParser(description="UMCF/SRR contact-plan solver")
    parser.add_argument("--case-dir", required=True, help="Path to benchmark case directory")
    parser.add_argument("--config-dir", default="", help="Optional config directory")
    parser.add_argument("--solution-dir", default="solution", help="Output directory for solution artifacts")
    args = parser.parse_args()

    result = solve(args.case_dir, args.solution_dir, args.config_dir)
    print(f"Solver finished. Solution written to {result['solution_dir']}")


if __name__ == "__main__":
    main()
