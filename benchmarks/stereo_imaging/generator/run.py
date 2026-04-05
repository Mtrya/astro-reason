"""CLI entry point for the stereo_imaging generator (v3 source layer)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import rasterio


def _load_runtime_modules():
    """Support `python path/to/run.py` without package context (see revisit_constellation)."""
    package_name = "_stereo_imaging_generator_runtime"
    package_dir = Path(__file__).resolve().parent

    package = sys.modules.get(package_name)
    if package is None:
        package = types.ModuleType(package_name)
        package.__path__ = [str(package_dir)]
        sys.modules[package_name] = package

    loaded = {}
    for module_name in ("normalize", "sources"):
        qualified_name = f"{package_name}.{module_name}"
        module = sys.modules.get(qualified_name)
        if module is None:
            spec = importlib.util.spec_from_file_location(
                qualified_name,
                package_dir / f"{module_name}.py",
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"Unable to load {qualified_name}")
            module = importlib.util.module_from_spec(spec)
            module.__package__ = package_name
            sys.modules[qualified_name] = module
            spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded["normalize"], loaded["sources"]


if __package__ in {None, ""}:  # pragma: no cover - script-path import support
    _normalize_module, _sources_module = _load_runtime_modules()
    fetch_all_sources = _sources_module.fetch_all_sources
    query_etopo_elevation = _normalize_module.query_etopo_elevation
    query_worldcover_class = _normalize_module.query_worldcover_class
    sources_module = _sources_module
else:  # pragma: no cover
    from . import sources as sources_module
    from .normalize import query_etopo_elevation, query_worldcover_class
    from .sources import fetch_all_sources


DEFAULT_DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "dataset" / "source_data"


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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _verify_geotiff(path: Path) -> dict[str, Any]:
    with rasterio.open(path) as ds:
        return {
            "width": ds.width,
            "height": ds.height,
            "crs": str(ds.crs) if ds.crs else None,
            "count": ds.count,
        }


def _write_provenance(
    dest_dir: Path,
    results: dict[str, Any],
    *,
    repo_root: Path,
) -> Path:
    prov_path = dest_dir / "provenance.json"
    cele = results["celestrak"]
    etopo = results["etopo"]
    cities = results["world_cities"]
    wc_tiles: list[Path] = list(results.get("worldcover_tiles") or [])

    doc: dict[str, Any] = {
        "generated_at_utc": _utc_now_iso(),
        "generator_revision": _git_revision(repo_root),
        "celestrak": {
            "url": sources_module.CELESTRAK_EARTH_RESOURCES_URL,
            "retrieval_timestamp_utc": _utc_now_iso(),
            "record_count": cele.extra.get("record_count"),
            "skipped_cached": cele.extra.get("skipped_cached"),
        },
        "etopo_2022": {
            "product_id": etopo.extra.get("product_id"),
            "url": etopo.extra.get("url") or sources_module.ETOPO_2022_60S_URLS[0],
            "urls_tried": etopo.extra.get("urls_tried"),
            "retrieval_timestamp_utc": _utc_now_iso(),
            "local_path": str(etopo.paths[0].relative_to(dest_dir)) if etopo.paths else None,
            "sha256": etopo.extra.get("sha256"),
            "skipped_cached": etopo.extra.get("skipped_cached"),
        },
        "worldcover": {
            "product_version": "v200",
            "year": 2021,
            "base_url": sources_module.WORLDCOVER_S3_BASE,
            "demo_tile_paths": [str(p.relative_to(dest_dir)) for p in wc_tiles],
            "retrieval_timestamp_utc": _utc_now_iso(),
        },
        "world_cities": {
            "kaggle_dataset": sources_module.WORLD_CITIES_DATASET,
            "retrieval_timestamp_utc": _utc_now_iso(),
            "skipped_cached": cities.extra.get("skipped_cached"),
        },
    }

    prov_path.parent.mkdir(parents=True, exist_ok=True)
    prov_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return prov_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch and normalize v3 source data for stereo_imaging (CelesTrak, ETOPO, WorldCover, world cities)"
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=DEFAULT_DOWNLOAD_DIR,
        help="Where to store source_data (default: <benchmark>/dataset/source_data)",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download sources even when cached files exist",
    )
    parser.add_argument(
        "--skip-worldcover-demo-tiles",
        action="store_true",
        help="Do not fetch the fixed WorldCover demo tiles (smaller run)",
    )
    args = parser.parse_args(argv)

    dest_dir = args.download_dir.resolve()
    repo_root = Path(__file__).resolve().parents[3]

    results = fetch_all_sources(
        dest_dir,
        force_download=args.force_download,
        include_worldcover_demo_tiles=not args.skip_worldcover_demo_tiles,
    )

    prov_path = _write_provenance(dest_dir, results, repo_root=repo_root)
    print(f"Wrote provenance to {prov_path}")

    # Smoke verification: GeoTIFFs open and point queries succeed
    etopo_path = dest_dir / "etopo" / sources_module.ETOPO_LOCAL_FILENAME
    if etopo_path.is_file():
        meta = _verify_geotiff(etopo_path)
        print(f"ETOPO GeoTIFF ok: {meta}")
        el = query_etopo_elevation(etopo_path, 48.8566, 2.3522)
        print(f"Sample ETOPO elevation (Paris): {el:.2f} m")

    wc_dir = dest_dir / "worldcover"
    if wc_dir.is_dir() and any(wc_dir.glob("*.tif")):
        sample = query_worldcover_class(wc_dir, 48.8566, 2.3522)
        print(f"Sample WorldCover class (Paris tile): {sample}")

    print(f"Stereo imaging source data ready under {dest_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
