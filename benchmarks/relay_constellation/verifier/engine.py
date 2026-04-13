"""Core verification logic for the relay_constellation benchmark."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import heapq
import math
from pathlib import Path

import brahe
import numpy as np

from .io import load_case, load_solution
from .models import (
    ActionFailure,
    LIGHT_SPEED_M_S,
    NUMERICAL_EPS,
    OrbitSummary,
    PathCandidate,
    RelayAction,
    RelayCase,
    RelayDemand,
    RelayEndpoint,
    RelaySatellite,
    RelaySolution,
    SampleAllocation,
    SampleRouteAssignment,
    SolutionAnalysis,
    ValidatedAction,
    VerificationResult,
)


_BRAHE_EOP_INITIALIZED = False


@dataclass(frozen=True)
class _SampleEdge:
    edge_id: str
    neighbor_id: str
    distance_m: float


def _ensure_brahe_ready() -> None:
    """
    Initialize Brahe's global Earth orientation (EOP) provider to a zeroed static provider for propagation routines.
    
    This call is idempotent: on the first invocation it configures Brahe's global EOP provider; subsequent calls have no effect.
    """
    global _BRAHE_EOP_INITIALIZED
    if _BRAHE_EOP_INITIALIZED:
        return
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    _BRAHE_EOP_INITIALIZED = True


def _default_metrics(case: RelayCase | None, solution: RelaySolution | None) -> dict[str, object]:
    """
    Create a default metrics dictionary populated with zero/empty values suitable for use when analysis cannot proceed.
    
    Parameters:
        case (RelayCase | None): The problem case; used only to derive counts (`num_demanded_windows`, `num_backbone_satellites`) when provided.
        solution (RelaySolution | None): The solution; used only to derive `num_added_satellites` when provided.
    
    Returns:
        dict[str, object]: A metrics mapping with these keys:
            - "service_fraction" (float): Weighted fraction of demand service, default 0.0.
            - "worst_demand_service_fraction" (float): Minimum per-demand service fraction, default 0.0.
            - "mean_latency_ms" (float | None): Pooled mean latency in milliseconds for served demand-samples, default None.
            - "latency_p95_ms" (float | None): 95th percentile latency in milliseconds for served demand-samples, default None.
            - "num_added_satellites" (int): Number of satellites in `solution.added_satellites` or 0 if `solution` is None.
            - "num_demanded_windows" (int): Number of demands in `case.demands` or 0 if `case` is None.
            - "num_backbone_satellites" (int): Number of backbone satellites in `case.backbone_satellites` or 0 if `case` is None.
            - "per_demand" (dict): Mapping from demand_id to per-demand metrics (requested/served sample counts, service fraction, mean/95th latency); empty by default.
    """
    return {
        "service_fraction": 0.0,
        "worst_demand_service_fraction": 0.0,
        "mean_latency_ms": None,
        "latency_p95_ms": None,
        "num_added_satellites": len(solution.added_satellites) if solution is not None else 0,
        "num_demanded_windows": len(case.demands) if case is not None else 0,
        "num_backbone_satellites": len(case.backbone_satellites) if case is not None else 0,
        "per_demand": {},
    }


def _datetime_to_epoch(value: datetime) -> brahe.Epoch:
    """
    Convert a datetime to a Brahe Epoch in UTC, preserving fractional seconds.
    
    Returns:
        brahe.Epoch: The corresponding epoch in the Brahe UTC time system with fractional seconds from the input preserved.
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


def _isoformat_z(value: datetime) -> str:
    """
    Format a datetime as an ISO 8601 / RFC 3339 string in UTC using the 'Z' timezone designator.
    
    Parameters:
        value (datetime): The datetime to format; it is converted to UTC if necessary.
    
    Returns:
        iso (str): An ISO 8601 string for the given time in UTC, ending with 'Z' instead of '+00:00'.
    """
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sample_index(case: RelayCase, instant: datetime, *, field: str) -> int:
    """
    Convert an instant to the integer routing sample index measured from the case horizon start.
    
    The instant must be on the case.manifest.routing_step_s grid, not earlier than horizon_start (within a small numerical tolerance), and not after the horizon end.
    
    Parameters:
        case: RelayCase providing manifest.horizon_start, manifest.routing_step_s, and manifest.total_samples.
        instant (datetime): The UTC-aware time to convert.
        field (str): Identifier used in raised ValueError messages to indicate which input failed validation.
    
    Returns:
        int: The zero-based sample index corresponding to the instant.
    
    Raises:
        ValueError: If the instant is before horizon_start, not aligned to the routing_step_s grid, or after the horizon end.
    """
    delta = instant.astimezone(UTC) - case.manifest.horizon_start
    total_seconds = delta.total_seconds()
    if total_seconds < -NUMERICAL_EPS:
        raise ValueError(f"{field} lies before horizon_start")
    step = case.manifest.routing_step_s
    index_float = total_seconds / step
    index_rounded = int(round(index_float))
    if abs(index_float - index_rounded) > 1e-9:
        raise ValueError(f"{field} must lie on the routing_step_s grid")
    if index_rounded > case.manifest.total_samples:
        raise ValueError(f"{field} lies after horizon_end")
    return index_rounded


def _time_for_index(case: RelayCase, sample_index: int) -> datetime:
    """
    Compute the datetime corresponding to a routing sample index within the case horizon.
    
    Parameters:
        case (RelayCase): Case containing a manifest with `horizon_start` and `routing_step_s`.
        sample_index (int): Zero-based sample index; each index advances time by `routing_step_s` seconds.
    
    Returns:
        datetime: The instant equal to `case.manifest.horizon_start + sample_index * routing_step_s`.
    """
    return case.manifest.horizon_start + timedelta(seconds=sample_index * case.manifest.routing_step_s)


def _interval_indices(case: RelayCase, start_time: datetime, end_time: datetime) -> tuple[int, ...]:
    """
    Compute the sequence of sample indices covered by an action's start and end times on the case's sampling grid.
    
    Parameters:
        case (RelayCase): The relay case containing the planning horizon and sampling configuration.
        start_time (datetime): Action start instant (inclusive).
        end_time (datetime): Action end instant (exclusive).
    
    Returns:
        tuple[int, ...]: A tuple of sample indices from the start sample (inclusive) up to but not including the end sample.
    
    Raises:
        ValueError: If the end time is not after the start time, if the end time lies outside the planning horizon, or if either time does not align with the case sampling grid.
    """
    start_index = _sample_index(case, start_time, field="action.start_time")
    end_index = _sample_index(case, end_time, field="action.end_time")
    if end_index <= start_index:
        raise ValueError("action.end_time must be after start_time")
    if end_index > case.manifest.total_samples:
        raise ValueError("action.end_time lies outside the planning horizon")
    return tuple(range(start_index, end_index))


def _demand_indices(case: RelayCase, demand: RelayDemand) -> tuple[int, ...]:
    """
    Compute the sequence of routing-sample indices that fall within a demand's time window.
    
    Returns:
    	tuple[int, ...]: Sample indices from the demand's start (inclusive) to end (exclusive) on the case's routing step grid.
    
    Raises:
    	ValueError: If the demand's end time is not after its start time such that at least one sampled instant is covered.
    """
    start_index = _sample_index(case, demand.start_time, field=f"demand {demand.demand_id} start_time")
    end_index = _sample_index(case, demand.end_time, field=f"demand {demand.demand_id} end_time")
    if end_index <= start_index:
        raise ValueError(f"Demand {demand.demand_id} must contain at least one sampled instant")
    return tuple(range(start_index, end_index))


