"""Map deterministic strip candidates to coverage-grid sample indices."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from candidates import StripCandidate
from case_io import CoverageSample, RegionalCoverageCase
from geometry import (
    PropagationContext,
    haversine_m,
    strip_centerline_and_half_width_m,
)


DIAGNOSTIC_TIME_BUCKET_S = 3600


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


def _bbox_dict(points: tuple[tuple[float, float], ...]) -> dict[str, float] | None:
    if not points:
        return None
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    return {
        "min_longitude_deg": min(lons),
        "max_longitude_deg": max(lons),
        "min_latitude_deg": min(lats),
        "max_latitude_deg": max(lats),
    }


def _expanded_bbox_dict(
    centerline: tuple[tuple[float, float], ...], margin_m: float
) -> dict[str, float] | None:
    if not centerline:
        return None
    min_lon, max_lon, min_lat, max_lat = _expanded_bbox(centerline, margin_m)
    return {
        "min_longitude_deg": min_lon,
        "max_longitude_deg": max_lon,
        "min_latitude_deg": min_lat,
        "max_latitude_deg": max_lat,
    }


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


def sample_bounds_by_region(case: RegionalCoverageCase) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[CoverageSample]] = defaultdict(list)
    for sample in case.coverage_grid.samples:
        grouped[sample.region_id].append(sample)
    summaries: dict[str, dict[str, Any]] = {}
    for region_id in sorted(grouped):
        samples = grouped[region_id]
        sample_weight_sum = sum(sample.weight_m2 for sample in samples)
        summaries[region_id] = {
            "sample_count": len(samples),
            "min_longitude_deg": min(sample.longitude_deg for sample in samples),
            "max_longitude_deg": max(sample.longitude_deg for sample in samples),
            "min_latitude_deg": min(sample.latitude_deg for sample in samples),
            "max_latitude_deg": max(sample.latitude_deg for sample in samples),
            "sample_weight_sum_m2": sample_weight_sum,
            "total_weight_m2": case.coverage_grid.total_weight_by_region_m2.get(
                region_id,
                sample_weight_sum,
            ),
        }
    return summaries


def _nearest_sample_to_centerline(
    centerline: tuple[tuple[float, float], ...],
    samples: tuple[CoverageSample, ...],
) -> dict[str, Any] | None:
    if not centerline or not samples:
        return None
    best: tuple[float, str, CoverageSample] | None = None
    for sample in samples:
        distance_m = min(
            haversine_m(lon, lat, sample.longitude_deg, sample.latitude_deg)
            for lon, lat in centerline
        )
        key = (distance_m, sample.sample_id, sample)
        if best is None or key[:2] < best[:2]:
            best = key
    if best is None:
        return None
    distance_m, _, sample = best
    return {
        "sample_id": sample.sample_id,
        "region_id": sample.region_id,
        "longitude_deg": sample.longitude_deg,
        "latitude_deg": sample.latitude_deg,
        "distance_m": distance_m,
    }


def _new_bucket() -> dict[str, Any]:
    return {
        "candidate_count": 0,
        "zero_coverage_count": 0,
        "covered_sample_count_sum": 0,
        "unique_sample_indices": set(),
    }


def _add_bucket(
    buckets: dict[str, dict[str, Any]],
    key: str,
    sample_indices: tuple[int, ...],
) -> None:
    bucket = buckets[key]
    bucket["candidate_count"] += 1
    if not sample_indices:
        bucket["zero_coverage_count"] += 1
    bucket["covered_sample_count_sum"] += len(sample_indices)
    bucket["unique_sample_indices"].update(sample_indices)


def _bucket_payload(values: dict[str, dict[str, Any]]) -> dict[str, dict[str, int]]:
    payload: dict[str, dict[str, int]] = {}
    for key in sorted(values):
        value = values[key]
        payload[key] = {
            "candidate_count": value["candidate_count"],
            "zero_coverage_count": value["zero_coverage_count"],
            "covered_sample_count_sum": value["covered_sample_count_sum"],
            "unique_sample_count": len(value["unique_sample_indices"]),
        }
    return payload


def coverage_bucket_summaries(
    candidates: list[StripCandidate],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    *,
    time_bucket_width_s: int = DIAGNOSTIC_TIME_BUCKET_S,
) -> dict[str, Any]:
    by_satellite: dict[str, dict[str, Any]] = defaultdict(_new_bucket)
    by_roll: dict[str, dict[str, Any]] = defaultdict(_new_bucket)
    by_duration: dict[str, dict[str, Any]] = defaultdict(_new_bucket)
    by_time_bucket: dict[str, dict[str, Any]] = defaultdict(_new_bucket)
    for candidate in candidates:
        sample_indices = coverage_by_candidate.get(candidate.candidate_id, ())
        _add_bucket(by_satellite, candidate.satellite_id, sample_indices)
        _add_bucket(by_roll, f"{candidate.roll_deg:.6f}", sample_indices)
        _add_bucket(by_duration, str(candidate.duration_s), sample_indices)
        bucket_start = (
            candidate.start_offset_s // time_bucket_width_s
        ) * time_bucket_width_s
        bucket_end = bucket_start + time_bucket_width_s - 1
        _add_bucket(by_time_bucket, f"{bucket_start:07d}-{bucket_end:07d}", sample_indices)
    return {
        "time_bucket_width_s": time_bucket_width_s,
        "by_satellite": _bucket_payload(by_satellite),
        "by_roll": _bucket_payload(by_roll),
        "by_duration": _bucket_payload(by_duration),
        "by_time_bucket": _bucket_payload(by_time_bucket),
    }


def candidate_diagnostic_rows(
    case: RegionalCoverageCase,
    candidates: list[StripCandidate],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    *,
    limit: int,
    context: PropagationContext | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if context is None:
        context = PropagationContext(
            case.satellites,
            step_s=float(max(1, case.manifest.coverage_sample_step_s)),
        )
    for candidate in candidates[: max(0, limit)]:
        satellite = case.satellites[candidate.satellite_id]
        centerline, half_width_m = strip_centerline_and_half_width_m(
            case.manifest,
            satellite,
            candidate,
            context=context,
        )
        nearest = _nearest_sample_to_centerline(centerline, case.coverage_grid.samples)
        sample_indices = coverage_by_candidate.get(candidate.candidate_id, ())
        rows.append(
            {
                **candidate.as_dict(),
                "covered_sample_count": len(sample_indices),
                "covered_sample_indices": list(sample_indices),
                "centerline_bbox": _bbox_dict(centerline),
                "coverage_bbox": _expanded_bbox_dict(centerline, half_width_m),
                "half_width_m": half_width_m,
                "nearest_sample": nearest,
                "nearest_sample_margin_m": (
                    nearest["distance_m"] - half_width_m if nearest is not None else None
                ),
            }
        )
    return rows


def build_coverage_diagnostics(
    case: RegionalCoverageCase,
    candidates: list[StripCandidate],
    coverage_by_candidate: dict[str, tuple[int, ...]],
    *,
    limit: int,
    context: PropagationContext | None = None,
) -> dict[str, Any]:
    zero_count = sum(
        1
        for candidate in candidates
        if not coverage_by_candidate.get(candidate.candidate_id, ())
    )
    return {
        "candidate_count": len(candidates),
        "debug_candidate_limit": max(0, limit),
        "all_candidates_zero_coverage": len(candidates) > 0 and zero_count == len(candidates),
        "zero_coverage_count": zero_count,
        "nonzero_coverage_count": len(candidates) - zero_count,
        "sample_bounds_by_region": sample_bounds_by_region(case),
        "coverage_buckets": coverage_bucket_summaries(
            candidates,
            coverage_by_candidate,
        ),
        "candidate_diagnostics": candidate_diagnostic_rows(
            case,
            candidates,
            coverage_by_candidate,
            limit=limit,
            context=context,
        ),
    }


def build_candidate_coverage(
    case: RegionalCoverageCase, candidates: list[StripCandidate]
) -> tuple[dict[str, tuple[int, ...]], CoverageSummary]:
    context = PropagationContext(
        case.satellites,
        step_s=float(max(1, case.manifest.coverage_sample_step_s)),
    )
    mapping: dict[str, tuple[int, ...]] = {}
    unique_samples: set[int] = set()
    sizes: list[int] = []
    for candidate in candidates:
        satellite = case.satellites[candidate.satellite_id]
        centerline, half_width_m = strip_centerline_and_half_width_m(
            case.manifest,
            satellite,
            candidate,
            context=context,
        )
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
