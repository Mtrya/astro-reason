"""Case-generation logic for the revisit_constellation benchmark."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import random
import shutil
from typing import Any

import yaml


EARTH_RADIUS_M = 6_371_000.0

CITY_COLUMN_ALIASES = {
    "name": ("name", "city", "city_ascii", "city_name"),
    "country": ("country", "country_name"),
    "latitude_deg": ("latitude_deg", "latitude", "lat"),
    "longitude_deg": ("longitude_deg", "longitude", "lon", "lng"),
    "altitude_m": ("altitude_m", "altitude", "elevation_m"),
    "population": ("population", "population_proper", "population_total"),
}


@dataclass(frozen=True)
class CityRecord:
    name: str
    country: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    population: float


@dataclass(frozen=True)
class CaseSpec:
    split: str
    case_id: str
    target_count: int
    max_num_satellites: int
    revisit_threshold_hours: float


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


def _require_list(mapping: dict[str, Any], key: str, label: str) -> list[Any]:
    value = mapping.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label}.{key} must be a non-empty list")
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


def load_generator_config(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"missing required splits config: {path}") from exc
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"failed to load splits config {path}: {exc}") from exc

    config = _require_mapping(payload, "splits config")
    source = _require_mapping(config.get("source"), "source")
    _require_mapping(source.get("world_cities"), "source.world_cities")
    splits = _require_mapping(config.get("splits"), "splits")
    if not splits:
        raise ValueError("splits config must contain a non-empty top-level 'splits' mapping")
    for split_name, split_config in splits.items():
        _validate_path_segment(split_name, "split name")
        split_payload = _require_mapping(split_config, f"splits.{split_name}")
        case_count = _require_int(split_payload, "case_count", f"splits.{split_name}")
        if case_count <= 0:
            raise ValueError(f"splits.{split_name}.case_count must be positive")
        _require_int(split_payload, "seed", f"splits.{split_name}")
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


def _sample_case_spec(
    rng: random.Random,
    *,
    case_spec_config: dict[str, Any],
) -> tuple[int, int, float]:
    """Sample case parameters from the per-case RNG (same seeding policy as stereo_imaging)."""
    target_bounds = _require_mapping(case_spec_config.get("target_count"), "case_spec.target_count")
    satellite_bounds = _require_mapping(
        case_spec_config.get("max_num_satellites"),
        "case_spec.max_num_satellites",
    )

    target_count = rng.randint(
        _require_int(target_bounds, "min", "case_spec.target_count"),
        _require_int(target_bounds, "max", "case_spec.target_count"),
    )
    threshold_options = tuple(
        float(value) for value in _require_list(case_spec_config, "revisit_threshold_hours_options", "case_spec")
    )
    revisit_threshold_hours = rng.choice(threshold_options)
    satellite_max = _require_int(satellite_bounds, "max", "case_spec.max_num_satellites")
    if revisit_threshold_hours == 6.0:
        max_num_satellites = satellite_max
    else:
        max_num_satellites = rng.randint(
            _require_int(satellite_bounds, "min", "case_spec.max_num_satellites"),
            satellite_max,
        )
    return target_count, max_num_satellites, revisit_threshold_hours


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _normalize_header_lookup(fieldnames: list[str]) -> dict[str, str]:
    return {field.strip().lower(): field for field in fieldnames}


def _resolve_column(fieldnames: list[str], aliases: tuple[str, ...], context: str) -> str:
    lookup = _normalize_header_lookup(fieldnames)
    for alias in aliases:
        if alias.lower() in lookup:
            return lookup[alias.lower()]
    raise ValueError(f"{context} is missing one of the required columns: {', '.join(aliases)}")


def _resolve_optional_column(fieldnames: list[str], aliases: tuple[str, ...]) -> str | None:
    lookup = _normalize_header_lookup(fieldnames)
    for alias in aliases:
        if alias.lower() in lookup:
            return lookup[alias.lower()]
    return None


def _coerce_float(value: str | None, *, default: float | None = None) -> float:
    if value is None or value == "":
        if default is None:
            raise ValueError("Missing numeric value")
        return default
    return float(value)


def _slugify(value: str) -> str:
    lowered = value.lower()
    chars = [char if char.isalnum() else "_" for char in lowered]
    slug = "".join(chars)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def _city_key(city: CityRecord) -> tuple[str, float, float]:
    return (_slugify(city.name), round(city.latitude_deg, 3), round(city.longitude_deg, 3))


def _haversine_distance_m(
    latitude_a_deg: float,
    longitude_a_deg: float,
    latitude_b_deg: float,
    longitude_b_deg: float,
) -> float:
    latitude_a = math.radians(latitude_a_deg)
    longitude_a = math.radians(longitude_a_deg)
    latitude_b = math.radians(latitude_b_deg)
    longitude_b = math.radians(longitude_b_deg)
    delta_lat = latitude_b - latitude_a
    delta_lon = longitude_b - longitude_a
    term = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(latitude_a) * math.cos(latitude_b) * math.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(term))


def load_city_rows(csv_path: Path) -> list[CityRecord]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{csv_path} must contain a CSV header row")
        name_col = _resolve_column(reader.fieldnames, CITY_COLUMN_ALIASES["name"], "world cities CSV")
        country_col = _resolve_column(
            reader.fieldnames, CITY_COLUMN_ALIASES["country"], "world cities CSV"
        )
        lat_col = _resolve_column(
            reader.fieldnames, CITY_COLUMN_ALIASES["latitude_deg"], "world cities CSV"
        )
        lon_col = _resolve_column(
            reader.fieldnames, CITY_COLUMN_ALIASES["longitude_deg"], "world cities CSV"
        )
        altitude_col = _resolve_optional_column(reader.fieldnames, CITY_COLUMN_ALIASES["altitude_m"])
        population_col = _resolve_column(
            reader.fieldnames, CITY_COLUMN_ALIASES["population"], "world cities CSV"
        )

        unique_rows: dict[tuple[str, float, float], CityRecord] = {}
        for row in reader:
            try:
                city = CityRecord(
                    name=str(row[name_col]).strip(),
                    country=str(row[country_col]).strip(),
                    latitude_deg=_coerce_float(row.get(lat_col)),
                    longitude_deg=_coerce_float(row.get(lon_col)),
                    altitude_m=_coerce_float(
                        row.get(altitude_col) if altitude_col is not None else None,
                        default=0.0,
                    ),
                    population=_coerce_float(row.get(population_col)),
                )
            except ValueError:
                continue
            if not city.name or not city.country or city.population <= 0.0:
                continue
            key = _city_key(city)
            existing = unique_rows.get(key)
            if existing is None or city.population > existing.population:
                unique_rows[key] = city
    cities = sorted(unique_rows.values(), key=lambda city: (-city.population, city.name))
    if not cities:
        raise ValueError(f"No usable city rows found in {csv_path}")
    return cities


def build_case_specs(split_name: str, split_config: dict[str, Any]) -> list[CaseSpec]:
    case_count = _require_int(split_config, "case_count", f"splits.{split_name}")
    seed = _require_int(split_config, "seed", f"splits.{split_name}")
    case_spec_seed_stride = _require_int(
        split_config,
        "case_spec_seed_stride",
        f"splits.{split_name}",
    )
    case_spec_config = _require_mapping(split_config.get("case_spec"), f"splits.{split_name}.case_spec")
    specs: list[CaseSpec] = []
    for case_index in range(case_count):
        # Per-case stream depends only on `seed` and `case_index` (see stereo_imaging `generate_dataset`).
        case_rng = random.Random(seed + case_index * case_spec_seed_stride)
        tc, ms, thr_h = _sample_case_spec(case_rng, case_spec_config=case_spec_config)
        specs.append(
            CaseSpec(
                split=split_name,
                case_id=f"case_{case_index + 1:04d}",
                target_count=tc,
                max_num_satellites=ms,
                revisit_threshold_hours=thr_h,
            )
        )
    return specs


def _select_initial_index(length: int, seed: int) -> int:
    rng = random.Random(seed)
    return rng.randrange(length)


def select_targets(
    cities: list[CityRecord],
    count: int,
    *,
    seed: int,
    min_target_separation_m: float,
    initial_pool_min_size: int,
    initial_pool_multiplier: int,
    max_abs_latitude_deg: float | None = None,
) -> list[CityRecord]:
    if max_abs_latitude_deg is not None:
        cities = [city for city in cities if abs(city.latitude_deg) < max_abs_latitude_deg]
    if count > len(cities):
        raise ValueError(f"Requested {count} targets, but only {len(cities)} cities are available")

    start_index = _select_initial_index(
        min(len(cities), max(initial_pool_min_size, count * initial_pool_multiplier)),
        seed,
    )
    selected = [cities[start_index]]
    remaining = [city for index, city in enumerate(cities) if index != start_index]

    while len(selected) < count:
        best_city: CityRecord | None = None
        best_distance = -1.0
        for city in remaining:
            min_distance = min(
                _haversine_distance_m(
                    city.latitude_deg,
                    city.longitude_deg,
                    existing.latitude_deg,
                    existing.longitude_deg,
                )
                for existing in selected
            )
            if min_distance < min_target_separation_m:
                continue
            if min_distance > best_distance:
                best_distance = min_distance
                best_city = city
        if best_city is None:
            raise ValueError(
                f"Unable to select {count} cities with {min_target_separation_m / 1000:.0f} km separation"
            )
        selected.append(best_city)
        remaining.remove(best_city)
    return sorted(selected, key=lambda city: city.name)


def build_assets_payload(case_spec: CaseSpec, satellite_model: dict[str, Any]) -> dict[str, Any]:
    return {
        "satellite_model": satellite_model,
        "max_num_satellites": case_spec.max_num_satellites,
    }


def build_mission_payload(
    case_spec: CaseSpec,
    targets: list[CityRecord],
    mission_config: dict[str, Any],
) -> dict[str, Any]:
    target_defaults = _require_mapping(mission_config.get("target_defaults"), "mission.target_defaults")
    return {
        "horizon_start": str(mission_config["horizon_start"]),
        "horizon_end": str(mission_config["horizon_end"]),
        "targets": [
            {
                "id": f"target_{index + 1:03d}",
                "name": f"{target.name}, {target.country}",
                "latitude_deg": target.latitude_deg,
                "longitude_deg": target.longitude_deg,
                "altitude_m": target.altitude_m,
                "expected_revisit_period_hours": case_spec.revisit_threshold_hours,
                "min_elevation_deg": _require_float(
                    target_defaults,
                    "min_elevation_deg",
                    "mission.target_defaults",
                ),
                "max_slant_range_m": _require_float(
                    target_defaults,
                    "max_slant_range_m",
                    "mission.target_defaults",
                ),
                "min_duration_sec": _require_float(
                    target_defaults,
                    "min_duration_sec",
                    "mission.target_defaults",
                ),
            }
            for index, target in enumerate(targets)
        ],
    }


def build_index_payload(
    case_specs: list[CaseSpec],
    *,
    split_configs: dict[str, dict[str, Any]],
    example_smoke_case: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    horizon_hours = None
    unique_seeds = {
        _require_int(split_config, "seed", f"splits.{split_name}")
        for split_name, split_config in split_configs.items()
    }
    if split_configs:
        first_split_name = next(iter(split_configs))
        mission = _require_mapping(split_configs[first_split_name].get("mission"), f"splits.{first_split_name}.mission")
        horizon_start = mission.get("horizon_start")
        horizon_end = mission.get("horizon_end")
        if isinstance(horizon_start, str) and isinstance(horizon_end, str):
            start_dt = datetime.fromisoformat(horizon_start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(horizon_end.replace("Z", "+00:00"))
            horizon_hours = int((end_dt - start_dt).total_seconds() // 3600)

    payload: dict[str, Any] = {
        "benchmark": "revisit_constellation",
        "source": source,
        "example_smoke_case": example_smoke_case,
        "cases": [
            {
                "split": case_spec.split,
                "case_id": case_spec.case_id,
                "path": f"cases/{case_spec.split}/{case_spec.case_id}",
                "target_count": case_spec.target_count,
                "max_num_satellites": case_spec.max_num_satellites,
                "uniform_revisit_threshold_hours": case_spec.revisit_threshold_hours,
            }
            for case_spec in case_specs
        ],
    }
    if horizon_hours is not None:
        payload["horizon_hours"] = horizon_hours
    if len(unique_seeds) == 1:
        payload["generator_seed"] = next(iter(unique_seeds))
    return payload


def generate_dataset(
    *,
    world_cities_path: Path,
    output_dir: Path,
    split_configs: dict[str, dict[str, Any]],
    source: dict[str, Any],
    example_smoke_case: str,
) -> Path:
    cities = load_city_rows(world_cities_path)
    case_specs: list[CaseSpec] = []
    for split_name, split_config_obj in split_configs.items():
        case_specs.extend(build_case_specs(split_name, _require_mapping(split_config_obj, f"splits.{split_name}")))

    cases_dir = output_dir / "cases"
    shutil.rmtree(cases_dir, ignore_errors=True)
    cases_dir.mkdir(parents=True, exist_ok=True)

    example_solution: dict | None = None
    smoke_split, smoke_case_id = example_smoke_case.split("/")

    for split_name, split_config_obj in split_configs.items():
        split_config = _require_mapping(split_config_obj, f"splits.{split_name}")
        mission = _require_mapping(split_config.get("mission"), f"splits.{split_name}.mission")
        target_selection = _require_mapping(
            split_config.get("target_selection"),
            f"splits.{split_name}.target_selection",
        )
        initial_pool = _require_mapping(
            target_selection.get("initial_pool"),
            f"splits.{split_name}.target_selection.initial_pool",
        )
        satellite_model = _require_mapping(
            split_config.get("satellite_model"),
            f"splits.{split_name}.satellite_model",
        )
        seed = _require_int(split_config, "seed", f"splits.{split_name}")
        target_selection_seed_stride = _require_int(
            split_config,
            "target_selection_seed_stride",
            f"splits.{split_name}",
        )
        target_selection_seed_offset = _require_int(
            split_config,
            "target_selection_seed_offset",
            f"splits.{split_name}",
        )
        split_specs = [case_spec for case_spec in case_specs if case_spec.split == split_name]
        for index, case_spec in enumerate(split_specs):
            case_seed = seed + (index * target_selection_seed_stride)
            case_targets = select_targets(
                cities,
                case_spec.target_count,
                seed=case_seed + target_selection_seed_offset,
                min_target_separation_m=_require_float(
                    mission,
                    "min_target_separation_m",
                    f"splits.{split_name}.mission",
                ),
                initial_pool_min_size=_require_int(
                    initial_pool,
                    "min_size",
                    f"splits.{split_name}.target_selection.initial_pool",
                ),
                initial_pool_multiplier=_require_int(
                    initial_pool,
                    "multiplier",
                    f"splits.{split_name}.target_selection.initial_pool",
                ),
                max_abs_latitude_deg=(
                    _require_float(target_selection, "max_abs_latitude_deg", f"splits.{split_name}.target_selection")
                    if "max_abs_latitude_deg" in target_selection
                    else None
                ),
            )
            case_dir = cases_dir / split_name / case_spec.case_id
            _write_json(case_dir / "assets.json", build_assets_payload(case_spec, satellite_model))
            _write_json(case_dir / "mission.json", build_mission_payload(case_spec, case_targets, mission))

            if split_name == smoke_split and case_spec.case_id == smoke_case_id:
                example_solution = {"satellites": [], "actions": []}

    index_payload = build_index_payload(
        case_specs,
        split_configs=split_configs,
        example_smoke_case=example_smoke_case,
        source=source,
    )
    _write_json(output_dir / "index.json", index_payload)
    if example_solution is None:
        raise RuntimeError(f"Expected configured smoke case {example_smoke_case} for example_solution.json")
    _write_json(output_dir / "example_solution.json", example_solution)
    return output_dir
