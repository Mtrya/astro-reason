"""
Visualize regional coverage for satellite mission plans.

This script plots geographic maps showing polygon coverage with observation strips,
using Cartopy for world map backgrounds.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.patches import Polygon as MplPolygon
import yaml
from skyfield.api import EarthSatellite, load, wgs84

# Ensure src is in path
_SRC: Path | None = None
for _p in Path(__file__).resolve().parents:
    if _p.name == "src":
        _SRC = _p
        break
if _SRC and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine.analytics import compute_polygon_coverage


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


def load_requirements(requirements_path: Path) -> Dict[str, Any]:
    """Load requirements.yaml containing polygons."""
    with requirements_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_plan(plan_path: Path) -> Dict[str, Any]:
    """Load plan.json with actions and registered strips."""
    return json.loads(plan_path.read_text(encoding="utf-8"))


def load_satellites(satellites_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load satellites.yaml for swath width lookup."""
    with satellites_path.open("r", encoding="utf-8") as f:
        satellites_list = yaml.safe_load(f) or []
    return {sat["id"]: sat for sat in satellites_list if "id" in sat}


def compute_ground_track(
    tle_line1: str,
    tle_line2: str,
    start_time: datetime,
    end_time: datetime,
    sample_points: int = 500
) -> tuple[List[float], List[float]]:
    """
    Compute satellite ground track using Skyfield.

    Args:
        tle_line1: TLE line 1
        tle_line2: TLE line 2
        start_time: Start time for ground track
        end_time: End time for ground track
        sample_points: Number of points to sample along the track

    Returns:
        (latitudes, longitudes) as lists of floats
    """
    # Load timescale
    ts = load.timescale()

    # Create satellite object
    satellite = EarthSatellite(tle_line1, tle_line2, "Satellite", ts)

    # Generate time samples
    t_start = ts.utc(start_time.year, start_time.month, start_time.day,
                     start_time.hour, start_time.minute, start_time.second)
    t_end = ts.utc(end_time.year, end_time.month, end_time.day,
                   end_time.hour, end_time.minute, end_time.second)

    # Create linspace of times
    times = ts.linspace(t_start, t_end, sample_points)

    # Compute positions
    geocentric = satellite.at(times)
    subpoint = wgs84.subpoint(geocentric)

    latitudes = subpoint.latitude.degrees
    longitudes = subpoint.longitude.degrees

    return list(latitudes), list(longitudes)


def compute_coverage_for_polygon(
    polygon: Dict[str, Any],
    plan: Dict[str, Any],
    satellites: Dict[str, Dict[str, Any]]
) -> float:
    """
    Compute coverage percentage for a polygon.

    Args:
        polygon: Polygon definition with vertices
        plan: Plan data with actions and registered_strips
        satellites: Satellite catalog for swath width lookup

    Returns:
        Coverage percentage (0-100)
    """
    vertices = [(lat, lon) for lat, lon in polygon["vertices"]]
    registered_strips = {s["id"]: s for s in plan.get("registered_strips", [])}

    # Build strips with width from observations
    strips_with_width = []
    observation_strip_ids = {
        action["strip_id"] for action in plan.get("actions", [])
        if action.get("type") == "observation" and action.get("strip_id")
    }

    for strip_id in observation_strip_ids:
        if strip_id in registered_strips:
            strip_data = registered_strips[strip_id]
            strip_polyline = [(lat, lon) for lat, lon in strip_data["points"]]

            # Find satellite for swath width
            swath_km = 5.7  # default
            for action in plan.get("actions", []):
                if action.get("strip_id") == strip_id:
                    sat = satellites.get(action.get("satellite_id"), {})
                    swath_km = sat.get("swath_width_km", 5.7)
                    break

            strips_with_width.append((strip_polyline, swath_km))

    if not strips_with_width:
        return 0.0

    stats = compute_polygon_coverage(vertices, strips_with_width, grid_step_deg=0.1)
    return stats["coverage_ratio"] * 100.0


