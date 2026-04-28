from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = REPO_ROOT / "results" / "main_solver"
SOLVER_PROFILE_DIR = REPO_ROOT / "experiments" / "main_solver" / "solvers"

BASE_FIELDNAMES = [
    "benchmark",
    "solver",
    "case_id",
    "status",
    "evidence_type",
    "runnable",
    "valid",
    "solve_duration_seconds",
    "verifier_duration_seconds",
    "verifier_metrics_json",
    "solver_status_json",
    "reported_metrics_json",
    "parse_error",
    "raw_text",
    "run_json",
]


def _read_run_json(path: Path) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return {
            "status": "malformed_artifact",
            "parse_error": str(exc),
            "raw_text": raw_text,
        }
    if not isinstance(payload, dict):
        return {
            "status": "malformed_artifact",
            "parse_error": "run.json must contain an object",
            "raw_text": raw_text,
        }
    return payload


def _json_compact(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _dot_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for key in path.split("."):
        if not key or not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"Failed to load solver profile {path}: {exc}") from exc
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"Solver profile must contain a mapping: {path}")
    return payload


def _load_solver_profiles() -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(SOLVER_PROFILE_DIR.glob("*.yaml")):
        profile = _load_yaml_mapping(path)
        solver_id = profile.get("id")
        if isinstance(solver_id, str) and solver_id:
            profiles[solver_id] = profile
    return profiles


def _aggregate_metric_declarations(profile: dict[str, Any]) -> list[dict[str, str]]:
    declarations = profile.get("aggregate_metrics", [])
    if declarations is None:
        return []
    if not isinstance(declarations, list):
        raise ValueError(
            f"Solver profile {profile.get('id', '<unknown>')} aggregate_metrics must be a list"
        )

    normalized: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for index, item in enumerate(declarations):
        if not isinstance(item, dict):
            raise ValueError(
                f"Solver profile {profile.get('id', '<unknown>')} aggregate_metrics[{index}] must be a mapping"
            )
        name = item.get("name")
        source = item.get("source")
        if not isinstance(name, str) or not name:
            raise ValueError(
                f"Solver profile {profile.get('id', '<unknown>')} aggregate_metrics[{index}].name must be a non-empty string"
            )
        if name in BASE_FIELDNAMES:
            raise ValueError(f"Aggregate metric {name!r} conflicts with a base column")
        if name in seen_names:
            raise ValueError(f"Duplicate aggregate metric name {name!r}")
        if (
            not isinstance(source, str)
            or not source
            or source.startswith(".")
            or source.endswith(".")
            or ".." in source
        ):
            raise ValueError(
                f"Aggregate metric {name!r} source must be a direct dot path"
            )
        seen_names.add(name)
        normalized.append({"name": name, "source": source})
    return normalized


def _base_row(payload: dict[str, Any], run_path: Path) -> dict[str, Any]:
    return {
        "benchmark": payload.get("benchmark"),
        "solver": payload.get("solver"),
        "case_id": payload.get("case_id"),
        "status": payload.get("status"),
        "evidence_type": payload.get("evidence_type"),
        "runnable": payload.get("runnable"),
        "valid": _dot_path(payload, "verifier.valid"),
        "solve_duration_seconds": _dot_path(payload, "solve.duration_seconds"),
        "verifier_duration_seconds": _dot_path(
            payload,
            "verifier.execution.duration_seconds",
        ),
        "verifier_metrics_json": _json_compact(_dot_path(payload, "verifier.metrics")),
        "solver_status_json": _json_compact(payload.get("solver_status")),
        "reported_metrics_json": _json_compact(payload.get("reported_metrics")),
        "parse_error": payload.get("parse_error"),
        "raw_text": payload.get("raw_text"),
        "run_json": str(run_path),
    }


def _rows(results_root: Path) -> list[dict[str, Any]]:
    profiles = _load_solver_profiles()
    solver_declarations = {
        solver_id: _aggregate_metric_declarations(profile)
        for solver_id, profile in profiles.items()
    }
    rows: list[dict[str, Any]] = []
    for run_path in sorted(results_root.glob("*/*/*/run.json")):
        payload = _read_run_json(run_path)
        row = _base_row(payload, run_path)
        solver = payload.get("solver")
        if isinstance(solver, str):
            for declaration in solver_declarations.get(solver, []):
                value = _dot_path(payload, declaration["source"])
                row[declaration["name"]] = (
                    _json_compact(value) if isinstance(value, (dict, list)) else value
                )
        rows.append(row)
    return rows


def _fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    fieldnames = list(BASE_FIELDNAMES)
    seen = set(fieldnames)
    for row in rows:
        for key in row:
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    return fieldnames


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=_fieldnames(rows))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate main solver results")
    parser.add_argument("--results-root", default=str(DEFAULT_RESULTS_ROOT))
    args = parser.parse_args()

    results_root = Path(args.results_root)
    results_root.mkdir(parents=True, exist_ok=True)
    rows = _rows(results_root)
    summary = {
        "results_root": str(results_root),
        "row_count": len(rows),
        "rows": rows,
    }
    (results_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(results_root / "summary.csv", rows)
    print(f"wrote {len(rows)} rows to {results_root / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
