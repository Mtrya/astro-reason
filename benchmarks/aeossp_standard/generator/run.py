"""CLI entry point for the aeossp_standard generator."""

from __future__ import annotations

import argparse
from pathlib import Path

from .build import generate_dataset, load_generator_config
from .sources import fetch_all_sources


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "dataset"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the canonical aeossp_standard dataset"
    )
    parser.add_argument(
        "splits_path",
        type=Path,
        help="Path to the benchmark-local splits.yaml describing canonical split generation",
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        help="Where downloaded/normalized source data should be stored; defaults to <output-dir>/source_data",
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
        help="Re-download source data even when normalized cached files already exist",
    )
    args = parser.parse_args(argv)

    config = load_generator_config(args.splits_path)
    output_dir = args.output_dir.resolve()
    download_dir = (args.download_dir or (output_dir / "source_data")).resolve()

    source_fetch_results = fetch_all_sources(download_dir, force_download=args.force_download)
    generate_dataset(
        source_dir=download_dir,
        output_dir=output_dir,
        split_configs=config["splits"],
        example_smoke_case=config["example_smoke_case"],
        source_config=config["source"],
        runtime_source_provenance={name: result.extra for name, result in source_fetch_results.items()},
    )
    print(f"Wrote aeossp_standard dataset to {output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
