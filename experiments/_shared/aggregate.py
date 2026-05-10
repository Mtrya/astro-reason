"""Shared helpers for experiment aggregate scripts."""

from __future__ import annotations

import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


def read_run_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def get_path_value(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def normalize_valid(verifier_payload: dict[str, Any], verifier_status: str) -> bool | None:
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


def is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def coerce_numeric(value: Any) -> int | float | None:
    if not is_numeric(value):
        return None
    if isinstance(value, int):
        return value
    return float(value)


def metric_stats(values: list[int | float]) -> dict[str, Any]:
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


def format_stat(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def status_counts(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter = Counter(str(record.get(key, "unknown")) for record in records)
    return dict(sorted(counter.items()))


def flag_counts(records: list[dict[str, Any]], metric_name: str) -> dict[str, int]:
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


def primary_metric(profile: Any) -> Any | None:
    for metric in profile.score_metrics:
        if metric.role == "primary":
            return metric
    return None


def secondary_metrics(profile: Any) -> tuple[Any, ...]:
    return tuple(metric for metric in profile.score_metrics if metric.role == "secondary")


def metric_values(records: list[dict[str, Any]], metric_name: str) -> list[int | float]:
    values: list[int | float] = []
    for record in records:
        if record["valid"] is not True:
            continue
        value = record["metrics"].get(metric_name)
        if is_numeric(value):
            values.append(value)
    return values


def processed_metric_names(records: list[dict[str, Any]]) -> tuple[str, ...]:
    names: set[str] = set()
    for record in records:
        processed_metrics = record.get("processed_metrics")
        if not isinstance(processed_metrics, dict):
            continue
        names.update(str(name) for name in processed_metrics)
    return tuple(sorted(names))


def processed_metric_values(records: list[dict[str, Any]], metric_name: str) -> list[int | float]:
    values: list[int | float] = []
    for record in records:
        value = record["processed_metrics"].get(metric_name)
        if is_numeric(value):
            values.append(value)
    return values


def build_group_summary(
    *,
    records: list[dict[str, Any]],
    profile: Any,
    benchmark: str,
    harness: str | None = None,
) -> dict[str, Any]:
    expected_runs = len(records)
    present_runs = sum(1 for record in records if record["artifact_state"] == "present")
    missing_runs = sum(1 for record in records if record["artifact_state"] == "missing_artifact")
    malformed_runs = sum(
        1 for record in records if record["artifact_state"] == "malformed_artifact"
    )
    primary = primary_metric(profile)
    secondary = secondary_metrics(profile)
    primary_stats = metric_stats(metric_values(records, primary.name)) if primary else None
    secondary_stats = {
        metric.name: metric_stats(metric_values(records, metric.name))
        for metric in secondary
    }
    processed_metric_stats = {
        metric_name: metric_stats(processed_metric_values(records, metric_name))
        for metric_name in processed_metric_names(records)
    }
    flags = {metric.name: flag_counts(records, metric.name) for metric in profile.flag_metrics}

    summary = {
        "benchmark": benchmark,
        "expected_runs": expected_runs,
        "present_runs": present_runs,
        "missing_runs": missing_runs,
        "malformed_runs": malformed_runs,
        "overall_status_counts": status_counts(records, "overall_status"),
        "agent_status_counts": status_counts(records, "agent_status"),
        "verifier_status_counts": status_counts(records, "verifier_status"),
        "valid_count": sum(1 for record in records if record["valid"] is True),
        "invalid_count": sum(1 for record in records if record["valid"] is False),
        "primary_metric": (
            {
                "name": primary.name,
                "path": primary.path,
                "direction": primary.direction,
                "stats": primary_stats,
            }
            if primary is not None
            else None
        ),
        "secondary_metrics": {
            metric.name: {
                "path": metric.path,
                "direction": metric.direction,
                "stats": secondary_stats[metric.name],
            }
            for metric in secondary
        },
        "processed_metrics": {
            metric_name: {
                "direction": "maximize",
                "stats": stats,
            }
            for metric_name, stats in processed_metric_stats.items()
        },
        "flag_metrics": flags,
    }
    if harness is not None:
        summary["harness"] = harness
    return summary


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")
