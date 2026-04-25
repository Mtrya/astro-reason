"""Map deterministic strip candidates to coverage-grid sample indices."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

from candidates import StripCandidate
from case_io import CoverageSample, RegionalCoverageCase
from geometry import approximate_half_width_m, haversine_m, strip_centerline_lon_lat


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    candidate_count: int
    zero_coverage_count: int
    unique_sample_count: int
    min_samples_per_candidate: int
    max_samples_per_candidate: int
    mean_samples_per_candidate: float
    coverage_count_histogram: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": self.candidate_count,
            "zero_coverage_count": self.zero_coverage_count,
            "unique_sample_count": self.unique_sample_count,
            "min_samples_per_candidate": self.min_samples_per_candidate,
            "max_samples_per_candidate": self.max_samples_per_candidate,
            "mean_samples_per_candidate": self.mean_samples_per_candidate,
            "coverage_count_histogram": self.coverage_count_histogram,
        }


def _expanded_bbox(
    centerline: tuple[tuple[float, float], ...], margin_m: float
) -> tuple[float, float, float, float]:
    lons = [point[0] for point in centerline]
    lats = [point[1] for point in centerline]
    mean_lat = sum(lats) / max(1, len(lats))
    lat_margin = margin_m / 111_320.0
    lon_margin = margin_m / max(1.0, 111_320.0 * abs(math.cos(math.radians(mean_lat))))
    return (
        min(lons) - lon_margin,
        max(lons) + lon_margin,
        min(lats) - lat_margin,
        max(lats) + lat_margin,
    )


def sample_indices_near_centerline(
    centerline: tuple[tuple[float, float], ...],
    samples: tuple[CoverageSample, ...],
    half_width_m: float,
) -> tuple[int, ...]:
    if not centerline:
        return ()
    min_lon, max_lon, min_lat, max_lat = _expanded_bbox(centerline, half_width_m)
    covered: set[int] = set()
    for sample in samples:
        if not (min_lat <= sample.latitude_deg <= max_lat):
            continue
        if not (min_lon <= sample.longitude_deg <= max_lon):
            continue
        for lon, lat in centerline:
            if haversine_m(lon, lat, sample.longitude_deg, sample.latitude_deg) <= half_width_m:
                covered.add(sample.index)
                break
    return tuple(sorted(covered))


def build_candidate_coverage(
    case: RegionalCoverageCase, candidates: list[StripCandidate]
) -> tuple[dict[str, tuple[int, ...]], CoverageSummary]:
    mapping: dict[str, tuple[int, ...]] = {}
    unique_samples: set[int] = set()
    sizes: list[int] = []
    for candidate in candidates:
        satellite = case.satellites[candidate.satellite_id]
        centerline = strip_centerline_lon_lat(case.manifest, satellite, candidate)
        half_width_m = approximate_half_width_m(satellite, candidate)
        sample_indices = sample_indices_near_centerline(
            centerline, case.coverage_grid.samples, half_width_m
        )
        mapping[candidate.candidate_id] = sample_indices
        unique_samples.update(sample_indices)
        sizes.append(len(sample_indices))
    histogram = Counter(str(size) for size in sizes)
    summary = CoverageSummary(
        candidate_count=len(candidates),
        zero_coverage_count=sum(1 for size in sizes if size == 0),
        unique_sample_count=len(unique_samples),
        min_samples_per_candidate=min(sizes) if sizes else 0,
        max_samples_per_candidate=max(sizes) if sizes else 0,
        mean_samples_per_candidate=(sum(sizes) / len(sizes) if sizes else 0.0),
        coverage_count_histogram=dict(sorted(histogram.items(), key=lambda kv: int(kv[0]))),
    )
    return mapping, summary
