#!/usr/bin/env python3
"""Plot verifier-exposure normalized scores by harness."""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import aggregate as family_aggregate  # type: ignore[no-redef]
    import write_reports as family_reports  # type: ignore[no-redef]
else:
    from . import aggregate as family_aggregate
    from . import write_reports as family_reports


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
DEFAULT_OUTPUT = FAMILY_DIR / "reports" / "verifier_exposure_scores.png"
DEFAULT_HARNESSES = ("codex", "opencode_dpsk")
EXPOSURE_ORDER = ("transparent", "opaque", "none")
EXPOSURE_LABELS = {
    "transparent": "Transparent",
    "opaque": "Opaque",
    "none": "None",
}
EXPOSURE_COLORS = {
    "transparent": "#2f8f6f",
    "opaque": "#d18f2f",
    "none": "#667085",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot verifier-exposure normalized scores for Codex and opencode_dpsk."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Config whose aggregate artifacts should be plotted.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output image path.",
    )
    return parser.parse_args(argv)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Aggregate CSV does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _aggregate_csv_path(config_path: Path) -> Path:
    config = family_aggregate._load_config(config_path)
    return family_aggregate._aggregate_dir(config, config_path) / "runs.csv"


def _mean_score(
    rows: list[dict[str, str]],
    *,
    harness: str,
    exposure: str,
) -> float | None:
    selected = [
        row
        for row in rows
        if row.get("kind", "agent") == "agent"
        and row.get("exposure") == exposure
        and (row.get("harness") or row.get("system")) == harness
    ]
    return family_reports._mean_normalized_score_pct(selected)


def _scores_by_harness(
    rows: list[dict[str, str]],
    *,
    harnesses: tuple[str, ...] = DEFAULT_HARNESSES,
    exposures: tuple[str, ...] = EXPOSURE_ORDER,
) -> dict[str, dict[str, float | None]]:
    return {
        harness: {
            exposure: _mean_score(rows, harness=harness, exposure=exposure)
            for exposure in exposures
        }
        for harness in harnesses
    }


def _plot_scores(
    scores: dict[str, dict[str, float | None]],
    *,
    output_path: Path,
) -> None:
    os.environ.setdefault(
        "MPLCONFIGDIR",
        str(Path(tempfile.gettempdir()) / "astroreason-verifier-exposure-matplotlib"),
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8), sharey=True)
    for ax, harness in zip(axes, DEFAULT_HARNESSES, strict=True):
        exposure_scores = scores.get(harness, {})
        values = [exposure_scores.get(exposure) for exposure in EXPOSURE_ORDER]
        plot_values = [0.0 if value is None else value for value in values]
        labels = [EXPOSURE_LABELS[exposure] for exposure in EXPOSURE_ORDER]
        colors = [EXPOSURE_COLORS[exposure] for exposure in EXPOSURE_ORDER]
        bars = ax.bar(labels, plot_values, color=colors, width=0.62)
        ax.set_title(harness, fontsize=13, fontweight="bold")
        ax.set_ylim(0, 100)
        ax.grid(axis="y", alpha=0.25)
        ax.set_axisbelow(True)
        ax.tick_params(axis="x", labelrotation=20)
        for bar, value in zip(bars, values, strict=True):
            label = "n/a" if value is None else f"{value:.1f}"
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1.5,
                label,
                ha="center",
                va="bottom",
                fontsize=9,
            )

    axes[0].set_ylabel("Normalized score")
    fig.suptitle("Verifier Exposure Normalized Scores", fontsize=15, fontweight="bold")
    fig.text(
        0.5,
        0.02,
        "Score is stereo normalized quality as percentage points; missing and invalid runs score 0.",
        ha="center",
        fontsize=9,
        color="#475467",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.06, 1, 0.94))
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.resolve()
    rows = _read_csv(_aggregate_csv_path(config_path))
    _plot_scores(
        _scores_by_harness(rows),
        output_path=args.output.resolve(),
    )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
