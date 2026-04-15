"""Source acquisition helpers for the aeossp_standard generator."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
import io
from pathlib import Path
import urllib.request
import zipfile

from . import cached_tles
from .normalize import parse_tle_text


CELESTRAK_EARTH_RESOURCES_URL = (
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=resource&FORMAT=tle"
)
CELESTRAK_SNAPSHOT_EPOCH_UTC = "2026-04-14T00:00:00Z"
CELESTRAK_RAW_NAME = "earth_resources_raw.tle"
CELESTRAK_CSV_NAME = "earth_resources.csv"

WORLD_CITIES_URL = "https://download.geonames.org/export/dump/cities15000.zip"
WORLD_CITIES_FILENAME = "world_cities.csv"

NATURAL_EARTH_LAND_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson"
)
NATURAL_EARTH_LAND_FILENAME = "ne_110m_land.geojson"


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
    raw_path = cele_dir / CELESTRAK_RAW_NAME
    csv_path = cele_dir / CELESTRAK_CSV_NAME
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(cached_tles.CACHED_CELESTRAK_ROWS)
    raw_lines: list[str] = []
    for row in rows:
        raw_lines.extend([row["name"], row["tle_line1"], row["tle_line2"]])
    raw_text = "\n".join(raw_lines) + "\n"
    records = parse_tle_text(raw_text)
    if len(records) != len(rows):
        raise RuntimeError(
            f"Vendored TLE snapshot parse mismatch: expected {len(rows)} satellites, got {len(records)}"
        )
    raw_bytes = raw_text.encode("utf-8")
    raw_path.write_bytes(raw_bytes)

    csv_buffer = io.StringIO()
    writer = csv.DictWriter(
        csv_buffer,
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
    csv_bytes = csv_buffer.getvalue().encode("utf-8")
    csv_path.write_bytes(csv_bytes)
    return SourceFetchResult(
        "celestrak",
        [raw_path, csv_path],
        {
            "url": CELESTRAK_EARTH_RESOURCES_URL,
            "snapshot_epoch_utc": CELESTRAK_SNAPSHOT_EPOCH_UTC,
            "record_count": len(rows),
            "sha256": hashlib.sha256(csv_bytes).hexdigest(),
            "vendored_snapshot": True,
        },
    )


def download_world_cities(dest_dir: Path, *, force_download: bool) -> SourceFetchResult:
    cities_dir = dest_dir / "world_cities"
    final_csv = cities_dir / WORLD_CITIES_FILENAME
    raw_zip = cities_dir / "cities15000.zip"

    if not force_download and final_csv.is_file():
        return SourceFetchResult(
            "world_cities",
            [final_csv],
            {
                "url": WORLD_CITIES_URL,
                "sha256": _sha256_file(final_csv),
            },
        )

    cities_dir.mkdir(parents=True, exist_ok=True)
    _download_bytes(WORLD_CITIES_URL, raw_zip)
    with zipfile.ZipFile(raw_zip) as archive:
        member = next((name for name in archive.namelist() if name.endswith(".txt")), None)
        if member is None:
            raise FileNotFoundError("Geonames cities archive did not contain a text dump")
        raw_text = archive.read(member).decode("utf-8")

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["name", "country", "latitude_deg", "longitude_deg", "population"])
    for line in raw_text.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 15:
            continue
        name = fields[1].strip()
        country_code = fields[8].strip() or "UNK"
        latitude_deg = fields[4].strip()
        longitude_deg = fields[5].strip()
        population = fields[14].strip() or "0"
        if not name:
            continue
        writer.writerow([name, country_code, latitude_deg, longitude_deg, population])
    final_csv.write_text(output.getvalue(), encoding="utf-8")
    return SourceFetchResult(
        "world_cities",
        [final_csv],
        {
            "url": WORLD_CITIES_URL,
            "sha256": _sha256_file(final_csv),
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
