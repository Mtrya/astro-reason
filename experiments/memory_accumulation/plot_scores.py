#!/usr/bin/env python3
"""Plot memory-accumulation transfer summaries."""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run as family_run  # type: ignore[no-redef]
else:
    from . import run as family_run


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
DEFAULT_REPORTS_DIR = FAMILY_DIR / "reports"
TRANSFER_DELTA_OUTPUT = "memory_transfer_delta.png"
SCORE_HEATMAP_OUTPUT = "memory_score_heatmap.png"
READINESS_OUTPUT = "memory_readiness.png"
PLOT_OUTPUTS = (TRANSFER_DELTA_OUTPUT, SCORE_HEATMAP_OUTPUT, READINESS_OUTPUT)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot memory-accumulation score summaries.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    return parser.parse_args(argv)


def _display_path(path: Path) -> str:
    if path.is_relative_to(REPO_ROOT):
        return path.relative_to(REPO_ROOT).as_posix()
    return path.as_posix()


def _aggregate_csv_path(config_path: Path) -> Path:
    config = family_run.load_family_config(config_path.resolve())
    return config.results.aggregate_dir / "runs.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Aggregate CSV does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _numeric(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _score(row: dict[str, str]) -> float | None:
    return _numeric(row.get("normalized_score_pct"))


