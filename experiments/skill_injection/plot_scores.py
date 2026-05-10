#!/usr/bin/env python3
"""Plot skill-injection normalized scores by benchmark and harness."""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import aggregate as family_aggregate  # type: ignore[no-redef]
else:
    from . import aggregate as family_aggregate


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
DEFAULT_REPORTS_DIR = FAMILY_DIR / "reports"


@dataclass(frozen=True)
class PlotSpec:
    benchmark: str
    harness: str
    conditions: tuple[str, ...]
    output_name: str


PLOT_SPECS = (
    PlotSpec(
        benchmark="stereo_imaging",
        harness="opencode_dpsk",
        conditions=("no_skill", "compact_domain", "skill_pack"),
        output_name="stereo_imaging_opencode_dpsk_scores.png",
    ),
    PlotSpec(
        benchmark="stereo_imaging",
        harness="opencode_minimax",
        conditions=("no_skill", "compact_domain", "skill_pack"),
        output_name="stereo_imaging_opencode_minimax_scores.png",
    ),
    PlotSpec(
        benchmark="satnet",
        harness="codex",
        conditions=("no_skill", "satnet_ortools_python"),
        output_name="satnet_codex_scores.png",
    ),
)

CONDITION_LABELS = {
    "no_skill": "No skill",
    "compact_domain": "Compact domain",
    "skill_pack": "Skill pack",
    "satnet_ortools_python": "Python + CP-SAT",
}
CONDITION_COLORS = {
    "no_skill": "#667085",
    "compact_domain": "#2f8f6f",
    "skill_pack": "#2f6fd1",
    "satnet_ortools_python": "#2f6fd1",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot skill-injection normalized score bars.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    return parser.parse_args(argv)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Aggregate CSV does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _aggregate_csv_path(config_path: Path) -> Path:
    config = family_aggregate.family_run.load_family_config(config_path)
    return family_aggregate._aggregate_dir(config) / "runs.csv"


def _numeric(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _mean_score(rows: list[dict[str, str]], *, benchmark: str, harness: str, condition: str) -> float | None:
    values = [
        value
        for row in rows
        if row.get("benchmark") == benchmark
        and row.get("harness") == harness
        and row.get("condition") == condition
        if (value := _numeric(row.get("normalized_score_pct"))) is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


def _plot_one(rows: list[dict[str, str]], *, spec: PlotSpec, output_path: Path) -> None:
    os.environ.setdefault(
        "MPLCONFIGDIR",
        str(Path(tempfile.gettempdir()) / "astroreason-skill-injection-matplotlib"),
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scores = [
        _mean_score(rows, benchmark=spec.benchmark, harness=spec.harness, condition=condition)
        for condition in spec.conditions
    ]
    heights = [0.0 if score is None else score for score in scores]
    labels = [CONDITION_LABELS.get(condition, condition) for condition in spec.conditions]
    colors = [CONDITION_COLORS.get(condition, "#2f6fd1") for condition in spec.conditions]

    fig, ax = plt.subplots(figsize=(6.2, 4.4))
    bars = ax.bar(labels, heights, color=colors, width=0.58)
    ax.set_title(f"{spec.benchmark} / {spec.harness}", fontsize=14, fontweight="bold")
    ax.set_ylabel("Normalized score")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", labelrotation=18)
    for bar, score in zip(bars, scores, strict=True):
        label = "n/a" if score is None else f"{score:.1f}"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.5,
            label,
            ha="center",
            va="bottom",
            fontsize=9,
        )
    fig.text(
        0.5,
        0.02,
        "Bars are mean normalized score across configured cases; missing runs are labeled n/a.",
        ha="center",
        fontsize=8.5,
        color="#475467",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def write_default_plots(*, config_path: Path = DEFAULT_CONFIG, reports_dir: Path = DEFAULT_REPORTS_DIR) -> list[Path]:
    rows = _read_csv(_aggregate_csv_path(config_path.resolve()))
    outputs: list[Path] = []
    for spec in PLOT_SPECS:
        output_path = reports_dir.resolve() / spec.output_name
        _plot_one(rows, spec=spec, output_path=output_path)
        outputs.append(output_path)
    return outputs


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    for output_path in write_default_plots(config_path=args.config, reports_dir=args.reports_dir):
        print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
