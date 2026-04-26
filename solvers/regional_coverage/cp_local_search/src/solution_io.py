"""Solution and debug artifact writing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .candidates import Candidate
from .case_io import Mission, iso_z
from .time_grid import offset_to_datetime


def candidate_to_action(mission: Mission, candidate: Candidate) -> dict[str, Any]:
    return {
        "type": "strip_observation",
        "satellite_id": candidate.satellite_id,
        "start_time": iso_z(offset_to_datetime(mission, candidate.start_offset_s)),
        "duration_s": candidate.duration_s,
        "roll_deg": candidate.roll_deg,
    }


def candidates_to_solution(mission: Mission, candidates: Iterable[Candidate]) -> dict[str, Any]:
    return {"actions": [candidate_to_action(mission, candidate) for candidate in candidates]}


def write_empty_solution(path: Path) -> None:
    write_json(path, {"actions": []})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

