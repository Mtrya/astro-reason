"""Case loading for the aeossp_standard visualizer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .geometry import parse_iso_utc


@dataclass(frozen=True)
class CaseData:
    case_dir: Path
    case_id: str
    mission: dict[str, Any]
    satellites: list[dict[str, Any]]
    tasks: list[dict[str, Any]]

    @property
    def horizon_start(self) -> datetime:
        return parse_iso_utc(self.mission["horizon_start"])

    @property
    def horizon_end(self) -> datetime:
        return parse_iso_utc(self.mission["horizon_end"])


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_case(case_dir: str | Path) -> CaseData:
    case_path = Path(case_dir).resolve()
    mission_doc = _load_yaml(case_path / "mission.yaml")
    satellites_doc = _load_yaml(case_path / "satellites.yaml")
    tasks_doc = _load_yaml(case_path / "tasks.yaml")

    mission = mission_doc.get("mission")
    satellites = satellites_doc.get("satellites")
    tasks = tasks_doc.get("tasks")
    if not isinstance(mission, dict):
        raise ValueError("mission.yaml must contain a top-level 'mission' mapping")
    if not isinstance(satellites, list):
        raise ValueError("satellites.yaml must contain a top-level 'satellites' list")
    if not isinstance(tasks, list):
        raise ValueError("tasks.yaml must contain a top-level 'tasks' list")

    case_id = str(mission.get("case_id") or case_path.name)
    return CaseData(
        case_dir=case_path,
        case_id=case_id,
        mission=mission,
        satellites=satellites,
        tasks=tasks,
    )
