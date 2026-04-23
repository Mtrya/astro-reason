"""Deterministic dataset generation for the aeossp_standard benchmark."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import math
from pathlib import Path
import random
from typing import Any

import brahe
import yaml
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

from .geometry import AccessInterval, derive_task_access_intervals, sample_orbit_grid
from .normalize import CityRecord, TleRecord, load_celestrak_csv, load_world_cities
from . import sources as sources_module

MIN_CANDIDATE_BATCH = 24
CITY_REACHABILITY_PREFILTER_MAX_SATELLITES = 8
EARTH_RADIUS_M = 6_371_000.0

_WORKER_CITIES: list[CityRecord] | None = None
_WORKER_LAND_GEOMETRY: Any | None = None

def _validate_path_segment(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "/" in value or "\\" in value:
        raise ValueError(f"{label} must be a non-empty single path segment")
    return value


def _require_mapping(mapping: object, label: str) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        raise ValueError(f"{label} must be a mapping")
    return mapping


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


def _require_str_list(mapping: dict[str, Any], key: str, label: str) -> list[str]:
    value = mapping.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label}.{key} must be a non-empty list")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{label}.{key} must contain only non-empty strings")
        normalized.append(item)
    return normalized


def _require_numeric_list(mapping: dict[str, Any], key: str, label: str) -> list[float]:
    value = mapping.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label}.{key} must be a non-empty list")
    normalized: list[float] = []
    for item in value:
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            raise ValueError(f"{label}.{key} must contain only numeric values")
        normalized.append(float(item))
    return normalized


def _require_probability(mapping: dict[str, Any], key: str, label: str) -> float:
    value = _require_float(mapping, key, label)
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{label}.{key} must be between 0.0 and 1.0")
    return value


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


def _require_supported_celestrak_snapshot_epoch(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    supported = sources_module.supported_celestrak_snapshot_epochs()
    if value not in supported:
        raise ValueError(
            "aeossp_standard only supports cached CelesTrak snapshot epochs "
            f"{', '.join(supported)}; got {value!r}"
        )
    return value


def _default_celestrak_snapshot_epoch(source_config: dict[str, Any]) -> str:
    celestrak = _require_mapping(source_config.get("celestrak"), "source.celestrak")
    return _require_supported_celestrak_snapshot_epoch(
        celestrak.get("snapshot_epoch_utc"),
        "source.celestrak.snapshot_epoch_utc",
    )


def _split_celestrak_snapshot_epoch(
    split_config: dict[str, Any],
    *,
    source_config: dict[str, Any],
    label: str,
) -> str:
    source_override = split_config.get("source")
    if source_override is None:
        return _default_celestrak_snapshot_epoch(source_config)
    split_source = _require_mapping(source_override, f"{label}.source")
    celestrak = _require_mapping(split_source.get("celestrak"), f"{label}.source.celestrak")
    return _require_supported_celestrak_snapshot_epoch(
        celestrak.get("snapshot_epoch_utc"),
        f"{label}.source.celestrak.snapshot_epoch_utc",
    )


def celestrak_snapshot_epochs_for_config(config: dict[str, Any]) -> tuple[str, ...]:
    source_config = _require_mapping(config.get("source"), "source")
    epochs = [_default_celestrak_snapshot_epoch(source_config)]
    for split_name, split_config in _require_mapping(config.get("splits"), "splits").items():
        split_payload = _require_mapping(split_config, f"splits.{split_name}")
        epochs.append(
            _split_celestrak_snapshot_epoch(
                split_payload,
                source_config=source_config,
                label=f"splits.{split_name}",
            )
        )
    return tuple(dict.fromkeys(epochs))


def load_generator_config(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"missing required splits config: {path}") from exc
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"failed to load splits config {path}: {exc}") from exc

    config = _require_mapping(payload, "splits config")
    source = _require_mapping(config.get("source"), "source")
    _require_mapping(source.get("celestrak"), "source.celestrak")
    _require_mapping(source.get("world_cities"), "source.world_cities")
    _require_mapping(source.get("natural_earth_land"), "source.natural_earth_land")
    _default_celestrak_snapshot_epoch(source)

    splits = _require_mapping(config.get("splits"), "splits")
    if not splits:
        raise ValueError("splits config must contain a non-empty top-level 'splits' mapping")

    for split_name, split_config in splits.items():
        _validate_path_segment(split_name, "split name")
        split_payload = _require_mapping(split_config, f"splits.{split_name}")
        _split_celestrak_snapshot_epoch(
            split_payload,
            source_config=source,
            label=f"splits.{split_name}",
        )
        case_count = _require_int(split_payload, "case_count", f"splits.{split_name}")
        if case_count <= 0:
            raise ValueError(f"splits.{split_name}.case_count must be positive")
        case_seed_stride = _require_int(split_payload, "case_seed_stride", f"splits.{split_name}")
        if case_seed_stride <= 0:
            raise ValueError(f"splits.{split_name}.case_seed_stride must be positive")
        _require_int(split_payload, "seed", f"splits.{split_name}")

        mission = _require_mapping(split_payload.get("mission"), f"splits.{split_name}.mission")
        for key in (
            "case_start_spacing_hours",
            "horizon_hours",
            "action_time_step_s",
            "geometry_sample_step_s",
            "resource_sample_step_s",
            "task_access_sample_step_s",
        ):
            if _require_int(mission, key, f"splits.{split_name}.mission") <= 0:
                raise ValueError(f"splits.{split_name}.mission.{key} must be positive")

        satellite_pool = _require_mapping(
            split_payload.get("satellite_pool"),
            f"splits.{split_name}.satellite_pool",
        )
        if _require_float(satellite_pool, "min_altitude_m", f"splits.{split_name}.satellite_pool") < 0:
            raise ValueError(f"splits.{split_name}.satellite_pool.min_altitude_m must be non-negative")
        if (
            _require_float(satellite_pool, "max_altitude_m", f"splits.{split_name}.satellite_pool")
            <= _require_float(satellite_pool, "min_altitude_m", f"splits.{split_name}.satellite_pool")
        ):
            raise ValueError(
                f"splits.{split_name}.satellite_pool.max_altitude_m must be greater than min_altitude_m"
            )
        if _require_int(satellite_pool, "min_retained_count", f"splits.{split_name}.satellite_pool") <= 0:
            raise ValueError(
                f"splits.{split_name}.satellite_pool.min_retained_count must be positive"
            )
        _require_str_list(satellite_pool, "include_name_tokens", f"splits.{split_name}.satellite_pool")
        _require_str_list(satellite_pool, "exclude_name_tokens", f"splits.{split_name}.satellite_pool")

        satellites = _require_mapping(split_payload.get("satellites"), f"splits.{split_name}.satellites")
        min_satellites = _require_int(satellites, "min_per_case", f"splits.{split_name}.satellites")
        max_satellites = _require_int(satellites, "max_per_case", f"splits.{split_name}.satellites")
        if min_satellites <= 0 or max_satellites < min_satellites:
            raise ValueError(
                f"splits.{split_name}.satellites must satisfy 0 < min_per_case <= max_per_case"
            )
        template_fractions = _require_mapping(
            satellites.get("template_fractions"),
            f"splits.{split_name}.satellites.template_fractions",
        )
        templates = _require_mapping(
            satellites.get("templates"),
            f"splits.{split_name}.satellites.templates",
        )
        required_templates = ("visible_agile", "visible_balanced", "infrared_balanced")
        fraction_sum = 0.0
        for template_name in required_templates:
            fraction_sum += _require_probability(
                template_fractions,
                template_name,
                f"splits.{split_name}.satellites.template_fractions",
            )
            _require_mapping(
                templates.get(template_name),
                f"splits.{split_name}.satellites.templates.{template_name}",
            )
        if not math.isclose(fraction_sum, 1.0, abs_tol=1e-9):
            raise ValueError(
                f"splits.{split_name}.satellites.template_fractions must sum to 1.0"
            )

        tasks = _require_mapping(split_payload.get("tasks"), f"splits.{split_name}.tasks")
        min_tasks = _require_int(tasks, "min_per_case", f"splits.{split_name}.tasks")
        max_tasks = _require_int(tasks, "max_per_case", f"splits.{split_name}.tasks")
        if min_tasks <= 0 or max_tasks < min_tasks:
            raise ValueError(
                f"splits.{split_name}.tasks must satisfy 0 < min_per_case <= max_per_case"
            )
        if _require_float(tasks, "min_target_separation_m", f"splits.{split_name}.tasks") <= 0.0:
            raise ValueError(
                f"splits.{split_name}.tasks.min_target_separation_m must be positive"
            )
        _require_probability(tasks, "city_fraction", f"splits.{split_name}.tasks")
        _require_probability(tasks, "visible_fraction", f"splits.{split_name}.tasks")
        _require_probability(tasks, "hotspot_probability", f"splits.{split_name}.tasks")
        if _require_int(tasks, "hotspot_count", f"splits.{split_name}.tasks") <= 0:
            raise ValueError(f"splits.{split_name}.tasks.hotspot_count must be positive")
        if _require_int(tasks, "hotspot_min_spacing_s", f"splits.{split_name}.tasks") <= 0:
            raise ValueError(
                f"splits.{split_name}.tasks.hotspot_min_spacing_s must be positive"
            )
        for key in (
            "city_weight_options",
            "background_weight_options",
            "duration_options_s",
            "hotspot_window_slack_options_s",
            "uniform_window_slack_options_s",
        ):
            _require_numeric_list(tasks, key, f"splits.{split_name}.tasks")

    smoke_split, smoke_case_id = _parse_smoke_case(config)
    split_payload = _require_mapping(splits.get(smoke_split), f"splits.{smoke_split}")
    case_count = _require_int(split_payload, "case_count", f"splits.{smoke_split}")
    try:
        smoke_case_number = int(smoke_case_id.removeprefix("case_"))
    except ValueError as exc:
        raise ValueError("example_smoke_case case_id must look like case_0001") from exc
    if smoke_case_number < 1 or smoke_case_number > case_count:
        raise ValueError(
            f"example_smoke_case {smoke_split}/{smoke_case_id} is outside the configured case_count"
        )
    return config


@dataclass(frozen=True)
class TaskSeed:
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    source_kind: str
    anchor_satellite_id: str | None = None


@dataclass(frozen=True)
class PlannedTask:
    seed: TaskSeed
    required_sensor_type: str
    required_duration_s: int
    weight: float
    release_time: datetime
    due_time: datetime
    access_interval: AccessInterval


@dataclass(frozen=True)
class GeneratedCase:
    order: int
    split_name: str
    case_id: str
    mission_payload: dict[str, Any]
    satellite_payload: dict[str, Any]
    task_payload: dict[str, Any]
    summary: dict[str, Any]


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
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(term))


def _unit_sphere_point(latitude_deg: float, longitude_deg: float) -> tuple[float, float, float]:
    lat = math.radians(latitude_deg)
    lon = math.radians(longitude_deg)
    cos_lat = math.cos(lat)
    return (
        cos_lat * math.cos(lon),
        cos_lat * math.sin(lon),
        math.sin(lat),
    )


class _TargetSeparationIndex:
    def __init__(
        self,
        *,
        min_target_separation_m: float,
        seeds: list[TaskSeed] | None = None,
    ) -> None:
        self._min_target_separation_m = min_target_separation_m
        self._min_chord = 2.0 * math.sin(min_target_separation_m / (2.0 * EARTH_RADIUS_M))
        self._cell_size = max(self._min_chord, 1.0e-12)
        self._cells: dict[tuple[int, int, int], list[tuple[float, float, float, float, float]]] = {}
        for seed in seeds or []:
            self.add(seed.latitude_deg, seed.longitude_deg)

    def clone(self) -> "_TargetSeparationIndex":
        clone = _TargetSeparationIndex(min_target_separation_m=self._min_target_separation_m)
        clone._cells = {cell: rows.copy() for cell, rows in self._cells.items()}
        return clone

    def _cell_for(self, point: tuple[float, float, float]) -> tuple[int, int, int]:
        return (
            math.floor(point[0] / self._cell_size),
            math.floor(point[1] / self._cell_size),
            math.floor(point[2] / self._cell_size),
        )

    def is_far_enough(self, latitude_deg: float, longitude_deg: float) -> bool:
        if self._min_target_separation_m <= 0.0:
            return True
        point = _unit_sphere_point(latitude_deg, longitude_deg)
        cell_x, cell_y, cell_z = self._cell_for(point)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for existing in self._cells.get((cell_x + dx, cell_y + dy, cell_z + dz), []):
                        chord = math.sqrt(
                            (point[0] - existing[0]) ** 2
                            + (point[1] - existing[1]) ** 2
                            + (point[2] - existing[2]) ** 2
                        )
                        if chord <= self._min_chord + 1.0e-12:
                            distance_m = _haversine_distance_m(
                                latitude_deg,
                                longitude_deg,
                                existing[3],
                                existing[4],
                            )
                            if distance_m < self._min_target_separation_m:
                                return False
        return True

    def add(self, latitude_deg: float, longitude_deg: float) -> None:
        point = _unit_sphere_point(latitude_deg, longitude_deg)
        self._cells.setdefault(self._cell_for(point), []).append(
            (point[0], point[1], point[2], latitude_deg, longitude_deg)
        )

    def add_seed(self, seed: TaskSeed) -> None:
        self.add(seed.latitude_deg, seed.longitude_deg)


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


def _load_land_geometry(geojson_path: Path):
    doc = json.loads(geojson_path.read_text(encoding="utf-8"))
    geometries = [shape(feature["geometry"]) for feature in doc["features"]]
    return prep(unary_union(geometries))


def _build_satellite_pool(
    celestrak_rows: list[TleRecord],
    *,
    satellite_pool_config: dict[str, Any],
) -> list[TleRecord]:
    include_tokens = tuple(
        token.upper()
        for token in _require_str_list(
            satellite_pool_config,
            "include_name_tokens",
            "satellite_pool",
        )
    )
    exclude_tokens = tuple(
        token.upper()
        for token in _require_str_list(
            satellite_pool_config,
            "exclude_name_tokens",
            "satellite_pool",
        )
    )
    min_altitude_m = _require_float(satellite_pool_config, "min_altitude_m", "satellite_pool")
    max_altitude_m = _require_float(satellite_pool_config, "max_altitude_m", "satellite_pool")
    retained = []
    for row in celestrak_rows:
        name_upper = row.name.upper()
        if not any(token in name_upper for token in include_tokens):
            continue
        if any(token in name_upper for token in exclude_tokens):
            continue
        if not (min_altitude_m <= row.altitude_m <= max_altitude_m):
            continue
        retained.append(row)
    retained.sort(key=lambda row: (row.name, row.norad_catalog_id))
    min_retained_count = _require_int(satellite_pool_config, "min_retained_count", "satellite_pool")
    if len(retained) < min_retained_count:
        raise ValueError(
            f"Only retained {len(retained)} EO satellites from the CelesTrak snapshot"
        )
    return retained


def _case_anchor_from_pool(retained_pool: list[TleRecord]) -> datetime:
    latest_epoch = max(_parse_iso_utc(row.epoch_iso) for row in retained_pool)
    return _ceil_to_next_hour(latest_epoch)


def _select_satellites(rng: random.Random, pool: list[TleRecord], count: int) -> list[TleRecord]:
    selected = rng.sample(pool, count)
    return sorted(selected, key=lambda row: row.norad_catalog_id)


def _assign_satellite_templates(
    rng: random.Random,
    count: int,
    *,
    satellites_config: dict[str, Any],
) -> list[str]:
    template_fractions = _require_mapping(
        satellites_config.get("template_fractions"),
        "satellites.template_fractions",
    )
    counts = _largest_remainder_counts(
        count,
        [
            (
                "infrared_balanced",
                _require_probability(
                    template_fractions,
                    "infrared_balanced",
                    "satellites.template_fractions",
                ),
            ),
            (
                "visible_agile",
                _require_probability(
                    template_fractions,
                    "visible_agile",
                    "satellites.template_fractions",
                ),
            ),
            (
                "visible_balanced",
                _require_probability(
                    template_fractions,
                    "visible_balanced",
                    "satellites.template_fractions",
                ),
            ),
        ],
    )
    assigned = (
        ["infrared_balanced"] * counts["infrared_balanced"]
        + ["visible_agile"] * counts["visible_agile"]
        + ["visible_balanced"] * counts["visible_balanced"]
    )
    rng.shuffle(assigned)
    return assigned


def _build_satellite_entry(
    record: TleRecord,
    template_name: str,
    satellite_index: int,
    *,
    satellites_config: dict[str, Any],
) -> dict[str, Any]:
    templates = _require_mapping(satellites_config.get("templates"), "satellites.templates")
    template = _require_mapping(templates.get(template_name), f"satellites.templates.{template_name}")
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


def _is_far_enough(
    lat: float,
    lon: float,
    accepted: list[TaskSeed],
    *,
    min_target_separation_m: float,
) -> bool:
    return all(
        _haversine_distance_m(lat, lon, existing.latitude_deg, existing.longitude_deg)
        >= min_target_separation_m
        for existing in accepted
    )


def _sample_city_tasks(
    rng: random.Random,
    cities: list[CityRecord],
    count: int,
    *,
    separation_index: _TargetSeparationIndex,
) -> list[TaskSeed]:
    buckets = _city_candidate_buckets(cities)
    bucket_names = sorted(buckets)
    bucket_offsets = {name: 0 for name in bucket_names}
    local_index = separation_index.clone()
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
        if not local_index.is_far_enough(
            candidate.latitude_deg,
            candidate.longitude_deg,
        ):
            attempts += 1
            continue
        seed = TaskSeed(
            name=f"{candidate.name}, {candidate.country}",
            latitude_deg=candidate.latitude_deg,
            longitude_deg=candidate.longitude_deg,
            altitude_m=0.0,
            source_kind="city",
        )
        selected.append(seed)
        local_index.add_seed(seed)
        attempts += 1
    if len(selected) < count:
        raise ValueError(f"Unable to sample {count} city tasks with the configured separation")
    return selected


def _sample_background_tasks(
    rng: random.Random,
    land_geometry,
    count: int,
    *,
    separation_index: _TargetSeparationIndex,
    orbit_grid: Any | None = None,
    compatible_satellite_ids: set[str] | None = None,
) -> list[TaskSeed]:
    local_index = separation_index.clone()
    selected: list[TaskSeed] = []
    attempts = 0
    max_attempts = max(20_000, count * 500)
    if orbit_grid is not None and compatible_satellite_ids:
        satellite_ids = sorted(compatible_satellite_ids)
        while len(selected) < count and attempts < max_attempts:
            satellite_id = rng.choice(satellite_ids)
            sampled_positions = orbit_grid.positions_ecef_m[satellite_id]
            sample_index = rng.randrange(sampled_positions.shape[0])
            lon, lat, _alt = brahe.position_ecef_to_geodetic(
                sampled_positions[sample_index],
                brahe.AngleFormat.DEGREES,
            )
            lon = float(lon)
            lat = float(lat)
            if not land_geometry.contains(Point(lon, lat)):
                attempts += 1
                continue
            if not local_index.is_far_enough(lat, lon):
                attempts += 1
                continue
            seed = TaskSeed(
                name=f"background_{len(selected) + 1:04d}",
                latitude_deg=lat,
                longitude_deg=lon,
                altitude_m=0.0,
                source_kind="background",
                anchor_satellite_id=satellite_id,
            )
            selected.append(seed)
            local_index.add_seed(seed)
            attempts += 1
        if len(selected) < count:
            raise ValueError(f"Unable to sample {count} background tasks with the configured separation")
        return selected

    while len(selected) < count and attempts < max_attempts:
        lon = rng.uniform(-180.0, 180.0)
        lat = math.degrees(math.asin(rng.uniform(-1.0, 1.0)))
        if not land_geometry.contains(Point(lon, lat)):
            attempts += 1
            continue
        if not local_index.is_far_enough(
            lat,
            lon,
        ):
            attempts += 1
            continue
        seed = TaskSeed(
            name=f"background_{len(selected) + 1:04d}",
            latitude_deg=lat,
            longitude_deg=lon,
            altitude_m=0.0,
            source_kind="background",
        )
        selected.append(seed)
        local_index.add_seed(seed)
        attempts += 1
    if len(selected) < count:
        raise ValueError(f"Unable to sample {count} background tasks with the configured separation")
    return selected


def _sample_hotspot_offsets(
    rng: random.Random,
    horizon_s: int,
    *,
    task_config: dict[str, Any],
) -> list[int]:
    offsets: list[int] = []
    hotspot_count = _require_int(task_config, "hotspot_count", "tasks")
    hotspot_min_spacing_s = _require_int(task_config, "hotspot_min_spacing_s", "tasks")
    while len(offsets) < hotspot_count:
        candidate = rng.randrange(0, horizon_s, 300)
        if all(abs(candidate - existing) >= hotspot_min_spacing_s for existing in offsets):
            offsets.append(candidate)
    offsets.sort()
    return offsets


def _task_weight_for_source(
    rng: random.Random,
    source_kind: str,
    *,
    task_config: dict[str, Any],
) -> float:
    if source_kind == "city":
        return rng.choice(_require_numeric_list(task_config, "city_weight_options", "tasks"))
    return rng.choice(_require_numeric_list(task_config, "background_weight_options", "tasks"))


def _group_task_counts(total: int, *, task_config: dict[str, Any]) -> dict[tuple[str, str], int]:
    city_fraction = _require_probability(task_config, "city_fraction", "tasks")
    visible_fraction = _require_probability(task_config, "visible_fraction", "tasks")
    flat_counts = _largest_remainder_counts(
        total,
        [
            ("city:visible", city_fraction * visible_fraction),
            ("city:infrared", city_fraction * (1.0 - visible_fraction)),
            ("background:visible", (1.0 - city_fraction) * visible_fraction),
            ("background:infrared", (1.0 - city_fraction) * (1.0 - visible_fraction)),
        ],
    )
    grouped: dict[tuple[str, str], int] = {}
    for key, value in flat_counts.items():
        source_kind, sensor_type = key.split(":")
        grouped[(source_kind, sensor_type)] = value
    return grouped


def _sample_candidate_seeds(
    rng: random.Random,
    *,
    source_kind: str,
    count: int,
    cities: list[CityRecord],
    land_geometry: Any,
    separation_index: _TargetSeparationIndex,
    orbit_grid: Any | None = None,
    compatible_satellite_ids: set[str] | None = None,
    candidate_cities: list[CityRecord] | None = None,
) -> list[TaskSeed]:
    if source_kind == "city":
        return _sample_city_tasks(
            rng,
            candidate_cities or cities,
            count,
            separation_index=separation_index,
        )
    return _sample_background_tasks(
        rng,
        land_geometry,
        count,
        separation_index=separation_index,
        orbit_grid=orbit_grid,
        compatible_satellite_ids=compatible_satellite_ids,
    )


def _adaptive_retry_budget(remaining: int, compatible_satellite_count: int) -> int:
    return max(
        12,
        remaining * 3,
        12 * (1 + max(0, 8 - compatible_satellite_count)),
    )


def _reachable_city_candidates(
    cities: list[CityRecord],
    *,
    satellites: list[dict[str, Any]],
    orbit_grid: Any,
    sensor_type: str,
    compatible_satellite_ids: set[str],
    task_config: dict[str, Any],
    min_reachable_count: int,
    max_checked_count: int,
) -> list[CityRecord]:
    min_duration_s = int(min(_require_numeric_list(task_config, "duration_options_s", "tasks")))
    reachable: list[CityRecord] = []
    buckets = _city_candidate_buckets(cities)
    bucket_names = sorted(buckets)
    bucket_offsets = {name: 0 for name in bucket_names}
    checked = 0
    while checked < max_checked_count and len(reachable) < min_reachable_count:
        exhausted = True
        for bucket in bucket_names:
            rows = buckets[bucket]
            offset = bucket_offsets[bucket]
            if offset >= len(rows):
                continue
            exhausted = False
            city = rows[offset]
            bucket_offsets[bucket] = offset + 1
            checked += 1
            if checked > max_checked_count:
                break
            intervals = derive_task_access_intervals(
                {
                    "latitude_deg": city.latitude_deg,
                    "longitude_deg": city.longitude_deg,
                    "altitude_m": 0.0,
                    "required_sensor_type": sensor_type,
                    "required_duration_s": min_duration_s,
                },
                satellites,
                orbit_grid,
                compatible_satellite_ids=compatible_satellite_ids,
                min_duration_s=min_duration_s,
            )
            if intervals:
                reachable.append(city)
        if exhausted:
            break
    return reachable or cities


def _round_down_to_step(seconds: int, step_s: int) -> int:
    return (seconds // step_s) * step_s


def _round_up_to_step(seconds: int, step_s: int) -> int:
    return ((seconds + step_s - 1) // step_s) * step_s


def _choose_access_interval(
    rng: random.Random,
    intervals: list[AccessInterval],
    *,
    horizon_start: datetime,
    hotspot_offsets_s: list[int],
    task_config: dict[str, Any],
) -> tuple[AccessInterval, bool]:
    if not intervals:
        raise ValueError("Cannot choose an access interval from an empty list")
    hotspot_mode = rng.random() < _require_probability(task_config, "hotspot_probability", "tasks")
    if not hotspot_mode:
        return rng.choice(intervals), False
    hotspot_offset_s = rng.choice(hotspot_offsets_s)
    return min(
        intervals,
        key=lambda interval: abs(
            int((interval.midpoint_time - horizon_start).total_seconds()) - hotspot_offset_s
        ),
    ), True


def _window_around_access(
    rng: random.Random,
    interval: AccessInterval,
    *,
    required_duration_s: int,
    horizon_start: datetime,
    horizon_end: datetime,
    hotspot_mode: bool,
    mission_config: dict[str, Any],
    task_config: dict[str, Any],
) -> tuple[datetime, datetime]:
    horizon_s = int((horizon_end - horizon_start).total_seconds())
    interval_start_s = int((interval.start_time - horizon_start).total_seconds())
    interval_end_s = int((interval.end_time - horizon_start).total_seconds())
    action_time_step_s = _require_int(mission_config, "action_time_step_s", "mission")
    slack_options = (
        _require_numeric_list(task_config, "hotspot_window_slack_options_s", "tasks")
        if hotspot_mode
        else _require_numeric_list(task_config, "uniform_window_slack_options_s", "tasks")
    )
    lead_slack_s = int(rng.choice(slack_options))
    trail_slack_s = int(rng.choice(slack_options))
    start_s = _round_down_to_step(max(0, interval_start_s - lead_slack_s), action_time_step_s)
    end_s = _round_up_to_step(min(horizon_s, interval_end_s + trail_slack_s), action_time_step_s)
    if end_s - start_s < required_duration_s:
        end_s = min(horizon_s, start_s + required_duration_s)
        start_s = max(0, end_s - required_duration_s)
        start_s = _round_down_to_step(start_s, action_time_step_s)
        end_s = _round_up_to_step(end_s, action_time_step_s)
    release_time = horizon_start + timedelta(seconds=start_s)
    due_time = horizon_start + timedelta(seconds=end_s)
    return release_time, due_time


def _provisional_task_like(
    seed: TaskSeed,
    *,
    sensor_type: str,
    required_duration_s: int,
) -> dict[str, Any]:
    return {
        "latitude_deg": seed.latitude_deg,
        "longitude_deg": seed.longitude_deg,
        "altitude_m": seed.altitude_m,
        "required_sensor_type": sensor_type,
        "required_duration_s": required_duration_s,
    }


def _build_task_entries(
    rng: random.Random,
    *,
    cities: list[CityRecord],
    land_geometry: Any,
    satellites: list[dict[str, Any]],
    horizon_start: datetime,
    horizon_end: datetime,
    task_count: int,
    split_config: dict[str, Any],
) -> list[dict[str, Any]]:
    mission_config = _require_mapping(split_config.get("mission"), "mission")
    task_config = _require_mapping(split_config.get("tasks"), "tasks")
    horizon_s = int((horizon_end - horizon_start).total_seconds())
    hotspot_offsets_s = _sample_hotspot_offsets(rng, horizon_s, task_config=task_config)
    orbit_grid = sample_orbit_grid(
        satellites,
        start_time=horizon_start,
        end_time=horizon_end,
        step_s=_require_int(mission_config, "task_access_sample_step_s", "mission"),
    )
    compatible_satellite_ids = {
        "visible": {
            sat["satellite_id"]
            for sat in satellites
            if sat["sensor"]["sensor_type"] == "visible"
        },
        "infrared": {
            sat["satellite_id"]
            for sat in satellites
            if sat["sensor"]["sensor_type"] == "infrared"
        },
    }
    group_counts = _group_task_counts(task_count, task_config=task_config)
    group_order = list(group_counts)
    rng.shuffle(group_order)
    accepted_seeds: list[TaskSeed] = []
    planned_tasks: list[PlannedTask] = []
    reachable_city_cache: dict[str, list[CityRecord]] = {}
    min_target_separation_m = _require_float(task_config, "min_target_separation_m", "tasks")
    separation_index = _TargetSeparationIndex(min_target_separation_m=min_target_separation_m)
    duration_options_s = [int(value) for value in _require_numeric_list(task_config, "duration_options_s", "tasks")]
    for source_kind, sensor_type in group_order:
        remaining = group_counts[(source_kind, sensor_type)]
        if remaining == 0:
            continue
        batch_rounds = 0
        stall_rounds = 0
        compatible_ids = compatible_satellite_ids[sensor_type]
        candidate_cities = cities
        if (
            source_kind == "city"
            and len(compatible_ids) <= CITY_REACHABILITY_PREFILTER_MAX_SATELLITES
        ):
            candidate_cities = reachable_city_cache.get(sensor_type)
            if candidate_cities is None:
                min_reachable_count = max(
                    MIN_CANDIDATE_BATCH * 4,
                    remaining * 4,
                    len(accepted_seeds) + remaining * 4,
                )
                candidate_cities = _reachable_city_candidates(
                    cities,
                    satellites=satellites,
                    orbit_grid=orbit_grid,
                    sensor_type=sensor_type,
                    compatible_satellite_ids=compatible_ids,
                    task_config=task_config,
                    min_reachable_count=min_reachable_count,
                    max_checked_count=min(
                        len(cities),
                        max(2000, min_reachable_count * 40),
                    ),
                )
                reachable_city_cache[sensor_type] = candidate_cities
        while remaining > 0:
            batch_size = max(MIN_CANDIDATE_BATCH, remaining * 2)
            if source_kind == "city":
                batch_size = max(1, min(batch_size, len(candidate_cities)))
            candidates = _sample_candidate_seeds(
                rng,
                source_kind=source_kind,
                count=batch_size,
                cities=cities,
                land_geometry=land_geometry,
                separation_index=separation_index,
                orbit_grid=orbit_grid,
                compatible_satellite_ids=compatible_ids,
                candidate_cities=candidate_cities,
            )
            accepted_this_round = 0
            for candidate in candidates:
                required_duration_s = rng.choice(duration_options_s)
                candidate_compatible_ids = (
                    {candidate.anchor_satellite_id}
                    if candidate.anchor_satellite_id is not None
                    else compatible_ids
                )
                intervals = derive_task_access_intervals(
                    _provisional_task_like(
                        candidate,
                        sensor_type=sensor_type,
                        required_duration_s=required_duration_s,
                    ),
                    satellites,
                    orbit_grid,
                    compatible_satellite_ids=candidate_compatible_ids,
                    min_duration_s=required_duration_s,
                )
                if not intervals:
                    continue
                selected_interval, hotspot_mode = _choose_access_interval(
                    rng,
                    intervals,
                    horizon_start=horizon_start,
                    hotspot_offsets_s=hotspot_offsets_s,
                    task_config=task_config,
                )
                release_time, due_time = _window_around_access(
                    rng,
                    selected_interval,
                    required_duration_s=required_duration_s,
                    horizon_start=horizon_start,
                    horizon_end=horizon_end,
                    hotspot_mode=hotspot_mode,
                    mission_config=mission_config,
                    task_config=task_config,
                )
                planned_tasks.append(
                    PlannedTask(
                        seed=candidate,
                        required_sensor_type=sensor_type,
                        required_duration_s=required_duration_s,
                        weight=_task_weight_for_source(rng, source_kind, task_config=task_config),
                        release_time=release_time,
                        due_time=due_time,
                        access_interval=selected_interval,
                    )
                )
                accepted_seeds.append(candidate)
                separation_index.add_seed(candidate)
                accepted_this_round += 1
                remaining -= 1
                if remaining == 0:
                    break
            batch_rounds += 1
            max_rounds = _adaptive_retry_budget(remaining, len(compatible_ids))
            if accepted_this_round == 0:
                stall_rounds += 1
            else:
                stall_rounds = 0
            if remaining == 0:
                break
            if stall_rounds >= max_rounds:
                raise ValueError(
                    f"Unable to find enough accessible {source_kind}/{sensor_type} tasks; "
                    f"{remaining} still missing after {batch_rounds} rounds "
                    f"({stall_rounds} consecutive empty rounds, budget={max_rounds})"
                )
    rng.shuffle(planned_tasks)
    tasks: list[dict[str, Any]] = []
    for index, plan in enumerate(planned_tasks, start=1):
        tasks.append(
            {
                "task_id": f"task_{index:04d}",
                "name": plan.seed.name,
                "latitude_deg": round(plan.seed.latitude_deg, 6),
                "longitude_deg": round(plan.seed.longitude_deg, 6),
                "altitude_m": round(plan.seed.altitude_m, 1),
                "release_time": _utc_iso(plan.release_time),
                "due_time": _utc_iso(plan.due_time),
                "required_duration_s": int(plan.required_duration_s),
                "required_sensor_type": plan.required_sensor_type,
                "weight": plan.weight,
            }
        )
    return tasks


def _mission_payload(
    case_id: str,
    horizon_start: datetime,
    horizon_end: datetime,
    *,
    mission_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "mission": {
            "case_id": case_id,
            "horizon_start": _utc_iso(horizon_start),
            "horizon_end": _utc_iso(horizon_end),
            "action_time_step_s": _require_int(mission_config, "action_time_step_s", "mission"),
            "geometry_sample_step_s": _require_int(mission_config, "geometry_sample_step_s", "mission"),
            "resource_sample_step_s": _require_int(mission_config, "resource_sample_step_s", "mission"),
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


def _case_seed(base_seed: int, case_index: int, *, case_seed_stride: int) -> int:
    return base_seed + case_index * case_seed_stride


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


def _task_source_mix(tasks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "city": sum(not task["name"].startswith("background_") for task in tasks),
        "background": sum(task["name"].startswith("background_") for task in tasks),
    }


def _build_generated_case(
    *,
    order: int,
    split_name: str,
    split_config: dict[str, Any],
    case_index: int,
    celestrak_snapshot_epoch_utc: str,
    retained_pool: list[TleRecord],
    anchor: datetime,
    cities: list[CityRecord],
    land_geometry: Any,
) -> GeneratedCase:
    mission_config = _require_mapping(split_config.get("mission"), "mission")
    satellites_config = _require_mapping(split_config.get("satellites"), "satellites")
    tasks_config = _require_mapping(split_config.get("tasks"), "tasks")
    seed = _require_int(split_config, "seed", "split")
    case_seed_stride = _require_int(split_config, "case_seed_stride", "split")
    case_start_spacing_hours = _require_int(mission_config, "case_start_spacing_hours", "mission")
    horizon_hours = _require_int(mission_config, "horizon_hours", "mission")

    case_id = _case_id(case_index)
    case_seed = _case_seed(seed, case_index, case_seed_stride=case_seed_stride)
    case_rng = random.Random(case_seed)
    horizon_start = anchor + timedelta(hours=(case_index - 1) * case_start_spacing_hours)
    horizon_end = horizon_start + timedelta(hours=horizon_hours)

    satellite_count = case_rng.randint(
        _require_int(satellites_config, "min_per_case", "satellites"),
        _require_int(satellites_config, "max_per_case", "satellites"),
    )
    task_count = case_rng.randint(
        _require_int(tasks_config, "min_per_case", "tasks"),
        _require_int(tasks_config, "max_per_case", "tasks"),
    )
    selected_satellites = _select_satellites(case_rng, retained_pool, satellite_count)
    templates = _assign_satellite_templates(
        case_rng,
        satellite_count,
        satellites_config=satellites_config,
    )
    satellite_entries = [
        _build_satellite_entry(
            record,
            template_name,
            satellite_index,
            satellites_config=satellites_config,
        )
        for satellite_index, (record, template_name) in enumerate(
            zip(selected_satellites, templates, strict=True),
            start=1,
        )
    ]

    task_entries = _build_task_entries(
        case_rng,
        cities=cities,
        land_geometry=land_geometry,
        satellites=satellite_entries,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        task_count=task_count,
        split_config=split_config,
    )
    mission_payload = _mission_payload(
        case_id,
        horizon_start,
        horizon_end,
        mission_config=mission_config,
    )
    _ensure_grid_contract(task_entries, mission_payload)

    relative_case_path = str(Path("cases") / split_name / case_id)
    summary = {
        "case_id": case_id,
        "split": split_name,
        "path": relative_case_path,
        "case_seed": case_seed,
        "num_satellites": len(satellite_entries),
        "num_tasks": len(task_entries),
        "horizon_hours": horizon_hours,
        "celestrak_snapshot_epoch_utc": celestrak_snapshot_epoch_utc,
        "satellite_sensor_mix": _satellite_sensor_mix(satellite_entries),
        "task_sensor_mix": _task_sensor_mix(task_entries),
        "task_source_mix": _task_source_mix(task_entries),
        "task_weight_summary": _task_weight_summary(task_entries),
        "norad_catalog_ids": [entry["norad_catalog_id"] for entry in satellite_entries],
    }
    return GeneratedCase(
        order=order,
        split_name=split_name,
        case_id=case_id,
        mission_payload=mission_payload,
        satellite_payload={"satellites": satellite_entries},
        task_payload={"tasks": task_entries},
        summary=summary,
    )


def _init_generation_worker(source_dir: str) -> None:
    global _WORKER_CITIES, _WORKER_LAND_GEOMETRY
    source_path = Path(source_dir)
    _WORKER_CITIES = load_world_cities(source_path / "world_cities" / "world_cities.csv")
    _WORKER_LAND_GEOMETRY = _load_land_geometry(
        source_path / "natural_earth" / "ne_110m_land.geojson"
    )


def _build_generated_case_worker(job: dict[str, Any]) -> GeneratedCase:
    if _WORKER_CITIES is None or _WORKER_LAND_GEOMETRY is None:
        raise RuntimeError("generation worker was not initialized")
    celestrak_snapshot_epoch_utc = str(job["celestrak_snapshot_epoch_utc"])
    split_config = _require_mapping(job["split_config"], "split")
    return _build_generated_case(
        order=int(job["order"]),
        split_name=str(job["split_name"]),
        split_config=split_config,
        case_index=int(job["case_index"]),
        celestrak_snapshot_epoch_utc=celestrak_snapshot_epoch_utc,
        retained_pool=job["retained_pool"],
        anchor=job["anchor"],
        cities=_WORKER_CITIES,
        land_geometry=_WORKER_LAND_GEOMETRY,
    )


def _write_generated_case(cases_dir: Path, generated_case: GeneratedCase) -> None:
    case_dir = cases_dir / generated_case.split_name / generated_case.case_id
    _write_yaml(case_dir / "mission.yaml", generated_case.mission_payload)
    _write_yaml(case_dir / "satellites.yaml", generated_case.satellite_payload)
    _write_yaml(case_dir / "tasks.yaml", generated_case.task_payload)


def generate_dataset(
    *,
    source_dir: Path,
    output_dir: Path,
    split_configs: dict[str, dict[str, Any]],
    example_smoke_case: str,
    source_config: dict[str, Any],
    jobs: int = 1,
) -> None:
    if jobs <= 0:
        raise ValueError("jobs must be positive")

    cities = load_world_cities(source_dir / "world_cities" / "world_cities.csv")
    land_geometry = _load_land_geometry(source_dir / "natural_earth" / "ne_110m_land.geojson")
    celestrak_rows_by_epoch: dict[str, list[TleRecord]] = {}

    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    case_summaries: list[dict[str, Any]] = []
    generated_case_paths: set[str] = set()
    case_jobs: list[dict[str, Any]] = []
    for split_name, split_config in split_configs.items():
        _require_mapping(split_config.get("mission"), "mission")
        case_count = _require_int(split_config, "case_count", "split")
        _require_mapping(split_config.get("satellites"), "satellites")
        _require_mapping(split_config.get("tasks"), "tasks")
        celestrak_snapshot_epoch_utc = _split_celestrak_snapshot_epoch(
            split_config,
            source_config=source_config,
            label=f"splits.{split_name}",
        )
        celestrak_rows = celestrak_rows_by_epoch.get(celestrak_snapshot_epoch_utc)
        if celestrak_rows is None:
            celestrak_rows = load_celestrak_csv(
                sources_module.celestrak_csv_path(source_dir, celestrak_snapshot_epoch_utc)
            )
            celestrak_rows_by_epoch[celestrak_snapshot_epoch_utc] = celestrak_rows

        retained_pool = _build_satellite_pool(
            celestrak_rows,
            satellite_pool_config=_require_mapping(split_config.get("satellite_pool"), "satellite_pool"),
        )
        anchor = _case_anchor_from_pool(retained_pool)
        (cases_dir / split_name).mkdir(parents=True, exist_ok=True)
        for case_index in range(1, case_count + 1):
            case_jobs.append(
                {
                    "order": len(case_jobs),
                    "split_name": split_name,
                    "split_config": split_config,
                    "case_index": case_index,
                    "celestrak_snapshot_epoch_utc": celestrak_snapshot_epoch_utc,
                    "retained_pool": retained_pool,
                    "anchor": anchor,
                }
            )

    generated_cases: list[GeneratedCase] = []
    if jobs == 1 or len(case_jobs) <= 1:
        for job in case_jobs:
            generated_cases.append(
                _build_generated_case(
                    order=int(job["order"]),
                    split_name=str(job["split_name"]),
                    split_config=_require_mapping(job["split_config"], "split"),
                    case_index=int(job["case_index"]),
                    celestrak_snapshot_epoch_utc=str(job["celestrak_snapshot_epoch_utc"]),
                    retained_pool=job["retained_pool"],
                    anchor=job["anchor"],
                    cities=cities,
                    land_geometry=land_geometry,
                )
            )
    else:
        with ProcessPoolExecutor(
            max_workers=jobs,
            initializer=_init_generation_worker,
            initargs=(str(source_dir),),
        ) as executor:
            generated_cases = list(executor.map(_build_generated_case_worker, case_jobs))

    for generated_case in sorted(generated_cases, key=lambda item: item.order):
        _write_generated_case(cases_dir, generated_case)
        generated_case_paths.add(f"{generated_case.split_name}/{generated_case.case_id}")
        case_summaries.append(generated_case.summary)

    if example_smoke_case not in generated_case_paths:
        raise ValueError(f"example_smoke_case {example_smoke_case} was not generated")

    index_payload = {
        "benchmark": "aeossp_standard",
        "example_smoke_case": example_smoke_case,
        "source": deepcopy(source_config),
        "splits": {
            split_name: {
                "seed": _require_int(split_config, "seed", "split"),
                "case_count": _require_int(split_config, "case_count", "split"),
                "case_seed_stride": _require_int(split_config, "case_seed_stride", "split"),
                "celestrak_snapshot_epoch_utc": _split_celestrak_snapshot_epoch(
                    split_config,
                    source_config=source_config,
                    label=f"splits.{split_name}",
                ),
            }
            for split_name, split_config in split_configs.items()
        },
        "cases": case_summaries,
    }
    _write_json(output_dir / "index.json", index_payload)
