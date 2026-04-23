"""Conservative repair pass: scan sequences for direct conflicts and remove the
least-valuable affected product.  This is a defensive final step that guarantees
output validity even if propagation drift or edge cases leave latent conflicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from case_io import StereoCase
from products import StereoProduct
from sequence import (
    SequenceState,
    SatelliteSequence,
    _slew_gap_required_s,
    remove_product,
)


def _clone_sequence_state(state: SequenceState) -> SequenceState:
    """Deep-copy sequence state (observations, earliest, latest).  sf_sats shared."""
    sequences: dict[str, SatelliteSequence] = {}
    for sid, seq in state.sequences.items():
        new_seq = SatelliteSequence(satellite_id=sid)
        new_seq.observations = list(seq.observations)
        new_seq.earliest = dict(seq.earliest)
        new_seq.latest = dict(seq.latest)
        sequences[sid] = new_seq
    return SequenceState(sequences=sequences, sf_sats=state.sf_sats)


@dataclass(frozen=True, slots=True)
class RepairConfig:
    enabled: bool = True
    max_repair_iterations: int = 100

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "RepairConfig":
        payload = payload or {}
        return cls(
            enabled=bool(payload.get("enable_repair", True)),
            max_repair_iterations=int(payload.get("max_repair_iterations", 100)),
        )

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "max_repair_iterations": self.max_repair_iterations,
        }


@dataclass(slots=True)
class RepairResult:
    removed_products: list[StereoProduct] = field(default_factory=list)
    lost_targets: list[str] = field(default_factory=list)
    iterations: int = 0
    final_coverage: int = 0
    final_quality: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "removed_product_ids": [p.product_id for p in self.removed_products],
            "removed_count": len(self.removed_products),
            "lost_targets": sorted(self.lost_targets),
            "lost_target_count": len(self.lost_targets),
            "iterations": self.iterations,
            "final_coverage": self.final_coverage,
            "final_quality": round(self.final_quality, 6),
        }


def _find_first_conflict(
    sequence: SatelliteSequence, sat_def, sf
) -> tuple[int, int] | None:
    """Return (i, j) indices of first conflicting adjacent observation pair.

    Checks for overlap and insufficient slew/settle gap.
    """
    obs = sequence.observations
    n = len(obs)
    for i in range(n - 1):
        o0 = obs[i]
        o1 = obs[i + 1]
        # Overlap
        if o1.start < o0.end:
            return (i, i + 1)
        # Slew/settle gap
        gap_s = (o1.start - o0.end).total_seconds()
        need_s = _slew_gap_required_s(o0, o1, sat_def, sf)
        if gap_s + 1e-9 < need_s:
            return (i, i + 1)
    return None


def _build_candidate_to_product(
    scheduled_products: dict[str, StereoProduct],
) -> dict[str, str]:
    """Map candidate_id -> product_id."""
    mapping: dict[str, str] = {}
    for pid, product in scheduled_products.items():
        for obs in product.observations:
            mapping[obs.candidate_id] = pid
    return mapping


def _compute_coverage_quality(
    scheduled_products: dict[str, StereoProduct],
) -> tuple[int, float]:
    """Compute coverage (unique targets) and total best quality."""
    best_by_target: dict[str, float] = {}
    for product in scheduled_products.values():
        tid = product.target_id
        best_by_target[tid] = max(best_by_target.get(tid, 0.0), product.quality)
    return len(best_by_target), sum(best_by_target.values())


def repair_state(
    state: SequenceState,
    scheduled_products: dict[str, StereoProduct],
    case: StereoCase,
    config: RepairConfig | None = None,
) -> tuple[RepairResult, SequenceState, dict[str, StereoProduct]]:
    """Repair a sequence state by removing the least valuable product involved
    in any direct observation-level conflict.

    Returns a RepairResult describing what was removed and the final coverage.
    """
    config = config or RepairConfig()
    if not config.enabled:
        coverage, quality = _compute_coverage_quality(scheduled_products)
        result = RepairResult(
            removed_products=[],
            lost_targets=[],
            iterations=0,
            final_coverage=coverage,
            final_quality=quality,
        )
        return result, _clone_sequence_state(state), dict(scheduled_products)

    # Work on a copy so the caller can decide whether to use the repaired state
    state = _clone_sequence_state(state)
    products = dict(scheduled_products)
    candidate_to_product = _build_candidate_to_product(products)

    removed: list[StereoProduct] = []

    for iteration in range(config.max_repair_iterations):
        conflict_found = False

        for sat_id, sequence in state.sequences.items():
            if len(sequence.observations) < 2:
                continue
            sat_def = case.satellites[sat_id]
            sf = state.sf_sats[sat_id]
            conflict = _find_first_conflict(sequence, sat_def, sf)
            if conflict is None:
                continue

            conflict_found = True
            i, j = conflict
            o0 = sequence.observations[i]
            o1 = sequence.observations[j]
            pid0 = candidate_to_product.get(o0.candidate_id)
            pid1 = candidate_to_product.get(o1.candidate_id)

            # Determine which product to remove (least valuable)
            candidates_to_remove: list[StereoProduct] = []
            if pid0 is not None and pid0 in products:
                candidates_to_remove.append(products[pid0])
            if pid1 is not None and pid1 in products and pid1 != pid0:
                candidates_to_remove.append(products[pid1])

            if not candidates_to_remove:
                # Should not happen, but break to avoid infinite loop
                break

            # Sort by quality asc, product_id asc for deterministic tie-breaking
            candidates_to_remove.sort(key=lambda p: (p.quality, p.product_id))
            to_remove = candidates_to_remove[0]

            # Remove product
            remove_product(to_remove, state, case)
            removed.append(to_remove)
            del products[to_remove.product_id]
            # Rebuild mapping after removal
            candidate_to_product = _build_candidate_to_product(products)
            break  # restart outer scan after any removal

        if not conflict_found:
            break

    # Compute lost targets
    covered_before = {p.target_id for p in scheduled_products.values()}
    covered_after = {p.target_id for p in products.values()}
    lost = sorted(covered_before - covered_after)

    coverage, quality = _compute_coverage_quality(products)
    result = RepairResult(
        removed_products=removed,
        lost_targets=lost,
        iterations=len(removed),
        final_coverage=coverage,
        final_quality=quality,
    )
    return result, state, products
