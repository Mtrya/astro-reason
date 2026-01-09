"""Compute all access windows for latency_optimization benchmark."""

import time
from typing import List, Callable, Any
from planner.scenario import Scenario
from planner.models import PlannerAccessWindow
from benchmark.scenarios.common_utils import shuffle_list, should_stop


def chunk_list(items: list, chunk_size: int = 10) -> list[list]:
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


def compute_all_windows(
    scenario: Scenario,
    max_observation_windows: int | None = None,
    max_downlink_windows: int | None = None,
    max_isl_windows: int | None = None,
    shuffle_seed: int | None = None,
) -> List[PlannerAccessWindow]:
    """Compute observation, downlink, and ISL windows for the scenario.

    Args:
        scenario: Loaded Scenario instance
        max_observation_windows: Maximum observation windows to compute (None for unlimited)
        max_downlink_windows: Maximum downlink windows to compute (None for unlimited)
        max_isl_windows: Maximum ISL windows to compute (None for unlimited)
        shuffle_seed: Random seed for shuffling targets/stations/peers (None for no shuffle)

    Returns:
        List of PlannerAccessWindow objects for:
        - sat→target (observation windows)
        - sat→station (downlink windows)
        - sat→sat (ISL windows)
    """
    sat_ids = list(scenario.satellites.keys())
    target_ids = shuffle_list(list(scenario.targets.keys()), shuffle_seed)
    station_ids = shuffle_list(list(scenario.stations.keys()), shuffle_seed)

    all_windows: List[PlannerAccessWindow] = []
    obs_count = 0
    dl_count = 0
    isl_count = 0

    # Compute observation windows with limit
    stop_obs = False
    for sat_id in sat_ids:
        if stop_obs:
            break

        if target_ids and not should_stop(obs_count, max_observation_windows):
            for target_chunk in chunk_list(target_ids, 10):
                windows = retry_on_connection_error(
                    scenario.compute_access_windows,
                    5,
                    sat_ids=[sat_id],
                    target_ids=target_chunk,
                )
                all_windows.extend(windows)
                obs_count += len(windows)

                if should_stop(obs_count, max_observation_windows):
                    stop_obs = True
                    break

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

    # Compute ISL windows with limit
    stop_isl = False
    for sat_id in sat_ids:
        if stop_isl:
            break

        peer_ids = [s for s in sat_ids if s != sat_id]
        peer_ids = shuffle_list(peer_ids, shuffle_seed)

        if peer_ids and not should_stop(isl_count, max_isl_windows):
            for peer_chunk in chunk_list(peer_ids, 1):
                windows = retry_on_connection_error(
                    scenario.compute_access_windows,
                    5,
                    sat_ids=[sat_id],
                    peer_satellite_ids=peer_chunk,
                )
                all_windows.extend(windows)
                isl_count += len(windows)

                if should_stop(isl_count, max_isl_windows):
                    stop_isl = True
                    break

    return scenario.register_windows(all_windows)