def _segment_clear_of_earth(point_a_m: np.ndarray, point_b_m: np.ndarray) -> bool:
    """
    Determine whether the straight line segment between two ECEF points remains outside the Earth.
    
    Parameters:
        point_a_m (np.ndarray): ECEF position of the first endpoint in meters.
        point_b_m (np.ndarray): ECEF position of the second endpoint in meters.
    
    Returns:
        bool: `true` if every point on the segment has distance greater than Earth radius + 1 meter, `false` otherwise. Degenerate segments (endpoints coincident) are treated by testing the endpoint's distance from Earth's center.
    """
    segment = point_b_m - point_a_m
    denom = float(np.dot(segment, segment))
    if denom <= NUMERICAL_EPS:
        return float(np.linalg.norm(point_a_m)) > float(brahe.R_EARTH)
    t = float(-np.dot(point_a_m, segment) / denom)
    t = max(0.0, min(1.0, t))
    closest = point_a_m + (t * segment)
    return float(np.linalg.norm(closest)) > float(brahe.R_EARTH) + 1.0


def _ground_link_feasible(
    endpoint: RelayEndpoint,
    satellite_position_ecef_m: np.ndarray,
    *,
    max_ground_range_m: float | None,
) -> tuple[bool, float]:
    """
    Determine whether a ground-to-satellite link meets the endpoint's elevation constraint and an optional maximum slant range.
    
    Parameters:
        endpoint (RelayEndpoint): Ground endpoint providing ECEF position and `min_elevation_deg`.
        satellite_position_ecef_m (numpy.ndarray): Satellite ECEF position (meters).
        max_ground_range_m (float | None): Optional maximum allowed slant range (meters). If None, no range limit is applied.
    
    Returns:
        tuple[bool, float]: `(feasible, slant_range_m)` where `feasible` is `True` if the computed elevation is greater than or equal to `endpoint.min_elevation_deg` and the slant range is less than or equal to `max_ground_range_m` when provided, `False` otherwise; `slant_range_m` is the computed slant range in meters.
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
    Check whether an inter-satellite link between two ECEF positions is feasible under range and Earth-obstruction constraints.
    
    Parameters:
        position_a_ecef_m (np.ndarray): ECEF coordinates of the first satellite in meters.
        position_b_ecef_m (np.ndarray): ECEF coordinates of the second satellite in meters.
        max_isl_range_m (float): Maximum allowable inter-satellite link range in meters.
    
    Returns:
        tuple[bool, float]: (feasible, distance_m) where `feasible` is `True` if the Euclidean distance between the two positions is less than or equal to `max_isl_range_m` and the straight line segment between them does not intersect the Earth, `False` otherwise; `distance_m` is the computed Euclidean distance in meters.
    """
    distance_m = float(np.linalg.norm(position_b_ecef_m - position_a_ecef_m))
    if distance_m > max_isl_range_m:
        return False, distance_m
    return _segment_clear_of_earth(position_a_ecef_m, position_b_ecef_m), distance_m


def _orbit_summary(satellite: RelaySatellite) -> OrbitSummary:
    """
    Compute a concise orbital-element summary for a satellite from its ECI state.
    
    Parameters:
        satellite (RelaySatellite): Satellite record whose `state_eci_m_mps` (ECI position then velocity, meters and meters/second) and `satellite_id` are used.
    
    Returns:
        OrbitSummary: Contains semi-major axis (meters), eccentricity, inclination (degrees), perigee altitude (meters), apogee altitude (meters), and the satellite_id.
    
    Raises:
        ValueError: If the satellite position has zero magnitude, the specific orbital energy is non-negative (not a bound orbit),
                    the eccentricity is >= 1.0 (not a closed orbit), or the orbital angular momentum is degenerate.
    """
    position_m = np.asarray(satellite.state_eci_m_mps[:3], dtype=float)
    velocity_m_s = np.asarray(satellite.state_eci_m_mps[3:], dtype=float)
    radius_m = float(np.linalg.norm(position_m))
    speed_m_s = float(np.linalg.norm(velocity_m_s))
    if radius_m <= NUMERICAL_EPS:
        raise ValueError(f"Satellite {satellite.satellite_id} has zero-magnitude position")

    mu_m3_s2 = float(brahe.GM_EARTH)
    specific_energy = (0.5 * speed_m_s * speed_m_s) - (mu_m3_s2 / radius_m)
    if specific_energy >= 0.0:
        raise ValueError(f"Satellite {satellite.satellite_id} is not in a bound orbit")

    semi_major_axis_m = -mu_m3_s2 / (2.0 * specific_energy)
    radial_velocity = float(np.dot(position_m, velocity_m_s))
    eccentricity_vector = (
        ((speed_m_s * speed_m_s) - (mu_m3_s2 / radius_m)) * position_m
        - (radial_velocity * velocity_m_s)
    ) / mu_m3_s2
    eccentricity = float(np.linalg.norm(eccentricity_vector))
    if eccentricity >= 1.0:
        raise ValueError(f"Satellite {satellite.satellite_id} is not in a closed orbit")

    angular_momentum = np.cross(position_m, velocity_m_s)
    angular_momentum_norm = float(np.linalg.norm(angular_momentum))
    if angular_momentum_norm <= NUMERICAL_EPS:
        raise ValueError(f"Satellite {satellite.satellite_id} has degenerate angular momentum")
    inclination_deg = math.degrees(
        math.acos(max(-1.0, min(1.0, float(angular_momentum[2]) / angular_momentum_norm)))
    )
    perigee_altitude_m = (semi_major_axis_m * (1.0 - eccentricity)) - float(brahe.R_EARTH)
    apogee_altitude_m = (semi_major_axis_m * (1.0 + eccentricity)) - float(brahe.R_EARTH)
    return OrbitSummary(
        satellite_id=satellite.satellite_id,
        semi_major_axis_m=semi_major_axis_m,
        eccentricity=eccentricity,
        inclination_deg=inclination_deg,
        perigee_altitude_m=perigee_altitude_m,
        apogee_altitude_m=apogee_altitude_m,
    )


def _validate_added_satellites(case: RelayCase, solution: RelaySolution) -> tuple[list[str], list[OrbitSummary]]:
    """
    Validate added satellites against case limits and orbital constraints.
    
    Checks that the number of added satellites does not exceed the case limit, that added satellite IDs do not collide with backbone satellite IDs, and that each added satellite's orbit satisfies bound/closed-orbit requirements and case-configured altitude, eccentricity, and inclination bounds. Violations are collected as human-readable strings.
    
    Parameters:
        case (RelayCase): Problem case containing manifest limits and backbone satellite IDs.
        solution (RelaySolution): Proposed solution containing `added_satellites` to validate.
    
    Returns:
        tuple[list[str], list[OrbitSummary]]: A pair where the first element is a list of violation messages (empty if none), and the second element is a list of OrbitSummary objects for added satellites that produced valid orbit summaries, sorted by `satellite_id`.
    """
    violations: list[str] = []
    orbit_summaries: list[OrbitSummary] = []
    if len(solution.added_satellites) > case.manifest.max_added_satellites:
        violations.append(
            f"Solution defines {len(solution.added_satellites)} added satellites but the case allows at most "
            f"{case.manifest.max_added_satellites}"
        )
    for satellite_id in solution.added_satellites:
        if satellite_id in case.backbone_satellites:
            violations.append(f"Added satellite_id collides with backbone satellite ID: {satellite_id}")

    for satellite in solution.added_satellites.values():
        try:
            summary = _orbit_summary(satellite)
        except ValueError as exc:
            violations.append(str(exc))
            continue
        orbit_summaries.append(summary)
        if summary.perigee_altitude_m < case.manifest.min_altitude_m - NUMERICAL_EPS:
            violations.append(
                f"Satellite {satellite.satellite_id} perigee altitude {summary.perigee_altitude_m:.3f} m "
                f"is below min_altitude_m {case.manifest.min_altitude_m:.3f} m"
            )
        if summary.apogee_altitude_m > case.manifest.max_altitude_m + NUMERICAL_EPS:
            violations.append(
                f"Satellite {satellite.satellite_id} apogee altitude {summary.apogee_altitude_m:.3f} m "
                f"exceeds max_altitude_m {case.manifest.max_altitude_m:.3f} m"
            )
        if (
            case.manifest.max_eccentricity is not None
            and summary.eccentricity > case.manifest.max_eccentricity + NUMERICAL_EPS
        ):
            violations.append(
                f"Satellite {satellite.satellite_id} eccentricity {summary.eccentricity:.6f} "
                f"exceeds max_eccentricity {case.manifest.max_eccentricity:.6f}"
            )
        if (
            case.manifest.min_inclination_deg is not None
            and summary.inclination_deg < case.manifest.min_inclination_deg - NUMERICAL_EPS
        ):
            violations.append(
                f"Satellite {satellite.satellite_id} inclination {summary.inclination_deg:.3f} deg "
                f"is below min_inclination_deg {case.manifest.min_inclination_deg:.3f} deg"
            )
        if (
            case.manifest.max_inclination_deg is not None
            and summary.inclination_deg > case.manifest.max_inclination_deg + NUMERICAL_EPS
        ):
            violations.append(
                f"Satellite {satellite.satellite_id} inclination {summary.inclination_deg:.3f} deg "
                f"exceeds max_inclination_deg {case.manifest.max_inclination_deg:.3f} deg"
            )
    orbit_summaries.sort(key=lambda row: row.satellite_id)
    return violations, orbit_summaries


