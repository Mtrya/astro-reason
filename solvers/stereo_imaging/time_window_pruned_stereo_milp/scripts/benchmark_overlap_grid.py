"""Benchmark overlap grid density vs accuracy and runtime on a single case."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

CONFIGS = [
    {"id": "8x3", "overlap_grid_angles": 8, "overlap_grid_radii": 3},
    {"id": "12x4", "overlap_grid_angles": 12, "overlap_grid_radii": 4},
    {"id": "16x5", "overlap_grid_angles": 16, "overlap_grid_radii": 5},
    {"id": "24x6", "overlap_grid_angles": 24, "overlap_grid_radii": 6},
]


def run(case_dir: Path):
    from candidates import generate_candidates
    from case_io import load_case, load_solver_config
    from products import enumerate_products

    if not case_dir.is_dir():
        raise FileNotFoundError(f"case directory not found: {case_dir}")

    mission, satellites, targets = load_case(case_dir)
    base_cfg = load_solver_config(None)
    base_cfg["debug"] = False
    base_cfg["parallel_candidate_generation"] = False

    # Generate candidates once
    candidates, _, _ = generate_candidates(mission, satellites, targets, base_cfg)

    results = []
    for grid_cfg in CONFIGS:
        cfg = dict(base_cfg)
        cfg.update(grid_cfg)

        t0 = time.perf_counter()
        pairs, tris, summary = enumerate_products(candidates, satellites, targets, mission, cfg)
        elapsed = time.perf_counter() - t0

        results.append({
            "config_id": grid_cfg["id"],
            "overlap_grid_angles": grid_cfg["overlap_grid_angles"],
            "overlap_grid_radii": grid_cfg["overlap_grid_radii"],
            "total_pairs": summary.total_pairs,
            "valid_pairs": summary.valid_pairs,
            "total_tris": summary.total_tris,
            "valid_tris": summary.valid_tris,
            "product_enumeration_time_s": round(elapsed, 3),
        })

    out = {
        "case": case_dir.name,
        "case_dir": str(case_dir),
        "candidates": len(candidates),
        "results": results,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark overlap grid settings for one explicit case directory.")
    parser.add_argument("case_dir")
    parsed = parser.parse_args()
    run(Path(parsed.case_dir).resolve())
