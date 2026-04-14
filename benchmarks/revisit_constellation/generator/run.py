"""CLI entry point for the revisit_constellation generator."""

from __future__ import annotations

import argparse
from pathlib import Path

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
    world_cities_path = download_sources(
        download_dir,
        force_download=args.force_download,
    )

    generate_dataset(
        world_cities_path=world_cities_path,
        output_dir=args.output_dir,
        case_count=args.case_count,
        seed=args.seed,
    )
    print(f"Wrote revisit_constellation dataset to {args.output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
