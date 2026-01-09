"""
Visualize satellite battery and storage curves over mission horizon.

This script plots per-satellite resource usage (battery level, storage level)
throughout the planning horizon, showing the impact of observations and downlinks.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import yaml

# Ensure src is in path
_SRC: Path | None = None
for _p in Path(__file__).resolve().parents:
    if _p.name == "src":
        _SRC = _p
        break
if _SRC and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine.models import Satellite, ResourceEvent
from engine.resources.power import simulate_power
from engine.resources.storage import simulate_storage
from engine.orbital.lighting import compute_lighting_windows, LightingCondition


def generate_timeline(
    events: List[ResourceEvent],
    initial_level: float,
    capacity: float | None,
    horizon_start: datetime,
    horizon_end: datetime,
    saturate: bool = False,
) -> tuple[List[datetime], List[float]]:
    """
    Generate timeline data from resource events for plotting.
    
    Returns:
        (times, levels) where times is a list of datetime objects and levels is resource levels
    """
    if not events:
        return [horizon_start, horizon_end], [initial_level, initial_level]
    
    # Build boundary points for rate changes
    points: List[tuple] = []
    for e in events:
        points.append((e.start, e.rate_change))
        points.append((e.end, -e.rate_change))
    
    # Sort by time
    points.sort(key=lambda p: p[0])
    
    # Generate timeline
    times = [horizon_start]
    levels = [initial_level]
    
    level = initial_level
    current_rate = 0.0
    last_time = horizon_start
    
    for time, delta_rate in points:
        if time > last_time:
            # Add point just before rate change
            duration_min = (time - last_time).total_seconds() / 60.0
            level += current_rate * duration_min
            
            # Apply saturation if enabled
            if saturate and capacity is not None and level > capacity:
                level = capacity
            
            times.append(time)
            levels.append(level)
            last_time = time
        
        current_rate += delta_rate
    
    # Add final point at horizon end
    if last_time < horizon_end:
        duration_min = (horizon_end - last_time).total_seconds() / 60.0
        level += current_rate * duration_min
        
        if saturate and capacity is not None and level > capacity:
            level = capacity
        
        times.append(horizon_end)
        levels.append(level)
    
    return times, levels


def parse_datetime(value: str | datetime) -> datetime:
    """Parse ISO datetime string."""
    if isinstance(value, datetime):
        return value
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_satellites(satellites_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load satellites catalog."""
    with satellites_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    return {rec["id"]: rec for rec in data if "id" in rec}


def load_plan(plan_path: Path) -> Dict[str, Any]:
    """Load plan JSON."""
    return json.loads(plan_path.read_text(encoding="utf-8"))


def get_engine_satellite(sat_data: Dict[str, Any]) -> Satellite:
    """Convert satellite dict to engine model."""
    return Satellite(
        tle_line1=sat_data["tle_line1"],
        tle_line2=sat_data["tle_line2"],
        apogee_km=sat_data.get("apogee_km", 800.0),
        perigee_km=sat_data.get("perigee_km", 800.0),
        period_min=sat_data.get("period_min", 90.0),
        inclination_deg=sat_data.get("inclination_deg", 98.0),
        storage_capacity_mb=sat_data.get("storage_capacity_mb", 16000.0),
        obs_store_rate_mb_per_min=sat_data.get("obs_store_rate_mb_per_min", 450.0),
        downlink_release_rate_mb_per_min=sat_data.get("downlink_release_rate_mb_per_min", 750.0),
        battery_capacity_wh=sat_data.get("battery_capacity_wh", 2500.0),
        charge_rate_w=sat_data.get("charge_rate_w", 450.0),
        obs_discharge_rate_w=sat_data.get("obs_discharge_rate_w", 700.0),
        downlink_discharge_rate_w=sat_data.get("downlink_discharge_rate_w", 350.0),
        idle_discharge_rate_w=sat_data.get("idle_discharge_rate_w", 10.0),
        initial_storage_mb=sat_data.get("initial_storage_mb", 8000.0),
        initial_battery_wh=sat_data.get("initial_battery_wh", 1500.0),
    )


