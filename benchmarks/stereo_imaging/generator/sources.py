"""Reproducible download and staging for stereo_imaging v3 source data."""

from __future__ import annotations

import csv
import hashlib
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import kagglehub

from .normalize import (
    WORLD_CITIES_REQUIRED_COLUMNS,
    parse_tle_text,
    worldcover_tile_filename,
)

CELESTRAK_EARTH_RESOURCES_URL = (
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=resource&FORMAT=tle"
)
CELESTRAK_RAW_NAME = "earth_resources_raw.tle"
CELESTRAK_CSV_NAME = "earth_resources.csv"

# Primary: static file server (often more reliable than THREDDS fileServer).
# Fallback: THREDDS path from NOAA documentation.
ETOPO_2022_60S_URLS = (
    "https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/60s/"
    "60s_surface_elev_gtif/ETOPO_2022_v1_60s_N90W180_surface.tif",
    "https://www.ngdc.noaa.gov/thredds/fileServer/global/ETOPO2022/60s/"
    "60s_surface_elevation_geotiff/ETOPO_2022_v1_60s_N90W180_surface.tif",
)
ETOPO_LOCAL_FILENAME = "ETOPO_2022_v1_60s_N90W180_surface.tif"

WORLDCOVER_S3_BASE = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
)

WORLD_CITIES_DATASET = "juanmah/world-cities"
WORLD_CITIES_FILENAME = "world_cities.csv"

USER_AGENT = "AstroReason-Bench-stereo-imaging-generator/1.0"


