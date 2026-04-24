#!/usr/bin/env python3
"""Aggregate temporal robustness run artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
METRICS = ("WCR", "CR", "TAT", "PC")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate temporal robustness artifacts")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser.parse_args(argv)


def _load_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Config must be a mapping: {path}")
    return data


def _repo_path(path_text: str) -> Path:
    path = Path(path_text)
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def _result_root(config: dict[str, Any], path: Path) -> Path:
    results = config.get("results")
    if not isinstance(results, dict) or not isinstance(results.get("root"), str):
        raise SystemExit(f"Config must define results.root: {path}")
    return _repo_path(results["root"])


def _aggregate_dir(config: dict[str, Any], path: Path) -> Path:
    results = config.get("results")
    if not isinstance(results, dict):
        raise SystemExit(f"Config must define results: {path}")
    root = _result_root(config, path)
    aggregate_dir = results.get("aggregate_dir", "summaries")
    if not isinstance(aggregate_dir, str):
        raise SystemExit(f"results.aggregate_dir must be a string: {path}")
    candidate = Path(aggregate_dir)
    return candidate.resolve() if candidate.is_absolute() else root / candidate


def _display_path(path: Path) -> str:
    if path.is_relative_to(REPO_ROOT):
        return path.relative_to(REPO_ROOT).as_posix()
    return path.as_posix()


def _read_run_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _metric(payload: dict[str, Any], name: str) -> float | None:
    verifier = payload.get("verifier")
    if not isinstance(verifier, dict):
        return None
    metrics = verifier.get("metrics")
    if not isinstance(metrics, dict):
        return None
    value = metrics.get(name)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _format(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.8g}"
    return str(value)


def _run_path(
    root: Path,
    config_name: str,
    *,
    split: str,
    benchmark: str,
    harness: str,
    case_id: str,
) -> Path:
    return root / config_name / split / benchmark / harness / case_id / "run.json"


def _records(config: dict[str, Any], config_path: Path) -> list[dict[str, Any]]:
    root = _result_root(config, config_path)
    benchmark = config.get("benchmark")
    splits = config.get("splits", [])
    harnesses = config.get("harnesses", [])
    cases = config.get("cases", [])
    if not isinstance(benchmark, str):
        raise SystemExit("Config benchmark must be a string")
    if not all(isinstance(value, list) for value in (splits, harnesses, cases)):
        raise SystemExit("Config splits, harnesses, and cases must be lists")

    rows: list[dict[str, Any]] = []
    for split in splits:
        for harness in harnesses:
            for case_id in cases:
                run_path = _run_path(
                    root,
                    config_path.stem,
                    split=str(split),
                    benchmark=benchmark,
                    harness=str(harness),
                    case_id=str(case_id),
                )
                payload = _read_run_json(run_path)
                row: dict[str, Any] = {
                    "split": split,
                    "benchmark": benchmark,
                    "harness": harness,
                    "case_id": case_id,
                    "result_path": _display_path(run_path),
                }
                if payload is None:
                    row.update(
                        {
                            "artifact_state": "missing_or_malformed",
                            "overall_status": "missing_artifact",
                            "agent_status": "missing_artifact",
                            "verifier_status": "missing_artifact",
                            "valid": None,
                            "duration_seconds": None,
                        }
                    )
                    for metric in METRICS:
                        row[metric] = None
                    rows.append(row)
                    continue
                verifier = payload.get("verifier") if isinstance(payload.get("verifier"), dict) else {}
                row.update(
                    {
                        "artifact_state": "present",
                        "overall_status": payload.get("overall_status", "unknown"),
                        "agent_status": payload.get("agent_status", "unknown"),
                        "verifier_status": payload.get("verifier_status", "unknown"),
                        "valid": verifier.get("valid") if isinstance(verifier.get("valid"), bool) else None,
                        "duration_seconds": payload.get("duration_seconds")
                        if isinstance(payload.get("duration_seconds"), (int, float))
                        and not isinstance(payload.get("duration_seconds"), bool)
                        else None,
                    }
                )
                for metric in METRICS:
                    row[metric] = _metric(payload, metric)
                rows.append(row)
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_split: dict[str, Any] = {}
    by_harness: dict[str, Any] = {}
    for split in sorted({str(row["split"]) for row in rows}):
        split_rows = [row for row in rows if row["split"] == split]
        by_split[split] = _group_summary(split_rows)
    for harness in sorted({str(row["harness"]) for row in rows}):
        harness_rows = [row for row in rows if row["harness"] == harness]
        by_harness[harness] = _group_summary(harness_rows)
    return {
        "schema_version": 1,
        "experiment": "temporal_robustness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "by_split": by_split,
        "by_harness": by_harness,
    }


def _group_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid_values = [row["valid"] for row in rows if isinstance(row["valid"], bool)]
    metric_means = {
        f"mean_{metric}": _mean([row[metric] for row in rows if isinstance(row.get(metric), float)])
        for metric in METRICS
    }
    return {
        "run_count": len(rows),
        "valid_count": sum(1 for value in valid_values if value),
        "valid_rate": (sum(1 for value in valid_values if value) / len(valid_values)) if valid_values else None,
        "overall_status_counts": dict(Counter(str(row["overall_status"]) for row in rows)),
        "verifier_status_counts": dict(Counter(str(row["verifier_status"]) for row in rows)),
        **metric_means,
    }


def _paired_deltas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {
        (str(row["harness"]), str(row["split"]), str(row["case_id"])): row
        for row in rows
    }
    harnesses = sorted({str(row["harness"]) for row in rows})
    case_ids = sorted({str(row["case_id"]) for row in rows})
    deltas: list[dict[str, Any]] = []
    for harness in harnesses:
        for case_id in case_ids:
            baseline = by_key.get((harness, "test", case_id))
            shifted = by_key.get((harness, "test_horizon_2022", case_id))
            row: dict[str, Any] = {
                "harness": harness,
                "case_id": case_id,
                "baseline_status": baseline.get("overall_status") if baseline else "missing_artifact",
                "shifted_status": shifted.get("overall_status") if shifted else "missing_artifact",
            }
            for metric in METRICS:
                baseline_value = baseline.get(metric) if baseline else None
                shifted_value = shifted.get(metric) if shifted else None
                row[f"baseline_{metric}"] = baseline_value
                row[f"shifted_{metric}"] = shifted_value
                row[f"delta_{metric}"] = (
                    shifted_value - baseline_value
                    if isinstance(baseline_value, float) and isinstance(shifted_value, float)
                    else None
                )
            deltas.append(row)
    return deltas


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _format(row.get(key)) for key in fieldnames})


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.resolve()
    config = _load_config(config_path)
    rows = _records(config, config_path)
    summary = _summary(rows)
    deltas = _paired_deltas(rows)
    aggregate_dir = _aggregate_dir(config, config_path)
    aggregate_dir.mkdir(parents=True, exist_ok=True)
    (aggregate_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    run_fields = [
        "split",
        "benchmark",
        "harness",
        "case_id",
        "artifact_state",
        "overall_status",
        "agent_status",
        "verifier_status",
        "valid",
        "duration_seconds",
        *METRICS,
        "result_path",
    ]
    delta_fields = ["harness", "case_id", "baseline_status", "shifted_status"]
    for metric in METRICS:
        delta_fields.extend([f"baseline_{metric}", f"shifted_{metric}", f"delta_{metric}"])
    _write_csv(aggregate_dir / "runs.csv", rows, run_fields)
    _write_csv(aggregate_dir / "paired_deltas.csv", deltas, delta_fields)
    print(f"Wrote {_display_path(aggregate_dir / 'summary.json')}")
    print(f"Wrote {_display_path(aggregate_dir / 'runs.csv')}")
    print(f"Wrote {_display_path(aggregate_dir / 'paired_deltas.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
