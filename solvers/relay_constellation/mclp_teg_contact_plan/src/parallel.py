"""Parallel propagation and link-feasibility computation via process pool."""

from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np


class ParallelExecutionError(Exception):
    """Raised when a process-pool stage fails; callers should fall back to sequential."""


# ---------------------------------------------------------------------------
# Propagation
# ---------------------------------------------------------------------------

def _propagate_one(
    args: tuple[str, tuple[float, ...], datetime, tuple[datetime, ...]]
) -> tuple[str, dict[int, np.ndarray], float]:
    """Worker: propagate a single satellite. Must be top-level for pickling."""
    satellite_id, state_eci_m_mps, epoch, sample_times = args
    # Import inside worker to avoid pickling module references
    from .propagation import propagate_satellite

    t0 = time.monotonic()
    positions = propagate_satellite(state_eci_m_mps, epoch, sample_times)
    elapsed_ms = (time.monotonic() - t0) * 1000.0
    return satellite_id, positions, elapsed_ms


def propagate_satellites_parallel(
    satellites: list[tuple[str, tuple[float, ...]]],
    epoch: datetime,
    sample_times: tuple[datetime, ...],
    max_workers: int | None = None,
) -> tuple[dict[str, dict[int, np.ndarray]], list[float]]:
    """Propagate many satellites in parallel via ProcessPoolExecutor.

    Parameters
    ----------
    satellites:
        List of (satellite_id, state_eci_m_mps) tuples.
    epoch:
        Case epoch.
    sample_times:
        Routing-grid sample instants.
    max_workers:
        Number of worker processes. Defaults to min(os.cpu_count(), len(satellites)).

    Returns
    -------
    Mapping satellite_id -> positions dict.

    Raises
    ------
    ParallelExecutionError
        If the process pool fails; callers should fall back to sequential.
    """
    if not satellites:
        return {}

    if max_workers is None:
        max_workers = min(os.cpu_count() or 1, len(satellites))

    if max_workers <= 1:
        from .propagation import propagate_satellite

        return {
            sid: propagate_satellite(state, epoch, sample_times)
            for sid, state in satellites
        }

    args_list = [(sid, state, epoch, sample_times) for sid, state in satellites]

    try:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(_propagate_one, args_list))
    except Exception as exc:
        raise ParallelExecutionError(f"Process pool propagation failed: {exc}") from exc

    positions_dict: dict[str, dict[int, np.ndarray]] = {}
    timings: list[float] = []
    for sid, positions, elapsed_ms in results:
        positions_dict[sid] = positions
        timings.append(elapsed_ms)

    return positions_dict, timings


# ---------------------------------------------------------------------------
# Link cache
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _EndpointData:
    endpoint_id: str
    ecef_m: tuple[float, float, float]
    min_elevation_deg: float


@dataclass(frozen=True)
class _LinkCacheChunkArgs:
    start_idx: int
    end_idx: int
    endpoint_data: tuple[_EndpointData, ...]
    sat_positions: dict[str, dict[int, tuple[float, float, float]]]
    max_ground_range_m: float | None
    max_isl_range_m: float


def _build_link_cache_chunk(args: _LinkCacheChunkArgs) -> list[tuple[str, int, str, str, float]]:
    """Worker: build link records for a chunk of sample indices.

    Returns flat list of (link_type, sample_index, node_a, node_b, distance_m).
    """
    import brahe
    from .link_geometry import ground_link_feasible, isl_feasible

    records: list[tuple[str, int, str, str, float]] = []
    sat_ids = list(args.sat_positions.keys())

    for sidx in range(args.start_idx, args.end_idx):
        # Ground links
        for ep in args.endpoint_data:
            ep_arr = np.array(ep.ecef_m, dtype=float)
            for sat_id in sat_ids:
                pos = np.array(args.sat_positions[sat_id][sidx], dtype=float)
                is_feasible, distance_m = ground_link_feasible(
                    ep.ecef_m, pos, ep.min_elevation_deg, args.max_ground_range_m
                )
                if is_feasible:
                    records.append(("ground", sidx, ep.endpoint_id, sat_id, distance_m))

        # ISLs
        for i in range(len(sat_ids)):
            for j in range(i + 1, len(sat_ids)):
                sat_a = sat_ids[i]
                sat_b = sat_ids[j]
                pos_a = np.array(args.sat_positions[sat_a][sidx], dtype=float)
                pos_b = np.array(args.sat_positions[sat_b][sidx], dtype=float)
                is_feasible, distance_m = isl_feasible(pos_a, pos_b, args.max_isl_range_m)
                if is_feasible:
                    records.append(("isl", sidx, sat_a, sat_b, distance_m))

    return records


