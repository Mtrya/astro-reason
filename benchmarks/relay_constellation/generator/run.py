"""CLI entry point for the relay_constellation generator."""

from __future__ import annotations

import argparse
from pathlib import Path

from .build import DEFAULT_DATASET_DIR, generate_dataset, load_generator_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the canonical relay_constellation dataset under dataset/cases/<split>/ "
            "plus dataset/index.json."
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
    summaries = generate_dataset(
        output_dir=args.output_dir,
        split_configs=config["splits"],
        example_smoke_case=config["example_smoke_case"],
    )
    print(f"Wrote relay_constellation dataset to {args.output_dir.resolve()}")
    for summary in summaries:
        backbone = summary["backbone"]
        print(
            f"{summary['split']}/{summary['case_id']}: backbone={summary['num_backbone_satellites']}, "
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
