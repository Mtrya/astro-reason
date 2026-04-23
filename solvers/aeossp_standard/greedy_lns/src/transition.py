"""Transition feasibility helpers for AEOSSP candidate pairs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np

from candidates import Candidate
from case_io import AeosspCase, NUMERICAL_EPS, Satellite
from geometry import (
    PropagationContext,
    angle_between_deg,
    required_slew_settle_s,
    target_vector_eci,
)


@dataclass(frozen=True, slots=True)
class TransitionResult:
    feasible: bool
    required_gap_s: float
    available_gap_s: float
    slew_angle_deg: float


class TransitionVectorCache:
    def __init__(self, case: AeosspCase, propagation: PropagationContext):
        self.case = case
        self.propagation = propagation
        self._vectors: dict[tuple[str, str], np.ndarray] = {}

    def vector(self, candidate: Candidate, endpoint: str) -> np.ndarray:
        key = (candidate.candidate_id, endpoint)
        cached = self._vectors.get(key)
        if cached is not None:
            return cached
        if endpoint == "start":
            offset_s = candidate.start_offset_s
        elif endpoint == "end":
            offset_s = candidate.end_offset_s
        else:
            raise ValueError(f"Unsupported endpoint: {endpoint}")
        instant = self.case.mission.horizon_start + timedelta(seconds=offset_s)
        vector = target_vector_eci(
            self.case.tasks[candidate.task_id],
            self.propagation,
            candidate.satellite_id,
            instant,
        )
        self._vectors[key] = vector
        return vector


def max_transition_gap_s(satellite: Satellite) -> float:
    return required_slew_settle_s(180.0, satellite)


def order_for_transition(
    candidate_a: Candidate,
    candidate_b: Candidate,
) -> tuple[Candidate, Candidate]:
    return tuple(
        sorted(
            (candidate_a, candidate_b),
            key=lambda item: (item.start_offset_s, item.end_offset_s, item.candidate_id),
        )
    )


def transition_result(
    previous: Candidate,
    current: Candidate,
    *,
    case: AeosspCase,
    vector_cache: TransitionVectorCache,
) -> TransitionResult:
    if previous.satellite_id != current.satellite_id:
        return TransitionResult(
            feasible=True,
            required_gap_s=0.0,
            available_gap_s=float("inf"),
            slew_angle_deg=0.0,
        )
    satellite = case.satellites[previous.satellite_id]
    available_gap_s = float(current.start_offset_s - previous.end_offset_s)
    from_vector = vector_cache.vector(previous, "end")
    to_vector = vector_cache.vector(current, "start")
    slew_angle_deg = angle_between_deg(from_vector, to_vector)
    required_gap_s = required_slew_settle_s(slew_angle_deg, satellite)
    return TransitionResult(
        feasible=available_gap_s + NUMERICAL_EPS >= required_gap_s,
        required_gap_s=required_gap_s,
        available_gap_s=available_gap_s,
        slew_angle_deg=slew_angle_deg,
    )


def transition_gap_conflict(
    candidate_a: Candidate,
    candidate_b: Candidate,
    *,
    case: AeosspCase,
    vector_cache: TransitionVectorCache,
) -> bool:
    previous, current = order_for_transition(candidate_a, candidate_b)
    if previous.end_offset_s > current.start_offset_s:
        return True
    return not transition_result(
        previous,
        current,
        case=case,
        vector_cache=vector_cache,
    ).feasible
