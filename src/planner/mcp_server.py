"""
MCP Server for Satellite Mission Planning.

This server exposes the planner tools to an LLM agent.
It manages a persistent Scenario instance for the session, allowing the agent
to perform stateful operations (like staging actions) without managing the state object itself.

MCP Layer Responsibilities:
1. Filtering (via `filters` dict syntax)
2. Pagination (`offset`, `limit`)
3. Rounding floats
4. Null-removal
5. Dict conversion (dataclass → dict)
6. Summarization (metrics → human-readable strings)
7. Exception catching → error dict for LLM
8. dry_run simulation for stage/unstage
"""

import os
import time
import argparse
from pathlib import Path
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

from planner.scenario import Scenario
from planner.state import StateFile
from planner.models import ScenarioError, ValidationError, ConflictError, ResourceViolationError
from planner.helpers import (
    satellite_summary_key,
    satellite_filter_key,
    target_key,
    station_key,
    window_summary_key,
    window_filter_key,
    strip_key,
    action_key,
    format_plan_status,
)
from planner.helpers.mcp_helpers import to_llm_dict, paginate, filter_items, format_satellite_summary

mcp = FastMCP("Satellite Planner")

STATE_FILE: StateFile | None = None
CATALOGS: Dict[str, str] = {}


def _auto_initialize(case_path: str | None = None):
    """Initialize state path and catalogs from environment or argument."""
    global STATE_FILE, CATALOGS
    
    if case_path is None:
        case_path = os.environ.get("CASE_PATH") or os.environ.get("ASTROX_CASE_PATH")
    
    if case_path is None:
        # Fallback to current directory if absolutely nothing provided
        base_dir = Path(".")
    else:
        base_dir = Path(case_path)
    
    state_path = os.environ.get("ASTROX_STATE_PATH", str(Path.home() / "state" / "scenario.json"))
    
    CATALOGS = {
        "satellite_file": str(base_dir / "satellites.yaml"),
        "target_file": str(base_dir / "targets.yaml"),
        "station_file": str(base_dir / "stations.yaml"),
        "plan_file": str(base_dir / "initial_plan.json"),
    }
    
    STATE_FILE = StateFile(state_path)


def _load_scenario() -> Scenario:
    """Load scenario from state file with fallback to raw catalogs."""
    state_dict = STATE_FILE.read()
    if state_dict:
        return Scenario.from_state(**CATALOGS, state_dict=state_dict)
    else:
        return Scenario(**CATALOGS)


def _save_scenario(scenario: Scenario):
    """Save scenario to state file."""
    STATE_FILE.write(scenario.export_to_state())





