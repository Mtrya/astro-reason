"""Formatting utilities for MCP server responses.

This module contains functions that transform planner data structures into
LLM-friendly dictionary formats for the MCP server.
"""

from typing import Dict, Any
from planner.models import PlannerSatellite, PlannerTarget, PlannerStation, PlannerAccessWindow, PlannerAction, PlannerStrip, PlanStatus
from planner.helpers.mcp_helpers import format_satellite_summary


def satellite_summary_key(sat: PlannerSatellite) -> Dict[str, Any]:
    """Extract fields for filtering, plus compute summary strings for output."""
    orbit = f"{sat.apogee_km:.0f}km x {sat.perigee_km:.0f}km @ {sat.inclination_deg:.1f}°"
    storage = f"{sat.storage_capacity_mb:.0f}MB, {sat.obs_store_rate_mb_per_min:.1f}MB/min obs, {sat.downlink_release_rate_mb_per_min:.1f}MB/min dl"
    power = f"{sat.battery_capacity_wh:.0f}Wh, {sat.charge_rate_w:.0f}W charge, {sat.idle_discharge_rate_w:.0f}W idle"
    wheel = f"{sat.max_slew_velocity_deg_per_sec:.1f}°/s max, {sat.max_slew_acceleration_deg_per_sec2:.2f}°/s² accel"
    return {
        "id": sat.id,
        "name": sat.name,
        "constellation": sat.constellation,
        "owner": sat.owner,
        "tle_epoch": sat.tle_epoch,
        "orbit": orbit,
        "storage": storage,
        "power": power,
        "wheel": wheel,
        "num_terminal": getattr(sat, "num_terminal", 1),
    }


def satellite_filter_key(sat: PlannerSatellite) -> Dict[str, Any]:
    """Extract all fields for filtering."""
    return sat.__dict__


def target_key(target: PlannerTarget) -> Dict[str, Any]:
    """Extract target fields for filtering."""
    return target.__dict__


def station_key(station: PlannerStation) -> Dict[str, Any]:
    """Extract station fields for filtering."""
    return station.__dict__


def window_summary_key(w: PlannerAccessWindow) -> Dict[str, Any]:
    """Convert window to dict with summary string for best elevation/range."""
    best_pt = w.max_elevation_point

    best_summary = ""
    if best_pt:
        best_summary = f"Elev: {best_pt.elevation_deg:.1f}° | Az: {best_pt.azimuth_deg:.1f}° | Range: {best_pt.range_m/1000:.1f}km | Time: {best_pt.time.strftime('%H:%M:%S')}"

    if w.target_id:
        counterpart_kind = "target"
    elif w.station_id:
        counterpart_kind = "station"
    elif w.peer_satellite_id:
        counterpart_kind = "satellite"
    elif w.strip_id:
        counterpart_kind = "strip"
    else:
        counterpart_kind = "unknown"

    return {
        "window_id": w.window_id,
        "satellite_id": w.satellite_id,
        "target_id": w.target_id,
        "station_id": w.station_id,
        "peer_satellite_id": w.peer_satellite_id,
        "counterpart_kind": counterpart_kind,
        "start": w.start.isoformat(),
        "end": w.end.isoformat(),
        "duration_sec": w.duration_sec,
        "best": best_summary,
    }


def window_filter_key(w: PlannerAccessWindow) -> Dict[str, Any]:
    """Extract fields for filtering windows."""
    best_pt = w.max_elevation_point
    
    if w.target_id:
        counterpart_kind = "target"
    elif w.station_id:
        counterpart_kind = "station"
    elif w.peer_satellite_id:
        counterpart_kind = "satellite"
    elif w.strip_id:
        counterpart_kind = "strip"
    else:
        counterpart_kind = "unknown"

    return {
        "window_id": w.window_id,
        "satellite_id": w.satellite_id,
        "target_id": w.target_id,
        "station_id": w.station_id,
        "peer_satellite_id": w.peer_satellite_id,
        "counterpart_kind": counterpart_kind,
        "start": w.start.isoformat(),
        "end": w.end.isoformat(),
        "duration_sec": w.duration_sec,
        "best_elevation_deg": best_pt.elevation_deg if best_pt else None,
        "best_range_km": best_pt.range_m / 1000.0 if best_pt else None,
        "best_azimuth_deg": best_pt.azimuth_deg if best_pt else None,
    }


def strip_key(strip: PlannerStrip) -> Dict[str, Any]:
    """Extract strip fields for display."""
    return {"id": strip.id, "name": strip.name, "points_count": len(strip.points)}


def action_key(action: PlannerAction) -> Dict[str, Any]:
    """Extract action fields for display."""
    return {
        "action_id": action.action_id,
        "type": action.type,
        "satellite_id": action.satellite_id,
        "target_id": action.target_id,
        "station_id": action.station_id,
        "peer_satellite_id": action.peer_satellite_id,
        "start": action.start_time.isoformat(),
        "end": action.end_time.isoformat(),
        "duration_sec": (action.end_time - action.start_time).total_seconds(),
    }


def format_plan_status(status: PlanStatus, horizon_start, horizon_end) -> Dict[str, Any]:
    """Format PlanStatus for LLM consumption."""
    sat_summaries = [format_satellite_summary(m) for m in status.metrics.satellites.values()]
    
    # Sort actions by start time and limit to top 20
    sorted_actions = sorted(status.actions.values(), key=lambda a: a.start_time)
    actions_list = [action_key(a) for a in sorted_actions[:20]]

    return {
        "action_count": len(status.actions),
        "total_observations": status.metrics.total_observations,
        "total_downlinks": status.metrics.total_downlinks,
        "top_staged_actions": actions_list,
        "satellites": sat_summaries,
        "horizon": f"{horizon_start.isoformat()} - {horizon_end.isoformat()}",
    }
