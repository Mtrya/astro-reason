"""Generate latency-optimization benchmark cases.

This module creates test cases for the latency-optimization benchmark by:
- Selecting satellites from LEO communication constellations
- Choosing target cities and station pairs for latency testing
- Generating requirements with time windows for station pairs
"""

from pathlib import Path
from typing import List, Dict, Any
import random
import math

from benchmark.utils.catalog_loader import load_archived_satellites, load_archived_targets, load_archived_stations
from benchmark.utils.generator_helpers import (
    filter_satellites_by_constellation,
    compute_average_inclination,
    filter_cities_by_inclination,
    ensure_global_distribution,
    write_manifest,
    write_satellites_yaml,
    write_targets_yaml,
    write_stations_yaml,
    write_requirements_yaml,
    write_initial_plan,
    render_mission_brief,
)



CONSTELLATIONS = ["QIANFAN"]


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points on Earth in kilometers."""
    R = 6371  # Earth radius in kilometers
    
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def select_station_pairs(stations: List[Dict[str, Any]], num_pairs: int = 5, min_distance_km: float = 3000.0) -> List[tuple]:
    """Select station pairs with significant separation.
    
    Args:
        stations: List of all stations
        num_pairs: Number of pairs to select
        min_distance_km: Minimum separation between stations
        
    Returns:
        List of (station_a, station_b) tuples
    """
    pairs = []
    attempts = 0
    max_attempts = 1000
    
    while len(pairs) < num_pairs and attempts < max_attempts:
        attempts += 1
        station_a, station_b = random.sample(stations, 2)
        
        distance = _haversine_distance(
            station_a["latitude_deg"], station_a["longitude_deg"],
            station_b["latitude_deg"], station_b["longitude_deg"]
        )
        
        if distance >= min_distance_km:
            # Check this pair isn't too similar to existing pairs
            is_duplicate = False
            for existing_a, existing_b in pairs:
                if ({station_a["id"], station_b["id"]} == {existing_a["id"], existing_b["id"]}):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                pairs.append((station_a, station_b))
    
    return pairs


def generate_case(
    case_id: str,
    output_dir: Path,
    seed: int = 42,
    horizon_start: str = "2025-07-17T12:00:00Z",
    horizon_end: str = "2025-07-21T12:00:00Z",
) -> None:
    """Generate a latency-optimization benchmark case.
    
    Args:
        case_id: Unique case identifier (e.g., "case_0001")
        output_dir: Directory to write case files
        seed: Random seed for reproducibility
        horizon_start: Mission horizon start time (ISO 8601)
        horizon_end: Mission horizon end time (ISO 8601)
    """
    random.seed(seed)
    
    # Load archived databases
    all_satellites = load_archived_satellites()
    all_cities = load_archived_targets()
    all_stations = load_archived_stations()
    
    # Filter satellites by constellation
    # Sample ONE constellation for this case
    selected_constellation = random.choice(CONSTELLATIONS)
    constellation_sats = filter_satellites_by_constellation(all_satellites, [selected_constellation])
    
    if not constellation_sats:
        raise ValueError(f"No satellites found for constellation: {selected_constellation}")
    
    # Cap constellation size to 100 satellites
    if len(constellation_sats) > 100:
        constellation_sats = random.sample(constellation_sats, 100)
    
    # Compute average inclination
    avg_inclination = compute_average_inclination(constellation_sats)
    
    # Filter cities by latitude compatibility
    compatible_cities = filter_cities_by_inclination(all_cities, avg_inclination, margin=15.0)
    
    # Sort by population (descending)
    compatible_cities.sort(key=lambda c: c["population"], reverse=True)
    
    # Select targets
    num_targets = max(1, len(constellation_sats) // 3)
    selected_cities = ensure_global_distribution(compatible_cities, num_targets, seed=seed)
    
    # Filter stations by latitude compatibility
    compatible_stations = filter_cities_by_inclination(all_stations, avg_inclination, margin=15.0)
    
    # Select station pairs
    num_pairs = 3
    station_pairs = select_station_pairs(compatible_stations, num_pairs, min_distance_km=3000.0)
    
    # Get unique stations from pairs
    selected_stations = []
    for station_a, station_b in station_pairs:
        if station_a not in selected_stations:
            selected_stations.append(station_a)
        if station_b not in selected_stations:
            selected_stations.append(station_b)
    
    # Generate random 6-hour time windows for each pair
    # Parse horizon times to generate windows within the horizon
    from datetime import datetime, timedelta
    horizon_start_dt = datetime.fromisoformat(horizon_start.replace('Z', '+00:00'))
    horizon_end_dt = datetime.fromisoformat(horizon_end.replace('Z', '+00:00'))
    total_hours = (horizon_end_dt - horizon_start_dt).total_seconds() / 3600
    
    station_pair_requirements = []
    for station_a, station_b in station_pairs:
        # Random start time within horizon (leaving room for 6-hour window)
        random_offset_hours = random.uniform(0, total_hours -6)
        window_start_dt = horizon_start_dt + timedelta(hours=random_offset_hours)
        window_end_dt = window_start_dt + timedelta(hours=6)
        
        station_pair_requirements.append({
            "station_a": station_a["id"],
            "station_b": station_b["id"],
            "time_window_start": window_start_dt.isoformat().replace('+00:00', 'Z'),
            "time_window_end": window_end_dt.isoformat().replace('+00:00', 'Z'),
        })
    
    # Generate requirements
    required_observations = {}
    for city in selected_cities:
        required_observations[city["id"]] = random.randint(2, 5)
    
    requirements = {
        "meta": {
            "case_id": case_id,
            "benchmark_type": "latency-optimization",
            "seed": seed,
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
        },
        "latency_optimization": {
            "target_ids": [c["id"] for c in selected_cities],
            "station_pairs": station_pair_requirements,
            "required_observations": required_observations,
        },
    }
    
    # Write all case files
    write_manifest(
        output_dir,
        case_id,
        "latency-optimization",
        seed,
        horizon_start,
        horizon_end,
        len(constellation_sats),
        len(selected_cities),
        len(selected_stations),
    )
    write_satellites_yaml(output_dir, constellation_sats)
    write_targets_yaml(output_dir, selected_cities)
    write_stations_yaml(output_dir, selected_stations)
    write_requirements_yaml(output_dir, requirements)
    write_initial_plan(output_dir, horizon_start, horizon_end)
    
    # Render mission brief
    template_path = Path(__file__).parent / "mission_brief.md.template"
    constellation_names = selected_constellation
    
    # Format requirements
    metrics_list = """
