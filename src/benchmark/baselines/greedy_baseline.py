"""Greedy baseline scheduler.

Purpose: Heuristic-based greedy optimization without backtracking.
Strategy: Score windows with benchmark-specific heuristics, stage best first.

Per user feedback: Filter to a small candidate group before scoring to avoid
scoring every window (which is expensive even with cheap heuristics).
"""

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, List, Dict, Any, Callable
from datetime import datetime

from .base import BaselineResult, load_scenario, window_to_action_dict, try_stage_action, compute_windows
from planner.models import PlannerAccessWindow

if TYPE_CHECKING:
    from planner.scenario import Scenario

logger = logging.getLogger(__name__)


MAX_CANDIDATES_PER_ROUND = 200


def run(
    case_path: Path,
    output_path: Path,
    timeout: int = 300,
    benchmark_type: str = "revisit_optimization",
    max_candidates_per_round: int = MAX_CANDIDATES_PER_ROUND,
) -> BaselineResult:
    """Run greedy baseline algorithm.

    Args:
        case_path: Path to case directory
        output_path: Path to save plan.json
        timeout: Maximum execution time in seconds
        benchmark_type: Type of benchmark (determines heuristic)
        max_candidates_per_round: Maximum candidates to score per round

    Returns:
        BaselineResult with success status, elapsed time, and action count
    """
    start_time = time.time()
    logger.info(f"Starting greedy baseline: benchmark={benchmark_type}, max_candidates={max_candidates_per_round}")

    try:
        scenario = load_scenario(case_path)
        windows = compute_windows(scenario, benchmark_type, case_path)
        logger.info(f"Computed {len(windows)} windows")

        heuristic = _get_heuristic(benchmark_type)
        state = _init_state(benchmark_type, scenario)

        used_window_ids = set()
        staged_count = 0
        round_num = 0

        while time.time() - start_time < timeout:
            available = [w for w in windows if w.window_id not in used_window_ids]
            if not available:
                logger.info(f"No more available windows after {round_num} rounds")
                break

            candidates = _filter_candidates(available, state, benchmark_type, max_candidates_per_round)
            if not candidates:
                logger.info(f"No more candidates after {round_num} rounds")
                break

            scored = [(w, heuristic(w, state, scenario)) for w in candidates]
            scored.sort(key=lambda x: x[1], reverse=True)

            staged_any = False
            for window, score in scored:
                if score <= 0:
                    break

                used_window_ids.add(window.window_id)
                use_middle = 5.0 if window.target_id or window.strip_id else None
                action_dict = window_to_action_dict(window, use_middle_minutes=use_middle)

                if try_stage_action(scenario, action_dict):
                    staged_count += 1
                    _update_state(state, window, benchmark_type)
                    staged_any = True
                    break

            if not staged_any:
                for window, _ in scored:
                    used_window_ids.add(window.window_id)
                if not scored:
                    break

            round_num += 1
            if round_num % 10 == 0:
                logger.debug(f"Round {round_num}: staged {staged_count} actions so far")

        result = scenario.commit_plan(str(output_path))
        logger.info(f"Completed: staged={staged_count}, valid={result.valid}, rounds={round_num}, elapsed={time.time()-start_time:.2f}s")

        return BaselineResult(
            success=result.valid,
            elapsed_seconds=time.time() - start_time,
            actions_count=staged_count,
        )
        
    except Exception as e:
        logger.error(f"Greedy baseline failed: {e}", exc_info=True)
        return BaselineResult(
            success=False,
            elapsed_seconds=time.time() - start_time,
            actions_count=0,
            error=str(e),
        )


def _get_heuristic(benchmark_type: str) -> Callable:
    """Get benchmark-specific heuristic function."""
    heuristics = {
        "revisit_optimization": _heuristic_revisit,
        "stereo_imaging": _heuristic_stereo,
        "latency_optimization": _heuristic_latency,
        "regional_coverage": _heuristic_regional,
    }
    return heuristics[benchmark_type]


def _init_state(benchmark_type: str, scenario: "Scenario") -> Dict[str, Any]:
    """Initialize heuristic state for the benchmark."""
    if benchmark_type == "revisit_optimization":
        return {
            "last_obs_time": {},
            "horizon_start": scenario.horizon_start,
            "horizon_end": scenario.horizon_end,
        }
    elif benchmark_type == "stereo_imaging":
        return {
            "obs_azimuths": {},
        }
    elif benchmark_type == "latency_optimization":
        return {
            "connected_sats": set(),
            "connected_stations": set(),
        }
    elif benchmark_type == "regional_coverage":
        return {
            "covered_strips": set(),
        }
    return {}