def _normalize_action(
    case: RelayCase,
    action: RelayAction,
    *,
    known_satellite_ids: set[str],
) -> tuple[tuple[str, ...], str, str]:
    """
    Normalize a RelayAction into a canonical link key and its two endpoint identifiers.
    
    Validates required fields and references for supported action types and returns a tuple describing the logical link:
    - For `ground_link`: returns link key ("ground_link", endpoint_id, satellite_id) and nodes (endpoint_id, satellite_id).
    - For `inter_satellite_link`: returns link key ("inter_satellite_link", sat_a, sat_b) with satellite IDs ordered lexicographically and nodes (sat_a, sat_b).
    
    Parameters:
        case: RelayCase containing ground endpoint definitions used to validate endpoint references.
        action: RelayAction to normalize and validate.
        known_satellite_ids: Set of satellite IDs considered valid for action references.
    
    Returns:
        A tuple (link_key, node_a, node_b) where `link_key` is a tuple identifying the link type and endpoints, and `node_a`/`node_b` are the endpoint identifiers in the same order as used in `link_key`.
    
    Raises:
        ValueError: If required fields are missing or empty, references are unknown, an inter-satellite link uses the same satellite on both ends, or the action_type is unsupported.
    """
    if action.action_type == "ground_link":
        if not isinstance(action.endpoint_id, str) or not action.endpoint_id:
            raise ValueError("ground_link action requires endpoint_id")
        if not isinstance(action.satellite_id, str) or not action.satellite_id:
            raise ValueError("ground_link action requires satellite_id")
        if action.endpoint_id not in case.ground_endpoints:
            raise ValueError(f"Unknown endpoint reference: {action.endpoint_id}")
        if action.satellite_id not in known_satellite_ids:
            raise ValueError(f"Unknown satellite reference: {action.satellite_id}")
        return ("ground_link", action.endpoint_id, action.satellite_id), action.endpoint_id, action.satellite_id

    if action.action_type == "inter_satellite_link":
        if not isinstance(action.satellite_id_1, str) or not action.satellite_id_1:
            raise ValueError("inter_satellite_link action requires satellite_id_1")
        if not isinstance(action.satellite_id_2, str) or not action.satellite_id_2:
            raise ValueError("inter_satellite_link action requires satellite_id_2")
        if action.satellite_id_1 == action.satellite_id_2:
            raise ValueError("inter_satellite_link action cannot use the same satellite on both ends")
        if action.satellite_id_1 not in known_satellite_ids:
            raise ValueError(f"Unknown satellite reference: {action.satellite_id_1}")
        if action.satellite_id_2 not in known_satellite_ids:
            raise ValueError(f"Unknown satellite reference: {action.satellite_id_2}")
        sat_a, sat_b = sorted((action.satellite_id_1, action.satellite_id_2))
        return ("inter_satellite_link", sat_a, sat_b), sat_a, sat_b

    raise ValueError(f"Unsupported action_type: {action.action_type}")


def _validate_action_schedule(
    case: RelayCase,
    solution: RelaySolution,
    actions: list[RelayAction],
) -> tuple[list[str], dict[int, tuple[str, ...]], dict[int, tuple[int, ...]]]:
    """
    Validate and normalize an action schedule, ensuring each action references existing nodes, its time interval aligns with the case sampling grid and horizon, and no two actions overlap on the same logical link.
    
    Parameters:
        case (RelayCase): Problem case containing manifest, backbone satellites, and endpoints used for validation.
        solution (RelaySolution): Submitted solution whose added satellites are allowed in actions.
        actions (list[RelayAction]): List of actions to validate.
    
    Returns:
        tuple:
            - violations (list[str]): Human-readable violation messages discovered (empty if none).
            - link_keys_by_action (dict[int, tuple[str, ...]]): Mapping from action index to a canonical link key tuple identifying the logical link for that action (e.g., ("ground_link", endpoint_id, satellite_id) or ("inter_satellite_link", sat_a, sat_b")).
            - sample_indices_by_action (dict[int, tuple[int, ...]]): Mapping from action index to the sequence of sample indices covered by the action (range of integers, end exclusive in internal checks but stored as contained indices).
    """
    violations: list[str] = []
    link_keys_by_action: dict[int, tuple[str, ...]] = {}
    sample_indices_by_action: dict[int, tuple[int, ...]] = {}
    actions_by_link: defaultdict[tuple[str, ...], list[tuple[int, int, int]]] = defaultdict(list)
    known_satellite_ids = set(case.backbone_satellites) | set(solution.added_satellites)

    for action_index, action in enumerate(actions):
        try:
            link_key, _, _ = _normalize_action(
                case,
                action,
                known_satellite_ids=known_satellite_ids,
            )
        except ValueError as exc:
            violations.append(f"actions[{action_index}]: {exc}")
            continue
        try:
            covered_indices = _interval_indices(case, action.start_time, action.end_time)
        except ValueError as exc:
            violations.append(f"actions[{action_index}]: {exc}")
            continue
        link_keys_by_action[action_index] = link_key
        sample_indices_by_action[action_index] = covered_indices
        actions_by_link[link_key].append((covered_indices[0], covered_indices[-1] + 1, action_index))

    for link_key, intervals in actions_by_link.items():
        intervals.sort()
        previous_end = None
        previous_action_index = None
        for start_index, end_index, action_index in intervals:
            if previous_end is not None and start_index < previous_end:
                violations.append(
                    f"actions[{action_index}] overlaps another action on link {link_key}: "
                    f"previous actions[{previous_action_index}] ends at sample {previous_end}"
                )
            previous_end = end_index
            previous_action_index = action_index

    return violations, link_keys_by_action, sample_indices_by_action


