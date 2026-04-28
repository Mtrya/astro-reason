"""CLI entry point for the relay_constellation visualizer."""

from __future__ import annotations

import argparse
from pathlib import Path

from .plot import (
    DEFAULT_PLOTS_DIR,
    render_overview,
)
from .solution import render_solution


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render relay_constellation case and solution inspection plots."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    overview_parser = subparsers.add_parser(
        "overview",
        help="Render case-only backbone ground tracks and baseline connectivity PNGs.",
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

    solution_parser = subparsers.add_parser(
        "solution",
        help="Render solution-aware ground tracks and scheduled connectivity PNGs.",
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
        help="Directory for solution PNGs (default: benchmarks/relay_constellation/visualizer/plots/<case_id>/solution/<solution_stem>)",
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
        result = render_overview(
            case_dir,
            out_dir,
            texture_path=args.texture_path,
        )
        print(
            f"Wrote {result['ground_tracks_png']} and "
            f"{result['baseline_connectivity_png']} to {out_dir.resolve()}"
        )
        return 0

    solution_path = Path(args.solution_path).resolve()
    out_dir = args.out_dir or (
        default_case_root / "solution" / solution_path.stem
    )
    result = render_solution(
        case_dir,
        solution_path,
        out_dir,
        texture_path=args.texture_path,
    )
    print(
        f"Wrote {result['ground_tracks_png']} and "
        f"{result['scheduled_connectivity_png']} plus "
        f"{len(result['demand_window_pngs'])} demand-window PNGs to {out_dir.resolve()}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
