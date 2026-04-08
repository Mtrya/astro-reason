"""CLI entry point for the regional_coverage generator."""

from __future__ import annotations

import argparse
from pathlib import Path

from .build import CANONICAL_SEED, generate_dataset


DEFAULT_DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Regional coverage generator: use vendored SAR-like TLEs and a vendored "
            "region library to emit the canonical dataset under dataset/cases/ plus "
            "index.json and example_solution.json."
        )
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=DEFAULT_DATASET_DIR,
        help="Where to write the canonical dataset (default: <benchmark>/dataset)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=CANONICAL_SEED,
        help=f"Deterministic dataset seed (default: {CANONICAL_SEED})",
    )
    args = parser.parse_args(argv)

    generate_dataset(output_dir=args.dataset_dir, seed=args.seed)
    print(f"Wrote regional_coverage dataset to {args.dataset_dir.resolve()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
