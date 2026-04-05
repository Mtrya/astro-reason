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

STATION_COLUMN_ALIASES = {
    "id": ("id", "station_id", "facility_id"),
    "name": ("name", "station_name", "facility_name"),
    "network_name": ("network_name", "network", "operator", "organization"),
    "latitude_deg": ("latitude_deg", "latitude", "lat"),
    "longitude_deg": ("longitude_deg", "longitude", "lon", "lng"),
    "altitude_m": ("altitude_m", "altitude", "elevation_m"),
}

SATELLITE_MODEL = {
    "model_name": "balanced_leo_eo_bus_v1",
    "sensor": {
        "max_off_nadir_angle_deg": 25.0,
        "max_range_m": 1_000_000.0,
        "obs_discharge_rate_w": 120.0,
        "obs_store_rate_mb_per_s": 20.0,
    },
    "terminal": {
        "downlink_release_rate_mb_per_s": 40.0,
        "downlink_discharge_rate_w": 80.0,
    },
    "resource_model": {
        "battery_capacity_wh": 2_000.0,
        "storage_capacity_mb": 20_000.0,
        "initial_battery_wh": 1_600.0,
        "initial_storage_mb": 1_000.0,
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
class StationRecord:
    station_id: str
    name: str
    network_name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    target_count: int
    station_count: int
    max_num_satellites: int
    revisit_threshold_hours: float


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


def _station_key(station: StationRecord) -> tuple[str, float, float]:
    return (_slugify(station.name), round(station.latitude_deg, 3), round(station.longitude_deg, 3))


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


def load_station_rows(csv_path: Path) -> list[StationRecord]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{csv_path} must contain a CSV header row")
        id_col = _resolve_optional_column(reader.fieldnames, STATION_COLUMN_ALIASES["id"])
        name_col = _resolve_column(reader.fieldnames, STATION_COLUMN_ALIASES["name"], "station CSV")
        network_col = _resolve_optional_column(
            reader.fieldnames, STATION_COLUMN_ALIASES["network_name"]
        )
        lat_col = _resolve_column(
            reader.fieldnames, STATION_COLUMN_ALIASES["latitude_deg"], "station CSV"
        )
        lon_col = _resolve_column(
            reader.fieldnames, STATION_COLUMN_ALIASES["longitude_deg"], "station CSV"
        )
        altitude_col = _resolve_optional_column(
            reader.fieldnames, STATION_COLUMN_ALIASES["altitude_m"]
        )

        unique_rows: dict[tuple[str, float, float], StationRecord] = {}
        for row in reader:
            try:
                name = str(row[name_col]).strip()
                station_id = (
                    str(row[id_col]).strip() if id_col is not None and row.get(id_col) else _slugify(name)
                )
                station = StationRecord(
                    station_id=station_id,
                    name=name,
                    network_name=(
                        str(row[network_col]).strip()
                        if network_col is not None and row.get(network_col)
                        else "unknown"
                    ),
                    latitude_deg=_coerce_float(row.get(lat_col)),
                    longitude_deg=_coerce_float(row.get(lon_col)),
                    altitude_m=_coerce_float(
                        row.get(altitude_col) if altitude_col is not None else None,
                        default=0.0,
                    ),
                )
            except ValueError:
                continue
            if not station.station_id or not station.name:
                continue
            key = _station_key(station)
            if key not in unique_rows:
                unique_rows[key] = station
    stations = sorted(unique_rows.values(), key=lambda station: station.station_id)
    if not stations:
        raise ValueError(f"No usable ground-station rows found in {csv_path}")
    return stations


def build_case_specs(case_count: int) -> list[CaseSpec]:
    if case_count <= 0:
        raise ValueError("--case-count must be positive")

    base_specs = [
        CaseSpec("case_0001", 8, 3, 4, 12.0),
        CaseSpec("case_0002", 12, 4, 5, 10.0),
        CaseSpec("case_0003", 16, 4, 8, 8.0),
        CaseSpec("case_0004", 20, 5, 12, 6.0),
        CaseSpec("case_0005", 24, 6, 16, 6.0),
    ]
    if case_count <= len(base_specs):
        return base_specs[:case_count]

    specs = list(base_specs)
    while len(specs) < case_count:
        previous = specs[-1]
        next_index = len(specs) + 1
        specs.append(
            CaseSpec(
                case_id=f"case_{next_index:04d}",
                target_count=previous.target_count + 4,
                station_count=min(previous.station_count + (1 if next_index % 2 == 0 else 0), 8),
                max_num_satellites=previous.max_num_satellites + 2,
                revisit_threshold_hours=6.0,
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


def select_stations(
    stations: list[StationRecord],
    count: int,
    *,
    seed: int,
) -> list[StationRecord]:
    if count > len(stations):
        raise ValueError(
            f"Requested {count} ground stations, but only {len(stations)} stations are available"
        )

    start_index = _select_initial_index(len(stations), seed)
    selected = [stations[start_index]]
    remaining = [station for index, station in enumerate(stations) if index != start_index]

    while len(selected) < count:
        best_station: StationRecord | None = None
        best_distance = -1.0
        for station in remaining:
            min_distance = min(
                _haversine_distance_m(
                    station.latitude_deg,
                    station.longitude_deg,
                    existing.latitude_deg,
                    existing.longitude_deg,
                )
                for existing in selected
            )
            if min_distance > best_distance:
                best_distance = min_distance
                best_station = station
        assert best_station is not None
        selected.append(best_station)
        remaining.remove(best_station)
    return sorted(selected, key=lambda station: station.station_id)


def build_assets_payload(case_spec: CaseSpec, stations: list[StationRecord]) -> dict:
    return {
        "satellite_model": SATELLITE_MODEL,
        "max_num_satellites": case_spec.max_num_satellites,
        "ground_stations": [
            {
                "id": station.station_id,
                "name": station.name,
                "latitude_deg": station.latitude_deg,
                "longitude_deg": station.longitude_deg,
                "altitude_m": station.altitude_m,
                "min_elevation_deg": 10.0,
                "min_duration_sec": 120.0,
            }
            for station in stations
        ],
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


def build_dataset_readme(index_payload: dict) -> str:
    source = index_payload["source"]
    return f"""# Revisit Constellation Dataset

This directory contains the canonical committed dataset for the
`revisit_constellation` benchmark.

## Layout

- `index.json`
- `example_solution.json`
- `cases/<case_id>/assets.json`
- `cases/<case_id>/mission.json`

Each case directory contains only the two canonical machine-readable files used
by the verifier. `example_solution.json` maps case IDs to minimal runnable
examples for verifier smoke tests; these are not baselines.

## Canonical Generation

This committed dataset is intended to be rebuilt with:

```bash
uv run python benchmarks/revisit_constellation/generator/run.py
```

The generator downloads the documented source datasets automatically via
`kagglehub`, stores the raw source data under `dataset/source_data/` by
default, and then rebuilds the canonical cases.

Source datasets:

- world cities: `{source["world_cities"]["dataset"]}`
- ground stations: `{source["ground_stations"]["dataset"]}`
"""


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
            "ground_stations": {
                "kind": "kaggle_dataset",
                "dataset": "pratiksharm/ground-station-dataset",
                "page_url": "https://www.kaggle.com/datasets/pratiksharm/ground-station-dataset",
            },
        },
        "cases": [
            {
                "case_id": case_spec.case_id,
                "path": f"cases/{case_spec.case_id}",
                "target_count": case_spec.target_count,
                "ground_station_count": case_spec.station_count,
                "max_num_satellites": case_spec.max_num_satellites,
                "uniform_revisit_threshold_hours": case_spec.revisit_threshold_hours,
            }
            for case_spec in case_specs
        ],
    }


def generate_dataset(
    *,
    world_cities_path: Path,
    ground_stations_path: Path,
    output_dir: Path,
    case_count: int,
    seed: int,
) -> Path:
    cities = load_city_rows(world_cities_path)
    stations = load_station_rows(ground_stations_path)
    case_specs = build_case_specs(case_count)

    cases_dir = output_dir / "cases"
    shutil.rmtree(cases_dir, ignore_errors=True)
    cases_dir.mkdir(parents=True, exist_ok=True)

    example_solution: dict[str, dict] = {}

    for index, case_spec in enumerate(case_specs):
        case_seed = seed + (index * 10_000)
        case_targets = select_targets(cities, case_spec.target_count, seed=case_seed + 1)
        case_stations = select_stations(stations, case_spec.station_count, seed=case_seed + 2)
        case_dir = cases_dir / case_spec.case_id
        _write_json(case_dir / "assets.json", build_assets_payload(case_spec, case_stations))
        _write_json(case_dir / "mission.json", build_mission_payload(case_spec, case_targets))

        if case_spec.case_id == "case_0001":
            example_solution[case_spec.case_id] = {"satellites": [], "actions": []}

    index_payload = build_index_payload(case_specs, seed=seed)
    _write_json(output_dir / "index.json", index_payload)
    _write_json(output_dir / "example_solution.json", example_solution)
    _write_text(output_dir / "README.md", build_dataset_readme(index_payload))
    return output_dir
