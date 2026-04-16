"""Source acquisition helpers for the aeossp_standard generator."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
import urllib.request

from . import cached_tles


CELESTRAK_EARTH_RESOURCES_URL = (
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=resource&FORMAT=tle"
)
CELESTRAK_SNAPSHOT_EPOCH_UTC = "2026-04-14T00:00:00Z"
CELESTRAK_CSV_NAME = "earth_resources.csv"
LEGACY_CELESTRAK_RAW_NAME = "earth_resources_raw.tle"

WORLD_CITIES_URL = "https://download.geonames.org/export/dump/cities15000.zip"
WORLD_CITIES_FILENAME = "world_cities.csv"
WORLD_CITIES_SNAPSHOT_NAME = "world_cities_snapshot.csv"

NATURAL_EARTH_LAND_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson"
)
NATURAL_EARTH_LAND_FILENAME = "ne_110m_land.geojson"

_GENERATOR_DIR = Path(__file__).resolve().parent
VENDORED_WORLD_CITIES_PATH = _GENERATOR_DIR / WORLD_CITIES_SNAPSHOT_NAME


@dataclass(frozen=True)
class SourceFetchResult:
    kind: str
    paths: list[Path]
    extra: dict[str, object]


def _sha256_file(path: Path, *, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _download_bytes(url: str, destination_path: Path) -> Path:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
        payload = response.read()
    destination_path.write_bytes(payload)
    return destination_path


def download_celestrak(dest_dir: Path, *, force_download: bool) -> SourceFetchResult:
    del force_download  # Vendored snapshot is always used for reproducibility.

    cele_dir = dest_dir / "celestrak"
    csv_path = cele_dir / CELESTRAK_CSV_NAME
    legacy_raw_path = cele_dir / LEGACY_CELESTRAK_RAW_NAME
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if legacy_raw_path.exists():
        legacy_raw_path.unlink()
    rows = list(cached_tles.CACHED_CELESTRAK_ROWS)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "name",
                "norad_catalog_id",
                "tle_line1",
                "tle_line2",
                "epoch_iso",
                "inclination_deg",
                "eccentricity",
                "mean_motion_rev_per_day",
                "altitude_m",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    csv_bytes = csv_path.read_bytes()
    return SourceFetchResult(
        "celestrak",
        [csv_path],
        {
            "url": CELESTRAK_EARTH_RESOURCES_URL,
            "snapshot_epoch_utc": CELESTRAK_SNAPSHOT_EPOCH_UTC,
            "record_count": len(rows),
            "sha256": hashlib.sha256(csv_bytes).hexdigest(),
            "vendored_snapshot": True,
        },
    )


def download_world_cities(dest_dir: Path, *, force_download: bool) -> SourceFetchResult:
    del force_download  # Vendored snapshot is always used for reproducibility.

    if not VENDORED_WORLD_CITIES_PATH.is_file():
        raise FileNotFoundError(
            f"Vendored world-cities snapshot is missing: {VENDORED_WORLD_CITIES_PATH}"
        )

    cities_dir = dest_dir / "world_cities"
    final_csv = cities_dir / WORLD_CITIES_FILENAME
    cities_dir.mkdir(parents=True, exist_ok=True)
    final_csv.write_bytes(VENDORED_WORLD_CITIES_PATH.read_bytes())
    return SourceFetchResult(
        "world_cities",
        [final_csv],
        {
            "url": WORLD_CITIES_URL,
            "sha256": _sha256_file(final_csv),
            "vendored_snapshot": True,
        },
    )


def download_natural_earth_land(dest_dir: Path, *, force_download: bool) -> SourceFetchResult:
    land_dir = dest_dir / "natural_earth"
    geojson_path = land_dir / NATURAL_EARTH_LAND_FILENAME
    if not force_download and geojson_path.is_file():
        return SourceFetchResult(
            "natural_earth_land",
            [geojson_path],
            {
                "url": NATURAL_EARTH_LAND_URL,
                "sha256": _sha256_file(geojson_path),
            },
        )
    _download_bytes(NATURAL_EARTH_LAND_URL, geojson_path)
    # Validate that the file is at least parseable GeoJSON before returning.
    json.loads(geojson_path.read_text(encoding="utf-8"))
    return SourceFetchResult(
        "natural_earth_land",
        [geojson_path],
        {
            "url": NATURAL_EARTH_LAND_URL,
            "sha256": _sha256_file(geojson_path),
        },
    )


def fetch_all_sources(dest_dir: Path, *, force_download: bool = False) -> dict[str, SourceFetchResult]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    return {
        "celestrak": download_celestrak(dest_dir, force_download=force_download),
        "world_cities": download_world_cities(dest_dir, force_download=force_download),
        "natural_earth_land": download_natural_earth_land(dest_dir, force_download=force_download),
    }
