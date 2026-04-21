"""Solution and status writers for the MWIS scaffold."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_empty_solution(solution_dir: Path) -> Path:
    path = solution_dir / "solution.json"
    write_json(path, {"actions": []})
    return path
