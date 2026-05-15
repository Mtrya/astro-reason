#!/usr/bin/env python3
"""Aggregate memory-accumulation held-out evaluation artifacts."""

from __future__ import annotations

import argparse
import csv
import functools
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run as family_run  # type: ignore[no-redef]
else:
    from . import run as family_run

from experiments._shared import aggregate as shared_aggregate
from experiments._shared import main_solver_baselines
from experiments._shared import score_normalization as score_norm


DEFAULT_CONFIG = Path(__file__).resolve().parent / "configs" / "default.yaml"
DEFAULT_MAIN_AGENTIC_ROOT = REPO_ROOT / "results" / "agent_runs" / "experiments" / "main_agentic" / "matrix"

METRIC_FIELDS = (
    "coverage_ratio",
    "weighted_coverage_ratio",
    "num_actions",
    "min_battery_wh",
    "service_fraction",
    "worst_demand_service_fraction",
    "num_added_satellites",
    "mean_latency_ms",
    "latency_p95_ms",
    "score_hours",
    "n_satisfied_requests",
    "u_rms",
    "u_max",
    "n_tracks",
    "normalized_score_pct",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate memory-accumulation artifacts.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--main-agentic-root", type=Path, default=DEFAULT_MAIN_AGENTIC_ROOT)
    return parser.parse_args(argv)


def _display_path(path: Path) -> str:
    if path.is_relative_to(REPO_ROOT):
        return path.relative_to(REPO_ROOT).as_posix()
    return path.as_posix()


def _artifact_state(path: Path) -> str:
    if not path.exists():
        return "missing_artifact"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "malformed_artifact"
    return "present" if isinstance(data, dict) else "malformed_artifact"


def _run_path(
    config: family_run.FamilyConfig,
    *,
    memory_source: str,
    benchmark: str,
    harness: str,
    split: str,
    case_id: str,
) -> Path:
    return (
        config.results.root
        / config.config_path.stem
        / "eval"
        / config.condition
        / memory_source
        / benchmark
        / harness
        / split
        / case_id
        / "run.json"
    )


def _main_agentic_run_path(
    root: Path,
    *,
    benchmark: str,
    harness: str,
    split: str,
    case_id: str,
) -> Path:
    return root / benchmark / harness / split / case_id / "run.json"


def _metric_from_mapping(metrics: dict[str, Any], key: str) -> float | None:
    value = shared_aggregate.coerce_numeric(metrics.get(key))
    return float(value) if value is not None else None


def _metrics_from_mapping(metrics: dict[str, Any]) -> dict[str, float | None]:
    return {field: _metric_from_mapping(metrics, field) for field in METRIC_FIELDS if field != "normalized_score_pct"}


def _case_dir(*, benchmark: str, split: str, case_id: str) -> Path:
    return REPO_ROOT / "benchmarks" / benchmark / "dataset" / "cases" / split / case_id


def _load_json_file(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _satellite_resource_models(path: Path) -> list[dict[str, object]]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    raw_satellites = data.get("satellites", data) if isinstance(data, dict) else data
    if not isinstance(raw_satellites, list):
        return []
    models: list[dict[str, object]] = []
    for satellite in raw_satellites:
        if not isinstance(satellite, dict):
            continue
        resource_model = satellite.get("resource_model")
        if isinstance(resource_model, dict):
            models.append(resource_model)
            continue
        power_model = satellite.get("power")
        if isinstance(power_model, dict):
            models.append(power_model)
    return models


def _satellite_battery_capacities(path: Path) -> list[float]:
    capacities: list[float] = []
    for resource_model in _satellite_resource_models(path):
        capacity = score_norm.to_float(resource_model.get("battery_capacity_wh"))
        if capacity is not None:
            capacities.append(capacity)
    return capacities


def _nested_number(payload: dict[str, object], path: tuple[str, ...]) -> float | None:
    current: object = payload
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return score_norm.to_float(current)


@functools.lru_cache(maxsize=None)
def _regional_case_constants(split: str, case_id: str) -> dict[str, float]:
    case_dir = _case_dir(benchmark="regional_coverage", split=split, case_id=case_id)
    manifest = _load_json_file(case_dir / "manifest.json") or {}
    max_actions = _nested_number(manifest, ("scoring", "max_actions_total"))
    battery_capacities = _satellite_battery_capacities(case_dir / "satellites.yaml")
    constants: dict[str, float] = {}
    if max_actions is not None:
        constants["max_actions_total"] = max_actions
    if battery_capacities:
        constants["battery_capacity_wh"] = max(battery_capacities)
    return constants


@functools.lru_cache(maxsize=None)
def _relay_case_constants(split: str, case_id: str) -> dict[str, float]:
    case_dir = _case_dir(benchmark="relay_constellation", split=split, case_id=case_id)
    manifest = _load_json_file(case_dir / "manifest.json") or {}
    max_added = _nested_number(manifest, ("constraints", "max_added_satellites"))
    return {"max_added_satellites": max_added} if max_added is not None else {}


def _normalized_score_pct(
    *,
    benchmark: str,
    split: str,
    case_id: str,
    valid: bool | None,
    metrics: dict[str, Any],
    baseline_data: dict[str, Any],
) -> float | None:
    if valid is not True:
        return 0.0 if valid is False else None
    normalization = baseline_data.get("normalization")
    config = normalization.get(benchmark) if isinstance(normalization, dict) else {}
    config = config if isinstance(config, dict) else {}
    if benchmark == "regional_coverage":
        constants = _regional_case_constants(split, case_id)
        return score_norm.regional_coverage_score_pct(
            weighted_coverage_ratio=metrics.get("weighted_coverage_ratio"),
            coverage_ratio=metrics.get("coverage_ratio"),
            num_actions=metrics.get("num_actions"),
            min_battery_wh=metrics.get("min_battery_wh"),
            max_actions_total=constants.get("max_actions_total"),
            battery_capacity_wh=constants.get("battery_capacity_wh"),
        )
    if benchmark == "relay_constellation":
        constants = _relay_case_constants(split, case_id)
        return score_norm.relay_constellation_score_pct(
            service_fraction=metrics.get("service_fraction"),
            worst_demand_service_fraction=metrics.get("worst_demand_service_fraction"),
            num_added_satellites=metrics.get("num_added_satellites"),
            mean_latency_ms=metrics.get("mean_latency_ms"),
            latency_p95_ms=metrics.get("latency_p95_ms"),
            min_added_satellites=config.get("min_added_satellites"),
            max_added_satellites=constants.get("max_added_satellites"),
            latency_cap_ms=config.get("latency_cap_ms"),
        )
    if benchmark == "satnet":
        return score_norm.satnet_score_pct(
            u_rms=metrics.get("u_rms"),
            u_max=metrics.get("u_max"),
            u_rms_cap=config.get("u_rms_cap"),
            u_max_cap=config.get("u_max_cap"),
        )
    return None


def _missing_row(
    *,
    benchmark: str,
    split: str,
    condition: str,
    memory_source: str,
    harness: str,
    case_id: str,
    run_path: Path,
    source_experiment: str,
    artifact_state: str,
) -> dict[str, Any]:
    return {
        "benchmark": benchmark,
        "split": split,
        "condition": condition,
        "memory_source": memory_source,
        "harness": harness,
        "case_id": case_id,
        "artifact_state": artifact_state,
        "source_experiment": source_experiment,
        "overall_status": artifact_state,
        "agent_status": artifact_state,
        "verifier_status": artifact_state,
        "valid": None,
        "duration_seconds": None,
        **{field: 0.0 if field == "normalized_score_pct" else None for field in METRIC_FIELDS},
        "result_path": _display_path(run_path),
    }


def _agent_row(
    *,
    benchmark: str,
    split: str,
    condition: str,
    memory_source: str,
    harness: str,
    case_id: str,
    run_path: Path,
    source_experiment: str,
    baseline_data: dict[str, Any],
) -> dict[str, Any]:
    payload = shared_aggregate.read_run_json(run_path)
    state = _artifact_state(run_path)
    if payload is None:
        return _missing_row(
            benchmark=benchmark,
            split=split,
            condition=condition,
            memory_source=memory_source,
            harness=harness,
            case_id=case_id,
            run_path=run_path,
            source_experiment=source_experiment,
            artifact_state=state,
        )
    verifier = payload.get("verifier") if isinstance(payload.get("verifier"), dict) else {}
    metrics = verifier.get("metrics") if isinstance(verifier.get("metrics"), dict) else {}
    valid = shared_aggregate.normalize_valid(verifier, str(payload.get("verifier_status", "")))
    metric_values = _metrics_from_mapping(metrics)
    return {
        "benchmark": payload.get("benchmark", benchmark),
        "split": payload.get("split", split),
        "condition": condition,
        "memory_source": payload.get("memory_source", memory_source),
        "harness": payload.get("harness", harness),
        "case_id": payload.get("case_id", case_id),
        "artifact_state": "present",
        "source_experiment": source_experiment,
        "overall_status": payload.get("overall_status", "unknown"),
        "agent_status": payload.get("agent_status", "unknown"),
        "verifier_status": payload.get("verifier_status", "unknown"),
        "valid": valid,
        "duration_seconds": shared_aggregate.coerce_numeric(payload.get("duration_seconds")),
        **metric_values,
        "normalized_score_pct": _normalized_score_pct(
            benchmark=benchmark,
            split=split,
            case_id=case_id,
            valid=valid,
            metrics=metric_values,
            baseline_data=baseline_data,
        ),
        "result_path": _display_path(run_path),
    }


def _records(
    config: family_run.FamilyConfig,
    *,
    baseline_data: dict[str, Any],
    main_agentic_root: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for selection in config.eval_benchmarks:
        for harness in config.eval_harnesses:
            for case_id in selection.cases:
                run_path = _main_agentic_run_path(
                    main_agentic_root,
                    benchmark=selection.benchmark,
                    harness=harness,
                    split=selection.split,
                    case_id=case_id,
                )
                rows.append(
                    _agent_row(
                        benchmark=selection.benchmark,
                        split=selection.split,
                        condition="no_memory",
                        memory_source="none",
                        harness=harness,
                        case_id=case_id,
                        run_path=run_path,
                        source_experiment="main_agentic",
                        baseline_data=baseline_data,
                    )
                )
        for memory_source in config.memory_sources:
            for harness in config.eval_harnesses:
                for case_id in selection.cases:
                    run_path = _run_path(
                        config,
                        memory_source=memory_source,
                        benchmark=selection.benchmark,
                        harness=harness,
                        split=selection.split,
                        case_id=case_id,
                    )
                    rows.append(
                        _agent_row(
                            benchmark=selection.benchmark,
                            split=selection.split,
                            condition=config.condition,
                            memory_source=memory_source,
                            harness=harness,
                            case_id=case_id,
                            run_path=run_path,
                            source_experiment="memory_accumulation",
                            baseline_data=baseline_data,
                        )
                    )
    return rows


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _group_summary(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, Any]:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(tuple(str(row.get(key, "")) for key in keys), []).append(row)
    summary: dict[str, Any] = {}
    for group_key, group_rows in sorted(groups.items()):
        label = " / ".join(group_key)
        scores = [
            float(value)
            for value in shared_aggregate.values_with_missing_penalty(
                [row.get("normalized_score_pct") for row in group_rows],
                direction="maximize",
                penalize_absent=True,
            )
        ]
        summary[label] = {
            "expected_count": len(group_rows),
            "present_count": sum(1 for row in group_rows if row["artifact_state"] == "present"),
            "missing_count": sum(1 for row in group_rows if row["artifact_state"] == "missing_artifact"),
            "valid_count": sum(1 for row in group_rows if row["valid"] is True),
            "mean_normalized_score_pct": _mean(scores),
            "overall_status_counts": shared_aggregate.status_counts(group_rows, "overall_status"),
        }
    return summary


def _format(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = family_run.load_family_config(args.config.resolve())
    baseline_data = main_solver_baselines.load_baseline_data()
    rows = _records(config, baseline_data=baseline_data, main_agentic_root=args.main_agentic_root)
    config.results.aggregate_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = [
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
        *METRIC_FIELDS,
        "result_path",
    ]
    with (config.results.aggregate_dir / "runs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({key: _format(row.get(key)) for key in fieldnames} for row in rows)
    summary = {
        "schema_version": 1,
        "experiment": "memory_accumulation",
        "config": _display_path(config.config_path),
        "row_count": len(rows),
        "by_memory_source": _group_summary(rows, ("memory_source",)),
        "by_memory_source_harness": _group_summary(rows, ("memory_source", "harness")),
        "by_benchmark_memory_source_harness": _group_summary(rows, ("benchmark", "memory_source", "harness")),
    }
    (config.results.aggregate_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {config.results.aggregate_dir / 'runs.csv'}")
    print(f"Wrote {config.results.aggregate_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
