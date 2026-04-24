"""Routing-aware candidate selection using cheap reachability proxies."""

from __future__ import annotations

from collections import deque
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .case_io import Case, Demand, Satellite
from .dynamic_graph import SampleGraph
from .time_grid import demand_indices


@dataclass
class SelectionConfig:
    """Configuration for candidate selection."""

    policy: str = "greedy_marginal"  # no-added, greedy_marginal, fixed
    max_added_satellites: int | None = None
    fixed_candidates: list[str] = field(default_factory=list)
    evaluation_sample_stride: int = 10
    latency_weight: float = 0.0


def load_selection_config(config_dir: str | Path | None) -> SelectionConfig:
    """Load candidate selection config from config_dir/config.yaml if present."""
    if not config_dir:
        return SelectionConfig()
    config_path = Path(config_dir) / "config.yaml"
    if not config_path.is_file():
        return SelectionConfig()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    sel = raw.get("candidate_selection", {})
    return SelectionConfig(
        policy=sel.get("policy", "greedy_marginal"),
        max_added_satellites=sel.get("max_added_satellites"),
        fixed_candidates=sel.get("fixed_candidates", []),
        evaluation_sample_stride=sel.get("evaluation_sample_stride", 10),
        latency_weight=sel.get("latency_weight", 0.0),
    )


class _UnionFind:
    """Simple Union-Find for small node sets."""

    def __init__(self, nodes: set[str]):
        self.parent = {node: node for node in nodes}
        self.rank = {node: 0 for node in nodes}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: str, y: str) -> None:
        px, py = self.find(x), self.find(y)
        if px == py:
            return
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1


def _evaluate_sample(
    graph: SampleGraph,
    demands: list[Demand],
    allowed_satellites: set[str],
) -> tuple[float, dict[str, int]]:
    """Compute served demand-samples for one sample graph using Union-Find on satellites.

    Returns (total_weighted_service, {demand_id: served_0_1}).
    """
    if not allowed_satellites:
        return 0.0, {d.demand_id: 0 for d in demands}

    # Build Union-Find on allowed satellites using ISLs
    uf = _UnionFind(allowed_satellites)
    for sat in allowed_satellites:
        for edge in graph.adjacency.get(sat, []):
            if edge.edge_type == "inter_satellite_link" and edge.node_b in allowed_satellites:
                uf.union(sat, edge.node_b)

    # Precompute ground connections for each endpoint
    endpoint_to_sats: dict[str, set[str]] = {}
    for ep_id in graph.endpoint_ids:
        sats: set[str] = set()
        for edge in graph.adjacency.get(ep_id, []):
            if edge.node_b in allowed_satellites:
                sats.add(edge.node_b)
        endpoint_to_sats[ep_id] = sats

    total_weighted = 0.0
    per_demand: dict[str, int] = {}
    for demand in demands:
        src_sats = endpoint_to_sats.get(demand.source_endpoint_id, set())
        dst_sats = endpoint_to_sats.get(demand.destination_endpoint_id, set())
        served = False
        for s1 in src_sats:
            root1 = uf.find(s1)
            for s2 in dst_sats:
                if root1 == uf.find(s2):
                    served = True
                    break
            if served:
                break
        per_demand[demand.demand_id] = 1 if served else 0
        if served:
            total_weighted += demand.weight

    return total_weighted, per_demand


def _evaluate_allowed_set(
    sample_graphs: list[SampleGraph],
    demands: list[Demand],
    allowed_satellites: set[str],
    sample_indices: list[int],
) -> dict[str, Any]:
    """Evaluate a full allowed satellite set over sampled indices."""
    total_weighted = 0.0
    per_demand_samples: dict[str, int] = {d.demand_id: 0 for d in demands}

    for idx in sample_indices:
        graph = sample_graphs[idx]
        w, pd = _evaluate_sample(graph, demands, allowed_satellites)
        total_weighted += w
        for did, val in pd.items():
            per_demand_samples[did] += val

    return {
        "total_weighted_service": total_weighted,
        "per_demand_samples": per_demand_samples,
    }


def _evaluate_candidate_worker(
    sample_graphs: list[SampleGraph],
    demands: list[Demand],
    current_allowed: list[str],
    candidate_id: str,
    sample_indices: list[int],
) -> dict[str, Any]:
    """Pickle-friendly worker for parallel candidate evaluation."""
    allowed = set(current_allowed) | {candidate_id}
    return _evaluate_allowed_set(sample_graphs, demands, allowed, sample_indices)


