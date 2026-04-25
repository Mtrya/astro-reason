"""Per-satellite sequence feasibility, insertion, propagation, and rollback.

This module implements Lemaitre-style earliest/latest propagation adapted to
fixed candidate start times.  Because benchmark candidates have fixed windows,
E_i = L_i = start_i; propagation degenerates to verifying non-overlap and
sufficient slew/settle gaps, but the e_i / l_i shape is preserved for debug
generality.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from skyfield.api import EarthSatellite

from case_io import SatelliteDef, StereoCase
from candidates import Candidate
from geometry import (
    _TS,
    _angle_between_deg,
    _boresight_unit_vector,
    _min_slew_time_s,
    _satellite_state_ecef_m,
)
from products import StereoProduct


@dataclass(slots=True)
class SatelliteSequence:
    satellite_id: str
    observations: list[Candidate] = field(default_factory=list)
    earliest: dict[str, datetime] = field(default_factory=dict)
    latest: dict[str, datetime] = field(default_factory=dict)
    ordering_keys: list[tuple[datetime, datetime, str]] = field(default_factory=list)
    slew_cache: dict[tuple[str, str], float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "satellite_id": self.satellite_id,
            "observation_count": len(self.observations),
            "observations": [o.candidate_id for o in self.observations],
            "earliest": {cid: dt.isoformat().replace("+00:00", "Z") for cid, dt in sorted(self.earliest.items())},
            "latest": {cid: dt.isoformat().replace("+00:00", "Z") for cid, dt in sorted(self.latest.items())},
        }


@dataclass(slots=True)
class SequenceState:
    sequences: dict[str, SatelliteSequence]
    sf_sats: dict[str, EarthSatellite]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequences": {sid: seq.as_dict() for sid, seq in sorted(self.sequences.items())},
        }


@dataclass(frozen=True, slots=True)
class InsertionResult:
    success: bool
    position: int
    reject_reasons: tuple[str, ...]
    rollback_snapshot: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProductInsertionResult:
    success: bool
    per_observation_results: tuple[InsertionResult, ...]
    rollback_snapshot: dict[str, Any]
    reject_reasons: tuple[str, ...]


def _slew_gap_required_s(
    before: Candidate,
    after: Candidate,
    sat_def: SatelliteDef,
    sf: EarthSatellite,
) -> float:
    """Benchmark verifier-style slew-plus-settle gap between two observations."""
    sp0, sv0 = _satellite_state_ecef_m(sf, before.end)
    sp1, sv1 = _satellite_state_ecef_m(sf, after.start)
    b0 = _boresight_unit_vector(
        sp0, sv0, before.off_nadir_along_deg, before.off_nadir_across_deg
    )
    b1 = _boresight_unit_vector(
        sp1, sv1, after.off_nadir_along_deg, after.off_nadir_across_deg
    )
    delta_deg = _angle_between_deg(b0, b1)
    return sat_def.settling_time_s + _min_slew_time_s(delta_deg, sat_def)


def _duration_s(candidate: Candidate) -> float:
    return (candidate.end - candidate.start).total_seconds()


def _candidate_ordering_key(candidate: Candidate) -> tuple[datetime, datetime, str]:
    return (candidate.start, candidate.end, candidate.candidate_id)


def _fixed_window_times(sequence: SatelliteSequence) -> tuple[dict[str, datetime], dict[str, datetime]]:
    times = {obs.candidate_id: obs.start for obs in sequence.observations}
    return dict(times), dict(times)


def _cached_slew_gap_required_s(
    before: Candidate,
    after: Candidate,
    sequence: SatelliteSequence,
    sat_def: SatelliteDef,
    sf: EarthSatellite,
) -> float:
    key = (before.candidate_id, after.candidate_id)
    cached = sequence.slew_cache.get(key)
    if cached is not None:
        return cached
    gap = _slew_gap_required_s(before, after, sat_def, sf)
    sequence.slew_cache[key] = gap
    return gap


def _insertion_reject_reasons(
    candidate: Candidate,
    sequence: SatelliteSequence,
    position: int,
    sat_def: SatelliteDef,
    sf: EarthSatellite,
) -> list[str]:
    reasons: list[str] = []

    if position < 0 or position > len(sequence.observations):
        reasons.append(f"insertion position {position} is out of bounds")
        return reasons

    candidate_key = _candidate_ordering_key(candidate)
    if position > 0:
        left = sequence.observations[position - 1]
        left_key = sequence.ordering_keys[position - 1]
        if left_key > candidate_key:
            reasons.append(
                f"candidate {candidate.candidate_id} would violate chronological order after {left.candidate_id}"
            )
        required_gap = _cached_slew_gap_required_s(left, candidate, sequence, sat_def, sf)
        if left.end + timedelta(seconds=required_gap) > candidate.start:
            reasons.append(
                f"candidate {candidate.candidate_id} cannot follow {left.candidate_id}: "
                f"requires {required_gap:.3f}s slew gap"
            )

    if position < len(sequence.observations):
        right = sequence.observations[position]
        right_key = sequence.ordering_keys[position]
        if candidate_key > right_key:
            reasons.append(
                f"candidate {candidate.candidate_id} would violate chronological order before {right.candidate_id}"
            )
        required_gap = _cached_slew_gap_required_s(candidate, right, sequence, sat_def, sf)
        if candidate.end + timedelta(seconds=required_gap) > right.start:
            reasons.append(
                f"candidate {candidate.candidate_id} cannot precede {right.candidate_id}: "
                f"requires {required_gap:.3f}s slew gap"
            )

    return reasons


def _rebuild_sequence_windows(sequence: SatelliteSequence) -> None:
    sequence.earliest, sequence.latest = _fixed_window_times(sequence)


def _snapshot_sequence(sequence: SatelliteSequence) -> dict[str, Any]:
    return {
        "observations": list(sequence.observations),
        "earliest": dict(sequence.earliest),
        "latest": dict(sequence.latest),
        "ordering_keys": list(sequence.ordering_keys),
        "slew_cache": dict(sequence.slew_cache),
    }


def _restore_sequence(sequence: SatelliteSequence, snapshot: dict[str, Any]) -> None:
    sequence.observations = list(snapshot["observations"])
    sequence.earliest = dict(snapshot["earliest"])
    sequence.latest = dict(snapshot["latest"])
    sequence.ordering_keys = list(snapshot["ordering_keys"])
    sequence.slew_cache = dict(snapshot["slew_cache"])


def _snapshot_state(state: SequenceState) -> dict[str, Any]:
    return {
        sid: _snapshot_sequence(seq)
        for sid, seq in state.sequences.items()
    }


def _restore_state(state: SequenceState, snapshot: dict[str, Any]) -> None:
    for sid, seq_snapshot in snapshot.items():
        _restore_sequence(state.sequences[sid], seq_snapshot)


def compute_earliest(
    sequence: SatelliteSequence,
    sat_def: SatelliteDef,
    sf: EarthSatellite,
) -> dict[str, datetime]:
    """Fixed-window benchmark candidates have deterministic earliest times."""
    earliest, _ = _fixed_window_times(sequence)
    return earliest


def compute_latest(
    sequence: SatelliteSequence,
    sat_def: SatelliteDef,
    sf: EarthSatellite,
) -> dict[str, datetime]:
    """Fixed-window benchmark candidates have deterministic latest times."""
    _, latest = _fixed_window_times(sequence)
    return latest


def propagate(
    sequence: SatelliteSequence,
    sat_def: SatelliteDef,
    sf: EarthSatellite,
) -> None:
    """Recompute sequence bookkeeping from the current fixed observation order."""
    sequence.ordering_keys = [_candidate_ordering_key(obs) for obs in sequence.observations]
    _rebuild_sequence_windows(sequence)


def is_consistent(
    sequence: SatelliteSequence,
    sat_def: SatelliteDef | None = None,
    sf: EarthSatellite | None = None,
) -> tuple[bool, list[str]]:
    """Return whether sequence bookkeeping and optional slew chronology are valid."""
    reasons: list[str] = []
    if len(sequence.ordering_keys) != len(sequence.observations):
        reasons.append(
            "ordering key count does not match observation count: "
            f"{len(sequence.ordering_keys)} != {len(sequence.observations)}"
        )

    for idx, obs in enumerate(sequence.observations):
        cid = obs.candidate_id
        if obs.satellite_id != sequence.satellite_id:
            reasons.append(
                f"Observation {cid} has satellite_id {obs.satellite_id}, "
                f"expected {sequence.satellite_id}"
            )
        if idx < len(sequence.ordering_keys):
            expected_key = _candidate_ordering_key(obs)
            if sequence.ordering_keys[idx] != expected_key:
                reasons.append(f"Ordering key mismatch for observation {cid}")
        e = sequence.earliest.get(cid)
        l_val = sequence.latest.get(cid)
        if e is None or l_val is None:
            reasons.append(f"Missing e/l for observation {cid}")
            continue
        if e > l_val:
            reasons.append(
                f"Inconsistency for {cid}: earliest {e.isoformat()} > latest {l_val.isoformat()}"
            )
    for before, after in zip(sequence.observations, sequence.observations[1:]):
        before_key = _candidate_ordering_key(before)
        after_key = _candidate_ordering_key(after)
        if before_key > after_key:
            reasons.append(
                f"Observation {after.candidate_id} appears before chronological predecessor {before.candidate_id}"
            )
        if before.end > after.start:
            reasons.append(
                f"Observation {after.candidate_id} overlaps predecessor {before.candidate_id}"
            )
        if sat_def is not None and sf is not None:
            required_gap = _cached_slew_gap_required_s(before, after, sequence, sat_def, sf)
            if before.end + timedelta(seconds=required_gap) > after.start:
                reasons.append(
                    f"Observation {after.candidate_id} violates slew gap after {before.candidate_id}: "
                    f"requires {required_gap:.3f}s"
                )
    return len(reasons) == 0, reasons


def possible_insertion_positions(
    candidate: Candidate,
    sequence: SatelliteSequence,
    sat_def: SatelliteDef,
    sf: EarthSatellite,
) -> list[int]:
    """Lemaitre POSSIBLEPOSITIONS adapted to fixed candidate times.

    Returns valid insertion indices 0 … len(sequence).
    """
    if not sequence.observations:
        return [0]

    candidate_key = _candidate_ordering_key(candidate)
    position = bisect_left(sequence.ordering_keys, candidate_key)
    reasons = _insertion_reject_reasons(candidate, sequence, position, sat_def, sf)
    return [] if reasons else [position]


def insert_observation(
    candidate: Candidate,
    sequence: SatelliteSequence,
    position: int,
    sat_def: SatelliteDef,
    sf: EarthSatellite,
) -> InsertionResult:
    """Insert candidate at position, propagate, and verify consistency.

    On failure the sequence is rolled back to its pre-call state.
    """
    snapshot = _snapshot_sequence(sequence)
    reasons = _insertion_reject_reasons(candidate, sequence, position, sat_def, sf)
    if reasons:
        return InsertionResult(
            success=False,
            position=position,
            reject_reasons=tuple(reasons),
            rollback_snapshot=snapshot,
        )

    sequence.observations.insert(position, candidate)
    sequence.ordering_keys.insert(position, _candidate_ordering_key(candidate))
    sequence.earliest[candidate.candidate_id] = candidate.start
    sequence.latest[candidate.candidate_id] = candidate.start

    return InsertionResult(
        success=True,
        position=position,
        reject_reasons=tuple(),
        rollback_snapshot=snapshot,
    )


def remove_observation(
    candidate_id: str,
    sequence: SatelliteSequence,
    sat_def: SatelliteDef,
    sf: EarthSatellite,
) -> None:
    """Remove observation by candidate_id and re-propagate."""
    removed_index = next(
        (idx for idx, obs in enumerate(sequence.observations) if obs.candidate_id == candidate_id),
        None,
    )
    if removed_index is None:
        return
    sequence.observations.pop(removed_index)
    sequence.ordering_keys.pop(removed_index)
    sequence.earliest.pop(candidate_id, None)
    sequence.latest.pop(candidate_id, None)
    if not sequence.observations:
        sequence.slew_cache = {}


def insert_product(
    product: StereoProduct,
    state: SequenceState,
    case: StereoCase,
) -> ProductInsertionResult:
    """Atomically insert all observations in a product.

    Observations are sorted by start time and inserted sequentially.
    If any insertion fails, the entire state is rolled back.
    """
    snapshot = _snapshot_state(state)
    results: list[InsertionResult] = []
    all_reasons: list[str] = []

    # Observations may span satellites; each one is inserted into its own
    # per-satellite sequence. Sort by start time for deterministic order.
    sorted_obs = sorted(product.observations, key=lambda o: o.start)

    for obs in sorted_obs:
        sat_id = obs.satellite_id
        seq = state.sequences[sat_id]
        sat_def = case.satellites[sat_id]
        sf = state.sf_sats[sat_id]

        positions = possible_insertion_positions(obs, seq, sat_def, sf)
        if not positions:
            all_reasons.append(
                f"No valid insertion position for {obs.candidate_id} in satellite {sat_id}"
            )
            _restore_state(state, snapshot)
            return ProductInsertionResult(
                success=False,
                per_observation_results=tuple(results),
                rollback_snapshot=snapshot,
                reject_reasons=tuple(all_reasons),
            )

        # Deterministic: choose the first valid position
        pos = positions[0]
        result = insert_observation(obs, seq, pos, sat_def, sf)
        results.append(result)
        if not result.success:
            all_reasons.extend(result.reject_reasons)
            _restore_state(state, snapshot)
            return ProductInsertionResult(
                success=False,
                per_observation_results=tuple(results),
                rollback_snapshot=snapshot,
                reject_reasons=tuple(all_reasons),
            )

    return ProductInsertionResult(
        success=True,
        per_observation_results=tuple(results),
        rollback_snapshot=snapshot,
        reject_reasons=tuple(),
    )


def remove_product(
    product: StereoProduct,
    state: SequenceState,
    case: StereoCase,
) -> None:
    """Remove all observations belonging to a product and re-propagate."""
    for obs in product.observations:
        sat_id = obs.satellite_id
        seq = state.sequences[sat_id]
        sat_def = case.satellites[sat_id]
        sf = state.sf_sats[sat_id]
        remove_observation(obs.candidate_id, seq, sat_def, sf)


def create_empty_state(case: StereoCase) -> SequenceState:
    """Initialize empty SatelliteSequences for all satellites in the case."""
    sequences: dict[str, SatelliteSequence] = {}
    sf_sats: dict[str, EarthSatellite] = {}
    for sat_id, sat_def in sorted(case.satellites.items()):
        sf_sats[sat_id] = EarthSatellite(
            sat_def.tle_line1, sat_def.tle_line2, name=sat_id, ts=_TS
        )
        sequences[sat_id] = SatelliteSequence(satellite_id=sat_id)
    return SequenceState(sequences=sequences, sf_sats=sf_sats)
