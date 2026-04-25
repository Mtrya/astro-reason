"""Deterministic greedy seed construction for stereo/tri-stereo products.

Builds a reproducible initial schedule that maximizes coverage before local
search spends effort improving quality.  Products are ranked coverage-first
with dynamic scarcity updates, then inserted atomically via sequence.py.

Changes:
- Dedicated tri-stereo-first pre-pass: attempt best feasible tri-stereo per
  target before falling back to pair-stereo greedy.
- Lexicographic sort key replaces ad-hoc composite bonus formula.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from typing import Any

from case_io import StereoCase
from products import ProductLibrary, ProductType, StereoProduct
from sequence import SequenceState, create_empty_state, insert_product


@dataclass(frozen=True, slots=True)
class SeedConfig:
    seed_only: bool = False
    tri_stereo_seed_phase: bool = True
    max_seed_products: int | None = None
    pair_weight: float = 1.0
    tri_weight: float = 1.5

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "SeedConfig":
        payload = payload or {}
        return cls(
            seed_only=bool(payload.get("seed_only", False)),
            tri_stereo_seed_phase=bool(payload.get("tri_stereo_seed_phase", True)),
            max_seed_products=_optional_positive_int(
                payload.get("max_seed_products")
            ),
            pair_weight=float(payload.get("pair_weight", 1.0)),
            tri_weight=float(payload.get("tri_weight", 1.5)),
        )

    def as_status_dict(self) -> dict[str, Any]:
        return asdict(self)


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("max_seed_products must be a positive integer")
    return parsed


@dataclass(slots=True)
class SeedDecisionRecord:
    product_id: str
    target_id: str
    product_type: str
    quality: float
    decision: str  # "accepted" or "rejected"
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "target_id": self.target_id,
            "product_type": self.product_type,
            "quality": self.quality,
            "decision": self.decision,
            "reasons": list(self.reasons),
        }


@dataclass(slots=True)
class SeedResult:
    accepted_products: list[StereoProduct]
    rejected_records: list[SeedDecisionRecord]
    covered_targets: set[str]
    state: SequenceState
    config: SeedConfig
    iterations: int
    tri_accepted: int = 0

    @property
    def accepted_count(self) -> int:
        return len(self.accepted_products)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected_records)

    @property
    def covered_target_count(self) -> int:
        return len(self.covered_targets)

    @property
    def sum_quality(self) -> float:
        return sum(p.quality for p in self.accepted_products)

    @property
    def mean_quality(self) -> float:
        n = self.accepted_count
        return self.sum_quality / n if n > 0 else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.as_status_dict(),
            "iterations": self.iterations,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "covered_target_count": self.covered_target_count,
            "covered_target_ids": sorted(self.covered_targets),
            "tri_accepted": self.tri_accepted,
            "sum_quality": round(self.sum_quality, 6),
            "mean_quality": round(self.mean_quality, 6),
            "accepted_product_ids": [p.product_id for p in self.accepted_products],
        }


def _compute_remaining_counts(
    products: list[StereoProduct],
) -> dict[str, int]:
    """Count remaining feasible products per target."""
    counts: dict[str, int] = {}
    for p in products:
        counts[p.target_id] = counts.get(p.target_id, 0) + 1
    return counts


def _product_sort_key(
    product: StereoProduct,
    covered_targets: set[str],
    remaining_counts: dict[str, int],
    config: SeedConfig,
    rng: random.Random | None = None,
) -> tuple[float, float, float, float, str]:
    """Return a lexicographic sort key for descending coverage-first ordering.

    Tuple elements (higher is better for max()):
    1. coverage_value          – 1.0 if target is uncovered, 0.0 otherwise
    2. scarcity_plus_quality   – scarcity + weighted_quality (combined bonus)
    3. scarcity                – 1.0 / remaining_count for this target
    4. weighted_quality        – quality * tri_weight or pair_weight
    5. product_id              – deterministic tie-break

    When *rng* is provided, a tiny random epsilon is added to the second
    element to break ties deterministically but differently per run.
    """
    coverage_value = 1.0 if product.target_id not in covered_targets else 0.0
    weight = config.tri_weight if product.product_type == ProductType.TRI else config.pair_weight
    weighted_quality = product.quality * weight
    scarcity = 1.0 / max(1, remaining_counts.get(product.target_id, 1))
    epsilon = rng.random() * 1e-9 if rng is not None else 0.0
    return (coverage_value, scarcity + weighted_quality + epsilon, scarcity, weighted_quality, product.product_id)


def _attempt_tri_stereo_pre_pass(
    product_library: ProductLibrary,
    state: SequenceState,
    case: StereoCase,
    config: SeedConfig,
) -> tuple[list[StereoProduct], list[SeedDecisionRecord], set[str], int]:
    """Attempt to insert the best feasible tri-stereo product for each target.

    Returns (accepted_products, rejected_records, covered_targets, tri_accepted).
    """
    accepted: list[StereoProduct] = []
    rejected: list[SeedDecisionRecord] = []
    covered: set[str] = set()
    tri_accepted = 0

    # Gather feasible tri-stereo products grouped by target
    tri_by_target: dict[str, list[StereoProduct]] = {}
    for target_id, products in sorted(product_library.per_target_products.items()):
        tri_products = [p for p in products if p.product_type == ProductType.TRI]
        if tri_products:
            tri_by_target[target_id] = tri_products

    # Process targets in deterministic order
    for target_id in sorted(tri_by_target):
        if config.max_seed_products is not None and len(accepted) >= config.max_seed_products:
            break

        # Sort by quality desc, product_id asc for deterministic selection
        candidates = sorted(
            tri_by_target[target_id],
            key=lambda p: (-p.quality, p.product_id),
        )

        for tri_product in candidates:
            result = insert_product(tri_product, state, case)
            if result.success:
                accepted.append(tri_product)
                covered.add(target_id)
                tri_accepted += 1
                break
            else:
                rejected.append(
                    SeedDecisionRecord(
                        product_id=tri_product.product_id,
                        target_id=target_id,
                        product_type=tri_product.product_type.value,
                        quality=tri_product.quality,
                        decision="rejected",
                        reasons=result.reject_reasons,
                    )
                )

    return accepted, rejected, covered, tri_accepted


def build_greedy_seed(
    product_library: ProductLibrary,
    case: StereoCase,
    config: SeedConfig | None = None,
    rng: random.Random | None = None,
) -> SeedResult:
    """Construct a deterministic greedy seed schedule.

    Algorithm:
    1. Pair-stereo coverage-first greedy: iteratively select highest-ranked
       feasible product (pair or tri) and attempt atomic insertion.
    2. Optional tri-stereo upgrade pass: for each target covered by a pair,
       try to replace it with a higher-quality tri-stereo product.  This
       preserves coverage while improving quality where tri-stereo fits.

    Ranking is recomputed after each accepted insertion so that covered targets
    and scarce remaining alternatives are reflected immediately.
    """
    config = config or SeedConfig()
    state = create_empty_state(case)

    accepted_products: list[StereoProduct] = []
    rejected_records: list[SeedDecisionRecord] = []
    covered_targets: set[str] = set()
    tri_accepted = 0
    iterations = 0

    # Step 1 — build pair-primary seed (pairs compete with tri in same pool)
    pool: list[StereoProduct] = list(product_library.products)

    while pool:
        if config.max_seed_products is not None and len(accepted_products) >= config.max_seed_products:
            break

        remaining_counts = _compute_remaining_counts(pool)

        best_idx = max(
            range(len(pool)),
            key=lambda i: _product_sort_key(pool[i], covered_targets, remaining_counts, config, rng),
        )
        best = pool.pop(best_idx)

        # Skip products for targets already covered by a previous insertion
        if best.target_id in covered_targets:
            continue

        iterations += 1

        result = insert_product(best, state, case)
        if result.success:
            accepted_products.append(best)
            covered_targets.add(best.target_id)
            if best.product_type == ProductType.TRI:
                tri_accepted += 1
        else:
            rejected_records.append(
                SeedDecisionRecord(
                    product_id=best.product_id,
                    target_id=best.target_id,
                    product_type=best.product_type.value,
                    quality=best.quality,
                    decision="rejected",
                    reasons=result.reject_reasons,
                )
            )

    # Step 2 — tri-stereo upgrade pass
    # For targets covered by a pair, try to upgrade to tri-stereo if a
    # higher-quality tri product exists and can fit in the freed capacity.
    if config.tri_stereo_seed_phase:
        # Build target -> covering product map
        target_to_product: dict[str, StereoProduct] = {}
        for p in accepted_products:
            if p.target_id not in target_to_product or p.product_type == ProductType.TRI:
                target_to_product[p.target_id] = p

        # Gather candidate targets for upgrade: covered by pair, with feasible tri
        upgrade_targets: list[str] = []
        for target_id, products in sorted(product_library.per_target_products.items()):
            if target_id not in target_to_product:
                continue
            current = target_to_product[target_id]
            if current.product_type == ProductType.TRI:
                continue  # already tri
            tri_candidates = [
                p for p in products
                if p.product_type == ProductType.TRI
            ]
            if tri_candidates:
                upgrade_targets.append(target_id)

        # Optionally shuffle upgrade target order for multi-run diversity
        if rng is not None:
            upgrade_targets = list(upgrade_targets)
            rng.shuffle(upgrade_targets)

        for target_id in upgrade_targets:
            current = target_to_product[target_id]
            current_weighted = current.quality * config.pair_weight

            # Best tri product for this target by weighted quality
            tri_candidates = [
                p for p in product_library.per_target_products[target_id]
                if p.product_type == ProductType.TRI
            ]
            tri_candidates.sort(key=lambda p: (-p.quality, p.product_id))
            best_tri = tri_candidates[0]
            tri_weighted = best_tri.quality * config.tri_weight

            # Only upgrade if tri offers strictly better weighted quality
            if tri_weighted <= current_weighted:
                continue

            # Attempt upgrade: remove pair, insert tri
            from sequence import remove_product, _snapshot_state, _restore_state
            snapshot = _snapshot_state(state)
            remove_product(current, state, case)

            # Remove current from accepted list
            accepted_products = [p for p in accepted_products if p.product_id != current.product_id]
            # Note: covered_targets stays unchanged since we're replacing, not uncovering

            result = insert_product(best_tri, state, case)
            if result.success:
                accepted_products.append(best_tri)
                tri_accepted += 1
            else:
                # Restore pair product
                _restore_state(state, snapshot)
                accepted_products.append(current)
                rejected_records.append(
                    SeedDecisionRecord(
                        product_id=best_tri.product_id,
                        target_id=target_id,
                        product_type=best_tri.product_type.value,
                        quality=best_tri.quality,
                        decision="rejected",
                        reasons=result.reject_reasons + ("tri_upgrade_failed",),
                    )
                )

    return SeedResult(
        accepted_products=accepted_products,
        rejected_records=rejected_records,
        covered_targets=covered_targets,
        state=state,
        config=config,
        iterations=iterations,
        tri_accepted=tri_accepted,
    )