def _build_reduced_timeline(
    case: RelayCase,
    actions: list[RelayAction],
    sample_indices_by_action: dict[int, tuple[int, ...]],
) -> tuple[list[int], dict[str, tuple[int, ...]], dict[int, list[RelayDemand]]]:
    """
    Builds a reduced timeline of sample indices referenced by actions and demands.
    
    Parameters:
        case: RelayCase containing demands and manifest timing.
        actions: List of actions (unused here except for alignment with call sites).
        sample_indices_by_action: Mapping from action index to the tuple of sample indices that action covers.
    
    Returns:
        action_samples (list[int]): Sorted list of unique sample indices covered by any action.
        active_demand_indices (dict[str, tuple[int, ...]]): Mapping from demand_id to the tuple of sample indices when that demand is active.
        demands_by_sample (dict[int, list[RelayDemand]]): Mapping from sample index to the list of demands active at that sample index.
    """
    active_demand_indices: dict[str, tuple[int, ...]] = {}
    demands_by_sample: dict[int, list[RelayDemand]] = defaultdict(list)

    for demand in case.demands:
        indices = _demand_indices(case, demand)
        active_demand_indices[demand.demand_id] = indices
        for sample_index in indices:
            demands_by_sample[sample_index].append(demand)

    action_samples = sorted(
        {
            sample_index
            for covered_indices in sample_indices_by_action.values()
            for sample_index in covered_indices
        }
    )
    return action_samples, active_demand_indices, demands_by_sample


def _propagate_positions(
    case: RelayCase,
    all_satellites: dict[str, RelaySatellite],
    reduced_samples: list[int],
) -> tuple[dict[int, int], dict[str, np.ndarray]]:
    """
    Propagate each satellite's initial ECI state to ECEF positions for the specified sample indices.
    
    Parameters:
        case (RelayCase): Defines the epoch and routing time grid used to convert sample indices to epochs.
        all_satellites (dict[str, RelaySatellite]): Mapping of satellite IDs to satellites whose `state_eci_m_mps` provide the initial ECI state.
        reduced_samples (list[int]): Sorted list of sample indices for which positions are required.
    
    Returns:
        tuple:
            sample_lookup (dict[int, int]): Maps a sample index to its row index in the per-satellite position arrays (i.e., index into the second return's arrays).
            positions_ecef_by_satellite (dict[str, numpy.ndarray]): Maps each satellite ID to a (N, 3) array of ECEF positions in meters, where N == len(reduced_samples) and rows are ordered according to `reduced_samples`.
    """
    if not reduced_samples:
        return {}, {}
    _ensure_brahe_ready()
    epoch = _datetime_to_epoch(case.manifest.epoch)
    last_sample_index = max(reduced_samples, default=0)
    last_epoch = _datetime_to_epoch(_time_for_index(case, last_sample_index))
    force_config = brahe.ForceModelConfig(
        gravity=brahe.GravityConfiguration.spherical_harmonic(2, 0)
    )
    sample_lookup = {sample_index: row_index for row_index, sample_index in enumerate(reduced_samples)}
    positions_ecef_by_satellite: dict[str, np.ndarray] = {}

    for satellite in all_satellites.values():
        propagator = brahe.NumericalOrbitPropagator.from_eci(
            epoch,
            satellite.state_eci_m_mps,
            force_config=force_config,
        )
        propagator.propagate_to(last_epoch)
        rows = np.zeros((len(reduced_samples), 3), dtype=float)
        for row_index, sample_index in enumerate(reduced_samples):
            sample_epoch = _datetime_to_epoch(_time_for_index(case, sample_index))
            state_eci = np.asarray(propagator.state(sample_epoch), dtype=float)
            rows[row_index] = np.asarray(
                brahe.position_eci_to_ecef(sample_epoch, state_eci[:3]),
                dtype=float,
            )
        positions_ecef_by_satellite[satellite.satellite_id] = rows
    return sample_lookup, positions_ecef_by_satellite


