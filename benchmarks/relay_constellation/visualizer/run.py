"""CLI entry point for the relay_constellation visualizer."""

from __future__ import annotations

import argparse
from pathlib import Path

from .plot import (
    DEFAULT_PLOTS_DIR,
    render_connectivity_report,
    render_overview_set,
)
from .solution import render_solution_report


DEFAULT_DATASET_DIR = Path(__file__).resolve().parents[1] / "dataset"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render relay_constellation case and solution inspection plots."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    overview_parser = subparsers.add_parser(
        "overview",
        help="Render per-demand 2D overview PNGs for one case.",
    )
    overview_parser.add_argument(
        "--case-dir",
        required=True,
        help="Path to dataset/cases/<case_id>",
    )
    overview_parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for overview PNGs (default: benchmarks/relay_constellation/visualizer/plots/<case_id>/overview)",
    )
    overview_parser.add_argument(
        "--texture-path",
        type=Path,
        help="Optional local Earth texture path to use instead of auto-downloading",
    )

    connectivity_parser = subparsers.add_parser(
        "connectivity",
        help="Render the infinite-concurrency connectivity PNG for one case.",
    )
    connectivity_parser.add_argument(
        "--case-dir",
        required=True,
        help="Path to dataset/cases/<case_id>",
    )
    connectivity_parser.add_argument(
        "--out-path",
        type=Path,
        default=None,
        help="Where to write connectivity.png (default: benchmarks/relay_constellation/visualizer/plots/<case_id>/connectivity.png)",
    )

    solution_parser = subparsers.add_parser(
        "solution",
        help="Render solution-inspection artifacts for one case and one solution.",
    )
    solution_parser.add_argument(
        "--case-dir",
        required=True,
        help="Path to dataset/cases/<case_id>",
    )
    solution_parser.add_argument(
        "--solution-path",
        required=True,
        help="Path to the solution JSON file",
    )
    solution_parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for solution artifacts (default: benchmarks/relay_constellation/visualizer/plots/<case_id>/solution/<solution_stem>)",
    )
    solution_parser.add_argument(
        "--texture-path",
        type=Path,
        help="Optional local Earth texture path to use instead of auto-downloading",
    )

    args = parser.parse_args(argv)

    case_dir = Path(args.case_dir).resolve()
    default_case_root = DEFAULT_PLOTS_DIR / case_dir.name

    if args.command == "overview":
        out_dir = args.out_dir or (default_case_root / "overview")
        manifest = render_overview_set(
            case_dir,
            out_dir,
            texture_path=args.texture_path,
        )
        print(
            f"Wrote {len(manifest['overview_pngs'])} overview PNGs to {out_dir.resolve()}"
        )
        return 0

    if args.command == "connectivity":
        out_path = args.out_path or (default_case_root / "connectivity.png")
        manifest = render_connectivity_report(case_dir, out_path)
        print(
            f"Wrote connectivity PNG to {out_path.resolve()} "
            f"for {len(manifest['endpoint_pairs'])} endpoint pairs"
        )
        return 0

    solution_path = Path(args.solution_path).resolve()
    out_dir = args.out_dir or (
        default_case_root / "solution" / solution_path.stem
    )
    manifest = render_solution_report(
        case_dir,
        solution_path,
        out_dir,
        texture_path=args.texture_path,
    )
    print(
        f"Wrote solution artifacts to {out_dir.resolve()} "
        f"with {len(manifest['snapshot_pngs'])} snapshots"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
