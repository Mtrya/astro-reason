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
