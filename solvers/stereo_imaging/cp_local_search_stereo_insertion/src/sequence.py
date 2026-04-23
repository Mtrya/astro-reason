"""Per-satellite sequence feasibility, insertion, propagation, and rollback.

This module implements Lemaitre-style earliest/latest propagation adapted to
fixed candidate start times.  Because benchmark candidates have fixed windows,
E_i = L_i = start_i; propagation degenerates to verifying non-overlap and
sufficient slew/settle gaps, but the e_i / l_i shape is preserved for debug
generality.
"""

from __future__ import annotations

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


def _snapshot_sequence(sequence: SatelliteSequence) -> dict[str, Any]:
    return {
        "observations": list(sequence.observations),
        "earliest": dict(sequence.earliest),
        "latest": dict(sequence.latest),
    }


def _restore_sequence(sequence: SatelliteSequence, snapshot: dict[str, Any]) -> None:
    sequence.observations = list(snapshot["observations"])
    sequence.earliest = dict(snapshot["earliest"])
    sequence.latest = dict(snapshot["latest"])


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
    """Upward propagation: e[p] = max(start_p, e[p-1] + dur_{p-1} + slew_{p-1,p})."""
    e: dict[str, datetime] = {}
    for p, obs in enumerate(sequence.observations):
        cid = obs.candidate_id
        if p == 0:
            e[cid] = obs.start
        else:
            prev = sequence.observations[p - 1]
            dur_prev = _duration_s(prev)
            slew = _slew_gap_required_s(prev, obs, sat_def, sf)
            e_prev = e[prev.candidate_id]
            e[cid] = max(obs.start, e_prev + timedelta(seconds=dur_prev + slew))
    return e


def compute_latest(
    sequence: SatelliteSequence,
    sat_def: SatelliteDef,
    sf: EarthSatellite,
) -> dict[str, datetime]:
    """Downward propagation: l[p] = min(start_p, l[p+1] - dur_p - slew_{p,p+1})."""
    l: dict[str, datetime] = {}
    n = len(sequence.observations)
    for p in range(n - 1, -1, -1):
        obs = sequence.observations[p]
        cid = obs.candidate_id
        if p == n - 1:
            l[cid] = obs.start
        else:
            nxt = sequence.observations[p + 1]
            dur_obs = _duration_s(obs)
            slew = _slew_gap_required_s(obs, nxt, sat_def, sf)
            l_next = l[nxt.candidate_id]
            l[cid] = min(obs.start, l_next - timedelta(seconds=dur_obs + slew))
    return l


def propagate(
    sequence: SatelliteSequence,
    sat_def: SatelliteDef,
    sf: EarthSatellite,
) -> None:
    """Recompute earliest and latest for the whole sequence."""
    sequence.earliest = compute_earliest(sequence, sat_def, sf)
    sequence.latest = compute_latest(sequence, sat_def, sf)


def is_consistent(sequence: SatelliteSequence) -> tuple[bool, list[str]]:
    """Return (ok, reasons) where reasons is empty when e[cid] <= l[cid] for all."""
    reasons: list[str] = []
    for obs in sequence.observations:
        cid = obs.candidate_id
        e = sequence.earliest.get(cid)
        l_val = sequence.latest.get(cid)
        if e is None or l_val is None:
            reasons.append(f"Missing e/l for observation {cid}")
            continue
        if e > l_val:
            reasons.append(
                f"Inconsistency for {cid}: earliest {e.isoformat()} > latest {l_val.isoformat()}"
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
    positions: list[int] = []
    n = len(sequence.observations)
    E_i = candidate.start
    D_i = _duration_s(candidate)

    if n == 0:
        return [0]

    e = sequence.earliest
    l_val = sequence.latest

    # Beginning: position 0
    first = sequence.observations[0]
    M_i_first = _slew_gap_required_s(candidate, first, sat_def, sf)
    if E_i + timedelta(seconds=D_i + M_i_first) <= l_val[first.candidate_id]:
        positions.append(0)

    # Middle: positions 1 … n-1
    for p in range(1, n):
        left = sequence.observations[p - 1]
        right = sequence.observations[p]
        D_left = _duration_s(left)
        M_left_i = _slew_gap_required_s(left, candidate, sat_def, sf)
        M_i_right = _slew_gap_required_s(candidate, right, sat_def, sf)
        e_i = max(E_i, e[left.candidate_id] + timedelta(seconds=D_left + M_left_i))
        l_i = min(E_i, l_val[right.candidate_id] - timedelta(seconds=D_i + M_i_right))
        if e_i <= l_i:
            positions.append(p)

    # End: position n
    last = sequence.observations[-1]
    D_last = _duration_s(last)
    M_last_i = _slew_gap_required_s(last, candidate, sat_def, sf)
    if e[last.candidate_id] + timedelta(seconds=D_last + M_last_i) <= E_i:
        positions.append(n)

    return positions


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
    sequence.observations.insert(position, candidate)
    propagate(sequence, sat_def, sf)
    ok, reasons = is_consistent(sequence)
    if ok:
        return InsertionResult(
            success=True,
            position=position,
            reject_reasons=tuple(),
            rollback_snapshot=snapshot,
        )
    _restore_sequence(sequence, snapshot)
    return InsertionResult(
        success=False,
        position=position,
        reject_reasons=tuple(reasons),
        rollback_snapshot=snapshot,
    )


def remove_observation(
    candidate_id: str,
    sequence: SatelliteSequence,
    sat_def: SatelliteDef,
    sf: EarthSatellite,
) -> None:
    """Remove observation by candidate_id and re-propagate."""
    sequence.observations = [o for o in sequence.observations if o.candidate_id != candidate_id]
    if sequence.observations:
        propagate(sequence, sat_def, sf)
    else:
        sequence.earliest = {}
        sequence.latest = {}


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

    # All observations in a product share the same satellite (same-pass constraint)
    # Sort by start time for deterministic insertion order
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
