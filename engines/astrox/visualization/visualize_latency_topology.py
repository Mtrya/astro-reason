"""
Visualize latency topology for satellite mission plans.

This script plots network graphs showing satellite-station connectivity
at specific timepoints, using NetworkX for force-directed layouts.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import networkx as nx
import yaml

# Ensure src is in path
_SRC: Path | None = None
for _p in Path(__file__).resolve().parents:
    if _p.name == "src":
        _SRC = _p
        break
if _SRC and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engines.astrox.models import Satellite, Station
from engines.astrox.orbital.chain import compute_chain_access_with_latency


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
    """Load latency requirements with station pairs."""
    with requirements_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_plan(plan_path: Path) -> Dict[str, Any]:
    """Load plan.json with communication actions."""
    return json.loads(plan_path.read_text(encoding="utf-8"))


def load_satellites(satellites_path: Path) -> Dict[str, Satellite]:
    """Load satellites as engine models."""
    with satellites_path.open("r", encoding="utf-8") as f:
        satellites_list = yaml.safe_load(f) or []

    result = {}
    for sat_data in satellites_list:
        sat_id = sat_data["id"]
        result[sat_id] = Satellite(
            tle_line1=sat_data["tle_line1"],
            tle_line2=sat_data["tle_line2"],
            apogee_km=sat_data.get("apogee_km", 800.0),
            perigee_km=sat_data.get("perigee_km", 800.0),
            period_min=sat_data.get("period_min", 90.0),
            inclination_deg=sat_data.get("inclination_deg", 98.0),
        )
    return result


def load_stations(stations_path: Path) -> Dict[str, Station]:
    """Load stations as engine models."""
    with stations_path.open("r", encoding="utf-8") as f:
        stations_list = yaml.safe_load(f) or []

    result = {}
    for station_data in stations_list:
        station_id = station_data["id"]
        result[station_id] = Station(
            latitude_deg=station_data["latitude_deg"],
            longitude_deg=station_data["longitude_deg"],
            altitude_m=station_data["altitude_m"]
        )
    return result


def build_topology_at_time(
    station_a_id: str,
    station_b_id: str,
    plan: Dict[str, Any],
    timepoint: datetime
) -> nx.Graph:
    """
    Build network topology at specific timepoint.

    Args:
        station_a_id: Source station ID
        station_b_id: Destination station ID
        plan: Plan data with actions
        timepoint: Specific time to snapshot topology

    Returns:
        NetworkX graph with nodes and edges active at timepoint
    """
    G = nx.Graph()

    # Add source and destination stations (even if not in actions)
    G.add_node(station_a_id, node_type="station", side="left")
    G.add_node(station_b_id, node_type="station", side="right")

    # Process ALL actions active at timepoint to build complete network
    for action in plan.get("actions", []):
        start = parse_datetime(action.get("start") or action.get("start_time"))
        end = parse_datetime(action.get("end") or action.get("end_time"))

        if not (start <= timepoint <= end):
            continue

        action_type = action.get("type")

        if action_type == "downlink":
            sat_id = action["satellite_id"]
            station_id = action["station_id"]

            # Add station node if not present
            if station_id not in G:
                # Determine side based on whether it's one of the target stations
                if station_id == station_a_id:
                    side = "left"
                elif station_id == station_b_id:
                    side = "right"
                else:
                    side = "middle"
                G.add_node(station_id, node_type="station", side=side)

            # Add satellite if not present
            if sat_id not in G:
                G.add_node(sat_id, node_type="satellite", side="middle")

            # Add bidirectional edge between satellite and station
            G.add_edge(sat_id, station_id, edge_type="downlink")

        elif action_type == "intersatellite_link":
            sat_a = action["satellite_id"]
            sat_b = action["peer_satellite_id"]

            # Add satellites if not present
            for sat_id in [sat_a, sat_b]:
                if sat_id not in G:
                    G.add_node(sat_id, node_type="satellite", side="middle")

            # Add bidirectional ISL edge
            G.add_edge(sat_a, sat_b, edge_type="isl")

    return G


def has_path_between_stations(G: nx.Graph, station_a_id: str, station_b_id: str) -> bool:
    """
    Check if there's a path between two stations in the graph.

    Args:
        G: NetworkX graph
        station_a_id: Source station ID
        station_b_id: Destination station ID

    Returns:
        True if a path exists, False otherwise
    """
    try:
        return nx.has_path(G, station_a_id, station_b_id)
    except nx.NodeNotFound:
        return False


def find_connection_timepoints(
    station_a_id: str,
    station_b_id: str,
    plan: Dict[str, Any],
    time_window: Tuple[datetime, datetime],
    sample_interval_sec: int = 60
) -> List[datetime]:
    """
    Find all timepoints where connections exist between two stations.

    Args:
        station_a_id: Source station ID
        station_b_id: Destination station ID
        plan: Plan data with actions
        time_window: (start, end) datetime tuple
        sample_interval_sec: Sampling interval in seconds

    Returns:
        List of timepoints where paths exist between stations
    """
    window_start, window_end = time_window
    connection_timepoints = []

    current_time = window_start
    while current_time <= window_end:
        G = build_topology_at_time(station_a_id, station_b_id, plan, current_time)

        # Check if there's a path between the two stations
        if has_path_between_stations(G, station_a_id, station_b_id):
            connection_timepoints.append(current_time)

        current_time += timedelta(seconds=sample_interval_sec)

    return connection_timepoints


def compute_latency_for_pair(
    station_a_id: str,
    station_b_id: str,
    satellites: Dict[str, Satellite],
    stations: Dict[str, Station],
    plan: Dict[str, Any],
    time_window: Tuple[str, str],
    timepoint: datetime
) -> Optional[float]:
    """
    Compute signal latency at specific timepoint.

    Args:
        station_a_id: Source station ID
        station_b_id: Destination station ID
        satellites: Satellite catalog
        stations: Station catalog
        plan: Plan data
        time_window: Time window as (start_iso, end_iso)
        timepoint: Specific time to compute latency for

    Returns:
        Latency in milliseconds, or None if no path exists
    """
    # Build all_nodes and connections from plan
    all_nodes = {}
    all_nodes[station_a_id] = stations[station_a_id]
    all_nodes[station_b_id] = stations[station_b_id]

    connections = []
    for action in plan.get("actions", []):
        action_type = action.get("type")
        if action_type == "downlink":
            sat_id = action["satellite_id"]
            station_id = action["station_id"]
            if sat_id in satellites:
                all_nodes[sat_id] = satellites[sat_id]
            connections.append((sat_id, station_id))
            connections.append((station_id, sat_id))  # Bidirectional
        elif action_type == "intersatellite_link":
            sat_a = action["satellite_id"]
            sat_b = action["peer_satellite_id"]
            for sat_id in [sat_a, sat_b]:
                if sat_id in satellites:
                    all_nodes[sat_id] = satellites[sat_id]
            connections.append((sat_a, sat_b))
            connections.append((sat_b, sat_a))  # Bidirectional

    try:
        result = compute_chain_access_with_latency(
            start_node=stations[station_a_id],
            end_node=stations[station_b_id],
            all_nodes=all_nodes,
            connections=connections,
            time_window=time_window,
            sample_step_sec=60.0
        )

        if result.windows:
            # Find latency sample closest to timepoint
            for window in result.windows:
                for sample in window.latency_samples:
                    if abs((sample.time - timepoint).total_seconds()) < 60:
                        return sample.latency_ms

        return None
    except Exception as e:
        print(f"  Warning: Could not compute latency: {e}")
        return None


def plot_topology(
    G: nx.Graph,
    station_a_id: str,
    station_b_id: str,
    timepoint: datetime,
    latency_ms: Optional[float],
    output_path: Path,
    timepoint_index: Optional[int] = None
):
    """
    Visualize network topology using force-directed layout.

    Args:
        G: NetworkX graph
        station_a_id: Source station ID
        station_b_id: Destination station ID
        timepoint: Timepoint of snapshot
        latency_ms: Computed latency (or None)
        output_path: Path to save PNG
    """
    fig, ax = plt.subplots(figsize=(16, 10))

    # Create position layout with fixed positions for stations
    fixed_positions = {
        station_a_id: (-1.0, 0.0),  # Left
        station_b_id: (1.0, 0.0)     # Right
    }

    pos = nx.spring_layout(
        G,
        pos=fixed_positions,
        fixed=[station_a_id, station_b_id],
        k=0.5,
        iterations=50
    )

    # Separate nodes by type
    station_nodes = [n for n in G.nodes() if G.nodes[n].get("node_type") == "station"]
    satellite_nodes = [n for n in G.nodes() if G.nodes[n].get("node_type") == "satellite"]

    # Draw nodes
    nx.draw_networkx_nodes(
        G, pos, nodelist=station_nodes,
        node_color='red', node_size=1000,
        node_shape='s', label='Ground Station',
        ax=ax
    )
    nx.draw_networkx_nodes(
        G, pos, nodelist=satellite_nodes,
        node_color='blue', node_size=700,
        node_shape='o', label='Satellite',
        ax=ax
    )

    # Draw edges by type
    downlink_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("edge_type") == "downlink"]
    isl_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("edge_type") == "isl"]

    nx.draw_networkx_edges(
        G, pos, edgelist=downlink_edges,
        edge_color='green', width=2.5, style='solid',
        label='Downlink', ax=ax
    )
    nx.draw_networkx_edges(
        G, pos, edgelist=isl_edges,
        edge_color='orange', width=2.5, style='dashed',
        label='Inter-Satellite Link', ax=ax
    )

    # Draw labels
    nx.draw_networkx_labels(G, pos, font_size=8, font_weight='bold', ax=ax)

    # Add title with latency
    latency_str = f"{latency_ms:.2f} ms" if latency_ms else "N/A"
    title = f"Topology: {station_a_id} → {station_b_id}"
    if timepoint_index is not None:
        title += f" (Snapshot #{timepoint_index})"
    title += f"\nTime: {timepoint.isoformat()}\n"
    title += f"Signal Latency: {latency_str}"
    ax.set_title(title, fontsize=13, fontweight='bold', pad=20)

    # Add legend
    ax.legend(loc='upper left', fontsize=11, framealpha=0.9)
    ax.axis('off')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()


def visualize_latency_topology(
    case_dir: Path,
    plan_path: Path,
    output_dir: Path,
    timepoint: Optional[datetime] = None,
    auto_discover: bool = False,
    sample_interval_sec: int = 60,
    max_snapshots: int = 10
):
    """
    Generate latency topology visualizations.

    Saves one PNG per station pair to output_dir.

    Args:
        case_dir: Path to case directory
        plan_path: Path to plan.json file
        output_dir: Directory to save PNG files
        timepoint: Optional timepoint for snapshot (default: midpoint of window)
        auto_discover: If True, automatically find all timepoints with connections
        sample_interval_sec: Sampling interval in seconds for auto-discovery
        max_snapshots: Maximum number of snapshots to generate per station pair
    """
    # Load data
    requirements = load_requirements(case_dir / "requirements.yaml")
    satellites = load_satellites(case_dir / "satellites.yaml")
    stations = load_stations(case_dir / "stations.yaml")
    plan = load_plan(plan_path)

    station_pairs = requirements.get("latency_optimization", {}).get("station_pairs", [])

    if not station_pairs:
        print("Warning: No station pairs found in requirements.yaml")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating topology visualizations for {len(station_pairs)} station pair(s)...")
    if auto_discover:
        print(f"  Mode: Auto-discover (sampling every {sample_interval_sec}s, max {max_snapshots} snapshots)")
    else:
        print(f"  Mode: Single snapshot")

    for pair in station_pairs:
        station_a = pair["station_a"]
        station_b = pair["station_b"]
        window_start = parse_datetime(pair["time_window_start"])
        window_end = parse_datetime(pair["time_window_end"])

        try:
            if auto_discover:
                # Find all connection timepoints
                print(f"\n  {station_a} → {station_b}: Searching for connections...")
                connection_timepoints = find_connection_timepoints(
                    station_a, station_b, plan,
                    (window_start, window_end),
                    sample_interval_sec
                )

                if not connection_timepoints:
                    print(f"    No connections found in time window")
                    continue

                print(f"    Found {len(connection_timepoints)} timepoint(s) with connections")

                # Limit to max_snapshots, evenly distributed
                if len(connection_timepoints) > max_snapshots:
                    step = len(connection_timepoints) // max_snapshots
                    selected_timepoints = [connection_timepoints[i * step] for i in range(max_snapshots)]
                else:
                    selected_timepoints = connection_timepoints

                # Generate snapshot for each timepoint
                for idx, tp in enumerate(selected_timepoints, start=1):
                    G = build_topology_at_time(station_a, station_b, plan, tp)

                    # Compute latency
                    latency_ms = compute_latency_for_pair(
                        station_a, station_b,
                        satellites, stations, plan,
                        (pair["time_window_start"], pair["time_window_end"]),
                        tp
                    )

                    # Plot with index
                    output_path = output_dir / f"topology_{station_a}_{station_b}_{idx:03d}.png"
                    plot_topology(G, station_a, station_b, tp, latency_ms, output_path, timepoint_index=idx)

                    latency_display = f"{latency_ms:.2f} ms" if latency_ms else "N/A"
                    print(f"    Snapshot {idx}/{len(selected_timepoints)}: {tp.strftime('%H:%M:%S')} - {latency_display} -> {output_path.name}")

            else:
                # Single snapshot mode
                # Use provided timepoint or default to midpoint
                if timepoint is None:
                    midpoint_sec = (window_end - window_start).total_seconds() / 2
                    tp = window_start + timedelta(seconds=midpoint_sec)
                else:
                    tp = timepoint

                # Build topology
                G = build_topology_at_time(station_a, station_b, plan, tp)

                # Compute latency (optional)
                latency_ms = compute_latency_for_pair(
                    station_a, station_b,
                    satellites, stations, plan,
                    (pair["time_window_start"], pair["time_window_end"]),
                    tp
                )

                # Plot
                output_path = output_dir / f"topology_{station_a}_{station_b}.png"
                plot_topology(G, station_a, station_b, tp, latency_ms, output_path)

                latency_display = f"{latency_ms:.2f} ms" if latency_ms else "N/A"
                print(f"  {station_a} → {station_b}: {latency_display} -> {output_path.name}")

        except Exception as e:
            print(f"  {station_a} → {station_b}: Error - {e}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Visualize latency topology for satellite mission plans"
    )
    parser.add_argument("--case-dir", required=True, help="Path to case directory")
    parser.add_argument("--plan", required=True, help="Path to plan.json file")
    parser.add_argument("--output-dir", default=".", help="Output directory (default: project root)")
    parser.add_argument("--timepoint", help="ISO timestamp for snapshot (default: midpoint of window)")
    parser.add_argument("--auto-discover", action="store_true",
                        help="Automatically find all timepoints with connections and generate multiple snapshots")
    parser.add_argument("--sample-interval", type=int, default=60,
                        help="Sampling interval in seconds for auto-discovery (default: 60)")
    parser.add_argument("--max-snapshots", type=int, default=10,
                        help="Maximum number of snapshots per station pair (default: 10)")

    args = parser.parse_args()

    tp = None
    if args.timepoint:
        tp = parse_datetime(args.timepoint)

    print("Latency Topology Visualization")
    print(f"  Case: {args.case_dir}")
    print(f"  Plan: {args.plan}")
    print(f"  Output: {args.output_dir}")
    if args.auto_discover:
        print(f"  Mode: Auto-discover connections")
        print(f"  Sample Interval: {args.sample_interval}s")
        print(f"  Max Snapshots: {args.max_snapshots}")
    elif tp:
        print(f"  Timepoint: {tp.isoformat()}")
    print()

    visualize_latency_topology(
        case_dir=Path(args.case_dir),
        plan_path=Path(args.plan),
        output_dir=Path(args.output_dir),
        timepoint=tp,
        auto_discover=args.auto_discover,
        sample_interval_sec=args.sample_interval,
        max_snapshots=args.max_snapshots
    )

    print("\nDone!")


if __name__ == "__main__":
    main()
