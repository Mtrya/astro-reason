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


CANONICAL_SEED = 42
NUM_CANONICAL_CASES = 5
DEFAULT_DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"
SITE_LIBRARY_PATH = Path(__file__).with_name("site_library.json")

BASE_EPOCH = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
HORIZON_HOURS = 96
ROUTING_STEP_S = 60
WINDOW_START_GRID_MIN = 5
MIN_ENDPOINT_SEPARATION_DEG = 15.0
MIN_LONG_PAIR_DISTANCE_M = 7_000_000.0
MIN_MEDIUM_PAIR_DISTANCE_M = 2_500_000.0
MAX_MEDIUM_PAIR_DISTANCE_M = 6_500_000.0
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
    epoch: datetime,
) -> tuple[list[BackboneSatellite], MeoBackboneSummary]:
    _ensure_brahe_ready()
    total_satellites = _weighted_choice(rng, (6, 8, 10), (1, 3, 1))
    num_planes = _weighted_choice(rng, (2, 3), (2, 3))
    plane_counts = _partition_total(total_satellites, num_planes, rng, minimum=2)
    altitude_km = float(_weighted_choice(rng, (8_000.0, 10_000.0, 12_000.0, 14_000.0), (1, 2, 2, 1)))
    inclination_deg = float(_weighted_choice(rng, (45.0, 55.0, 63.0, 75.0), (1, 3, 3, 1)))
    eccentricity = rng.uniform(0.0002, 0.006)
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
) -> list[EndpointRecord]:
    num_endpoints = _weighted_choice(rng, (4, 5, 6), (2, 3, 2))
    candidates = list(site_library)
    for _ in range(200):
        chosen_sites = rng.sample(candidates, num_endpoints)
        if _min_pairwise_separation_deg(chosen_sites) < MIN_ENDPOINT_SEPARATION_DEG:
            continue
        pair_distances_m = [
            _haversine_distance_m(a.latitude_deg, a.longitude_deg, b.latitude_deg, b.longitude_deg)
            for a, b in itertools.combinations(chosen_sites, 2)
        ]
        if max(pair_distances_m) < MIN_LONG_PAIR_DISTANCE_M:
            continue
        if not any(
            MIN_MEDIUM_PAIR_DISTANCE_M <= distance_m <= MAX_MEDIUM_PAIR_DISTANCE_M
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
) -> list[DemandWindow]:
    endpoint_by_id = {endpoint.endpoint_id: endpoint for endpoint in endpoints}
    all_pairs = [(a.endpoint_id, b.endpoint_id) for a, b in itertools.combinations(endpoints, 2)]

    long_pairs = []
    medium_pairs = []
    other_pairs = []
    for source_id, destination_id in all_pairs:
        distance_m = _pair_distance_m(endpoint_by_id[source_id], endpoint_by_id[destination_id])
        if distance_m >= MIN_LONG_PAIR_DISTANCE_M:
            long_pairs.append((source_id, destination_id))
        elif MIN_MEDIUM_PAIR_DISTANCE_M <= distance_m <= MAX_MEDIUM_PAIR_DISTANCE_M:
            medium_pairs.append((source_id, destination_id))
        else:
            other_pairs.append((source_id, destination_id))

    pair_target = _weighted_choice(rng, (2, 3, 4, 5), (1, 2, 2, 1))
    selected_pairs: list[tuple[str, str]] = []
    selected_pair_set: set[tuple[str, str]] = set()
    if long_pairs:
        pair = rng.choice(long_pairs)
        selected_pairs.append(pair)
        selected_pair_set.add(pair)
    if medium_pairs and len(selected_pairs) < pair_target:
        pair = rng.choice([pair for pair in medium_pairs if pair not in selected_pair_set])
        selected_pairs.append(pair)
        selected_pair_set.add(pair)
    if len(selected_pairs) < pair_target:
        remaining = [pair for pair in all_pairs if pair not in selected_pair_set]
        rng.shuffle(remaining)
        selected_pairs.extend(remaining[: pair_target - len(selected_pairs)])

    selected_pairs = selected_pairs[:pair_target]
    if len(selected_pairs) < 2:
        raise RuntimeError("need at least two endpoint pairs for demand generation")

    total_demands = _weighted_choice(rng, (5, 6, 7, 8, 9), (1, 2, 3, 2, 1))
    total_demands = min(total_demands, 2 * len(selected_pairs))
    window_counts = [1] * len(selected_pairs)
    while sum(window_counts) < total_demands:
        index = rng.randrange(len(window_counts))
        if window_counts[index] < 2:
            window_counts[index] += 1

    horizon_minutes = int((horizon_end - horizon_start).total_seconds() // 60)
    duration_minutes_options = (
        30,
        45,
        60,
        75,
        90,
        120,
        150,
        180,
    )
    duration_weights = (1, 1, 2, 3, 3, 3, 1, 1)
    overlap_anchor_minutes = rng.randrange(6 * 60, 70 * 60, WINDOW_START_GRID_MIN)

    demands: list[DemandWindow] = []
    demand_counter = 0
    used_by_pair: defaultdict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    for pair_index, ((source_id, destination_id), window_count) in enumerate(
        zip(selected_pairs, window_counts, strict=True)
    ):
        for window_index in range(window_count):
            duration_minutes = _weighted_choice(rng, duration_minutes_options, duration_weights)
            if pair_index == 0 and window_index == 0:
                start_minutes = overlap_anchor_minutes
            elif pair_index == 1 and window_index == 0:
                offset_steps = rng.randint(-6, 6)
                start_minutes = max(
                    0,
                    min(
                        overlap_anchor_minutes + offset_steps * WINDOW_START_GRID_MIN,
                        horizon_minutes - duration_minutes,
                    ),
                )
            else:
                start_minutes = rng.randrange(
                    0,
                    horizon_minutes - duration_minutes + WINDOW_START_GRID_MIN,
                    WINDOW_START_GRID_MIN,
                )
            attempts = 0
            while attempts < 50:
                if all(
                    abs(start_minutes - prior_start) >= 180 or start_minutes >= prior_end
                    for prior_start, prior_end in used_by_pair[(source_id, destination_id)]
                ):
                    break
                start_minutes = rng.randrange(
                    0,
                    horizon_minutes - duration_minutes + WINDOW_START_GRID_MIN,
                    WINDOW_START_GRID_MIN,
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
) -> dict[str, Any]:
    return {
        "benchmark": "relay_constellation",
        "case_id": case_id,
        "constraints": {
            "max_added_satellites": max_added_satellites,
            "max_eccentricity": 0.02,
            "max_inclination_deg": 85.0,
            "max_isl_range_m": 20_000_000.0,
            "max_links_per_endpoint": 1,
            "max_links_per_satellite": 3,
            "max_altitude_m": 1_500_000.0,
            "min_altitude_m": 500_000.0,
            "min_inclination_deg": 20.0,
        },
        "epoch": _isoformat_z(epoch),
        "horizon_end": _isoformat_z(horizon_end),
        "horizon_start": _isoformat_z(horizon_start),
        "propagation": {
            "earth_fixed_frame": "itrf",
            "frame": "gcrf",
            "model": "j2",
        },
        "routing_step_s": ROUTING_STEP_S,
        "scoring": {
            "primary_metric": "service_fraction",
            "secondary_metric": "latency_p95_ms",
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
    case_index: int,
    seed: int,
    site_library: tuple[SiteRecord, ...],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    case_id = f"case_{case_index + 1:04d}"
    horizon_start = BASE_EPOCH + timedelta(hours=12 * case_index)
    horizon_end = horizon_start + timedelta(hours=HORIZON_HOURS)
    case_seed = seed + case_index * 10_007
    rng = random.Random(case_seed)
    max_added_satellites = _weighted_choice(rng, (4, 6, 8), (2, 3, 2))
    satellites, backbone_summary = _sample_backbone(rng, epoch=horizon_start)
    endpoints = _sample_endpoints(rng, site_library)
    demands = _sample_demand_windows(
        rng,
        horizon_start,
        horizon_end,
        endpoints,
    )

    manifest = _case_manifest(
        case_id=case_id,
        seed=case_seed,
        epoch=horizon_start,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        max_added_satellites=max_added_satellites,
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
        "case_id": case_id,
        "horizon_hours": HORIZON_HOURS,
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
    seed: int = CANONICAL_SEED,
    *,
    num_cases: int = NUM_CANONICAL_CASES,
) -> list[dict[str, Any]]:
    output_dir = output_dir.resolve()
    cases_dir = output_dir / "cases"
    if cases_dir.exists():
        shutil.rmtree(cases_dir)
    cases_dir.mkdir(parents=True, exist_ok=True)

    site_library = _load_site_library()
    summaries: list[dict[str, Any]] = []
    for case_index in range(num_cases):
        manifest, network, demands_payload, summary = _build_case(case_index, seed, site_library)
        case_id = manifest["case_id"]
        case_dir = cases_dir / case_id
        _write_json(case_dir / "manifest.json", manifest)
        _write_json(case_dir / "network.json", network)
        _write_json(case_dir / "demands.json", demands_payload)
        summaries.append(summary)

    _write_json(
        output_dir / "index.json",
        {
            "benchmark": "relay_constellation",
            "cases": [
                {
                    "case_id": summary["case_id"],
                    "horizon_hours": summary["horizon_hours"],
                    "max_added_satellites": summary["max_added_satellites"],
                    "num_backbone_satellites": summary["num_backbone_satellites"],
                    "num_demanded_windows": summary["num_demanded_windows"],
                    "num_endpoint_pairs": summary["num_endpoint_pairs"],
                    "num_ground_endpoints": summary["num_ground_endpoints"],
                    "path": f"cases/{summary['case_id']}",
                }
                for summary in summaries
            ],
            "example_smoke_case_id": "case_0005",
            "generator_seed": seed,
        },
    )
    return summaries
