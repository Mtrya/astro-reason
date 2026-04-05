"""CLI entry point for the revisit_constellation generator."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
import types


def _load_runtime_modules():
    package_name = "_revisit_constellation_generator_runtime"
    package_dir = Path(__file__).resolve().parent

    package = sys.modules.get(package_name)
    if package is None:
        package = types.ModuleType(package_name)
        package.__path__ = [str(package_dir)]
        sys.modules[package_name] = package

    loaded = {}
    for module_name in ("build", "sources"):
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
            sys.modules[qualified_name] = module
            spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded["build"], loaded["sources"]


if __package__ in {None, ""}:  # pragma: no cover - script-path import support
    _build_module, _sources_module = _load_runtime_modules()
    generate_dataset = _build_module.generate_dataset
    download_sources = _sources_module.download_sources
else:  # pragma: no cover - exercised through the same runtime path
    from .build import generate_dataset
    from .sources import download_sources


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "dataset"
DEFAULT_CASE_COUNT = 5
DEFAULT_SEED = 42


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the canonical revisit_constellation dataset"
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        help=(
            "Where downloaded source CSVs and raw dataset contents should be stored; "
            "defaults to <output-dir>/source_data"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where the canonical dataset should be written",
    )
    parser.add_argument(
        "--case-count",
        type=int,
        default=DEFAULT_CASE_COUNT,
        help="How many cases to generate",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Deterministic seed for all sampling",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Force kagglehub to re-download the source datasets",
    )
    args = parser.parse_args(argv)

    download_dir = args.download_dir or (args.output_dir / "source_data")
    world_cities_path, ground_stations_path = download_sources(
        download_dir,
        force_download=args.force_download,
    )

    generate_dataset(
        world_cities_path=world_cities_path,
        ground_stations_path=ground_stations_path,
        output_dir=args.output_dir,
        case_count=args.case_count,
        seed=args.seed,
    )
    print(f"Wrote revisit_constellation dataset to {args.output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
