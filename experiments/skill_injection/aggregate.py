#!/usr/bin/env python3
"""Aggregate skill-injection ablation artifacts."""

from __future__ import annotations

import argparse
import csv
import functools
import json
import sys
from datetime import datetime, timezone
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


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
DEFAULT_MAIN_AGENTIC_ROOT = (
    REPO_ROOT / "results" / "agent_runs" / "experiments" / "main_agentic" / "matrix"
)
METRIC_FIELDS = (
    "coverage_ratio",
    "normalized_quality",
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
METRIC_DIRECTIONS = {
    "coverage_ratio": "maximize",
    "normalized_quality": "maximize",
    "weighted_coverage_ratio": "maximize",
    "num_actions": "minimize",
    "min_battery_wh": "maximize",
    "service_fraction": "maximize",
    "worst_demand_service_fraction": "maximize",
    "num_added_satellites": "minimize",
    "mean_latency_ms": "minimize",
    "latency_p95_ms": "minimize",
    "score_hours": "maximize",
    "n_satisfied_requests": "maximize",
    "u_rms": "minimize",
    "u_max": "minimize",
    "n_tracks": "maximize",
    "normalized_score_pct": "maximize",
}

NORMALIZATION_CONFIG = main_solver_baselines.NORMALIZATION


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate skill-injection run artifacts.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--main-agentic-root",
        type=Path,
        default=DEFAULT_MAIN_AGENTIC_ROOT,
        help="Root containing main_agentic matrix artifacts used for no_skill rows.",
    )
    return parser.parse_args(argv)


def _aggregate_dir(config: family_run.FamilyConfig) -> Path:
    return config.results.aggregate_dir


