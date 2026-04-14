"""Normalization helpers for the aeossp_standard generator."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math
from pathlib import Path


EARTH_RADIUS_M = 6_378_137.0
EARTH_MU_M3_S2 = 3.986_004_418e14

WORLD_CITIES_REQUIRED_COLUMNS = {
    "name": ("name", "city", "city_ascii", "city_name"),
    "country": ("country", "country_name"),
    "latitude_deg": ("latitude_deg", "latitude", "lat"),
    "longitude_deg": ("longitude_deg", "longitude", "lon", "lng"),
    "population": ("population", "population_proper", "population_total"),
}


@dataclass(frozen=True)
class TleRecord:
    name: str
    norad_catalog_id: int
    tle_line1: str
    tle_line2: str
    epoch_iso: str
    inclination_deg: float
    eccentricity: float
    mean_motion_rev_per_day: float
    altitude_m: float


@dataclass(frozen=True)
class CityRecord:
    name: str
    country: str
    latitude_deg: float
    longitude_deg: float
    population: float


def _normalize_header_lookup(fieldnames: list[str]) -> dict[str, str]:
    return {field.strip().lower(): field for field in fieldnames}


def _resolve_column(fieldnames: list[str], aliases: tuple[str, ...], context: str) -> str:
    lookup = _normalize_header_lookup(fieldnames)
    for alias in aliases:
        if alias.lower() in lookup:
            return lookup[alias.lower()]
    raise ValueError(f"{context} missing required column from {aliases}")


def _coerce_float(value: str | None) -> float:
    if value is None or value == "":
        raise ValueError("Missing numeric value")
    return float(value)


def _tle_epoch_to_datetime(epoch_fragment: str) -> datetime:
    year_short = int(epoch_fragment[:2])
    day_of_year = float(epoch_fragment[2:])
    year = 1900 + year_short if year_short >= 57 else 2000 + year_short
    day_integer = int(math.floor(day_of_year))
    fractional_day = day_of_year - day_integer
    start = datetime(year, 1, 1, tzinfo=UTC)
    return start + timedelta(days=day_integer - 1, seconds=fractional_day * 86400.0)


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _altitude_from_mean_motion_m(mean_motion_rev_per_day: float) -> float:
    mean_motion_rad_s = mean_motion_rev_per_day * 2.0 * math.pi / 86400.0
    semi_major_axis_m = (EARTH_MU_M3_S2 / (mean_motion_rad_s**2)) ** (1.0 / 3.0)
    return semi_major_axis_m - EARTH_RADIUS_M


def parse_tle_text(raw_text: str) -> list[TleRecord]:
    lines = [line.rstrip() for line in raw_text.splitlines() if line.strip()]
    if len(lines) % 3 != 0:
        raise ValueError("TLE text must contain name + 2 lines per object")

    records: list[TleRecord] = []
    for index in range(0, len(lines), 3):
        name = lines[index].strip()
        line1 = lines[index + 1].strip()
        line2 = lines[index + 2].strip()
        if not line1.startswith("1 ") or not line2.startswith("2 "):
            raise ValueError(f"Malformed TLE record for {name}")
        norad_catalog_id = int(line1[2:7])
        epoch_iso = _utc_iso(_tle_epoch_to_datetime(line1[18:32]))
        inclination_deg = float(line2[8:16].strip())
        eccentricity = float(f"0.{line2[26:33].strip()}")
        mean_motion_rev_per_day = float(line2[52:63].strip())
        altitude_m = _altitude_from_mean_motion_m(mean_motion_rev_per_day)
        records.append(
            TleRecord(
                name=name,
                norad_catalog_id=norad_catalog_id,
                tle_line1=line1,
                tle_line2=line2,
                epoch_iso=epoch_iso,
                inclination_deg=inclination_deg,
                eccentricity=eccentricity,
                mean_motion_rev_per_day=mean_motion_rev_per_day,
                altitude_m=altitude_m,
            )
        )
    return records


def load_celestrak_csv(csv_path: Path) -> list[TleRecord]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[TleRecord] = []
        for row in reader:
            rows.append(
                TleRecord(
                    name=str(row["name"]).strip(),
                    norad_catalog_id=int(row["norad_catalog_id"]),
                    tle_line1=str(row["tle_line1"]).strip(),
                    tle_line2=str(row["tle_line2"]).strip(),
                    epoch_iso=str(row["epoch_iso"]).strip(),
                    inclination_deg=float(row["inclination_deg"]),
                    eccentricity=float(row["eccentricity"]),
                    mean_motion_rev_per_day=float(row["mean_motion_rev_per_day"]),
                    altitude_m=float(row["altitude_m"]),
                )
            )
    if not rows:
        raise ValueError(f"No TLE rows found in {csv_path}")
    return rows


def load_world_cities(csv_path: Path) -> list[CityRecord]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{csv_path} must contain a CSV header row")
        name_col = _resolve_column(reader.fieldnames, WORLD_CITIES_REQUIRED_COLUMNS["name"], "world cities CSV")
        country_col = _resolve_column(
            reader.fieldnames,
            WORLD_CITIES_REQUIRED_COLUMNS["country"],
            "world cities CSV",
        )
        lat_col = _resolve_column(
            reader.fieldnames,
            WORLD_CITIES_REQUIRED_COLUMNS["latitude_deg"],
            "world cities CSV",
        )
        lon_col = _resolve_column(
            reader.fieldnames,
            WORLD_CITIES_REQUIRED_COLUMNS["longitude_deg"],
            "world cities CSV",
        )
        population_col = _resolve_column(
            reader.fieldnames,
            WORLD_CITIES_REQUIRED_COLUMNS["population"],
            "world cities CSV",
        )

        deduped: dict[tuple[str, str, float, float], CityRecord] = {}
        for row in reader:
            try:
                record = CityRecord(
                    name=str(row[name_col]).strip(),
                    country=str(row[country_col]).strip(),
                    latitude_deg=_coerce_float(row.get(lat_col)),
                    longitude_deg=_coerce_float(row.get(lon_col)),
                    population=_coerce_float(row.get(population_col)),
                )
            except ValueError:
                continue
            if not record.name or not record.country or record.population <= 0:
                continue
            key = (
                record.name.lower(),
                record.country.lower(),
                round(record.latitude_deg, 4),
                round(record.longitude_deg, 4),
            )
            current = deduped.get(key)
            if current is None or record.population > current.population:
                deduped[key] = record

    cities = sorted(deduped.values(), key=lambda row: (-row.population, row.name, row.country))
    if not cities:
        raise ValueError(f"No usable city rows found in {csv_path}")
    return cities

