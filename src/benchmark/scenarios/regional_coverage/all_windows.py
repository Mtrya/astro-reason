"""Compute all access windows for regional_coverage benchmark."""

import time
from typing import List, Tuple, Callable, Any
from pathlib import Path
import yaml

from planner.scenario import Scenario
from planner.models import PlannerAccessWindow
from benchmark.scenarios.common_utils import shuffle_list, should_stop


def chunk_list(items: list, chunk_size: int = 1) -> list[list]:
    """Split a list into chunks of specified size."""
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def retry_on_connection_error(func: Callable, max_retries: int = 5, *args, **kwargs) -> Any:
    """Retry a function call on connection errors.

    Args:
        func: Function to call
        max_retries: Maximum number of retry attempts
        *args, **kwargs: Arguments to pass to func

    Returns:
        Result of successful function call

    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4, 8, 16 seconds
                print(f"Connection error on attempt {attempt + 1}/{max_retries}: {e}")
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"Failed after {max_retries} attempts")

    raise last_exception


def _generate_strips_for_polygon(
    polygon_id: str,
    vertices: List[Tuple[float, float]],
    num_strips: int = 5,
) -> List[dict]:
    """Generate horizontal and vertical strip decompositions for a polygon.
    
    Args:
        polygon_id: ID of the polygon
        vertices: List of (lat, lon) vertices
        num_strips: Number of strips per orientation
        
    Returns:
        List of strip dicts suitable for register_strips()
    """
    lats = [v[0] for v in vertices]
    lons = [v[1] for v in vertices]
    
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    
    strips = []
    
    lat_step = (max_lat - min_lat) / num_strips
    for i in range(num_strips):
        lat = min_lat + (i + 0.5) * lat_step
        strips.append({
            "id": f"{polygon_id}_h{i}",
            "name": f"{polygon_id} horizontal strip {i}",
            "points": [(lat, min_lon), (lat, max_lon)],
        })
    
    lon_step = (max_lon - min_lon) / num_strips
    for i in range(num_strips):
        lon = min_lon + (i + 0.5) * lon_step
        strips.append({
            "id": f"{polygon_id}_v{i}",
            "name": f"{polygon_id} vertical strip {i}",
            "points": [(min_lat, lon), (max_lat, lon)],
        })
    
    return strips


def compute_all_windows(
    scenario: Scenario,
    case_path: Path | None = None,
    max_observation_windows: int | None = None,
    max_downlink_windows: int | None = None,
    shuffle_seed: int | None = None,
) -> List[PlannerAccessWindow]:
    """Compute strip and downlink windows for the scenario.

    Args:
        scenario: Loaded Scenario instance
        case_path: Path to case directory (needed to load requirements.yaml)
        max_observation_windows: Maximum observation windows to compute (None for unlimited)
        max_downlink_windows: Maximum downlink windows to compute (None for unlimited)
        shuffle_seed: Random seed for shuffling strips/stations (None for no shuffle)

    Returns:
        List of PlannerAccessWindow objects for:
        - sat→strip (observation windows)
        - sat→station (downlink windows)
    """
    if case_path is None:
        raise ValueError("case_path is required for regional_coverage benchmark")

    with open(case_path / "requirements.yaml") as f:
        requirements = yaml.safe_load(f)

    polygons = requirements.get("regional_coverage", {}).get("polygons", [])

    all_strips = []
    for polygon in polygons:
        polygon_id = polygon["id"]
        vertices = [(v[0], v[1]) for v in polygon["vertices"]]
        all_strips.extend(_generate_strips_for_polygon(polygon_id, vertices))

    scenario.register_strips(all_strips)

    sat_ids = list(scenario.satellites.keys())
    strip_ids = shuffle_list(list(scenario.strips.keys()), shuffle_seed)
    station_ids = shuffle_list(list(scenario.stations.keys()), shuffle_seed)

    all_windows: List[PlannerAccessWindow] = []
    obs_count = 0
    dl_count = 0

    # Compute strip observation windows with limit
    stop_obs = False
    for sat_id in sat_ids:
        if stop_obs:
            break

        for strip_id in strip_ids:
            if should_stop(obs_count, max_observation_windows):
                stop_obs = True
                break

            windows = retry_on_connection_error(
                scenario.compute_strip_windows,
                5,
                sat_ids=[sat_id],
                strip_ids=[strip_id],
            )
            all_windows.extend(windows)
            obs_count += len(windows)

    # Compute downlink windows with limit
    stop_dl = False
    for sat_id in sat_ids:
        if stop_dl:
            break

        if station_ids and not should_stop(dl_count, max_downlink_windows):
            for station_chunk in chunk_list(station_ids, 10):
                windows = retry_on_connection_error(
                    scenario.compute_access_windows,
                    5,
                    sat_ids=[sat_id],
                    station_ids=station_chunk,
                )
                all_windows.extend(windows)
                dl_count += len(windows)

                if should_stop(dl_count, max_downlink_windows):
                    stop_dl = True
                    break

    return scenario.register_windows(all_windows)
