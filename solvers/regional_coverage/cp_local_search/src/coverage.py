"""Coverage-grid mapping for solver-local strip candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .case_io import CoverageSample, RegionalCoverageCase
from .geometry import haversine_m, oriented_offsets_m


@dataclass(frozen=True, slots=True)
class CoverageFootprint:
    center_latitude_deg: float
    center_longitude_deg: float
    heading_deg: float
    along_half_m: float
    cross_half_m: float


@dataclass(slots=True)
class CoverageIndex:
    samples: tuple[CoverageSample, ...]
    total_weight_m2: float
    sample_weight_by_id: dict[str, float]

    @classmethod
    def from_case(cls, case: RegionalCoverageCase) -> "CoverageIndex":
        return cls(
            samples=case.samples,
            total_weight_m2=case.total_sample_weight_m2,
            sample_weight_by_id={sample.sample_id: sample.weight_m2 for sample in case.samples},
        )

    def samples_for_footprint(self, footprint: CoverageFootprint) -> frozenset[str]:
        radius_m = (footprint.along_half_m**2 + footprint.cross_half_m**2) ** 0.5
        hits: set[str] = set()
        for sample in self.samples:
            if (
                haversine_m(
                    footprint.center_latitude_deg,
                    footprint.center_longitude_deg,
                    sample.latitude_deg,
                    sample.longitude_deg,
                )
                > radius_m
            ):
                continue
            along_m, cross_m = oriented_offsets_m(
                footprint.center_latitude_deg,
                footprint.center_longitude_deg,
                sample.latitude_deg,
                sample.longitude_deg,
                footprint.heading_deg,
            )
            if abs(along_m) <= footprint.along_half_m and abs(cross_m) <= footprint.cross_half_m:
                hits.add(sample.sample_id)
        return frozenset(hits)

    def total_weight(self, sample_ids: Iterable[str]) -> float:
        return sum(self.sample_weight_by_id.get(sample_id, 0.0) for sample_id in sample_ids)


@dataclass(slots=True)
class CoverageAccumulator:
    index: CoverageIndex
    covered_sample_ids: set[str] = field(default_factory=set)

    def marginal_weight(self, sample_ids: Iterable[str]) -> float:
        return sum(
            self.index.sample_weight_by_id.get(sample_id, 0.0)
            for sample_id in sample_ids
            if sample_id not in self.covered_sample_ids
        )

    def add(self, sample_ids: Iterable[str]) -> float:
        weight = self.marginal_weight(sample_ids)
        self.covered_sample_ids.update(sample_ids)
        return weight

