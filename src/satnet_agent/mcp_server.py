"""
MCP Server for SatNet (DSN Scheduling).

This server exposes the DSN scheduling tools to an LLM agent.
State is persisted to a JSON file for synchronization with agent scripts.
"""

import os
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP

from satnet_agent.state import SatNetStateFile
from satnet_agent.scenario import SatNetScenario
from satnet_agent import (
    SatNetRequest,
    SatNetViewPeriod,
    SatNetAntennaStatus,
    SatNetTrack,
    SatNetValidationError,
    SatNetConflictError,
    SatNetNotFoundError,
)

mcp = FastMCP("SatNet DSN Scheduler")

STATE_FILE: SatNetStateFile | None = None


def _auto_initialize():
    """Initialize state file from environment variables.
    
    Uses defaults relative to $HOME for local testing:
        - SATNET_STATE_PATH: $HOME/state/scenario.json
        - SATNET_PROBLEMS_PATH: $HOME/data/problems.json
        - SATNET_MAINTENANCE_PATH: $HOME/data/maintenance.csv
    """
    global STATE_FILE

    home = os.environ.get("HOME", ".")
    
    state_path = os.environ.get("SATNET_STATE_PATH", f"{home}/state/scenario.json")
    problems_path = os.environ.get("SATNET_PROBLEMS_PATH", f"{home}/data/problems.json")
    maintenance_path = os.environ.get("SATNET_MAINTENANCE_PATH", f"{home}/data/maintenance.csv")
    week = int(os.environ.get("SATNET_WEEK", "40"))
    year = int(os.environ.get("SATNET_YEAR", "2018"))

    STATE_FILE = SatNetStateFile(state_path)

    if not STATE_FILE.exists():
        STATE_FILE.initialize(problems_path, maintenance_path, week, year)


def _load_scenario(exclusive: bool = False) -> SatNetScenario:
    """Load scenario from state file."""
    state = STATE_FILE.read()
    if state is None:
        raise RuntimeError("State not initialized")
    return SatNetScenario.from_state(state)


def _save_scenario(scenario: SatNetScenario) -> None:
    """Save scenario to state file."""
    STATE_FILE.write(scenario.to_state())


def _format_request_summary(req: SatNetRequest) -> str:
    return f"{req.request_id}: {req.remaining_hours:.1f}h remaining (min {req.min_duration_hours:.1f}h)"


def _format_view_period(vp: SatNetViewPeriod) -> Dict[str, Any]:
    return {
        "antenna": vp.antenna,
        "start_seconds": vp.start_seconds,
        "end_seconds": vp.end_seconds,
        "duration_hours": vp.duration_hours,
    }


def _format_antenna_summary(status: SatNetAntennaStatus) -> str:
    return f"{status.antenna}: {status.hours_available:.1f}h available"


def _format_track(track: SatNetTrack) -> Dict[str, Any]:
    return {
        "action_id": track.action_id,
        "request_id": track.request_id,
        "mission_id": track.mission_id,
        "antenna": track.antenna,
        "trx_on": track.trx_on,
        "trx_off": track.trx_off,
        "setup_start": track.setup_start,
        "teardown_end": track.teardown_end,
        "duration_hours": round(track.duration_hours, 3),
    }


