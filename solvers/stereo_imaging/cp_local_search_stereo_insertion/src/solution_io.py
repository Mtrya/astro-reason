"""Solution and debug artifact writers for the stereo_imaging CP/local-search solver."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from candidates import Candidate, CandidateSummary
from products import ProductLibrary
from sequence import SequenceState


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_solution(solution_dir: Path) -> Path:
    path = solution_dir / "solution.json"
    write_json(path, {"actions": []})
    return path


def write_solution_from_state(solution_dir: Path, state: SequenceState) -> Path:
    """Convert a SequenceState to a benchmark-shaped solution.json."""
    actions: list[dict[str, Any]] = []
    for sat_id, seq in sorted(state.sequences.items()):
        for obs in seq.observations:
            actions.append(
                {
                    "type": "observation",
                    "satellite_id": obs.satellite_id,
                    "target_id": obs.target_id,
                    "start_time": obs.start.isoformat().replace("+00:00", "Z"),
                    "end_time": obs.end.isoformat().replace("+00:00", "Z"),
                    "off_nadir_along_deg": obs.off_nadir_along_deg,
                    "off_nadir_across_deg": obs.off_nadir_across_deg,
                }
            )
    # Deterministic ordering
    actions.sort(key=lambda a: (a["satellite_id"], a["start_time"]))
    path = solution_dir / "solution.json"
    write_json(path, {"actions": actions})
    return path


def write_debug_artifacts(
    solution_dir: Path,
    *,
    case_id: str,
    candidates: list[Candidate],
    candidate_summary: CandidateSummary,
    product_library: ProductLibrary,
    timing_seconds: dict[str, float],
    sequence_state: SequenceState | None = None,
    seed_result: Any | None = None,
) -> None:
    debug_dir = solution_dir / "debug"
    write_json(
        debug_dir / "candidates.json",
        [c.as_dict() for c in candidates],
    )
    write_json(
        debug_dir / "candidate_summary.json",
        {
            "case_id": case_id,
            "summary": candidate_summary.as_dict(),
        },
    )
    write_json(
        debug_dir / "products.json",
        [p.as_dict() for p in product_library.products],
    )
    write_json(
        debug_dir / "product_summary.json",
        {
            "case_id": case_id,
            "summary": product_library.summary.as_dict(),
        },
    )
    if sequence_state is not None:
        write_json(
            debug_dir / "sequence_state.json",
            {
                "case_id": case_id,
                "state": sequence_state.as_dict(),
            },
        )
    if seed_result is not None:
        write_json(
            debug_dir / "seed_accepted.json",
            [r.as_dict() for r in seed_result.accepted_products],
        )
        write_json(
            debug_dir / "seed_rejected.json",
            [r.as_dict() for r in seed_result.rejected_records],
        )
        write_json(
            debug_dir / "seed_summary.json",
            {
                "case_id": case_id,
                "seed": seed_result.as_dict(),
            },
        )
