"""CLI entry point for the regional_coverage generator."""

from __future__ import annotations

import argparse
from pathlib import Path

from .build import generate_dataset, load_generator_config


DEFAULT_DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Regional coverage generator: use vendored SAR-like TLEs and a vendored "
            "region library to emit the canonical dataset under dataset/cases/<split>/ plus "
            "index.json and example_solution.json."
        )
    )
    parser.add_argument(
        "splits_path",
        type=Path,
        help="Path to the benchmark-local splits.yaml describing canonical split generation",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DATASET_DIR,
        help="Where to write the canonical dataset (default: <benchmark>/dataset)",
    )
    args = parser.parse_args(argv)

    config = load_generator_config(args.splits_path)
    generate_dataset(
        output_dir=args.output_dir,
        split_configs=config["splits"],
        example_smoke_case=config["example_smoke_case"],
        source_config=config["source"],
    )
    print(f"Wrote regional_coverage dataset to {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
