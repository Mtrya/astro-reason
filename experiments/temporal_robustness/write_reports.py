#!/usr/bin/env python3
"""Write temporal robustness comparison reports."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))

from experiments._shared import aggregate as shared_aggregate
from experiments._shared import write_reports as shared_reports

FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
DEFAULT_BASELINES = FAMILY_DIR / "baselines" / "main_solver.yaml"
DEFAULT_REPORTS_DIR = FAMILY_DIR / "reports"
MAIN_AGENTIC_ROOT = REPO_ROOT / "results" / "agent_runs" / "experiments" / "main_agentic" / "matrix"
TEMPORAL_ROOT = REPO_ROOT / "results" / "agent_runs" / "experiments" / "temporal_robustness"
BENCHMARK = "aeossp_standard"
AGENT_SYSTEMS = ("codex", "opencode_dpsk")
SOLVER_SYSTEMS = ("aeossp_standard_greedy_lns", "aeossp_standard_mwis_conflict_graph")
SPLITS = ("test", "test_horizon_2022")
METRICS = ("WCR", "CR", "TAT", "PC")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write human-readable temporal robustness comparison reports."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--baseline-data", type=Path, default=DEFAULT_BASELINES)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    return parser.parse_args(argv)


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"YAML file must be a mapping: {path}")
    return data


def _metric(metrics: dict[str, Any], name: str) -> float | None:
    value = shared_aggregate.coerce_numeric(metrics.get(name))
    return float(value) if value is not None else None


def _verifier_metrics(payload: dict[str, Any] | None) -> dict[str, float | None]:
    if payload is None:
        return {metric: None for metric in METRICS}
    verifier = payload.get("verifier")
    if not isinstance(verifier, dict):
        return {metric: None for metric in METRICS}
    metrics = verifier.get("metrics")
    if not isinstance(metrics, dict):
        return {metric: None for metric in METRICS}
    return {metric: _metric(metrics, metric) for metric in METRICS}


def _agent_run_path(*, split: str, harness: str, case_id: str, config_name: str) -> Path:
    if split == "test":
        return MAIN_AGENTIC_ROOT / BENCHMARK / harness / split / case_id / "run.json"
    return TEMPORAL_ROOT / config_name / split / BENCHMARK / harness / case_id / "run.json"


def _agent_row(*, split: str, harness: str, case_id: str, config_name: str) -> dict[str, Any]:
    path = _agent_run_path(split=split, harness=harness, case_id=case_id, config_name=config_name)
    payload = shared_aggregate.read_run_json(path)
    verifier = payload.get("verifier") if isinstance(payload, dict) and isinstance(payload.get("verifier"), dict) else {}
    metrics = _verifier_metrics(payload)
    valid = verifier.get("valid") if isinstance(verifier.get("valid"), bool) else None
    return {
        "kind": "agent",
        "system": harness,
        "split": split,
        "case_id": case_id,
        "valid": valid,
        "status": payload.get("overall_status", "missing_artifact") if payload else "missing_artifact",
        "duration_seconds": payload.get("duration_seconds") if payload else None,
        "source": _display_path(path),
        **metrics,
    }


def _solver_rows(baseline_data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = baseline_data.get("rows")
    if not isinstance(rows, list):
        raise SystemExit("Baseline data must contain a rows list.")

    records: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        method = row.get("method")
        split = row.get("split")
        case_id = row.get("case_id")
        metrics = row.get("metrics")
        if method not in SOLVER_SYSTEMS or split not in SPLITS or not isinstance(case_id, str):
            continue
        if not isinstance(metrics, dict):
            metrics = {}
        records.append(
            {
                "kind": "solver",
                "system": method,
                "split": split,
                "case_id": case_id,
                "valid": row.get("valid") if isinstance(row.get("valid"), bool) else None,
                "status": row.get("status", "unknown"),
                "duration_seconds": None,
                "source": "baselines/main_solver.yaml",
                **{metric: _metric(metrics, metric) for metric in METRICS},
            }
        )
    return records


def _display_path(path: Path) -> str:
    if path.is_relative_to(REPO_ROOT):
        return path.relative_to(REPO_ROOT).as_posix()
    return path.as_posix()


def _case_ids(config: dict[str, Any]) -> tuple[str, ...]:
    cases = config.get("cases")
    if not isinstance(cases, list) or any(not isinstance(case, str) for case in cases):
        raise SystemExit("Config cases must be a list of strings.")
    return tuple(cases)


def _config_name(config_path: Path) -> str:
    return config_path.stem


def _all_rows(config: dict[str, Any], config_path: Path, baseline_data: dict[str, Any]) -> list[dict[str, Any]]:
    case_ids = _case_ids(config)
    config_name = _config_name(config_path)
    rows: list[dict[str, Any]] = []
    for split in SPLITS:
        for harness in AGENT_SYSTEMS:
            for case_id in case_ids:
                rows.append(_agent_row(split=split, harness=harness, case_id=case_id, config_name=config_name))
    rows.extend(_solver_rows(baseline_data))
    return rows


def _mean(values: list[float]) -> float | None:
    stats = shared_aggregate.metric_stats(values)
    mean = stats["mean"]
    return float(mean) if mean is not None else None


def _format(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return shared_reports.format_value(str(value))
    return str(value)


def _table(headers: list[str], rows: list[list[str]], *, numeric_from: int = 0) -> list[str]:
    return shared_reports.table(headers, rows, numeric_from=numeric_from)


def _system_label(system: str) -> str:
    return system.replace("aeossp_standard_", "")


def _summary_rows(rows: list[dict[str, Any]]) -> list[list[str]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["kind"]), str(row["system"]), str(row["split"]))].append(row)

    table_rows: list[list[str]] = []
    for kind in ("agent", "solver"):
        systems = AGENT_SYSTEMS if kind == "agent" else SOLVER_SYSTEMS
        for system in systems:
            values = [_system_label(system), kind]
            for split in SPLITS:
                group = grouped.get((kind, system, split), [])
                valid_values = [row["valid"] for row in group if isinstance(row.get("valid"), bool)]
                metric_means = {
                    metric: _mean([row[metric] for row in group if isinstance(row.get(metric), float)])
                    for metric in METRICS
                }
                values.extend(
                    [
                        str(len(group)),
                        str(sum(1 for value in valid_values if value)),
                        _format(metric_means["WCR"]),
                        _format(metric_means["CR"]),
                        _format(metric_means["TAT"]),
                        _format(metric_means["PC"]),
                    ]
                )
            table_rows.append(values)
    return table_rows


def _summary_headers() -> list[str]:
    headers = ["System", "Kind"]
    for split in SPLITS:
        headers.extend(
            [
                f"{split} Runs",
                f"{split} Valid",
                f"{split} Mean WCR",
                f"{split} Mean CR",
                f"{split} Mean TAT",
                f"{split} Mean PC",
            ]
        )
    return headers


def _split_case_table_rows(rows: list[dict[str, Any]], *, split: str) -> list[list[str]]:
    filtered = [row for row in rows if row.get("split") == split]
    by_key = {(row["kind"], row["system"], row["case_id"]): row for row in filtered}
    case_ids = sorted({str(row["case_id"]) for row in filtered})
    table_rows: list[list[str]] = []
    for case_id in case_ids:
        for kind in ("agent", "solver"):
            systems = AGENT_SYSTEMS if kind == "agent" else SOLVER_SYSTEMS
            for system in systems:
                row = by_key.get((kind, system, case_id))
                if row is None:
                    values = [case_id, kind, _system_label(system), "-", "-", "-", "-", "-", "-"]
                else:
                    values = [
                        case_id,
                        kind,
                        _system_label(system),
                        _format(row.get("valid")),
                        _format(row.get("WCR")),
                        _format(row.get("CR")),
                        _format(row.get("TAT")),
                        _format(row.get("PC")),
                        _format(row.get("status")),
                    ]
                table_rows.append(values)
    return table_rows


def _write_report(*, rows: list[dict[str, Any]], reports_dir: Path, config: dict[str, Any]) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Temporal Robustness",
        "",
        "AEOSSP comparison across the default `test` split and `test_horizon_2022` split.",
        "",
        "`test` agent rows are reused from `main_agentic`; `test_horizon_2022` agent rows come from this experiment.",
        "Solver rows come from `baselines/main_solver.yaml`.",
        "Case identifiers are split-scoped: `test/case_0001` and `test_horizon_2022/case_0001` are different cases.",
        "",
        "## Summary",
        "",
    ]
    lines.extend(
        _table(
            _summary_headers(),
            _summary_rows(rows),
            numeric_from=2,
        )
    )
    lines.append("")

    for split in SPLITS:
        lines.extend([f"## {split} Cases", ""])
        lines.extend(
            _table(
                ["Case", "Kind", "System", "Valid", "WCR", "CR", "TAT", "PC", "Status"],
                _split_case_table_rows(rows, split=split),
                numeric_from=4,
            )
        )
        lines.append("")

    (reports_dir / "aeossp_standard.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.resolve()
    config = _load_yaml(config_path)
    baseline_data = _load_yaml(args.baseline_data.resolve())
    rows = _all_rows(config, config_path, baseline_data)
    _write_report(rows=rows, reports_dir=args.reports_dir.resolve(), config=config)
    print(f"Wrote {_display_path(args.reports_dir.resolve() / 'aeossp_standard.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