def _run_path(
    config: family_run.FamilyConfig,
    *,
    condition: str,
    benchmark: str,
    harness: str,
    split: str,
    case_id: str,
) -> Path:
    return (
        config.results.root
        / config.config_path.stem
        / condition
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


def _metric_from_mapping(metrics: dict[str, Any], key: str) -> float | None:
    value = shared_aggregate.coerce_numeric(metrics.get(key))
    return float(value) if value is not None else None


def _metrics_from_mapping(metrics: dict[str, Any]) -> dict[str, float | None]:
    values = {field: _metric_from_mapping(metrics, field) for field in METRIC_FIELDS if field != "normalized_score_pct"}
    return values


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


def _case_dir(*, benchmark: str, split: str, case_id: str) -> Path:
    return REPO_ROOT / "benchmarks" / benchmark / "dataset" / "cases" / split / case_id


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


def _normalization_config(benchmark: str) -> dict[str, Any]:
    config = NORMALIZATION_CONFIG.get(benchmark)
    return config if isinstance(config, dict) else {}


def _normalized_score_pct(
    *,
    benchmark: str,
    split: str,
    case_id: str,
    valid: bool | None,
    metrics: dict[str, Any],
) -> float | None:
    if valid is not True:
        return 0.0 if valid is False else None
    if benchmark == "stereo_imaging":
        return score_norm.stereo_imaging_score_pct(normalized_quality=metrics.get("normalized_quality"))
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
        config = _normalization_config(benchmark)
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
    return None


def _condition_skills(condition: str, benchmark: str) -> tuple[str, ...]:
    profile = family_run.load_condition_profile(condition)
    return tuple(skill.name for skill in family_run._skills_for_benchmark(profile, benchmark))


def _missing_row(
    *,
    config: family_run.FamilyConfig,
    benchmark: str,
    split: str,
    condition: str,
    harness: str,
    case_id: str,
    run_path: Path,
    artifact_state: str,
    skills: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "benchmark": benchmark,
        "split": split,
        "condition": condition,
        "harness": harness,
        "case_id": case_id,
        "artifact_state": artifact_state,
        "source_experiment": "main_agentic" if condition == "no_skill" else "skill_injection",
        "overall_status": artifact_state,
        "agent_status": artifact_state,
        "verifier_status": artifact_state,
        "valid": None,
        "duration_seconds": None,
        "skill_count": len(skills),
        "skills": list(skills),
        **{field: 0.0 if field == "normalized_score_pct" else None for field in METRIC_FIELDS},
        "result_path": _display_path(run_path),
    }


def _agent_row(
    *,
    config: family_run.FamilyConfig,
    benchmark: str,
    split: str,
    condition: str,
    harness: str,
    case_id: str,
    run_path: Path,
    skills: tuple[str, ...],
) -> dict[str, Any]:
    payload = shared_aggregate.read_run_json(run_path)
    state = _artifact_state(run_path)
    if payload is None:
        return _missing_row(
            config=config,
            benchmark=benchmark,
            split=split,
            condition=condition,
            harness=harness,
            case_id=case_id,
            run_path=run_path,
            artifact_state=state,
            skills=skills,
        )

    verifier = payload.get("verifier") if isinstance(payload.get("verifier"), dict) else {}
    metrics = verifier.get("metrics") if isinstance(verifier.get("metrics"), dict) else {}
    valid = shared_aggregate.normalize_valid(verifier, str(payload.get("verifier_status", "")))
    metric_values = _metrics_from_mapping(metrics)
    skill_names = payload.get("skills")
    if not isinstance(skill_names, list) or any(not isinstance(name, str) for name in skill_names):
        skill_names = list(skills)
    return {
        "benchmark": payload.get("benchmark", benchmark),
        "split": payload.get("split", split),
        "condition": payload.get("condition", condition),
        "harness": payload.get("harness", harness),
        "case_id": payload.get("case_id", case_id),
        "artifact_state": "present",
        "source_experiment": "main_agentic" if condition == "no_skill" else "skill_injection",
        "overall_status": payload.get("overall_status", "unknown"),
        "agent_status": payload.get("agent_status", "unknown"),
        "verifier_status": payload.get("verifier_status", "unknown"),
        "valid": valid,
        "duration_seconds": shared_aggregate.coerce_numeric(payload.get("duration_seconds")),
        "skill_count": len(skill_names),
        "skills": skill_names,
        **metric_values,
        "normalized_score_pct": _normalized_score_pct(
            benchmark=str(payload.get("benchmark", benchmark)),
            split=str(payload.get("split", split)),
            case_id=str(payload.get("case_id", case_id)),
            valid=valid,
            metrics=metric_values,
        ),
        "result_path": _display_path(run_path),
    }


def _condition_names(selection: family_run.BenchmarkSelection) -> tuple[str, ...]:
    configured = tuple(condition for condition in selection.conditions if condition != "no_skill")
    return ("no_skill", *configured)


def _records(config: family_run.FamilyConfig, *, main_agentic_root: Path = DEFAULT_MAIN_AGENTIC_ROOT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for selection in config.benchmarks:
        condition_names = _condition_names(selection)
        skills_by_condition = {
            condition: _condition_skills(condition, selection.benchmark)
            for condition in condition_names
        }
        for condition in condition_names:
            for harness in selection.harnesses:
                for case_id in selection.cases:
                    if condition == "no_skill":
                        run_path = _main_agentic_run_path(
                            main_agentic_root,
                            benchmark=selection.benchmark,
                            harness=harness,
                            split=selection.split,
                            case_id=case_id,
                        )
                    else:
                        run_path = _run_path(
                            config,
                            condition=condition,
                            benchmark=selection.benchmark,
                            harness=harness,
                            split=selection.split,
                            case_id=case_id,
                        )
                    rows.append(
                        _agent_row(
                            config=config,
                            benchmark=selection.benchmark,
                            split=selection.split,
                            condition=condition,
                            harness=harness,
                            case_id=case_id,
                            run_path=run_path,
                            skills=skills_by_condition[condition],
                        )
                    )
    return rows


def _mean(values: list[float]) -> float | None:
    stats = shared_aggregate.metric_stats(values)
    mean = stats["mean"]
    return float(mean) if mean is not None else None


def _group_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid_values = [row["valid"] for row in rows if isinstance(row["valid"], bool)]
    valid_count = sum(1 for value in valid_values if value)
    return {
        "run_count": len(rows),
        "present_count": sum(1 for row in rows if row.get("artifact_state") == "present"),
        "missing_count": sum(1 for row in rows if row.get("artifact_state") == "missing_artifact"),
        "malformed_count": sum(1 for row in rows if row.get("artifact_state") == "malformed_artifact"),
        "valid_count": valid_count,
        "valid_rate": valid_count / len(rows) if rows else None,
        "overall_status_counts": shared_aggregate.status_counts(rows, "overall_status"),
        "agent_status_counts": shared_aggregate.status_counts(rows, "agent_status"),
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
        "mean_duration_seconds": _mean(
            [float(row["duration_seconds"]) for row in rows if isinstance(row.get("duration_seconds"), (int, float))]
        ),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_benchmark_condition: dict[str, Any] = {}
    by_benchmark_condition_harness: dict[str, Any] = {}
    for benchmark in sorted({str(row["benchmark"]) for row in rows}):
        benchmark_rows = [row for row in rows if row["benchmark"] == benchmark]
        for condition in sorted({str(row["condition"]) for row in benchmark_rows}):
            condition_rows = [row for row in benchmark_rows if row["condition"] == condition]
            by_benchmark_condition[f"{benchmark}/{condition}"] = _group_summary(condition_rows)
            for harness in sorted({str(row["harness"]) for row in condition_rows}):
                group_rows = [row for row in condition_rows if row["harness"] == harness]
                by_benchmark_condition_harness[f"{benchmark}/{condition}/{harness}"] = _group_summary(group_rows)
    return {
        "schema_version": 1,
        "experiment": "skill_injection",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "by_benchmark_condition": by_benchmark_condition,
        "by_benchmark_condition_harness": by_benchmark_condition_harness,
        "by_condition": {
            key.split("/", maxsplit=1)[1]: value
            for key, value in by_benchmark_condition.items()
            if key.startswith("stereo_imaging/")
        },
        "by_condition_harness": {
            key.removeprefix("stereo_imaging/"): value
            for key, value in by_benchmark_condition_harness.items()
            if key.startswith("stereo_imaging/")
        },
    }


def _format(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    return str(value)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "benchmark",
        "split",
        "condition",
        "harness",
        "case_id",
        "artifact_state",
        "source_experiment",
        "overall_status",
        "agent_status",
        "verifier_status",
        "valid",
        "duration_seconds",
        "skill_count",
        "skills",
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
    config = family_run.load_family_config(args.config.resolve())
    aggregate_dir = _aggregate_dir(config)
    rows = _records(config, main_agentic_root=args.main_agentic_root.resolve())
    summary = _summary(rows)
    shared_aggregate.write_json(aggregate_dir / "summary.json", summary)
    _write_csv(aggregate_dir / "runs.csv", rows)
    print(f"Wrote {aggregate_dir / 'summary.json'}")
    print(f"Wrote {aggregate_dir / 'runs.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
