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

BASELINE_SPECS = {
    "aeossp_standard": {
        "agent_metric": "WCR",
        "direction": "maximize",
    },
    "regional_coverage": {
        "agent_metric": "coverage_ratio",
        "direction": "maximize",
    },
    "relay_constellation": {
        "agent_metric": "service_fraction",
        "direction": "maximize",
    },
    "revisit_constellation": {
        "agent_metric": "capped_max_revisit_gap_hours",
        "direction": "minimize",
    },
    "satnet": {
        "agent_metric": "score_hours",
        "direction": "maximize",
    },
    "spot5": {
        "agent_metric": "computed_profit",
        "direction": "maximize",
    },
    "stereo_imaging": {
        "agent_metric": "coverage_ratio",
        "direction": "maximize",
    },
}

# Best per-case traditional-solver baselines from experiments/main_solver.
# Values are intentionally hardcoded so this plot is stable even if the
# prose/tables in experiments/main_solver/README.md are later reorganized.
SOLVER_BASELINES = {
    "aeossp_standard": {
        "test/case_0001": 0.7057,
        "test/case_0002": 0.7763,
        "test/case_0003": 0.7837,
        "test/case_0004": 0.7395,
        "test/case_0005": 0.7858,
    },
    "regional_coverage": {
        "test/case_0001": 1.0,
        "test/case_0002": 0.9986,
        "test/case_0003": 0.9781,
        "test/case_0004": 1.0,
        "test/case_0005": 1.0,
    },
    "relay_constellation": {
        "test/case_0001": 0.9259,
        "test/case_0002": 0.9524,
        "test/case_0003": 0.9911,
        "test/case_0004": 0.9444,
        "test/case_0005": 0.9111,
    },
    "revisit_constellation": {
        "test/case_0001": 8.0,
        "test/case_0002": 8.0,
        "test/case_0003": 12.464,
        "test/case_0004": 12.0,
        "test/case_0005": 12.0,
    },
    "satnet": {
        "test/W10_2018": 886.0,
        "test/W20_2018": 1059.0,
        "test/W30_2018": 1100.0,
        "test/W40_2018": 1058.0,
        "test/W50_2018": 879.0,
    },
    "spot5": {
        "test/1021": 169243.0,
        "test/1403": 172143.0,
        "test/1506": 164241.0,
        "test/28": 56053.0,
        "test/8": 10.0,
    },
    "stereo_imaging": {
        "test/case_0001": 0.9789,
        "test/case_0002": 0.9917,
        "test/case_0003": 0.9587,
        "test/case_0004": 0.9444,
        "test/case_0005": 0.9787,
    },
}


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


def _case_keys(split: str, case_id: str) -> tuple[str, ...]:
    return (f"{split}/{case_id}", case_id)


def _case_baseline(
    *,
    benchmark: str,
    split: str,
    case_id: str,
) -> float | None:
    benchmark_baselines = SOLVER_BASELINES.get(benchmark, {})
    for key in _case_keys(split, case_id):
        if key in benchmark_baselines:
            return benchmark_baselines[key]
    return None


def _case_score_pct(
    *,
    value: float,
    baseline: float,
    direction: str,
) -> float | None:
    if baseline <= 0 or value <= 0:
        return None
    if direction == "maximize":
        return 100.0 * value / baseline
    return 100.0 * baseline / value


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _load_scores(summaries_root: Path) -> tuple[list[str], dict[str, dict[str, float]]]:
    scores_by_harness_benchmark: dict[str, dict[str, list[float]]] = {}
    for benchmark, spec in BASELINE_SPECS.items():
        csv_path = summaries_root / "benchmarks" / f"{benchmark}.csv"
        if not csv_path.exists():
            continue
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("valid") != "True":
                    score = 0.0
                else:
                    metric_value = _float_field(row, str(spec["agent_metric"]))
                    baseline = _case_baseline(
                        benchmark=benchmark,
                        split=row.get("split", ""),
                        case_id=row.get("case_id", ""),
                    )
                    if metric_value is None or baseline is None:
                        continue
                    score = _case_score_pct(
                        value=metric_value,
                        baseline=baseline,
                        direction=str(spec["direction"]),
                    )
                    if score is None:
                        continue
                scores_by_harness_benchmark.setdefault(row["harness"], {}).setdefault(
                    benchmark, []
                ).append(score)

    scores: dict[str, dict[str, float]] = {}
    for harness, benchmark_scores in scores_by_harness_benchmark.items():
        for benchmark, values in benchmark_scores.items():
            mean_score = _mean(values)
            if mean_score is not None:
                scores.setdefault(harness, {})[benchmark] = mean_score
    benchmarks = [
        benchmark for benchmark in BASELINE_SPECS if any(benchmark in item for item in scores.values())
    ]
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
    ax.set_title("Main Agentic Harness Radar vs Best Main Solver", pad=24)
    ax.legend(loc="upper right", bbox_to_anchor=(1.28, 1.12), frameon=False)
    ax.grid(True, alpha=0.35)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.resolve()
    _ensure_summary_csv(config_path, no_aggregate=args.no_aggregate)
    benchmarks, scores = _load_scores(_summaries_root(config_path))
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
