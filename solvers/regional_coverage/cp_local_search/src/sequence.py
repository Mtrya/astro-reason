"""Satellite-local fixed-start sequence model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .candidates import Candidate, candidate_sort_key
from .case_io import RegionalCoverageCase
from .coverage import CoverageIndex
from .transition import TransitionResult, transition_result


@dataclass(slots=True)
class SatelliteSequence:
    satellite_id: str
    candidates: list[Candidate] = field(default_factory=list)
    reject_counters: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "satellite_id": self.satellite_id,
            "candidate_count": len(self.candidates),
            "candidates": [candidate.candidate_id for candidate in self.candidates],
            "coverage_sample_count": len(self.covered_sample_ids()),
            "base_weight_m2": self.base_weight_m2(),
            "reject_counters": dict(sorted(self.reject_counters.items())),
        }

    def covered_sample_ids(self) -> set[str]:
        covered: set[str] = set()
        for candidate in self.candidates:
            covered.update(candidate.coverage_sample_ids)
        return covered

    def base_weight_m2(self) -> float:
        return sum(candidate.base_coverage_weight_m2 for candidate in self.candidates)

    def unique_weight_m2(self, index: CoverageIndex) -> float:
        return index.total_weight(self.covered_sample_ids())


@dataclass(slots=True)
class SequenceState:
    sequences: dict[str, SatelliteSequence]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequences": {
                satellite_id: sequence.as_dict()
                for satellite_id, sequence in sorted(self.sequences.items())
            }
        }


@dataclass(frozen=True, slots=True)
class InsertionResult:
    success: bool
    position: int | None
    reject_reasons: tuple[str, ...]
    transition_checks: tuple[TransitionResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "position": self.position,
            "reject_reasons": list(self.reject_reasons),
            "transition_checks": [
                {
                    "feasible": item.feasible,
                    "required_gap_s": item.required_gap_s,
                    "available_gap_s": item.available_gap_s,
                    "roll_delta_deg": item.roll_delta_deg,
                }
                for item in self.transition_checks
            ],
        }


def create_empty_state(case: RegionalCoverageCase) -> SequenceState:
    return SequenceState(
        sequences={
            satellite_id: SatelliteSequence(satellite_id=satellite_id)
            for satellite_id in sorted(case.satellites)
        }
    )


def possible_insertion_positions(sequence: SatelliteSequence, candidate: Candidate) -> list[int]:
    positions: list[int] = []
    key = candidate_sort_key(candidate)
    for position in range(len(sequence.candidates) + 1):
        left_ok = position == 0 or candidate_sort_key(sequence.candidates[position - 1]) <= key
        right_ok = position == len(sequence.candidates) or key <= candidate_sort_key(sequence.candidates[position])
        if left_ok and right_ok:
            positions.append(position)
    return positions


def check_insertion(
    case: RegionalCoverageCase,
    sequence: SatelliteSequence,
    candidate: Candidate,
    position: int,
) -> InsertionResult:
    reasons: list[str] = []
    checks: list[TransitionResult] = []
    if candidate.satellite_id != sequence.satellite_id:
        reasons.append("candidate satellite does not match sequence")
    if position < 0 or position > len(sequence.candidates):
        return InsertionResult(False, position, ("position out of bounds",), ())

    key = candidate_sort_key(candidate)
    satellite = case.satellites[sequence.satellite_id]
    if position > 0:
        previous = sequence.candidates[position - 1]
        if candidate_sort_key(previous) > key:
            reasons.append("candidate would violate chronological order")
        result = transition_result(previous, candidate, satellite=satellite)
        checks.append(result)
        if previous.end_offset_s > candidate.start_offset_s:
            reasons.append("candidate overlaps previous candidate")
        if not result.feasible:
            reasons.append("candidate lacks required transition gap from previous")

    if position < len(sequence.candidates):
        current = sequence.candidates[position]
        if key > candidate_sort_key(current):
            reasons.append("candidate would violate chronological order")
        result = transition_result(candidate, current, satellite=satellite)
        checks.append(result)
        if candidate.end_offset_s > current.start_offset_s:
            reasons.append("candidate overlaps next candidate")
        if not result.feasible:
            reasons.append("candidate lacks required transition gap to next")

    return InsertionResult(not reasons, position, tuple(reasons), tuple(checks))


def insert_candidate(
    case: RegionalCoverageCase,
    sequence: SatelliteSequence,
    candidate: Candidate,
    position: int | None = None,
) -> InsertionResult:
    if position is None:
        positions = possible_insertion_positions(sequence, candidate)
    else:
        positions = [position]
    last_result = InsertionResult(False, None, ("no insertion position",), ())
    for pos in positions:
        result = check_insertion(case, sequence, candidate, pos)
        if result.success:
            sequence.candidates.insert(pos, candidate)
            return result
        last_result = result
        for reason in result.reject_reasons:
            sequence.reject_counters[reason] = sequence.reject_counters.get(reason, 0) + 1
    return last_result


def remove_candidate(sequence: SatelliteSequence, candidate_id: str) -> Candidate:
    for idx, candidate in enumerate(sequence.candidates):
        if candidate.candidate_id == candidate_id:
            return sequence.candidates.pop(idx)
    raise KeyError(candidate_id)


def is_consistent(case: RegionalCoverageCase, sequence: SatelliteSequence) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for idx, candidate in enumerate(sequence.candidates):
        if candidate.satellite_id != sequence.satellite_id:
            reasons.append(f"{candidate.candidate_id}: satellite mismatch")
        if idx > 0:
            previous = sequence.candidates[idx - 1]
            if candidate_sort_key(previous) > candidate_sort_key(candidate):
                reasons.append(f"{candidate.candidate_id}: chronological order violation")
            result = transition_result(previous, candidate, satellite=case.satellites[sequence.satellite_id])
            if previous.end_offset_s > candidate.start_offset_s:
                reasons.append(f"{candidate.candidate_id}: overlaps previous candidate")
            if not result.feasible:
                reasons.append(f"{candidate.candidate_id}: transition gap violation")
    return not reasons, reasons

