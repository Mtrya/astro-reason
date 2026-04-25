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


def write_solution_from_candidates(
    solution_dir: Path,
    candidates_by_id: dict[str, StripCandidate],
    selected_candidate_ids: tuple[str, ...],
) -> Path:
    actions = []
    for candidate_id in selected_candidate_ids:
        candidate = candidates_by_id[candidate_id]
        actions.append(
            {
                "type": "strip_observation",
                "satellite_id": candidate.satellite_id,
                "start_time": candidate.start_time,
                "duration_s": candidate.duration_s,
                "roll_deg": candidate.roll_deg,
            }
        )
    solution_path = solution_dir / "solution.json"
    write_json(solution_path, {"actions": actions})
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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def write_celf_debug(
    solution_dir: Path,
    *,
    candidate_summary: dict[str, Any],
    celf_summary: dict[str, Any],
    iteration_rows: list[dict[str, Any]],
    selected_candidates: list[dict[str, Any]],
    write_iterations: bool,
) -> None:
    debug_dir = solution_dir / "debug"
    write_json(debug_dir / "candidate_summary.json", candidate_summary)
    write_json(debug_dir / "celf_summary.json", celf_summary)
    write_json(debug_dir / "selected_candidates.json", selected_candidates)
    if write_iterations:
        write_jsonl(debug_dir / "celf_iterations.jsonl", iteration_rows)
