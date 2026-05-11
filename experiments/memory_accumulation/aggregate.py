#!/usr/bin/env python3
"""Aggregate memory-accumulation held-out evaluation artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run as family_run  # type: ignore[no-redef]
else:
    from . import run as family_run

from experiments._shared import aggregate as shared_aggregate
from experiments._shared import main_solver_baselines
from experiments.main_agentic import plot_radar as radar_scores


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
    return radar_scores._normalized_score_pct(
        benchmark=benchmark,
        split=split,
        case_id=case_id,
        metrics=metrics,
        baseline_data=baseline_data,
    )


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
        **{field: None for field in METRIC_FIELDS},
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
            float(row["normalized_score_pct"])
            for row in group_rows
            if shared_aggregate.is_numeric(row.get("normalized_score_pct"))
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