def _validate_action_geometry(
    case: RelayCase,
    solution: RelaySolution,
    actions: list[RelayAction],
    link_keys_by_action: dict[int, tuple[str, ...]],
    sample_indices_by_action: dict[int, tuple[int, ...]],
    sample_lookup: dict[int, int],
    positions_ecef_by_satellite: dict[str, np.ndarray],
) -> tuple[list[str], list[ValidatedAction], list[ActionFailure], dict[str, int], dict[str, int]]:
    """
    Validate geometric feasibility of actions across sampled times and enforce per-sample link capacity limits.
    
    For each action present in link_keys_by_action this function:
    - Normalizes the action endpoints and, for each covered sample index, checks geometric feasibility using the propagated ECEF positions:
      - ground links: endpoint elevation and max ground range
      - inter-satellite links (ISLs): range and Earth-clear segment test
    - On first infeasible sample for an action records a violation string and an ActionFailure and stops further checks for that action.
    - For fully feasible actions collects a ValidatedAction with per-sample distances.
    - Counts active links per satellite and per endpoint at each sample and after processing all actions emits violations for any sample where counts exceed manifest limits.
    
    Parameters:
        case (RelayCase): Problem case containing manifest, ground endpoints, and limits.
        solution (RelaySolution): Submitted solution (used to resolve added satellites).
        actions (list[RelayAction]): Ordered list of actions to validate.
        link_keys_by_action (dict[int, tuple[str, ...]]): Mapping from action index to normalized link key.
        sample_indices_by_action (dict[int, tuple[int, ...]]): Mapping from action index to the sampled indices the action covers.
        sample_lookup (dict[int, int]): Mapping from global sample index to row index in the propagated position arrays.
        positions_ecef_by_satellite (dict[str, np.ndarray]): Per-satellite arrays of ECEF positions indexed by the propagated row index.
    
    Returns:
        tuple containing:
        - violations (list[str]): Human-readable violation messages (geometry and capacity).
        - validated_actions (list[ValidatedAction]): Actions that were feasible for all their samples, including per-sample distances.
        - action_failures (list[ActionFailure]): Failures recorded for actions that were geometrically infeasible (one per failing action at first failing sample).
        - diagnostics_counts (dict[str, int]): Counts summarizing validated actions by type and total validated actions.
        - feasibility_counts (dict[str, int]): Counts of samples checked for each link type (keys: "ground_link_samples_checked", "inter_satellite_link_samples_checked").
    """
    violations: list[str] = []
    validated_actions: list[ValidatedAction] = []
    action_failures: list[ActionFailure] = []
    satellite_link_counts: defaultdict[int, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
    endpoint_link_counts: defaultdict[int, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
    feasibility_counts = {
        "ground_link_samples_checked": 0,
        "inter_satellite_link_samples_checked": 0,
    }

    for action_index, action in enumerate(actions):
        if action_index not in link_keys_by_action:
            continue
        link_key = link_keys_by_action[action_index]
        sample_indices = sample_indices_by_action[action_index]
        _, node_a, node_b = _normalize_action(
            case,
            action,
            known_satellite_ids=set(case.backbone_satellites) | set(solution.added_satellites),
        )
        distances_m_by_sample: dict[int, float] = {}

        for sample_index in sample_indices:
            row_index = sample_lookup[sample_index]
            if action.action_type == "ground_link":
                endpoint = case.ground_endpoints[node_a]
                is_feasible, distance_m = _ground_link_feasible(
                    endpoint,
                    positions_ecef_by_satellite[node_b][row_index],
                    max_ground_range_m=case.manifest.max_ground_range_m,
                )
                feasibility_counts["ground_link_samples_checked"] += 1
            else:
                is_feasible, distance_m = _isl_feasible(
                    positions_ecef_by_satellite[node_a][row_index],
                    positions_ecef_by_satellite[node_b][row_index],
                    max_isl_range_m=case.manifest.max_isl_range_m,
                )
                feasibility_counts["inter_satellite_link_samples_checked"] += 1

            if not is_feasible:
                reason = (
                    f"actions[{action_index}] is geometrically infeasible at "
                    f"{_isoformat_z(_time_for_index(case, sample_index))}"
                )
                violations.append(reason)
                action_failures.append(
                    ActionFailure(
                        action_index=action_index,
                        action_type=action.action_type,
                        reason=reason,
                        node_a=node_a,
                        node_b=node_b,
                        sample_index=sample_index,
                        time=_time_for_index(case, sample_index),
                    )
                )
                break

            distances_m_by_sample[sample_index] = distance_m
            if action.action_type == "ground_link":
                endpoint_link_counts[sample_index][node_a] += 1
                satellite_link_counts[sample_index][node_b] += 1
            else:
                satellite_link_counts[sample_index][node_a] += 1
                satellite_link_counts[sample_index][node_b] += 1
        else:
            validated_actions.append(
                ValidatedAction(
                    action_index=action_index,
                    action_type=action.action_type,
                    node_a=node_a,
                    node_b=node_b,
                    link_key=link_key,
                    sample_indices=sample_indices,
                    distances_m_by_sample=distances_m_by_sample,
                )
            )

    for sample_index, per_satellite in satellite_link_counts.items():
        for satellite_id, count in per_satellite.items():
            if count > case.manifest.max_links_per_satellite:
                violations.append(
                    f"Satellite {satellite_id} has {count} active links at {_isoformat_z(_time_for_index(case, sample_index))}, "
                    f"exceeding max_links_per_satellite={case.manifest.max_links_per_satellite}"
                )
    for sample_index, per_endpoint in endpoint_link_counts.items():
        for endpoint_id, count in per_endpoint.items():
            if count > case.manifest.max_links_per_endpoint:
                violations.append(
                    f"Endpoint {endpoint_id} has {count} active links at {_isoformat_z(_time_for_index(case, sample_index))}, "
                    f"exceeding max_links_per_endpoint={case.manifest.max_links_per_endpoint}"
                )

    diagnostics_counts = {
        "validated_actions": len(validated_actions),
        "ground_link_actions": sum(1 for action in validated_actions if action.action_type == "ground_link"),
        "inter_satellite_link_actions": sum(
            1 for action in validated_actions if action.action_type == "inter_satellite_link"
        ),
    }
    return violations, validated_actions, action_failures, diagnostics_counts, feasibility_counts


def _build_active_edges_by_sample(validated_actions: list[ValidatedAction]) -> dict[int, list[ValidatedAction]]:
    """
    Builds a mapping from sample index to the list of validated actions active at that sample.
    
    Parameters:
        validated_actions (list[ValidatedAction]): Validated actions each containing a sequence of active sample indices.
    
    Returns:
        dict[int, list[ValidatedAction]]: Mapping from sample index to the list of validated actions active at that index. Each list is sorted by the action's `action_id`.
    """
    active_edges_by_sample: dict[int, list[ValidatedAction]] = defaultdict(list)
    for action in validated_actions:
        for sample_index in action.sample_indices:
            active_edges_by_sample[sample_index].append(action)
    for sample_index in active_edges_by_sample:
        active_edges_by_sample[sample_index].sort(key=lambda row: row.action_id)
    return active_edges_by_sample


def _enumerate_paths(
    adjacency: dict[str, list[_SampleEdge]],
    source_id: str,
    destination_id: str,
    endpoint_ids: set[str],
) -> list[PathCandidate]:
    """
    Enumerate all simple, endpoint-constrained paths from source to destination in an undirected adjacency graph.
    
    Searches depth-first for all simple paths that start at `source_id` and end at `destination_id`, forbidding intermediate visits to any node in `endpoint_ids` (except when the endpoint is the destination). Each discovered path is returned as a PathCandidate with the ordered node sequence, the corresponding edge IDs in traversal order, and the summed distance. The returned list is sorted by (total_distance_m, nodes, edge_ids).
    
    Parameters:
        adjacency (dict[str, list[_SampleEdge]]): Mapping from a node ID to a list of adjacent sampled edges.
        source_id (str): Starting node ID for paths.
        destination_id (str): Target node ID for paths.
        endpoint_ids (set[str]): Set of endpoint node IDs that must not appear as intermediate nodes on a path (the destination may be in this set).
    
    Returns:
        list[PathCandidate]: Sorted list of discovered path candidates, each containing `nodes`, `edge_ids`, and `total_distance_m`.
    """
    candidates: list[PathCandidate] = []

    def _dfs(
        node_id: str,
        visited: set[str],
        nodes: list[str],
        edge_ids: list[str],
        total_distance_m: float,
    ) -> None:
        """
        Depth-first search that explores simple paths from the current node to a predefined destination and records complete path candidates.
        
        Parameters:
            node_id (str): Current node identifier being explored.
            visited (set[str]): Set of node IDs already visited in the current search branch to avoid cycles.
            nodes (list[str]): Ordered list of node IDs along the current path (start through current node); mutated in-place.
            edge_ids (list[str]): Ordered list of edge IDs corresponding to traversed edges along the current path; mutated in-place.
            total_distance_m (float): Cumulative distance of the current path in meters.
        
        Side effects:
            Appends a PathCandidate to the outer-scope `candidates` list when a path reaches the predefined destination. Mutates `visited`, `nodes`, and `edge_ids` during recursion.
        """
        if node_id == destination_id:
            candidates.append(
                PathCandidate(
                    nodes=tuple(nodes),
                    edge_ids=tuple(edge_ids),
                    total_distance_m=total_distance_m,
                )
            )
            return
        for edge in adjacency.get(node_id, []):
            neighbor_id = edge.neighbor_id
            if neighbor_id in visited:
                continue
            if neighbor_id in endpoint_ids and neighbor_id != destination_id:
                continue
            visited.add(neighbor_id)
            nodes.append(neighbor_id)
            edge_ids.append(edge.edge_id)
            _dfs(
                neighbor_id,
                visited,
                nodes,
                edge_ids,
                total_distance_m + edge.distance_m,
            )
            edge_ids.pop()
            nodes.pop()
            visited.remove(neighbor_id)

    _dfs(source_id, {source_id}, [source_id], [], 0.0)
    candidates.sort(key=lambda row: (row.total_distance_m, row.nodes, row.edge_ids))
    return candidates


def _shortest_path_candidate(
    adjacency: dict[str, list[_SampleEdge]],
    source_id: str,
    destination_id: str,
    all_endpoint_ids: set[str],
) -> PathCandidate | None:
    """
    Finds the shortest simple path from source_id to destination_id that does not pass through other endpoint nodes.
    
    Searches for a minimum-total-distance path (no repeated nodes) using a Dijkstra-like best-first search. Intermediate visits to any node in all_endpoint_ids are disallowed unless the node is the destination.
    
    Parameters:
        all_endpoint_ids (set[str]): Endpoint node IDs that must not appear as intermediate nodes on a path (the destination may be in this set).
    
    Returns:
        PathCandidate | None: A PathCandidate containing `nodes` (tuple of node IDs in path order), `edge_ids` (tuple of edge IDs in the same order), and `total_distance_m` if a feasible path exists; `None` if no path is found.
    """
    queue: list[tuple[float, tuple[str, ...], tuple[str, ...], str]] = [
        (0.0, (source_id,), (), source_id)
    ]
    best_distance_by_node: dict[str, float] = {source_id: 0.0}
    while queue:
        total_distance_m, nodes, edge_ids, node_id = heapq.heappop(queue)
        if total_distance_m > best_distance_by_node.get(node_id, math.inf) + NUMERICAL_EPS:
            continue
        if node_id == destination_id:
            return PathCandidate(
                nodes=nodes,
                edge_ids=edge_ids,
                total_distance_m=total_distance_m,
            )
        for edge in adjacency.get(node_id, []):
            neighbor_id = edge.neighbor_id
            if neighbor_id in nodes:
                continue
            if neighbor_id in all_endpoint_ids and neighbor_id != destination_id:
                continue
            new_distance_m = total_distance_m + edge.distance_m
            if new_distance_m < best_distance_by_node.get(neighbor_id, math.inf) - NUMERICAL_EPS:
                best_distance_by_node[neighbor_id] = new_distance_m
                heapq.heappush(
                    queue,
                    (
                        new_distance_m,
                        nodes + (neighbor_id,),
                        edge_ids + (edge.edge_id,),
                        neighbor_id,
                    ),
                )
    return None


def _assignment_signature(assignments: dict[str, PathCandidate]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """
    Create a deterministic, order-independent signature for a set of demand path assignments.
    
    Parameters:
        assignments (dict[str, PathCandidate]): Mapping from demand ID to chosen path candidate.
    
    Returns:
        signature (tuple[tuple[str, tuple[str, ...]], ...]): A tuple of pairs (demand_id, nodes) sorted by `demand_id`, where `nodes` is the tuple of node IDs for that demand's path.
    """
    return tuple(
        (demand_id, assignments[demand_id].nodes)
        for demand_id in sorted(assignments)
    )


def _score_assignment(
    assignments: dict[str, PathCandidate],
    demand_by_id: dict[str, RelayDemand],
) -> tuple[float, float, tuple[tuple[str, tuple[str, ...]], ...]]:
    """
    Compute scoring components for a candidate assignment of demands to paths.
    
    Parameters:
        assignments (dict[str, PathCandidate]): Mapping from demand ID to chosen path candidate.
        demand_by_id (dict[str, RelayDemand]): Mapping from demand ID to its RelayDemand object (used to read weights).
    
    Returns:
        tuple:
            served_weight (float): Sum of weights for the demands present in `assignments`.
            total_latency_ms (float): Sum of propagation latencies for assigned paths in milliseconds (distance / c * 1000).
            signature (tuple[tuple[str, tuple[str, ...]], ...]): Deterministic, ordering-independent signature of the assignment used for tie-breaking.
    """
    served_weight = sum(demand_by_id[demand_id].weight for demand_id in assignments)
    total_latency_ms = sum(
        1000.0 * candidate.total_distance_m / LIGHT_SPEED_M_S
        for candidate in assignments.values()
    )
    return served_weight, total_latency_ms, _assignment_signature(assignments)


def _better_assignment(
    candidate: tuple[float, float, tuple[tuple[str, tuple[str, ...]], ...]],
    incumbent: tuple[float, float, tuple[tuple[str, tuple[str, ...]], ...]] | None,
) -> bool:
    """
    Determine whether a candidate assignment is preferable to the incumbent based on served weight, latency, and signature tie-breaker.
    
    Parameters:
        candidate (tuple): (served_weight, total_latency, signature) where
            served_weight (float) is the summed weight of served demands,
            total_latency (float) is the pooled latency metric (lower is better),
            signature (tuple) is a deterministic ordering-independent tuple used for final tie-breaking.
        incumbent (tuple | None): Same structure as `candidate`, or `None` to indicate no incumbent.
    
    Returns:
        bool: `True` if `candidate` is strictly preferred to `incumbent` according to the following priority:
            1. larger `served_weight` (uses NUMERICAL_EPS tolerance),
            2. lower `total_latency` (uses NUMERICAL_EPS tolerance) if weights are effectively equal,
            3. lexicographically smaller `signature` if both weight and latency are effectively equal.
    """
    if incumbent is None:
        return True
    candidate_weight, candidate_latency, candidate_signature = candidate
    incumbent_weight, incumbent_latency, incumbent_signature = incumbent
    if candidate_weight > incumbent_weight + NUMERICAL_EPS:
        return True
    if incumbent_weight > candidate_weight + NUMERICAL_EPS:
        return False
    if candidate_latency < incumbent_latency - NUMERICAL_EPS:
        return True
    if candidate_latency > incumbent_latency + NUMERICAL_EPS:
        return False
    return candidate_signature < incumbent_signature


def _build_sample_adjacency(
    active_edges: list[ValidatedAction],
    sample_index: int,
) -> dict[str, list[_SampleEdge]]:
    """
    Build an undirected adjacency map of nodes to neighboring sampled edges for a given sample index.
    
    Parameters:
    	active_edges (list[ValidatedAction]): Validated actions active at the sample; each provides `node_a`, `node_b`, `action_id`, and `distances_m_by_sample`.
    	sample_index (int): Index of the sample whose per-edge distances to use.
    
    Returns:
    	adjacency (dict[str, list[_SampleEdge]]): Mapping from node ID to a list of _SampleEdge entries representing neighbors active at the sample. Each list is sorted by `(distance_m, neighbor_id, edge_id)`.
    """
    adjacency: dict[str, list[_SampleEdge]] = defaultdict(list)
    for edge in active_edges:
        distance_m = edge.distances_m_by_sample[sample_index]
        adjacency[edge.node_a].append(
            _SampleEdge(edge_id=edge.action_id, neighbor_id=edge.node_b, distance_m=distance_m)
        )
        adjacency[edge.node_b].append(
            _SampleEdge(edge_id=edge.action_id, neighbor_id=edge.node_a, distance_m=distance_m)
        )
    for node_id in adjacency:
        adjacency[node_id].sort(key=lambda row: (row.distance_m, row.neighbor_id, row.edge_id))
    return adjacency


def _allocate_sample_demands(
    demands: list[RelayDemand],
    active_edges: list[ValidatedAction],
    sample_index: int,
    all_endpoint_ids: set[str],
) -> dict[str, PathCandidate]:
    """
    Selects and returns a best non-overlapping assignment of demand routes for a single sample instant.
    
    For the given sample index, builds the sample-specific adjacency from active edges and produces path candidates for each demand. If there is exactly one demand, returns its shortest feasible path candidate (if any). When multiple demands are present, searches for an assignment that uses disjoint edge sets and maximizes the sum of served demand weights; among assignments with equal served weight, selects the one with lower total latency (sum of path distances / c), and uses a deterministic signature tie-breaker for remaining ties.
    
    Parameters:
        demands (list[RelayDemand]): Demands active at this sample.
        active_edges (list[ValidatedAction]): Validated actions active at this sample providing edges and per-sample distances.
        sample_index (int): Sample index for which adjacency and per-edge distances are evaluated.
        all_endpoint_ids (set[str]): Set of endpoint node IDs (used to prevent routing through intermediate endpoints).
    
    Returns:
        dict[str, PathCandidate]: Mapping from demand_id to the chosen PathCandidate for served demands. Returns an empty dict if no feasible assignment exists.
    """
    if not demands or not active_edges:
        return {}

    adjacency = _build_sample_adjacency(active_edges, sample_index)
    if len(demands) == 1:
        demand = demands[0]
        candidate = _shortest_path_candidate(
            adjacency,
            demand.source_endpoint_id,
            demand.destination_endpoint_id,
            all_endpoint_ids,
        )
        return {demand.demand_id: candidate} if candidate is not None else {}

    demand_candidates: dict[str, list[PathCandidate]] = {}
    for demand in demands:
        demand_candidates[demand.demand_id] = _enumerate_paths(
            adjacency,
            demand.source_endpoint_id,
            demand.destination_endpoint_id,
            all_endpoint_ids,
        )

    demand_by_id = {demand.demand_id: demand for demand in demands}
    ordered_demands = sorted(
        demands,
        key=lambda demand: (len(demand_candidates[demand.demand_id]), demand.demand_id),
    )
    remaining_weights: list[float] = []
    running_weight = 0.0
    for demand in reversed(ordered_demands):
        running_weight += demand.weight
        remaining_weights.append(running_weight)
    remaining_weights.reverse()

    best_assignment: dict[str, PathCandidate] = {}
    best_score: tuple[float, float, tuple[tuple[str, tuple[str, ...]], ...]] | None = None

    def _search(
        demand_index: int,
        used_edges: set[str],
        assignments: dict[str, PathCandidate],
        served_weight: float,
        total_latency_ms: float,
    ) -> None:
        """
        Recursively searches for the best disjoint-path assignment for the ordered demands, maximizing total served demand weight and minimizing total latency as a tie-breaker.
        
        Performs depth-first backtracking over candidate paths for each demand, maintaining a set of already used edge IDs to ensure assignments are edge-disjoint. Prunes branches when the remaining possible served weight cannot beat the current best score or when equal-weight branches cannot improve latency.
        
        Parameters:
            demand_index (int): Index in the ordered_demands list to process next.
            used_edges (set[str]): Edge IDs already assigned to previous demands in the current partial solution.
            assignments (dict[str, PathCandidate]): Current partial mapping from demand_id to chosen PathCandidate.
            served_weight (float): Sum of weights of demands already assigned in the current partial solution.
            total_latency_ms (float): Cumulative latency (milliseconds) of the current partial solution.
        
        Returns:
            None
        """
        nonlocal best_assignment, best_score
        if demand_index >= len(ordered_demands):
            candidate_score = _score_assignment(assignments, demand_by_id)
            if _better_assignment(candidate_score, best_score):
                best_score = candidate_score
                best_assignment = dict(assignments)
            return

        max_possible_weight = served_weight + remaining_weights[demand_index]
        if best_score is not None and max_possible_weight < best_score[0] - NUMERICAL_EPS:
            return
        if (
            best_score is not None
            and abs(max_possible_weight - best_score[0]) <= NUMERICAL_EPS
            and total_latency_ms >= best_score[1] - NUMERICAL_EPS
        ):
            return

        demand = ordered_demands[demand_index]
        for candidate in demand_candidates[demand.demand_id]:
            if any(edge_id in used_edges for edge_id in candidate.edge_ids):
                continue
            assignments[demand.demand_id] = candidate
            for edge_id in candidate.edge_ids:
                used_edges.add(edge_id)
            _search(
                demand_index + 1,
                used_edges,
                assignments,
                served_weight + demand.weight,
                total_latency_ms + (1000.0 * candidate.total_distance_m / LIGHT_SPEED_M_S),
            )
            for edge_id in candidate.edge_ids:
                used_edges.remove(edge_id)
            assignments.pop(demand.demand_id, None)

        _search(demand_index + 1, used_edges, assignments, served_weight, total_latency_ms)

    _search(0, set(), {}, 0.0, 0.0)
    return best_assignment


def _percentile_95(values: list[float]) -> float | None:
    """
    Compute the 95th percentile of the provided numeric values.
    
    Parameters:
        values (list[float]): Sample values to compute the percentile from.
    
    Returns:
        float | None: The 95th percentile as a float if `values` is non-empty, `None` otherwise.
    """
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=float), 95))


