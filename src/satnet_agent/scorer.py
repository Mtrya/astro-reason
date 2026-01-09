"""
SatNet Official Scorer

Uses the upstream SchedulingSimulator to replay and score plans,
ensuring 100% alignment with the official benchmark.
"""

import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

import sys
from collections import defaultdict

# Ensure satnet is in path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SATNET_PATH = PROJECT_ROOT / "satnet"
if str(SATNET_PATH) not in sys.path:
    sys.path.insert(0, str(SATNET_PATH))

import satnet
from satnet.simulator.prob_handler import ProbHandler
from satnet.simulator.scheduling_simulator import SchedulingSimulator
from satnet.envs import NORMAL


@dataclass
class SatNetScore:
    """Score result from official simulator replay."""
    u_max: float
    u_rms: float
    u_avg: float
    requests_satisfied: int
    requests_total: int
    hours_allocated: float
    valid: bool
    errors: List[str] = field(default_factory=list)


def load_schedule(schedule_path: str) -> list:
    """Load schedule in official format."""
    with open(schedule_path) as f:
        return json.load(f)


def initialize_simulator(week: int, year: int = 2018) -> SchedulingSimulator:
    """Initialize official simulator for a given week."""
    ph = ProbHandler(satnet.problems[year])
    config = {
        "prob_handler": ph,
        "week": week,
        "shuffle_requests": False,
        "shuffle_antennas": False,
        "allow_splitting": True,
    }
    return SchedulingSimulator(config)


def replay_schedule(sim: SchedulingSimulator, schedule: list) -> List[str]:
    """Replay schedule through simulator, return list of errors."""
    errors = []
    
    # helper: group split tracks (for arraying)
    # Map: track_id -> list of entries
    grouped_tracks = defaultdict(list)
    for track in schedule:
        grouped_tracks[track["TRACK_ID"]].append(track)
        
    # We must replay in some order. The simulator handles tracks one by one.
    
    sorted_track_ids = sorted(
        grouped_tracks.keys(),
        key=lambda tid: grouped_tracks[tid][0]["START_TIME"]
    )

    for track_id in sorted_track_ids:
        parts = grouped_tracks[track_id]
        
        # All parts should have same times
        first = parts[0]
        trx_on = first["TRACKING_ON"] - int(sim.start_date)
        trx_off = first["TRACKING_OFF"] - int(sim.start_date)
        
        # Combine antennas
        # e.g. DSS-54, DSS-65 -> "DSS-54_DSS-65"
        # Must be sorted alphabetically to match satnet resources
        antennas = sorted([part["RESOURCE"] for part in parts])
        antenna_str = "_".join(antennas)
        
        action = {
            "track_id": track_id,
            "antennas": antenna_str,
            "trx_on": trx_on,
            "trx_off": trx_off,
        }
        
        try:
            result = sim.advance(action)
            if NORMAL not in sim.status:
                status_codes = list(sim.status)
                errors.append(f"Track {track_id}: status={status_codes}")
        except Exception as e:
            # import traceback
            # traceback.print_exc()
            errors.append(f"Track {track_id}: {e}")
    
    return errors


def score_plan(schedule_path: str, week: int, year: int = 2018) -> SatNetScore:
    """Score a plan using official simulator."""
    schedule = load_schedule(schedule_path)
    sim = initialize_simulator(week, year)
    errors = replay_schedule(sim, schedule)
    
    hours_allocated = (
        sum(sim.mission_requested_duration.values()) - 
        sum(sim.mission_remaining_duration.values())
    ) / 3600
    
    return SatNetScore(
        u_max=float(sim.U_max),
        u_rms=float(sim.U_rms),
        u_avg=float(sim.U_i.mean()),
        requests_satisfied=sim.num_reqs_satisfied,
        requests_total=sim.num_requests,
        hours_allocated=round(hours_allocated, 2),
        valid=len(errors) == 0,
        errors=errors,
    )


def score_plan_safe(schedule_path: str, week: int, year: int = 2018) -> SatNetScore | None:
    """Score a plan, returning None if invalid or error occurs."""
    try:
        score = score_plan(schedule_path, week, year)
        return score if score.valid else None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Score SatNet plan using official simulator")
    parser.add_argument("schedule", help="Path to schedule JSON")
    parser.add_argument("--week", type=int, default=40, help="Week number")
    parser.add_argument("--year", type=int, default=2018, help="Year")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    score = score_plan(args.schedule, args.week, args.year)
    
    if args.json:
        import json as json_module
        result = {
            "u_max": score.u_max,
            "u_rms": score.u_rms,
            "u_avg": score.u_avg,
            "requests_satisfied": score.requests_satisfied,
            "requests_total": score.requests_total,
            "hours_allocated": score.hours_allocated,
            "valid": score.valid,
            "errors": score.errors[:10] if score.errors else [],
        }
        print(json_module.dumps(result, indent=2))
    else:
        print(f"U_max: {score.u_max:.4f}")
        print(f"U_rms: {score.u_rms:.4f}")
        print(f"U_avg: {score.u_avg:.4f}")
        print(f"Satisfied: {score.requests_satisfied}/{score.requests_total}")
        print(f"Hours allocated: {score.hours_allocated:.2f}")
        print(f"Valid: {score.valid}")
        if score.errors:
            print(f"Errors ({len(score.errors)} total):")
            for err in score.errors[:5]:
                print(f"  - {err}")
            if len(score.errors) > 5:
                print(f"  ... and {len(score.errors) - 5} more")


if __name__ == "__main__":
    main()
