"""Benchmark-shaped revisit-gap helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .case_io import RevisitCase


def revisit_gaps_hours(
    horizon_start: datetime,
    horizon_end: datetime,
    observation_midpoints: list[datetime],
) -> list[float]:
    unique_midpoints = sorted(set(observation_midpoints))
    times = [horizon_start, *unique_midpoints, horizon_end]
    return [
        (right - left).total_seconds() / 3600.0
        for left, right in zip(times, times[1:])
    ]


def max_revisit_gap_hours(
    horizon_start: datetime,
    horizon_end: datetime,
    observation_midpoints: list[datetime],
) -> float:
    gaps = revisit_gaps_hours(horizon_start, horizon_end, observation_midpoints)
    return max(gaps) if gaps else 0.0


@dataclass(frozen=True, slots=True)
class TargetGapScore:
    target_id: str
    expected_revisit_period_hours: float
    mean_revisit_gap_hours: float
    max_revisit_gap_hours: float
    observation_count: int

    @property
    def threshold_violated(self) -> bool:
        return self.max_revisit_gap_hours > self.expected_revisit_period_hours

    @property
    def capped_max_revisit_gap_hours(self) -> float:
        return max(self.max_revisit_gap_hours, self.expected_revisit_period_hours)

    def as_dict(self) -> dict[str, float | int]:
        return {
            "expected_revisit_period_hours": self.expected_revisit_period_hours,
            "mean_revisit_gap_hours": self.mean_revisit_gap_hours,
            "max_revisit_gap_hours": self.max_revisit_gap_hours,
            "observation_count": self.observation_count,
        }


def _target_gap_score(
    *,
    case: RevisitCase,
    target_id: str,
    unique_midpoints: list[datetime],
) -> TargetGapScore:
    target = case.targets[target_id]
    gaps = revisit_gaps_hours(case.horizon_start, case.horizon_end, unique_midpoints)
    mean_gap = sum(gaps) / len(gaps)
    max_gap = max(gaps)
    return TargetGapScore(
        target_id=target_id,
        expected_revisit_period_hours=target.expected_revisit_period_hours,
        mean_revisit_gap_hours=mean_gap,
        max_revisit_gap_hours=max_gap,
        observation_count=len(unique_midpoints),
    )


@dataclass(frozen=True, slots=True)
class GapScore:
    capped_max_revisit_gap_hours: float
    max_revisit_gap_hours: float
    mean_revisit_gap_hours: float
    threshold_violation_count: int
    target_gap_summary: dict[str, TargetGapScore]

    @property
    def optimization_key(self) -> tuple[int, float, float, float]:
        """Lower-is-better key for greedy marginal improvement."""
        return (
            self.threshold_violation_count,
            self.capped_max_revisit_gap_hours,
            self.max_revisit_gap_hours,
            self.mean_revisit_gap_hours,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "capped_max_revisit_gap_hours": self.capped_max_revisit_gap_hours,
            "max_revisit_gap_hours": self.max_revisit_gap_hours,
            "mean_revisit_gap_hours": self.mean_revisit_gap_hours,
            "threshold_violation_count": self.threshold_violation_count,
            "target_gap_summary": {
                target_id: score.as_dict()
                for target_id, score in self.target_gap_summary.items()
            },
        }


def _aggregate_gap_score(
    case: RevisitCase,
    target_gap_summary: dict[str, TargetGapScore],
) -> GapScore:
    capped_max_values: list[float] = []
    max_values: list[float] = []
    mean_values: list[float] = []
    threshold_violation_count = 0
    ordered_summary: dict[str, TargetGapScore] = {}

    for target_id in case.targets:
        score = target_gap_summary[target_id]
        ordered_summary[target_id] = score
        capped_max_values.append(score.capped_max_revisit_gap_hours)
        max_values.append(score.max_revisit_gap_hours)
        mean_values.append(score.mean_revisit_gap_hours)
        if score.threshold_violated:
            threshold_violation_count += 1

    return GapScore(
        capped_max_revisit_gap_hours=max(capped_max_values) if capped_max_values else 0.0,
        max_revisit_gap_hours=max(max_values) if max_values else 0.0,
        mean_revisit_gap_hours=(sum(mean_values) / len(mean_values)) if mean_values else 0.0,
        threshold_violation_count=threshold_violation_count,
        target_gap_summary=ordered_summary,
    )


class IncrementalGapState:
    """Mutable target-timeline state with verifier-style scoring semantics."""

    def __init__(
        self,
        case: RevisitCase,
        midpoint_counts_by_target: dict[str, dict[datetime, int]] | None = None,
    ):
        self._case = case
        self._midpoint_counts_by_target: dict[str, dict[datetime, int]] = {
            target_id: {}
            for target_id in case.targets
        }
        if midpoint_counts_by_target:
            for target_id, counts in midpoint_counts_by_target.items():
                if target_id not in self._midpoint_counts_by_target:
                    continue
                self._midpoint_counts_by_target[target_id] = {
                    midpoint: count
                    for midpoint, count in counts.items()
                    if count > 0
                }
        self._target_scores = {
            target_id: self._score_target(target_id)
            for target_id in case.targets
        }
        self._score = _aggregate_gap_score(case, self._target_scores)

    @classmethod
    def empty(cls, case: RevisitCase) -> "IncrementalGapState":
        return cls(case)

    @classmethod
    def from_timelines(
        cls,
        case: RevisitCase,
        observation_midpoints_by_target: dict[str, list[datetime]],
    ) -> "IncrementalGapState":
        counts_by_target: dict[str, dict[datetime, int]] = {}
        for target_id, midpoints in observation_midpoints_by_target.items():
            target_counts: dict[datetime, int] = {}
            for midpoint in midpoints:
                target_counts[midpoint] = target_counts.get(midpoint, 0) + 1
            counts_by_target[target_id] = target_counts
        return cls(case, counts_by_target)

    @property
    def score(self) -> GapScore:
        return self._score

    def midpoint_count(self, target_id: str, midpoint: datetime) -> int:
        return self._midpoint_counts_by_target[target_id].get(midpoint, 0)

    def target_midpoints(self, target_id: str) -> list[datetime]:
        return sorted(self._midpoint_counts_by_target[target_id])

    def _score_target(self, target_id: str) -> TargetGapScore:
        return _target_gap_score(
            case=self._case,
            target_id=target_id,
            unique_midpoints=self.target_midpoints(target_id),
        )

    def _score_with_target_score(
        self,
        target_id: str,
        target_score: TargetGapScore,
    ) -> GapScore:
        target_scores = dict(self._target_scores)
        target_scores[target_id] = target_score
        return _aggregate_gap_score(self._case, target_scores)

    def score_with_added(self, target_id: str, midpoint: datetime) -> GapScore:
        if self.midpoint_count(target_id, midpoint) > 0:
            return self._score
        midpoints = sorted([*self._midpoint_counts_by_target[target_id], midpoint])
        target_score = _target_gap_score(
            case=self._case,
            target_id=target_id,
            unique_midpoints=midpoints,
        )
        return self._score_with_target_score(target_id, target_score)

    def score_with_removed(self, target_id: str, midpoint: datetime) -> GapScore:
        count = self.midpoint_count(target_id, midpoint)
        if count <= 0:
            raise ValueError(f"midpoint not present for target {target_id}")
        if count > 1:
            return self._score
        midpoints = [
            item
            for item in self.target_midpoints(target_id)
            if item != midpoint
        ]
        target_score = _target_gap_score(
            case=self._case,
            target_id=target_id,
            unique_midpoints=midpoints,
        )
        return self._score_with_target_score(target_id, target_score)

    def score_with_swap(
        self,
        remove_target_id: str,
        remove_midpoint: datetime,
        add_target_id: str,
        add_midpoint: datetime,
    ) -> GapScore:
        clone = self.copy()
        clone.remove(remove_target_id, remove_midpoint)
        clone.add(add_target_id, add_midpoint)
        return clone.score

    def add(self, target_id: str, midpoint: datetime) -> GapScore:
        counts = self._midpoint_counts_by_target[target_id]
        previous_count = counts.get(midpoint, 0)
        counts[midpoint] = previous_count + 1
        if previous_count == 0:
            self._target_scores[target_id] = self._score_target(target_id)
            self._score = _aggregate_gap_score(self._case, self._target_scores)
        return self._score

    def remove(self, target_id: str, midpoint: datetime) -> GapScore:
        counts = self._midpoint_counts_by_target[target_id]
        previous_count = counts.get(midpoint, 0)
        if previous_count <= 0:
            raise ValueError(f"midpoint not present for target {target_id}")
        if previous_count == 1:
            del counts[midpoint]
            self._target_scores[target_id] = self._score_target(target_id)
            self._score = _aggregate_gap_score(self._case, self._target_scores)
        else:
            counts[midpoint] = previous_count - 1
        return self._score

    def swap(
        self,
        remove_target_id: str,
        remove_midpoint: datetime,
        add_target_id: str,
        add_midpoint: datetime,
    ) -> GapScore:
        self.remove(remove_target_id, remove_midpoint)
        return self.add(add_target_id, add_midpoint)

    def copy(self) -> "IncrementalGapState":
        return IncrementalGapState(
            self._case,
            {
                target_id: dict(counts)
                for target_id, counts in self._midpoint_counts_by_target.items()
            },
        )


@dataclass(frozen=True, slots=True)
class GapImprovement:
    threshold_violation_reduction: int
    capped_max_revisit_gap_reduction_hours: float
    max_revisit_gap_reduction_hours: float
    mean_revisit_gap_reduction_hours: float

    @property
    def optimization_key(self) -> tuple[int, float, float, float]:
        """Higher-is-better key matching the score components."""
        return (
            self.threshold_violation_reduction,
            self.capped_max_revisit_gap_reduction_hours,
            self.max_revisit_gap_reduction_hours,
            self.mean_revisit_gap_reduction_hours,
        )

    @property
    def is_positive(self) -> bool:
        return any(value > 1.0e-12 for value in self.optimization_key)

    def as_dict(self) -> dict[str, float | int]:
        return {
            "threshold_violation_reduction": self.threshold_violation_reduction,
            "capped_max_revisit_gap_reduction_hours": (
                self.capped_max_revisit_gap_reduction_hours
            ),
            "max_revisit_gap_reduction_hours": self.max_revisit_gap_reduction_hours,
            "mean_revisit_gap_reduction_hours": self.mean_revisit_gap_reduction_hours,
        }


def score_observation_timelines(
    case: RevisitCase,
    observation_midpoints_by_target: dict[str, list[datetime]],
) -> GapScore:
    """Compute the verifier-style boundary-inclusive midpoint gap metrics."""
    target_gap_summary: dict[str, TargetGapScore] = {}

    for target_id, target in case.targets.items():
        unique_midpoints = sorted(set(observation_midpoints_by_target.get(target_id, [])))
        score = _target_gap_score(
            case=case,
            target_id=target_id,
            unique_midpoints=unique_midpoints,
        )
        target_gap_summary[target_id] = score

    return _aggregate_gap_score(case, target_gap_summary)


def gap_improvement(before: GapScore, after: GapScore) -> GapImprovement:
    return GapImprovement(
        threshold_violation_reduction=(
            before.threshold_violation_count - after.threshold_violation_count
        ),
        capped_max_revisit_gap_reduction_hours=(
            before.capped_max_revisit_gap_hours - after.capped_max_revisit_gap_hours
        ),
        max_revisit_gap_reduction_hours=before.max_revisit_gap_hours
        - after.max_revisit_gap_hours,
        mean_revisit_gap_reduction_hours=before.mean_revisit_gap_hours
        - after.mean_revisit_gap_hours,
    )
