#!/usr/bin/env python3
"""Write skill-injection reports from aggregate artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import aggregate as family_aggregate  # type: ignore[no-redef]
    import plot_scores as family_plots  # type: ignore[no-redef]
else:
    from . import aggregate as family_aggregate
    from . import plot_scores as family_plots

from experiments._shared import write_reports as shared_reports


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
DEFAULT_REPORTS_DIR = FAMILY_DIR / "reports"

BENCHMARK_METRICS = {
    "stereo_imaging": (
        ("Mean Coverage", "mean_coverage_ratio", "coverage_ratio"),
        ("Mean Quality", "mean_normalized_quality", "normalized_quality"),
    ),
    "regional_coverage": (
        ("Mean Weighted Coverage", "mean_weighted_coverage_ratio", "weighted_coverage_ratio"),
        ("Mean Coverage", "mean_coverage_ratio", "coverage_ratio"),
        ("Mean Actions", "mean_num_actions", "num_actions"),
        ("Mean Min Battery", "mean_min_battery_wh", "min_battery_wh"),
    ),
    "relay_constellation": (
        ("Mean Service", "mean_service_fraction", "service_fraction"),
        (
            "Mean Worst Demand",
            "mean_worst_demand_service_fraction",
            "worst_demand_service_fraction",
        ),
        ("Mean Added Satellites", "mean_num_added_satellites", "num_added_satellites"),
        ("Mean Latency", "mean_mean_latency_ms", "mean_latency_ms"),
        ("Mean P95 Latency", "mean_latency_p95_ms", "latency_p95_ms"),
    ),
    "satnet": (
        ("Mean Hours", "mean_score_hours", "score_hours"),
        ("Mean U RMS", "mean_u_rms", "u_rms"),
        ("Mean U Max", "mean_u_max", "u_max"),
    ),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write skill-injection markdown reports.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    return parser.parse_args(argv)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Aggregate summary does not exist: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Aggregate summary must be a mapping: {path}")
    return data


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Aggregate CSV does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    return shared_reports.format_value(str(value))


def _format_status_counts(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "-"
    return ", ".join(f"{key}: {_format_value(count)}" for key, count in sorted(value.items()))


def _benchmark_summary(summary: dict[str, Any], benchmark: str) -> dict[str, Any]:
    by_condition = {
        key.split("/", maxsplit=1)[1]: value
        for key, value in (summary.get("by_benchmark_condition") or {}).items()
        if isinstance(key, str) and key.startswith(f"{benchmark}/")
    }
    by_condition_harness = {
        key.removeprefix(f"{benchmark}/"): value
        for key, value in (summary.get("by_benchmark_condition_harness") or {}).items()
        if isinstance(key, str) and key.startswith(f"{benchmark}/")
    }
    return {**summary, "by_condition": by_condition, "by_condition_harness": by_condition_harness}


def _condition_rows(summary: dict[str, Any]) -> list[list[str]]:
    by_condition = summary.get("by_condition")
    if not isinstance(by_condition, dict):
        return []
    rows: list[list[str]] = []
    for condition, values in sorted(by_condition.items()):
        if not isinstance(values, dict):
            continue
        rows.append(
            [
                str(condition),
                _format_value(values.get("run_count")),
                _format_value(values.get("present_count")),
                _format_value(values.get("valid_count")),
                _format_value(values.get("valid_rate")),
                *[
                    _format_value(values.get(summary_key))
                    for _label, summary_key, _row_key in BENCHMARK_METRICS.get(
                        str(summary.get("benchmark", "")),
                        (),
                    )
                ],
                _format_value(values.get("mean_normalized_score_pct")),
                _format_status_counts(values.get("overall_status_counts")),
            ]
        )
    return rows


def _condition_harness_rows(summary: dict[str, Any]) -> list[list[str]]:
    by_condition_harness = summary.get("by_condition_harness")
    if not isinstance(by_condition_harness, dict):
        return []
    rows: list[list[str]] = []
    for key, values in sorted(by_condition_harness.items()):
        if not isinstance(values, dict):
            continue
        condition, _, harness = str(key).partition("/")
        rows.append(
            [
                condition,
                harness,
                _format_value(values.get("run_count")),
                _format_value(values.get("present_count")),
                _format_value(values.get("valid_count")),
                _format_value(values.get("valid_rate")),
                *[
                    _format_value(values.get(summary_key))
                    for _label, summary_key, _row_key in BENCHMARK_METRICS.get(
                        str(summary.get("benchmark", "")),
                        (),
                    )
                ],
                _format_value(values.get("mean_normalized_score_pct")),
                _format_status_counts(values.get("overall_status_counts")),
            ]
        )
    return rows


def _case_rows(rows: list[dict[str, str]], *, benchmark: str) -> list[list[str]]:
    table_rows: list[list[str]] = []
    for row in sorted(
        rows,
        key=lambda item: (
            item.get("condition", ""),
            item.get("harness", ""),
            item.get("case_id", ""),
        ),
    ):
        table_rows.append(
            [
                row.get("condition", ""),
                row.get("harness", ""),
                row.get("split", ""),
                row.get("case_id", ""),
                _format_value(row.get("artifact_state")),
                _format_value(row.get("overall_status")),
                _format_value(row.get("verifier_status")),
                _format_value(row.get("valid")),
                _format_value(row.get("duration_seconds")),
                _format_value(row.get("skill_count")),
                *[
                    _format_value(row.get(row_key))
                    for _label, _summary_key, row_key in BENCHMARK_METRICS.get(benchmark, ())
                ],
                _format_value(row.get("normalized_score_pct")),
            ]
        )
    return table_rows


def _write_report(
    *,
    summary: dict[str, Any],
    rows: list[dict[str, str]],
    reports_dir: Path,
    benchmark: str,
) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{benchmark}.md"
    rows = [row for row in rows if row.get("benchmark") == benchmark]
    summary = _benchmark_summary(summary, benchmark)
    summary["benchmark"] = benchmark
    metric_specs = BENCHMARK_METRICS.get(benchmark, ())
    lines = [
        "# Skill Injection",
        "",
        f"{benchmark} skill-ablation results across configured conditions and harnesses.",
        "",
        "Generated from the current `skill_injection` aggregate artifacts.",
        "",
    ]
    plot_specs = [spec for spec in family_plots.PLOT_SPECS if spec.benchmark == benchmark]
    if plot_specs:
        lines.extend(["## Score Plots", ""])
        for spec in plot_specs:
            lines.extend([f"![{spec.benchmark} / {spec.harness}]({spec.output_name})", ""])
    lines.extend(
        [
        "## Condition Summary",
        "",
        ]
    )
    lines.extend(
        shared_reports.table(
            [
                "Condition",
                "Runs",
                "Present",
                "Valid",
                "Valid Rate",
                *[label for label, _summary_key, _row_key in metric_specs],
                "Mean Score",
                "Overall Statuses",
            ],
            _condition_rows(summary),
            numeric_from=1,
        )
    )
    lines.extend(["", "## Condition And Harness Summary", ""])
    lines.extend(
        shared_reports.table(
            [
                "Condition",
                "Harness",
                "Runs",
                "Present",
                "Valid",
                "Valid Rate",
                *[label for label, _summary_key, _row_key in metric_specs],
                "Mean Score",
                "Overall Statuses",
            ],
            _condition_harness_rows(summary),
            numeric_from=2,
        )
    )
    lines.extend(["", "## Cases", ""])
    lines.extend(
        shared_reports.table(
            [
                "Condition",
                "Harness",
                "Split",
                "Case",
                "Artifact",
                "Overall Status",
                "Verifier Status",
                "Valid",
                "Duration (s)",
                "Skills",
                *[label.removeprefix("Mean ") for label, _summary_key, _row_key in metric_specs],
                "Score",
            ],
            _case_rows(rows, benchmark=benchmark),
            numeric_from=8,
        )
    )
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _display_path(path: Path) -> str:
    if path.is_relative_to(REPO_ROOT):
        return path.relative_to(REPO_ROOT).as_posix()
    return path.as_posix()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.resolve()
    config = family_aggregate.family_run.load_family_config(config_path)
    aggregate_dir = family_aggregate._aggregate_dir(config)
    summary = _read_json(aggregate_dir / "summary.json")
    rows = _read_csv(aggregate_dir / "runs.csv")
    benchmarks = sorted({row.get("benchmark") or config.benchmark for row in rows})
    for benchmark in benchmarks:
        report_path = _write_report(
            summary=summary,
            rows=rows,
            reports_dir=args.reports_dir.resolve(),
            benchmark=benchmark,
        )
        print(f"Wrote {_display_path(report_path)}")
    for plot_path in family_plots.write_default_plots(
        config_path=config_path,
        reports_dir=args.reports_dir.resolve(),
    ):
        print(f"Wrote {_display_path(plot_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