def _http_get_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP error fetching {url}: {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error fetching {url}: {exc}") from exc


def download_url_to_file(
    url: str,
    dest: Path,
    *,
    chunk_size: int = 1 << 20,
    retries: int = 5,
) -> None:
    """Stream a URL to disk (for large binaries such as GeoTIFF)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:  # noqa: S310
                with dest.open("wb") as handle:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        handle.write(chunk)
            return
        except urllib.error.HTTPError as exc:
            if attempt < retries - 1 and exc.code in {502, 503, 504}:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"HTTP error fetching {url}: {exc.code} {exc.reason}") from exc
        except urllib.error.URLError as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Network error fetching {url}: {exc}") from exc


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


def _sha256_file(path: Path, *, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class SourceFetchResult:
    """Paths and metadata returned by individual fetch steps."""

    kind: str
    paths: list[Path]
    extra: dict[str, Any]


def download_celestrak(dest_dir: Path, *, force_download: bool) -> SourceFetchResult:
    """Download Earth-resources TLEs from CelesTrak and write normalized CSV."""
    cele_dir = dest_dir / "celestrak"
    raw_path = cele_dir / CELESTRAK_RAW_NAME
    csv_path = cele_dir / CELESTRAK_CSV_NAME

    if not force_download and csv_path.is_file() and raw_path.is_file():
        records = parse_tle_text(raw_path.read_text(encoding="utf-8", errors="replace"))
        return SourceFetchResult(
            "celestrak",
            [raw_path, csv_path],
            {
                "url": CELESTRAK_EARTH_RESOURCES_URL,
                "record_count": len(records),
                "skipped_cached": True,
            },
        )

    raw_bytes = _http_get_bytes(CELESTRAK_EARTH_RESOURCES_URL)
    text = raw_bytes.decode("utf-8", errors="replace")
    cele_dir.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(text, encoding="utf-8")

    records = parse_tle_text(text)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["name", "norad_catalog_id", "tle_line1", "tle_line2", "epoch_iso"],
        )
        writer.writeheader()
        for row in records:
            writer.writerow(row)

    return SourceFetchResult(
        "celestrak",
        [raw_path, csv_path],
        {
            "url": CELESTRAK_EARTH_RESOURCES_URL,
            "record_count": len(records),
            "skipped_cached": False,
        },
    )


def download_etopo(dest_dir: Path, *, force_download: bool) -> SourceFetchResult:
    """Download ETOPO 2022 60 arc-second global surface GeoTIFF."""
    etopo_dir = dest_dir / "etopo"
    tif_path = etopo_dir / ETOPO_LOCAL_FILENAME

    if not force_download and tif_path.is_file():
        return SourceFetchResult(
            "etopo",
            [tif_path],
            {
                "product_id": "ETOPO_2022_v1_60s_N90W180_surface",
                "url": ETOPO_2022_60S_URLS[0],
                "urls_tried": list(ETOPO_2022_60S_URLS),
                "sha256": _sha256_file(tif_path),
                "skipped_cached": True,
            },
        )

    etopo_dir.mkdir(parents=True, exist_ok=True)
    last_err: RuntimeError | None = None
    for attempt_url in ETOPO_2022_60S_URLS:
        try:
            download_url_to_file(attempt_url, tif_path)
            return SourceFetchResult(
                "etopo",
                [tif_path],
                {
                    "product_id": "ETOPO_2022_v1_60s_N90W180_surface",
                    "url": attempt_url,
                    "urls_tried": list(ETOPO_2022_60S_URLS),
                    "sha256": _sha256_file(tif_path),
                    "skipped_cached": False,
                },
            )
        except RuntimeError as exc:
            last_err = exc
            if tif_path.is_file():
                tif_path.unlink(missing_ok=True)
            continue
    raise RuntimeError(
        f"ETOPO download failed after trying {len(ETOPO_2022_60S_URLS)} URLs"
    ) from last_err


def worldcover_tile_url(lat: float, lon: float) -> str:
    """HTTPS URL for the WorldCover v200 map tile covering (lat, lon)."""
    fname = worldcover_tile_filename(lat, lon)
    return f"{WORLDCOVER_S3_BASE}/{fname}"


def fetch_worldcover_tile(
    dest_dir: Path,
    lat: float,
    lon: float,
    *,
    force_download: bool = False,
) -> Path:
    """Download the WorldCover 10 m classification tile covering (lat, lon)."""
    wc_dir = dest_dir / "worldcover"
    fname = worldcover_tile_filename(lat, lon)
    out_path = wc_dir / fname
    url = worldcover_tile_url(lat, lon)

    if not force_download and out_path.is_file():
        return out_path

    wc_dir.mkdir(parents=True, exist_ok=True)
    download_url_to_file(url, out_path)
    return out_path


# Fixed demo locations (lat, lon) to validate WorldCover fetch without Phase 1.B sampling.
WORLDCOVER_DEMO_POINTS: tuple[tuple[float, float], ...] = (
    (48.8566, 2.3522),  # Paris -> N48E000
    (37.7749, -122.4194),  # San Francisco -> N36W123
    (35.6762, 139.6503),  # Tokyo -> N33E138
    (-33.8688, 151.2093),  # Sydney -> S33E150
)


def fetch_worldcover_demo_tiles(
    dest_dir: Path,
    *,
    force_download: bool = False,
) -> list[Path]:
    """Fetch a small fixed set of WorldCover tiles for pipeline smoke checks."""
    paths: list[Path] = []
    for lat, lon in WORLDCOVER_DEMO_POINTS:
        paths.append(fetch_worldcover_tile(dest_dir, lat, lon, force_download=force_download))
    return paths


def download_world_cities(dest_dir: Path, *, force_download: bool) -> SourceFetchResult:
    """Download and normalize the juanmah/world-cities Kaggle dataset."""
    cities_dir = dest_dir / "world_cities"
    final_csv = cities_dir / WORLD_CITIES_FILENAME

    if not force_download and final_csv.is_file():
        return SourceFetchResult(
            "world_cities",
            [final_csv],
            {
                "kaggle_dataset": WORLD_CITIES_DATASET,
                "skipped_cached": True,
            },
        )

    cities_dir.mkdir(parents=True, exist_ok=True)
    raw_root = Path(
        kagglehub.dataset_download(
            WORLD_CITIES_DATASET,
            force_download=force_download,
            output_dir=str(cities_dir / "world_cities_raw"),
        )
    )
    copied = _copy_matching_csv(
        source_root=raw_root,
        alias_groups=WORLD_CITIES_REQUIRED_COLUMNS,
        destination_path=final_csv,
    )
    return SourceFetchResult(
        "world_cities",
        [copied],
        {
            "kaggle_dataset": WORLD_CITIES_DATASET,
            "skipped_cached": False,
        },
    )


def fetch_all_sources(
    dest_dir: Path,
    *,
    force_download: bool = False,
    include_worldcover_demo_tiles: bool = True,
) -> dict[str, SourceFetchResult | list[Path]]:
    """Download CelesTrak, ETOPO, world cities, and optionally WorldCover demo tiles."""
    results: dict[str, SourceFetchResult | list[Path]] = {}
    results["celestrak"] = download_celestrak(dest_dir, force_download=force_download)
    results["etopo"] = download_etopo(dest_dir, force_download=force_download)
    results["world_cities"] = download_world_cities(dest_dir, force_download=force_download)
    if include_worldcover_demo_tiles:
        results["worldcover_tiles"] = fetch_worldcover_demo_tiles(
            dest_dir, force_download=force_download
        )
    return results
