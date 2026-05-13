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
from experiments._shared import score_normalization as score_norm

FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
DEFAULT_BASELINES = main_solver_baselines.DEFAULT_MAIN_SOLVER_README
DEFAULT_MAIN_AGENTIC_ROOT = (
    REPO_ROOT / "results" / "agent_runs" / "experiments" / "main_agentic" / "matrix"
)
METRIC_FIELDS = (
    "coverage_ratio",
    "normalized_quality",
    "score_hours",
    "n_satisfied_requests",
    "u_rms",
    "u_max",
    "n_tracks",
    "normalized_score_pct",
)
METRIC_DIRECTIONS = {
    "coverage_ratio": "maximize",
    "normalized_quality": "maximize",
    "score_hours": "maximize",
    "n_satisfied_requests": "maximize",
    "u_rms": "minimize",
    "u_max": "minimize",
    "n_tracks": "maximize",
    "normalized_score_pct": "maximize",
}


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
    benchmark: str,
    split: str,
    exposure: str,
    harness: str,
    case_id: str,
    run_path: Path,
    source_experiment: str,
) -> dict[str, Any]:
    return {
        "kind": "agent",
        "source_experiment": source_experiment,
        "benchmark": benchmark,
        "split": split,
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
        **{field: 0.0 if field == "normalized_score_pct" else None for field in METRIC_FIELDS},
        "result_path": _display_path(run_path),
    }


def _agent_row(
    *,
    benchmark: str,
    split: str,
    exposure: str,
    harness: str,
    case_id: str,
    run_path: Path,
    source_experiment: str,
    baseline_data: dict[str, Any],
) -> dict[str, Any]:
    payload = shared_aggregate.read_run_json(run_path)
    if payload is None:
        return _missing_agent_row(
            benchmark=_benchmark_from_expected_path(run_path, source_experiment),
            split=_split_from_expected_path(run_path, source_experiment),
            exposure=exposure,
            harness=harness,
            case_id=case_id,
            run_path=run_path,
            source_experiment=source_experiment,
        )
    verifier = payload.get("verifier") if isinstance(payload.get("verifier"), dict) else {}
    metrics = verifier.get("metrics") if isinstance(verifier.get("metrics"), dict) else {}
    duration_seconds = shared_aggregate.coerce_numeric(payload.get("duration_seconds"))
    benchmark = payload.get("benchmark", benchmark)
    split = payload.get("split", split)
    valid = verifier.get("valid") if isinstance(verifier.get("valid"), bool) else None
    metric_values = _metrics_from_mapping(metrics)
    return {
        "kind": "agent",
        "source_experiment": source_experiment,
        "benchmark": benchmark,
        "split": split,
        "exposure": payload.get("exposure", exposure),
        "system": payload.get("harness", harness),
        "harness": payload.get("harness", harness),
        "case_id": payload.get("case_id", case_id),
        "artifact_state": "present",
        "overall_status": payload.get("overall_status", "unknown"),
        "agent_status": payload.get("agent_status", "unknown"),
        "verifier_status": payload.get("verifier_status", "unknown"),
        "valid": valid,
        "duration_seconds": duration_seconds,
        **metric_values,
        "normalized_score_pct": _normalized_score_pct(
            benchmark=str(benchmark),
            valid=valid,
            metrics=metric_values,
            baseline_data=baseline_data,
        ),
        "result_path": _display_path(run_path),
    }


def _benchmark_from_run_path(path: Path) -> str | None:
    parts = path.parts
    for index, part in enumerate(parts):
        if part == "main_agentic" and index + 2 < len(parts):
            return parts[index + 2]
    return None


def _benchmark_from_expected_path(path: Path, source_experiment: str) -> str:
    parts = path.parts
    if source_experiment == "main_agentic":
        for index, part in enumerate(parts):
            if part == "matrix" and index + 1 < len(parts):
                return parts[index + 1]
    for index, part in enumerate(parts):
        if part == "verifier_exposure" and index + 3 < len(parts):
            return parts[index + 3]
    return ""


def _split_from_expected_path(path: Path, source_experiment: str) -> str:
    parts = path.parts
    if source_experiment == "main_agentic":
        for index, part in enumerate(parts):
            if part == "matrix" and index + 3 < len(parts):
                return parts[index + 3]
    for index, part in enumerate(parts):
        if part == "verifier_exposure" and index + 5 < len(parts):
            return parts[index + 5]
    return ""


def _metrics_from_mapping(metrics: dict[str, Any]) -> dict[str, float | None]:
    return {field: _metric_from_mapping(metrics, field) for field in METRIC_FIELDS if field != "normalized_score_pct"}


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


def _normalization_config(baseline_data: dict[str, Any], benchmark: str) -> dict[str, Any]:
    normalization = baseline_data.get("normalization")
    if not isinstance(normalization, dict):
        return {}
    config = normalization.get(benchmark)
    return config if isinstance(config, dict) else {}


def _normalized_score_pct(
    *,
    benchmark: str,
    valid: bool | None,
    metrics: dict[str, Any],
    baseline_data: dict[str, Any],
) -> float | None:
    if valid is not True:
        return 0.0
    if benchmark == "stereo_imaging":
        return score_norm.stereo_imaging_score_pct(
            normalized_quality=metrics.get("normalized_quality"),
        )
    if benchmark == "satnet":
        config = _normalization_config(baseline_data, benchmark)
        return score_norm.satnet_score_pct(
            u_rms=metrics.get("u_rms"),
            u_max=metrics.get("u_max"),
            u_rms_cap=config.get("u_rms_cap"),
            u_max_cap=config.get("u_max_cap"),
        )
    return None


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


