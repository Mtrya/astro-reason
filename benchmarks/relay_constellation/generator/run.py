"""CLI entry point for the relay_constellation generator."""

from __future__ import annotations

import argparse
from pathlib import Path

from .build import CANONICAL_SEED, DEFAULT_DATASET_DIR, generate_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the canonical relay_constellation dataset under dataset/cases/ "
            "plus dataset/index.json."
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

    summaries = generate_dataset(output_dir=args.dataset_dir, seed=args.seed)
    print(f"Wrote relay_constellation dataset to {args.dataset_dir.resolve()}")
    for summary in summaries:
        backbone = summary["backbone"]
        print(
            f"{summary['case_id']}: backbone={summary['num_backbone_satellites']}, "
            f"endpoints={summary['num_ground_endpoints']}, "
            f"endpoint_pairs={summary['num_endpoint_pairs']}, "
            f"demanded_windows={summary['num_demanded_windows']}, "
            f"max_added_satellites={summary['max_added_satellites']}, "
            f"meo_backbone={backbone['count']} @ {backbone['altitude_km']:.0f} km / "
            f"{backbone['inclination_deg']:.0f} deg across {backbone['num_planes']} planes"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