def plot_polygon_coverage(
    polygon: Dict[str, Any],
    plan: Dict[str, Any],
    satellites: Dict[str, Dict[str, Any]],
    coverage_pct: float,
    output_path: Path,
    show_ground_track: bool = True,
    ground_track_satellite_id: str | None = None
):
    """
    Create coverage visualization for a single polygon.

    Args:
        polygon: Polygon definition with id and vertices
        plan: Plan data with actions and registered_strips
        satellites: Satellite catalog for swath width
        coverage_pct: Computed coverage percentage
        output_path: Path to save PNG output
        show_ground_track: Whether to show satellite ground track
        ground_track_satellite_id: Specific satellite ID for ground track (defaults to first satellite with observations)
    """
    # Extract polygon vertices (lat, lon)
    vertices = polygon["vertices"]
    lats = [v[0] for v in vertices]
    lons = [v[1] for v in vertices]

    # Calculate map extent with padding (wider coverage)
    lat_pad = (max(lats) - min(lats)) * 0.8 if len(lats) > 1 else 3.0
    lon_pad = (max(lons) - min(lons)) * 0.8 if len(lons) > 1 else 3.0
    extent = [
        min(lons) - lon_pad, max(lons) + lon_pad,
        min(lats) - lat_pad, max(lats) + lat_pad
    ]

    # Create figure
    fig = plt.figure(figsize=(14, 10))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent(extent, crs=ccrs.PlateCarree())

    # Add map features
    ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
    ax.add_feature(cfeature.BORDERS, linewidth=0.5, alpha=0.5)
    ax.add_feature(cfeature.LAND, facecolor='lightgray', alpha=0.3)
    ax.add_feature(cfeature.OCEAN, facecolor='lightblue', alpha=0.2)
    ax.gridlines(draw_labels=True, alpha=0.3)

    # Plot polygon as filled area
    poly_coords = [(lon, lat) for lat, lon in vertices]
    poly_patch = MplPolygon(
        poly_coords,
        closed=True,
        facecolor='yellow',
        alpha=0.3,
        edgecolor='red',
        linewidth=2,
        transform=ccrs.PlateCarree(),
        label=f'Target Polygon: {polygon["id"]}'
    )
    ax.add_patch(poly_patch)

    # Plot registered strips
    registered_strips = {s["id"]: s for s in plan.get("registered_strips", [])}
    observation_strip_ids = {
        action["strip_id"] for action in plan.get("actions", [])
        if action.get("type") == "observation" and action.get("strip_id")
    }

    # Option A: Strips not in actions (polylines without width)
    other_strips = set(registered_strips.keys()) - observation_strip_ids
    for strip_id in other_strips:
        strip = registered_strips[strip_id]
        strip_lons = [lon for lat, lon in strip["points"]]
        strip_lats = [lat for lat, lon in strip["points"]]
        ax.plot(strip_lons, strip_lats, 'blue', linewidth=2.0, alpha=0.8,
                transform=ccrs.PlateCarree(), label='Registered Strip', linestyle=':')

    # Option B: Strips in observation actions (with swath annotation)
    for strip_id in observation_strip_ids:
        if strip_id not in registered_strips:
            continue
        strip = registered_strips[strip_id]

        # Get swath width
        swath_km = 5.7
        for action in plan.get("actions", []):
            if action.get("strip_id") == strip_id:
                sat = satellites.get(action.get("satellite_id"), {})
                swath_km = sat.get("swath_width_km", 5.7)
                break

        # Draw strip centerline
        strip_lons = [lon for lat, lon in strip["points"]]
        strip_lats = [lat for lat, lon in strip["points"]]
        ax.plot(strip_lons, strip_lats, 'blue', linewidth=2, alpha=0.7,
                transform=ccrs.PlateCarree(), label=f'Observation Strip ({swath_km:.1f}km swath)')

    # Plot ground track if requested
    if show_ground_track:
        # Determine which satellite to show ground track for
        target_sat_id = ground_track_satellite_id
        if target_sat_id is None:
            # Default to first satellite with observations
            for action in plan.get("actions", []):
                if action.get("type") == "observation" and action.get("satellite_id"):
                    target_sat_id = action["satellite_id"]
                    break

        if target_sat_id and target_sat_id in satellites:
            sat_data = satellites[target_sat_id]
            horizon_start = parse_datetime(plan["metadata"]["horizon_start"])
            horizon_end = parse_datetime(plan["metadata"]["horizon_end"])

            try:
                track_lats, track_lons = compute_ground_track(
                    sat_data["tle_line1"],
                    sat_data["tle_line2"],
                    horizon_start,
                    horizon_end,
                    sample_points=500
                )

                ax.plot(track_lons, track_lats, 'cyan', linewidth=1.5, alpha=0.8,
                        transform=ccrs.PlateCarree(), label=f'Ground Track ({target_sat_id})',
                        linestyle='--')
            except Exception as e:
                print(f"    Warning: Could not compute ground track for {target_sat_id}: {e}")

    # Add legend (avoiding duplicates)
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), loc='upper right', fontsize=12)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()