def matched_delta_records(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    baseline: dict[tuple[str, str, str, str], float] = {}
    for row in rows:
        if row.get("memory_source") != "none":
            continue
        if row.get("artifact_state") != "present":
            continue
        score = _score(row)
        if score is None:
            continue
        baseline[
            (
                row.get("benchmark", ""),
                row.get("harness", ""),
                row.get("split", ""),
                row.get("case_id", ""),
            )
        ] = score

    records: list[dict[str, Any]] = []
    for row in rows:
        memory_source = row.get("memory_source", "")
        if memory_source in ("", "none"):
            continue
        if row.get("artifact_state") != "present":
            continue
        score = _score(row)
        if score is None:
            continue
        key = (
            row.get("benchmark", ""),
            row.get("harness", ""),
            row.get("split", ""),
            row.get("case_id", ""),
        )
        baseline_score = baseline.get(key)
        if baseline_score is None:
            continue
        records.append(
            {
                "benchmark": key[0],
                "harness": key[1],
                "split": key[2],
                "case_id": key[3],
                "memory_source": memory_source,
                "baseline_score": baseline_score,
                "memory_score": score,
                "delta": score - baseline_score,
            }
        )
    return records


def delta_summaries(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in matched_delta_records(rows):
        groups[(record["benchmark"], record["memory_source"], record["harness"])].append(record)

    summaries: list[dict[str, Any]] = []
    for (benchmark, memory_source, harness), records in sorted(groups.items()):
        deltas = [float(record["delta"]) for record in records]
        memory_scores = [float(record["memory_score"]) for record in records]
        baseline_scores = [float(record["baseline_score"]) for record in records]
        summaries.append(
            {
                "benchmark": benchmark,
                "memory_source": memory_source,
                "harness": harness,
                "pair_count": len(records),
                "mean_baseline_score": _mean(baseline_scores),
                "mean_memory_score": _mean(memory_scores),
                "mean_delta": _mean(deltas),
                "improved_count": sum(1 for value in deltas if value > 0),
                "regressed_count": sum(1 for value in deltas if value < 0),
            }
        )
    return summaries


def readiness_summaries(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row.get("memory_source", ""), row.get("harness", ""))].append(row)

    summaries: list[dict[str, Any]] = []
    for (memory_source, harness), group_rows in sorted(groups.items()):
        present = sum(1 for row in group_rows if row.get("artifact_state") == "present")
        missing = sum(1 for row in group_rows if row.get("artifact_state") == "missing_artifact")
        other = len(group_rows) - present - missing
        summaries.append(
            {
                "memory_source": memory_source,
                "harness": harness,
                "expected_count": len(group_rows),
                "present_count": present,
                "missing_count": missing,
                "other_count": other,
            }
        )
    return summaries


def score_matrix(rows: list[dict[str, str]]) -> tuple[list[str], list[str], list[list[float | None]]]:
    benchmarks = sorted({row.get("benchmark", "") for row in rows if row.get("benchmark")})
    combos = sorted(
        {
            (row.get("memory_source", ""), row.get("harness", ""))
            for row in rows
            if row.get("memory_source") and row.get("harness")
        }
    )
    combo_labels = [f"{source}->{harness}" for source, harness in combos]
    matrix: list[list[float | None]] = []
    for benchmark in benchmarks:
        row_values: list[float | None] = []
        for memory_source, harness in combos:
            values = [
                score
                for row in rows
                if row.get("benchmark") == benchmark
                and row.get("memory_source") == memory_source
                and row.get("harness") == harness
                if (score := _score(row)) is not None
            ]
            row_values.append(_mean(values))
        matrix.append(row_values)
    return benchmarks, combo_labels, matrix


def _setup_matplotlib() -> Any:
    os.environ.setdefault(
        "MPLCONFIGDIR",
        str(Path(tempfile.gettempdir()) / "astroreason-memory-accumulation-matplotlib"),
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _empty_plot(output_path: Path, title: str, message: str) -> None:
    plt = _setup_matplotlib()
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.axis("off")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=11, color="#475467")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _plot_transfer_delta(rows: list[dict[str, str]], output_path: Path) -> None:
    summaries = [item for item in delta_summaries(rows) if item.get("mean_delta") is not None]
    if not summaries:
        _empty_plot(output_path, "Memory Transfer Delta", "No matched scored memory comparisons.")
        return

    plt = _setup_matplotlib()
    summaries = sorted(summaries, key=lambda item: float(item["mean_delta"]))
    labels = [
        f"{item['benchmark']}\n{item['memory_source']}->{item['harness']}"
        for item in summaries
    ]
    values = [float(item["mean_delta"]) for item in summaries]
    colors = ["#2f8f6f" if value >= 0 else "#c75f3a" for value in values]

    fig_height = max(4.8, 0.42 * len(values) + 1.6)
    fig, ax = plt.subplots(figsize=(9.2, fig_height))
    bars = ax.barh(labels, values, color=colors)
    ax.axvline(0, color="#344054", linewidth=1)
    ax.set_title("Memory Transfer Delta", fontsize=15, fontweight="bold")
    ax.set_xlabel("Mean normalized-score delta vs no memory")
    ax.grid(axis="x", alpha=0.22)
    ax.set_axisbelow(True)
    for bar, value in zip(bars, values, strict=True):
        offset = 0.8 if value >= 0 else -0.8
        ha = "left" if value >= 0 else "right"
        ax.text(value + offset, bar.get_y() + bar.get_height() / 2, f"{value:+.1f}", va="center", ha=ha, fontsize=8.5)
    fig.text(
        0.5,
        0.015,
        "Only matched case pairs with numeric normalized scores on both sides are included.",
        ha="center",
        fontsize=8.5,
        color="#475467",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _plot_score_heatmap(rows: list[dict[str, str]], output_path: Path) -> None:
    benchmarks, combo_labels, matrix = score_matrix(rows)
    if not benchmarks or not combo_labels:
        _empty_plot(output_path, "Memory Score Heatmap", "No scored aggregate rows.")
        return

    plt = _setup_matplotlib()
    masked_values = [[0.0 if value is None else value for value in row] for row in matrix]
    fig_width = max(7.5, 0.7 * len(combo_labels) + 2.6)
    fig_height = max(4.8, 0.55 * len(benchmarks) + 1.8)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    image = ax.imshow(masked_values, cmap="YlGnBu", vmin=0, vmax=100, aspect="auto")
    ax.set_title("Mean Normalized Score", fontsize=15, fontweight="bold")
    ax.set_xticks(range(len(combo_labels)), combo_labels, rotation=35, ha="right")
    ax.set_yticks(range(len(benchmarks)), benchmarks)
    for y, row in enumerate(matrix):
        for x, value in enumerate(row):
            label = "n/a" if value is None else f"{value:.1f}"
            ax.text(x, y, label, ha="center", va="center", fontsize=8.3, color="#101828")
    colorbar = fig.colorbar(image, ax=ax)
    colorbar.set_label("Mean normalized score")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _plot_readiness(rows: list[dict[str, str]], output_path: Path) -> None:
    summaries = readiness_summaries(rows)
    if not summaries:
        _empty_plot(output_path, "Memory Matrix Readiness", "No aggregate rows.")
        return

    plt = _setup_matplotlib()
    labels = [f"{item['memory_source']}->{item['harness']}" for item in summaries]
    present = [int(item["present_count"]) for item in summaries]
    missing = [int(item["missing_count"]) for item in summaries]
    other = [int(item["other_count"]) for item in summaries]

    fig_width = max(8.4, 0.55 * len(labels) + 2.0)
    fig, ax = plt.subplots(figsize=(fig_width, 4.8))
    x_positions = list(range(len(labels)))
    ax.bar(x_positions, present, color="#2f8f6f", label="Present")
    ax.bar(x_positions, missing, bottom=present, color="#d0d5dd", label="Missing")
    stacked = [left + right for left, right in zip(present, missing, strict=True)]
    ax.bar(x_positions, other, bottom=stacked, color="#d18f2f", label="Other")
    ax.set_title("Memory Matrix Readiness", fontsize=15, fontweight="bold")
    ax.set_ylabel("Run count")
    ax.set_xticks(x_positions, labels, rotation=35, ha="right")
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def write_default_plots(*, config_path: Path = DEFAULT_CONFIG, reports_dir: Path = DEFAULT_REPORTS_DIR) -> list[Path]:
    rows = _read_csv(_aggregate_csv_path(config_path.resolve()))
    reports_dir = reports_dir.resolve()
    outputs = [
        reports_dir / TRANSFER_DELTA_OUTPUT,
        reports_dir / SCORE_HEATMAP_OUTPUT,
        reports_dir / READINESS_OUTPUT,
    ]
    _plot_transfer_delta(rows, outputs[0])
    _plot_score_heatmap(rows, outputs[1])
    _plot_readiness(rows, outputs[2])
    return outputs


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    for output_path in write_default_plots(config_path=args.config, reports_dir=args.reports_dir):
        print(f"Wrote {_display_path(output_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
