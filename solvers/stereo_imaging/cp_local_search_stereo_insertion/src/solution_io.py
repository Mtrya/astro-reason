"""Solution and debug artifact writers for the stereo_imaging CP/local-search solver."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from candidates import Candidate, CandidateSummary
from products import ProductLibrary


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


def write_debug_artifacts(
    solution_dir: Path,
    *,
    case_id: str,
    candidates: list[Candidate],
    candidate_summary: CandidateSummary,
    product_library: ProductLibrary,
    timing_seconds: dict[str, float],
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