def _filter_candidates(
    windows: List[PlannerAccessWindow],
    state: Dict[str, Any],
    benchmark_type: str,
    max_candidates: int,
) -> List[PlannerAccessWindow]:
    """Filter to a small candidate group before scoring."""
    if benchmark_type == "revisit_optimization":
        targets_with_no_obs = [
            w for w in windows
            if w.target_id and w.target_id not in state["last_obs_time"]
        ]
        if targets_with_no_obs:
            return targets_with_no_obs[:max_candidates]

        obs_windows = [w for w in windows if w.target_id]
        dl_windows = [w for w in windows if w.station_id]
        return obs_windows[:max_candidates // 2] + dl_windows[:max_candidates // 2]

    elif benchmark_type == "stereo_imaging":
        targets_with_one_obs = [
            w for w in windows
            if w.target_id and len(state["obs_azimuths"].get(w.target_id, [])) == 1
        ]
        if targets_with_one_obs:
            return targets_with_one_obs[:max_candidates]

        targets_with_no_obs = [w for w in windows if w.target_id and w.target_id not in state["obs_azimuths"]]
        return targets_with_no_obs[:max_candidates]

    elif benchmark_type == "latency_optimization":
        isl_windows = [w for w in windows if w.peer_satellite_id]
        dl_windows = [w for w in windows if w.station_id]
        return isl_windows[:max_candidates // 2] + dl_windows[:max_candidates // 2]

    elif benchmark_type == "regional_coverage":
        uncovered = [w for w in windows if w.strip_id and w.strip_id not in state["covered_strips"]]
        if uncovered:
            return uncovered[:max_candidates]
        dl_windows = [w for w in windows if w.station_id]
        return dl_windows[:max_candidates]

    return windows[:max_candidates]


def _update_state(state: Dict[str, Any], window: PlannerAccessWindow, benchmark_type: str):
    """Update heuristic state after staging a window."""
    if benchmark_type == "revisit_optimization":
        if window.target_id:
            state["last_obs_time"][window.target_id] = window.start
    elif benchmark_type == "stereo_imaging":
        if window.target_id:
            if window.target_id not in state["obs_azimuths"]:
                state["obs_azimuths"][window.target_id] = []
            if window.max_elevation_point:
                state["obs_azimuths"][window.target_id].append(window.max_elevation_point.azimuth_deg)
    elif benchmark_type == "latency_optimization":
        if window.peer_satellite_id:
            state["connected_sats"].add(window.satellite_id)
            state["connected_sats"].add(window.peer_satellite_id)
        if window.station_id:
            state["connected_stations"].add(window.station_id)
    elif benchmark_type == "regional_coverage":
        if window.strip_id:
            state["covered_strips"].add(window.strip_id)


def _heuristic_revisit(window: PlannerAccessWindow, state: Dict[str, Any], scenario: "Scenario") -> float:
    """Prioritize targets with largest current observation gap."""
    if window.station_id:
        return 0.5
    
    if not window.target_id:
        return 0.0
    
    target_id = window.target_id
    last_time = state["last_obs_time"].get(target_id, state["horizon_start"])
    gap_seconds = (window.start - last_time).total_seconds()
    
    return gap_seconds / 3600.0


def _heuristic_stereo(window: PlannerAccessWindow, state: Dict[str, Any], scenario: "Scenario") -> float:
    """Prioritize windows that complete stereo pairs."""
    if window.station_id:
        return 0.5
    
    if not window.target_id or not window.max_elevation_point:
        return 0.0
    
    target_id = window.target_id
    existing_azimuths = state["obs_azimuths"].get(target_id, [])
    
    if len(existing_azimuths) == 0:
        return 1.0
    
    if len(existing_azimuths) >= 2:
        return 0.0
    
    new_az = window.max_elevation_point.azimuth_deg
    existing_az = existing_azimuths[0]
    separation = abs(new_az - existing_az)
    if separation > 180:
        separation = 360 - separation
    
    if 15 <= separation <= 60:
        return 10.0 + separation
    return 0.1


def _heuristic_latency(window: PlannerAccessWindow, state: Dict[str, Any], scenario: "Scenario") -> float:
    """Prioritize ISL and downlink windows for connectivity."""
    if window.peer_satellite_id:
        sat_a = window.satellite_id
        sat_b = window.peer_satellite_id
        new_connections = 0
        if sat_a not in state["connected_sats"]:
            new_connections += 1
        if sat_b not in state["connected_sats"]:
            new_connections += 1
        return 1.0 + new_connections * 2.0
    
    if window.station_id:
        if window.station_id not in state["connected_stations"]:
            return 5.0
        return 1.0
    
    return 0.0


def _heuristic_regional(window: PlannerAccessWindow, state: Dict[str, Any], scenario: "Scenario") -> float:
    """Prioritize uncovered strips."""
    if window.station_id:
        return 0.5
    
    if not window.strip_id:
        return 0.0
    
    if window.strip_id in state["covered_strips"]:
        return 0.0
    
    return 1.0 + window.duration_sec / 60.0
