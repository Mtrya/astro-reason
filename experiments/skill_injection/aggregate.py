#!/usr/bin/env python3
"""Aggregate skill-injection ablation artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
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
from experiments._shared import score_normalization as score_norm


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
METRIC_FIELDS = (
    "coverage_ratio",
    "normalized_quality",
    "normalized_score_pct",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate skill-injection run artifacts.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser.parse_args(argv)


def _aggregate_dir(config: family_run.FamilyConfig) -> Path:
    return config.results.aggregate_dir


def _run_path(config: family_run.FamilyConfig, *, condition: str, harness: str, case_id: str) -> Path:
    return (
        config.results.root
        / config.config_path.stem
        / condition
        / config.benchmark
        / harness
        / config.split
        / case_id
        / "run.json"
    )


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
    values["normalized_score_pct"] = score_norm.stereo_imaging_score_pct(
        normalized_quality=values.get("normalized_quality")
    )
    return values


def _normalized_score_pct(valid: bool | None, metrics: dict[str, Any]) -> float | None:
    if valid is not True:
        return 0.0 if valid is False else None
    return score_norm.stereo_imaging_score_pct(normalized_quality=metrics.get("normalized_quality"))


def _condition_skills(condition: str) -> tuple[str, ...]:
    profile = family_run.load_condition_profile(condition)
    return tuple(skill.name for skill in profile.skills)


def _missing_row(
    *,
    config: family_run.FamilyConfig,
    condition: str,
    harness: str,
    case_id: str,
    run_path: Path,
    artifact_state: str,
    skills: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "benchmark": config.benchmark,
        "split": config.split,
        "condition": condition,
        "harness": harness,
        "case_id": case_id,
        "artifact_state": artifact_state,
        "overall_status": artifact_state,
        "agent_status": artifact_state,
        "verifier_status": artifact_state,
        "valid": None,
        "duration_seconds": None,
        "skill_count": len(skills),
        "skills": list(skills),
        **{field: None for field in METRIC_FIELDS},
        "result_path": _display_path(run_path),
    }


def _agent_row(
    *,
    config: family_run.FamilyConfig,
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
        "benchmark": payload.get("benchmark", config.benchmark),
        "split": payload.get("split", config.split),
        "condition": payload.get("condition", condition),
        "harness": payload.get("harness", harness),
        "case_id": payload.get("case_id", case_id),
        "artifact_state": "present",
        "overall_status": payload.get("overall_status", "unknown"),
        "agent_status": payload.get("agent_status", "unknown"),
        "verifier_status": payload.get("verifier_status", "unknown"),
        "valid": valid,
        "duration_seconds": shared_aggregate.coerce_numeric(payload.get("duration_seconds")),
        "skill_count": len(skill_names),
        "skills": skill_names,
        **metric_values,
        "normalized_score_pct": _normalized_score_pct(valid, metric_values),
        "result_path": _display_path(run_path),
    }


def _records(config: family_run.FamilyConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    skills_by_condition = {condition: _condition_skills(condition) for condition in config.conditions}
    for condition in config.conditions:
        for harness in config.harnesses:
            for case_id in config.cases:
                run_path = _run_path(config, condition=condition, harness=harness, case_id=case_id)
                rows.append(
                    _agent_row(
                        config=config,
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
    return {
        "run_count": len(rows),
        "present_count": sum(1 for row in rows if row.get("artifact_state") == "present"),
        "missing_count": sum(1 for row in rows if row.get("artifact_state") == "missing_artifact"),
        "malformed_count": sum(1 for row in rows if row.get("artifact_state") == "malformed_artifact"),
        "valid_count": sum(1 for value in valid_values if value),
        "valid_rate": (
            sum(1 for value in valid_values if value) / len(valid_values)
            if valid_values
            else None
        ),
        "overall_status_counts": shared_aggregate.status_counts(rows, "overall_status"),
        "agent_status_counts": shared_aggregate.status_counts(rows, "agent_status"),
        "verifier_status_counts": shared_aggregate.status_counts(rows, "verifier_status"),
        **{
            f"mean_{field}": _mean([row[field] for row in rows if isinstance(row.get(field), float)])
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
    rows = _records(config)
    summary = _summary(rows)
    shared_aggregate.write_json(aggregate_dir / "summary.json", summary)
    _write_csv(aggregate_dir / "runs.csv", rows)
    print(f"Wrote {aggregate_dir / 'summary.json'}")
    print(f"Wrote {aggregate_dir / 'runs.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
