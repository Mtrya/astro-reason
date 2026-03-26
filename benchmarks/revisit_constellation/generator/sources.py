"""Source acquisition helpers for the revisit_constellation generator."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import kagglehub

from .build import CITY_COLUMN_ALIASES, STATION_COLUMN_ALIASES


WORLD_CITIES_DATASET = "juanmah/world-cities"
GROUND_STATIONS_DATASET = "pratiksharm/ground-station-dataset"
WORLD_CITIES_FILENAME = "world_cities.csv"
GROUND_STATIONS_FILENAME = "ground_stations.csv"
WORLD_CITIES_REQUIRED_COLUMNS = {
    key: CITY_COLUMN_ALIASES[key]
    for key in ("name", "country", "latitude_deg", "longitude_deg", "population")
}
GROUND_STATIONS_REQUIRED_COLUMNS = {
    key: STATION_COLUMN_ALIASES[key]
    for key in ("name", "latitude_deg", "longitude_deg")
}


def _normalize_header_lookup(fieldnames: list[str]) -> set[str]:
    return {field.strip().lower() for field in fieldnames}


def _matches_alias_groups(csv_path: Path, alias_groups: dict[str, tuple[str, ...]]) -> bool:
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            fieldnames = next(reader)
    except (OSError, StopIteration, UnicodeDecodeError, csv.Error):
        return False
    normalized = _normalize_header_lookup(fieldnames)
    return all(any(alias.lower() in normalized for alias in aliases) for aliases in alias_groups.values())


def _copy_matching_csv(
    *,
    source_root: Path,
    alias_groups: dict[str, tuple[str, ...]],
    destination_path: Path,
) -> Path:
    csv_candidates = sorted(path for path in source_root.rglob("*.csv") if path.is_file())
    for candidate in csv_candidates:
        if _matches_alias_groups(candidate, alias_groups):
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, destination_path)
            return destination_path
    raise FileNotFoundError(
        f"No CSV in {source_root} matched the required schema for {destination_path.name}"
    )


def _download_dataset(dataset: str, destination_dir: Path, *, force_download: bool) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    resolved_path = kagglehub.dataset_download(
        dataset,
        force_download=force_download,
        output_dir=str(destination_dir),
    )
    return Path(resolved_path)


def download_sources(
    destination_dir: Path,
    *,
    force_download: bool = False,
) -> tuple[Path, Path]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    world_root = _download_dataset(
        WORLD_CITIES_DATASET,
        destination_dir / "world_cities_raw",
        force_download=force_download,
    )
    station_root = _download_dataset(
        GROUND_STATIONS_DATASET,
        destination_dir / "ground_stations_raw",
        force_download=force_download,
    )
    final_world_csv = _copy_matching_csv(
        source_root=world_root,
        alias_groups=WORLD_CITIES_REQUIRED_COLUMNS,
        destination_path=destination_dir / WORLD_CITIES_FILENAME,
    )
    final_station_csv = _copy_matching_csv(
        source_root=station_root,
        alias_groups=GROUND_STATIONS_REQUIRED_COLUMNS,
        destination_path=destination_dir / GROUND_STATIONS_FILENAME,
    )
    return final_world_csv, final_station_csv