def _benchmark_selections(config: dict[str, Any], path: Path) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    raw = config.get("benchmarks")
    if raw is None:
        benchmark = config.get("benchmark")
        split = config.get("split")
        if not isinstance(benchmark, str) or not isinstance(split, str):
            raise SystemExit("Config benchmark and split must be strings")
        return ((benchmark, split, _config_list(config, "cases")),)
    if not isinstance(raw, list) or not raw:
        raise SystemExit(f"Config benchmarks must be a non-empty list: {path}")
    selections: list[tuple[str, str, tuple[str, ...]]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SystemExit(f"Config benchmarks[{index}] must be a mapping: {path}")
        benchmark = item.get("benchmark")
        split = item.get("split")
        cases = item.get("cases", [])
        if not isinstance(benchmark, str) or not isinstance(split, str):
            raise SystemExit(f"Config benchmarks[{index}] benchmark and split must be strings: {path}")
        if not isinstance(cases, list) or any(not isinstance(case, str) for case in cases):
            raise SystemExit(f"Config benchmarks[{index}].cases must be a list of strings: {path}")
        selections.append((benchmark, split, tuple(cases)))
    return tuple(selections)


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
        metric_values = _metrics_from_mapping(metrics)
        records.append(
            {
                "kind": "solver",
                "source_experiment": "main_solver",
                "benchmark": benchmark,
                "split": split,
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
                **metric_values,
                "normalized_score_pct": _normalized_score_pct(
                    benchmark=benchmark,
                    valid=valid if isinstance(valid, bool) else True,
                    metrics=metric_values,
                    baseline_data=baseline_data,
                ),
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
    exposures = _config_list(config, "exposures")
    harnesses = _config_list(config, "harnesses")
    if not harnesses:
        raise SystemExit(f"Config harnesses must contain at least one item: {config_path}")
    rows: list[dict[str, Any]] = []
    for benchmark, split, case_ids in _benchmark_selections(config, config_path):
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
                            benchmark=benchmark,
                            split=split,
                            exposure=exposure,
                            harness=harness,
                            case_id=case_id,
                            run_path=run_path,
                            source_experiment="verifier_exposure",
                            baseline_data=baseline_data,
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
                        benchmark=benchmark,
                        split=split,
                        exposure="opaque",
                        harness=harness,
                        case_id=case_id,
                        run_path=run_path,
                        source_experiment="main_agentic",
                        baseline_data=baseline_data,
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
    by_benchmark_exposure: dict[str, Any] = {}
    by_benchmark_exposure_system: dict[str, Any] = {}
    for benchmark in sorted({str(row["benchmark"]) for row in rows}):
        benchmark_rows = [row for row in rows if row["benchmark"] == benchmark]
        for exposure in sorted({str(row["exposure"]) for row in benchmark_rows}):
            exposure_rows = [row for row in benchmark_rows if row["exposure"] == exposure]
            by_benchmark_exposure[f"{benchmark}/{exposure}"] = _group_summary(exposure_rows)
            for system in sorted({str(row["system"]) for row in exposure_rows}):
                group_rows = [row for row in exposure_rows if row["system"] == system]
                summary = _group_summary(group_rows)
                summary["kind"] = group_rows[0].get("kind", "agent") if group_rows else "unknown"
                by_benchmark_exposure_system[f"{benchmark}/{exposure}/{system}"] = summary
    return {
        "schema_version": 3,
        "experiment": "verifier_exposure",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "by_benchmark_exposure": by_benchmark_exposure,
        "by_benchmark_exposure_system": by_benchmark_exposure_system,
        "by_exposure": {
            key.split("/", maxsplit=1)[1]: value
            for key, value in by_benchmark_exposure.items()
            if key.startswith("stereo_imaging/")
        },
        "by_exposure_system": {
            key.removeprefix("stereo_imaging/"): value
            for key, value in by_benchmark_exposure_system.items()
            if key.startswith("stereo_imaging/")
        },
        "by_exposure_harness": {
            key.removeprefix("stereo_imaging/"): value
            for key, value in by_benchmark_exposure_system.items()
            if key.startswith("stereo_imaging/")
        },
    }


def _group_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid_values = [row["valid"] for row in rows if isinstance(row["valid"], bool)]
    valid_count = sum(1 for value in valid_values if value)
    return {
        "run_count": len(rows),
        "valid_count": valid_count,
        "valid_rate": valid_count / len(rows) if rows else None,
        "overall_status_counts": shared_aggregate.status_counts(rows, "overall_status"),
        "verifier_status_counts": shared_aggregate.status_counts(rows, "verifier_status"),
        **{
            f"mean_{field}": _mean(
                [
                    float(value)
                    for value in shared_aggregate.values_with_missing_penalty(
                        [
                            row.get(field)
                            if field == "normalized_score_pct" or row.get("valid") is True
                            else None
                            for row in rows
                        ],
                        direction=METRIC_DIRECTIONS[field],
                        penalize_absent=field == "normalized_score_pct",
                    )
                ]
            )
            for field in METRIC_FIELDS
        },
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "kind",
        "source_experiment",
        "benchmark",
        "split",
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
        *METRIC_FIELDS,
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