@mcp.tool()
def list_unsatisfied_requests(
    offset: int = 0,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Get the list of requests still needing time allocation.
    This is your "to-do list" of missions needing antenna time.

    Args:
        offset: Skip this many requests (for pagination)
        limit: Return at most this many requests (default 20)

    Returns dict with:
        - total: Total number of unsatisfied requests
        - offset: Current offset
        - limit: Current limit
        - items: List of request summaries with fields:
            - request_id: Unique track ID (use this for schedule_track)
            - mission_id: Mission identifier (integer)
            - total_required_hours: Total requested communication time
            - remaining_hours: How much time still needs to be scheduled
            - min_duration_hours: Minimum acceptable track duration
            - setup_seconds: Required antenna setup time before track
            - teardown_seconds: Required antenna teardown time after track
            - summary: Human-readable summary
    """
    with STATE_FILE.lock(exclusive=False):
        scenario = _load_scenario()
        requests = scenario.list_unsatisfied_requests()
    
    total = len(requests)
    page = requests[offset:offset + limit]
    
    items = []
    for req in page:
        items.append({
            "request_id": req.request_id,
            "mission_id": req.mission_id,
            "total_required_hours": req.total_required_hours,
            "remaining_hours": req.remaining_hours,
            "min_duration_hours": req.min_duration_hours,
            "setup_seconds": req.setup_seconds,
            "teardown_seconds": req.teardown_seconds,
            "summary": _format_request_summary(req),
        })
    
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": items,
    }


@mcp.tool()
def get_antenna_status(include_blocked_ranges: bool = False) -> Dict[str, Any]:
    """
    Get availability status for all 12 DSN antennas.

    Args:
        include_blocked_ranges: If True, include detailed blocked time ranges

    Returns a map of antenna ID to status:
        DSS-14, DSS-24, DSS-25, DSS-26, DSS-34, DSS-35,
        DSS-36, DSS-43, DSS-54, DSS-55, DSS-63, DSS-65

    Each status contains:
        - hours_available: Remaining unblocked hours this week
        - summary: Human-readable summary
        - blocked_ranges: (only if include_blocked_ranges=True)
    """
    with STATE_FILE.lock(exclusive=False):
        scenario = _load_scenario()
        status = scenario.get_antenna_status()
    
    result = {}
    for antenna, s in status.items():
        entry = {
            "hours_available": s.hours_available,
            "summary": _format_antenna_summary(s),
        }
        if include_blocked_ranges:
            entry["blocked_ranges"] = s.blocked_ranges
        result[antenna] = entry
    
    return result


@mcp.tool()
def find_view_periods(
    request_id: str,
    min_duration_hours: float = 0,
    offset: int = 0,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Find available scheduling slots for a specific request.
    This is the "magic" lookup tool - it tells you WHEN you can schedule.

    Args:
        request_id: Track ID from list_unsatisfied_requests()
        min_duration_hours: Filter out slots shorter than this (default: 0)
        offset: Skip this many view periods (for pagination)
        limit: Return at most this many view periods (default 10)

    Returns dict with:
        - total: Total number of available view periods
        - offset: Current offset
        - limit: Current limit
        - items: List of available windows, sorted by duration (longest first):
            - antenna: Antenna or array (e.g., "DSS-43" or "DSS-34_DSS-35")
            - start_seconds: Start time (epoch seconds)
            - end_seconds: End time (epoch seconds)
            - duration_hours: Available duration

    NOTE: The returned windows already account for:
        - Antenna maintenance
        - Already scheduled tracks
        - Setup/teardown overhead

    To schedule, pick a window and call schedule_track with a
    [trx_on, trx_off] interval within [start_seconds, end_seconds].
    """
    with STATE_FILE.lock(exclusive=False):
        scenario = _load_scenario()
        try:
            vps = scenario.find_view_periods(request_id, min_duration_hours)
        except SatNetNotFoundError as e:
            return {"error": str(e), "status": 6523}
    
    total = len(vps)
    page = vps[offset:offset + limit]
    
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [_format_view_period(vp) for vp in page],
        "hint": f"Found {total} scheduling opportunities. Windows are sorted by duration (longest first).",
    }


