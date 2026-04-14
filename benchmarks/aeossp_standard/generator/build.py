"""Deterministic dataset generation for the aeossp_standard benchmark."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import math
from pathlib import Path
import random
from typing import Any

import yaml
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

from .normalize import CityRecord, TleRecord, load_celestrak_csv, load_world_cities


CANONICAL_SEED = 42
NUM_CANONICAL_CASES = 5
HORIZON_HOURS = 12
ACTION_TIME_STEP_S = 5
GEOMETRY_SAMPLE_STEP_S = 5
RESOURCE_SAMPLE_STEP_S = 10

MIN_SATELLITES_PER_CASE = 20
MAX_SATELLITES_PER_CASE = 40
MIN_TASKS_PER_CASE = 200
MAX_TASKS_PER_CASE = 800
MIN_TARGET_SEPARATION_M = 25_000.0

CITY_TASK_FRACTION = 0.60
VISIBLE_TASK_FRACTION = 0.80
INFRARED_SATELLITE_FRACTION = 0.20
VISIBLE_AGILE_FRACTION = 0.32

CITY_TASK_WEIGHTS = (3.0, 4.0, 5.0)
BACKGROUND_TASK_WEIGHTS = (1.0, 1.5, 2.0)
TASK_DURATION_OPTIONS_S = tuple(range(15, 95, 5))
HOTSPOT_WIDTH_OPTIONS_S = (900, 1200, 1800, 2400, 3600, 5400)
UNIFORM_WIDTH_OPTIONS_S = (1800, 3600, 5400, 7200)
HOTSPOT_JITTER_OPTIONS_S = (-900, -600, -300, 0, 300, 600, 900)

INCLUDE_NAME_TOKENS = (
    "LANDSAT",
    "SENTINEL-2",
    "SPOT",
    "PLEIADES",
    "PNEO",
    "DEIMOS",
    "GAOFEN",
    "ZIYUAN",
    "SUPERDOVE",
    "SKYSAT",
    "KANOPUS",
    "FORMOSAT-5",
    "CARTOSAT",
    "RESOURCESAT",
    "THEOS",
    "EROS",
)

EXCLUDE_NAME_TOKENS = (
    "SAR",
    "ICEYE",
    "CAPELLA",
    "RADARSAT",
    "RISAT",
    "RCM",
    "SAOCOM",
    "COSMO",
    "UMBRA",
    "TERRASAR",
    "PAZ",
    "ALOS-2",
    "QPS-SAR",
    "STRIX",
)

TEMPLATE_DEFS: dict[str, dict[str, Any]] = {
    "visible_agile": {
        "sensor_type": "visible",
        "max_off_nadir_deg": 30.0,
        "max_slew_velocity_deg_per_s": 1.8,
        "max_slew_acceleration_deg_per_s2": 0.6,
        "settling_time_s": 2.0,
        "battery_capacity_wh": 1300.0,
        "initial_battery_wh": 910.0,
        "idle_power_w": 85.0,
        "imaging_power_w": 240.0,
        "slew_power_w": 140.0,
        "sunlit_charge_power_w": 260.0,
    },
    "visible_balanced": {
        "sensor_type": "visible",
        "max_off_nadir_deg": 25.0,
        "max_slew_velocity_deg_per_s": 1.2,
        "max_slew_acceleration_deg_per_s2": 0.35,
        "settling_time_s": 3.0,
        "battery_capacity_wh": 1600.0,
        "initial_battery_wh": 1120.0,
        "idle_power_w": 95.0,
        "imaging_power_w": 260.0,
        "slew_power_w": 155.0,
        "sunlit_charge_power_w": 245.0,
    },
    "infrared_balanced": {
        "sensor_type": "infrared",
        "max_off_nadir_deg": 20.0,
        "max_slew_velocity_deg_per_s": 0.9,
        "max_slew_acceleration_deg_per_s2": 0.25,
        "settling_time_s": 3.5,
        "battery_capacity_wh": 1800.0,
        "initial_battery_wh": 1260.0,
        "idle_power_w": 110.0,
        "imaging_power_w": 290.0,
        "slew_power_w": 165.0,
        "sunlit_charge_power_w": 250.0,
    },
}


@dataclass(frozen=True)
class TaskSeed:
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    source_kind: str


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(UTC)


def _ceil_to_next_hour(dt: datetime) -> datetime:
    dt = dt.astimezone(UTC)
    floored = dt.replace(minute=0, second=0, microsecond=0)
    if floored == dt:
        return dt
    return floored + timedelta(hours=1)


def _haversine_distance_m(
    lat_a_deg: float,
    lon_a_deg: float,
    lat_b_deg: float,
    lon_b_deg: float,
) -> float:
    radius_m = 6_371_000.0
    lat_a = math.radians(lat_a_deg)
    lon_a = math.radians(lon_a_deg)
    lat_b = math.radians(lat_b_deg)
    lon_b = math.radians(lon_b_deg)
    delta_lat = lat_b - lat_a
    delta_lon = lon_b - lon_a
    term = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * radius_m * math.asin(math.sqrt(term))


def _macro_region(latitude_deg: float, longitude_deg: float) -> str:
    if longitude_deg < -25.0:
        return "americas_north" if latitude_deg >= 12.0 else "americas_south"
    if longitude_deg < 60.0:
        return "europe_africa"
    if longitude_deg < 110.0:
        return "asia_west"
    return "asia_east_oceania"


def _largest_remainder_counts(total: int, proportions: list[tuple[str, float]]) -> dict[str, int]:
    raw = [(name, total * fraction) for name, fraction in proportions]
    counts = {name: int(math.floor(value)) for name, value in raw}
    remaining = total - sum(counts.values())
    remainders = sorted(
        ((value - counts[name], name) for name, value in raw),
        reverse=True,
    )
    for _, name in remainders[:remaining]:
        counts[name] += 1
    return counts


def _retain_eo_satellite(record: TleRecord) -> bool:
    name_upper = record.name.upper()
    if not any(token in name_upper for token in INCLUDE_NAME_TOKENS):
        return False
    if any(token in name_upper for token in EXCLUDE_NAME_TOKENS):
        return False
    if not (450_000.0 <= record.altitude_m <= 900_000.0):
        return False
    return True


def _load_land_geometry(geojson_path: Path):
    doc = json.loads(geojson_path.read_text(encoding="utf-8"))
    geometries = [shape(feature["geometry"]) for feature in doc["features"]]
    return prep(unary_union(geometries))


def _build_satellite_pool(celestrak_rows: list[TleRecord]) -> list[TleRecord]:
    retained = [row for row in celestrak_rows if _retain_eo_satellite(row)]
    retained.sort(key=lambda row: (row.name, row.norad_catalog_id))
    if len(retained) < 40:
        raise ValueError(f"Only retained {len(retained)} EO satellites from the CelesTrak snapshot")
    return retained


def _case_anchor_from_pool(retained_pool: list[TleRecord]) -> datetime:
    latest_epoch = max(_parse_iso_utc(row.epoch_iso) for row in retained_pool)
    return _ceil_to_next_hour(latest_epoch)


def _select_satellites(rng: random.Random, pool: list[TleRecord], count: int) -> list[TleRecord]:
    selected = rng.sample(pool, count)
    return sorted(selected, key=lambda row: row.norad_catalog_id)


def _assign_satellite_templates(rng: random.Random, count: int) -> list[str]:
    counts = _largest_remainder_counts(
        count,
        [
            ("infrared_balanced", INFRARED_SATELLITE_FRACTION),
            ("visible_agile", VISIBLE_AGILE_FRACTION),
            ("visible_balanced", 1.0 - INFRARED_SATELLITE_FRACTION - VISIBLE_AGILE_FRACTION),
        ],
    )
    assigned = (
        ["infrared_balanced"] * counts["infrared_balanced"]
        + ["visible_agile"] * counts["visible_agile"]
        + ["visible_balanced"] * counts["visible_balanced"]
    )
    rng.shuffle(assigned)
    return assigned


def _build_satellite_entry(record: TleRecord, template_name: str, satellite_index: int) -> dict[str, Any]:
    template = TEMPLATE_DEFS[template_name]
    return {
        "satellite_id": f"sat_{satellite_index:03d}",
        "norad_catalog_id": record.norad_catalog_id,
        "tle_line1": record.tle_line1,
        "tle_line2": record.tle_line2,
        "sensor": {
            "sensor_type": template["sensor_type"],
        },
        "attitude_model": {
            "max_slew_velocity_deg_per_s": template["max_slew_velocity_deg_per_s"],
            "max_slew_acceleration_deg_per_s2": template["max_slew_acceleration_deg_per_s2"],
            "settling_time_s": template["settling_time_s"],
            "max_off_nadir_deg": template["max_off_nadir_deg"],
        },
        "resource_model": {
            "battery_capacity_wh": template["battery_capacity_wh"],
            "initial_battery_wh": template["initial_battery_wh"],
            "idle_power_w": template["idle_power_w"],
            "imaging_power_w": template["imaging_power_w"],
            "slew_power_w": template["slew_power_w"],
            "sunlit_charge_power_w": template["sunlit_charge_power_w"],
        },
    }


def _city_candidate_buckets(cities: list[CityRecord]) -> dict[str, list[CityRecord]]:
    buckets: dict[str, list[CityRecord]] = {}
    for city in cities:
        bucket = _macro_region(city.latitude_deg, city.longitude_deg)
        buckets.setdefault(bucket, []).append(city)
    for bucket_rows in buckets.values():
        bucket_rows.sort(key=lambda city: (-city.population, city.name, city.country))
    return buckets


def _is_far_enough(lat: float, lon: float, accepted: list[TaskSeed]) -> bool:
    return all(
        _haversine_distance_m(lat, lon, existing.latitude_deg, existing.longitude_deg)
        >= MIN_TARGET_SEPARATION_M
        for existing in accepted
    )


def _sample_city_tasks(
    rng: random.Random,
    cities: list[CityRecord],
    count: int,
    accepted: list[TaskSeed],
) -> list[TaskSeed]:
    buckets = _city_candidate_buckets(cities)
    bucket_names = sorted(buckets)
    bucket_offsets = {name: 0 for name in bucket_names}
    selected: list[TaskSeed] = []
    attempts = 0
    while len(selected) < count and attempts < max(5000, count * 40):
        bucket = bucket_names[attempts % len(bucket_names)]
        rows = buckets[bucket]
        offset = bucket_offsets[bucket]
        if offset >= len(rows):
            attempts += 1
            continue
        head_limit = min(len(rows), offset + 12)
        candidate = rng.choice(rows[offset:head_limit])
        bucket_offsets[bucket] = min(len(rows), offset + 1)
        if not _is_far_enough(candidate.latitude_deg, candidate.longitude_deg, accepted + selected):
            attempts += 1
            continue
        selected.append(
            TaskSeed(
                name=f"{candidate.name}, {candidate.country}",
                latitude_deg=candidate.latitude_deg,
                longitude_deg=candidate.longitude_deg,
                altitude_m=0.0,
                source_kind="city",
            )
        )
        attempts += 1
    if len(selected) < count:
        raise ValueError(f"Unable to sample {count} city tasks with the configured separation")
    return selected


def _sample_background_tasks(
    rng: random.Random,
    land_geometry,
    count: int,
    accepted: list[TaskSeed],
) -> list[TaskSeed]:
    selected: list[TaskSeed] = []
    attempts = 0
    max_attempts = max(20_000, count * 500)
    while len(selected) < count and attempts < max_attempts:
        lon = rng.uniform(-180.0, 180.0)
        lat = math.degrees(math.asin(rng.uniform(-1.0, 1.0)))
        if not land_geometry.contains(Point(lon, lat)):
            attempts += 1
            continue
        if not _is_far_enough(lat, lon, accepted + selected):
            attempts += 1
            continue
        selected.append(
            TaskSeed(
                name=f"background_{len(selected) + 1:04d}",
                latitude_deg=lat,
                longitude_deg=lon,
                altitude_m=0.0,
                source_kind="background",
            )
        )
        attempts += 1
    if len(selected) < count:
        raise ValueError(f"Unable to sample {count} background tasks with the configured separation")
    return selected


def _sample_hotspot_offsets(rng: random.Random, horizon_s: int) -> list[int]:
    offsets: list[int] = []
    while len(offsets) < 4:
        candidate = rng.randrange(0, horizon_s, 300)
        if all(abs(candidate - existing) >= 3600 for existing in offsets):
            offsets.append(candidate)
    offsets.sort()
    return offsets


def _window_from_center(
    center_offset_s: int,
    width_s: int,
    *,
    horizon_s: int,
) -> tuple[int, int]:
    start = center_offset_s - width_s // 2
    end = start + width_s
    if start < 0:
        end -= start
        start = 0
    if end > horizon_s:
        shift = end - horizon_s
        start -= shift
        end = horizon_s
    return start, end


def _sample_task_window(
    rng: random.Random,
    hotspot_offsets_s: list[int],
    *,
    horizon_s: int,
) -> tuple[int, int]:
    if rng.random() < 0.70:
        center = rng.choice(hotspot_offsets_s) + rng.choice(HOTSPOT_JITTER_OPTIONS_S)
        center = max(0, min(horizon_s, center))
        width_s = rng.choice(HOTSPOT_WIDTH_OPTIONS_S)
    else:
        center = rng.randrange(0, horizon_s + ACTION_TIME_STEP_S, ACTION_TIME_STEP_S)
        width_s = rng.choice(UNIFORM_WIDTH_OPTIONS_S)
    return _window_from_center(center, width_s, horizon_s=horizon_s)


def _task_sensor_labels(rng: random.Random, count: int) -> list[str]:
    counts = _largest_remainder_counts(
        count,
        [
            ("visible", VISIBLE_TASK_FRACTION),
            ("infrared", 1.0 - VISIBLE_TASK_FRACTION),
        ],
    )
    labels = ["visible"] * counts["visible"] + ["infrared"] * counts["infrared"]
    rng.shuffle(labels)
    return labels


def _task_weight_for_source(rng: random.Random, source_kind: str) -> float:
    if source_kind == "city":
        return rng.choice(CITY_TASK_WEIGHTS)
    return rng.choice(BACKGROUND_TASK_WEIGHTS)


def _build_task_entries(
    rng: random.Random,
    seeds: list[TaskSeed],
    horizon_start: datetime,
    horizon_end: datetime,
) -> list[dict[str, Any]]:
    horizon_s = int((horizon_end - horizon_start).total_seconds())
    hotspot_offsets_s = _sample_hotspot_offsets(rng, horizon_s)
    sensor_labels = _task_sensor_labels(rng, len(seeds))
    tasks: list[dict[str, Any]] = []
    for index, seed in enumerate(seeds, start=1):
        required_duration_s = rng.choice(TASK_DURATION_OPTIONS_S)
        start_offset_s, end_offset_s = _sample_task_window(rng, hotspot_offsets_s, horizon_s=horizon_s)
        if end_offset_s - start_offset_s < required_duration_s:
            end_offset_s = min(horizon_s, start_offset_s + required_duration_s)
        release_time = horizon_start + timedelta(seconds=start_offset_s)
        due_time = horizon_start + timedelta(seconds=end_offset_s)
        tasks.append(
            {
                "task_id": f"task_{index:04d}",
                "name": seed.name,
                "latitude_deg": round(seed.latitude_deg, 6),
                "longitude_deg": round(seed.longitude_deg, 6),
                "altitude_m": round(seed.altitude_m, 1),
                "release_time": _utc_iso(release_time),
                "due_time": _utc_iso(due_time),
                "required_duration_s": int(required_duration_s),
                "required_sensor_type": sensor_labels[index - 1],
                "weight": _task_weight_for_source(rng, seed.source_kind),
            }
        )
    return tasks


def _mission_payload(case_id: str, horizon_start: datetime, horizon_end: datetime) -> dict[str, Any]:
    return {
        "mission": {
            "case_id": case_id,
            "horizon_start": _utc_iso(horizon_start),
            "horizon_end": _utc_iso(horizon_end),
            "action_time_step_s": ACTION_TIME_STEP_S,
            "geometry_sample_step_s": GEOMETRY_SAMPLE_STEP_S,
            "resource_sample_step_s": RESOURCE_SAMPLE_STEP_S,
            "propagation": {
                "model": "sgp4",
                "frame_inertial": "gcrf",
                "frame_fixed": "itrf",
                "earth_shape": "wgs84",
            },
            "scoring": {
                "ranking_order": ["valid", "WCR", "CR", "TAT", "PC"],
                "reported_metrics": ["CR", "WCR", "TAT", "PC"],
            },
        }
    }


def _case_seed(base_seed: int, case_index: int) -> int:
    return base_seed + case_index * 1009


def _case_id(case_index: int) -> str:
    return f"case_{case_index:04d}"


def _ensure_grid_contract(tasks: list[dict[str, Any]], mission: dict[str, Any]) -> None:
    horizon_start = _parse_iso_utc(mission["mission"]["horizon_start"])
    horizon_end = _parse_iso_utc(mission["mission"]["horizon_end"])
    action_step = mission["mission"]["action_time_step_s"]
    horizon_s = int((horizon_end - horizon_start).total_seconds())
    if horizon_s % action_step != 0:
        raise ValueError("Mission horizon is not divisible by the public action grid")
    for task in tasks:
        release = _parse_iso_utc(task["release_time"])
        due = _parse_iso_utc(task["due_time"])
        release_offset = int((release - horizon_start).total_seconds())
        due_offset = int((due - horizon_start).total_seconds())
        duration = int(task["required_duration_s"])
        if release < horizon_start or due > horizon_end:
            raise ValueError(f"Task {task['task_id']} lies outside the mission horizon")
        if release_offset % action_step != 0 or due_offset % action_step != 0 or duration % action_step != 0:
            raise ValueError(f"Task {task['task_id']} violates the public action grid")


def _satellite_sensor_mix(satellites: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(sat["sensor"]["sensor_type"] for sat in satellites))


def _task_sensor_mix(tasks: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(task["required_sensor_type"] for task in tasks))


def _task_weight_summary(tasks: list[dict[str, Any]]) -> dict[str, float]:
    weights = [float(task["weight"]) for task in tasks]
    return {
        "min": min(weights),
        "max": max(weights),
        "mean": round(sum(weights) / len(weights), 6),
    }


def generate_dataset(
    *,
    source_dir: Path,
    output_dir: Path,
    seed: int,
    case_count: int,
) -> None:
    celestrak_rows = load_celestrak_csv(source_dir / "celestrak" / "earth_resources.csv")
    cities = load_world_cities(source_dir / "world_cities" / "world_cities.csv")
    land_geometry = _load_land_geometry(source_dir / "natural_earth" / "ne_110m_land.geojson")

    retained_pool = _build_satellite_pool(celestrak_rows)
    anchor = _case_anchor_from_pool(retained_pool)
    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    case_ids: list[str] = []
    case_summaries: list[dict[str, Any]] = []
    for case_index in range(1, case_count + 1):
        case_id = _case_id(case_index)
        case_rng = random.Random(_case_seed(seed, case_index))
        horizon_start = anchor + timedelta(hours=(case_index - 1) * 2)
        horizon_end = horizon_start + timedelta(hours=HORIZON_HOURS)

        satellite_count = case_rng.randint(MIN_SATELLITES_PER_CASE, MAX_SATELLITES_PER_CASE)
        task_count = case_rng.randint(MIN_TASKS_PER_CASE, MAX_TASKS_PER_CASE)
        city_count = int(round(task_count * CITY_TASK_FRACTION))
        background_count = task_count - city_count

        selected_satellites = _select_satellites(case_rng, retained_pool, satellite_count)
        templates = _assign_satellite_templates(case_rng, satellite_count)
        satellite_entries = [
            _build_satellite_entry(record, template_name, satellite_index)
            for satellite_index, (record, template_name) in enumerate(
                zip(selected_satellites, templates, strict=True),
                start=1,
            )
        ]

        city_tasks = _sample_city_tasks(case_rng, cities, city_count, accepted=[])
        background_tasks = _sample_background_tasks(
            case_rng,
            land_geometry,
            background_count,
            accepted=city_tasks,
        )
        task_seeds = city_tasks + background_tasks
        case_rng.shuffle(task_seeds)
        task_entries = _build_task_entries(case_rng, task_seeds, horizon_start, horizon_end)
        mission_payload = _mission_payload(case_id, horizon_start, horizon_end)
        _ensure_grid_contract(task_entries, mission_payload)

        case_dir = cases_dir / case_id
        _write_yaml(case_dir / "mission.yaml", mission_payload)
        _write_yaml(case_dir / "satellites.yaml", {"satellites": satellite_entries})
        _write_yaml(case_dir / "tasks.yaml", {"tasks": task_entries})

        case_ids.append(case_id)
        case_summaries.append(
            {
                "case_id": case_id,
                "path": str(Path("cases") / case_id),
                "case_seed": _case_seed(seed, case_index),
                "num_satellites": len(satellite_entries),
                "num_tasks": len(task_entries),
                "horizon_hours": HORIZON_HOURS,
                "satellite_sensor_mix": _satellite_sensor_mix(satellite_entries),
                "task_sensor_mix": _task_sensor_mix(task_entries),
                "task_weight_summary": _task_weight_summary(task_entries),
                "norad_catalog_ids": [entry["norad_catalog_id"] for entry in satellite_entries],
            }
        )

    index_payload = {
        "benchmark": "aeossp_standard",
        "canonical_seed": seed,
        "case_ids": case_ids,
        "example_smoke_case_id": case_ids[0] if case_ids else None,
        "sources": {
            "celestrak": {
                "url": "https://celestrak.org/NORAD/elements/gp.php?GROUP=resource&FORMAT=tle",
                "path": "source_data/celestrak/earth_resources.csv",
            },
            "world_cities": {
                "url": "https://download.geonames.org/export/dump/cities15000.zip",
                "path": "source_data/world_cities/world_cities.csv",
            },
            "natural_earth_land": {
                "url": "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson",
                "path": "source_data/natural_earth/ne_110m_land.geojson",
            },
        },
        "cases": case_summaries,
    }
    _write_json(output_dir / "index.json", index_payload)