def _schedule_action_failures(
    case: RelayCase,
    actions: list[RelayAction],
    violations: list[str],
) -> list[ActionFailure]:
    """
    Extracts action-indexed failures from textual violation messages and returns corresponding ActionFailure records.
    
    Parameters:
        case (RelayCase): The analyzed case (used only to provide context; not read by this function).
        actions (list[RelayAction]): List of actions to reference by index when constructing failures.
        violations (list[str]): Violation strings; those starting with "actions[<index>]" will be parsed to extract <index>.
    
    Returns:
        failures (list[ActionFailure]): Sorted list of ActionFailure objects for each well-formed "actions[<index>]" violation,
        with `sample_index` and `time` set to None.
    """
    failures: list[ActionFailure] = []
    for violation in violations:
        if not violation.startswith("actions["):
            continue
        index_end = violation.find("]")
        if index_end <= len("actions["):
            continue
        try:
            action_index = int(violation[len("actions[") : index_end])
        except ValueError:
            continue
        if not (0 <= action_index < len(actions)):
            continue
        action = actions[action_index]
        node_a = action.endpoint_id if action.action_type == "ground_link" else action.satellite_id_1
        node_b = action.satellite_id if action.action_type == "ground_link" else action.satellite_id_2
        failures.append(
            ActionFailure(
                action_index=action_index,
                action_type=action.action_type,
                reason=violation,
                node_a=node_a,
                node_b=node_b,
                sample_index=None,
                time=None,
            )
        )
    failures.sort(key=lambda row: row.action_index)
    return failures


