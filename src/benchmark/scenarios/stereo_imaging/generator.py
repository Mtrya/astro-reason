"""Generate stereo-imaging benchmark cases.

This module creates test cases for the stereo-imaging benchmark by:
- Selecting satellites from high-agility constellations
- Choosing target cities for stereo pair opportunities
- Generating requirements with stereo constraints
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



CONSTELLATIONS = ["SPOT", "ALOS", "WORLDVIEW", "TERRASAR", "TANDEM", "ZIYUAN", "GAOFEN"]


def generate_case(
    case_id: str,
    output_dir: Path,
    seed: int = 42,
    horizon_start: str = "2025-07-17T12:00:00Z",
    horizon_end: str = "2025-07-21T12:00:00Z",
    min_azimuth_sep_deg: float = 15.0,
    max_azimuth_sep_deg: float = 60.0,
    max_time_between_obs_hours: float = 2.0,
    min_elevation_deg: float = 30.0,
) -> None:
    """Generate a stereo-imaging benchmark case.
    
    Args:
        case_id: Unique case identifier (e.g., "case_0001")
        output_dir: Directory to write case files
        seed: Random seed for reproducibility
        horizon_start: Mission horizon start time (ISO 8601)
        horizon_end: Mission horizon end time (ISO 8601)
        min_azimuth_sep_deg: Minimum azimuth separation for stereo pairs
        max_azimuth_sep_deg: Maximum azimuth separation for stereo pairs
        max_time_between_obs_hours: Maximum time between stereo observations
        min_elevation_deg: Minimum elevation for valid observations
    """
    random.seed(seed)
    
    # Load archived databases
    all_satellites = load_archived_satellites()
    all_cities = load_archived_targets()
    all_stations = load_archived_stations()
    
    # Filter satellites by constellation
    # Sample THREE constellations for this case to increase variety
    selected_constellations = random.sample(CONSTELLATIONS, 3)
    # Filter satellites by constellation (capped at 100)
    constellation_sats = filter_satellites_by_constellation(all_satellites, selected_constellations, max_limit=100)
    
    if not constellation_sats:
        raise ValueError(f"No satellites found for constellations: {CONSTELLATIONS}")
    
    # Compute average inclination
    avg_inclination = compute_average_inclination(constellation_sats)
    
    # Filter cities by latitude compatibility
    compatible_cities = filter_cities_by_inclination(all_cities, avg_inclination, margin=15.0)
    
    # Sort by population (descending)
    compatible_cities.sort(key=lambda c: c["population"], reverse=True)
    
    # Select more targets than revisit (for agility testing)
    num_targets = max(1, len(constellation_sats))
    selected_cities = ensure_global_distribution(compatible_cities, num_targets, seed=seed)
    
    # Select ground stations
    num_stations = min(5, len(all_stations))
    selected_stations = random.sample(all_stations, num_stations)
    
    # Generate requirements - all targets need minimum 2 observations for stereo
    required_observations = {}
    for city in selected_cities:
        required_observations[city["id"]] = 2
    
    requirements = {
        "meta": {
            "case_id": case_id,
            "benchmark_type": "stereo-imaging",
            "seed": seed,
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
        },
        "stereo_imaging": {
            "target_ids": [c["id"] for c in selected_cities],
            "min_azimuth_sep_deg": min_azimuth_sep_deg,
            "max_azimuth_sep_deg": max_azimuth_sep_deg,
            "max_time_between_obs_hours": max_time_between_obs_hours,
            "min_elevation_deg": min_elevation_deg,
            "required_observations": required_observations,
        },
    }
    
    # Write all case files
    write_manifest(
        output_dir,
        case_id,
        "stereo-imaging",
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
    constellation_names = ", ".join(selected_constellations)
    
    # Format requirements
    metrics_list = """
1.  **Stereo Yield**: The percentage of high-value targets for which at least one valid stereo pair (two observations meeting angle/time constraints) is successfully acquired.
2.  **Plan Validity**: Your plan must satisfy all physical constraints (battery, storage, slew time).
"""

    targets_formatted = "### Stereo Target List (High-Priority)\n\n"
    targets_formatted += "For each target below, you must attempt to collect a **stereo pair**. A valid pair consists of two observations that satisfy the following physical constraints:\n\n"
    targets_formatted += f"**Physical Constraints for Stereo Pairs**:\n"
    targets_formatted += f"- **Azimuth Separation**: Between {min_azimuth_sep_deg}° and {max_azimuth_sep_deg}°\n"
    targets_formatted += f"- **Max Temporal Gap**: {max_time_between_obs_hours} hours between the two observations\n"
    targets_formatted += f"- **Min Elevation**: {min_elevation_deg}°\n\n"
    
    for city in selected_cities:
        targets_formatted += f"- **{city['name']}** (ID: `{city['id']}`)\n"
        targets_formatted += f"  - Location: {city['latitude_deg']:.2f}°, {city['longitude_deg']:.2f}°\n"

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
        output_dir=Path("dataset/stereo_imaging/cases/case_0001"),
        seed=42,
    )



if __name__ == "__main__":
    # Example usage
    generate_case(
        case_id="case_0001",
        output_dir=Path("dataset/stereo_imaging/cases/case_0001"),
        seed=42,
    )