@mcp.tool()
def query_satellites(filters: Dict[str, Any], offset: int = 0, limit: int = 10) -> List[Dict[str, Any]] | Dict[str, Any]:
    """
    Get available satellites (paged).

    Record fields (summarized for token efficiency):
        - id, name, constellation, owner, tle_epoch
        - orbit: "apogee x perigee @ inclination"
        - storage: "capacity, obs_rate, dl_rate"
        - power: "capacity, charge, idle"
        - wheel: "max_rate, accel"
        - num_terminal

    Args:
        filters: Dictionary of filters. Examples:
            - {"name": {"fuzzy": "skycity", "min_ratio": 0.6}}
            - {"inclination_deg": {"gte": 50, "lt": 55}}
            - {} returns all satellites. (recommended)
        offset: Start index (default 0).
        limit: Max records (default 10).
    """
    try:
        with STATE_FILE.lock(exclusive=False):
            scenario = _load_scenario()
            all_sats = scenario.query_satellites()
        filtered = filter_items(all_sats, filters, satellite_filter_key)
        paged = paginate(filtered, offset, limit)
        results = [satellite_summary_key(s) for s in paged]
        
        if len(filtered) > offset + len(results):
            return {
                "satellites": results,
                "warning": f"Only first {len(results)} elements are returned (offset {offset}). {len(filtered)} total matches found."
            }
        return results
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def query_targets(filters: Dict[str, Any], offset: int = 0, limit: int = 10) -> List[Dict[str, Any]] | Dict[str, Any]:
    """
    Get available target locations (paged).

    Record fields:
        - id, name, country
        - latitude_deg, longitude_deg, altitude_m

    Args:
        filters: Dictionary of filters. Examples:
            - {"name": {"contains": "city", "ignore_case": True}}
            - {"latitude_deg": {"gt": 0.0}, "longitude_deg": {"lt": 0.0}}
            - {} returns all targets. (recommended)
        offset: Start index (default 0).
        limit: Max records (default 10).
    """
    try:
        with STATE_FILE.lock(exclusive=False):
            scenario = _load_scenario()
            all_targets = scenario.query_targets()
        filtered = filter_items(all_targets, filters, target_key)
        paged = paginate(filtered, offset, limit)
        results = [to_llm_dict(t) for t in paged]

        if len(filtered) > offset + len(results):
            return {
                "targets": results,
                "warning": f"Only first {len(results)} elements are returned (offset {offset}). {len(filtered)} total matches found."
            }
        return results
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def query_stations(filters: Dict[str, Any], offset: int = 0, limit: int = 10) -> List[Dict[str, Any]] | Dict[str, Any]:
    """
    Get available ground stations (paged).

    Record fields:
        - id, name, network_name
        - latitude_deg, longitude_deg, altitude_m

    Args:
        filters: Dictionary of filters. Examples:
            - {"network_name": {"contains": "nasa", "ignore_case": True}}
            - {} returns all stations. (recommended)
        offset: Start index (default 0).
        limit: Max records (default 10).
    """
    try:
        with STATE_FILE.lock(exclusive=False):
            scenario = _load_scenario()
            all_stations = scenario.query_stations()
        filtered = filter_items(all_stations, filters, station_key)
        paged = paginate(filtered, offset, limit)
        results = [to_llm_dict(s) for s in paged]

        if len(filtered) > offset + len(results):
            return {
                "stations": results,
                "warning": f"Only first {len(results)} elements are returned (offset {offset}). {len(filtered)} total matches found."
            }
        return results
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def register_strips(strips: List[Dict[str, Any]]) -> List[Dict[str, Any]] | Dict[str, str]:
    """
    Register strip targets (polylines) for mosaic missions.

    Args:
        strips: List of strip definitions. Each must have:
            - id: Unique identifier
            - name: Human-readable name (optional, defaults to id)
            - points: List of [lat, lon] coordinate pairs
    """
    try:
        with STATE_FILE.lock(exclusive=True):
            scenario = _load_scenario()
            registered = scenario.register_strips(strips)
            _save_scenario(scenario)
        return [strip_key(s) for s in registered]
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def unregister_strips(strip_ids: List[str]) -> Dict[str, Any]:
    """
    Remove strip targets from the scenario.

    Args:
        strip_ids: List of strip IDs to remove.
    """
    try:
        with STATE_FILE.lock(exclusive=True):
            scenario = _load_scenario()
            scenario.unregister_strips(strip_ids)
            _save_scenario(scenario)
        return {"status": "success", "removed": strip_ids}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def query_strips(offset: int = 0, limit: int = 10) -> List[Dict[str, Any]] | Dict[str, Any]:
    """
    Get registered strip targets (paged).

    Record fields:
        - id, name, points_count

    Args:
        offset: Start index (default 0).
        limit: Max records (default 10).
    """
    try:
        with STATE_FILE.lock(exclusive=False):
            scenario = _load_scenario()
            all_strips = scenario.query_strips()
        paged = paginate(all_strips, offset, limit)
        results = [strip_key(s) for s in paged]

        if len(all_strips) > offset + len(results):
            return {
                "strips": results,
                "warning": f"Only first {len(results)} elements are returned (offset {offset}). {len(all_strips)} total strips found."
            }
        return results
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def compute_strip_windows(
    sat_ids: List[str],
    strip_ids: List[str],
    start_time: str,
    end_time: str,
    constraints: List[Dict[str, Any]] | None = None,
    offset: int = 0,
    limit: int = 10,
) -> List[Dict[str, Any]] | Dict[str, str]:
    """
    Compute visibility windows for strip targets.

    Windows are automatically registered for later use with stage_action.

    Note: To avoid excessive computation, this tool supports either multiple satellites 
    for a single strip, OR multiple strips for a single satellite. If both lists 
    contain multiple elements, only the first strip will be processed.

    Args:
        sat_ids: List of satellite IDs.
        strip_ids: List of strip IDs (must be registered first).
        start_time: Start time ISO format.
        end_time: End time ISO format.
        constraints: Optional list of constraint dicts.
        offset: Start index (default 0).
        limit: Max records (default 10; **capped at 20**).
    """
    try:
        warning = None
        if len(sat_ids) > 1 and len(strip_ids) > 1:
            warning = f"Multiple satellites ({len(sat_ids)}) and multiple strips ({len(strip_ids)}) provided. Only the first strip '{strip_ids[0]}' will be used to avoid excessive computation."
            strip_ids = [strip_ids[0]]

        with STATE_FILE.lock(exclusive=True):
            scenario = _load_scenario()
            windows = scenario.compute_strip_windows(
                sat_ids, strip_ids, start_time, end_time, constraints=constraints
            )
            registered = scenario.register_windows(windows)
            _save_scenario(scenario)

        limit = min(limit, 20)
        paged = paginate(registered, offset, limit)
        window_dicts = [window_summary_key(w) for w in paged]

        # Combine warnings if both truncation and sat/strip constraints apply
        warnings = []
        if warning:
            warnings.append(warning)
        if len(registered) > offset + len(window_dicts):
            warnings.append(f"Only first {len(window_dicts)} elements are returned (offset {offset}). {len(registered)} total windows computed.")

        if warnings:
            return {
                "warning": " | ".join(warnings),
                "windows": window_dicts
            }

        return window_dicts
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def query_windows(filters: Dict[str, Any], offset: int = 0, limit: int = 10) -> List[Dict[str, Any]] | Dict[str, Any]:
    """
    Query already registered access windows (paged).

    Record fields:
        - window_id, satellite_id, target_id, station_id, counterpart_kind
        - start, end, duration_sec
        - best: summary string with elevation/range info

    Args:
        filters: Dictionary of filters. Examples:
            - {"satellite_id": "sat_noaa_16"}
            - {"duration_sec": {"gte": 300}}
            - {"best_elevation_deg": {"gt": 30}}
            - {} returns all windows.
        offset: Start index (default 0).
        limit: Max records (default 10; **capped at 20**).
    """
    try:
        with STATE_FILE.lock(exclusive=False):
            scenario = _load_scenario()
            all_windows = scenario.query_windows()

        from planner.helpers import record_matches_filters
        filter_dicts = [window_filter_key(w) for w in all_windows]
        if filters:
            indices = [i for i, d in enumerate(filter_dicts) if record_matches_filters(d, filters)]
            filtered_windows = [all_windows[i] for i in indices]
        else:
            filtered_windows = all_windows

        limit = min(limit, 20)
        paged = paginate(filtered_windows, offset, limit)
        results = [window_summary_key(w) for w in paged]

        if len(filtered_windows) > offset + len(results):
            return {
                "windows": results,
                "warning": f"Only first {len(results)} elements are returned (offset {offset}). {len(filtered_windows)} total matches found."
            }
        return results
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def query_actions(filters: Dict[str, Any], offset: int = 0, limit: int = 10) -> List[Dict[str, Any]] | Dict[str, Any]:
    """
    Query staged actions (paged).

    Record fields:
        - action_id, type, satellite_id, target_id, station_id
        - start, end, duration_sec

    Args:
        filters: Dictionary of filters. Examples:
            - {"satellite_id": "sat_yaogan-29_deb"}
            - {"type": "observation"}
            - {} returns all staged actions.
        offset: Start index (default 0).
        limit: Max records (default 10; **capped at 20**).
    """
    try:
        with STATE_FILE.lock(exclusive=False):
            scenario = _load_scenario()
            all_actions = scenario.query_actions()
        action_dicts = [action_key(a) for a in all_actions]

        from planner.helpers import record_matches_filters
        if filters:
            filtered_dicts = [d for d in action_dicts if record_matches_filters(d, filters)]
        else:
            filtered_dicts = action_dicts

        limit = min(limit, 20)
        paged = paginate(filtered_dicts, offset, limit)
        results = [to_llm_dict(d) for d in paged]

        if len(filtered_dicts) > offset + len(results):
            return {
                "actions": results,
                "warning": f"Only first {len(results)} elements are returned (offset {offset}). {len(filtered_dicts)} total matches found."
            }
        return results
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def compute_lighting_windows(
    sat_ids: List[str],
    start_time: str,
    end_time: str,
    offset: int = 0,
    limit: int = 10,
) -> List[Dict[str, Any]] | Dict[str, Any]:
    """
    Compute lighting windows (sunlight/umbra/penumbra) for satellites.

    Args:
        sat_ids: List of satellite IDs.
        start_time: Start time ISO string.
        end_time: End time ISO string.
        offset: Start index (default 0).
        limit: Max records (default 10; **capped at 20**).
    """
    try:
        with STATE_FILE.lock(exclusive=False):
            scenario = _load_scenario()
            windows = scenario.compute_lighting_windows(sat_ids, start_time, end_time)
        limit = min(limit, 20)
        paged = paginate(windows, offset, limit)
        results = [to_llm_dict(w) for w in paged]

        if len(windows) > offset + len(results):
            return {
                "lighting_windows": results,
                "warning": f"Only first {len(results)} elements are returned (offset {offset}). {len(windows)} total windows computed."
            }
        return results
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_ground_track(
    satellite_id: str,
    start_time: str,
    end_time: str,
    step_sec: float = 60.0,
    filter_polygon: List[List[float]] | None = None,
    offset: int = 0,
    limit: int = 100,
) -> List[Dict[str, Any]] | Dict[str, str]:
    """
    Get satellite ground track (subsatellite points over time).
    
    IMPORTANT: To avoid filling up the context window, use one of these strategies:
    1. Query a SMALL time window (e.g., 1-2 orbits ~90-180 minutes)
    2. Use filter_polygon to limit the geographic region
    3. Increase step_sec for coarser sampling (default 60s)
    
    Even with filtering and small windows, only the first 100 points are returned by default.
    If more points exist, the response will include a "truncated" field indicating the total count.
    
    Args:
        satellite_id: ID of the satellite
        start_time: Start time ISO format
        end_time: End time ISO format
        step_sec: Time step between points in seconds (default 60.0)
        filter_polygon: Optional polygon [[lat, lon], ...] to filter points inside
        offset: Start index for pagination (default 0)
        limit: Maximum number of points to return (default 100, max 200)
        
    Returns:
        List of ground track points with fields:
            - lat: Latitude in degrees
            - lon: Longitude in degrees
            - time: ISO formatted timestamp
    """
    try:
        # Convert filter_polygon format if provided
        polygon_tuples = None
        if filter_polygon:
            polygon_tuples = [(pt[0], pt[1]) for pt in filter_polygon]
        
        with STATE_FILE.lock(exclusive=False):
            scenario = _load_scenario()
            points = scenario.get_ground_track(
                satellite_id,
                start_time,
                end_time,
                step_sec=step_sec,
                filter_polygon=polygon_tuples
            )
        
        total_count = len(points)
        
        # Cap limit to 200 to prevent context overflow
        limit = min(limit, 200)
        paged = paginate(points, offset, limit)
        
        result = [
            {
                "lat": round(p.lat, 4),
                "lon": round(p.lon, 4),
                "time": p.time.isoformat(),
            }
            for p in paged
        ]
        
        # Add pagination metadata if truncated
        if total_count > len(result):
            return {
                "points": result,
                "total_count": total_count,
                "returned_count": len(result),
                "warning": f"Showing {len(result)} of {total_count} points. Use offset/limit for more, or narrow your time window/polygon."
            }
        
        return result
    except Exception as e:
        return {"error": str(e)}