@mcp.tool()
def schedule_track(
    request_id: str,
    antenna: str,
    trx_on: int,
    trx_off: int,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Commit a communication track to the schedule.

    Args:
        request_id: Track ID from list_unsatisfied_requests()
        antenna: Antenna identifier (e.g., "DSS-43" or "DSS-34_DSS-35")
        trx_on: Track start time (epoch seconds)
        trx_off: Track end time (epoch seconds)
        dry_run: If True, validate but don't actually schedule

    Returns on success:
        - action_id: Identifier for this scheduled track
        - track: Details of the scheduled track
        - status: 0 (success)
        - dry_run: Whether this was a dry run

    Returns on error:
        - error: Error message
        - status: Error code
        - suggestion: Hint for fixing the error

    IMPORTANT: The system automatically reserves setup time BEFORE trx_on
    and teardown time AFTER trx_off. Ensure the full interval
    [trx_on - setup, trx_off + teardown] fits within a view period
    and doesn't overlap with maintenance or other tracks.
    """
    with STATE_FILE.lock(exclusive=True):
        scenario = _load_scenario()
        try:
            if dry_run:
                scenario._validate_track(request_id, antenna, trx_on, trx_off)
                return {
                    "status": 0,
                    "dry_run": True,
                    "message": "Validation successful - track would be accepted",
                }
            
            result = scenario.schedule_track(request_id, antenna, trx_on, trx_off)
            _save_scenario(scenario)
            duration_h = result.track.duration_hours
            buffer_h = (result.track.teardown_end - result.track.setup_start) / 3600 - duration_h
            return {
                "action_id": result.action_id,
                "track": _format_track(result.track),
                "status": 0,
                "dry_run": False,
                "summary": f"Scheduled {duration_h:.2f}h track (+ {buffer_h:.2f}h setup/teardown buffer)",
            }
        except SatNetNotFoundError as e:
            return {
                "error": str(e),
                "status": 6523,
                "suggestion": "Check request_id from list_unsatisfied_requests()",
            }
        except SatNetValidationError as e:
            return {
                "error": str(e),
                "status": 8794,
                "suggestion": "Use find_view_periods() to get valid scheduling windows",
            }
        except SatNetConflictError as e:
            return {
                "error": str(e),
                "status": 8800,
                "suggestion": "Choose a different time or antenna with no conflicts",
            }


@mcp.tool()
def unschedule_track(action_id: str, dry_run: bool = False) -> Dict[str, Any]:
    """
    Remove a scheduled track, freeing up the time slot.

    Args:
        action_id: ID returned by schedule_track()
        dry_run: If True, check if track can be unscheduled but don't remove it

    Returns:
        - status: 0 (success) or error code
        - error: Error message if failed
        - dry_run: Whether this was a dry run
    """
    with STATE_FILE.lock(exclusive=True):
        scenario = _load_scenario()
        try:
            if dry_run:
                if action_id not in scenario._scheduled_tracks:
                    raise SatNetNotFoundError(f"Track not found: {action_id}")
                return {
                    "status": 0,
                    "dry_run": True,
                    "message": "Track exists and can be unscheduled",
                }
            
            scenario.unschedule_track(action_id)
            _save_scenario(scenario)
            return {"status": 0, "dry_run": False}
        except SatNetNotFoundError as e:
            return {"error": str(e), "status": 6523}


@mcp.tool()
def get_plan_status() -> Dict[str, Any]:
    """
    Get current plan status including all scheduled tracks and metrics.

    Returns:
        - num_tracks: Number of scheduled tracks
        - tracks: List of scheduled track details
        - metrics: Current scoring metrics
            - total_allocated_hours: Sum of all scheduled track durations
            - requests_satisfied: Number of requests fully allocated
            - requests_unsatisfied: Number of requests with remaining time
            - u_max: Maximum unsatisfied fraction across all missions
            - u_rms: Root-mean-square of unsatisfied fractions
    """
    with STATE_FILE.lock(exclusive=False):
        scenario = _load_scenario()
        status = scenario.get_plan_status()
    
    tracks = [_format_track(t) for t in status.tracks.values()]
    
    metrics = None
    if status.metrics:
        metrics = {
            "total_allocated_hours": status.metrics.total_allocated_hours,
            "requests_satisfied": status.metrics.requests_satisfied,
            "requests_unsatisfied": status.metrics.requests_unsatisfied,
            "u_max": status.metrics.u_max,
            "u_rms": status.metrics.u_rms,
        }
    
    return {
        "num_tracks": len(tracks),
        "tracks": tracks,
        "metrics": metrics,
    }


@mcp.tool()
def commit_plan() -> Dict[str, Any]:
    """
    Finalize the schedule and compute scoring metrics.

    Returns:
        - total_allocated_hours: Sum of all scheduled track durations
        - requests_satisfied: Number of requests fully allocated
        - requests_unsatisfied: Number of requests with remaining time
        - u_max: Maximum unsatisfied fraction across all missions
        - u_rms: Root-mean-square of unsatisfied fractions

    Lower u_max and u_rms indicate better schedules.
    The goal is to minimize unfairness (u_max) and overall unmet demand (u_rms).
    """
    output_path = os.environ.get("SATNET_OUTPUT_PATH", "plan.json")
    
    with STATE_FILE.lock(exclusive=True):
        scenario = _load_scenario()
        result = scenario.commit_plan(output_path)
        _save_scenario(scenario)
    
    return {
        "total_allocated_hours": result.metrics.total_allocated_hours,
        "requests_satisfied": result.metrics.requests_satisfied,
        "requests_unsatisfied": result.metrics.requests_unsatisfied,
        "u_max": result.metrics.u_max,
        "u_rms": result.metrics.u_rms,
        "plan_json_path": result.plan_json_path,
    }


@mcp.tool()
def reset() -> Dict[str, str]:
    """
    Reset the schedule to initial (empty) state.
    All scheduled tracks are removed and request allocations are restored.
    """
    with STATE_FILE.lock(exclusive=True):
        scenario = _load_scenario()
        scenario.reset()
        _save_scenario(scenario)
    return {"status": "reset"}


if __name__ == "__main__":
    _auto_initialize()
    mcp.run(transport="stdio")
