#!/usr/bin/env python3
"""Write verifier-exposure reports from aggregate artifacts."""

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
else:
    from . import aggregate as family_aggregate

from experiments._shared import write_reports as shared_reports
from experiments._shared import score_normalization as score_norm

FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
DEFAULT_REPORTS_DIR = FAMILY_DIR / "reports"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write verifier-exposure report markdown files from aggregate artifacts."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Config whose aggregate artifacts should be reported.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory where report markdown files should be written.",
    )
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


def _valid_value(row: dict[str, Any]) -> bool:
    value = row.get("valid")
    if isinstance(value, bool):
        return value
    return value == "True"


def _float_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _normalized_score_pct(row: dict[str, Any]) -> float | None:
    if not _valid_value(row):
        return 0.0
    return score_norm.stereo_imaging_score_pct(
        normalized_quality=_float_value(row.get("normalized_quality")),
    )


def _mean_normalized_score_pct(rows: list[dict[str, Any]]) -> float | None:
    values = [
        score
        for row in rows
        if (score := _normalized_score_pct(row)) is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


def _format_status_counts(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "-"
    return ", ".join(f"{key}: {_format_value(count)}" for key, count in sorted(value.items()))


def _exposure_summary_rows(summary: dict[str, Any]) -> list[list[str]]:
    by_exposure = summary.get("by_exposure")
    if not isinstance(by_exposure, dict):
        return []

    rows: list[list[str]] = []
    for exposure, values in sorted(by_exposure.items()):
        if not isinstance(values, dict):
            continue
        rows.append(
            [
                str(exposure),
                _format_value(values.get("run_count")),
                _format_value(values.get("valid_count")),
                _format_value(values.get("valid_rate")),
                _format_value(values.get("mean_coverage_ratio")),
                _format_value(values.get("mean_normalized_quality")),
                _format_value(values.get("mean_normalized_score_pct")),
                _format_status_counts(values.get("overall_status_counts")),
                _format_status_counts(values.get("verifier_status_counts")),
            ]
        )
    return rows


def _exposure_harness_summary_rows(summary: dict[str, Any]) -> list[list[str]]:
    by_exposure_system = summary.get("by_exposure_system") or summary.get("by_exposure_harness")
    if not isinstance(by_exposure_system, dict):
        return []

    rows: list[list[str]] = []
    for key, values in sorted(by_exposure_system.items()):
        if not isinstance(values, dict):
            continue
        exposure, _, system = str(key).partition("/")
        rows.append(
            [
                exposure,
                _format_value(values.get("kind", "agent")),
                system or "-",
                _format_value(values.get("run_count")),
                _format_value(values.get("valid_count")),
                _format_value(values.get("valid_rate")),
                _format_value(values.get("mean_coverage_ratio")),
                _format_value(values.get("mean_normalized_quality")),
                _format_value(values.get("mean_normalized_score_pct")),
                _format_status_counts(values.get("overall_status_counts")),
            ]
        )
    return rows


def _case_rows(rows: list[dict[str, str]]) -> list[list[str]]:
    table_rows: list[list[str]] = []
    for row in sorted(
        rows,
        key=lambda item: (
            item.get("exposure", ""),
            item.get("kind", "agent"),
            item.get("system") or item.get("harness", ""),
            item.get("case_id", ""),
        ),
    ):
        table_rows.append(
            [
                row.get("exposure", ""),
                row.get("kind", "agent"),
                row.get("system") or row.get("harness", ""),
                row.get("case_id", ""),
                _format_value(row.get("artifact_state")),
                _format_value(row.get("overall_status")),
                _format_value(row.get("verifier_status")),
                _format_value(row.get("valid")),
                _format_value(row.get("duration_seconds")),
                _format_value(row.get("coverage_ratio")),
                _format_value(row.get("normalized_quality")),
                _format_value(_normalized_score_pct(row)),
            ]
        )
    return table_rows


def _summary_with_normalized_scores(
    summary: dict[str, Any],
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    updated = dict(summary)
    for key in ("by_exposure", "by_exposure_system", "by_exposure_harness"):
        groups = summary.get(key)
        if not isinstance(groups, dict):
            continue
        updated_groups: dict[str, Any] = {}
        for group_key, values in groups.items():
            if not isinstance(values, dict):
                updated_groups[group_key] = values
                continue
            exposure, _, system = str(group_key).partition("/")
            group_rows = [
                row
                for row in rows
                if row.get("exposure") == str(group_key)
                or (
                    row.get("exposure") == exposure
                    and system
                    and (row.get("system") or row.get("harness")) == system
                )
            ]
            next_values = dict(values)
            next_values["mean_normalized_score_pct"] = _mean_normalized_score_pct(group_rows)
            updated_groups[group_key] = next_values
        updated[key] = updated_groups
    return updated


def _write_report(*, summary: dict[str, Any], rows: list[dict[str, str]], reports_dir: Path) -> Path:
    summary = _summary_with_normalized_scores(summary, rows)
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "stereo_imaging.md"
    lines = [
        "# Verifier Exposure",
        "",
        "Stereo-imaging comparison across verifier exposure tiers.",
        "",
        "Generated from the current `verifier_exposure` aggregate artifacts.",
        "",
        "## Exposure Summary",
        "",
    ]
    lines.extend(
        shared_reports.table(
            [
                "Exposure",
                "Runs",
                "Valid",
                "Valid Rate",
                "Mean Coverage",
                "Mean Quality",
                "Mean Score",
                "Overall Statuses",
                "Verifier Statuses",
            ],
            _exposure_summary_rows(summary),
            numeric_from=1,
        )
    )
    lines.extend(["", "## Exposure And System Summary", ""])
    lines.extend(
        shared_reports.table(
            [
                "Exposure",
                "Kind",
                "System",
                "Runs",
                "Valid",
                "Valid Rate",
                "Mean Coverage",
                "Mean Quality",
                "Mean Score",
                "Overall Statuses",
            ],
            _exposure_harness_summary_rows(summary),
            numeric_from=3,
        )
    )
    lines.extend(["", "## Cases", ""])
    lines.extend(
        shared_reports.table(
            [
                "Exposure",
                "Kind",
                "System",
                "Case",
                "Artifact",
                "Overall Status",
                "Verifier Status",
                "Valid",
                "Duration (s)",
                "Coverage",
                "Quality",
                "Score",
            ],
            _case_rows(rows),
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
    config = family_aggregate._load_config(config_path)
    aggregate_dir = family_aggregate._aggregate_dir(config, config_path)
    report_path = _write_report(
        summary=_read_json(aggregate_dir / "summary.json"),
        rows=_read_csv(aggregate_dir / "runs.csv"),
        reports_dir=args.reports_dir.resolve(),
    )
    print(f"Wrote {_display_path(report_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
