"""Quantify access-interval drift between coarse (30 s) and fine (15 s) time steps."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from candidates import find_access_intervals
from case_io import load_case

REPO_ROOT = Path(__file__).resolve().parents[4]
CASES_ROOT = REPO_ROOT / "benchmarks" / "stereo_imaging" / "dataset" / "cases" / "test"


def _intervals_to_dict(intervals):
    return [
        {"start": i.start.isoformat(), "end": i.end.isoformat(), "duration_s": (i.end - i.start).total_seconds()}
        for i in intervals
    ]


def run(case_name: str):
    case_dir = CASES_ROOT / case_name
    if not case_dir.exists():
        print(f"Case not found: {case_dir}")
        return

    mission, satellites, targets = load_case(case_dir)

    results = []
    for sat in satellites.values():
        for target in targets.values():
            intervals_30 = find_access_intervals(sat, target, mission, time_step_s=30.0)
            intervals_15 = find_access_intervals(sat, target, mission, time_step_s=15.0)
            if not intervals_30 and not intervals_15:
                continue

            drift = len(intervals_15) - len(intervals_30)
            duration_diff = sum((i.end - i.start).total_seconds() for i in intervals_15) - sum(
                (i.end - i.start).total_seconds() for i in intervals_30
            )

            results.append({
                "sat_id": sat.id,
                "target_id": target.id,
                "intervals_30s": len(intervals_30),
                "intervals_15s": len(intervals_15),
                "count_drift": drift,
                "total_duration_diff_s": round(duration_diff, 3),
                "detail_30s": _intervals_to_dict(intervals_30),
                "detail_15s": _intervals_to_dict(intervals_15),
            })

    out = {
        "case": case_name,
        "summary": {
            "pairs_checked": len(satellites) * len(targets),
            "pairs_with_access": len(results),
            "total_count_drift": sum(r["count_drift"] for r in results),
            "total_duration_diff_s": round(sum(r["total_duration_diff_s"] for r in results), 3),
        },
        "results": results,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    case = sys.argv[1] if len(sys.argv) > 1 else "case_0001"
    run(case)
