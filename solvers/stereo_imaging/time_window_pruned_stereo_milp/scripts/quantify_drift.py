"""Quantify access-interval drift between coarse (30 s) and fine (15 s) time steps."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _intervals_to_dict(intervals):
    return [
        {"start": i.start.isoformat(), "end": i.end.isoformat(), "duration_s": (i.end - i.start).total_seconds()}
        for i in intervals
    ]


def run(case_dir: Path):
    from candidates import find_access_intervals
    from case_io import load_case

    if not case_dir.is_dir():
        raise FileNotFoundError(f"case directory not found: {case_dir}")

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
        "case": case_dir.name,
        "case_dir": str(case_dir),
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
    parser = argparse.ArgumentParser(description="Compare solver-local access intervals for one explicit case directory.")
    parser.add_argument("case_dir")
    parsed = parser.parse_args()
    run(Path(parsed.case_dir).resolve())
