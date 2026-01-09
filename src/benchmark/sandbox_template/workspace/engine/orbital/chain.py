"""
Chain access computation with signal latency calculation.

Wraps the Astrox ChainCompute API and adds local latency calculation
by propagating satellite positions and computing path distances.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Union

import requests

from engine.models import Satellite, Station
from engine.orbital.propagation import propagate_satellite
from engine.orbital.attitude import lla_to_eci

ASTROX_API_URL = "http://astrox.cn:8765"
SPEED_OF_LIGHT_KM_PER_SEC = 299792.458


class ChainComputeError(Exception):
    pass


@dataclass
class LatencySample:
    time: datetime
    latency_ms: float


@dataclass
class ChainWindow:
    path: List[str]
    start: datetime
    end: datetime
    duration_sec: float
    latency_samples: List[LatencySample]


@dataclass
class ChainAccessResult:
    windows: List[ChainWindow]


ChainNode = Union[Satellite, Station]


def _quantize_time(dt: datetime, step_sec: float) -> datetime:
    """
    Quantize datetime to grid boundaries for cache efficiency.
    
    Aligns time to floor of step_sec intervals from midnight UTC.
    Example: step_sec=60 means 1:45:30 -> 1:45:00
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = (dt - midnight).total_seconds()
    quantized_elapsed = (elapsed // step_sec) * step_sec
    return midnight + timedelta(seconds=quantized_elapsed)


def _generate_quantized_sample_times(
    start: datetime, end: datetime, step_sec: float
) -> List[datetime]:
    """
    Generate sample times aligned to grid boundaries.
    
    Extends range slightly to ensure full coverage of the window.
    """
    q_start = _quantize_time(start, step_sec)
    if q_start > start:
        q_start -= timedelta(seconds=step_sec)
    
    times = []
    current = q_start
    while current <= end:
        times.append(current)
        current += timedelta(seconds=step_sec)
    
    if current - timedelta(seconds=step_sec) < end:
        times.append(current)
    
    return times


def _build_chain_payload(
    start_node: ChainNode,
    end_node: ChainNode,
    all_nodes: Dict[str, ChainNode],
    connections: List[Tuple[str, str]],
    time_window: Tuple[str, str],
) -> dict:
    """Build the JSON payload for Astrox ChainCompute endpoint."""
    start_time, end_time = time_window

    all_objects = []
    for name, node in all_nodes.items():
        if isinstance(node, Satellite):
            obj = {
                "$type": "EntityPath",
                "Name": name,
                "Position": {
                    "$type": "SGP4",
                    "TLEs": [node.tle_line1, node.tle_line2],
                },
            }
        elif isinstance(node, Station):
            obj = {
                "$type": "EntityPath",
                "Name": name,
                "Position": {
                    "$type": "SitePosition",
                    "cartographicDegrees": [
                        node.longitude_deg,
                        node.latitude_deg,
                        node.altitude_m,
                    ],
                },
            }
        else:
            raise ChainComputeError(f"Unsupported node type: {type(node)}")
        all_objects.append(obj)

    start_name = None
    end_name = None
    for name, node in all_nodes.items():
        if node is start_node:
            start_name = name
        if node is end_node:
            end_name = name
    if start_name is None or end_name is None:
        raise ChainComputeError("start_node and end_node must be in all_nodes")

    conn_list = [{"FromObject": from_name, "ToObject": to_name} for from_name, to_name in connections]

    return {
        "Start": start_time,
        "Stop": end_time,
        "AllObjects": all_objects,
        "StartObject": start_name,
        "EndObject": end_name,
        "Connections": conn_list if conn_list else None,
        "UseLightTimeDelay": False,
    }


def _parse_datetime(s: str) -> datetime:
    """Parse Astrox datetime string to Python datetime with UTC timezone."""
    s_clean = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s_clean)


@dataclass
class _RawChainWindow:
    path: List[str]
    start: datetime
    end: datetime
    duration_sec: float


