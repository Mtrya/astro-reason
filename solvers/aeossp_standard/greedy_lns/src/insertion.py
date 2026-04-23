"""Deterministic greedy insertion scheduler for AEOSSP candidates."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

from candidates import Candidate
from case_io import AeosspCase
from geometry import PropagationContext, initial_slew_feasible
from transition import TransitionVectorCache, transition_result


@dataclass(frozen=True, slots=True)
class InsertionConfig:
    max_repair_iterations: int = 200

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "InsertionConfig":
        payload = payload or {}
        return cls(max_repair_iterations=max(0, int(payload.get("max_repair_iterations", 200))))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InsertionStats:
    candidates_considered: int = 0
    candidates_inserted: int = 0
    candidates_skipped_duplicate_task: int = 0
    candidates_rejected_overlap: int = 0
    candidates_rejected_transition: int = 0
    candidates_rejected_initial_slew: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InsertionResult:
    selected: list[Candidate]
    stats: InsertionStats

    def as_dict(self) -> dict[str, Any]:
        return {
            "selected_count": len(self.selected),
            "stats": self.stats.as_dict(),
        }


def _candidate_sort_key(candidate: Candidate) -> tuple[float, ...]:
    """Sort key: higher utility first, then tie-break tuple."""
    return (-candidate.utility, candidate.utility_tie_break)


def _insertion_position(
    satellite_schedule: list[Candidate],
    candidate: Candidate,
) -> int:
    """Return the index at which *candidate* should be inserted to keep the
    schedule ordered by ``(start_offset_s, end_offset_s, candidate_id)``.
    """
    return bisect_left(
        satellite_schedule,
        (candidate.start_offset_s, candidate.end_offset_s, candidate.candidate_id),
        key=lambda item: (item.start_offset_s, item.end_offset_s, item.candidate_id),
    )


def greedy_insertion(
    case: AeosspCase,
    candidates: list[Candidate],
    config: InsertionConfig | None = None,
) -> InsertionResult:
    """Build a schedule by greedily inserting candidates in utility order.

    Conflicts handled:
    - duplicate task (a task may be scheduled at most once)
    - same-satellite overlap
    - same-satellite insufficient transition gap
    - first-action initial slew from nadir

    Battery feasibility is *not* checked during insertion; run solver-local
    validation/repair afterwards if needed.
    """
    config = config or InsertionConfig()
    stats = InsertionStats()

    step_s = float(min(case.mission.action_time_step_s, case.mission.geometry_sample_step_s))
    propagation = PropagationContext(case.satellites, step_s=step_s)
    vector_cache = TransitionVectorCache(case, propagation)

    sorted_candidates = sorted(candidates, key=_candidate_sort_key)

    # satellite_id -> ordered list of selected candidates
    satellite_schedules: dict[str, list[Candidate]] = {
        satellite_id: [] for satellite_id in sorted(case.satellites)
    }
    scheduled_tasks: set[str] = set()

    for candidate in sorted_candidates:
        stats.candidates_considered += 1

        if candidate.task_id in scheduled_tasks:
            stats.candidates_skipped_duplicate_task += 1
            continue

        schedule = satellite_schedules[candidate.satellite_id]
        pos = _insertion_position(schedule, candidate)

        # --- overlap checks ---
        left = schedule[pos - 1] if pos > 0 else None
        right = schedule[pos] if pos < len(schedule) else None

        if left is not None and left.end_offset_s > candidate.start_offset_s:
            stats.candidates_rejected_overlap += 1
            continue
        if right is not None and candidate.end_offset_s > right.start_offset_s:
            stats.candidates_rejected_overlap += 1
            continue

        # --- transition checks ---
        transition_ok = True
        if left is not None:
            result = transition_result(left, candidate, case=case, vector_cache=vector_cache)
            if not result.feasible:
                stats.candidates_rejected_transition += 1
                transition_ok = False
        if transition_ok and right is not None:
            result = transition_result(candidate, right, case=case, vector_cache=vector_cache)
            if not result.feasible:
                stats.candidates_rejected_transition += 1
                transition_ok = False
        if not transition_ok:
            continue

        # --- initial slew check (only if first on this satellite) ---
        if left is None:
            start_time = case.mission.horizon_start + timedelta(seconds=candidate.start_offset_s)
            if not initial_slew_feasible(
                mission=case.mission,
                satellite=case.satellites[candidate.satellite_id],
                task=case.tasks[candidate.task_id],
                propagation=propagation,
                start_time=start_time,
            ):
                stats.candidates_rejected_initial_slew += 1
                continue

        schedule.insert(pos, candidate)
        scheduled_tasks.add(candidate.task_id)
        stats.candidates_inserted += 1

    # Flatten schedules into a single sorted list
    selected = [
        candidate
        for satellite_id in sorted(satellite_schedules)
        for candidate in satellite_schedules[satellite_id]
    ]

    return InsertionResult(selected=selected, stats=stats)