1.  **Communication Latency**: The average and maximum communication latency (signal propagation delay) between designated station pairs during their priority windows (minimized).
2.  **Target Coverage**: The percentage of required observations completed for ground targets (maximized).
3.  **Plan Validity**: Your plan must satisfy all physical constraints (battery, storage, terminal limits).
"""

    targets_formatted = "### Target Cities (Priority Observation Quotas)\n\n"
    targets_formatted += "The following cities must be observed the specified number of times to fulfill mission requirements:\n\n"
    for city in selected_cities:
        req_count = required_observations[city["id"]]
        targets_formatted += f"- **{city['name']}** (ID: `{city['id']}`): Requires **{req_count}** observations\n"
        
    pairs_formatted = "### Station Priority Windows (Low-Latency Link Requests)\n\n"
    pairs_formatted += "You must establish the most direct communication path possible between these station pairs during the specified windows:\n\n"
    for i, req in enumerate(station_pair_requirements, 1):
        pairs_formatted += f"{i}. **{req['station_a']}** ↔ **{req['station_b']}**\n"
        pairs_formatted += f"   - **Window**: {req['time_window_start']} to {req['time_window_end']}\n"
        pairs_formatted += f"   - **Objective**: Minimize Latency\n"

    render_mission_brief(
        template_path,
        output_dir,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        constellation_names=constellation_names,
        num_satellites=len(constellation_sats),
        num_targets=len(selected_cities),
        num_station_pairs=len(station_pair_requirements),
        metrics_list=metrics_list,
        targets_list=targets_formatted,
        station_pairs_list=pairs_formatted,
    )


if __name__ == "__main__":
    # Example usage
    generate_case(
        case_id="case_0001",
        output_dir=Path("dataset/latency_optimization/cases/case_0001"),
        seed=42,
    )
