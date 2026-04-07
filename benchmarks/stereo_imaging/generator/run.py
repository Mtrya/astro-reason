"""CLI entry point for the stereo_imaging generator."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from .build import (
    CANONICAL_SEED,
    bilinear_elevation_m,
    generate_dataset,
    lookup_scene_type,
    lookup_table_metadata,
)
from . import sources as sources_module
from .sources import fetch_all_sources


_BENCHMARK_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOWNLOAD_DIR = _BENCHMARK_ROOT / "dataset" / "source_data"
DEFAULT_DATASET_DIR = _BENCHMARK_ROOT / "dataset"


def _git_revision(repo_root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _write_provenance(
    dest_dir: Path,
    results: dict[str, Any],
    *,
    repo_root: Path,
) -> Path:
    prov_path = dest_dir / "provenance.json"
    cele = results["celestrak"]
    cities = results["world_cities"]

    doc: dict[str, Any] = {
        "celestrak": {
            "url": sources_module.CELESTRAK_EARTH_RESOURCES_URL,
            "record_count": cele.extra.get("record_count"),
            "sha256": cele.extra.get("sha256"),
            "vendored_snapshot": cele.extra.get("vendored_snapshot"),
        },
        "world_cities": {
            "kaggle_dataset": sources_module.WORLD_CITIES_DATASET,
            "sha256": cities.extra.get("sha256"),
        },
        "lookup_tables": lookup_table_metadata(),
    }

    prov_path.parent.mkdir(parents=True, exist_ok=True)
    prov_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return prov_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stereo imaging v3 generator: stage runtime sources (vendored CelesTrak-format TLEs; "
            "Kaggle world-cities when needed), then emit the canonical dataset "
            "(dataset/cases/, index.json, example_solution.json)."
        )
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=DEFAULT_DOWNLOAD_DIR,
        help="Where to store runtime source_data (default: <benchmark>/dataset/source_data)",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help=(
            "Where to write cases, index.json, example_solution.json "
            f"(default: {DEFAULT_DATASET_DIR})"
        ),
    )
    parser.add_argument(
        "--sources-only",
        action="store_true",
        help="Only fetch and normalize runtime source data; skip canonical dataset emission.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=f"Canonical RNG seed for dataset generation (default: {CANONICAL_SEED})",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download runtime sources even when cached files exist",
    )
    args = parser.parse_args(argv)

    dest_dir = args.download_dir.resolve()
    dataset_dir = (args.dataset_dir or DEFAULT_DATASET_DIR).resolve()
    repo_root = Path(__file__).resolve().parents[3]
    seed = CANONICAL_SEED if args.seed is None else args.seed
    lookup_meta = lookup_table_metadata()

    if not args.sources_only and (
        lookup_meta["elevation_cell_count"] == 0 or lookup_meta["scene_cell_count"] == 0
    ):
        print(
            "Vendored lookup tables are empty. Generate "
            "benchmarks/stereo_imaging/generator/lookup_tables.py before dataset emission."
        )
        print(f"Current lookup metadata: {lookup_meta}")
        return 1

    results = fetch_all_sources(
        dest_dir,
        force_download=args.force_download,
    )

    prov_path = _write_provenance(dest_dir, results, repo_root=repo_root)
    print(f"Wrote provenance to {prov_path}")
    print(f"Vendored lookup tables: {lookup_meta}")
    if lookup_meta["elevation_cell_count"] > 0 and lookup_meta["scene_cell_count"] > 0:
        print(f"Sample lookup elevation (Paris): {bilinear_elevation_m(48.8566, 2.3522):.2f} m")
        print(f"Sample lookup scene (Paris): {lookup_scene_type(48.8566, 2.3522)}")
    else:
        print(
            "Vendored lookup tables are empty. Generate "
            "benchmarks/stereo_imaging/generator/lookup_tables.py before dataset emission."
        )
    print(f"Stereo imaging runtime source data ready under {dest_dir}")

    if args.sources_only:
        return 0

    rev = _git_revision(repo_root)
    generate_dataset(
        source_dir=dest_dir,
        output_dir=dataset_dir,
        seed=seed,
        git_revision=rev,
    )
    print(f"Canonical v3 dataset written under {dataset_dir / 'cases'}")
    print(f"Wrote {dataset_dir / 'index.json'} and {dataset_dir / 'example_solution.json'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
