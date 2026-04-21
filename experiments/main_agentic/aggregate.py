#!/usr/bin/env python3
"""Aggregate run artifacts for the main agentic experiment family."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import plan as family_plan  # type: ignore[no-redef]
else:
    from . import plan as family_plan


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "matrix.yaml"
SUMMARY_VERSION = 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate main agentic run artifacts into reviewable summaries"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Batch config whose results should be aggregated.",
    )
    return parser.parse_args(argv)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _relative_display(path: Path) -> str:
    if path.is_relative_to(family_plan.REPO_ROOT):
        return path.relative_to(family_plan.REPO_ROOT).as_posix()
    return str(path)


def _load_config_mode(config_path: Path) -> str:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"Family config must be a mapping: {config_path}")
    mode = raw.get("mode")
    if not isinstance(mode, str) or not mode:
        raise SystemExit(f"Family config must define a non-empty mode: {config_path}")
    return mode


def _read_run_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _get_path_value(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _normalize_valid(verifier_payload: dict[str, Any], verifier_status: str) -> bool | None:
    valid = verifier_payload.get("valid")
    if isinstance(valid, bool):
        return valid
    is_valid = verifier_payload.get("is_valid")
    if isinstance(is_valid, bool):
        return is_valid
    if verifier_status == "valid":
        return True
    if verifier_status == "invalid":
        return False
    return None


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _coerce_numeric(value: Any) -> int | float | None:
    if not _is_numeric(value):
        return None
    if isinstance(value, int):
        return value
    return float(value)


def _metric_stats(values: list[int | float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
        }
    normalized = [float(value) for value in values]
    return {
        "count": len(normalized),
        "mean": statistics.mean(normalized),
        "median": statistics.median(normalized),
        "min": min(normalized),
        "max": max(normalized),
    }


def _format_stat(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _build_missing_record(item: family_plan.RunItem) -> dict[str, Any]:
    metrics = {metric.name: None for metric in item.benchmark_profile.score_metrics}
    flags = {metric.name: None for metric in item.benchmark_profile.flag_metrics}
    return {
        "config_name": item.config_name,
        "benchmark": item.benchmark,
        "harness": item.harness,
        "split": item.split,
        "case_id": item.case_id,
        "result_path": _relative_display(family_plan.run_output_dir(item)),
        "artifact_state": "missing_artifact",
        "mode": "batch",
        "overall_status": "missing_artifact",
        "agent_status": "missing_artifact",
        "verifier_status": "missing_artifact",
        "valid": None,
        "duration_seconds": None,
        "start_time": None,
        "end_time": None,
        "metrics": metrics,
        "flags": flags,
        "raw_verifier": {},
    }


def _build_malformed_record(item: family_plan.RunItem) -> dict[str, Any]:
    metrics = {metric.name: None for metric in item.benchmark_profile.score_metrics}
    flags = {metric.name: None for metric in item.benchmark_profile.flag_metrics}
    return {
        "config_name": item.config_name,
        "benchmark": item.benchmark,
        "harness": item.harness,
        "split": item.split,
        "case_id": item.case_id,
        "result_path": _relative_display(family_plan.run_output_dir(item)),
        "artifact_state": "malformed_artifact",
        "mode": "batch",
        "overall_status": "malformed_artifact",
        "agent_status": "malformed_artifact",
        "verifier_status": "malformed_artifact",
        "valid": None,
        "duration_seconds": None,
        "start_time": None,
        "end_time": None,
        "metrics": metrics,
        "flags": flags,
        "raw_verifier": {},
    }


def _normalize_run_record(item: family_plan.RunItem, run_data: dict[str, Any]) -> dict[str, Any]:
    verifier_payload = run_data.get("verifier")
    if not isinstance(verifier_payload, dict):
        verifier_payload = {}

    overall_status = run_data.get("overall_status")
    agent_status = run_data.get("agent_status")
    verifier_status = run_data.get("verifier_status")
    metrics = {
        metric.name: _coerce_numeric(_get_path_value(verifier_payload, metric.path))
        for metric in item.benchmark_profile.score_metrics
    }
    flags = {
        metric.name: (
            value if isinstance(value := _get_path_value(verifier_payload, metric.path), bool) else None
        )
        for metric in item.benchmark_profile.flag_metrics
    }

    return {
        "config_name": item.config_name,
        "benchmark": item.benchmark,
        "harness": item.harness,
        "split": item.split,
        "case_id": item.case_id,
        "result_path": _relative_display(family_plan.run_output_dir(item)),
        "artifact_state": "present",
        "mode": run_data.get("mode", "batch"),
        "overall_status": overall_status if isinstance(overall_status, str) else "unknown",
        "agent_status": agent_status if isinstance(agent_status, str) else "unknown",
        "verifier_status": verifier_status if isinstance(verifier_status, str) else "unknown",
        "valid": _normalize_valid(
            verifier_payload,
            verifier_status if isinstance(verifier_status, str) else "unknown",
        ),
        "duration_seconds": run_data.get("duration_seconds")
        if _is_numeric(run_data.get("duration_seconds"))
        else None,
        "start_time": run_data.get("start_time")
        if isinstance(run_data.get("start_time"), str)
        else None,
        "end_time": run_data.get("end_time") if isinstance(run_data.get("end_time"), str) else None,
        "metrics": metrics,
        "flags": flags,
        "raw_verifier": verifier_payload,
    }


def _load_expected_records(plan: family_plan.BatchPlan) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in plan.items:
        run_json_path = family_plan.run_output_dir(item) / "run.json"
        if not run_json_path.exists():
            records.append(_build_missing_record(item))
            continue
        run_data = _read_run_json(run_json_path)
        if run_data is None:
            records.append(_build_malformed_record(item))
            continue
        records.append(_normalize_run_record(item, run_data))
    return records


def _status_counts(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter = Counter(str(record.get(key, "unknown")) for record in records)
    return dict(sorted(counter.items()))


def _flag_counts(records: list[dict[str, Any]], metric_name: str) -> dict[str, int]:
    true_count = 0
    false_count = 0
    null_count = 0
    for record in records:
        value = record["flags"].get(metric_name)
        if value is True:
            true_count += 1
        elif value is False:
            false_count += 1
        else:
            null_count += 1
    return {
        "true_count": true_count,
        "false_count": false_count,
        "null_count": null_count,
    }


def _primary_metric(profile: family_plan.BenchmarkProfile) -> family_plan.MetricSpec | None:
    for metric in profile.score_metrics:
        if metric.role == "primary":
            return metric
    return None


def _secondary_metrics(profile: family_plan.BenchmarkProfile) -> tuple[family_plan.MetricSpec, ...]:
    return tuple(metric for metric in profile.score_metrics if metric.role == "secondary")


def _metric_values(records: list[dict[str, Any]], metric_name: str) -> list[int | float]:
    values: list[int | float] = []
    for record in records:
        if record["valid"] is not True:
            continue
        value = record["metrics"].get(metric_name)
        if _is_numeric(value):
            values.append(value)
    return values


def _build_group_summary(
    *,
    records: list[dict[str, Any]],
    profile: family_plan.BenchmarkProfile,
    benchmark: str,
    harness: str | None = None,
) -> dict[str, Any]:
    expected_runs = len(records)
    present_runs = sum(1 for record in records if record["artifact_state"] == "present")
    missing_runs = sum(1 for record in records if record["artifact_state"] == "missing_artifact")
    malformed_runs = sum(
        1 for record in records if record["artifact_state"] == "malformed_artifact"
    )
    primary_metric = _primary_metric(profile)
    secondary_metrics = _secondary_metrics(profile)
    primary_stats = (
        _metric_stats(_metric_values(records, primary_metric.name)) if primary_metric else None
    )
    secondary_stats = {
        metric.name: _metric_stats(_metric_values(records, metric.name))
        for metric in secondary_metrics
    }
    flag_counts = {
        metric.name: _flag_counts(records, metric.name) for metric in profile.flag_metrics
    }

    summary = {
        "benchmark": benchmark,
        "expected_runs": expected_runs,
        "present_runs": present_runs,
        "missing_runs": missing_runs,
        "malformed_runs": malformed_runs,
        "overall_status_counts": _status_counts(records, "overall_status"),
        "agent_status_counts": _status_counts(records, "agent_status"),
        "verifier_status_counts": _status_counts(records, "verifier_status"),
        "valid_count": sum(1 for record in records if record["valid"] is True),
        "invalid_count": sum(1 for record in records if record["valid"] is False),
        "primary_metric": (
            {
                "name": primary_metric.name,
                "path": primary_metric.path,
                "direction": primary_metric.direction,
                "stats": primary_stats,
            }
            if primary_metric is not None
            else None
        ),
        "secondary_metrics": {
            metric.name: {
                "path": metric.path,
                "direction": metric.direction,
                "stats": secondary_stats[metric.name],
            }
            for metric in secondary_metrics
        },
        "flag_metrics": flag_counts,
    }
    if harness is not None:
        summary["harness"] = harness
    return summary


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    _ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _matrix_summary_markdown(
    *,
    generated_at: str,
    config_name: str,
    config_path: Path,
    expected_runs: int,
    present_runs: int,
    missing_runs: int,
    malformed_runs: int,
    benchmark_harness_rows: list[dict[str, Any]],
) -> str:
    lines = [
        "# Main Agentic Matrix Summary",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Config: `{_relative_display(config_path)}`",
        f"- Config name: `{config_name}`",
        f"- Expected runs: `{expected_runs}`",
        f"- Present runs: `{present_runs}`",
        f"- Missing runs: `{missing_runs}`",
        f"- Malformed runs: `{malformed_runs}`",
        "",
        "| Benchmark | Harness | Expected | Present | Missing | Success | Valid | Invalid | Timeout | No Solution | Verifier Error | Primary Metric |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in benchmark_harness_rows:
        primary_metric_text = (
            f"{row['primary_metric_name']}: n={row['primary_metric_count']}, "
            f"mean={_format_stat(row['primary_metric_mean'])}"
            if row["primary_metric_name"]
            else "-"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["benchmark"]),
                    str(row["harness"]),
                    str(row["expected_runs"]),
                    str(row["present_runs"]),
                    str(row["missing_runs"]),
                    str(row["success_count"]),
                    str(row["valid_count"]),
                    str(row["invalid_count"]),
                    str(row["timeout_count"]),
                    str(row["no_solution_count"]),
                    str(row["verifier_error_count"]),
                    primary_metric_text,
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.resolve()
    mode = _load_config_mode(config_path)
    if mode != "batch":
        raise SystemExit(
            f"Interactive aggregation is not supported in Phase 6. Expected batch config, found mode '{mode}': {config_path}"
        )

    plan = family_plan.build_batch_plan(
        config_path=config_path,
        benchmark_filters=(),
        harness_filters=(),
        require_real_configs=False,
    )
    records = _load_expected_records(plan)
    generated_at = _utc_now_iso()
    summaries_root = (
        plan.config.results.root / plan.config.config_path.stem / plan.config.results.aggregate_dir
    )
    benchmark_harness_rows: list[dict[str, Any]] = []
    benchmark_json_summaries: dict[str, Any] = {}

    for benchmark in plan.selected_benchmarks:
        benchmark_profile = next(
            item.benchmark_profile for item in plan.items if item.benchmark == benchmark
        )
        benchmark_records = [record for record in records if record["benchmark"] == benchmark]
        per_harness: dict[str, Any] = {}
        for harness in plan.selected_harnesses:
            harness_records = [
                record
                for record in benchmark_records
                if record["harness"] == harness
            ]
            harness_summary = _build_group_summary(
                records=harness_records,
                profile=benchmark_profile,
                benchmark=benchmark,
                harness=harness,
            )
            per_harness[harness] = harness_summary
            primary_metric = harness_summary["primary_metric"] or {}
            benchmark_harness_rows.append(
                {
                    "config_name": plan.config.config_path.stem,
                    "benchmark": benchmark,
                    "harness": harness,
                    "expected_runs": harness_summary["expected_runs"],
                    "present_runs": harness_summary["present_runs"],
                    "missing_runs": harness_summary["missing_runs"],
                    "malformed_runs": harness_summary["malformed_runs"],
                    "success_count": harness_summary["overall_status_counts"].get("success", 0),
                    "valid_count": harness_summary["valid_count"],
                    "invalid_count": harness_summary["invalid_count"],
                    "timeout_count": harness_summary["overall_status_counts"].get("timeout", 0),
                    "no_solution_count": harness_summary["verifier_status_counts"].get("no_solution", 0),
                    "verifier_error_count": harness_summary["verifier_status_counts"].get("error", 0),
                    "primary_metric_name": primary_metric.get("name"),
                    "primary_metric_direction": primary_metric.get("direction"),
                    "primary_metric_count": (primary_metric.get("stats") or {}).get("count"),
                    "primary_metric_mean": (primary_metric.get("stats") or {}).get("mean"),
                    "primary_metric_median": (primary_metric.get("stats") or {}).get("median"),
                    "primary_metric_min": (primary_metric.get("stats") or {}).get("min"),
                    "primary_metric_max": (primary_metric.get("stats") or {}).get("max"),
                    "secondary_metric_stats_json": json.dumps(
                        harness_summary["secondary_metrics"], sort_keys=True
                    ),
                    "flag_metric_counts_json": json.dumps(
                        harness_summary["flag_metrics"], sort_keys=True
                    ),
                    "overall_status_counts_json": json.dumps(
                        harness_summary["overall_status_counts"], sort_keys=True
                    ),
                    "agent_status_counts_json": json.dumps(
                        harness_summary["agent_status_counts"], sort_keys=True
                    ),
                    "verifier_status_counts_json": json.dumps(
                        harness_summary["verifier_status_counts"], sort_keys=True
                    ),
                }
            )

        benchmark_summary = _build_group_summary(
            records=benchmark_records,
            profile=benchmark_profile,
            benchmark=benchmark,
        )
        benchmark_summary_payload = {
            "summary_version": SUMMARY_VERSION,
            "generated_at": generated_at,
            "config_name": plan.config.config_path.stem,
            "config_path": _relative_display(plan.config.config_path),
            **benchmark_summary,
            "harnesses": per_harness,
            "runs": benchmark_records,
        }
        benchmark_json_summaries[benchmark] = {
            key: value for key, value in benchmark_summary_payload.items() if key != "runs"
        }
        _write_json(summaries_root / "benchmarks" / f"{benchmark}.json", benchmark_summary_payload)

        metric_fieldnames = [metric.name for metric in benchmark_profile.score_metrics]
        flag_fieldnames = [metric.name for metric in benchmark_profile.flag_metrics]
        benchmark_csv_rows = []
        for record in benchmark_records:
            row = {
                "config_name": record["config_name"],
                "benchmark": record["benchmark"],
                "harness": record["harness"],
                "split": record["split"],
                "case_id": record["case_id"],
                "result_path": record["result_path"],
                "artifact_state": record["artifact_state"],
                "mode": record["mode"],
                "overall_status": record["overall_status"],
                "agent_status": record["agent_status"],
                "verifier_status": record["verifier_status"],
                "valid": record["valid"],
                "duration_seconds": record["duration_seconds"],
                "start_time": record["start_time"],
                "end_time": record["end_time"],
            }
            for name in metric_fieldnames:
                row[name] = record["metrics"].get(name)
            for name in flag_fieldnames:
                row[name] = record["flags"].get(name)
            benchmark_csv_rows.append(row)
        _write_csv(
            summaries_root / "benchmarks" / f"{benchmark}.csv",
            benchmark_csv_rows,
            [
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
                *metric_fieldnames,
                *flag_fieldnames,
            ],
        )

    matrix_summary = {
        "summary_version": SUMMARY_VERSION,
        "generated_at": generated_at,
        "config_name": plan.config.config_path.stem,
        "config_path": _relative_display(plan.config.config_path),
        "expected_runs": len(records),
        "present_runs": sum(1 for record in records if record["artifact_state"] == "present"),
        "missing_runs": sum(
            1 for record in records if record["artifact_state"] == "missing_artifact"
        ),
        "malformed_runs": sum(
            1 for record in records if record["artifact_state"] == "malformed_artifact"
        ),
        "overall_status_counts": _status_counts(records, "overall_status"),
        "agent_status_counts": _status_counts(records, "agent_status"),
        "verifier_status_counts": _status_counts(records, "verifier_status"),
        "benchmarks": benchmark_json_summaries,
    }

    _write_json(summaries_root / "matrix_summary.json", matrix_summary)
    _write_text(
        summaries_root / "matrix_summary.md",
        _matrix_summary_markdown(
            generated_at=generated_at,
            config_name=plan.config.config_path.stem,
            config_path=plan.config.config_path,
            expected_runs=matrix_summary["expected_runs"],
            present_runs=matrix_summary["present_runs"],
            missing_runs=matrix_summary["missing_runs"],
            malformed_runs=matrix_summary["malformed_runs"],
            benchmark_harness_rows=benchmark_harness_rows,
        ),
    )
    _write_csv(
        summaries_root / "benchmark_harness_summary.csv",
        benchmark_harness_rows,
        [
            "config_name",
            "benchmark",
            "harness",
            "expected_runs",
            "present_runs",
            "missing_runs",
            "malformed_runs",
            "success_count",
            "valid_count",
            "invalid_count",
            "timeout_count",
            "no_solution_count",
            "verifier_error_count",
            "primary_metric_name",
            "primary_metric_direction",
            "primary_metric_count",
            "primary_metric_mean",
            "primary_metric_median",
            "primary_metric_min",
            "primary_metric_max",
            "secondary_metric_stats_json",
            "flag_metric_counts_json",
            "overall_status_counts_json",
            "agent_status_counts_json",
            "verifier_status_counts_json",
        ],
    )

    print(f"Summaries written to {summaries_root}")
    return 0


def _write_text(path: Path, content: str) -> None:
    _ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