@mcp.tool()
def evaluate_comms_latency(
    source_station_id: str,
    dest_station_id: str,
    start_time: str,
    end_time: str,
    sample_step_sec: float = 60.0,
) -> Dict[str, Any]:
    """
    Evaluate signal latency for communication between two ground stations.
    
    Builds a dynamic topology from staged ISL and downlink actions, then computes
    chain access and signal propagation latency (distance / speed of light).
    
    The topology is time-varying: connections only exist when corresponding actions
    are active. The function computes separate chain access windows for each
    topology interval.
    
    Args:
        source_station_id: ID of source ground station
        dest_station_id: ID of destination ground station
        start_time: Start time ISO format
        end_time: End time ISO format
        sample_step_sec: Sampling interval for latency calculation (default 60s)
        
    Returns:
        Dictionary with:
            - window_count: Total number of communication windows found
            - total_duration_minutes: Total minutes of established connectivity
            - windows: List of window summaries with path and latency statistics
    """
    try:
        with STATE_FILE.lock(exclusive=False):
            scenario = _load_scenario()
            result = scenario.evaluate_comms_latency(
                source_station_id,
                dest_station_id,
                start_time,
                end_time,
                sample_step_sec,
            )
        
        # Format windows for LLM-friendly output
        formatted_windows = []
        total_established_sec = 0.0
        
        for window in result.windows:
            total_established_sec += window.duration_sec
            latencies = [s.latency_ms for s in window.latency_samples]
            if not latencies:
                # Should not happen given we assume visibility now, but safe fallback
                formatted_windows.append({
                    "path": " > ".join(window.path),
                    "start": window.start.isoformat(),
                    "end": window.end.isoformat(),
                    "duration_sec": round(window.duration_sec, 1),
                    "latency_min_ms": None,
                    "latency_max_ms": None,
                    "latency_mean_ms": None,
                    "sample_count": 0,
                })
                continue
                
            formatted_windows.append({
                "path": " > ".join(window.path),
                "start": window.start.isoformat(),
                "end": window.end.isoformat(),
                "duration_sec": round(window.duration_sec, 1),
                "latency_min_ms": round(min(latencies), 2),
                "latency_max_ms": round(max(latencies), 2),
                "latency_mean_ms": round(sum(latencies) / len(latencies), 2),
                "sample_count": len(latencies),
            })
        
        return {
            "window_count": len(formatted_windows),
            "total_duration_minutes": round(total_established_sec / 60.0, 2),
            "windows": formatted_windows,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def compute_access_windows(
    sat_ids: List[str],
    target_ids: List[str] | None,
    station_ids: List[str] | None,
    peer_satellite_ids: List[str] | None,
    start_time: str,
    end_time: str,
    constraints: List[Dict[str, Any]] | None = None,
    offset: int = 0,
    limit: int = 10,
) -> List[Dict[str, Any]] | Dict[str, Any]:
    """
    Compute visibility windows between satellites and targets/stations/satellites.

    Windows are automatically registered for later use with stage_action.

    Args:
        sat_ids: List of satellite IDs.
        target_ids: List of target IDs (optional).
        station_ids: List of station IDs (optional).
        peer_satellite_ids: List of peer satellite IDs for ISL windows (optional).
        start_time: Start time ISO format.
        end_time: End time ISO format.
        constraints: Optional list of constraint dicts.
        offset: Start index (default 0).
        limit: Max records (default 10; **capped at 20**).
    """
    try:
        with STATE_FILE.lock(exclusive=True):
            scenario = _load_scenario()
            windows = scenario.compute_access_windows(
                sat_ids, target_ids, station_ids, peer_satellite_ids,
                start_time, end_time, constraints=constraints
            )
            registered = scenario.register_windows(windows)
            _save_scenario(scenario)

        limit = min(limit, 20)
        paged = paginate(registered, offset, limit)
        results = [window_summary_key(w) for w in paged]

        if len(registered) > offset + len(results):
            return {
                "windows": results,
                "warning": f"Only first {len(results)} elements are returned (offset {offset}). {len(registered)} total windows computed."
            }
        return results
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_plan_status() -> Dict[str, Any]:
    """
    Inspect the current state of the plan.

    Returns:
        - action_count, total_observations, total_downlinks
        - staged_actions: List of action summaries
        - satellites: List of satellite status summaries (power/storage status)
        - horizon: The planning horizon time range
    """
    try:
        with STATE_FILE.lock(exclusive=False):
            scenario = _load_scenario()
            status = scenario.get_plan_status()
            horizon_start, horizon_end = scenario.horizon_start, scenario.horizon_end
        return to_llm_dict(format_plan_status(status, horizon_start, horizon_end))
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def stage_action(action: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    """
    Stage an action to the plan.

    Args:
        action: The action details. Must include:
            - type: "observation", "downlink", or "intersatellite_link"
            - satellite_id: ID of the satellite
            - target_id: ID of the target (for observation)
            - station_id: ID of the station (for downlink)
            - peer_satellite_id: ID of peer satellite (for intersatellite_link)
            - window_id OR (start_time and end_time)
        
        IMPORTANT: All link types (downlink, intersatellite_link) are bidirectional.
        Data can flow in both directions once the link is established.

        dry_run: If True, simulates and returns projected status.
                 If False, actually stages the action.
    """
    try:
        with STATE_FILE.lock(exclusive=not dry_run):
            scenario = _load_scenario()
            if dry_run:
                # Need horizon for status formatting
                h_start, h_end = scenario.horizon_start, scenario.horizon_end
                result = scenario.stage_action(action)
                status = scenario.get_plan_status()
                # DO NOT SAVE, just return projected
                return to_llm_dict({
                    "action_id": result.action_id,
                    "status": "feasible",
                    "projected_status": format_plan_status(status, h_start, h_end),
                })
            else:
                result = scenario.stage_action(action)
                _save_scenario(scenario)
                return to_llm_dict({
                    "action_id": result.action_id,
                    "status": "staged",
                })
    except (ValidationError, ConflictError, ResourceViolationError) as e:
        return {"feasible": False, "reason": str(e)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def unstage_action(action_id: str, dry_run: bool = False) -> Dict[str, Any]:
    """
    Remove an action from the staging area.

    Args:
        action_id: The ID of the action to remove.
        dry_run: If True, simulates and returns projected status.
                 If False, actually removes the action.
    """
    try:
        with STATE_FILE.lock(exclusive=not dry_run):
            scenario = _load_scenario()
            if action_id not in scenario.staged_actions:
                 return {"status": "error", "reason": f"Action '{action_id}' not found"}
            
            if dry_run:
                action = scenario.staged_actions[action_id]
                h_start, h_end = scenario.horizon_start, scenario.horizon_end
                # Temporarily remove for projected status
                scenario.unstage_action(action_id)
                status = scenario.get_plan_status()
                return to_llm_dict({
                    "action_id": action_id,
                    "status": "can_unstage",
                    "projected_status": format_plan_status(status, h_start, h_end),
                })
            else:
                result = scenario.unstage_action(action_id)
                _save_scenario(scenario)
                return to_llm_dict({
                    "action_id": result.action_id,
                    "status": "unstaged",
                })
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def commit_plan() -> Dict[str, Any]:
    """
    Finalize and validate the entire plan.

    Checks for conflicts across all staged actions.
    If valid, commits the plan and returns the final metrics.
    If invalid, returns the violations.
    """
    try:
        with STATE_FILE.lock(exclusive=True):
            scenario = _load_scenario()
            result = scenario.commit_plan()
            _save_scenario(scenario)

        sat_summaries = [format_satellite_summary(m) for m in result.metrics.satellites.values()]

        violations_list = []
        for v in result.violations:
            violations_list.append({
                "action_id": v.action_id,
                "type": v.violation_type,
                "message": v.message,
                "conflicting_action_ids": v.conflicting_action_ids,
            })

        return to_llm_dict({
            "valid": result.valid,
            "violations": violations_list if violations_list else None,
            "action_count": result.metrics.total_actions,
            "total_observations": result.metrics.total_observations,
            "total_downlinks": result.metrics.total_downlinks,
            "satellites": sat_summaries,
            "plan_json_path": result.plan_json_path,
        })
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def reset_plan() -> Dict[str, Any]:
    """
    Clear all staged actions and reset the plan to the initial state.
    """
    try:
        with STATE_FILE.lock(exclusive=True):
            scenario = _load_scenario()
            scenario.reset_plan()
            _save_scenario(scenario)
        return {"status": "reset", "message": "Plan reset to initial state"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def evaluate_revisit_gaps(
    target_ids: List[str],
    start_time: str | None = None,
    end_time: str | None = None,
) -> List[Dict[str, Any]] | Dict[str, str]:
    """
    Analyze revisit gaps for targets based on staged observations.
    
    Args:
        target_ids: List of target IDs to analyze.
        start_time: Analysis window start (defaults to horizon).
        end_time: Analysis window end (defaults to horizon).
        
    Returns:
        List of results with:
            - target_id: Target analyzed
            - max_gap_seconds: Largest gap between passes (or horizon edge)
            - mean_gap_seconds: Average gap duration
            - coverage_count: Number of observation passes
    """
    try:
        with STATE_FILE.lock(exclusive=False):
            scenario = _load_scenario()
            results = scenario.evaluate_revisit_gaps(target_ids, start_time, end_time)
        return [to_llm_dict(r) for r in results]
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def evaluate_stereo_coverage(
    target_ids: List[str],
    min_separation_deg: float = 10.0,
) -> List[Dict[str, Any]] | Dict[str, str]:
    """
    Check for stereo (multi-angle) coverage of targets.
    
    Args:
        target_ids: List of target IDs.
        min_separation_deg: Minimum angular separation required (default 10.0).
        
    Returns:
        List of results with:
            - target_id: Target analyzed
            - has_stereo: Boolean true/false
            - best_pair_azimuth_diff_deg: The best angular spread achieved
            - stereo_pairs: List of interacting (action_id, action_id) pairs
    """
    try:
        with STATE_FILE.lock(exclusive=False):
            scenario = _load_scenario()
            results = scenario.evaluate_stereo_coverage(target_ids, min_separation_deg)
        return [to_llm_dict(r) for r in results]
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def evaluate_polygon_coverage(
    polygon: List[List[float]],
) -> Dict[str, Any]:
    """
    Calculate coverage of a geographic polygon by mosaic strips.
    
    Args:
        polygon: List of [lat, lon] vertices.
        
    Returns:
        Dictionary with:
            - coverage_ratio: 0.0 to 1.0
            - total_area_km2: Approximate total polygon area
            - covered_area_km2: Approximate covered area
    """
    try:
        # Convert list-of-lists to list-of-tuples
        poly_tuples = [(p[0], p[1]) for p in polygon]
        with STATE_FILE.lock(exclusive=False):
            scenario = _load_scenario()
            result = scenario.evaluate_polygon_coverage(poly_tuples)
        
        result_dict = to_llm_dict(result)
        # Drop heavy grid to avoid context overflow
        result_dict.pop("coverage_grid", None)
        return result_dict
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def wait(seconds: float) -> Dict[str, Any]:
    """
    Do nothing and wait for a specified number of seconds.
    This is useful if you are waiting for a background process (like a python script) to finish.

    Args:
        seconds: The number of seconds to wait. (Capped between 0 and 120 during processing).
    """
    try:
        # Cap to (0, 120)
        actual_seconds = max(0.0, min(float(seconds), 120.0))
        time.sleep(actual_seconds)
        return {"waited": actual_seconds}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Satellite Mission Planning MCP Server")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--case-path",
        type=str,
        default=None,
        help="Path to benchmark case directory",
    )

    args = parser.parse_args()

    _auto_initialize(args.case_path)

    mcp.run(transport="stdio")
