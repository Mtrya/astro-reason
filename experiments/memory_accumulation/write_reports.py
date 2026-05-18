#!/usr/bin/env python3
"""Write memory-accumulation reports from aggregate artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
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
STANDARD_COLUMNS = {
    "benchmark",
    "split",
    "condition",
    "memory_source",
    "harness",
    "case_id",
    "artifact_state",
    "source_experiment",
    "overall_status",
    "agent_status",
    "verifier_status",
    "valid",
    "duration_seconds",
    "normalized_score_pct",
    "result_path",
}
BENCHMARK_TITLES = {
    "regional_coverage": "Regional Coverage",
    "relay_constellation": "Relay Constellation",
    "satnet": "SatNet",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write memory-accumulation markdown reports.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    return parser.parse_args(argv)


def _display_path(path: Path) -> str:
    if path.is_relative_to(REPO_ROOT):
        return path.relative_to(REPO_ROOT).as_posix()
    return path.as_posix()


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


def _aggregate_dir(config_path: Path) -> Path:
    config = family_aggregate.family_run.load_family_config(config_path.resolve())
    return config.results.aggregate_dir


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


def _numeric(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _group_rows(rows: list[dict[str, str]], keys: tuple[str, ...]) -> dict[tuple[str, ...], list[dict[str, str]]]:
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(key, "") for key in keys)].append(row)
    return groups


def _score_mean(rows: list[dict[str, str]]) -> float | None:
    return _mean(
        [
            score
            for row in rows
            if (score := _numeric(row.get("normalized_score_pct"))) is not None
        ]
    )


def _valid_count(rows: list[dict[str, str]]) -> int:
    return sum(1 for row in rows if row.get("valid") == "True")


def _status_counts(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key) or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _readiness_rows(rows: list[dict[str, str]]) -> list[list[str]]:
    table_rows: list[list[str]] = []
    for (memory_source, harness), group_rows in sorted(_group_rows(rows, ("memory_source", "harness")).items()):
        present = sum(1 for row in group_rows if row.get("artifact_state") == "present")
        missing = sum(1 for row in group_rows if row.get("artifact_state") == "missing_artifact")
        table_rows.append(
            [
                memory_source,
                harness,
                _format_value(len(group_rows)),
                _format_value(present),
                _format_value(missing),
                _format_value(_valid_count(group_rows)),
                _format_value(_score_mean(group_rows)),
                _format_status_counts(_status_counts(group_rows, "overall_status")),
            ]
        )
    return table_rows


def _delta_table_rows(
    rows: list[dict[str, str]],
    *,
    positive: bool | None = None,
) -> list[list[str]]:
    summaries = family_plots.delta_summaries(rows)
    if positive is True:
        summaries = [item for item in summaries if (item.get("mean_delta") or 0) > 0]
        summaries = sorted(summaries, key=lambda item: float(item["mean_delta"]), reverse=True)
    elif positive is False:
        summaries = [item for item in summaries if (item.get("mean_delta") or 0) < 0]
        summaries = sorted(summaries, key=lambda item: float(item["mean_delta"]))
    else:
        summaries = sorted(summaries, key=lambda item: (item["benchmark"], item["memory_source"], item["harness"]))

    return [
        [
            item["benchmark"],
            item["memory_source"],
            item["harness"],
            _format_value(item.get("pair_count")),
            _format_value(item.get("mean_baseline_score")),
            _format_value(item.get("mean_memory_score")),
            _format_value(item.get("mean_delta")),
            _format_value(item.get("improved_count")),
            _format_value(item.get("regressed_count")),
        ]
        for item in summaries
    ]


def _benchmark_summary_rows(rows: list[dict[str, str]], benchmark: str) -> list[list[str]]:
    benchmark_rows = [row for row in rows if row.get("benchmark") == benchmark]
    table_rows: list[list[str]] = []
    for (memory_source, harness), group_rows in sorted(_group_rows(benchmark_rows, ("memory_source", "harness")).items()):
        present = sum(1 for row in group_rows if row.get("artifact_state") == "present")
        missing = sum(1 for row in group_rows if row.get("artifact_state") == "missing_artifact")
        table_rows.append(
            [
                memory_source,
                harness,
                _format_value(len(group_rows)),
                _format_value(present),
                _format_value(missing),
                _format_value(_valid_count(group_rows)),
                _format_value(_score_mean(group_rows)),
                _format_status_counts(_status_counts(group_rows, "overall_status")),
            ]
        )
    return table_rows


def _metric_columns(rows: list[dict[str, str]]) -> list[str]:
    return [
        field
        for field in family_aggregate.METRIC_FIELDS
        if field != "normalized_score_pct"
        and any(row.get(field) not in (None, "") for row in rows)
    ]


def _case_rows(rows: list[dict[str, str]], benchmark: str) -> list[list[str]]:
    benchmark_rows = [row for row in rows if row.get("benchmark") == benchmark]
    metric_columns = _metric_columns(benchmark_rows)
    table_rows: list[list[str]] = []
    for row in sorted(
        benchmark_rows,
        key=lambda item: (
            item.get("memory_source", ""),
            item.get("harness", ""),
            item.get("split", ""),
            item.get("case_id", ""),
        ),
    ):
        table_rows.append(
            [
                row.get("memory_source", ""),
                row.get("harness", ""),
                row.get("split", ""),
                row.get("case_id", ""),
                _format_value(row.get("artifact_state")),
                _format_value(row.get("overall_status")),
                _format_value(row.get("verifier_status")),
                _format_value(row.get("valid")),
                _format_value(row.get("duration_seconds")),
                _format_value(row.get("normalized_score_pct")),
                *[_format_value(row.get(metric)) for metric in metric_columns],
            ]
        )
    return table_rows


def _figure_lines(reports_dir: Path) -> list[str]:
    labels = {
        family_plots.TRANSFER_DELTA_OUTPUT: "Memory transfer delta",
        family_plots.SCORE_HEATMAP_OUTPUT: "Memory score heatmap",
        family_plots.READINESS_OUTPUT: "Memory matrix readiness",
    }
    lines: list[str] = []
    for output_name in family_plots.PLOT_OUTPUTS:
        if (reports_dir / output_name).exists():
            lines.extend([f"![{labels[output_name]}]({output_name})", ""])
    return lines


def _write_overview(*, summary: dict[str, Any], rows: list[dict[str, str]], reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "overview.md"
    lines = [
        "# Memory Accumulation",
        "",
        "Cross-benchmark memory-accumulation results comparing accumulated memory against matched no-memory main-agentic runs.",
        "",
        "Generated from the current `memory_accumulation` aggregate artifacts.",
        "",
    ]
    figure_lines = _figure_lines(reports_dir)
    if figure_lines:
        lines.extend(["## Figures", "", *figure_lines])
    lines.extend(["## Matrix Readiness", ""])
    lines.extend(
        shared_reports.table(
            [
                "Memory Source",
                "Harness",
                "Expected",
                "Present",
                "Missing",
                "Valid",
                "Mean Score",
                "Overall Statuses",
            ],
            _readiness_rows(rows),
            numeric_from=2,
        )
    )
    lines.extend(["", "## Best Demonstrations", ""])
    positive_rows = _delta_table_rows(rows, positive=True)
    if positive_rows:
        lines.extend(
            shared_reports.table(
                [
                    "Benchmark",
                    "Memory Source",
                    "Harness",
                    "Pairs",
                    "No-Memory Mean",
                    "Memory Mean",
                    "Delta",
                    "Improved",
                    "Regressed",
                ],
                positive_rows,
                numeric_from=3,
            )
        )
    else:
        lines.append("No positive matched scored deltas yet.")
    lines.extend(["", "## Regressions", ""])
    regression_rows = _delta_table_rows(rows, positive=False)
    if regression_rows:
        lines.extend(
            shared_reports.table(
                [
                    "Benchmark",
                    "Memory Source",
                    "Harness",
                    "Pairs",
                    "No-Memory Mean",
                    "Memory Mean",
                    "Delta",
                    "Improved",
                    "Regressed",
                ],
                regression_rows,
                numeric_from=3,
            )
        )
    else:
        lines.append("No negative matched scored deltas yet.")
    lines.extend(
        [
            "",
            "## Aggregate Metadata",
            "",
            f"- Config: `{summary.get('config', '-')}`",
            f"- Rows: `{summary.get('row_count', len(rows))}`",
            f"- Schema version: `{summary.get('schema_version', '-')}`",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _write_benchmark_report(*, rows: list[dict[str, str]], reports_dir: Path, benchmark: str) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    title = BENCHMARK_TITLES.get(benchmark, benchmark.replace("_", " ").title())
    report_path = reports_dir / f"{benchmark}.md"
    metric_columns = _metric_columns([row for row in rows if row.get("benchmark") == benchmark])
    lines = [
        f"# {title}",
        "",
        f"{benchmark} memory-accumulation comparison by memory source and evaluation harness.",
        "",
        "Generated from the current `memory_accumulation` aggregate artifacts.",
        "",
        "## Source And Harness Summary",
        "",
    ]
    lines.extend(
        shared_reports.table(
            [
                "Memory Source",
                "Harness",
                "Expected",
                "Present",
                "Missing",
                "Valid",
                "Mean Score",
                "Overall Statuses",
            ],
            _benchmark_summary_rows(rows, benchmark),
            numeric_from=2,
        )
    )
    lines.extend(["", "## Cases", ""])
    lines.extend(
        shared_reports.table(
            [
                "Memory Source",
                "Harness",
                "Split",
                "Case",
                "Artifact",
                "Overall Status",
                "Verifier Status",
                "Valid",
                "Duration (s)",
                "Score",
                *metric_columns,
            ],
            _case_rows(rows, benchmark),
            numeric_from=8,
        )
    )
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    aggregate_dir = _aggregate_dir(args.config)
    summary = _read_json(aggregate_dir / "summary.json")
    rows = _read_csv(aggregate_dir / "runs.csv")
    reports_dir = args.reports_dir.resolve()
    written = [_write_overview(summary=summary, rows=rows, reports_dir=reports_dir)]
    for benchmark in sorted({row.get("benchmark", "") for row in rows if row.get("benchmark")}):
        written.append(_write_benchmark_report(rows=rows, reports_dir=reports_dir, benchmark=benchmark))
    for path in written:
        print(f"Wrote {_display_path(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
