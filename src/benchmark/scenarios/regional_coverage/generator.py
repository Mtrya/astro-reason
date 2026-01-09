"""Generate regional-coverage benchmark cases.

This module creates test cases for the regional-coverage benchmark by:
- Selecting satellites from high-resolution imaging constellations
- Choosing polygons representing geographic regions
- Generating requirements for regional coverage
"""

from pathlib import Path
from typing import List, Dict, Any
import random
import yaml

from benchmark.utils.catalog_loader import load_archived_satellites, load_archived_targets, load_archived_stations
from benchmark.utils.generator_helpers import (
    filter_satellites_by_constellation,
    write_manifest,
    write_satellites_yaml,
    write_targets_yaml,
    write_stations_yaml,
    write_requirements_yaml,
    write_initial_plan,
    render_mission_brief,
)



CONSTELLATIONS = ["SKYSAT", "ICEYE"]


def load_polygons() -> List[Dict[str, Any]]:
    """Load hardcoded polygons from config.
    
    Returns:
        List of polygon dictionaries
    """
    config_dir = Path(__file__).parent.parent.parent / "config"
    polygon_path = config_dir / "hardcoded_polygons.yaml"
    
    with open(polygon_path) as f:
        polygons = yaml.safe_load(f)
    
    return polygons


def select_polygons(num_polygons: int = 5, seed: int = None) -> List[Dict[str, Any]]:
    """Select polygons ensuring diversity in vertex count.
    
    Args:
        num_polygons: Number of polygons to select
        seed: Random seed for reproducibility
        
    Returns:
        Selected polygons with diverse vertex counts
    """
    if seed is not None:
        random.seed(seed)
    
    all_polygons = load_polygons()
    
    # Group by vertex count
    by_vertex_count = {}
    for polygon in all_polygons:
        vertex_count = len(polygon["vertices"])
        if vertex_count not in by_vertex_count:
            by_vertex_count[vertex_count] = []
        by_vertex_count[vertex_count].append(polygon)
    
    # Ensure diversity: try to get polygons with different vertex counts (4, 5, 6, 7)
    selected = []
    target_vertex_counts = [4, 5, 6, 7]
    
    # First, try to get one from each vertex count
    for vc in target_vertex_counts:
        if vc in by_vertex_count and by_vertex_count[vc]:
            selected.append(random.choice(by_vertex_count[vc]))
            if len(selected) >= num_polygons:
                break
    
    # If we need more, sample randomly from remaining
    if len(selected) < num_polygons:
        remaining = [p for p in all_polygons if p not in selected]
        additional = min(num_polygons - len(selected), len(remaining))
        selected.extend(random.sample(remaining, additional))
    
    return selected[:num_polygons]


def generate_case(
    case_id: str,
    output_dir: Path,
    seed: int = 42,
    horizon_start: str = "2025-07-17T12:00:00Z",
    horizon_end: str = "2025-07-21T12:00:00Z",
    num_polygons: int = 3,
) -> None:
    """Generate a regional-coverage benchmark case.
    
    Args:
        case_id: Unique case identifier (e.g., "case_0001")
        output_dir: Directory to write case files
        seed: Random seed for reproducibility
        horizon_start: Mission horizon start time (ISO 8601)
        horizon_end: Mission horizon end time (ISO 8601)
        num_polygons: Number of polygons to include
    """
    random.seed(seed)
    
    # Load archived databases
    all_satellites = load_archived_satellites()
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
    
    # Select polygons
    selected_polygons = select_polygons(num_polygons, seed=seed)
    
    # Select ground stations
    num_stations = min(5, len(all_stations))
    selected_stations = random.sample(all_stations, num_stations)
    
    # Build requirements with polygons
    polygon_requirements = []
    for polygon in selected_polygons:
        polygon_requirements.append({
            "id": polygon["id"],
            "vertices": polygon["vertices"],
        })
    
    requirements = {
        "meta": {
            "case_id": case_id,
            "benchmark_type": "regional-coverage",
            "seed": seed,
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
        },
        "regional_coverage": {
            "polygons": polygon_requirements,
        },
    }
    
    # Write all case files
    write_manifest(
        output_dir,
        case_id,
        "regional-coverage",
        seed,
        horizon_start,
        horizon_end,
        len(constellation_sats),
        0,  # No explicit targets for regional coverage
        len(selected_stations),
    )
    write_satellites_yaml(output_dir, constellation_sats)
    write_targets_yaml(output_dir, [])  # Empty targets list
    write_stations_yaml(output_dir, selected_stations)
    write_requirements_yaml(output_dir, requirements)
    write_initial_plan(output_dir, horizon_start, horizon_end)
    
    # Render mission brief
    template_path = Path(__file__).parent / "mission_brief.md.template"
    constellation_names = selected_constellation
    
    # Format requirements
    metrics_list = """
1.  **Polygon Coverage**: The total percentage of the area within the priority polygons that is covered by at least one valid observation strip (maximized).
2.  **Plan Validity**: Your plan must satisfy all physical constraints (battery, storage, slew time).
"""

    polygons_formatted = "### Priority Geographic Regions (Polygons)\n\n"
    polygons_formatted += "The following polygons represent the areas of interest for this mission. You must plan observation strips to cover as much area as possible within these boundaries:\n\n"
    for polygon in selected_polygons:
        polygons_formatted += f"- **{polygon['name']}** (ID: `{polygon['id']}`)\n"
        polygons_formatted += "  - **Vertices** (Lat, Lon):\n"
        for v in polygon["vertices"]:
            polygons_formatted += f"    - ({v[0]:.4f}, {v[1]:.4f})\n"
        polygons_formatted += "\n"

    render_mission_brief(
        template_path,
        output_dir,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        constellation_names=constellation_names,
        num_satellites=len(constellation_sats),
        num_polygons=len(selected_polygons),
        metrics_list=metrics_list,
        polygons_list=polygons_formatted,
    )


if __name__ == "__main__":
    # Example usage
    generate_case(
        case_id="case_0001",
        output_dir=Path("dataset/regional_coverage/cases/case_0001"),
        seed=42,
    )
