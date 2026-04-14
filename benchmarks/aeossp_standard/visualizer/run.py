"""CLI entry point for the aeossp_standard case visualizer."""

from __future__ import annotations

import argparse
from pathlib import Path

from .plot import DEFAULT_PLOTS_DIR, render_case_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render aeossp_standard case-inspection artifacts."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    case_parser = subparsers.add_parser(
        "case",
        help="Render case-only inspection artifacts for one case.",
    )
    case_parser.add_argument(
        "--case-dir",
        required=True,
        help="Path to dataset/cases/<case_id>",
    )
    case_parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for rendered artifacts (default: benchmarks/aeossp_standard/visualizer/plots/<case_id>/case)",
    )
    case_parser.add_argument(
        "--texture-path",
        type=Path,
        default=None,
        help="Optional local Earth texture path for the overview map",
    )
    case_parser.add_argument(
        "--access-step-s",
        type=int,
        default=60,
        help="Sampling step in seconds for coarse access summaries",
    )
    case_parser.add_argument(
        "--track-step-s",
        type=int,
        default=300,
        help="Sampling step in seconds for satellite ground tracks",
    )

    args = parser.parse_args(argv)
    case_dir = Path(args.case_dir).resolve()
    out_dir = args.out_dir or (DEFAULT_PLOTS_DIR / case_dir.name / "case")
    manifest = render_case_bundle(
        case_dir,
        out_dir,
        texture_path=args.texture_path,
        access_step_s=args.access_step_s,
        track_step_s=args.track_step_s,
    )
    print(
        f"Wrote case artifacts to {Path(out_dir).resolve()} "
        f"for {manifest['counts']['num_tasks']} tasks"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
