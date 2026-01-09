"""Helper functions for benchmark case generators.

This module provides shared utility functions for all benchmark generators:
- Filtering satellites and targets
- Ensuring global distribution
- Writing case files (YAML, JSON, markdown)
"""

from pathlib import Path
from typing import Any, Dict, List
import json
import random
import yaml


def filter_satellites_by_constellation(
    satellites: List[Dict[str, Any]], constellations: List[str], max_limit: int = None
) -> List[Dict[str, Any]]:
    """Filter satellites by constellation names.
    
    Args:
        satellites: List of all satellite dictionaries
        constellations: List of constellation names to filter by
        max_limit: Maximum number of satellites to return (optional)
        
    Returns:
        Filtered list of satellites matching any of the constellations
    """
    filtered = []
    for sat in satellites:
        for const in constellations:
            if const.upper() in sat["constellation"].upper():
                filtered.append(sat)
                break
    
    if max_limit is not None and len(filtered) > max_limit:
        return random.sample(filtered, max_limit)
        
    return filtered


def compute_average_inclination(satellites: List[Dict[str, Any]]) -> float:
    """Compute average inclination of a satellite constellation.
    
    Args:
        satellites: List of satellite dictionaries
        
    Returns:
        Average inclination in degrees
    """
    if not satellites:
        return 0.0
    return sum(sat["inclination_deg"] for sat in satellites) / len(satellites)


def filter_cities_by_inclination(
    cities: List[Dict[str, Any]], inclination_deg: float, margin: float = 5.0
) -> List[Dict[str, Any]]:
    """Filter cities by latitude compatibility with satellite inclination.
    
    Args:
        cities: List of all city dictionaries
        inclination_deg: Satellite constellation inclination
        margin: Safety margin in degrees (default 5.0)
        
    Returns:
        Cities within satellite ground track
    """
    max_lat = inclination_deg - margin
    return [c for c in cities if abs(c["latitude_deg"]) <= max_lat]


def ensure_global_distribution(
    cities: List[Dict[str, Any]], num_samples: int, seed: int = None
) -> List[Dict[str, Any]]:
    """Sample cities to ensure global distribution across lat/lon bins.
    
    Creates a 4x4 grid of lat/lon bins and samples proportionally from each bin.
    
    Args:
        cities: List of city dictionaries to sample from
        num_samples: Number of cities to select
        seed: Random seed for reproducibility
        
    Returns:
        Globally distributed sample of cities
    """
    if seed is not None:
        random.seed(seed)
    
    if len(cities) <= num_samples:
        return cities
    
    # Create 4x4 lat/lon grid
    lat_bins = 4
    lon_bins = 4
    bins: Dict[tuple, List[Dict[str, Any]]] = {}
    
    for city in cities:
        lat_idx = int((city["latitude_deg"] + 90) / 180 * lat_bins)
        lon_idx = int((city["longitude_deg"] + 180) / 360 * lon_bins)
        lat_idx = min(lat_idx, lat_bins - 1)
        lon_idx = min(lon_idx, lon_bins - 1)
        
        key = (lat_idx, lon_idx)
        if key not in bins:
            bins[key] = []
        bins[key].append(city)
    
    # Sample from each bin proportionally
    selected = []
    non_empty_bins = [b for b in bins.values() if b]
    samples_per_bin = max(1, num_samples // len(non_empty_bins))
    
    for bin_cities in non_empty_bins:
        sample_count = min(samples_per_bin, len(bin_cities))
        selected.extend(random.sample(bin_cities, sample_count))
    
    # If we haven't reached num_samples, add more randomly
    if len(selected) < num_samples:
        remaining = [c for c in cities if c not in selected]
        additional = min(num_samples - len(selected), len(remaining))
        selected.extend(random.sample(remaining, additional))
    
    return selected[:num_samples]


def write_manifest(
    output_dir: Path,
    case_id: str,
    benchmark_type: str,
    seed: int,
    horizon_start: str,
    horizon_end: str,
    num_satellites: int,
    num_targets: int,
    num_stations: int = 0,
) -> None:
    """Write manifest.json file.
    
    Args:
        output_dir: Output directory
        case_id: Unique case identifier
        benchmark_type: Type of benchmark
        seed: Random seed used
        horizon_start: Mission start time (ISO 8601)
        horizon_end: Mission end time (ISO 8601)
        num_satellites: Number of satellites
        num_targets: Number of targets
        num_stations: Number of stations (default 0)
    """
    manifest = {
        "case_id": case_id,
        "benchmark_type": benchmark_type,
        "seed": seed,
        "horizon_start": horizon_start,
        "horizon_end": horizon_end,
        "num_satellites": num_satellites,
        "num_targets": num_targets,
        "num_stations": num_stations,
    }
    
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)


def write_satellites_yaml(output_dir: Path, satellites: List[Dict[str, Any]]) -> None:
    """Write satellites.yaml file.
    
    Args:
        output_dir: Output directory
        satellites: List of satellite dictionaries
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "satellites.yaml", "w") as f:
        yaml.safe_dump(satellites, f, sort_keys=False)


def write_targets_yaml(output_dir: Path, targets: List[Dict[str, Any]]) -> None:
    """Write targets.yaml file.
    
    Args:
        output_dir: Output directory
        targets: List of target dictionaries
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "targets.yaml", "w") as f:
        yaml.safe_dump(targets, f, sort_keys=False)


def write_stations_yaml(output_dir: Path, stations: List[Dict[str, Any]]) -> None:
    """Write stations.yaml file.
    
    Args:
        output_dir: Output directory
        stations: List of station dictionaries
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "stations.yaml", "w") as f:
        yaml.safe_dump(stations, f, sort_keys=False)


def write_requirements_yaml(output_dir: Path, requirements: Dict[str, Any]) -> None:
    """Write requirements.yaml file.
    
    Args:
        output_dir: Output directory
        requirements: Requirements dictionary
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "requirements.yaml", "w") as f:
        yaml.safe_dump(requirements, f, sort_keys=False)


def write_initial_plan(output_dir: Path, horizon_start: str = None, horizon_end: str = None) -> None:
    """Write initial_plan.json file with horizon metadata.
    
    Args:
        output_dir: Output directory
        horizon_start: Mission start time (ISO 8601), optional
        horizon_end: Mission end time (ISO 8601), optional
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plan_data = {}
    if horizon_start and horizon_end:
        plan_data["metadata"] = {
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
        }
    
    with open(output_dir / "initial_plan.json", "w") as f:
        json.dump(plan_data, f, indent=2)


def render_mission_brief(
    template_path: Path, output_dir: Path, **template_vars
) -> None:
    """Render mission_brief.md from template using Python string formatting.
    
    Template variables should be in {variable_name} format.
    
    Args:
        template_path: Path to mission_brief.md.template
        output_dir: Output directory
        **template_vars: Variables to substitute in template
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(template_path) as f:
        template_content = f.read()
    
    # Use Python's format() for variable substitution
    rendered = template_content.format(**template_vars)
    
    with open(output_dir / "mission_brief.md", "w") as f:
        f.write(rendered)
