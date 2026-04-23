"""Solution and status writers for the greedy-LNS scaffold."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .candidates import Candidate


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


def candidates_to_actions(candidates: list[Candidate]) -> list[dict[str, str]]:
    return [
        {
            "type": "observation",
            "satellite_id": candidate.satellite_id,
            "task_id": candidate.task_id,
            "start_time": candidate.start_time,
            "end_time": candidate.end_time,
        }
        for candidate in sorted(
            candidates,
            key=lambda item: (item.start_offset_s, item.satellite_id, item.task_id),
        )
    ]


def write_solution(solution_dir: Path, candidates: list[Candidate]) -> Path:
    path = solution_dir / "solution.json"
    write_json(path, {"actions": candidates_to_actions(candidates)})
    return path
