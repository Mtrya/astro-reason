#!/usr/bin/env python3
"""Aggregate verifier-exposure ablation artifacts."""

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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate verifier-exposure run artifacts")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser.parse_args(argv)


def _load_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Config must be a mapping: {path}")
    return data


def _repo_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


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
    candidate = _repo_path(aggregate_dir)
    return candidate if candidate.is_relative_to(root) else root / aggregate_dir


def _run_path(
    root: Path,
    config_name: str,
    *,
    exposure: str,
    benchmark: str,
    harness: str,
    split: str,
    case_id: str,
) -> Path:
    return root / config_name / exposure / benchmark / harness / split / case_id / "run.json"


def _read_run_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _metric(payload: dict[str, Any], key: str) -> float | None:
    verifier = payload.get("verifier")
    if not isinstance(verifier, dict):
        return None
    metrics = verifier.get("metrics")
    if not isinstance(metrics, dict):
        return None
    value = metrics.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _format(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _display_path(path: Path) -> str:
    if path.is_relative_to(REPO_ROOT):
        return path.relative_to(REPO_ROOT).as_posix()
    return path.as_posix()


def _records(config: dict[str, Any], config_path: Path) -> list[dict[str, Any]]:
    root = _result_root(config, config_path)
    exposures = config.get("exposures", [])
    cases = config.get("cases", [])
    benchmark = config.get("benchmark")
    harnesses = config.get("harnesses", [])
    split = config.get("split")
    if not isinstance(exposures, list) or not isinstance(cases, list):
        raise SystemExit("Config exposures and cases must be lists")
    if not isinstance(harnesses, list):
        raise SystemExit("Config harnesses must be a list")
    if not isinstance(benchmark, str) or not isinstance(split, str):
        raise SystemExit("Config benchmark and split must be strings")
    rows: list[dict[str, Any]] = []
    for exposure in exposures:
        for harness in harnesses:
            for case_id in cases:
                run_path = _run_path(
                    root,
                    config_path.stem,
                    exposure=str(exposure),
                    benchmark=benchmark,
                    harness=str(harness),
                    split=split,
                    case_id=str(case_id),
                )
                payload = _read_run_json(run_path)
                if payload is None:
                    rows.append(
                        {
                            "exposure": exposure,
                            "harness": harness,
                            "case_id": case_id,
                            "artifact_state": "missing_or_malformed",
                            "overall_status": "missing_artifact",
                            "agent_status": "missing_artifact",
                            "verifier_status": "missing_artifact",
                            "valid": None,
                            "service_fraction": None,
                            "worst_demand_service_fraction": None,
                            "mean_latency_ms": None,
                            "latency_p95_ms": None,
                            "result_path": _display_path(run_path),
                        }
                    )
                    continue
                verifier = payload.get("verifier") if isinstance(payload.get("verifier"), dict) else {}
                rows.append(
                    {
                        "exposure": payload.get("exposure", exposure),
                        "harness": payload.get("harness", harness),
                        "case_id": payload.get("case_id", case_id),
                        "artifact_state": "present",
                        "overall_status": payload.get("overall_status", "unknown"),
                        "agent_status": payload.get("agent_status", "unknown"),
                        "verifier_status": payload.get("verifier_status", "unknown"),
                        "valid": verifier.get("valid") if isinstance(verifier.get("valid"), bool) else None,
                        "service_fraction": _metric(payload, "service_fraction"),
                        "worst_demand_service_fraction": _metric(payload, "worst_demand_service_fraction"),
                        "mean_latency_ms": _metric(payload, "mean_latency_ms"),
                        "latency_p95_ms": _metric(payload, "latency_p95_ms"),
                        "result_path": _display_path(run_path),
                    }
                )
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exposures = sorted({str(row["exposure"]) for row in rows})
    by_exposure: dict[str, Any] = {}
    for exposure in exposures:
        exposure_rows = [row for row in rows if row["exposure"] == exposure]
        valid_values = [row["valid"] for row in exposure_rows if isinstance(row["valid"], bool)]
        by_exposure[exposure] = {
            "run_count": len(exposure_rows),
            "valid_count": sum(1 for value in valid_values if value),
            "valid_rate": (sum(1 for value in valid_values if value) / len(valid_values)) if valid_values else None,
            "overall_status_counts": dict(Counter(str(row["overall_status"]) for row in exposure_rows)),
            "verifier_status_counts": dict(Counter(str(row["verifier_status"]) for row in exposure_rows)),
            "mean_service_fraction": _mean(
                [row["service_fraction"] for row in exposure_rows if isinstance(row["service_fraction"], float)]
            ),
            "mean_worst_demand_service_fraction": _mean(
                [
                    row["worst_demand_service_fraction"]
                    for row in exposure_rows
                    if isinstance(row["worst_demand_service_fraction"], float)
                ]
            ),
            "mean_latency_ms": _mean(
                [row["mean_latency_ms"] for row in exposure_rows if isinstance(row["mean_latency_ms"], float)]
            ),
        }
    by_exposure_harness: dict[str, Any] = {}
    for exposure in exposures:
        for harness in sorted({str(row["harness"]) for row in rows if row["exposure"] == exposure}):
            group_rows = [row for row in rows if row["exposure"] == exposure and row["harness"] == harness]
            valid_values = [row["valid"] for row in group_rows if isinstance(row["valid"], bool)]
            by_exposure_harness[f"{exposure}/{harness}"] = {
                "run_count": len(group_rows),
                "valid_count": sum(1 for value in valid_values if value),
                "valid_rate": (sum(1 for value in valid_values if value) / len(valid_values)) if valid_values else None,
                "overall_status_counts": dict(Counter(str(row["overall_status"]) for row in group_rows)),
                "mean_service_fraction": _mean(
                    [row["service_fraction"] for row in group_rows if isinstance(row["service_fraction"], float)]
                ),
                "mean_worst_demand_service_fraction": _mean(
                    [
                        row["worst_demand_service_fraction"]
                        for row in group_rows
                        if isinstance(row["worst_demand_service_fraction"], float)
                    ]
                ),
            }
    return {
        "schema_version": 1,
        "experiment": "verifier_exposure",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "by_exposure": by_exposure,
        "by_exposure_harness": by_exposure_harness,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "exposure",
        "harness",
        "case_id",
        "artifact_state",
        "overall_status",
        "agent_status",
        "verifier_status",
        "valid",
        "service_fraction",
        "worst_demand_service_fraction",
        "mean_latency_ms",
        "latency_p95_ms",
        "result_path",
    ]
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
    aggregate_dir = _aggregate_dir(config, config_path)
    rows = _records(config, config_path)
    summary = _summary(rows)
    aggregate_dir.mkdir(parents=True, exist_ok=True)
    (aggregate_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(aggregate_dir / "runs.csv", rows)
    print(f"Wrote {aggregate_dir / 'summary.json'}")
    print(f"Wrote {aggregate_dir / 'runs.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
