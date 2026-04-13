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
    global _BRAHE_EOP_INITIALIZED
    if _BRAHE_EOP_INITIALIZED:
        return
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    _BRAHE_EOP_INITIALIZED = True


def _datetime_to_epoch(value: datetime) -> brahe.Epoch:
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
    windows = tuple((demand.start_time, demand.end_time) for demand in case.demands)
    return _sample_times_for_windows(
        windows,
        step_s=case.manifest.routing_step_s,
    )


def _pair_id(source_endpoint_id: str, destination_endpoint_id: str) -> str:
    return f"{source_endpoint_id}->{destination_endpoint_id}"


def _segment_clear_of_earth(point_a_m: np.ndarray, point_b_m: np.ndarray) -> bool:
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
    distance_m = float(np.linalg.norm(position_b_ecef_m - position_a_ecef_m))
    if distance_m > max_isl_range_m:
        return False, distance_m
    return _segment_clear_of_earth(position_a_ecef_m, position_b_ecef_m), distance_m


def _build_propagators(case: RelayCase) -> dict[str, brahe.NumericalOrbitPropagator]:
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
) -> tuple[tuple[str, ...] | None, float | None]:
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
    grouped: dict[str, list[tuple[datetime, datetime]]] = {}
    for demand in case.demands:
        pair_id = _pair_id(demand.source_endpoint_id, demand.destination_endpoint_id)
        grouped.setdefault(pair_id, []).append((demand.start_time, demand.end_time))
    return grouped


def _demand_pairs(case: RelayCase) -> list[tuple[str, str]]:
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
    for window_start, window_end in windows:
        if start_time < window_end and end_time > window_start:
            return True
    return False


def _contains_time(
    instant: datetime,
    windows: tuple[tuple[datetime, datetime], ...],
) -> bool:
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
            path, total_length_m = _shortest_path(adjacency, source_id, destination_id)
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
    """Return all demands in a stable order for per-window overview plots."""
    return list(case.demands)


def relevant_satellites_for_demand(
    case: RelayCase,
    demand: RelayDemand,
    *,
    sample_times: list[datetime],
    states_ecef_by_satellite: dict[str, np.ndarray],
) -> set[str]:
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