def visualize_regional_coverage(
    case_dir: Path,
    plan_path: Path,
    output_dir: Path,
    show_ground_track: bool = True,
    ground_track_satellite_id: str | None = None
):
    """
    Generate regional coverage visualizations.

    Saves one PNG per polygon to output_dir.

    Args:
        case_dir: Path to case directory
        plan_path: Path to plan.json file
        output_dir: Directory to save PNG files
        show_ground_track: Whether to show satellite ground track
        ground_track_satellite_id: Specific satellite ID for ground track (defaults to first satellite)
    """
    # Load data
    requirements = load_requirements(case_dir / "requirements.yaml")
    satellites = load_satellites(case_dir / "satellites.yaml")
    plan = load_plan(plan_path)

    polygons = requirements.get("regional_coverage", {}).get("polygons", [])

    if not polygons:
        print("Warning: No polygons found in requirements.yaml")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating coverage visualizations for {len(polygons)} polygon(s)...")

    for polygon in polygons:
        polygon_id = polygon["id"]

        try:
            coverage_pct = compute_coverage_for_polygon(polygon, plan, satellites)
            output_path = output_dir / f"coverage_{polygon_id}.png"

            plot_polygon_coverage(
                polygon, plan, satellites, coverage_pct, output_path,
                show_ground_track=show_ground_track,
                ground_track_satellite_id=ground_track_satellite_id
            )
            print(f"  {polygon_id}: {coverage_pct:.1f}% coverage -> {output_path.name}")

        except Exception as e:
            print(f"  {polygon_id}: Error - {e}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Visualize regional coverage for satellite mission plans"
    )
    parser.add_argument("--case-dir", required=True, help="Path to case directory")
    parser.add_argument("--plan", required=True, help="Path to plan.json file")
    parser.add_argument("--output-dir", default=".", help="Output directory (default: project root)")
    parser.add_argument("--no-ground-track", action="store_true", help="Disable ground track visualization")
    parser.add_argument("--satellite-id", help="Specific satellite ID for ground track (default: first satellite)")

    args = parser.parse_args()

    print("Regional Coverage Visualization")
    print(f"  Case: {args.case_dir}")
    print(f"  Plan: {args.plan}")
    print(f"  Output: {args.output_dir}")
    if not args.no_ground_track:
        if args.satellite_id:
            print(f"  Ground Track: {args.satellite_id}")
        else:
            print(f"  Ground Track: Auto (first satellite)")
    print()

    visualize_regional_coverage(
        case_dir=Path(args.case_dir),
        plan_path=Path(args.plan),
        output_dir=Path(args.output_dir),
        show_ground_track=not args.no_ground_track,
        ground_track_satellite_id=args.satellite_id
    )

    print("\nDone!")


if __name__ == "__main__":
    main()
