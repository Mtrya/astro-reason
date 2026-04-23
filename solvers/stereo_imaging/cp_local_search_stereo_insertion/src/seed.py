"""Deterministic greedy seed construction for stereo/tri-stereo products.

Builds a reproducible initial schedule that maximizes coverage before local
search spends effort improving quality.  Products are ranked coverage-first
with dynamic scarcity updates, then inserted atomically via sequence.py.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from case_io import StereoCase
from products import ProductLibrary, ProductType, StereoProduct
from sequence import SequenceState, create_empty_state, insert_product


@dataclass(frozen=True, slots=True)
class SeedConfig:
    seed_only: bool = False
    tri_first: bool = True
    max_seed_products: int | None = None
    coverage_bonus: float = 10.0
    scarcity_weight: float = 1.0
    tri_bonus: float = 0.5

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "SeedConfig":
        payload = payload or {}
        return cls(
            seed_only=bool(payload.get("seed_only", False)),
            tri_first=bool(payload.get("tri_first", True)),
            max_seed_products=_optional_positive_int(
                payload.get("max_seed_products")
            ),
            coverage_bonus=float(payload.get("coverage_bonus", 10.0)),
            scarcity_weight=float(payload.get("scarcity_weight", 1.0)),
            tri_bonus=float(payload.get("tri_bonus", 0.5)),
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
) -> tuple[float, float, float, float, str]:
    """Return a sort key for descending coverage-first ordering.

    Tuple elements (all meant for descending sort except last):
    1. coverage bonus (uncovered targets win)
    2. scarcity (fewer remaining products win)
    3. tri bonus (tri-stereo wins when tri_first)
    4. quality (higher wins)
    5. product_id (ascending lexicographic tie-break)
    """
    uncovered_bonus = config.coverage_bonus if product.target_id not in covered_targets else 0.0
    scarcity = config.scarcity_weight / max(1, remaining_counts.get(product.target_id, 1))
    if config.tri_first:
        tri_score = config.tri_bonus if product.product_type == ProductType.TRI else 0.0
    else:
        tri_score = config.tri_bonus if product.product_type == ProductType.PAIR else 0.0

    return (
        uncovered_bonus + scarcity + tri_score + product.quality,
        scarcity,
        tri_score,
        product.quality,
        product.product_id,
    )


def build_greedy_seed(
    product_library: ProductLibrary,
    case: StereoCase,
    config: SeedConfig | None = None,
) -> SeedResult:
    """Construct a deterministic greedy seed schedule.

    Iteratively selects the highest-ranked feasible product, attempts atomic
    insertion into per-satellite sequences, and records accept/reject decisions.
    Ranking is recomputed after each accepted insertion so that covered targets
    and scarce remaining alternatives are reflected immediately.
    """
    config = config or SeedConfig()
    state = create_empty_state(case)

    accepted_products: list[StereoProduct] = []
    rejected_records: list[SeedDecisionRecord] = []
    covered_targets: set[str] = set()

    pool: list[StereoProduct] = [p for p in product_library.products if p.feasible]
    iterations = 0

    while pool:
        if config.max_seed_products is not None and len(accepted_products) >= config.max_seed_products:
            break

        remaining_counts = _compute_remaining_counts(pool)

        # O(n) max scan instead of O(n log n) sort; preserves exact deterministic order
        best_idx = max(
            range(len(pool)),
            key=lambda i: _product_sort_key(pool[i], covered_targets, remaining_counts, config),
        )
        best = pool.pop(best_idx)
        iterations += 1

        result = insert_product(best, state, case)
        if result.success:
            accepted_products.append(best)
            covered_targets.add(best.target_id)
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

    return SeedResult(
        accepted_products=accepted_products,
        rejected_records=rejected_records,
        covered_targets=covered_targets,
        state=state,
        config=config,
        iterations=iterations,
    )
