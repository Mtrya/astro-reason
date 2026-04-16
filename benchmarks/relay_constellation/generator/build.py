"""Deterministic canonical dataset generator for relay_constellation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import itertools
import json
import math
from pathlib import Path
import random
import shutil
from typing import Any

import brahe
import numpy as np
import yaml


DEFAULT_DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"
SITE_LIBRARY_PATH = Path(__file__).with_name("site_library.json")
EARTH_RADIUS_M = float(brahe.R_EARTH)
_BRAHE_EOP_INITIALIZED = False


@dataclass(frozen=True)
class SiteRecord:
    site_id: str
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float


@dataclass(frozen=True)
class EndpointRecord:
    endpoint_id: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    min_elevation_deg: float
    ecef_position_m: tuple[float, float, float]


@dataclass(frozen=True)
class BackboneSatellite:
    satellite_id: str
    state_eci_m_mps: tuple[float, float, float, float, float, float]
    shell_index: int


@dataclass(frozen=True)
class DemandWindow:
    demand_id: str
    source_endpoint_id: str
    destination_endpoint_id: str
    start: datetime
    end: datetime
    weight: float


@dataclass(frozen=True)
class MeoBackboneSummary:
    count: int
    altitude_km: float
    inclination_deg: float
    num_planes: int


def _ensure_brahe_ready() -> None:
    global _BRAHE_EOP_INITIALIZED
    if _BRAHE_EOP_INITIALIZED:
        return
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    _BRAHE_EOP_INITIALIZED = True


def _validate_path_segment(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "/" in value or "\\" in value:
        raise ValueError(f"{label} must be a non-empty single path segment")
    return value


def _require_mapping(mapping: object, label: str) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        raise ValueError(f"{label} must be a mapping")
    return mapping


def _require_sequence(values: object, label: str) -> list[Any]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{label} must be a non-empty list")
    return values


def _require_int(mapping: dict[str, Any], key: str, label: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label}.{key} must be an integer")
    return value


def _require_float(mapping: dict[str, Any], key: str, label: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label}.{key} must be numeric")
    return float(value)


def _parse_iso8601_utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty ISO 8601 string")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _load_weighted_options(mapping: object, label: str) -> tuple[tuple[Any, ...], tuple[int, ...]]:
    payload = _require_mapping(mapping, label)
    values = _require_sequence(payload.get("values"), f"{label}.values")
    weights = _require_sequence(payload.get("weights"), f"{label}.weights")
    if len(values) != len(weights):
        raise ValueError(f"{label}.values and {label}.weights must have the same length")
    normalized_weights: list[int] = []
    for weight in weights:
        if not isinstance(weight, int) or isinstance(weight, bool) or weight <= 0:
            raise ValueError(f"{label}.weights entries must be positive integers")
        normalized_weights.append(weight)
    return tuple(values), tuple(normalized_weights)


def _load_numeric_range(mapping: object, label: str) -> tuple[float, float]:
    payload = _require_mapping(mapping, label)
    minimum = _require_float(payload, "min", label)
    maximum = _require_float(payload, "max", label)
    if minimum > maximum:
        raise ValueError(f"{label}.min must be <= {label}.max")
    return minimum, maximum


def _parse_smoke_case(config: dict[str, Any]) -> tuple[str, str]:
    smoke_case = config.get("example_smoke_case")
    if not isinstance(smoke_case, str) or not smoke_case:
        raise ValueError("splits config must include example_smoke_case")
    parts = smoke_case.split("/")
    if len(parts) != 2:
        raise ValueError("example_smoke_case must be formatted as <split>/<case_id>")
    return (
        _validate_path_segment(parts[0], "example_smoke_case split"),
        _validate_path_segment(parts[1], "example_smoke_case case_id"),
    )


def load_generator_config(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"missing required splits config: {path}") from exc
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"failed to load splits config {path}: {exc}") from exc

    config = _require_mapping(payload, "splits config")
    splits = _require_mapping(config.get("splits"), "splits")
    if not splits:
        raise ValueError("splits config must contain a non-empty top-level 'splits' mapping")
    for split_name, split_config in splits.items():
        _validate_path_segment(split_name, "split name")
        split_payload = _require_mapping(split_config, f"splits.{split_name}")
        _require_int(split_payload, "seed", f"splits.{split_name}")
        case_count = _require_int(split_payload, "case_count", f"splits.{split_name}")
        if case_count <= 0:
            raise ValueError(f"splits.{split_name}.case_count must be positive")
    smoke_split, smoke_case_id = _parse_smoke_case(config)
    smoke_split_config = splits.get(smoke_split)
    if smoke_split_config is None:
        raise ValueError(
            f"example_smoke_case {smoke_split}/{smoke_case_id} references unknown split {smoke_split!r}"
        )
    case_count = _require_int(smoke_split_config, "case_count", f"splits.{smoke_split}")
    try:
        smoke_case_number = int(smoke_case_id.removeprefix("case_"))
    except ValueError as exc:
        raise ValueError("example_smoke_case case_id must look like case_0001") from exc
    if smoke_case_number < 1 or smoke_case_number > case_count:
        raise ValueError(
            f"example_smoke_case {smoke_split}/{smoke_case_id} is outside the configured case_count"
        )
    return config


def _isoformat_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _haversine_distance_m(
    latitude_a_deg: float,
    longitude_a_deg: float,
    latitude_b_deg: float,
    longitude_b_deg: float,
) -> float:
    lat_a = math.radians(latitude_a_deg)
    lon_a = math.radians(longitude_a_deg)
    lat_b = math.radians(latitude_b_deg)
    lon_b = math.radians(longitude_b_deg)
    delta_lat = lat_b - lat_a
    delta_lon = lon_b - lon_a
    term = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(term))


def _min_pairwise_separation_deg(sites: list[SiteRecord]) -> float:
    min_deg = math.inf
    for site_a, site_b in itertools.combinations(sites, 2):
        distance_m = _haversine_distance_m(
            site_a.latitude_deg,
            site_a.longitude_deg,
            site_b.latitude_deg,
            site_b.longitude_deg,
        )
        min_deg = min(min_deg, math.degrees(distance_m / EARTH_RADIUS_M))
    return min_deg if math.isfinite(min_deg) else 180.0


def _load_site_library() -> tuple[SiteRecord, ...]:
    raw = json.loads(SITE_LIBRARY_PATH.read_text(encoding="utf-8"))
    sites = [
        SiteRecord(
            site_id=str(row["site_id"]),
            name=str(row["name"]),
            latitude_deg=float(row["latitude_deg"]),
            longitude_deg=float(row["longitude_deg"]),
            altitude_m=float(row["altitude_m"]),
        )
        for row in raw
    ]
    if len(sites) < 24:
        raise ValueError("site library must contain at least 24 sites")
    return tuple(sites)


def _weighted_choice(rng: random.Random, values: tuple[Any, ...], weights: tuple[int, ...]) -> Any:
    return rng.choices(values, weights=weights, k=1)[0]


def _partition_total(total: int, parts: int, rng: random.Random, minimum: int) -> list[int]:
    remaining = total - (parts * minimum)
    counts = [minimum] * parts
    for _ in range(remaining):
        counts[rng.randrange(parts)] += 1
    return counts


def _sample_backbone(
    rng: random.Random,
    *,
    config: dict[str, Any],
) -> tuple[list[BackboneSatellite], MeoBackboneSummary]:
    _ensure_brahe_ready()
    total_satellites_options, total_satellites_weights = _load_weighted_options(
        config.get("total_satellites"),
        "backbone.total_satellites",
    )
    num_planes_options, num_planes_weights = _load_weighted_options(
        config.get("num_planes"),
        "backbone.num_planes",
    )
    altitude_options, altitude_weights = _load_weighted_options(
        config.get("altitude_km"),
        "backbone.altitude_km",
    )
    inclination_options, inclination_weights = _load_weighted_options(
        config.get("inclination_deg"),
        "backbone.inclination_deg",
    )
    eccentricity_min, eccentricity_max = _load_numeric_range(
        config.get("eccentricity"),
        "backbone.eccentricity",
    )

    total_satellites = int(_weighted_choice(rng, total_satellites_options, total_satellites_weights))
    num_planes = int(_weighted_choice(rng, num_planes_options, num_planes_weights))
    plane_counts = _partition_total(total_satellites, num_planes, rng, minimum=2)
    altitude_km = float(_weighted_choice(rng, altitude_options, altitude_weights))
    inclination_deg = float(_weighted_choice(rng, inclination_options, inclination_weights))
    eccentricity = rng.uniform(eccentricity_min, eccentricity_max)
    argument_of_perigee_deg = rng.uniform(0.0, 360.0)
    shell_raan_offset_deg = rng.uniform(0.0, 360.0)
    shell_phase_offset_deg = rng.uniform(0.0, 360.0)
    semi_major_axis_m = EARTH_RADIUS_M + altitude_km * 1_000.0

    satellites: list[BackboneSatellite] = []
    satellite_counter = 0
    for plane_index, plane_count in enumerate(plane_counts):
        raan_deg = (shell_raan_offset_deg + plane_index * (360.0 / num_planes)) % 360.0
        for slot_index in range(plane_count):
            mean_anomaly_deg = (
                shell_phase_offset_deg
                + slot_index * (360.0 / plane_count)
                + plane_index * (180.0 / max(1, total_satellites))
            ) % 360.0
            koe = np.array(
                [
                    semi_major_axis_m,
                    eccentricity,
                    inclination_deg,
                    raan_deg,
                    argument_of_perigee_deg,
                    mean_anomaly_deg,
                ],
                dtype=float,
            )
            state_eci = brahe.state_koe_to_eci(koe, brahe.AngleFormat.DEGREES)
            satellite_counter += 1
            satellites.append(
                BackboneSatellite(
                    satellite_id=f"backbone_{satellite_counter:03d}",
                    state_eci_m_mps=tuple(float(value) for value in state_eci.tolist()),
                    shell_index=1,
                )
            )

    summary = MeoBackboneSummary(
        count=total_satellites,
        altitude_km=altitude_km,
        inclination_deg=inclination_deg,
        num_planes=num_planes,
    )
    return satellites, summary


def _sample_endpoints(
    rng: random.Random,
    site_library: tuple[SiteRecord, ...],
    config: dict[str, Any],
) -> list[EndpointRecord]:
    count_options, count_weights = _load_weighted_options(
        config.get("count"),
        "endpoints.count",
    )
    num_endpoints = int(_weighted_choice(rng, count_options, count_weights))
    min_endpoint_separation_deg = _require_float(
        config,
        "min_separation_deg",
        "endpoints",
    )
    min_long_pair_distance_m = _require_float(
        config,
        "long_pair_min_distance_m",
        "endpoints",
    )
    medium_pair_range = _require_mapping(config.get("medium_pair_distance_m"), "endpoints.medium_pair_distance_m")
    min_medium_pair_distance_m = _require_float(
        medium_pair_range,
        "min",
        "endpoints.medium_pair_distance_m",
    )
    max_medium_pair_distance_m = _require_float(
        medium_pair_range,
        "max",
        "endpoints.medium_pair_distance_m",
    )
    candidates = list(site_library)
    for _ in range(200):
        chosen_sites = rng.sample(candidates, num_endpoints)
        if _min_pairwise_separation_deg(chosen_sites) < min_endpoint_separation_deg:
            continue
        pair_distances_m = [
            _haversine_distance_m(a.latitude_deg, a.longitude_deg, b.latitude_deg, b.longitude_deg)
            for a, b in itertools.combinations(chosen_sites, 2)
        ]
        if max(pair_distances_m) < min_long_pair_distance_m:
            continue
        if not any(
            min_medium_pair_distance_m <= distance_m <= max_medium_pair_distance_m
            for distance_m in pair_distances_m
        ):
            continue

        endpoints: list[EndpointRecord] = []
        for index, site in enumerate(sorted(chosen_sites, key=lambda row: row.site_id), start=1):
            ecef = brahe.position_geodetic_to_ecef(
                [site.longitude_deg, site.latitude_deg, site.altitude_m],
                brahe.AngleFormat.DEGREES,
            )
            endpoints.append(
                EndpointRecord(
                    endpoint_id=f"ground_{index:03d}",
                    latitude_deg=site.latitude_deg,
                    longitude_deg=site.longitude_deg,
                    altitude_m=site.altitude_m,
                    min_elevation_deg=10.0,
                    ecef_position_m=tuple(float(value) for value in ecef.tolist()),
                )
            )
        return endpoints
    raise RuntimeError("failed to sample a sufficiently diverse endpoint set")


def _pair_distance_m(
    source: EndpointRecord,
    destination: EndpointRecord,
) -> float:
    return _haversine_distance_m(
        source.latitude_deg,
        source.longitude_deg,
        destination.latitude_deg,
        destination.longitude_deg,
    )


def _sample_demand_windows(
    rng: random.Random,
    horizon_start: datetime,
    horizon_end: datetime,
    endpoints: list[EndpointRecord],
    config: dict[str, Any],
    window_start_grid_min: int,
) -> list[DemandWindow]:
    endpoint_by_id = {endpoint.endpoint_id: endpoint for endpoint in endpoints}
    all_pairs = [(a.endpoint_id, b.endpoint_id) for a, b in itertools.combinations(endpoints, 2)]
    pair_count_options, pair_count_weights = _load_weighted_options(
        config.get("pair_count"),
        "demands.pair_count",
    )
    total_windows_options, total_windows_weights = _load_weighted_options(
        config.get("total_windows"),
        "demands.total_windows",
    )
    duration_options, duration_weights = _load_weighted_options(
        config.get("duration_minutes"),
        "demands.duration_minutes",
    )
    overlap_anchor_minutes = _require_mapping(
        config.get("overlap_anchor_minutes"),
        "demands.overlap_anchor_minutes",
    )
    secondary_pair_offset_steps = _require_mapping(
        config.get("secondary_pair_offset_steps"),
        "demands.secondary_pair_offset_steps",
    )
    min_repeat_gap_minutes = _require_int(config, "min_repeat_gap_minutes", "demands")
    retry_limit = _require_int(config, "retry_limit", "demands")
    min_long_pair_distance_m = _require_float(
        _require_mapping(config.get("endpoint_distance_m"), "demands.endpoint_distance_m"),
        "long_min",
        "demands.endpoint_distance_m",
    )
    medium_min_distance_m = _require_float(
        _require_mapping(config.get("endpoint_distance_m"), "demands.endpoint_distance_m"),
        "medium_min",
        "demands.endpoint_distance_m",
    )
    medium_max_distance_m = _require_float(
        _require_mapping(config.get("endpoint_distance_m"), "demands.endpoint_distance_m"),
        "medium_max",
        "demands.endpoint_distance_m",
    )

    long_pairs = []
    medium_pairs = []
    other_pairs = []
    for source_id, destination_id in all_pairs:
        distance_m = _pair_distance_m(endpoint_by_id[source_id], endpoint_by_id[destination_id])
        if distance_m >= min_long_pair_distance_m:
            long_pairs.append((source_id, destination_id))
        elif medium_min_distance_m <= distance_m <= medium_max_distance_m:
            medium_pairs.append((source_id, destination_id))
        else:
            other_pairs.append((source_id, destination_id))

    pair_target = int(_weighted_choice(rng, pair_count_options, pair_count_weights))
    selected_pairs: list[tuple[str, str]] = []
    selected_pair_set: set[tuple[str, str]] = set()
    if long_pairs:
        pair = rng.choice(long_pairs)
        selected_pairs.append(pair)
        selected_pair_set.add(pair)
    if medium_pairs and len(selected_pairs) < pair_target:
        medium_candidates = [pair for pair in medium_pairs if pair not in selected_pair_set]
        if medium_candidates:
            pair = rng.choice(medium_candidates)
            selected_pairs.append(pair)
            selected_pair_set.add(pair)
    if len(selected_pairs) < pair_target:
        remaining = [pair for pair in all_pairs if pair not in selected_pair_set]
        rng.shuffle(remaining)
        selected_pairs.extend(remaining[: pair_target - len(selected_pairs)])

    selected_pairs = selected_pairs[:pair_target]
    if len(selected_pairs) < 2:
        raise RuntimeError("need at least two endpoint pairs for demand generation")

    total_demands = int(_weighted_choice(rng, total_windows_options, total_windows_weights))
    total_demands = min(total_demands, 2 * len(selected_pairs))
    window_counts = [1] * len(selected_pairs)
    while sum(window_counts) < total_demands:
        index = rng.randrange(len(window_counts))
        if window_counts[index] < 2:
            window_counts[index] += 1

    horizon_minutes = int((horizon_end - horizon_start).total_seconds() // 60)
    overlap_anchor_minutes = rng.randrange(
        _require_int(overlap_anchor_minutes, "start", "demands.overlap_anchor_minutes"),
        _require_int(overlap_anchor_minutes, "stop", "demands.overlap_anchor_minutes"),
        _require_int(overlap_anchor_minutes, "step", "demands.overlap_anchor_minutes"),
    )

    demands: list[DemandWindow] = []
    demand_counter = 0
    used_by_pair: defaultdict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    for pair_index, ((source_id, destination_id), window_count) in enumerate(
        zip(selected_pairs, window_counts, strict=True)
    ):
        for window_index in range(window_count):
            duration_minutes = int(_weighted_choice(rng, duration_options, duration_weights))
            if pair_index == 0 and window_index == 0:
                start_minutes = overlap_anchor_minutes
            elif pair_index == 1 and window_index == 0:
                offset_steps = rng.randint(
                    _require_int(
                        secondary_pair_offset_steps,
                        "min",
                        "demands.secondary_pair_offset_steps",
                    ),
                    _require_int(
                        secondary_pair_offset_steps,
                        "max",
                        "demands.secondary_pair_offset_steps",
                    ),
                )
                start_minutes = max(
                    0,
                    min(
                        overlap_anchor_minutes + offset_steps * window_start_grid_min,
                        horizon_minutes - duration_minutes,
                    ),
                )
            else:
                start_minutes = rng.randrange(
                    0,
                    horizon_minutes - duration_minutes + window_start_grid_min,
                    window_start_grid_min,
                )
            attempts = 0
            while attempts < retry_limit:
                if all(
                    abs(start_minutes - prior_start) >= min_repeat_gap_minutes
                    or start_minutes >= prior_end
                    for prior_start, prior_end in used_by_pair[(source_id, destination_id)]
                ):
                    break
                start_minutes = rng.randrange(
                    0,
                    horizon_minutes - duration_minutes + window_start_grid_min,
                    window_start_grid_min,
                )
                attempts += 1
            used_by_pair[(source_id, destination_id)].append((start_minutes, start_minutes + duration_minutes))
            start = horizon_start + timedelta(minutes=start_minutes)
            end = start + timedelta(minutes=duration_minutes)
            demand_counter += 1
            demands.append(
                DemandWindow(
                    demand_id=f"demand_{demand_counter:03d}",
                    source_endpoint_id=source_id,
                    destination_endpoint_id=destination_id,
                    start=start,
                    end=end,
                    weight=1.0,
                )
            )
    demands.sort(key=lambda demand: (demand.start, demand.end, demand.demand_id))
    return demands


def _case_manifest(
    case_id: str,
    seed: int,
    epoch: datetime,
    horizon_start: datetime,
    horizon_end: datetime,
    max_added_satellites: int,
    routing_step_s: int,
    constraints_config: dict[str, Any],
) -> dict[str, Any]:
    orbit_constraints = _require_mapping(constraints_config.get("orbit"), "constraints.orbit")
    link_constraints = _require_mapping(constraints_config.get("links"), "constraints.links")
    return {
        "benchmark": "relay_constellation",
        "case_id": case_id,
        "constraints": {
            "max_added_satellites": max_added_satellites,
            "max_eccentricity": _require_float(orbit_constraints, "max_eccentricity", "constraints.orbit"),
            "max_inclination_deg": _require_float(orbit_constraints, "max_inclination_deg", "constraints.orbit"),
            "max_isl_range_m": _require_float(link_constraints, "max_isl_range_m", "constraints.links"),
            "max_links_per_endpoint": _require_int(
                link_constraints,
                "max_links_per_endpoint",
                "constraints.links",
            ),
            "max_links_per_satellite": _require_int(
                link_constraints,
                "max_links_per_satellite",
                "constraints.links",
            ),
            "max_altitude_m": _require_float(orbit_constraints, "max_altitude_m", "constraints.orbit"),
            "min_altitude_m": _require_float(orbit_constraints, "min_altitude_m", "constraints.orbit"),
            "min_inclination_deg": _require_float(orbit_constraints, "min_inclination_deg", "constraints.orbit"),
        },
        "epoch": _isoformat_z(epoch),
        "horizon_end": _isoformat_z(horizon_end),
        "horizon_start": _isoformat_z(horizon_start),
        "propagation": {
            "earth_fixed_frame": "itrf",
            "frame": "gcrf",
            "model": "j2",
        },
        "routing_step_s": routing_step_s,
        "scoring": {
            "primary_metric": "service_fraction",
            "secondary_metric": "worst_demand_service_fraction",
        },
        "seed": seed,
    }


def _case_network(
    endpoints: list[EndpointRecord],
    satellites: list[BackboneSatellite],
) -> dict[str, Any]:
    return {
        "backbone_satellites": [
            {
                "satellite_id": satellite.satellite_id,
                "x_m": satellite.state_eci_m_mps[0],
                "y_m": satellite.state_eci_m_mps[1],
                "z_m": satellite.state_eci_m_mps[2],
                "vx_m_s": satellite.state_eci_m_mps[3],
                "vy_m_s": satellite.state_eci_m_mps[4],
                "vz_m_s": satellite.state_eci_m_mps[5],
            }
            for satellite in satellites
        ],
        "ground_endpoints": [
            {
                "endpoint_id": endpoint.endpoint_id,
                "latitude_deg": endpoint.latitude_deg,
                "longitude_deg": endpoint.longitude_deg,
                "altitude_m": endpoint.altitude_m,
                "min_elevation_deg": endpoint.min_elevation_deg,
            }
            for endpoint in endpoints
        ],
    }


def _case_demands(
    demands: list[DemandWindow],
) -> dict[str, Any]:
    return {
        "demanded_windows": [
            {
                "demand_id": demand.demand_id,
                "source_endpoint_id": demand.source_endpoint_id,
                "destination_endpoint_id": demand.destination_endpoint_id,
                "start_time": _isoformat_z(demand.start),
                "end_time": _isoformat_z(demand.end),
                "weight": demand.weight,
            }
            for demand in demands
        ]
    }


def _build_case(
    split_name: str,
    case_index: int,
    split_config: dict[str, Any],
    site_library: tuple[SiteRecord, ...],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    case_id = f"case_{case_index + 1:04d}"
    schedule = _require_mapping(split_config.get("schedule"), f"splits.{split_name}.schedule")
    constraints = _require_mapping(split_config.get("constraints"), f"splits.{split_name}.constraints")
    base_epoch = _parse_iso8601_utc(
        str(schedule.get("base_epoch")),
        f"splits.{split_name}.schedule.base_epoch",
    )
    case_start_spacing_hours = _require_int(
        schedule,
        "case_start_spacing_hours",
        f"splits.{split_name}.schedule",
    )
    horizon_hours = _require_int(schedule, "horizon_hours", f"splits.{split_name}.schedule")
    routing_step_s = _require_int(schedule, "routing_step_s", f"splits.{split_name}.schedule")
    window_start_grid_min = _require_int(
        schedule,
        "window_start_grid_min",
        f"splits.{split_name}.schedule",
    )
    seed = _require_int(split_config, "seed", f"splits.{split_name}")
    case_seed_stride = _require_int(split_config, "case_seed_stride", f"splits.{split_name}")
    horizon_start = base_epoch + timedelta(hours=case_start_spacing_hours * case_index)
    horizon_end = horizon_start + timedelta(hours=horizon_hours)
    case_seed = seed + case_index * case_seed_stride
    rng = random.Random(case_seed)
    max_added_options, max_added_weights = _load_weighted_options(
        constraints.get("max_added_satellites"),
        "constraints.max_added_satellites",
    )
    max_added_satellites = int(_weighted_choice(rng, max_added_options, max_added_weights))
    satellites, backbone_summary = _sample_backbone(
        rng,
        config=_require_mapping(split_config.get("backbone"), f"splits.{split_name}.backbone"),
    )
    endpoints = _sample_endpoints(
        rng,
        site_library,
        _require_mapping(split_config.get("endpoints"), f"splits.{split_name}.endpoints"),
    )
    demands = _sample_demand_windows(
        rng,
        horizon_start,
        horizon_end,
        endpoints,
        _require_mapping(split_config.get("demands"), f"splits.{split_name}.demands"),
        window_start_grid_min,
    )

    manifest = _case_manifest(
        case_id=case_id,
        seed=case_seed,
        epoch=horizon_start,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        max_added_satellites=max_added_satellites,
        routing_step_s=routing_step_s,
        constraints_config=constraints,
    )
    network = _case_network(endpoints, satellites)
    demands_payload = _case_demands(demands)
    num_endpoint_pairs = len(
        {
            (demand.source_endpoint_id, demand.destination_endpoint_id)
            for demand in demands
        }
    )
    summary = {
        "split": split_name,
        "case_id": case_id,
        "horizon_hours": horizon_hours,
        "max_added_satellites": max_added_satellites,
        "num_backbone_satellites": len(satellites),
        "num_demanded_windows": len(demands),
        "num_endpoint_pairs": num_endpoint_pairs,
        "num_ground_endpoints": len(endpoints),
        "backbone": {
            "altitude_km": backbone_summary.altitude_km,
            "count": backbone_summary.count,
            "inclination_deg": backbone_summary.inclination_deg,
            "num_planes": backbone_summary.num_planes,
            "type": "meo",
        },
    }
    return manifest, network, demands_payload, summary


def generate_dataset(
    output_dir: Path,
    split_configs: dict[str, dict[str, Any]],
    example_smoke_case: str,
) -> list[dict[str, Any]]:
    output_dir = output_dir.resolve()
    cases_dir = output_dir / "cases"
    if cases_dir.exists():
        shutil.rmtree(cases_dir)
    cases_dir.mkdir(parents=True, exist_ok=True)

    site_library = _load_site_library()
    summaries: list[dict[str, Any]] = []
    smoke_split, smoke_case_id = example_smoke_case.split("/")
    smoke_found = False
    for split_name, split_config_obj in split_configs.items():
        split_config = _require_mapping(split_config_obj, f"splits.{split_name}")
        case_count = _require_int(split_config, "case_count", f"splits.{split_name}")
        for case_index in range(case_count):
            manifest, network, demands_payload, summary = _build_case(
                split_name,
                case_index,
                split_config,
                site_library,
            )
            case_id = manifest["case_id"]
            case_dir = cases_dir / split_name / case_id
            _write_json(case_dir / "manifest.json", manifest)
            _write_json(case_dir / "network.json", network)
            _write_json(case_dir / "demands.json", demands_payload)
            summaries.append(summary)
            if split_name == smoke_split and case_id == smoke_case_id:
                smoke_found = True

    if not smoke_found:
        raise ValueError(f"example_smoke_case {example_smoke_case} was not generated")

    unique_seeds = {
        _require_int(split_config, "seed", f"splits.{split_name}")
        for split_name, split_config in split_configs.items()
    }
    index_payload: dict[str, Any] = {
        "benchmark": "relay_constellation",
        "cases": [
            {
                "split": summary["split"],
                "case_id": summary["case_id"],
                "horizon_hours": summary["horizon_hours"],
                "max_added_satellites": summary["max_added_satellites"],
                "num_backbone_satellites": summary["num_backbone_satellites"],
                "num_demanded_windows": summary["num_demanded_windows"],
                "num_endpoint_pairs": summary["num_endpoint_pairs"],
                "num_ground_endpoints": summary["num_ground_endpoints"],
                "path": f"cases/{summary['split']}/{summary['case_id']}",
            }
            for summary in summaries
        ],
        "example_smoke_case": example_smoke_case,
    }
    if len(unique_seeds) == 1:
        index_payload["generator_seed"] = next(iter(unique_seeds))

    _write_json(
        output_dir / "index.json",
        index_payload,
    )
    return summaries