def analyze(
    case: RelayCase,
    solution: RelaySolution,
    *,
    include_demand_sample_positions: bool = False,
) -> SolutionAnalysis:
    """
    Run full verification and allocation for a relay-constellation solution against a case.
    
    Performs orbit and schedule validation, propagates satellite positions for a reduced set of sample times,
    validates geometric feasibility and capacity constraints for scheduled actions, and if geometry passes,
    builds per-sample active-edge graphs and allocates demand samples to non-overlapping paths to compute
    service and latency metrics.
    
    Parameters:
        case (RelayCase): Problem case containing manifest, backbone satellites, endpoints, and demands.
        solution (RelaySolution): Proposed solution including added satellites and scheduled actions.
        include_demand_sample_positions (bool): If True, include demand sample instants in the propagated sample set
            so propagated satellite positions are available at demand times (default False).
    
    Returns:
        SolutionAnalysis: Complete analysis object containing the verification result (valid or not), diagnostics
        and metrics, propagation sample indices and lookups, propagated ECEF positions for referenced satellites,
        validated actions and any action failures, and per-sample allocation/route assignments when analysis succeeds.
    """
    metrics = _default_metrics(case, solution)

    orbit_violations, orbit_summaries = _validate_added_satellites(case, solution)
    schedule_violations, link_keys_by_action, sample_indices_by_action = _validate_action_schedule(
        case,
        solution,
        solution.actions,
    )
    violations = orbit_violations + schedule_violations
    schedule_action_failures = _schedule_action_failures(case, solution.actions, schedule_violations)
    demand_indices_by_id = {
        demand.demand_id: _demand_indices(case, demand)
        for demand in case.demands
    }
    if violations:
        result = VerificationResult(
            valid=False,
            metrics=metrics,
            violations=violations,
            diagnostics={
                "orbit_summaries": [row.to_dict() for row in orbit_summaries],
                "action_counts": {"total": len(solution.actions)},
                "action_failures": [row.to_dict() for row in schedule_action_failures],
            },
        )
        return SolutionAnalysis(
            case=case,
            solution=solution,
            result=result,
            propagation_sample_indices=(),
            demand_sample_indices_by_id=demand_indices_by_id,
            sample_lookup={},
            positions_ecef_by_satellite={},
            validated_actions=(),
            action_failures=tuple(schedule_action_failures),
            sample_allocations=(),
        )

    reduced_samples, demand_indices_by_id, demands_by_sample = _build_reduced_timeline(
        case,
        solution.actions,
        sample_indices_by_action,
    )
    referenced_satellite_ids = {
        satellite_id
        for action in solution.actions
        for satellite_id in (
            action.satellite_id,
            action.satellite_id_1,
            action.satellite_id_2,
        )
        if isinstance(satellite_id, str)
    }
    all_satellites = {
        satellite_id: satellite
        for satellite_id, satellite in {
            **case.backbone_satellites,
            **solution.added_satellites,
        }.items()
        if satellite_id in referenced_satellite_ids
    }
    propagation_samples = reduced_samples
    if include_demand_sample_positions:
        propagation_samples = sorted(set(reduced_samples) | set(demands_by_sample))
    sample_lookup, positions_ecef_by_satellite = _propagate_positions(
        case,
        all_satellites,
        propagation_samples,
    )
    geometry_violations, validated_actions, geometry_failures, action_counts, link_feasibility_counts = _validate_action_geometry(
        case,
        solution,
        solution.actions,
        link_keys_by_action,
        sample_indices_by_action,
        sample_lookup,
        positions_ecef_by_satellite,
    )
    if geometry_violations:
        result = VerificationResult(
            valid=False,
            metrics=metrics,
            violations=geometry_violations,
            diagnostics={
                "orbit_summaries": [row.to_dict() for row in orbit_summaries],
                "action_counts": action_counts,
                "link_feasibility": link_feasibility_counts,
                "action_failures": [row.to_dict() for row in geometry_failures],
            },
        )
        return SolutionAnalysis(
            case=case,
            solution=solution,
            result=result,
            propagation_sample_indices=tuple(propagation_samples),
            demand_sample_indices_by_id=demand_indices_by_id,
            sample_lookup=sample_lookup,
            positions_ecef_by_satellite=positions_ecef_by_satellite,
            validated_actions=tuple(validated_actions),
            action_failures=tuple(geometry_failures),
            sample_allocations=(),
        )

    active_edges_by_sample = _build_active_edges_by_sample(validated_actions)
    served_latencies_by_demand: dict[str, list[float]] = defaultdict(list)
    served_counts_by_demand: dict[str, int] = defaultdict(int)
    pooled_latencies_ms: list[float] = []
    sample_allocations: list[SampleAllocation] = []
    allocation_summary = {
        "sample_count_with_active_demands": 0,
        "served_demand_sample_count": 0,
        "unserved_demand_sample_count": 0,
    }

    for sample_index in sorted(demands_by_sample):
        active_demands = sorted(demands_by_sample[sample_index], key=lambda row: row.demand_id)
        allocation_summary["sample_count_with_active_demands"] += 1
        assignments = _allocate_sample_demands(
            active_demands,
            active_edges_by_sample.get(sample_index, []),
            sample_index,
            set(case.ground_endpoints),
        )
        served_routes: list[SampleRouteAssignment] = []
        served_this_sample = 0
        for demand in active_demands:
            candidate = assignments.get(demand.demand_id)
            if candidate is None:
                continue
            served_this_sample += 1
            latency_ms = 1000.0 * candidate.total_distance_m / LIGHT_SPEED_M_S
            served_counts_by_demand[demand.demand_id] += 1
            served_latencies_by_demand[demand.demand_id].append(latency_ms)
            pooled_latencies_ms.append(latency_ms)
            served_routes.append(
                SampleRouteAssignment(
                    demand_id=demand.demand_id,
                    nodes=candidate.nodes,
                    edge_ids=candidate.edge_ids,
                    total_distance_m=candidate.total_distance_m,
                    latency_ms=latency_ms,
                )
            )
        allocation_summary["served_demand_sample_count"] += served_this_sample
        allocation_summary["unserved_demand_sample_count"] += len(active_demands) - served_this_sample
        sample_allocations.append(
            SampleAllocation(
                sample_index=sample_index,
                time=_time_for_index(case, sample_index),
                active_demand_ids=tuple(demand.demand_id for demand in active_demands),
                served_routes=tuple(sorted(served_routes, key=lambda row: row.demand_id)),
            )
        )

    per_demand_metrics: dict[str, dict[str, float | int | None]] = {}
    weighted_service_numerator = 0.0
    total_weight = 0.0
    worst_service_fraction = None
    for demand in sorted(case.demands, key=lambda row: row.demand_id):
        requested_sample_count = len(demand_indices_by_id[demand.demand_id])
        served_sample_count = served_counts_by_demand[demand.demand_id]
        service_fraction = (
            served_sample_count / requested_sample_count
            if requested_sample_count > 0
            else 0.0
        )
        latencies_ms = served_latencies_by_demand[demand.demand_id]
        per_demand_metrics[demand.demand_id] = {
            "requested_sample_count": requested_sample_count,
            "served_sample_count": served_sample_count,
            "service_fraction": service_fraction,
            "mean_latency_ms": (
                float(np.mean(np.asarray(latencies_ms, dtype=float)))
                if latencies_ms
                else None
            ),
            "latency_p95_ms": _percentile_95(latencies_ms),
        }
        weighted_service_numerator += demand.weight * service_fraction
        total_weight += demand.weight
        worst_service_fraction = (
            service_fraction
            if worst_service_fraction is None
            else min(worst_service_fraction, service_fraction)
        )

    metrics = {
        "service_fraction": (
            weighted_service_numerator / total_weight if total_weight > 0.0 else 0.0
        ),
        "worst_demand_service_fraction": worst_service_fraction if worst_service_fraction is not None else 0.0,
        "mean_latency_ms": (
            float(np.mean(np.asarray(pooled_latencies_ms, dtype=float)))
            if pooled_latencies_ms
            else None
        ),
        "latency_p95_ms": _percentile_95(pooled_latencies_ms),
        "num_added_satellites": len(solution.added_satellites),
        "num_demanded_windows": len(case.demands),
        "num_backbone_satellites": len(case.backbone_satellites),
        "per_demand": per_demand_metrics,
    }
    diagnostics = {
        "orbit_summaries": [row.to_dict() for row in orbit_summaries],
        "action_counts": {
            **action_counts,
            "total": len(solution.actions),
        },
        "link_feasibility": link_feasibility_counts,
        "allocation": allocation_summary,
        "per_demand_served_sample_counts": {
            demand_id: served_counts_by_demand[demand_id]
            for demand_id in sorted(per_demand_metrics)
        },
        "reduced_sample_count": len(reduced_samples),
        "action_failures": [],
    }
    result = VerificationResult(
        valid=True,
        metrics=metrics,
        violations=[],
        diagnostics=diagnostics,
    )
    return SolutionAnalysis(
        case=case,
        solution=solution,
        result=result,
        propagation_sample_indices=tuple(propagation_samples),
        demand_sample_indices_by_id=demand_indices_by_id,
        sample_lookup=sample_lookup,
        positions_ecef_by_satellite=positions_ecef_by_satellite,
        validated_actions=tuple(validated_actions),
        action_failures=(),
        sample_allocations=tuple(sample_allocations),
    )


