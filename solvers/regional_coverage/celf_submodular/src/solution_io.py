"""Output helpers for the regional-coverage CELF scaffold."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from candidates import StripCandidate


def write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_empty_solution(solution_dir: Path) -> Path:
    solution_path = solution_dir / "solution.json"
    write_json(solution_path, {"actions": []})
    return solution_path


def write_candidate_debug(
    solution_dir: Path,
    candidates: list[StripCandidate],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    *,
    limit: int,
) -> None:
    rows = []
    for candidate in candidates[: max(0, limit)]:
        rows.append(
            {
                **candidate.as_dict(),
                "covered_sample_indices": list(coverage_by_candidate.get(candidate.candidate_id, ())),
                "covered_sample_count": len(coverage_by_candidate.get(candidate.candidate_id, ())),
            }
        )
    write_json(solution_dir / "candidate_debug.json", rows)
