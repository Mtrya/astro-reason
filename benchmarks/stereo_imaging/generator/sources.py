"""Reproducible download and staging for stereo_imaging source data."""

from __future__ import annotations

import csv
import hashlib
import io
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import kagglehub

from . import cached_tles
from .normalize import WORLD_CITIES_REQUIRED_COLUMNS, parse_tle_text

CELESTRAK_EARTH_RESOURCES_URL = (
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=resource&FORMAT=tle"
)
CELESTRAK_SNAPSHOT_EPOCH_UTC = "2026-04-06T00:00:00Z"
CELESTRAK_RAW_NAME = "earth_resources_raw.tle"
CELESTRAK_CSV_NAME = "earth_resources.csv"

WORLD_CITIES_DATASET = "juanmah/world-cities"
WORLD_CITIES_FILENAME = "world_cities.csv"


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
    """Write normalized CelesTrak-format TLE CSV from `cached_tles` (no live HTTP fetch)."""
    del force_download  # Kept for API parity with `download_world_cities`; TLEs are always vendored.

    cele_dir = dest_dir / "celestrak"
    raw_path = cele_dir / CELESTRAK_RAW_NAME
    csv_path = cele_dir / CELESTRAK_CSV_NAME
    cele_dir.mkdir(parents=True, exist_ok=True)

    rows = list(cached_tles.CACHED_CELESTRAK_ROWS)
    lines: list[str] = []
    for row in rows:
        lines.extend([row["name"], row["tle_line1"], row["tle_line2"]])
    raw_text = "\n".join(lines) + "\n"
    records = parse_tle_text(raw_text)
    if len(records) != len(rows):
        raise RuntimeError(
            f"Vendored TLE snapshot parse mismatch: expected {len(rows)} satellites, got {len(records)}"
        )
    raw_bytes = raw_text.encode("utf-8")
    raw_path.write_bytes(raw_bytes)

    csv_buf = io.StringIO()
    writer = csv.DictWriter(
        csv_buf,
        fieldnames=["name", "norad_catalog_id", "tle_line1", "tle_line2", "epoch_iso"],
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    csv_bytes = csv_buf.getvalue().encode("utf-8")
    csv_path.write_bytes(csv_bytes)
    csv_sha256 = hashlib.sha256(csv_bytes).hexdigest()

    return SourceFetchResult(
        "celestrak",
        [raw_path, csv_path],
        {
            "url": CELESTRAK_EARTH_RESOURCES_URL,
            "snapshot_epoch_utc": CELESTRAK_SNAPSHOT_EPOCH_UTC,
            "record_count": len(rows),
            "sha256": csv_sha256,
            "vendored_snapshot": True,
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
