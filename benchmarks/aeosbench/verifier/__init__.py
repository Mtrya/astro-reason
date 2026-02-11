"""BSK-based verifier for AEOS-Bench.

This verifier uses the official Basilisk (bsk) package to compute ground-truth
metrics from satellite constellation scheduling solutions.

Example:
    from verifier_bsk import AEOSVerifierBSK

    with open("constellation.json") as f:
        constellation = json.load(f)
    with open("taskset.json") as f:
        taskset = json.load(f)

    verifier = AEOSVerifierBSK(constellation, taskset)

    # assignments: dict[int, list[int]] - sat_id -> task_id per timestep
    metrics = verifier.verify(assignments)

    print(f"CR: {metrics['CR']:.4f}")
"""

from __future__ import annotations

from typing import Any

from .constants import INTERVAL, NUM_TIMESTEPS
from .models import load_constellation, load_taskset
from .progress import ProgressTracker
from .simulation import BSKEnvironment, sec2nano


class AEOSVerifierBSK:
    """BSK-based verifier for AEOS-Bench solutions.

    Computes ground-truth metrics (CR, WCR, PCR, WPCR, TAT, PC) using
    the official Basilisk astrodynamics simulation.
    """

    def __init__(
        self,
        constellation_json: dict[str, Any],
        taskset_json: dict[str, Any],
    ):
        """Initialize verifier with case data.

        Args:
            constellation_json: Parsed JSON dict with constellation definition.
            taskset_json: Parsed JSON dict with task set definition.
        """
        self.constellation = load_constellation(constellation_json)
        self.taskset = load_taskset(taskset_json)

    def verify(self, assignments: dict[int, list[int]]) -> dict[str, float]:
        """Verify a solution and compute metrics.

        Runs the full BSK simulation following the exact loop structure from
        generate_fixtures.py:replay_and_extract():

        For t in 0..3600 (3601 iterations):
            1. Get assignments for this timestep
            2. Read visibility from BSK (current state)
            3. Update progress tracking
            4. Determine toggles and target locations
            5. Apply actions to BSK
            6. Advance BSK to next time

        Args:
            assignments: Dict mapping satellite_id -> list of task assignments
                per timestep. -1 means idle. Each list must have 3601 entries
                (indices 0..3600).

        Returns:
            Dict with metrics: CR, WCR, PCR, WPCR, TAT, PC, valid.
        """
        # Create BSK environment
        env = BSKEnvironment(self.constellation, self.taskset)

        # Create progress tracker
        tracker = ProgressTracker(self.constellation, self.taskset)

        # Get sorted satellite IDs for consistent ordering
        sat_ids = sorted(assignments.keys())

        # Build task lookup
        task_id_to_task = {t.id: t for t in self.taskset.tasks}

        # Validate assignments
        for sid in sat_ids:
            if len(assignments[sid]) != NUM_TIMESTEPS:
                return {
                    "CR": 0.0,
                    "WCR": 0.0,
                    "PCR": 0.0,
                    "WPCR": 0.0,
                    "TAT": 0.0,
                    "PC": 0.0,
                    "valid": False,
                }

        # Main simulation loop - 3601 iterations (0..3600)
        for t in range(NUM_TIMESTEPS):
            # Get ongoing tasks for this timestep
            ongoing_ids = tracker.get_ongoing_ids(t)

            # Get assignment for this timestep
            assignment_t = [assignments[sid][t] for sid in sat_ids]

            # Step 1: Read visibility from BSK (before any actions)
            # This reads current BSK state (already initialized at t=0)
            vis = env.is_visible(self.taskset)

            # Step 2: Update progress tracking
            tracker.record(t, vis, assignment_t)

            # Step 3: Determine toggles and target locations
            toggles = []
            target_locations = []

            for i, sat_id in enumerate(sat_ids):
                task_id = assignment_t[i]

                # Toggle logic: should_be_enabled != is_enabled
                should_be_enabled = task_id != -1
                is_enabled = env.satellites[i].is_sensor_enabled
                toggles.append(should_be_enabled != is_enabled)

                # Target location: only if task is ongoing
                if task_id in ongoing_ids and task_id in task_id_to_task:
                    coord = task_id_to_task[task_id].coordinate
                    target_locations.append(coord)
                else:
                    target_locations.append(None)

            # Step 4: Apply actions to BSK
            env.take_actions(toggles, target_locations)

            # Step 5: Advance BSK (t -> t+1, BSK to (t+1)*INTERVAL)
            # After step(), BSK state reflects time (t+1) seconds from epoch
            env.step(sec2nano((t + 1) * INTERVAL))

        # Compute and return metrics
        metrics = tracker.compute_metrics()

        # DEBUG: Store tracker for inspection
        self._last_tracker = tracker

        return metrics


def verify_solution(
    constellation_json: dict[str, Any],
    taskset_json: dict[str, Any],
    assignments: dict[int, list[int]],
) -> dict[str, float]:
    """Convenience function to verify a solution without creating a class instance.

    Args:
        constellation_json: Parsed JSON dict with constellation definition.
        taskset_json: Parsed JSON dict with task set definition.
        assignments: Dict mapping satellite_id -> list of task assignments.

    Returns:
        Dict with metrics: CR, WCR, PCR, WPCR, TAT, PC, valid.
    """
    verifier = AEOSVerifierBSK(constellation_json, taskset_json)
    return verifier.verify(assignments)


__all__ = ["AEOSVerifierBSK", "verify_solution"]
