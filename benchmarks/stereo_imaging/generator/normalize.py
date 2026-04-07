"""Normalization helpers for cached stereo_imaging source data."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# World cities CSV: canonical column names after normalization
WORLD_CITIES_CANONICAL_FIELDS = (
    "name",
    "country",
    "latitude_deg",
    "longitude_deg",
    "population",
)

WORLD_CITIES_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "city", "city_ascii", "city_name"),
    "country": ("country", "country_name"),
    "latitude_deg": ("latitude_deg", "latitude", "lat"),
    "longitude_deg": ("longitude_deg", "longitude", "lon", "lng"),
    "population": ("population", "population_proper", "population_total"),
}

WORLD_CITIES_REQUIRED_COLUMNS = {
    key: WORLD_CITIES_COLUMN_ALIASES[key]
    for key in ("name", "country", "latitude_deg", "longitude_deg", "population")
}


def _normalize_header_lookup(fieldnames: list[str]) -> set[str]:
    return {field.strip().lower() for field in fieldnames}


def _resolve_column(fieldnames: list[str] | None, aliases: tuple[str, ...], context: str) -> str:
    if not fieldnames:
        raise ValueError(f"{context}: missing CSV header row")
    normalized = _normalize_header_lookup(fieldnames)
    for alias in aliases:
        if alias.lower() in normalized:
            for raw in fieldnames:
                if raw.strip().lower() == alias.lower():
                    return raw
    raise ValueError(f"{context}: could not resolve column from aliases {aliases}")


def parse_tle_text(raw: str) -> list[dict[str, Any]]:
    """Parse CelesTrak three-line TLE groups into satellite records."""
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    records: list[dict[str, Any]] = []
    i = 0
    while i + 2 < len(lines):
        name = lines[i]
        line1 = lines[i + 1]
        line2 = lines[i + 2]
        if not line1.startswith("1 ") or not line2.startswith("2 "):
            i += 1
            continue
        norad = _tle_catalog_number(line1)
        epoch_iso = tle_line1_epoch_to_iso(line1)
        records.append(
            {
                "name": name,
                "norad_catalog_id": norad,
                "tle_line1": line1,
                "tle_line2": line2,
                "epoch_iso": epoch_iso,
            }
        )
        i += 3
    return records


def _tle_catalog_number(line1: str) -> int:
    """Extract the 5-digit NORAD catalog id from TLE line 1."""
    if len(line1) < 7:
        raise ValueError("TLE line 1 too short for catalog number")
    return int(line1[2:7])


def tle_line1_epoch_to_iso(line1: str) -> str | None:
    """Convert TLE epoch field (columns 19-32, 1-based) to ISO 8601 UTC string."""
    if len(line1) < 32:
        return None
    epoch_field = line1[18:32].strip()
    if not epoch_field or "." not in epoch_field:
        return None
    yy = int(epoch_field[:2])
    day_of_year_float = float(epoch_field[2:])
    year = 2000 + yy if yy < 57 else 1900 + yy
    base = datetime(year, 1, 1, tzinfo=timezone.utc)
    dt = base + timedelta(days=day_of_year_float - 1.0)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def load_celestrak_csv(csv_path: Path) -> list[dict[str, Any]]:
    """Load normalized CelesTrak CSV written by sources.download_celestrak."""
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Missing header in {csv_path}")
        return [dict(row) for row in reader]


def load_world_cities(csv_path: Path) -> list[dict[str, Any]]:
    """Load world cities CSV and expose canonical keys (latitude_deg, longitude_deg, ...)."""
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Missing header in {csv_path}")
        name_col = _resolve_column(reader.fieldnames, WORLD_CITIES_COLUMN_ALIASES["name"], "world cities")
        country_col = _resolve_column(reader.fieldnames, WORLD_CITIES_COLUMN_ALIASES["country"], "world cities")
        lat_col = _resolve_column(reader.fieldnames, WORLD_CITIES_COLUMN_ALIASES["latitude_deg"], "world cities")
        lon_col = _resolve_column(reader.fieldnames, WORLD_CITIES_COLUMN_ALIASES["longitude_deg"], "world cities")
        pop_col = _resolve_column(reader.fieldnames, WORLD_CITIES_COLUMN_ALIASES["population"], "world cities")

        rows: list[dict[str, Any]] = []
        for row in reader:
            rows.append(
                {
                    "name": row[name_col],
                    "country": row[country_col],
                    "latitude_deg": float(row[lat_col]),
                    "longitude_deg": float(row[lon_col]),
                    "population": int(float(row[pop_col])) if row.get(pop_col) not in (None, "") else 0,
                }
            )
        return rows