def plot_satellite_resources(
    satellites_path: Path,
    plan_path: Path,
    output_dir: Path,
    sat_ids: List[str] | None = None,
):
    """
    Plot battery and storage curves for satellites.
    
    Args:
        satellites_path: Path to satellites.yaml
        plan_path: Path to plan.json
        output_dir: Directory to save plots
        sat_ids: Optional list of satellite IDs to plot (defaults to all with actions)
    """
    # Load data
    satellites = load_satellites(satellites_path)
    plan = load_plan(plan_path)
    
    horizon_start = parse_datetime(plan["metadata"]["horizon_start"])
    horizon_end = parse_datetime(plan["metadata"]["horizon_end"])
    
    # Group actions by satellite
    actions_by_sat: Dict[str, List[Dict[str, Any]]] = {}
    for action in plan.get("actions", []):
        sat_id = action["satellite_id"]
        if sat_id not in actions_by_sat:
            actions_by_sat[sat_id] = []
        actions_by_sat[sat_id].append(action)
    
    # Determine which satellites to plot
    if sat_ids is None:
        sat_ids = sorted(actions_by_sat.keys())
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Plot each satellite
    for sat_id in sat_ids:
        if sat_id not in satellites:
            print(f"Warning: Satellite {sat_id} not found in catalog")
            continue
        
        sat_data = satellites[sat_id]
        sat_model = get_engine_satellite(sat_data)
        sat_actions = actions_by_sat.get(sat_id, [])
        
        if not sat_actions:
            print(f"  {sat_id}: No actions, skipping")
            continue
        
        # Create power events
        power_events = []
        for action in sat_actions:
            start = parse_datetime(action.get("start") or action.get("start_time"))
            end = parse_datetime(action.get("end") or action.get("end_time"))
            action_type = action.get("type")
            
            if action_type == "observation":
                rate = -(sat_data.get("obs_discharge_rate_w") / 60.0)
            else:
                rate = -(sat_data.get("downlink_discharge_rate_w") / 60.0)
            
            power_events.append(ResourceEvent(start=start, end=end, rate_change=rate))
        
        # Create storage events
        storage_events = []
        for action in sat_actions:
            start = parse_datetime(action.get("start") or action.get("start_time"))
            end = parse_datetime(action.get("end") or action.get("end_time"))
            action_type = action.get("type")
            
            if action_type == "observation":
                rate = sat_data.get("obs_store_rate_mb_per_min")
            else:
                rate = -sat_data.get("downlink_release_rate_mb_per_min")
            
            storage_events.append(ResourceEvent(start=start, end=end, rate_change=rate))
        
        # Simulate power
        battery_params = (
            sat_data.get("battery_capacity_wh"),
            sat_data.get("charge_rate_w"),
            sat_data.get("obs_discharge_rate_w"),
            sat_data.get("downlink_discharge_rate_w"),
            sat_data.get("idle_discharge_rate_w"),
            sat_data.get("initial_battery_wh"),
        )
        
        power_stats = simulate_power(
            usage_events=power_events,
            satellite_model=sat_model,
            time_window=(horizon_start, horizon_end),
            battery_params=battery_params,
        )
        
        # Simulate storage
        storage_stats = simulate_storage(
            usage_events=storage_events,
            capacity=sat_data.get("storage_capacity_mb"),
            initial=sat_data.get("initial_storage_mb"),
        )
        
        # Create figure with 2 subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        fig.suptitle(f'{sat_id} - Resource Usage\n{sat_data.get("name", sat_id)}', fontsize=14, fontweight='bold')
        
        # Generate power timeline with idle discharge and sunlight charging
        capacity = battery_params[0]
        initial_battery = battery_params[5]
        charge_rate_w = battery_params[1]
        idle_discharge_w = battery_params[4]
        
        # Add idle discharge event
        all_power_events = list(power_events)
        all_power_events.append(
            ResourceEvent(start=horizon_start, end=horizon_end, rate_change=-(idle_discharge_w / 60.0))
        )
        
        # Add sunlight charging events
        light_windows = compute_lighting_windows(sat_model, (horizon_start, horizon_end))
        for w in light_windows:
            if w.condition != LightingCondition.SUNLIGHT:
                continue
            s = max(w.start, horizon_start)
            e = min(w.end, horizon_end)
            if s >= e:
                continue
            all_power_events.append(ResourceEvent(start=s, end=e, rate_change=charge_rate_w / 60.0))
        
        # Generate timeline
        times, levels = generate_timeline(
            all_power_events, initial_battery, capacity, horizon_start, horizon_end, saturate=True
        )
        
        ax1.plot(times, levels, 'b-', linewidth=2, label='Battery Level')
        ax1.axhline(y=capacity, color='g', linestyle='--', alpha=0.5, label=f'Capacity ({capacity:.0f} Wh)')
        ax1.axhline(y=0, color='r', linestyle='--', alpha=0.5, label='Empty')
        
        # Highlight violations
        if power_stats.get("violated_low"):
            ax1.axhline(y=0, color='r', linestyle='-', linewidth=2, alpha=0.8)
            ax1.text(0.02, 0.98, '⚠ BATTERY DEPLETED', transform=ax1.transAxes,
                    verticalalignment='top', color='red', fontweight='bold',
                    bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7))
        
        ax1.set_ylabel('Battery (Wh)', fontsize=11)
        ax1.legend(loc='upper right')
        ax1.grid(True, alpha=0.3)
        ax1.set_ylim(bottom=min(0, min(levels) * 1.1), top=capacity * 1.1)
        
        
        # Generate storage timeline
        storage_capacity = sat_data.get("storage_capacity_mb")
        initial_storage = sat_data.get("initial_storage_mb")
        
        times, levels = generate_timeline(
            storage_events, initial_storage, storage_capacity, horizon_start, horizon_end, saturate=False
        )
        
        ax2.plot(times, levels, 'orange', linewidth=2, label='Storage Level')
        ax2.axhline(y=storage_capacity, color='r', linestyle='--', alpha=0.5, label=f'Capacity ({storage_capacity:.0f} MB)')
        ax2.axhline(y=0, color='g', linestyle='--', alpha=0.5, label='Empty')
        
        # Highlight violations
        if storage_stats.get("peak", 0) > storage_capacity:
            ax2.axhline(y=storage_capacity, color='r', linestyle='-', linewidth=2, alpha=0.8)
            ax2.text(0.02, 0.98, '⚠ STORAGE OVERFLOW', transform=ax2.transAxes,
                    verticalalignment='top', color='red', fontweight='bold',
                    bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7))
        
        ax2.set_ylabel('Storage (MB)', fontsize=11)
        ax2.set_xlabel('Time (UTC)', fontsize=11)
        ax2.legend(loc='upper right')
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(bottom=0, top=max(storage_capacity, max(levels)) * 1.1)
        
        # Format x-axis
        fig.autofmt_xdate()
        
        plt.tight_layout()
        
        # Save figure
        output_path = output_dir / f"{sat_id}_resources.png"
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"  {sat_id}: {len(sat_actions)} actions, saved to {output_path.name}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Visualize satellite battery and storage curves")
    parser.add_argument("--satellites", required=True, help="Path to satellites.yaml")
    parser.add_argument("--plan", required=True, help="Path to plan.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for plots")
    parser.add_argument("--sat-ids", help="Comma-separated satellite IDs to plot (default: all)")
    
    args = parser.parse_args()
    
    sat_ids = None
    if args.sat_ids:
        sat_ids = [s.strip() for s in args.sat_ids.split(",") if s.strip()]
    
    print(f"Plotting resource curves...")
    print(f"  Satellites: {args.satellites}")
    print(f"  Plan: {args.plan}")
    print(f"  Output: {args.output_dir}")
    
    plot_satellite_resources(
        satellites_path=Path(args.satellites),
        plan_path=Path(args.plan),
        output_dir=Path(args.output_dir),
        sat_ids=sat_ids,
    )
    
    print("Done!")


if __name__ == "__main__":
    main()