def compute_chain_access(
    start_node: ChainNode,
    end_node: ChainNode,
    all_nodes: Dict[str, ChainNode],
    connections: List[Tuple[str, str]],
    time_window: Tuple[str, str],
) -> List[_RawChainWindow]:
    """
    Compute chain access windows by intersecting individual link windows.
    Replaces buggy Astrox ChainCompute API with client-side logic.
    """
    from collections import defaultdict

    # Identify start/end names
    start_name = None
    end_name = None
    for name, node in all_nodes.items():
        if node is start_node:
            start_name = name
        if node is end_node:
            end_name = name
    
    if not start_name or not end_name:
        return []

    # Build Graph
    adj = defaultdict(list)
    for u, v in connections:
        adj[u].append(v)
    
    # 1. Find all simple paths (BFS/DFS)
    # Since plans are small, simple DFS is fine. We want to find THE path that connects start to end.
    paths = []
    stack = [(start_name, [start_name])]
    while stack:
        cur, path = stack.pop()
        if cur == end_name:
            paths.append(path)
            continue
        
        # Limit path depth to prevent infinite loops or excessive computation
        if len(path) > 10:
            continue
            
        for nxt in adj[cur]:
            if nxt not in path:
                stack.append((nxt, path + [nxt]))
    
    if not paths:
        return []

    results = []
    start_dt = _parse_datetime(time_window[0])
    end_dt = _parse_datetime(time_window[1])

    for path in paths:
        # User requested to assume full visibility for the chain if connected.
        # This relies on the planner having already validated the individual links.
        results.append(
            _RawChainWindow(
                path=path,
                start=start_dt,
                end=end_dt,
                duration_sec=(end_dt - start_dt).total_seconds()
            )
        )
                
    return results


def _compute_path_latency(
    path: List[str],
    all_nodes: Dict[str, ChainNode],
    start: datetime,
    end: datetime,
    step_sec: float,
    position_cache: Dict[Tuple[str, datetime], List[float]],
) -> List[LatencySample]:
    """
    Compute latency samples for a single path over a time window.

    Uses position_cache keyed by (node_name, quantized_time) to maximize hit rate.
    Positions are computed in ECI (GCRS) frame for consistency.
    """
    sample_times = _generate_quantized_sample_times(start, end, step_sec)
    if not sample_times:
        sample_times = [_quantize_time(start, step_sec)]

    node_positions: Dict[str, List[List[float]]] = {}
    for node_name in path:
        node = all_nodes[node_name]

        needed_times = [t for t in sample_times if (node_name, t) not in position_cache]
        if needed_times:
            if isinstance(node, Station):
                for t in needed_times:
                    eci_pos = lla_to_eci(node.latitude_deg, node.longitude_deg, node.altitude_m, t)
                    position_cache[(node_name, t)] = list(eci_pos)
            elif isinstance(node, Satellite):
                state_vectors = propagate_satellite(
                    node.tle_line1, node.tle_line2, needed_times, step_seconds=step_sec
                )
                for t, (pos, _) in zip(needed_times, state_vectors):
                    position_cache[(node_name, t)] = pos

        positions = [position_cache[(node_name, t)] for t in sample_times]
        node_positions[node_name] = positions

    samples = []
    for i, t in enumerate(sample_times):
        total_distance_m = 0.0
        for j in range(len(path) - 1):
            p1 = node_positions[path[j]][i]
            p2 = node_positions[path[j + 1]][i]
            distance_m = math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))
            total_distance_m += distance_m

        total_distance_km = total_distance_m / 1000.0
        latency_ms = (total_distance_km / SPEED_OF_LIGHT_KM_PER_SEC) * 1000.0
        samples.append(LatencySample(time=t, latency_ms=latency_ms))

    return samples


def compute_chain_access_with_latency(
    start_node: ChainNode,
    end_node: ChainNode,
    all_nodes: Dict[str, ChainNode],
    connections: List[Tuple[str, str]],
    time_window: Tuple[str, str],
    sample_step_sec: float = 60.0,
) -> ChainAccessResult:
    """
    Compute chain access windows with signal latency.

    For each viable communication path, samples positions at regular intervals
    and computes signal latency (distance / speed of light).

    Args:
        start_node: Source node (Station or Satellite).
        end_node: Destination node (Station or Satellite).
        all_nodes: All participating nodes, keyed by name.
        connections: Allowed links as (from_name, to_name) tuples.
        time_window: (start_time, end_time) as ISO strings.
        sample_step_sec: Time interval between latency samples.

    Returns:
        ChainAccessResult with windows containing latency time series.
    """
    raw_windows = compute_chain_access(start_node, end_node, all_nodes, connections, time_window)

    if not raw_windows:
        return ChainAccessResult(windows=[])

    position_cache: Dict[Tuple[str, datetime], List[float]] = {}

    windows = []
    for raw in raw_windows:
        latency_samples = _compute_path_latency(
            raw.path,
            all_nodes,
            raw.start,
            raw.end,
            sample_step_sec,
            position_cache,
        )
        windows.append(
            ChainWindow(
                path=raw.path,
                start=raw.start,
                end=raw.end,
                duration_sec=raw.duration_sec,
                latency_samples=latency_samples,
            )
        )

    return ChainAccessResult(windows=windows)
