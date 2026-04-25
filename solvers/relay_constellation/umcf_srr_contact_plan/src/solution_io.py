"""Write solution.json and status.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .case_io import Satellite


def write_solution(
    solution_dir: Path,
    added_satellites: dict[str, Satellite],
    actions: list[dict[str, Any]],
) -> Path:
    """Write the primary benchmark solution file."""
    solution_dir.mkdir(parents=True, exist_ok=True)
    solution_path = solution_dir / "solution.json"

    added_list = []
    for sat_id in sorted(added_satellites.keys()):
        sat = added_satellites[sat_id]
        added_list.append({
            "satellite_id": sat.satellite_id,
            "x_m": float(sat.state_eci_m_mps[0]),
            "y_m": float(sat.state_eci_m_mps[1]),
            "z_m": float(sat.state_eci_m_mps[2]),
            "vx_m_s": float(sat.state_eci_m_mps[3]),
            "vy_m_s": float(sat.state_eci_m_mps[4]),
            "vz_m_s": float(sat.state_eci_m_mps[5]),
        })

    payload = {
        "added_satellites": added_list,
        "actions": actions,
    }
    solution_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return solution_path


def write_status(
    solution_dir: Path,
    timing_s: dict[str, float],
    summary: dict[str, Any],
) -> Path:
    """Write solver status and timing summary."""
    solution_dir.mkdir(parents=True, exist_ok=True)
    status_path = solution_dir / "status.json"

    payload = {
        "timing_s": timing_s,
        **summary,
    }
    status_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return status_path
