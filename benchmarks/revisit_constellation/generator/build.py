"""Case-generation logic for the revisit_constellation benchmark."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
import shutil


EARTH_RADIUS_M = 6_371_000.0
MIN_TARGET_SEPARATION_M = 250_000.0
HORIZON_START = "2025-07-17T12:00:00Z"
HORIZON_END = "2025-07-19T12:00:00Z"

CITY_COLUMN_ALIASES = {
    "name": ("name", "city", "city_ascii", "city_name"),
    "country": ("country", "country_name"),
    "latitude_deg": ("latitude_deg", "latitude", "lat"),
    "longitude_deg": ("longitude_deg", "longitude", "lon", "lng"),
    "altitude_m": ("altitude_m", "altitude", "elevation_m"),
    "population": ("population", "population_proper", "population_total"),
}

SATELLITE_MODEL = {
    "model_name": "balanced_leo_eo_bus_v1",
    "sensor": {
        "max_off_nadir_angle_deg": 25.0,
        "max_range_m": 1_000_000.0,
        "obs_discharge_rate_w": 120.0,
    },
    "resource_model": {
        "battery_capacity_wh": 2_000.0,
        "initial_battery_wh": 1_600.0,
        "idle_discharge_rate_w": 5.0,
        "sunlight_charge_rate_w": 100.0,
    },
    "attitude_model": {
        "max_slew_velocity_deg_per_sec": 1.0,
        "max_slew_acceleration_deg_per_sec2": 0.45,
        "settling_time_sec": 10.0,
        "maneuver_discharge_rate_w": 90.0,
    },
    "min_altitude_m": 500_000.0,
    "max_altitude_m": 850_000.0,
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
    case_id: str
    target_count: int
    max_num_satellites: int
    revisit_threshold_hours: float


def _sample_case_spec(rng: random.Random) -> tuple[int, int, float]:
    """Sample case parameters from the per-case RNG (same seeding policy as stereo_imaging)."""
    target_bounds = (12, 24)
    satellite_bounds = (6, 18)

    target_count = rng.randint(*target_bounds)
    max_num_satellites = rng.randint(*satellite_bounds)

    threshold_options = (6.0, 8.0, 10.0, 12.0)
    revisit_threshold_hours = rng.choice(threshold_options)
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


def build_case_specs(case_count: int, *, seed: int) -> list[CaseSpec]:
    if case_count <= 0:
        raise ValueError("--case-count must be positive")

    specs: list[CaseSpec] = []
    for case_index in range(case_count):
        # Per-case stream depends only on `seed` and `case_index` (see stereo_imaging `generate_dataset`).
        case_rng = random.Random(seed + case_index * 10_007)
        tc, ms, thr_h = _sample_case_spec(case_rng)
        specs.append(
            CaseSpec(
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


def select_targets(cities: list[CityRecord], count: int, *, seed: int) -> list[CityRecord]:
    if count > len(cities):
        raise ValueError(f"Requested {count} targets, but only {len(cities)} cities are available")

    start_index = _select_initial_index(min(len(cities), max(10, count * 2)), seed)
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
            if min_distance < MIN_TARGET_SEPARATION_M:
                continue
            if min_distance > best_distance:
                best_distance = min_distance
                best_city = city
        if best_city is None:
            raise ValueError(
                f"Unable to select {count} cities with {MIN_TARGET_SEPARATION_M / 1000:.0f} km separation"
            )
        selected.append(best_city)
        remaining.remove(best_city)
    return sorted(selected, key=lambda city: city.name)


def build_assets_payload(case_spec: CaseSpec) -> dict:
    return {
        "satellite_model": SATELLITE_MODEL,
        "max_num_satellites": case_spec.max_num_satellites,
    }


def build_mission_payload(case_spec: CaseSpec, targets: list[CityRecord]) -> dict:
    return {
        "horizon_start": HORIZON_START,
        "horizon_end": HORIZON_END,
        "targets": [
            {
                "id": f"target_{index + 1:03d}",
                "name": f"{target.name}, {target.country}",
                "latitude_deg": target.latitude_deg,
                "longitude_deg": target.longitude_deg,
                "altitude_m": target.altitude_m,
                "expected_revisit_period_hours": case_spec.revisit_threshold_hours,
                "min_elevation_deg": 20.0,
                "max_slant_range_m": 1_800_000.0,
                "min_duration_sec": 30.0,
            }
            for index, target in enumerate(targets)
        ],
    }

def build_index_payload(case_specs: list[CaseSpec], *, seed: int) -> dict:
    return {
        "benchmark": "revisit_constellation",
        "case_dir_layout": "cases/<case_id>",
        "horizon_hours": 48,
        "generator_seed": seed,
        "source": {
            "world_cities": {
                "kind": "kaggle_dataset",
                "dataset": "juanmah/world-cities",
                "page_url": "https://www.kaggle.com/datasets/juanmah/world-cities",
            },
        },
        "cases": [
            {
                "case_id": case_spec.case_id,
                "path": f"cases/{case_spec.case_id}",
                "target_count": case_spec.target_count,
                "max_num_satellites": case_spec.max_num_satellites,
                "uniform_revisit_threshold_hours": case_spec.revisit_threshold_hours,
            }
            for case_spec in case_specs
        ],
    }


def generate_dataset(
    *,
    world_cities_path: Path,
    output_dir: Path,
    case_count: int,
    seed: int,
) -> Path:
    cities = load_city_rows(world_cities_path)
    case_specs = build_case_specs(case_count, seed=seed)

    cases_dir = output_dir / "cases"
    shutil.rmtree(cases_dir, ignore_errors=True)
    cases_dir.mkdir(parents=True, exist_ok=True)

    example_solution: dict | None = None

    for index, case_spec in enumerate(case_specs):
        case_seed = seed + (index * 10_000)
        case_targets = select_targets(cities, case_spec.target_count, seed=case_seed + 1)
        case_dir = cases_dir / case_spec.case_id
        _write_json(case_dir / "assets.json", build_assets_payload(case_spec))
        _write_json(case_dir / "mission.json", build_mission_payload(case_spec, case_targets))

        if case_spec.case_id == "case_0001":
            example_solution = {"satellites": [], "actions": []}

    index_payload = build_index_payload(case_specs, seed=seed)
    _write_json(output_dir / "index.json", index_payload)
    if example_solution is None:
        raise RuntimeError("Expected case_0001 for example_solution.json")
    _write_json(output_dir / "example_solution.json", example_solution)
    return output_dir