def _compute_marginal_scores(
    sample_graphs: list[SampleGraph],
    demands: list[Demand],
    backbone_ids: set[str],
    selected_ids: set[str],
    remaining_candidates: list[str],
    sample_indices: list[int],
) -> dict[str, dict[str, Any]]:
    """Compute marginal scores for all remaining candidates."""
    current_allowed = backbone_ids | selected_ids
    baseline = _evaluate_allowed_set(sample_graphs, demands, current_allowed, sample_indices)

    # Evaluate each candidate
    if len(remaining_candidates) == 1:
        results = {
            remaining_candidates[0]: _evaluate_allowed_set(
                sample_graphs, demands,
                current_allowed | {remaining_candidates[0]}, sample_indices
            )
        }
    else:
        with ProcessPoolExecutor() as executor:
            futures = {
                executor.submit(
                    _evaluate_candidate_worker,
                    sample_graphs, demands,
                    sorted(current_allowed), cid, sample_indices
                ): cid
                for cid in remaining_candidates
            }
            results = {cid: f.result() for f, cid in futures.items()}

    scores: dict[str, dict[str, Any]] = {}
    for cid in remaining_candidates:
        total_new = results[cid]["total_weighted_service"] - baseline["total_weighted_service"]
        worst_new = max(
            results[cid]["per_demand_samples"][d.demand_id] - baseline["per_demand_samples"][d.demand_id]
            for d in demands
        )
        scores[cid] = {
            "total_weighted_service": total_new,
            "worst_demand_samples": worst_new,
        }

    return scores


def select_candidates(
    case: Case,
    sample_graphs: list[SampleGraph],
    candidates: dict[str, Satellite],
    config: SelectionConfig | None = None,
) -> tuple[dict[str, Satellite], dict[str, Any]]:
    """Select added satellite candidates according to config.

    Returns (selected_candidates, debug_info).
    """
    if config is None:
        config = SelectionConfig()

    backbone_ids = set(case.backbone_satellites.keys())
    max_added = config.max_added_satellites
    if max_added is None:
        max_added = case.manifest.max_added_satellites

    # Determine sample indices to evaluate
    all_indices = list(range(len(sample_graphs)))
    if config.evaluation_sample_stride > 1:
        sample_indices = all_indices[::config.evaluation_sample_stride]
    else:
        sample_indices = all_indices

    if config.policy == "no-added":
        return {}, {
            "policy": "no-added",
            "selected_candidate_ids": [],
            "baseline_total_weighted_service": _evaluate_allowed_set(
                sample_graphs, case.demands, backbone_ids, sample_indices
            )["total_weighted_service"],
            "scores_by_iteration": [],
        }

    if config.policy == "fixed":
        fixed = config.fixed_candidates
        invalid = [cid for cid in fixed if cid not in candidates]
        if invalid:
            raise ValueError(f"Fixed candidates not in library: {invalid}")
        selected = {cid: candidates[cid] for cid in fixed}
        return selected, {
            "policy": "fixed",
            "selected_candidate_ids": fixed,
            "baseline_total_weighted_service": _evaluate_allowed_set(
                sample_graphs, case.demands, backbone_ids, sample_indices
            )["total_weighted_service"],
            "scores_by_iteration": [],
        }

    # greedy_marginal
    remaining = sorted(candidates.keys())
    selected_ids: set[str] = set()
    selected_order: list[str] = []
    scores_by_iteration: list[dict[str, Any]] = []

    for _ in range(max_added):
        if not remaining:
            break

        scores = _compute_marginal_scores(
            sample_graphs, case.demands,
            backbone_ids, selected_ids, remaining, sample_indices
        )

        # Pick best: highest total, then highest worst-demand, then deterministic id
        best = max(remaining, key=lambda cid: (
            scores[cid]["total_weighted_service"],
            scores[cid]["worst_demand_samples"],
            cid,
        ))

        if scores[best]["total_weighted_service"] <= 0:
            break

        selected_ids.add(best)
        selected_order.append(best)
        remaining.remove(best)
        scores_by_iteration.append({
            "candidate_id": best,
            **scores[best],
        })

    selected = {cid: candidates[cid] for cid in selected_order}
    baseline_result = _evaluate_allowed_set(
        sample_graphs, case.demands, backbone_ids, sample_indices
    )
    selected_result = _evaluate_allowed_set(
        sample_graphs, case.demands, backbone_ids | selected_ids, sample_indices
    )

    debug_info = {
        "policy": "greedy_marginal",
        "evaluation_sample_count": len(sample_indices),
        "evaluation_sample_stride": config.evaluation_sample_stride,
        "selected_candidate_ids": selected_order,
        "baseline_total_weighted_service": baseline_result["total_weighted_service"],
        "selected_total_weighted_service": selected_result["total_weighted_service"],
        "scores_by_iteration": scores_by_iteration,
    }

    return selected, debug_info
