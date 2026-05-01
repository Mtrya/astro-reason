#!/usr/bin/env python3
"""Plot main-agentic harness radar summaries."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
import tempfile
from datetime import datetime
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
        "agent_metric": "weighted_coverage_ratio",
        "direction": "maximize",
    },
    "relay_constellation": {
        "agent_metric": "service_fraction",
        "direction": "maximize",
    },
    "revisit_constellation": {
        "agent_metric": "revisit_score_pct",
        "direction": "maximize",
        "baseline_transform": "revisit_score_pct",
    },
    "satnet": {
        "agent_metric": "u_rms",
        "direction": "minimize",
    },
    "spot5": {
        "agent_metric": "computed_profit",
        "direction": "maximize",
    },
    "stereo_imaging": {
        "agent_metric": "normalized_quality",
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
        "test/case_0002": 0.9989,
        "test/case_0003": 0.9776,
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
        "test/W10_2018": 0.26,
        "test/W20_2018": 0.21,
        "test/W30_2018": 0.28,
        "test/W40_2018": 0.39,
        "test/W50_2018": 0.35,
    },
    "spot5": {
        "test/1021": 169243.0,
        "test/1403": 172143.0,
        "test/1506": 164241.0,
        "test/28": 56053.0,
        "test/8": 10.0,
    },
    "stereo_imaging": {
        "test/case_0001": 0.9581,
        "test/case_0002": 0.9887,
        "test/case_0003": 0.9572,
        "test/case_0004": 0.9238,
        "test/case_0005": 0.9747,
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


def _parse_iso_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


def _is_numeric(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _revisit_solver_score_pct(*, split: str, case_id: str, max_gap_hours: float) -> float | None:
    mission_path = (
        family_plan.REPO_ROOT
        / "benchmarks"
        / "revisit_constellation"
        / "dataset"
        / "cases"
        / split
        / case_id
        / "mission.json"
    )
    try:
        mission = json.loads(mission_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(mission, dict):
        return None

    horizon_start = mission.get("horizon_start")
    horizon_end = mission.get("horizon_end")
    if not isinstance(horizon_start, str) or not isinstance(horizon_end, str):
        return None
    try:
        start = _parse_iso_datetime(horizon_start)
        end = _parse_iso_datetime(horizon_end)
    except ValueError:
        return None
    horizon_hours = (end - start).total_seconds() / 3600.0
    if horizon_hours <= 0:
        return None

    targets = mission.get("targets")
    if not isinstance(targets, list) or not targets:
        return None
    target_scores: list[float] = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        expected = target.get("expected_revisit_period_hours")
        if not _is_numeric(expected):
            continue
        target_scores.append(
            family_aggregate._revisit_target_score_pct(
                max_gap_hours=max_gap_hours,
                expected_revisit_hours=float(expected),
                horizon_hours=horizon_hours,
            )
        )
    if not target_scores:
        return None
    return statistics.mean(target_scores)


def _case_keys(split: str, case_id: str) -> tuple[str, ...]:
    return (f"{split}/{case_id}", case_id)


def _case_baseline(
    *,
    benchmark: str,
    split: str,
    case_id: str,
    transform: str | None = None,
) -> float | None:
    benchmark_baselines = SOLVER_BASELINES.get(benchmark, {})
    for key in _case_keys(split, case_id):
        if key in benchmark_baselines:
            baseline = benchmark_baselines[key]
            if transform == "revisit_score_pct":
                return _revisit_solver_score_pct(
                    split=split,
                    case_id=case_id,
                    max_gap_hours=baseline,
                )
            return baseline
    return None


def _case_score_pct(
    *,
    value: float,
    baseline: float,
    direction: str,
) -> float | None:
    if baseline <= 0 or value < 0:
        return None
    if direction == "maximize":
        return 100.0 * value / baseline
    if value <= 0:
        return None
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
                        transform=(
                            str(spec["baseline_transform"])
                            if "baseline_transform" in spec
                            else None
                        ),
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
