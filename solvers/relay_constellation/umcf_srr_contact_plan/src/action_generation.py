"""Convert SRR rounded paths into compacted, verifier-valid link actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np

from .case_io import Manifest
from .srr import Path
from .time_grid import time_for_index
from .umcf import UMCFInstance


def _isoformat_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_edge(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


@dataclass(frozen=True)
class LinkAction:
    """Benchmark-shaped link action."""

    action_type: str
    start_time: datetime
    end_time: datetime
    endpoint_id: str | None = None
    satellite_id: str | None = None
    satellite_id_1: str | None = None
    satellite_id_2: str | None = None


def filter_infeasible_edges(
    edge_samples: dict[tuple[str, str], set[int]],
    positions_ecef: dict[str, np.ndarray],
    endpoints: dict[str, Endpoint],
    manifest: Manifest,
) -> tuple[dict[tuple[str, str], set[int]], dict[str, Any]]:
    """Remove ground-link samples that fail the exact brahe geometry check.

    The solver's fast vectorised elevation computation is approximate; this
    filter tightens the edge set to samples that are guaranteed to pass the
    verifier's exact check.
    """
    import brahe

    filtered: dict[tuple[str, str], set[int]] = {
        edge: set(samples) for edge, samples in edge_samples.items()
    }
    removed_count = 0

    for edge, samples in filtered.items():
        a, b = edge
        # Identify ground-link edges
        endpoint_id: str | None = None
        satellite_id: str | None = None
        if a in endpoints:
            endpoint_id = a
            satellite_id = b
        elif b in endpoints:
            endpoint_id = b
            satellite_id = a
        else:
            continue  # ISL — solver already matches verifier exactly

        endpoint = endpoints[endpoint_id]
        sat_pos = positions_ecef[satellite_id]

        to_remove: set[int] = set()
        for sample_idx in samples:
            relative_enz = np.asarray(
                brahe.relative_position_ecef_to_enz(
                    endpoint.ecef_position_m,
                    sat_pos[sample_idx],
                    brahe.EllipsoidalConversionType.GEODETIC,
                ),
                dtype=float,
            )
            azel = np.asarray(
                brahe.position_enz_to_azel(relative_enz, brahe.AngleFormat.DEGREES),
                dtype=float,
            )
            elevation_deg = float(azel[1])
            range_m = float(azel[2])

            is_feasible = elevation_deg >= endpoint.min_elevation_deg
            if manifest.max_ground_range_m is not None:
                is_feasible = is_feasible and (range_m <= manifest.max_ground_range_m)

            if not is_feasible:
                to_remove.add(sample_idx)
                removed_count += 1

        samples -= to_remove

    # Clean up empty sets
    filtered = {edge: samples for edge, samples in filtered.items() if samples}

    summary = {"removed_ground_link_samples": removed_count}
    return filtered, summary


def extract_edge_samples(
    umcf_instances: list[UMCFInstance],
    sample_assignments: list[dict[str, Path]],
) -> dict[tuple[str, str], set[int]]:
    """Map each canonical edge to the set of sample indices where it is used.

    Parameters
    ----------
    umcf_instances
        One per entry in ``sample_assignments``, used only for ``sample_index``.
    sample_assignments
        List of demand-to-path maps, one per UMCF instance.

    Returns
    -------
    dict[tuple[str, str], set[int]]
        Canonical edge -> sample indices where the edge appears in an SRR path.
    """
    edge_samples: dict[tuple[str, str], set[int]] = {}
    for instance, assignments in zip(umcf_instances, sample_assignments):
        sample_idx = instance.sample_index
        for path in assignments.values():
            for edge in path.edges:
                edge_samples.setdefault(edge, set()).add(sample_idx)
    return edge_samples


def _build_edge_importance(
    umcf_instances: list[UMCFInstance],
    sample_assignments: list[dict[str, Path]],
) -> dict[tuple[int, tuple[str, str]], float]:
    """Compute importance = max commodity weight per (sample, edge)."""
    importance: dict[tuple[int, tuple[str, str]], float] = {}
    for instance, assignments in zip(umcf_instances, sample_assignments):
        sample_idx = instance.sample_index
        weight_by_demand = {c.demand_id: c.weight for c in instance.commodities}
        for demand_id, path in assignments.items():
            weight = weight_by_demand.get(demand_id, 0.0)
            for edge in path.edges:
                key = (sample_idx, edge)
                importance[key] = max(importance.get(key, 0.0), weight)
    return importance


def repair_degree_caps(
    edge_samples: dict[tuple[str, str], set[int]],
    umcf_instances: list[UMCFInstance],
    sample_assignments: list[dict[str, Path]],
    max_links_per_satellite: int,
    max_links_per_endpoint: int,
    endpoint_ids: set[str],
) -> tuple[dict[tuple[str, str], set[int]], dict[str, Any]]:
    """Deterministically drop edges at samples that violate degree caps.

    Importance per edge per sample is the maximum commodity weight of any
    demand whose SRR path uses that edge at that sample.  Edges with lower
    importance are dropped first; ties break by canonical edge tuple.

    Returns
    -------
    repaired edge_samples mapping and a repair summary dict.
    """
    importance = _build_edge_importance(umcf_instances, sample_assignments)

    # Deep copy so we don't mutate the caller's mapping
    repaired: dict[tuple[str, str], set[int]] = {
        edge: set(samples) for edge, samples in edge_samples.items()
    }

    # Collect all sample indices that appear
    all_samples: set[int] = set()
    for samples in repaired.values():
        all_samples.update(samples)

    total_dropped = 0
    samples_repaired = 0

    for sample_idx in sorted(all_samples):
        # Iteratively drop least-important edges incident to over-cap nodes
        while True:
            active_edges = {
                edge for edge, samples in repaired.items() if sample_idx in samples
            }
            if not active_edges:
                break

            # Count degrees
            degrees: dict[str, int] = {}
            for edge in active_edges:
                a, b = edge
                degrees[a] = degrees.get(a, 0) + 1
                degrees[b] = degrees.get(b, 0) + 1

            # Find over-cap nodes and their excess
            over_cap_nodes: set[str] = set()
            for node, deg in degrees.items():
                cap = max_links_per_endpoint if node in endpoint_ids else max_links_per_satellite
                if deg > cap:
                    over_cap_nodes.add(node)

            if not over_cap_nodes:
                break

            # Candidate drops: edges incident to at least one over-cap node
            candidates = []
            for edge in active_edges:
                a, b = edge
                if a in over_cap_nodes or b in over_cap_nodes:
                    imp = importance.get((sample_idx, edge), 0.0)
                    candidates.append((imp, edge))

            # Sort by ascending importance, then deterministic edge tuple
            candidates.sort(key=lambda x: (x[0], x[1]))

            # Drop the least important edge
            _, edge_to_drop = candidates[0]
            repaired[edge_to_drop].discard(sample_idx)
            total_dropped += 1

        # Check if this sample had any repair work
        original_count = sum(
            1 for samples in edge_samples.values() if sample_idx in samples
        )
        repaired_count = sum(
            1 for samples in repaired.values() if sample_idx in samples
        )
        if repaired_count < original_count:
            samples_repaired += 1

    # Clean up empty sets
    repaired = {edge: samples for edge, samples in repaired.items() if samples}

    summary = {
        "total_dropped_edges": total_dropped,
        "samples_repaired": samples_repaired,
    }
    return repaired, summary


def compact_actions(
    edge_samples: dict[tuple[str, str], set[int]],
    endpoint_ids: set[str],
    manifest: Manifest,
) -> tuple[list[LinkAction], dict[str, Any]]:
    """Merge consecutive sample indices into interval actions.

    Each maximal consecutive run of sample indices for an edge becomes one
    action with grid-aligned start and end times.

    Returns
    -------
    List of LinkAction objects and a compaction summary.
    """
    actions: list[LinkAction] = []
    total_edge_samples = 0

    for edge, samples in edge_samples.items():
        if not samples:
            continue
        sorted_samples = sorted(samples)
        total_edge_samples += len(sorted_samples)

        # Merge consecutive runs
        run_start = sorted_samples[0]
        prev = run_start

        for s in sorted_samples[1:]:
            if s == prev + 1:
                prev = s
            else:
                # Emit [run_start, prev]
                actions.append(_make_action(edge, run_start, prev, endpoint_ids, manifest))
                run_start = s
                prev = s

        # Emit final run
        actions.append(_make_action(edge, run_start, prev, endpoint_ids, manifest))

    summary = {
        "num_actions": len(actions),
        "num_unique_edges": len(edge_samples),
        "total_edge_samples": total_edge_samples,
    }
    return actions, summary


def _make_action(
    edge: tuple[str, str],
    run_start: int,
    run_end: int,
    endpoint_ids: set[str],
    manifest: Manifest,
) -> LinkAction:
    """Create a LinkAction for a consecutive sample run."""
    a, b = edge
    start_time = time_for_index(manifest, run_start)
    end_time = time_for_index(manifest, run_end + 1)

    if a in endpoint_ids or b in endpoint_ids:
        # ground_link
        endpoint_id = a if a in endpoint_ids else b
        satellite_id = b if a in endpoint_ids else a
        return LinkAction(
            action_type="ground_link",
            start_time=start_time,
            end_time=end_time,
            endpoint_id=endpoint_id,
            satellite_id=satellite_id,
        )
    else:
        # inter_satellite_link — sort satellite IDs for determinism
        sat_a, sat_b = sorted((a, b))
        return LinkAction(
            action_type="inter_satellite_link",
            start_time=start_time,
            end_time=end_time,
            satellite_id_1=sat_a,
            satellite_id_2=sat_b,
        )


def actions_to_json(actions: list[LinkAction]) -> list[dict[str, Any]]:
    """Convert LinkAction objects to benchmark solution JSON schema."""
    result = []
    for action in sorted(
        actions,
        key=lambda a: (
            a.action_type,
            a.endpoint_id or "",
            a.satellite_id or "",
            a.satellite_id_1 or "",
            a.satellite_id_2 or "",
            a.start_time.isoformat(),
        ),
    ):
        payload: dict[str, Any] = {
            "action_type": action.action_type,
            "start_time": _isoformat_z(action.start_time),
            "end_time": _isoformat_z(action.end_time),
        }
        if action.action_type == "ground_link":
            payload["endpoint_id"] = action.endpoint_id
            payload["satellite_id"] = action.satellite_id
        else:
            payload["satellite_id_1"] = action.satellite_id_1
            payload["satellite_id_2"] = action.satellite_id_2
        result.append(payload)
    return result
