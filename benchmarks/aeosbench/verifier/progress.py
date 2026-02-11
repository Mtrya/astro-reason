"""Task progress tracking and metrics computation for AEOS-Bench.

Mirrors constellation/task_managers.py progress logic and evaluators.
"""

from __future__ import annotations

import numpy as np

from .models import Constellation, TaskSet


class ProgressTracker:
    """Tracks task progress state machine over simulation timesteps.

    Mirrors TaskManager.record() logic from constellation/task_managers.py.
    """

    def __init__(self, constellation: Constellation, taskset: TaskSet):
        self.constellation = constellation
        self.taskset = taskset
        n_tasks = len(taskset.tasks)
        n_sats = len(constellation.satellites)

        # State arrays
        self.progress = np.zeros(n_tasks, dtype=np.int32)
        self.max_progress = np.zeros(n_tasks, dtype=np.int32)  # Track maximum progress
        self.succeeded = np.zeros(n_tasks, dtype=bool)
        self.completion_time = np.full(n_tasks, -1, dtype=np.int32)

        # Working timesteps per satellite (for PC calculation)
        self.working_timesteps = np.zeros(n_sats, dtype=np.int32)

        # Cache task data for faster access
        self._task_release = np.array([t.release_time for t in taskset.tasks])
        self._task_due = np.array([t.due_time for t in taskset.tasks])
        self._task_duration = np.array([t.duration for t in taskset.tasks])
        self._task_sensor_type = np.array([t.sensor_type for t in taskset.tasks])

    def get_ongoing_mask(self, t: int) -> np.ndarray:
        """Get boolean mask of ongoing tasks at timestep t.

        Ongoing = not succeeded AND released <= t <= due
        """
        released = self._task_release <= t
        not_due = t <= self._task_due
        return ~self.succeeded & released & not_due

    def get_ongoing_ids(self, t: int) -> set[int]:
        """Get set of ongoing task IDs at timestep t."""
        mask = self.get_ongoing_mask(t)
        return {self.taskset.tasks[i].id for i in np.where(mask)[0]}

    def record(self, t: int, visibility: np.ndarray, assignment: list[int]) -> None:
        """Record progress at timestep t.

        Args:
            t: Current timestep (0..3600)
            visibility: (n_sat, n_task) bool array of visibility
            assignment: List of task_id per satellite at this timestep
        """
        _ = len(assignment)  # assignment is used in the loop below

        # Get ongoing mask
        ongoing_mask = self.get_ongoing_mask(t)

        # Mask out non-ongoing tasks from visibility
        vis = visibility.copy()
        vis[:, ~ongoing_mask] = False

        # Any satellite sees the task
        any_visible = vis.any(axis=0)

        # Progress: increment by 1 if visible, reset to 0 if not visible
        # Formula: progress = (progress + 1) * any_visible
        self.progress = (self.progress + 1) * any_visible.astype(np.int32)

        # Track maximum progress (for PCR/WPCR)
        self.max_progress = np.maximum(self.max_progress, self.progress)

        # Check for newly completed tasks
        newly_succeeded = (~self.succeeded) & (self.progress >= self._task_duration)
        if newly_succeeded.any():
            self.succeeded |= newly_succeeded
            self.completion_time[newly_succeeded] = t

        # Count working timesteps per satellite (assignment != -1)
        for i, task_id in enumerate(assignment):
            if task_id != -1:
                self.working_timesteps[i] += 1

    def compute_metrics(self) -> dict[str, float]:
        """Compute all 6 metrics from progress tracking.

        Returns dict with CR, WCR, PCR, WPCR, TAT, PC.
        """
        # Get task data
        durations = self._task_duration
        n_tasks = len(self.taskset.tasks)

        # Use tracked max_progress (clamped to duration)
        max_progress = np.minimum(self.max_progress, durations)

        # CR: Completion Rate
        num_succeeded = self.succeeded.sum()
        CR = num_succeeded / n_tasks if n_tasks > 0 else 0.0

        # WCR: Weighted Completion Rate
        if durations.sum() > 0:
            WCR = durations[self.succeeded].sum() / durations.sum()
        else:
            WCR = 0.0

        # PCR: Partial Completion Rate (mean of progress/duration)
        pcr_per_task = max_progress / np.maximum(durations, 1)
        PCR = pcr_per_task.mean()

        # WPCR: Weighted Partial Completion Rate
        if durations.sum() > 0:
            WPCR = max_progress.sum() / durations.sum()
        else:
            WPCR = 0.0

        # TAT: Turn-Around Time (mean completion_time - release_time)
        if num_succeeded > 0:
            succeeded_mask = self.succeeded
            release_times = self._task_release[succeeded_mask]
            completion_times = self.completion_time[succeeded_mask]
            # Filter out tasks that weren't completed (completion_time = -1)
            valid = completion_times >= 0
            if valid.any():
                TAT = (completion_times[valid] - release_times[valid]).mean()
            else:
                TAT = 0.0
        else:
            TAT = 0.0

        # PC: Power Consumption
        sensor_powers = np.array([sat.sensor.power for sat in self.constellation.satellites])
        PC = (self.working_timesteps * sensor_powers).sum()

        return {
            "CR": float(CR),
            "WCR": float(WCR),
            "PCR": float(PCR),
            "WPCR": float(WPCR),
            "TAT": float(TAT),
            "PC": float(PC),
            "valid": True,
        }
