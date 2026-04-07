"""Reproducible download and staging for stereo_imaging v3 source data."""

from __future__ import annotations

import csv
import hashlib
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import kagglehub

from .normalize import WORLD_CITIES_REQUIRED_COLUMNS, parse_tle_text

CELESTRAK_EARTH_RESOURCES_URL = (
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=resource&FORMAT=tle"
)
CELESTRAK_RAW_NAME = "earth_resources_raw.tle"
CELESTRAK_CSV_NAME = "earth_resources.csv"

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
                "sha256": _sha256_file(csv_path),
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
            "sha256": _sha256_file(csv_path),
            "skipped_cached": False,
        },
    )


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
                "sha256": _sha256_file(final_csv),
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
            "sha256": _sha256_file(copied),
            "skipped_cached": False,
        },
    )


def fetch_all_sources(
    dest_dir: Path,
    *,
    force_download: bool = False,
) -> dict[str, SourceFetchResult]:
    """Download the runtime source inputs needed by the lookup-table-based generator."""
    return {
        "celestrak": download_celestrak(dest_dir, force_download=force_download),
        "world_cities": download_world_cities(dest_dir, force_download=force_download),
    }