def build_link_cache_parallel(
    case: Any,
    backbone_positions: dict[str, dict[int, np.ndarray]],
    candidate_positions: dict[str, dict[int, np.ndarray]],
    max_workers: int | None = None,
) -> tuple[tuple[Any, ...], dict[str, object]]:
    """Build link-feasibility cache in parallel over sample chunks.

    Parameters
    ----------
    case:
        Loaded Case object.
    backbone_positions:
        satellite_id -> sample_index -> ECEF ndarray.
    candidate_positions:
        satellite_id -> sample_index -> ECEF ndarray.
    max_workers:
        Number of worker processes. Defaults to os.cpu_count().

    Returns
    -------
    (link_records, summary) matching the contract of ``link_cache.build_link_cache``.

    Raises
    ------
    ParallelExecutionError
        If the process pool fails; callers should fall back to sequential.
    """
    import brahe
    from .link_cache import LinkRecord

    constraints = case.manifest.constraints
    endpoints = case.network.ground_endpoints
    num_samples = len(next(iter(backbone_positions.values())))

    if max_workers is None:
        max_workers = os.cpu_count() or 1

    if max_workers <= 1 or num_samples <= 1:
        from .link_cache import build_link_cache

        return build_link_cache(case, backbone_positions, candidate_positions)

    # Precompute endpoint ECEF positions
    endpoint_data: list[_EndpointData] = []
    for endpoint in endpoints:
        ecef_arr = brahe.position_geodetic_to_ecef(
            [endpoint.longitude_deg, endpoint.latitude_deg, endpoint.altitude_m],
            brahe.AngleFormat.DEGREES,
        )
        endpoint_data.append(
            _EndpointData(
                endpoint_id=endpoint.endpoint_id,
                ecef_m=tuple(float(v) for v in ecef_arr.tolist()),
                min_elevation_deg=endpoint.min_elevation_deg,
            )
        )

    # Convert positions to plain nested dicts for cheaper pickling
    all_sat_positions: dict[str, dict[int, tuple[float, float, float]]] = {}
    for sid, positions in backbone_positions.items():
        all_sat_positions[sid] = {idx: tuple(float(v) for v in pos.tolist()) for idx, pos in positions.items()}
    for sid, positions in candidate_positions.items():
        all_sat_positions[sid] = {idx: tuple(float(v) for v in pos.tolist()) for idx, pos in positions.items()}

    # Build chunks
    chunk_size = max(1, num_samples // max_workers)
    chunks: list[tuple[int, int]] = []
    start = 0
    while start < num_samples:
        end = min(start + chunk_size, num_samples)
        chunks.append((start, end))
        start = end

    args_list = [
        _LinkCacheChunkArgs(
            start_idx=s,
            end_idx=e,
            endpoint_data=tuple(endpoint_data),
            sat_positions=all_sat_positions,
            max_ground_range_m=constraints.max_ground_range_m,
            max_isl_range_m=constraints.max_isl_range_m,
        )
        for s, e in chunks
    ]

    try:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            chunk_results = list(executor.map(_build_link_cache_chunk, args_list))
    except Exception as exc:
        raise ParallelExecutionError(f"Process pool link cache failed: {exc}") from exc

    # Assemble records
    records: list[LinkRecord] = []
    summary = {
        "num_samples": num_samples,
        "ground_link_records": 0,
        "isl_link_records": 0,
        "per_sample_ground_counts": [0] * num_samples,
        "per_sample_isl_counts": [0] * num_samples,
    }

    for chunk in chunk_results:
        for link_type, sidx, node_a, node_b, distance_m in chunk:
            records.append(
                LinkRecord(
                    sample_index=sidx,
                    node_a=node_a,
                    node_b=node_b,
                    distance_m=distance_m,
                    link_type=link_type,
                )
            )
            if link_type == "ground":
                summary["ground_link_records"] += 1
                summary["per_sample_ground_counts"][sidx] += 1
            else:
                summary["isl_link_records"] += 1
                summary["per_sample_isl_counts"][sidx] += 1

    summary["total_records"] = len(records)
    summary["per_sample_total_counts"] = [
        summary["per_sample_ground_counts"][s] + summary["per_sample_isl_counts"][s]
        for s in range(num_samples)
    ]

    return tuple(records), summary
