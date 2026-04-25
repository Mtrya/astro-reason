"""Write solution.json, status.json, and debug artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _isoformat_z(value: Any) -> str:
    from datetime import datetime
    if isinstance(value, datetime):
        return value.astimezone(__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def write_solution(
    solution_dir: Path,
    *,
    added_satellites: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> None:
    solution_dir = Path(solution_dir)
    solution_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "added_satellites": added_satellites,
        "actions": actions,
    }
    (solution_dir / "solution.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_status(solution_dir: Path, status: dict[str, Any]) -> None:
    solution_dir = Path(solution_dir)
    solution_dir.mkdir(parents=True, exist_ok=True)
    (solution_dir / "status.json").write_text(
        json.dumps(status, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_debug_summary(solution_dir: Path, name: str, payload: dict[str, Any]) -> None:
    solution_dir = Path(solution_dir)
    debug_dir = solution_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / f"{name}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_reproduction_summary(
    solution_dir: Path,
    *,
    mclp_mode: str,
    scheduler_mode: str,
    parallel_mode: str,
    worker_count: int,
    time_budget_s: int,
) -> None:
    """Emit debug/reproduction_summary.json mapping implementation to paper sources."""
    payload = {
        "paper_components": {
            "mclp_candidate_selection": "Rogers et al. MCLP (greedy adaptation; optional small MILP)",
            "teg_contact_scheduler": "Gerard et al. TEG scheduling (greedy max-weight matching + bounded per-sample MILP)",
            "orbit_library": "Rogers-style finite orbital slot library",
            "link_geometry": "Gerard-style ISL visibility with Earth occultation",
            "parallel_propagation": "Embarrassingly parallel satellite propagation across workers",
        },
        "benchmark_adaptations": [
            "Rogers observation reward (coverage over targets) -> demand-window service-potential score (path diversity via ground+ISL connectivity)",
            "Rogers fixed cardinality N (exactly N satellites) -> benchmark max_added_satellites upper bound (<= K)",
            "Gerard capacity objective (maximize temporal flow) -> benchmark action-interval generator (ground_link and inter_satellite_link intervals)",
            "Gerard retargeting delay (pointing/acquisition overhead) -> NOT modeled; benchmark assumes instant link switching",
            "Benchmark verifier owns route allocation and latency scoring; solver submits only added_satellites and actions",
            "Rogers MILP over full candidate set -> greedy marginal-gain heuristic with optional small MILP for <=20 candidates",
            "Gerard full-horizon MILP scheduler -> bounded per-sample MILP with deterministic greedy fallback",
        ],
        "compute_envelope": {
            "parallel_mode": parallel_mode,
            "worker_count": worker_count,
            "time_budget_s": time_budget_s,
        },
        "mode_used": {
            "mclp_mode": mclp_mode,
            "scheduler_mode": scheduler_mode,
        },
    }
    write_debug_summary(solution_dir, "reproduction_summary", payload)
