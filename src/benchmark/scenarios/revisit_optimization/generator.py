"""Generate revisit-optimization benchmark cases.

This module creates test cases for the revisit-optimization benchmark by:
- Selecting satellites from weather/Earth observation constellations
- Choosing target cities based on latitude compatibility
- Generating requirements with revisit gap constraints
"""

from pathlib import Path
from typing import List
import random

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



CONSTELLATIONS = ["METEOR", "FENGYUN", "NOAA", "COSMOS", "YAOGAN", "DMSP"]


def generate_case(
    case_id: str,
    output_dir: Path,
    seed: int = 42,
    horizon_start: str = "2025-07-17T12:00:00Z",
    horizon_end: str = "2025-07-21T12:00:00Z",
) -> None:
    """Generate a revisit-optimization benchmark case.
    
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
    
    # Select top N cities with global distribution
    num_targets = max(2, len(constellation_sats) // 4)
    selected_cities = ensure_global_distribution(compatible_cities, num_targets, seed=seed)
    
    # Split cities into monitoring and mapping
    random.shuffle(selected_cities)
    num_monitoring = max(1, len(selected_cities) // 2)
    monitoring_cities = selected_cities[:num_monitoring]
    mapping_cities = selected_cities[num_monitoring:]
    
    # Select a few ground stations for downlink
    num_stations = min(5, len(all_stations))
    selected_stations = random.sample(all_stations, num_stations)
    
    # Generate requirements
    mapping_requirements = {}
    for city in mapping_cities:
        mapping_requirements[city["id"]] = random.randint(2, 4)
    
    requirements = {
        "meta": {
            "case_id": case_id,
            "benchmark_type": "revisit-optimization",
            "seed": seed,
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
        },
        "revisit_optimization": {
            "monitoring_targets": [c["id"] for c in monitoring_cities],
            "mapping_targets": mapping_requirements,
        },
    }
    
    # Write all case files
    write_manifest(
        output_dir,
        case_id,
        "revisit-optimization",
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
    
    # Format requirements for brief
    metrics_list = """
1.  **Monitoring Quality (Revisit Gap)**: For high-priority monitoring targets, minimize the maximum and average time gaps between consecutive observations. Smaller gaps indicate better responsiveness.
2.  **Mapping Completeness (Coverage Ratio)**: For mapping targets, ensure at least the required number of observations are completed.
3.  **Plan Validity**: Your plan must satisfy all physical constraints (battery, storage, slew time).
"""

    targets_formatted = "### Monitoring Targets (Continuous Monitoring Required)\n\n"
    targets_formatted += "These targets require continuous monitoring. Your goal is to **minimize the revisit gap** (time between any two consecutive observations) as much as possible.\n\n"
    targets_formatted += "Note: The revisit gap calculation includes the time from the start of the mission to the first observation, and from the last observation to the end of the mission horizon.\n\n"
    for city in monitoring_cities:
        targets_formatted += f"- **{city['name']}** (ID: `{city['id']}`)\n"
        targets_formatted += f"  - Location: {city['latitude_deg']:.2f}°, {city['longitude_deg']:.2f}°\n"
        targets_formatted += f"  - Objective: Minimize Revisit Gap\n"

    targets_formatted += "\n### Mapping Targets (Quota-based Observations)\n\n"
    targets_formatted += "These targets require a minimum number of successful observations during the mission horizon.\n\n"
    for city in mapping_cities:
        req_count = mapping_requirements[city["id"]]
        targets_formatted += f"- **{city['name']}** (ID: `{city['id']}`)\n"
        targets_formatted += f"  - Location: {city['latitude_deg']:.2f}°, {city['longitude_deg']:.2f}°\n"
        targets_formatted += f"  - Required Observations: {req_count}\n"

    render_mission_brief(
        template_path,
        output_dir,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        constellation_names=constellation_names,
        num_satellites=len(constellation_sats),
        num_targets=len(selected_cities),
        metrics_list=metrics_list,
        targets_list=targets_formatted,
    )


if __name__ == "__main__":
    # Example usage
    generate_case(
        case_id="case_0001",
        output_dir=Path("dataset/revisit_optimization/cases/case_0001"),
        seed=42,
    )
