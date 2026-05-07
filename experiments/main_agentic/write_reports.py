#!/usr/bin/env python3
"""Write main-agentic benchmark reports from aggregate summaries."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import plan as family_plan  # type: ignore[no-redef]
    import plot_radar as radar_scores  # type: ignore[no-redef]
else:
    from . import plan as family_plan
    from . import plot_radar as radar_scores


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "matrix.yaml"
DEFAULT_REPORTS_DIR = FAMILY_DIR / "reports"
DEFAULT_BASELINES = FAMILY_DIR / "baselines" / "main_solver.yaml"
STANDARD_RUN_COLUMNS = {
    "config_name",
    "benchmark",
    "harness",
    "split",
    "case_id",
    "result_path",
    "artifact_state",
    "mode",
    "overall_status",
    "agent_status",
    "verifier_status",
    "valid",
    "duration_seconds",
    "start_time",
    "end_time",
}
PROCESSED_METRIC_COLUMNS = {
    "profit_score_pct",
    "revisit_score_pct",
}
BENCHMARK_TITLES = {
    "aeossp_standard": "AEOSSP Standard",
    "regional_coverage": "Regional Coverage",
    "relay_constellation": "Relay Constellation",
    "revisit_constellation": "Revisit Constellation",
    "satnet": "SatNet",
    "spot5": "SPOT-5",
    "stereo_imaging": "Stereo Imaging",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write main-agentic report markdown files from aggregate CSV summaries."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Batch config whose aggregate summaries should be reported.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory where benchmark report markdown files should be written.",
    )
    parser.add_argument(
        "--baseline-data",
        type=Path,
        default=DEFAULT_BASELINES,
        help="YAML file containing baseline constants for normalized score computation.",
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


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Aggregate CSV does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _format_value(value: str | None) -> str:
    if value in (None, ""):
        return "-"
    if value in {"True", "False"}:
        return value.lower()
    try:
        numeric = float(value)
    except ValueError:
        return value
    if numeric.is_integer() and "." not in value.lower().split("e", maxsplit=1)[0]:
        return str(int(numeric))
    if abs(numeric) >= 100:
        return f"{numeric:.1f}"
    if abs(numeric) >= 10:
        return f"{numeric:.2f}"
    return f"{numeric:.4f}"


def _metric_columns(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return []
    fieldnames = list(rows[0])
    return [
        name
        for name in fieldnames
        if name not in STANDARD_RUN_COLUMNS
        and name not in PROCESSED_METRIC_COLUMNS
        and any(row.get(name) not in (None, "") for row in rows)
    ]


def _valid_value(row: dict[str, str]) -> bool:
    return row.get("valid") == "True"


def _normalized_score(
    *,
    benchmark: str,
    row: dict[str, str],
    baseline_data: dict[str, object],
) -> float:
    if not _valid_value(row):
        return 0.0
    score = radar_scores._normalized_score_pct(
        benchmark=benchmark,
        split=row.get("split", ""),
        case_id=row.get("case_id", ""),
        metrics=radar_scores._numeric_row_metrics(row),
        baseline_data=baseline_data,
    )
    return score if score is not None else 0.0


def _mean_normalized_score(
    *,
    benchmark: str,
    harness: str,
    rows: list[dict[str, str]],
    baseline_data: dict[str, object],
) -> float | None:
    scores = [
        _normalized_score(benchmark=benchmark, row=row, baseline_data=baseline_data)
        for row in rows
        if row.get("harness") == harness
    ]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _table(headers: list[str], rows: list[list[str]], *, numeric_from: int = 0) -> list[str]:
    align = ["---"] * len(headers)
    for index in range(numeric_from, len(headers)):
        align[index] = "---:"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(align) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _summary_rows(
    benchmark: str,
    summary_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        row
        for row in summary_rows
        if row.get("benchmark") == benchmark and row.get("present_runs") not in ("", "0")
    ]


def _write_benchmark_report(
    *,
    benchmark: str,
    summary_rows: list[dict[str, str]],
    run_rows: list[dict[str, str]],
    reports_dir: Path,
    baseline_data: dict[str, object],
) -> None:
    title = BENCHMARK_TITLES.get(benchmark, benchmark.replace("_", " ").title())
    present_rows = [row for row in run_rows if row.get("artifact_state") == "present"]
    metric_columns = _metric_columns(present_rows)
    benchmark_summary_rows = _summary_rows(benchmark, summary_rows)

    lines = [
        f"# {title}",
        "",
        "Generated from the current `main_agentic` aggregate summaries.",
        "",
    ]
    if not present_rows:
        lines.extend(["No present run artifacts yet.", ""])
        (reports_dir / f"{benchmark}.md").write_text("\n".join(lines), encoding="utf-8")
        return

    lines.extend(
        _table(
            [
                "Harness",
                "Present",
                "Success",
                "Valid",
                "Invalid",
                "Timeout",
                "Primary Mean",
                "Normalized Mean",
            ],
            [
                [
                    row["harness"],
                    _format_value(row.get("present_runs")),
                    _format_value(row.get("success_count")),
                    _format_value(row.get("valid_count")),
                    _format_value(row.get("invalid_count")),
                    _format_value(row.get("timeout_count")),
                    (
                        f"{row['primary_metric_name']}={_format_value(row.get('primary_metric_mean'))}"
                        if row.get("primary_metric_name")
                        else "-"
                    ),
                    _format_value(
                        str(
                            _mean_normalized_score(
                                benchmark=benchmark,
                                harness=row["harness"],
                                rows=present_rows,
                                baseline_data=baseline_data,
                            )
                        )
                    ),
                ]
                for row in benchmark_summary_rows
            ],
            numeric_from=1,
        )
    )
    lines.append("")

    for harness in sorted({row["harness"] for row in present_rows}):
        harness_rows = [row for row in present_rows if row["harness"] == harness]
        lines.extend([f"## {harness}", ""])
        headers = ["Case", "Valid", "Duration (s)", "Normalized Score", *metric_columns]
        table_rows = []
        for row in sorted(harness_rows, key=lambda item: item["case_id"]):
            table_rows.append(
                [
                    row["case_id"],
                    "true" if _valid_value(row) else "false",
                    _format_value(row.get("duration_seconds")),
                    _format_value(
                        str(
                            _normalized_score(
                                benchmark=benchmark,
                                row=row,
                                baseline_data=baseline_data,
                            )
                        )
                    ),
                    *[_format_value(row.get(metric)) for metric in metric_columns],
                ]
            )
        lines.extend(_table(headers, table_rows, numeric_from=2))
        lines.append("")

    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"{benchmark}.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.resolve()
    summaries_root = _summaries_root(config_path)
    summary_rows = _read_csv(summaries_root / "benchmark_harness_summary.csv")
    baseline_data = radar_scores._load_baseline_data(args.baseline_data.resolve())

    for benchmark_csv in sorted((summaries_root / "benchmarks").glob("*.csv")):
        benchmark = benchmark_csv.stem
        _write_benchmark_report(
            benchmark=benchmark,
            summary_rows=summary_rows,
            run_rows=_read_csv(benchmark_csv),
            reports_dir=args.reports_dir.resolve(),
            baseline_data=baseline_data,
        )

    print(f"Reports written to {args.reports_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
