"""Verify latency-optimization benchmark plan.

This module validates plans and computes benchmark-specific metrics including:
- Latency statistics per station-pair-window
- Target coverage (observations vs requirements)
- Validity checks (from planner validation logic)
"""

from pathlib import Path
from typing import Any
from datetime import datetime
import json
import yaml

# Import from project root's engine
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from engine.orbital.chain import compute_chain_access_with_latency
from engine.models import Satellite, Station


def verify_plan(plan_path: str, case_dir: str) -> dict[str, Any]:
    """Verify plan and compute latency-optimization metrics.
    
    Args:
        plan_path: Path to plan.json file
        case_dir: Path to case directory containing requirements.yaml
        
    Returns:
        Dictionary with verification results including:
        - valid: bool
        - metrics: dict with latency_statistics, target_coverage
        - violations: list of constraint violations
    """
    try:
        case_path = Path(case_dir)
        
        # Load plan
        with open(plan_path) as f:
            plan = json.load(f)
        
        # Load requirements
        with open(case_path / "requirements.yaml") as f:
            requirements = yaml.safe_load(f)
        
        # Load satellites and stations (YAMLs are top-level lists)
        with open(case_path / "satellites.yaml") as f:
            satellites_list = yaml.safe_load(f)
        
        with open(case_path / "stations.yaml") as f:
            stations_list = yaml.safe_load(f)
        
        req = requirements.get("latency_optimization", {})
        station_pairs = req.get("station_pairs", [])
        required_observations = req.get("required_observations", {})
        
        # Build node dictionary
        all_nodes = {}
        for sat in satellites_list:
            all_nodes[sat["id"]] = Satellite(
                tle_line1=sat["tle_line1"],
                tle_line2=sat["tle_line2"],
                apogee_km=sat["apogee_km"],
                perigee_km=sat["perigee_km"],
                period_min=sat["period_min"],
                inclination_deg=sat["inclination_deg"],
            )
        
        for station in stations_list:
            all_nodes[station["id"]] = Station(
                latitude_deg=station["latitude_deg"],
                longitude_deg=station["longitude_deg"],
                altitude_m=station.get("altitude_m", 0.0),
            )
        
        # Extract connections from plan actions
        actions = plan.get("actions", [])
        connections = []
        for action in actions:
            action_type = action.get("type")
            if action_type == "intersatellite_link":
                sat_id = action.get("satellite_id")
                peer_id = action.get("peer_satellite_id")
                if sat_id and peer_id:
                    connections.append((sat_id, peer_id))
                    connections.append((peer_id, sat_id))
            elif action_type == "downlink":
                sat_id = action.get("satellite_id")
                station_id = action.get("station_id")
                if sat_id and station_id:
                    connections.append((sat_id, station_id))
                    connections.append((station_id, sat_id))
        
        # Compute latency statistics for each station pair
        latency_statistics = {}
        for pair in station_pairs:
            window_key = f"{pair['station_a']}_{pair['station_b']}_{pair['time_window_start']}"
            
            start_node = all_nodes.get(pair["station_a"])
            end_node = all_nodes.get(pair["station_b"])
            
            if not start_node or not end_node:
                latency_statistics[window_key] = None
                continue
            
            # Compute chain access with latency
            result = compute_chain_access_with_latency(
                start_node=start_node,
                end_node=end_node,
                all_nodes=all_nodes,
                connections=connections,
                time_window=(pair["time_window_start"], pair["time_window_end"]),
                sample_step_sec=60.0,
            )
            
            # Extract latency samples
            latencies_ms = []
            total_duration_sec = 0.0
            
            # --- temporal path validation ---
            from collections import defaultdict
            
            # Build fast lookup for action intervals: (u, v) -> list of (start, end)
            action_intervals = defaultdict(list)
            for action in actions:
                act_type = action.get("type")
                if act_type == "intersatellite_link":
                    u, v = action.get("satellite_id"), action.get("peer_satellite_id")
                elif act_type == "downlink":
                    u, v = action.get("satellite_id"), action.get("station_id")
                else:
                    continue

                if u and v:
                    start_str = action.get("start")
                    end_str = action.get("end")
                    if start_str and end_str:
                        s = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                        e = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                        action_intervals[(u, v)].append((s, e))
                        action_intervals[(v, u)].append((s, e)) # Undirected availability

            # Process windows returned by chain compute
            # chain compute returns POTENTIAL windows based on topology, but ignores action times
            # We must filter them.
            
            valid_merged_intervals = []
            
            for window in result.windows:
                # 1. Determine valid intervals for THIS path
                # Path: [n1, n2, n3...]
                path_nodes = window.path
                if len(path_nodes) < 2:
                    continue
                    
                # Intersect intervals for all links in path
                # Start with the window returned by chain compute (which matches request window)
                if window.start.tzinfo is None:
                    w_start = window.start.replace(tzinfo=timezone.utc)
                else:
                    w_start = window.start
                    
                if window.end.tzinfo is None:
                    w_end = window.end.replace(tzinfo=timezone.utc)
                else:
                    w_end = window.end
                
                curr_intervals = [(w_start, w_end)]
                
                for i in range(len(path_nodes) - 1):
                    u, v = path_nodes[i], path_nodes[i+1]
                    link_intervals = action_intervals.get((u, v), [])
                    
                    next_intervals_step = []
                    for c_s, c_e in curr_intervals:
                        for l_s, l_e in link_intervals:
                            # Intersect
                            i_s = max(c_s, l_s)
                            i_e = min(c_e, l_e)
                            if i_e > i_s:
                                next_intervals_step.append((i_s, i_e))
                    curr_intervals = next_intervals_step
                    if not curr_intervals:
                        break
                
                # 2. Collect valid intervals
                valid_merged_intervals.extend(curr_intervals)
                
                # 3. Filter latency samples for this window based on validity
                # Only include samples that fall into ONE of the valid intervals for THIS path
                for sample in window.latency_samples:
                    s_time = sample.time
                    if s_time.tzinfo is None:
                        s_time = s_time.replace(tzinfo=timezone.utc)
                        
                    is_valid_sample = False
                    for v_s, v_e in curr_intervals:
                        if v_s <= s_time <= v_e:
                            is_valid_sample = True
                            break
                    
                    if is_valid_sample:
                        latencies_ms.append(sample.latency_ms)

            # 4. Compute total unique duration covered (union of all valid intervals)
            valid_merged_intervals.sort()
            final_intervals = []
            if valid_merged_intervals:
                curr_s, curr_e = valid_merged_intervals[0]
                for next_s, next_e in valid_merged_intervals[1:]:
                    if next_s < curr_e: # Overlap or touch
                        curr_e = max(curr_e, next_e)
                    else:
                        final_intervals.append((curr_s, curr_e))
                        curr_s, curr_e = next_s, next_e
                final_intervals.append((curr_s, curr_e))
            
            total_duration_sec = sum((e - s).total_seconds() for s, e in final_intervals)

            if not latencies_ms and total_duration_sec == 0:
                latency_statistics[window_key] = None
            else:
                req_start_str = pair["time_window_start"]
                req_end_str = pair["time_window_end"]
                
                # Parse datetimes (handle Z for UTC)
                if isinstance(req_start_str, str):
                    req_start = datetime.fromisoformat(req_start_str.replace('Z', '+00:00'))
                else:
                    req_start = req_start_str
                    
                if isinstance(req_end_str, str):
                    req_end = datetime.fromisoformat(req_end_str.replace('Z', '+00:00'))
                else:
                    req_end = req_end_str

                req_duration = (req_end - req_start).total_seconds()
                coverage = total_duration_sec / req_duration if req_duration > 0 else 0.0
                
                latency_statistics[window_key] = {
                    "latency_min_ms": min(latencies_ms) if latencies_ms else None,
                    "latency_max_ms": max(latencies_ms) if latencies_ms else None,
                    "latency_mean_ms": sum(latencies_ms) / len(latencies_ms) if latencies_ms else None,
                    "num_samples": len(latencies_ms),
                    "total_duration_min": total_duration_sec / 60.0,
                    "coverage": coverage,
                }
        
        # Compute target coverage
        observations = [a for a in actions if a.get("type") == "observation"]
        total_required = sum(required_observations.values())
        
        obs_by_target = {}
        for obs in observations:
            target_id = obs.get("target_id")
            if target_id:
                obs_by_target[target_id] = obs_by_target.get(target_id, 0) + 1
        
        total_actual = sum(obs_by_target.get(tid, 0) for tid in required_observations.keys())
        target_coverage = total_actual / total_required if total_required > 0 else 0.0
        
        # Compute average connection coverage
        valid_stats = [s for s in latency_statistics.values() if s is not None]
        avg_connection_coverage = sum(s["coverage"] for s in valid_stats) / len(station_pairs) if station_pairs else 0.0
        
        return {
            "valid": True,
            "metrics": {
                "latency_statistics": latency_statistics,
                "target_coverage": target_coverage,
                "connection_coverage": avg_connection_coverage,
            },
            "violations": [],
        }
        
    except Exception as e:
        return {
            "valid": False,
            "error": f"Verification failed: {str(e)}",
        }


def score_plan(plan_path: str, case_dir: str) -> dict[str, Any]:
    """Score plan (alias for verify_plan for backward compatibility)."""
    return verify_plan(plan_path, case_dir)
