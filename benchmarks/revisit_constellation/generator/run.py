"""CLI entry point for the revisit_constellation generator."""

from __future__ import annotations

import argparse
from pathlib import Path

from .build import generate_dataset, load_generator_config
from .sources import download_sources


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "dataset"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the canonical revisit_constellation dataset"
    )
    parser.add_argument(
        "splits_path",
        type=Path,
        help="Path to the benchmark-local splits.yaml describing canonical split generation",
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
        "--force-download",
        action="store_true",
        help="Force kagglehub to re-download the source datasets",
    )
    args = parser.parse_args(argv)

    config = load_generator_config(args.splits_path)
    download_dir = args.download_dir or (args.output_dir / "source_data")
    world_cities_path = download_sources(
        download_dir,
        force_download=args.force_download,
    )

    generate_dataset(
        world_cities_path=world_cities_path,
        output_dir=args.output_dir,
        split_configs=config["splits"],
        source=config["source"],
        example_smoke_case=config["example_smoke_case"],
    )
    print(f"Wrote revisit_constellation dataset to {args.output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
