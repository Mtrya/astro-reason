"""Deterministic local search over whole stereo/tri-stereo products.

Implements replace-first, insert-uncovered, and remove-then-repair moves
with clone-based trial evaluation.  All moves are atomic and rollback on
failure or lack of objective improvement.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from case_io import StereoCase
from products import ProductLibrary, StereoProduct
from sequence import (
    SequenceState,
    SatelliteSequence,
    insert_product as _seq_insert_product,
    remove_product as _seq_remove_product,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LocalSearchConfig:
    max_passes: int = 10
    max_moves_per_pass: int = 500
    max_time_seconds: float = 60.0
    enable_repair: bool = True
    repair_candidates_limit: int = 20

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "LocalSearchConfig":
        payload = payload or {}
        return cls(
            max_passes=int(payload.get("max_passes", 10)),
            max_moves_per_pass=int(payload.get("max_moves_per_pass", 500)),
            max_time_seconds=float(payload.get("max_time_seconds", 60.0)),
            enable_repair=bool(payload.get("enable_repair", True)),
            repair_candidates_limit=int(payload.get("repair_candidates_limit", 20)),
        )

    def as_status_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

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


@dataclass(slots=True)
class LocalSearchState:
    sequence_state: SequenceState
    scheduled_products: dict[str, StereoProduct]  # product_id -> product
    target_to_product_id: dict[str, str]  # target_id -> product_id

    @classmethod
    def from_seed(
        cls, seed_state: SequenceState, seed_products: list[StereoProduct]
    ) -> "LocalSearchState":
        state = cls(
            sequence_state=_clone_sequence_state(seed_state),
            scheduled_products={},
            target_to_product_id={},
        )
        for product in seed_products:
            state.scheduled_products[product.product_id] = product
            current = state.target_to_product_id.get(product.target_id)
            if current is None or product.quality > state.scheduled_products[current].quality:
                state.target_to_product_id[product.target_id] = product.product_id
        return state

    @property
    def coverage_count(self) -> int:
        return len(self.target_to_product_id)

    @property
    def total_best_quality(self) -> float:
        return sum(
            self.scheduled_products[pid].quality
            for pid in self.target_to_product_id.values()
        )

    def objective(self) -> tuple[int, float]:
        """Lexicographic objective: (coverage, total_best_quality)."""
        return (self.coverage_count, self.total_best_quality)

    def clone(self) -> "LocalSearchState":
        return LocalSearchState(
            sequence_state=_clone_sequence_state(self.sequence_state),
            scheduled_products=dict(self.scheduled_products),
            target_to_product_id=dict(self.target_to_product_id),
        )

    def add_product(self, product: StereoProduct, case: StereoCase) -> bool:
        result = _seq_insert_product(product, self.sequence_state, case)
        if not result.success:
            return False
        self.scheduled_products[product.product_id] = product
        current = self.target_to_product_id.get(product.target_id)
        if current is None or product.quality > self.scheduled_products[current].quality:
            self.target_to_product_id[product.target_id] = product.product_id
        return True

    def remove_product(self, product: StereoProduct, case: StereoCase) -> None:
        _seq_remove_product(product, self.sequence_state, case)
        self.scheduled_products.pop(product.product_id, None)
        best: StereoProduct | None = None
        for p in self.scheduled_products.values():
            if p.target_id == product.target_id:
                if best is None or p.quality > best.quality:
                    best = p
        if best is not None:
            self.target_to_product_id[product.target_id] = best.product_id
        else:
            self.target_to_product_id.pop(product.target_id, None)


# ---------------------------------------------------------------------------
# Move log
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class MoveRecord:
    move_number: int
    pass_number: int
    move_type: str
    target_id: str | None
    product_ids: list[str]
    before_objective: tuple[int, float]
    after_objective: tuple[int, float] | None
    accepted: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "move_number": self.move_number,
            "pass_number": self.pass_number,
            "move_type": self.move_type,
            "target_id": self.target_id,
            "product_ids": self.product_ids,
            "before_objective": list(self.before_objective),
            "after_objective": list(self.after_objective) if self.after_objective else None,
            "accepted": self.accepted,
            "reason": self.reason,
        }


@dataclass(slots=True)
class LocalSearchResult:
    best_state: LocalSearchState
    final_state: LocalSearchState
    log: list[MoveRecord]
    passes_completed: int
    moves_attempted: int
    moves_accepted: int
    best_objective: tuple[int, float]
    time_seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "passes_completed": self.passes_completed,
            "moves_attempted": self.moves_attempted,
            "moves_accepted": self.moves_accepted,
            "best_objective": list(self.best_objective),
            "time_seconds": round(self.time_seconds, 3),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_feasible_by_target(
    product_library: ProductLibrary,
) -> dict[str, list[StereoProduct]]:
    """Map target_id -> feasible products sorted by quality desc, product_id asc."""
    by_target: dict[str, list[StereoProduct]] = {}
    for product in product_library.products:
        if not product.feasible:
            continue
        by_target.setdefault(product.target_id, []).append(product)
    for target_id in by_target:
        by_target[target_id].sort(
            key=lambda p: (-p.quality, p.product_id)
        )
    return by_target


def _uncovered_targets(state: LocalSearchState, case: StereoCase) -> list[str]:
    return sorted(
        tid for tid in case.targets if tid not in state.target_to_product_id
    )


def _time_exceeded(start: float, limit: float) -> bool:
    return limit > 0 and time.perf_counter() - start >= limit


# ---------------------------------------------------------------------------
# Move evaluators
# ---------------------------------------------------------------------------

def _try_insert(
    state: LocalSearchState, product: StereoProduct, case: StereoCase
) -> tuple[bool, LocalSearchState | None, str]:
    trial = state.clone()
    ok = trial.add_product(product, case)
    if not ok:
        return False, None, "insertion_failed"
    if trial.objective() > state.objective():
        return True, trial, "improved"
    return False, None, "no_improvement"


def _try_replace(
    state: LocalSearchState,
    old_product: StereoProduct,
    new_product: StereoProduct,
    case: StereoCase,
) -> tuple[bool, LocalSearchState | None, str]:
    trial = state.clone()
    trial.remove_product(old_product, case)
    ok = trial.add_product(new_product, case)
    if not ok:
        return False, None, "replacement_insert_failed"
    if trial.objective() > state.objective():
        return True, trial, "improved"
    return False, None, "no_improvement"


def _try_swap(
    state: LocalSearchState,
    remove_product: StereoProduct,
    feasible_by_target: dict[str, list[StereoProduct]],
    case: StereoCase,
    config: LocalSearchConfig,
) -> tuple[bool, LocalSearchState | None, str]:
    trial = state.clone()
    trial.remove_product(remove_product, case)

    # Gather candidate products that could improve the trial state
    candidates: list[StereoProduct] = []
    seen = set(trial.scheduled_products.keys())
    for target_id, products in feasible_by_target.items():
        current_pid = trial.target_to_product_id.get(target_id)
        current_quality = (
            trial.scheduled_products[current_pid].quality
            if current_pid else 0.0
        )
        for p in products:
            if p.product_id in seen:
                continue
            if p.target_id not in trial.target_to_product_id or p.quality > current_quality:
                candidates.append(p)
                break  # best candidate for this target already found (products sorted)

    # Sort: uncovered targets first, then higher quality
    candidates.sort(
        key=lambda p: (p.target_id not in trial.target_to_product_id, p.quality, p.product_id),
        reverse=True,
    )

    inserted = 0
    for product in candidates[: config.repair_candidates_limit]:
        ok = trial.add_product(product, case)
        if ok:
            inserted += 1

    if trial.objective() > state.objective():
        return True, trial, f"improved (removed {remove_product.product_id}, inserted {inserted})"
    return False, None, "no_improvement"


# ---------------------------------------------------------------------------
# Search loop
# ---------------------------------------------------------------------------

def run_local_search(
    seed_state: SequenceState,
    seed_products: list[StereoProduct],
    product_library: ProductLibrary,
    case: StereoCase,
    config: LocalSearchConfig | None = None,
) -> LocalSearchResult:
    """Improve a greedy seed via deterministic product-level local search.

    Move priority per pass:
    1. INSERT uncovered targets (increases coverage).
    2. REPLACE with higher quality for already-covered targets.
    3. SWAP / remove-then-repair (remove low-quality, insert better alternatives).

    Stops when a pass makes no improving moves, or budget exhausted.
    """
    config = config or LocalSearchConfig()
    start_time = time.perf_counter()

    feasible_by_target = _build_feasible_by_target(product_library)

    state = LocalSearchState.from_seed(seed_state, seed_products)
    best_state = state.clone()
    best_objective = best_state.objective()

    log: list[MoveRecord] = []
    move_number = 0
    moves_accepted = 0

    def _record(
        pass_num: int,
        move_type: str,
        target_id: str | None,
        product_ids: list[str],
        before: tuple[int, float],
        accepted: bool,
        after_state: LocalSearchState | None,
        reason: str,
    ) -> None:
        nonlocal move_number
        move_number += 1
        log.append(
            MoveRecord(
                move_number=move_number,
                pass_number=pass_num,
                move_type=move_type,
                target_id=target_id,
                product_ids=product_ids,
                before_objective=before,
                after_objective=after_state.objective() if after_state else None,
                accepted=accepted,
                reason=reason,
            )
        )

    def _budget_exceeded() -> bool:
        if move_number >= config.max_passes * config.max_moves_per_pass:
            return True
        if _time_exceeded(start_time, config.max_time_seconds):
            return True
        return False

    for pass_num in range(config.max_passes):
        if _budget_exceeded():
            break

        improved_this_pass = False

        # -----------------------------------------------------------------
        # Move 1: INSERT uncovered targets
        # -----------------------------------------------------------------
        for target_id in _uncovered_targets(state, case):
            if _budget_exceeded():
                break
            products = feasible_by_target.get(target_id, [])
            before = state.objective()
            accepted = False
            trial_state: LocalSearchState | None = None
            reason = "no_candidate"
            for product in products:
                accepted, trial_state, reason = _try_insert(state, product, case)
                if accepted:
                    break
            _record(
                pass_num, "insert", target_id,
                [trial_state.target_to_product_id[target_id]] if trial_state else [],
                before, accepted, trial_state, reason,
            )
            if accepted:
                state = trial_state  # type: ignore[assignment]
                moves_accepted += 1
                if state.objective() > best_objective:
                    best_state = state.clone()
                    best_objective = best_state.objective()
                improved_this_pass = True

        # -----------------------------------------------------------------
        # Move 2: REPLACE with higher quality for covered targets
        # -----------------------------------------------------------------
        for target_id in sorted(state.target_to_product_id.keys()):
            if _budget_exceeded():
                break
            current_pid = state.target_to_product_id[target_id]
            current_product = state.scheduled_products[current_pid]
            candidates = [
                p for p in feasible_by_target.get(target_id, [])
                if p.product_id != current_pid and p.quality > current_product.quality
            ]
            before = state.objective()
            accepted = False
            trial_state = None
            reason = "no_better_candidate"
            for product in candidates:
                accepted, trial_state, reason = _try_replace(
                    state, current_product, product, case
                )
                if accepted:
                    break
            _record(
                pass_num, "replace", target_id,
                [current_pid] + ([trial_state.target_to_product_id[target_id]] if trial_state else []),
                before, accepted, trial_state, reason,
            )
            if accepted:
                state = trial_state  # type: ignore[assignment]
                moves_accepted += 1
                if state.objective() > best_objective:
                    best_state = state.clone()
                    best_objective = best_state.objective()
                improved_this_pass = True

        # -----------------------------------------------------------------
        # Move 3: SWAP / remove-then-repair
        # -----------------------------------------------------------------
        if config.enable_repair and not improved_this_pass:
            scheduled = list(state.scheduled_products.values())
            scheduled.sort(key=lambda p: (p.quality, p.product_id))
            for product in scheduled:
                if _budget_exceeded():
                    break
                before = state.objective()
                accepted, trial_state, reason = _try_swap(
                    state, product, feasible_by_target, case, config
                )
                _record(
                    pass_num, "swap", product.target_id,
                    [product.product_id] + (
                        list(trial_state.scheduled_products.keys()) if trial_state else []
                    ),
                    before, accepted, trial_state, reason,
                )
                if accepted:
                    state = trial_state  # type: ignore[assignment]
                    moves_accepted += 1
                    if state.objective() > best_objective:
                        best_state = state.clone()
                        best_objective = best_state.objective()
                    improved_this_pass = True
                    break

        if not improved_this_pass:
            break

    elapsed = time.perf_counter() - start_time
    return LocalSearchResult(
        best_state=best_state,
        final_state=state,
        log=log,
        passes_completed=pass_num + 1,
        moves_attempted=move_number,
        moves_accepted=moves_accepted,
        best_objective=best_objective,
        time_seconds=elapsed,
    )
