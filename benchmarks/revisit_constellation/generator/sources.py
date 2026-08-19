"""Source acquisition helpers for the revisit_constellation generator."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

from .build import CITY_COLUMN_ALIASES


WORLD_CITIES_DATASET = "juanmah/world-cities"
WORLD_CITIES_FILENAME = "world_cities.csv"
WORLD_CITIES_SNAPSHOT_NAME = "world_cities_snapshot.csv"
WORLD_CITIES_REQUIRED_COLUMNS = {
    key: CITY_COLUMN_ALIASES[key]
    for key in ("name", "country", "latitude_deg", "longitude_deg", "population")
}

_GENERATOR_DIR = Path(__file__).resolve().parent
VENDORED_WORLD_CITIES_PATH = _GENERATOR_DIR / WORLD_CITIES_SNAPSHOT_NAME


def _normalize_header_lookup(fieldnames: list[str]) -> set[str]:
    return {field.strip().lower() for field in fieldnames}


def _matches_alias_groups(csv_path: Path, alias_groups: dict[str, tuple[str, ...]]) -> bool:
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            fieldnames = next(reader)
            has_data_row = any(any(cell.strip() for cell in row) for row in reader)
    except (OSError, StopIteration, UnicodeDecodeError, csv.Error):
        return False
    normalized = _normalize_header_lookup(fieldnames)
    return has_data_row and all(
        any(alias.lower() in normalized for alias in aliases)
        for aliases in alias_groups.values()
    )


def download_sources(
    destination_dir: Path,
    *,
    force_download: bool = False,
) -> Path:
    """Stage the vendored world-cities snapshot into the source-data directory.

    The canonical dataset is always generated from the vendored snapshot so
    that rebuilds do not depend on live upstream downloads.
    """
    del force_download  # Vendored snapshot is always used for reproducibility.

    if not VENDORED_WORLD_CITIES_PATH.is_file():
        raise FileNotFoundError(
            f"Vendored world-cities snapshot is missing: {VENDORED_WORLD_CITIES_PATH}"
        )
    if not _matches_alias_groups(VENDORED_WORLD_CITIES_PATH, WORLD_CITIES_REQUIRED_COLUMNS):
        raise ValueError(
            f"Vendored world-cities snapshot {VENDORED_WORLD_CITIES_PATH} "
            "does not match the required schema"
        )

    destination_dir.mkdir(parents=True, exist_ok=True)
    final_world_csv = destination_dir / WORLD_CITIES_FILENAME
    shutil.copyfile(VENDORED_WORLD_CITIES_PATH, final_world_csv)
    return final_world_csv
