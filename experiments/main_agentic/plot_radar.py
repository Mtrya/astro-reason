#!/usr/bin/env python3
"""Plot main-agentic harness radar summaries."""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import aggregate as family_aggregate  # type: ignore[no-redef]
    import plan as family_plan  # type: ignore[no-redef]
else:
    from . import aggregate as family_aggregate
    from . import plan as family_plan


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "matrix.yaml"
DEFAULT_OUTPUT = FAMILY_DIR / "reports" / "harness_radar.png"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot a radar chart of harness performance across main-agentic benchmarks."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Batch config whose aggregate summaries should be plotted.",
    )
    parser.add_argument(
        "--harness",
        action="append",
        default=[],
        help="Harness to include. May be repeated. Defaults to every harness with a plottable score.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output image path. Defaults to experiments/main_agentic/reports/harness_radar.png.",
    )
    parser.add_argument(
        "--no-aggregate",
        action="store_true",
        help="Do not regenerate aggregate summaries when the summary CSV is missing.",
    )
    return parser.parse_args(argv)


def _summaries_root(config_path: Path) -> Path:
    plan = family_plan.build_batch_plan(
        config_path=config_path.resolve(),
        benchmark_filters=(),
        harness_filters=(),
        require_real_configs=False,
    )
    return plan.config.results.root / plan.config.config_path.stem / plan.config.results.aggregate_dir


def _summary_csv_path(config_path: Path) -> Path:
    return _summaries_root(config_path) / "benchmark_harness_summary.csv"


def _ensure_summary_csv(config_path: Path, *, no_aggregate: bool) -> Path:
    summary_csv = _summary_csv_path(config_path)
    if summary_csv.exists():
        return summary_csv
    if no_aggregate:
        raise SystemExit(f"Aggregate summary does not exist: {summary_csv}")
    family_aggregate.main(["--config", str(config_path)])
    if not summary_csv.exists():
        raise SystemExit(f"Aggregate summary was not created: {summary_csv}")
    return summary_csv


def _float_field(row: dict[str, str], key: str) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _row_score_pct(row: dict[str, str]) -> float | None:
    processed_mean = _float_field(row, "processed_metric_mean")
    if processed_mean is not None:
        return processed_mean

    primary_mean = _float_field(row, "primary_metric_mean")
    if primary_mean is None:
        return None
    if row.get("primary_metric_direction") == "maximize" and 0.0 <= primary_mean <= 1.0:
        return primary_mean * 100.0
    return None


def _load_scores(summary_csv: Path) -> tuple[list[str], dict[str, dict[str, float]]]:
    rows: list[dict[str, str]] = []
    with summary_csv.open("r", encoding="utf-8", newline="") as handle:
        rows.extend(csv.DictReader(handle))

    benchmarks = sorted({row["benchmark"] for row in rows})
    scores: dict[str, dict[str, float]] = {}
    for row in rows:
        score = _row_score_pct(row)
        if score is None:
            continue
        scores.setdefault(row["harness"], {})[row["benchmark"]] = score
    return benchmarks, scores


def _selected_scores(
    scores: dict[str, dict[str, float]],
    requested_harnesses: list[str],
) -> dict[str, dict[str, float]]:
    if not requested_harnesses:
        return scores
    missing = [harness for harness in requested_harnesses if harness not in scores]
    if missing:
        raise SystemExit(
            "No plottable scores for harness(es): " + ", ".join(sorted(missing))
        )
    return {harness: scores[harness] for harness in requested_harnesses}


def _plot_radar(
    *,
    benchmarks: list[str],
    scores: dict[str, dict[str, float]],
    output_path: Path,
) -> None:
    if not benchmarks:
        raise SystemExit("No benchmarks were found in the aggregate summary.")
    if not scores:
        raise SystemExit("No plottable harness scores were found in the aggregate summary.")

    os.environ.setdefault(
        "MPLCONFIGDIR",
        str(Path(tempfile.gettempdir()) / "astroreason-main-agentic-matplotlib"),
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [benchmark.replace("_", "\n") for benchmark in benchmarks]
    angles = [2 * math.pi * index / len(benchmarks) for index in range(len(benchmarks))]
    closed_angles = angles + angles[:1]
    max_score = max(
        [100.0]
        + [
            score
            for harness_scores in scores.values()
            for score in harness_scores.values()
        ]
    )
    radial_max = math.ceil(max_score / 10.0) * 10.0

    fig, ax = plt.subplots(figsize=(9, 7), subplot_kw={"projection": "polar"})
    for harness, harness_scores in sorted(scores.items()):
        values = [harness_scores.get(benchmark, 0.0) for benchmark in benchmarks]
        closed_values = values + values[:1]
        ax.plot(closed_angles, closed_values, linewidth=2, label=harness)
        ax.fill(closed_angles, closed_values, alpha=0.08)

    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, radial_max)
    ax.set_yticks([tick for tick in (25, 50, 75, 100) if tick <= radial_max])
    ax.set_yticklabels([str(tick) for tick in ax.get_yticks()], fontsize=8)
    ax.set_title("Main Agentic Harness Radar", pad=24)
    ax.legend(loc="upper right", bbox_to_anchor=(1.28, 1.12), frameon=False)
    ax.grid(True, alpha=0.35)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.resolve()
    summary_csv = _ensure_summary_csv(config_path, no_aggregate=args.no_aggregate)
    benchmarks, scores = _load_scores(summary_csv)
    selected_scores = _selected_scores(scores, list(args.harness))
    _plot_radar(
        benchmarks=benchmarks,
        scores=selected_scores,
        output_path=args.output.resolve(),
    )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
