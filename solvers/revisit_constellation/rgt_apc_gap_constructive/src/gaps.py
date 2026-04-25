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
    capped_max_values: list[float] = []
    max_values: list[float] = []
    mean_values: list[float] = []
    threshold_violation_count = 0

    for target_id, target in case.targets.items():
        unique_midpoints = sorted(set(observation_midpoints_by_target.get(target_id, [])))
        gaps = revisit_gaps_hours(case.horizon_start, case.horizon_end, unique_midpoints)
        mean_gap = sum(gaps) / len(gaps)
        max_gap = max(gaps)
        score = TargetGapScore(
            target_id=target_id,
            expected_revisit_period_hours=target.expected_revisit_period_hours,
            mean_revisit_gap_hours=mean_gap,
            max_revisit_gap_hours=max_gap,
            observation_count=len(unique_midpoints),
        )
        target_gap_summary[target_id] = score
        capped_max_values.append(score.capped_max_revisit_gap_hours)
        max_values.append(max_gap)
        mean_values.append(mean_gap)
        if score.threshold_violated:
            threshold_violation_count += 1

    return GapScore(
        capped_max_revisit_gap_hours=max(capped_max_values) if capped_max_values else 0.0,
        max_revisit_gap_hours=max(max_values) if max_values else 0.0,
        mean_revisit_gap_hours=(sum(mean_values) / len(mean_values)) if mean_values else 0.0,
        threshold_violation_count=threshold_violation_count,
        target_gap_summary=target_gap_summary,
    )


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
