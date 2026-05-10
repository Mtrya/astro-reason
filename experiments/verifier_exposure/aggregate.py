#!/usr/bin/env python3
"""Aggregate verifier-exposure ablation artifacts."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))

from experiments._shared import aggregate as shared_aggregate
from experiments._shared import main_solver_baselines

FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
DEFAULT_BASELINES = main_solver_baselines.DEFAULT_MAIN_SOLVER_README
DEFAULT_MAIN_AGENTIC_ROOT = (
    REPO_ROOT / "results" / "agent_runs" / "experiments" / "main_agentic" / "matrix"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate verifier-exposure run artifacts")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--baseline-data",
        type=Path,
        default=DEFAULT_BASELINES,
        help="Main-solver baseline source.",
    )
    parser.add_argument(
        "--main-agentic-root",
        type=Path,
        default=DEFAULT_MAIN_AGENTIC_ROOT,
        help="Root containing main_agentic matrix artifacts used for opaque rows.",
    )
    return parser.parse_args(argv)


def _load_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Config must be a mapping: {path}")
    return data


def _load_yaml(path: Path) -> dict[str, Any]:
    return main_solver_baselines.load_baseline_data(path)


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


def _main_agentic_run_path(
    root: Path,
    *,
    benchmark: str,
    harness: str,
    split: str,
    case_id: str,
) -> Path:
    return root / benchmark / harness / split / case_id / "run.json"


def _missing_agent_row(
    *,
    exposure: str,
    harness: str,
    case_id: str,
    run_path: Path,
    source_experiment: str,
) -> dict[str, Any]:
    return {
        "kind": "agent",
        "source_experiment": source_experiment,
        "exposure": exposure,
        "system": harness,
        "harness": harness,
        "case_id": case_id,
        "artifact_state": "missing_or_malformed",
        "overall_status": "missing_artifact",
        "agent_status": "missing_artifact",
        "verifier_status": "missing_artifact",
        "valid": None,
        "duration_seconds": None,
        "coverage_ratio": None,
        "normalized_quality": None,
        "result_path": _display_path(run_path),
    }


def _agent_row(
    *,
    exposure: str,
    harness: str,
    case_id: str,
    run_path: Path,
    source_experiment: str,
) -> dict[str, Any]:
    payload = shared_aggregate.read_run_json(run_path)
    if payload is None:
        return _missing_agent_row(
            exposure=exposure,
            harness=harness,
            case_id=case_id,
            run_path=run_path,
            source_experiment=source_experiment,
        )
    verifier = payload.get("verifier") if isinstance(payload.get("verifier"), dict) else {}
    duration_seconds = shared_aggregate.coerce_numeric(payload.get("duration_seconds"))
    return {
        "kind": "agent",
        "source_experiment": source_experiment,
        "exposure": payload.get("exposure", exposure),
        "system": payload.get("harness", harness),
        "harness": payload.get("harness", harness),
        "case_id": payload.get("case_id", case_id),
        "artifact_state": "present",
        "overall_status": payload.get("overall_status", "unknown"),
        "agent_status": payload.get("agent_status", "unknown"),
        "verifier_status": payload.get("verifier_status", "unknown"),
        "valid": verifier.get("valid") if isinstance(verifier.get("valid"), bool) else None,
        "duration_seconds": duration_seconds,
        "coverage_ratio": _metric(payload, "coverage_ratio"),
        "normalized_quality": _metric(payload, "normalized_quality"),
        "result_path": _display_path(run_path),
    }


def _metric(payload: dict[str, Any], key: str) -> float | None:
    verifier = payload.get("verifier")
    if not isinstance(verifier, dict):
        return None
    metrics = verifier.get("metrics")
    if not isinstance(metrics, dict):
        return None
    value = shared_aggregate.coerce_numeric(metrics.get(key))
    return float(value) if value is not None else None


def _metric_from_mapping(metrics: dict[str, Any], key: str) -> float | None:
    value = shared_aggregate.coerce_numeric(metrics.get(key))
    return float(value) if value is not None else None


def _mean(values: list[float]) -> float | None:
    stats = shared_aggregate.metric_stats(values)
    mean = stats["mean"]
    return float(mean) if mean is not None else None


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


def _config_list(config: dict[str, Any], key: str) -> tuple[str, ...]:
    values = config.get(key, [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise SystemExit(f"Config {key} must be a list of strings")
    return tuple(values)


def _solver_rows(
    *,
    baseline_data: dict[str, Any],
    baseline_path: Path = DEFAULT_BASELINES,
    benchmark: str,
    split: str,
    case_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    rows = baseline_data.get("rows")
    if not isinstance(rows, list):
        raise SystemExit("Baseline data must contain a rows list.")

    records: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        method = row.get("method")
        metrics = row.get("metrics")
        case_id = row.get("case_id")
        if row.get("benchmark") != benchmark or row.get("split") != split:
            continue
        if not isinstance(method, str) or not isinstance(case_id, str):
            continue
        if case_id not in case_ids:
            continue
        if not isinstance(metrics, dict):
            metrics = {}
        valid = row.get("valid")
        records.append(
            {
                "kind": "solver",
                "source_experiment": "main_solver",
                "exposure": "solver",
                "system": method,
                "harness": "",
                "case_id": case_id,
                "artifact_state": "baseline",
                "overall_status": row.get("status", "verified"),
                "agent_status": "",
                "verifier_status": row.get("status", "verified"),
                "valid": valid if isinstance(valid, bool) else True,
                "duration_seconds": _metric_from_mapping(metrics, "solve_s"),
                "coverage_ratio": _metric_from_mapping(metrics, "coverage_ratio"),
                "normalized_quality": _metric_from_mapping(metrics, "normalized_quality"),
                "result_path": _display_path(baseline_path),
            }
        )
    return records


def _records(
    config: dict[str, Any],
    config_path: Path,
    *,
    baseline_data: dict[str, Any],
    baseline_path: Path = DEFAULT_BASELINES,
    main_agentic_root: Path = DEFAULT_MAIN_AGENTIC_ROOT,
) -> list[dict[str, Any]]:
    root = _result_root(config, config_path)
    benchmark = config.get("benchmark")
    split = config.get("split")
    exposures = _config_list(config, "exposures")
    case_ids = _config_list(config, "cases")
    harnesses = _config_list(config, "harnesses")
    if not harnesses:
        raise SystemExit(f"Config harnesses must contain at least one item: {config_path}")
    if not isinstance(benchmark, str) or not isinstance(split, str):
        raise SystemExit("Config benchmark and split must be strings")
    rows: list[dict[str, Any]] = []
    for exposure in exposures:
        if exposure == "opaque":
            continue
        for harness in harnesses:
            for case_id in case_ids:
                run_path = _run_path(
                    root,
                    config_path.stem,
                    exposure=exposure,
                    benchmark=benchmark,
                    harness=harness,
                    split=split,
                    case_id=case_id,
                )
                rows.append(
                    _agent_row(
                        exposure=exposure,
                        harness=harness,
                        case_id=case_id,
                        run_path=run_path,
                        source_experiment="verifier_exposure",
                    )
                )

    for harness in harnesses:
        for case_id in case_ids:
            run_path = _main_agentic_run_path(
                main_agentic_root,
                benchmark=benchmark,
                harness=harness,
                split=split,
                case_id=case_id,
            )
            rows.append(
                _agent_row(
                    exposure="opaque",
                    harness=harness,
                    case_id=case_id,
                    run_path=run_path,
                    source_experiment="main_agentic",
                )
            )

    rows.extend(
        _solver_rows(
            baseline_data=baseline_data,
            baseline_path=baseline_path,
            benchmark=benchmark,
            split=split,
            case_ids=case_ids,
        )
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
            "valid_rate": (
                sum(1 for value in valid_values if value) / len(valid_values)
                if valid_values
                else None
            ),
            "overall_status_counts": shared_aggregate.status_counts(exposure_rows, "overall_status"),
            "verifier_status_counts": shared_aggregate.status_counts(exposure_rows, "verifier_status"),
            "mean_coverage_ratio": _mean(
                [row["coverage_ratio"] for row in exposure_rows if isinstance(row["coverage_ratio"], float)]
            ),
            "mean_normalized_quality": _mean(
                [
                    row["normalized_quality"]
                    for row in exposure_rows
                    if isinstance(row["normalized_quality"], float)
                ]
            ),
        }
    by_exposure_system: dict[str, Any] = {}
    for exposure in exposures:
        for system in sorted({str(row["system"]) for row in rows if row["exposure"] == exposure}):
            group_rows = [row for row in rows if row["exposure"] == exposure and row["system"] == system]
            valid_values = [row["valid"] for row in group_rows if isinstance(row["valid"], bool)]
            by_exposure_system[f"{exposure}/{system}"] = {
                "kind": group_rows[0].get("kind", "agent") if group_rows else "unknown",
                "run_count": len(group_rows),
                "valid_count": sum(1 for value in valid_values if value),
                "valid_rate": (
                    sum(1 for value in valid_values if value) / len(valid_values)
                    if valid_values
                    else None
                ),
                "overall_status_counts": shared_aggregate.status_counts(group_rows, "overall_status"),
                "mean_coverage_ratio": _mean(
                    [row["coverage_ratio"] for row in group_rows if isinstance(row["coverage_ratio"], float)]
                ),
                "mean_normalized_quality": _mean(
                    [
                        row["normalized_quality"]
                        for row in group_rows
                        if isinstance(row["normalized_quality"], float)
                    ]
                ),
            }
    return {
        "schema_version": 2,
        "experiment": "verifier_exposure",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "by_exposure": by_exposure,
        "by_exposure_system": by_exposure_system,
        "by_exposure_harness": by_exposure_system,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "kind",
        "source_experiment",
        "exposure",
        "system",
        "harness",
        "case_id",
        "artifact_state",
        "overall_status",
        "agent_status",
        "verifier_status",
        "valid",
        "duration_seconds",
        "coverage_ratio",
        "normalized_quality",
        "result_path",
    ]
    shared_aggregate.ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _format(row.get(key)) for key in fieldnames})


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.resolve()
    config = _load_config(config_path)
    baseline_data = _load_yaml(args.baseline_data.resolve())
    aggregate_dir = _aggregate_dir(config, config_path)
    rows = _records(
        config,
        config_path,
        baseline_data=baseline_data,
        baseline_path=args.baseline_data.resolve(),
        main_agentic_root=args.main_agentic_root.resolve(),
    )
    summary = _summary(rows)
    shared_aggregate.ensure_dir(aggregate_dir)
    shared_aggregate.write_json(aggregate_dir / "summary.json", summary)
    _write_csv(aggregate_dir / "runs.csv", rows)
    print(f"Wrote {aggregate_dir / 'summary.json'}")
    print(f"Wrote {aggregate_dir / 'runs.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
