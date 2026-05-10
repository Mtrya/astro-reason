"""Read main-solver baseline rows from repo-owned public sources."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAIN_SOLVER_README = REPO_ROOT / "experiments" / "main_solver" / "README.md"

NORMALIZATION: dict[str, dict[str, Any]] = {
    "satnet": {"u_rms_cap": 1.0, "u_max_cap": 1.0},
    "relay_constellation": {"min_added_satellites": 0, "latency_cap_ms": 1000.0},
    "revisit_constellation": {"min_satellites": 1},
    "regional_coverage": {"battery_capacity_mode": "max_satellite_capacity_wh"},
}

BENCHMARK_TITLES = {
    "SPOT5": "spot5",
    "SatNet": "satnet",
    "AEOSSP Standard": "aeossp_standard",
    "Stereo Imaging": "stereo_imaging",
    "Relay Constellation": "relay_constellation",
    "Revisit Constellation": "revisit_constellation",
    "Regional Coverage": "regional_coverage",
}

METRIC_NAMES = {
    "spot5": {"profit": "computed_profit", "weight": "computed_weight"},
    "satnet": {
        "u_rms": "u_rms",
        "u_max": "u_max",
        "total_h": "score_hours",
        "satisfied": "n_satisfied_requests",
        "run_h": "run_h",
        "train_h": "train_h",
    },
    "aeossp_standard": {"WCR": "WCR", "CR": "CR", "TAT": "TAT", "PC": "PC", "solve_s": "solve_s"},
    "stereo_imaging": {
        "coverage": "coverage_ratio",
        "quality": "normalized_quality",
        "solve_s": "solve_s",
    },
    "relay_constellation": {
        "service": "service_fraction",
        "worst_service": "worst_demand_service_fraction",
        "mean_ms": "mean_latency_ms",
        "p95_ms": "latency_p95_ms",
        "added": "num_added_satellites",
        "solve_s": "solve_s",
    },
    "revisit_constellation": {
        "sats": "num_satellites",
        "actions": "num_actions",
        "capped_gap_h": "capped_max_revisit_gap_hours",
        "solver_s": "solver_s",
    },
    "regional_coverage": {
        "coverage": "coverage_ratio",
        "weighted_coverage": "weighted_coverage_ratio",
        "min_battery_wh": "min_battery_wh",
        "solver_s": "solver_s",
    },
}

REGIONAL_NUM_ACTIONS = {
    ("regional_coverage_celf_submodular", "case_0001"): 64,
    ("regional_coverage_celf_submodular", "case_0002"): 64,
    ("regional_coverage_celf_submodular", "case_0003"): 61,
    ("regional_coverage_celf_submodular", "case_0004"): 39,
    ("regional_coverage_celf_submodular", "case_0005"): 44,
    ("regional_coverage_cp_local_search", "case_0001"): 16,
    ("regional_coverage_cp_local_search", "case_0002"): 19,
    ("regional_coverage_cp_local_search", "case_0003"): 39,
    ("regional_coverage_cp_local_search", "case_0004"): 12,
    ("regional_coverage_cp_local_search", "case_0005"): 9,
}


def load_baseline_data(path: Path = DEFAULT_MAIN_SOLVER_README) -> dict[str, Any]:
    if path.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
            raise SystemExit(f"Baseline data must contain a rows list: {path}")
        return data
    return _load_from_readme(path)


def _load_from_readme(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return {
        "source": path.relative_to(REPO_ROOT).as_posix() if path.is_relative_to(REPO_ROOT) else path.as_posix(),
        "source_commit": _source_commit(text),
        "description": "Main-solver baseline rows parsed from the Main Result Matrix tables.",
        "normalization": NORMALIZATION,
        "rows": _parse_rows(text),
    }


def _source_commit(text: str) -> str | None:
    match = re.search(r"matrix from commit `([^`]+)`", text)
    return match.group(1) if match else None


def _parse_rows(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    rows: list[dict[str, Any]] = []
    index = 0
    benchmark: str | None = None
    while index < len(lines):
        line = lines[index]
        if line.startswith("### "):
            benchmark = BENCHMARK_TITLES.get(line.removeprefix("### ").strip())
            index += 1
            continue
        if benchmark is not None and line.startswith("| method |"):
            headers = _split_row(line)
            index += 2
            while index < len(lines) and lines[index].startswith("| "):
                values = _split_row(lines[index])
                if len(values) == len(headers):
                    rows.append(_row_from_table(benchmark, dict(zip(headers, values))))
                index += 1
            benchmark = None
            continue
        index += 1
    return rows


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _row_from_table(benchmark: str, raw: dict[str, str]) -> dict[str, Any]:
    case_text = raw.get("case", "")
    if "/" in case_text:
        split, case_id = case_text.split("/", maxsplit=1)
    else:
        split, case_id = "test", case_text
    row: dict[str, Any] = {
        "benchmark": benchmark,
        "method": raw.get("method", ""),
        "split": split,
        "case_id": case_id,
    }
    if "valid" in raw:
        row["valid"] = raw["valid"].lower() == "true"
    if "evidence" in raw:
        row["evidence"] = raw["evidence"]
    metrics = {
        metric_name: value
        for header, metric_name in METRIC_NAMES.get(benchmark, {}).items()
        if (value := _parse_number(raw.get(header))) is not None
    }
    if benchmark == "regional_coverage":
        actions = REGIONAL_NUM_ACTIONS.get((str(row["method"]), str(row["case_id"])))
        if actions is not None:
            metrics["num_actions"] = actions
    row["metrics"] = metrics
    return row


def _parse_number(value: str | None) -> float | int | None:
    if value in (None, "", "-"):
        return None
    try:
        numeric = float(value)
    except ValueError:
        return None
    return int(numeric) if numeric.is_integer() else numeric