def verify(case: RelayCase, solution: RelaySolution) -> VerificationResult:
    """
    Run a full analysis for the given RelayCase and RelaySolution and return the verification result.
    
    Parameters:
        case (RelayCase): The problem case to analyze.
        solution (RelaySolution): The proposed solution to verify.
    
    Returns:
        VerificationResult: Result object containing the validity flag, discovered violations, and diagnostics.
    """
    return analyze(case, solution).result


def verify_solution(case_dir: str | Path, solution_path: str | Path) -> VerificationResult:
    """
    Load a case and solution from the given filesystem paths and run verification on them.
    
    If loading the case or solution raises FileNotFoundError or ValueError, returns a VerificationResult with valid set to False, metrics produced by _default_metrics(case, solution), violations containing the exception message, and empty diagnostics. Otherwise returns the result of verify(case, solution).
    
    Returns:
        VerificationResult: The verification outcome for the loaded case and solution.
    """
    case: RelayCase | None = None
    solution: RelaySolution | None = None
    try:
        case = load_case(case_dir)
        solution = load_solution(solution_path)
    except (FileNotFoundError, ValueError) as exc:
        return VerificationResult(
            valid=False,
            metrics=_default_metrics(case, solution),
            violations=[str(exc)],
            diagnostics={},
        )
    return verify(case, solution)


def analyze_solution(
    case_dir: str | Path,
    solution_path: str | Path,
    *,
    include_demand_sample_positions: bool = True,
) -> SolutionAnalysis:
    """
    Load a case and a solution from the given paths and run the full relay-constellation analysis.
    
    Parameters:
    	case_dir (str | Path): Path to the case directory to load.
    	solution_path (str | Path): Path to the solution file to load.
    	include_demand_sample_positions (bool): If True, include demand sample instants when propagating satellite positions for geometry checks and demand-position reporting.
    
    Returns:
    	SolutionAnalysis: The complete analysis result containing the verification outcome, diagnostics, propagated positions, validated actions, and allocation/latency metrics.
    """
    case = load_case(case_dir)
    solution = load_solution(solution_path)
    return analyze(
        case,
        solution,
        include_demand_sample_positions=include_demand_sample_positions,
    )
