"""Geometry and routing helpers for the relay_constellation visualizer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import heapq
import math

import brahe
import numpy as np

from .io import RelayCase, RelayDemand, RelayEndpoint


_BRAHE_EOP_INITIALIZED = False
_LIGHT_SPEED_M_S = 299_792_458.0


@dataclass(frozen=True)
class RouteInterval:
    pair_id: str
    source_endpoint_id: str
    destination_endpoint_id: str
    start_time: datetime
    end_time: datetime
    route_nodes: tuple[str, ...]
    total_path_length_m: float
    latency_ms: float


@dataclass(frozen=True)
class ConnectivityPairSummary:
    pair_id: str
    source_endpoint_id: str
    destination_endpoint_id: str
    demand_windows: tuple[tuple[datetime, datetime], ...]
    route_intervals: tuple[RouteInterval, ...]
    route_intervals_overlapping_demands: tuple[RouteInterval, ...]
    requested_sample_count: int
    served_sample_count: int


def _ensure_brahe_ready() -> None:
    """
    Ensure BRAHE's global Earth Orientation Parameters (EOP) provider is initialized exactly once.
    
    This function is idempotent: if the provider is already set it returns immediately; otherwise it installs a static zero-based EOP provider and marks initialization complete.
    """
    global _BRAHE_EOP_INITIALIZED
    if _BRAHE_EOP_INITIALIZED:
        return
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    _BRAHE_EOP_INITIALIZED = True


def _datetime_to_epoch(value: datetime) -> brahe.Epoch:
    """
    Convert a timezone-aware datetime to a BRAHE Epoch in UTC.
    
    Parameters:
        value (datetime): A timezone-aware datetime; its instant will be converted to UTC before constructing the epoch.
    
    Returns:
        brahe.Epoch: An epoch representing the same instant in UTC.
    """
    value = value.astimezone(UTC)
    second = float(value.second) + (value.microsecond / 1_000_000.0)
    return brahe.Epoch.from_datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        second,
        0.0,
        brahe.TimeSystem.UTC,
    )


def _sample_times(start: datetime, end: datetime, step_s: int) -> list[datetime]:
    """
    Generate a list of datetimes from start (inclusive) to end (exclusive) separated by step_s seconds.
    
    Parameters:
    	start (datetime): Inclusive start of the sampling interval.
    	end (datetime): Exclusive end of the sampling interval.
    	step_s (int): Step size in seconds between consecutive samples.
    
    Returns:
    	list[datetime]: Ordered datetimes beginning at `start`, each incremented by `step_s` seconds, where every returned instant is strictly less than `end`.
    """
    times: list[datetime] = []
    current = start
    delta = timedelta(seconds=step_s)
    while current < end:
        times.append(current)
        current = current + delta
    return times


def _sample_times_for_windows(
    windows: tuple[tuple[datetime, datetime], ...],
    *,
    step_s: int,
) -> list[datetime]:
    """
    Sample datetimes across multiple time windows at fixed step intervals.
    
    For each (start, end) window this produces instants beginning at `start` and advancing by `step_s` seconds while the instant is strictly less than `end`. Instants that fall in overlapping windows are deduplicated; the returned list is sorted in ascending order.
    
    Parameters:
        windows (tuple[tuple[datetime, datetime], ...]): Iterable of (start, end) time windows.
        step_s (int): Sampling step in seconds.
    
    Returns:
        list[datetime]: Sorted list of sampled datetimes (each in [start, end) for its window).
    """
    sampled: list[datetime] = []
    seen: set[datetime] = set()
    step = timedelta(seconds=step_s)
    for start_time, end_time in sorted(windows):
        current = start_time
        while current < end_time:
            if current not in seen:
                seen.add(current)
                sampled.append(current)
            current = current + step
    sampled.sort()
    return sampled


def sampled_times_for_demands(case: RelayCase) -> list[datetime]:
    """
    Produce routing sample instants covering all demand windows in the case.
    
    Builds time windows from each demand's start_time and end_time and samples each window at
    case.manifest.routing_step_s-second intervals. Overlapping windows produce deduplicated
    instants; the returned list is sorted in ascending order.
    
    Parameters:
        case (RelayCase): Relay case containing `demands` (with `start_time`/`end_time`)
            and `manifest.routing_step_s` used as the sampling interval.
    
    Returns:
        list[datetime]: Sorted datetimes sampled from all demand windows.
    """
    windows = tuple((demand.start_time, demand.end_time) for demand in case.demands)
    return _sample_times_for_windows(
        windows,
        step_s=case.manifest.routing_step_s,
    )


def _pair_id(source_endpoint_id: str, destination_endpoint_id: str) -> str:
    """
    Builds a stable identifier string for an ordered endpoint pair.
    
    Returns:
        str: Identifier in the format "source_endpoint_id->destination_endpoint_id".
    """
    return f"{source_endpoint_id}->{destination_endpoint_id}"


def _segment_clear_of_earth(point_a_m: np.ndarray, point_b_m: np.ndarray) -> bool:
    """
    Determine whether the straight-line segment between two ECEF points does not intersect or come within 1 meter of Earth's surface.
    
    Parameters:
        point_a_m (np.ndarray): 3-element ECEF position (meters) of the first endpoint.
        point_b_m (np.ndarray): 3-element ECEF position (meters) of the second endpoint.
    
    Returns:
        bool: `True` if every point along the line segment lies strictly farther than 1 meter above Earth's radius, `False` if the segment intersects or comes within 1 meter of Earth.
        
    Notes:
        - For segments whose length is effectively zero, the check reduces to whether `point_a_m` lies outside Earth's radius.
    """
    segment = point_b_m - point_a_m
    denom = float(np.dot(segment, segment))
    if denom <= 1e-9:
        return float(np.linalg.norm(point_a_m)) > float(brahe.R_EARTH)
    t = float(-np.dot(point_a_m, segment) / denom)
    t = max(0.0, min(1.0, t))
    closest = point_a_m + (t * segment)
    return float(np.linalg.norm(closest)) > float(brahe.R_EARTH) + 1.0


def _endpoint_visible(
    endpoint: RelayEndpoint,
    satellite_position_ecef_m: np.ndarray,
    *,
    max_ground_range_m: float | None,
) -> tuple[bool, float]:
    """
    Determine whether a ground endpoint is visible from a satellite position and return the slant range.
    
    Parameters:
        endpoint (RelayEndpoint): Endpoint providing `ecef_position_m` and `min_elevation_deg`.
        satellite_position_ecef_m (np.ndarray): Satellite ECEF position in meters.
        max_ground_range_m (float | None): Optional maximum allowable slant range in meters; if provided, visibility requires the slant range to be <= this value.
    
    Returns:
        tuple[bool, float]: A tuple whose first element is `True` if the endpoint's elevation as seen from the satellite is at least `endpoint.min_elevation_deg` and, when `max_ground_range_m` is provided, the slant range does not exceed it; `False` otherwise. The second element is the computed slant range in meters.
    """
    relative_enz = np.asarray(
        brahe.relative_position_ecef_to_enz(
            endpoint.ecef_position_m,
            satellite_position_ecef_m,
            brahe.EllipsoidalConversionType.GEODETIC,
        ),
        dtype=float,
    )
    azel = np.asarray(
        brahe.position_enz_to_azel(relative_enz, brahe.AngleFormat.DEGREES),
        dtype=float,
    )
    elevation_deg = float(azel[1])
    slant_range_m = float(azel[2])
    if elevation_deg < endpoint.min_elevation_deg:
        return False, slant_range_m
    if max_ground_range_m is not None and slant_range_m > max_ground_range_m:
        return False, slant_range_m
    return True, slant_range_m


def _isl_feasible(
    position_a_ecef_m: np.ndarray,
    position_b_ecef_m: np.ndarray,
    *,
    max_isl_range_m: float,
) -> tuple[bool, float]:
    """
    Determine whether a direct inter-satellite link (ISL) between two ECEF positions is allowed based on maximum range and clearance from Earth's surface.
    
    Parameters:
        position_a_ecef_m (np.ndarray): ECEF position of the first satellite in meters.
        position_b_ecef_m (np.ndarray): ECEF position of the second satellite in meters.
        max_isl_range_m (float): Maximum allowable ISL distance in meters.
    
    Returns:
        feasible (bool): `True` if the Euclidean distance between the positions is less than or equal to `max_isl_range_m` and the straight-line segment between them does not intersect or come within the Earth's surface margin; `False` otherwise.
        distance_m (float): The straight-line Euclidean distance between the two positions in meters.
    """
    distance_m = float(np.linalg.norm(position_b_ecef_m - position_a_ecef_m))
    if distance_m > max_isl_range_m:
        return False, distance_m
    return _segment_clear_of_earth(position_a_ecef_m, position_b_ecef_m), distance_m


def _build_propagators(case: RelayCase) -> dict[str, brahe.NumericalOrbitPropagator]:
    """
    Builds numerical orbit propagators for each backbone satellite and advances them to the case horizon end.
    
    Parameters:
        case (RelayCase): Relay scenario containing manifest epoch and horizon_end, and backbone_satellites with initial ECI states.
    
    Returns:
        dict[str, brahe.NumericalOrbitPropagator]: Mapping from satellite ID to a propagator initialized at the manifest epoch and propagated to the horizon end.
    """
    _ensure_brahe_ready()
    epoch = _datetime_to_epoch(case.manifest.epoch)
    horizon_end_epoch = _datetime_to_epoch(case.manifest.horizon_end)
    force_config = brahe.ForceModelConfig(
        gravity=brahe.GravityConfiguration.spherical_harmonic(2, 0)
    )
    propagators: dict[str, brahe.NumericalOrbitPropagator] = {}
    for satellite in case.backbone_satellites.values():
        propagator = brahe.NumericalOrbitPropagator.from_eci(
            epoch,
            satellite.state_eci_m_mps,
            force_config=force_config,
        )
        propagator.propagate_to(horizon_end_epoch)
        propagators[satellite.satellite_id] = propagator
    return propagators


def build_state_cache(case: RelayCase) -> tuple[list[datetime], dict[str, np.ndarray]]:
    """
    Build a time-ordered cache of satellites' ECEF positions sampled across the case horizon.
    
    Constructs a list of datetimes sampled from the case manifest's horizon start (inclusive) to horizon end (exclusive) at the manifest's routing step, and computes each backbone satellite's ECEF position at those instants.
    
    Parameters:
        case (RelayCase): Scenario containing manifest timing and backbone satellite definitions.
    
    Returns:
        tuple[list[datetime], dict[str, np.ndarray]]: A pair where the first element is the ordered list of sample datetimes, and the second is a mapping from satellite ID to an (N, 3) numpy array of ECEF positions (meters) corresponding to the sample times.
    """
    propagators = _build_propagators(case)
    sample_times = _sample_times(
        case.manifest.horizon_start,
        case.manifest.horizon_end,
        case.manifest.routing_step_s,
    )
    states_ecef_by_satellite: dict[str, np.ndarray] = {}
    for satellite_id, propagator in propagators.items():
        rows = np.zeros((len(sample_times), 3), dtype=float)
        for index, instant in enumerate(sample_times):
            epoch = _datetime_to_epoch(instant)
            state_eci = np.asarray(propagator.state(epoch), dtype=float)
            rows[index] = np.asarray(
                brahe.position_eci_to_ecef(epoch, state_eci[:3]),
                dtype=float,
            )
        states_ecef_by_satellite[satellite_id] = rows
    return sample_times, states_ecef_by_satellite


def build_state_cache_for_times(
    case: RelayCase,
    sample_times: list[datetime],
) -> tuple[list[datetime], dict[str, np.ndarray]]:
    """
    Build a cache of satellite ECEF positions sampled at the provided instants.
    
    Parameters:
        case (RelayCase): Relay scenario describing backbone satellites and propagation settings.
        sample_times (list[datetime]): List of timezone-aware datetimes at which to sample satellite positions.
    
    Returns:
        tuple[list[datetime], dict[str, np.ndarray]]: The original `sample_times` list and a mapping from satellite ID to a NumPy array of shape (len(sample_times), 3) containing ECEF positions in meters. Each row in an array corresponds to the satellite position at the matching index in `sample_times`.
    """
    propagators = _build_propagators(case)
    states_ecef_by_satellite: dict[str, np.ndarray] = {}
    for satellite_id, propagator in propagators.items():
        rows = np.zeros((len(sample_times), 3), dtype=float)
        for index, instant in enumerate(sample_times):
            epoch = _datetime_to_epoch(instant)
            state_eci = np.asarray(propagator.state(epoch), dtype=float)
            rows[index] = np.asarray(
                brahe.position_eci_to_ecef(epoch, state_eci[:3]),
                dtype=float,
            )
        states_ecef_by_satellite[satellite_id] = rows
    return sample_times, states_ecef_by_satellite


def _shortest_path(
    adjacency: dict[str, list[tuple[str, float]]],
    source_id: str,
    destination_id: str,
    all_endpoint_ids: set[str],
) -> tuple[tuple[str, ...] | None, float | None]:
    """
    Finds the shortest-weight path from source_id to destination_id in a weighted graph and the path's total weight.
    
    Parameters:
        adjacency (dict[str, list[tuple[str, float]]]): Mapping from node id to list of (neighbor_id, edge_weight).
        source_id (str): Starting node id.
        destination_id (str): Target node id.
        all_endpoint_ids (set[str]): Node ids considered endpoints; traversal is not allowed through these nodes except when they are the destination.
    
    Returns:
        tuple[path, total_distance]:
            path (tuple[str, ...] | None): Ordered sequence of node ids from source to destination, or `None` if no path exists.
            total_distance (float | None): Sum of edge weights along `path`, or `None` if no path exists.
    """
    queue: list[tuple[float, str]] = [(0.0, source_id)]
    distances: dict[str, float] = {source_id: 0.0}
    parents: dict[str, str | None] = {source_id: None}
    while queue:
        distance, node_id = heapq.heappop(queue)
        if distance > distances.get(node_id, math.inf):
            continue
        if node_id == destination_id:
            break
        for neighbor_id, edge_distance in adjacency.get(node_id, []):
            if neighbor_id in all_endpoint_ids and neighbor_id != destination_id:
                continue
            new_distance = distance + edge_distance
            if new_distance + 1e-9 < distances.get(neighbor_id, math.inf):
                distances[neighbor_id] = new_distance
                parents[neighbor_id] = node_id
                heapq.heappush(queue, (new_distance, neighbor_id))
    if destination_id not in distances:
        return None, None
    path: list[str] = []
    current: str | None = destination_id
    while current is not None:
        path.append(current)
        current = parents[current]
    path.reverse()
    return tuple(path), distances[destination_id]


def _pair_windows(case: RelayCase) -> dict[str, list[tuple[datetime, datetime]]]:
    """
    Group demand time windows by source→destination endpoint pair.
    
    Each dictionary key is the stable pair identifier "source->destination" and the
    value is a list of (start_time, end_time) tuples for that pair in the same
    order they appear in case.demands.
    
    Parameters:
        case (RelayCase): Relay case containing a sequence of demands with
            source_endpoint_id, destination_endpoint_id, start_time, and end_time.
    
    Returns:
        dict[str, list[tuple[datetime, datetime]]]: Mapping from pair id to the
        list of demand time windows for that pair.
    """
    grouped: dict[str, list[tuple[datetime, datetime]]] = {}
    for demand in case.demands:
        pair_id = _pair_id(demand.source_endpoint_id, demand.destination_endpoint_id)
        grouped.setdefault(pair_id, []).append((demand.start_time, demand.end_time))
    return grouped


def _demand_pairs(case: RelayCase) -> list[tuple[str, str]]:
    """
    Return the sorted list of unique (source_endpoint_id, destination_endpoint_id) pairs present in the case demands.
    
    Parameters:
        case (RelayCase): Relay case containing a sequence of demand objects with source_endpoint_id and destination_endpoint_id.
    
    Returns:
        pairs (list[tuple[str, str]]): Sorted list of unique (source_endpoint_id, destination_endpoint_id) tuples.
    """
    pairs = sorted(
        {
            (demand.source_endpoint_id, demand.destination_endpoint_id)
            for demand in case.demands
        }
    )
    return pairs


def _overlaps_windows(
    start_time: datetime,
    end_time: datetime,
    windows: tuple[tuple[datetime, datetime], ...],
) -> bool:
    """
    Determine whether the time interval [start_time, end_time) overlaps any of the provided windows.
    
    Parameters:
        start_time (datetime): Start of the interval (inclusive).
        end_time (datetime): End of the interval (exclusive).
        windows (tuple[tuple[datetime, datetime], ...]): Sequence of (start, end) windows treated as half-open intervals [start, end).
    
    Returns:
        `true` if the interval [start_time, end_time) overlaps any window, `false` otherwise.
    """
    for window_start, window_end in windows:
        if start_time < window_end and end_time > window_start:
            return True
    return False


def _contains_time(
    instant: datetime,
    windows: tuple[tuple[datetime, datetime], ...],
) -> bool:
    """
    Determine whether `instant` lies inside any half-open time window.
    
    Parameters:
    	instant (datetime): The datetime to test.
    	windows (tuple[tuple[datetime, datetime], ...]): Iterable of (start_time, end_time) pairs where each window includes `start_time` and excludes `end_time`.
    
    Returns:
    	bool: `True` if `instant` is >= a window's start_time and < that window's end_time, `False` otherwise.
    """
    for start_time, end_time in windows:
        if start_time <= instant < end_time:
            return True
    return False


def compute_connectivity_summaries(
    case: RelayCase,
    *,
    sample_times: list[datetime] | None = None,
    states_ecef_by_satellite: dict[str, np.ndarray] | None = None,
) -> list[ConnectivityPairSummary]:
    """
    Compute per-endpoint-pair connectivity summaries over the routing horizon.
    
    For each unique source→destination demand pair this samples the network at the routing step instants (or uses the supplied instants and satellite ECEF states), builds per-instant adjacency between ground endpoints and satellites plus feasible inter-satellite links, finds the shortest route at each instant, compresses consecutive identical routes into RouteInterval objects, and counts requested versus served samples within the demand windows.
    
    Parameters:
        case (RelayCase): Problem specification including demands, manifest parameters, ground endpoints, and backbone satellite definitions.
        sample_times (list[datetime] | None): Optional precomputed sampling instants to evaluate connectivity. If omitted, instants are generated from the union of demand windows using the manifest.routing_step_s.
        states_ecef_by_satellite (dict[str, np.ndarray] | None): Optional precomputed per-satellite ECEF positions aligned with `sample_times`. If omitted, a state cache is built for the sampling instants.
    
    Returns:
        list[ConnectivityPairSummary]: One summary per unique demand pair containing demand windows, compressed route intervals (with path length and latency), intervals overlapping demands, and counts of requested and served samples.
    """
    pair_windows = {
        pair_id: tuple(windows)
        for pair_id, windows in _pair_windows(case).items()
    }
    if sample_times is None or states_ecef_by_satellite is None:
        all_windows = tuple(window for windows in pair_windows.values() for window in windows)
        sample_times = _sample_times_for_windows(
            all_windows,
            step_s=case.manifest.routing_step_s,
        )
        sample_times, states_ecef_by_satellite = build_state_cache_for_times(
            case,
            sample_times,
        )
    pair_demands = _demand_pairs(case)
    all_endpoint_ids = set(case.ground_endpoints)

    pair_samples: dict[str, list[tuple[datetime, tuple[str, ...] | None, float | None]]] = {
        _pair_id(source_id, destination_id): []
        for source_id, destination_id in pair_demands
    }

    satellite_ids = sorted(states_ecef_by_satellite)
    endpoint_ids = sorted(case.ground_endpoints)

    for sample_index, instant in enumerate(sample_times):
        satellite_positions = {
            satellite_id: states_ecef_by_satellite[satellite_id][sample_index]
            for satellite_id in satellite_ids
        }
        adjacency: dict[str, list[tuple[str, float]]] = {
            node_id: [] for node_id in endpoint_ids + satellite_ids
        }

        for endpoint in case.ground_endpoints.values():
            for satellite_id in satellite_ids:
                is_visible, distance_m = _endpoint_visible(
                    endpoint,
                    satellite_positions[satellite_id],
                    max_ground_range_m=case.manifest.max_ground_range_m,
                )
                if not is_visible:
                    continue
                adjacency[endpoint.endpoint_id].append((satellite_id, distance_m))
                adjacency[satellite_id].append((endpoint.endpoint_id, distance_m))

        for first_index, satellite_id_1 in enumerate(satellite_ids):
            position_1 = satellite_positions[satellite_id_1]
            for satellite_id_2 in satellite_ids[first_index + 1 :]:
                is_feasible, distance_m = _isl_feasible(
                    position_1,
                    satellite_positions[satellite_id_2],
                    max_isl_range_m=case.manifest.max_isl_range_m,
                )
                if not is_feasible:
                    continue
                adjacency[satellite_id_1].append((satellite_id_2, distance_m))
                adjacency[satellite_id_2].append((satellite_id_1, distance_m))

        for source_id, destination_id in pair_demands:
            path, total_length_m = _shortest_path(
                adjacency,
                source_id,
                destination_id,
                all_endpoint_ids,
            )
            pair_samples[_pair_id(source_id, destination_id)].append(
                (instant, path, total_length_m)
            )

    summaries: list[ConnectivityPairSummary] = []
    step = timedelta(seconds=case.manifest.routing_step_s)
    for source_id, destination_id in pair_demands:
        pair_id = _pair_id(source_id, destination_id)
        windows = pair_windows[pair_id]
        samples = pair_samples[pair_id]
        intervals: list[RouteInterval] = []
        current_start: datetime | None = None
        current_route: tuple[str, ...] | None = None
        current_length_m: float | None = None
        previous_instant: datetime | None = None

        for instant, route_nodes, total_length_m in samples:
            if route_nodes == current_route:
                previous_instant = instant
                continue
            if current_route is not None and current_start is not None and previous_instant is not None:
                intervals.append(
                    RouteInterval(
                        pair_id=pair_id,
                        source_endpoint_id=source_id,
                        destination_endpoint_id=destination_id,
                        start_time=current_start,
                        end_time=previous_instant + step,
                        route_nodes=current_route,
                        total_path_length_m=float(current_length_m),
                        latency_ms=(1000.0 * float(current_length_m) / _LIGHT_SPEED_M_S),
                    )
                )
            current_start = instant
            current_route = route_nodes
            current_length_m = total_length_m
            previous_instant = instant

        if current_route is not None and current_start is not None and previous_instant is not None:
            intervals.append(
                RouteInterval(
                    pair_id=pair_id,
                    source_endpoint_id=source_id,
                    destination_endpoint_id=destination_id,
                    start_time=current_start,
                    end_time=previous_instant + step,
                    route_nodes=current_route,
                    total_path_length_m=float(current_length_m),
                    latency_ms=(1000.0 * float(current_length_m) / _LIGHT_SPEED_M_S),
                )
            )

        requested_sample_count = sum(
            1 for instant, _, _ in samples if _contains_time(instant, windows)
        )
        served_sample_count = sum(
            1
            for instant, route_nodes, _ in samples
            if route_nodes is not None and _contains_time(instant, windows)
        )
        summaries.append(
            ConnectivityPairSummary(
                pair_id=pair_id,
                source_endpoint_id=source_id,
                destination_endpoint_id=destination_id,
                demand_windows=windows,
                route_intervals=tuple(
                    interval for interval in intervals if interval.route_nodes is not None
                ),
                route_intervals_overlapping_demands=tuple(
                    interval
                    for interval in intervals
                    if interval.route_nodes is not None
                    and _overlaps_windows(interval.start_time, interval.end_time, windows)
                ),
                requested_sample_count=requested_sample_count,
                served_sample_count=served_sample_count,
            )
        )
    return summaries


def representative_demands(case: RelayCase) -> list[RelayDemand]:
    """
    Get the relay demands from the case in a stable (original) order for plotting and analysis.
    
    Parameters:
        case (RelayCase): Relay case containing an iterable of RelayDemand objects.
    
    Returns:
        list[RelayDemand]: Demands in the same order as provided by case.demands.
    """
    return list(case.demands)


def relevant_satellites_for_demand(
    case: RelayCase,
    demand: RelayDemand,
    *,
    sample_times: list[datetime],
    states_ecef_by_satellite: dict[str, np.ndarray],
) -> set[str]:
    """
    Identify satellites that are visible to either the demand's source or destination at any sampled instant within the demand's time window.
    
    Parameters:
        case (RelayCase): Relay scenario containing ground endpoints and manifest settings (used for min elevation and max ground range).
        demand (RelayDemand): Demand with `source_endpoint_id`, `destination_endpoint_id`, `start_time`, and `end_time`.
        sample_times (list[datetime]): Ordered sample instants corresponding to the rows in `states_ecef_by_satellite`.
        states_ecef_by_satellite (dict[str, np.ndarray]): Mapping from satellite ID to an array of ECEF positions with shape (len(sample_times), 3).
    
    Returns:
        set[str]: Satellite IDs that are visible to the source or destination at least once during the half-open interval [demand.start_time, demand.end_time).
    """
    relevant: set[str] = set()
    source = case.ground_endpoints[demand.source_endpoint_id]
    destination = case.ground_endpoints[demand.destination_endpoint_id]
    for sample_index, instant in enumerate(sample_times):
        if instant < demand.start_time or instant >= demand.end_time:
            continue
        for satellite_id, state_rows in states_ecef_by_satellite.items():
            satellite_position = state_rows[sample_index]
            if _endpoint_visible(
                source,
                satellite_position,
                max_ground_range_m=case.manifest.max_ground_range_m,
            )[0] or _endpoint_visible(
                destination,
                satellite_position,
                max_ground_range_m=case.manifest.max_ground_range_m,
            )[0]:
                relevant.add(satellite_id)
    return relevant


def midpoint_index(sample_times: list[datetime], demand: RelayDemand) -> int:
    """
    Finds the index of the sample time closest to the midpoint of a demand window.
    
    Parameters:
        sample_times (list[datetime]): Candidate datetimes to search.
        demand (RelayDemand): Demand whose midpoint (start_time + half duration) is used as the target.
    
    Returns:
        int: Index in `sample_times` whose datetime is nearest the demand midpoint.
    """
    midpoint = demand.start_time + ((demand.end_time - demand.start_time) / 2)
    best_index = min(
        range(len(sample_times)),
        key=lambda index: abs((sample_times[index] - midpoint).total_seconds()),
    )
    return int(best_index)


def visible_endpoint_links_at_index(
    case: RelayCase,
    demand: RelayDemand,
    *,
    sample_index: int,
    states_ecef_by_satellite: dict[str, np.ndarray],
    satellite_ids: set[str],
) -> list[tuple[str, str]]:
    """
    List endpoint-to-satellite links that are visible at a specific sample index for a demand's source and destination.
    
    Checks visibility for the demand's source and destination endpoints against each satellite in `satellite_ids` using the satellite ECEF positions at `sample_index` and the manifest's `max_ground_range_m`.
    
    Parameters:
        case (RelayCase): Relay case containing ground endpoint definitions and manifest settings.
        demand (RelayDemand): Demand whose source and destination endpoints are checked.
        sample_index (int): Index into the per-satellite time-sampled state arrays.
        states_ecef_by_satellite (dict[str, numpy.ndarray]): Mapping from satellite ID to an array of ECEF positions indexed by sample time.
        satellite_ids (set[str]): Satellite IDs to evaluate for visibility.
    
    Returns:
        list[tuple[str, str]]: List of (endpoint_id, satellite_id) pairs that are visible at the given sample index.
    """
    links: list[tuple[str, str]] = []
    for endpoint_id in (demand.source_endpoint_id, demand.destination_endpoint_id):
        endpoint = case.ground_endpoints[endpoint_id]
        for satellite_id in sorted(satellite_ids):
            if _endpoint_visible(
                endpoint,
                states_ecef_by_satellite[satellite_id][sample_index],
                max_ground_range_m=case.manifest.max_ground_range_m,
            )[0]:
                links.append((endpoint_id, satellite_id))
    return links
