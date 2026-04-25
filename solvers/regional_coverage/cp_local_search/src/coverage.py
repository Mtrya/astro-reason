"""Coverage-grid mapping for solver-local strip candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable

from shapely.geometry import Point, Polygon
from shapely.prepared import prep

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
    sample_bins: dict[tuple[int, int], tuple[CoverageSample, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sample_bins or not self.samples:
            return
        bins: dict[tuple[int, int], list[CoverageSample]] = {}
        for sample in self.samples:
            bins.setdefault(_sample_bin_key(sample.longitude_deg, sample.latitude_deg), []).append(sample)
        self.sample_bins = {key: tuple(rows) for key, rows in bins.items()}

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

    def samples_for_polygons(self, polygons: Iterable[Polygon]) -> frozenset[str]:
        """Return grid samples covered by verifier-shaped lon/lat strip segments."""

        hits: set[str] = set()
        for polygon in polygons:
            if polygon.is_empty:
                continue
            min_lon, min_lat, max_lon, max_lat = polygon.bounds
            prepared = prep(polygon)
            for sample in self._samples_in_bbox(min_lon, min_lat, max_lon, max_lat):
                if sample.sample_id in hits:
                    continue
                if prepared.covers(Point(sample.longitude_deg, sample.latitude_deg)):
                    hits.add(sample.sample_id)
        return frozenset(hits)

    def total_weight(self, sample_ids: Iterable[str]) -> float:
        return sum(self.sample_weight_by_id.get(sample_id, 0.0) for sample_id in sample_ids)

    def _samples_in_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> Iterable[CoverageSample]:
        if not self.sample_bins:
            return ()
        min_lon_bin = math.floor(min_lon)
        max_lon_bin = math.floor(max_lon)
        min_lat_bin = math.floor(min_lat)
        max_lat_bin = math.floor(max_lat)
        rows: list[CoverageSample] = []
        for lon_bin in range(min_lon_bin, max_lon_bin + 1):
            for lat_bin in range(min_lat_bin, max_lat_bin + 1):
                rows.extend(self.sample_bins.get((lon_bin, lat_bin), ()))
        return rows


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


def _sample_bin_key(longitude_deg: float, latitude_deg: float) -> tuple[int, int]:
    return (math.floor(longitude_deg), math.floor(latitude_deg))
