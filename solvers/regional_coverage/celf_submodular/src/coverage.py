"""Map deterministic strip candidates to coverage-grid sample indices."""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from candidates import StripCandidate
from case_io import CoverageSample, RegionalCoverageCase
from geometry import (
    EARTH_RADIUS_M,
    PropagationContext,
    haversine_m,
    strip_centerline_and_half_width_m,
)


DIAGNOSTIC_TIME_BUCKET_S = 3600
DEFAULT_SPATIAL_BIN_DEG = 0.25


@dataclass(frozen=True, slots=True)
class CoverageMappingConfig:
    method: str = "indexed"
    spatial_bin_deg: float = DEFAULT_SPATIAL_BIN_DEG

    def as_status_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "spatial_bin_deg": self.spatial_bin_deg,
        }


DEFAULT_COVERAGE_MAPPING_CONFIG = CoverageMappingConfig()


@dataclass(frozen=True, slots=True)
class CoverageRuntimeSummary:
    method: str
    spatial_bin_deg: float | None
    sample_count: int
    spatial_cell_count: int
    candidate_count: int
    candidate_sample_upper_bound: int
    candidate_cell_range_visits: int
    candidate_cell_visits: int
    candidate_empty_cell_skips: int
    candidate_bbox_sample_checks: int
    candidate_centerline_latitude_prefilter_skips: int
    candidate_exact_distance_checks: int

    def as_dict(self) -> dict[str, Any]:
        upper_bound = self.candidate_sample_upper_bound
        checked = self.candidate_bbox_sample_checks
        return {
            "method": self.method,
            "spatial_bin_deg": self.spatial_bin_deg,
            "sample_count": self.sample_count,
            "spatial_cell_count": self.spatial_cell_count,
            "candidate_count": self.candidate_count,
            "candidate_sample_upper_bound": upper_bound,
            "candidate_cell_range_visits": self.candidate_cell_range_visits,
            "candidate_cell_visits": self.candidate_cell_visits,
            "candidate_empty_cell_skips": self.candidate_empty_cell_skips,
            "candidate_bbox_sample_checks": checked,
            "candidate_centerline_latitude_prefilter_skips": (
                self.candidate_centerline_latitude_prefilter_skips
            ),
            "candidate_exact_distance_checks": self.candidate_exact_distance_checks,
            "bbox_prefilter_reduction_ratio": (
                1.0 - (checked / upper_bound) if upper_bound > 0 else None
            ),
            "sparse_cell_skip_ratio": (
                self.candidate_empty_cell_skips / self.candidate_cell_range_visits
                if self.candidate_cell_range_visits > 0
                else None
            ),
        }


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


class CoverageStats:
    def __init__(self) -> None:
        self.candidate_cell_range_visits = 0
        self.candidate_cell_visits = 0
        self.candidate_empty_cell_skips = 0
        self.candidate_bbox_sample_checks = 0
        self.candidate_centerline_latitude_prefilter_skips = 0
        self.candidate_exact_distance_checks = 0


@dataclass(frozen=True, slots=True)
class SpatialSampleIndex:
    bin_deg: float
    cells: dict[tuple[int, int], tuple[CoverageSample, ...]]
    lon_cells: tuple[int, ...]
    cells_by_lon: dict[int, tuple[tuple[int, tuple[CoverageSample, ...]], ...]]

    @property
    def cell_count(self) -> int:
        return len(self.cells)

    @classmethod
    def build(
        cls,
        samples: tuple[CoverageSample, ...],
        *,
        bin_deg: float,
    ) -> "SpatialSampleIndex":
        if bin_deg <= 0.0:
            raise ValueError("coverage_mapping.spatial_bin_deg must be positive")
        grouped: dict[tuple[int, int], list[CoverageSample]] = defaultdict(list)
        for sample in samples:
            grouped[_spatial_cell(sample.longitude_deg, sample.latitude_deg, bin_deg)].append(
                sample
            )
        cells = {
            key: tuple(sorted(values, key=lambda sample: sample.index))
            for key, values in grouped.items()
        }
        by_lon: dict[int, list[tuple[int, tuple[CoverageSample, ...]]]] = defaultdict(list)
        for (lon_cell, lat_cell), samples_for_cell in cells.items():
            by_lon[lon_cell].append((lat_cell, samples_for_cell))
        cells_by_lon = {
            lon_cell: tuple(sorted(lat_rows, key=lambda row: row[0]))
            for lon_cell, lat_rows in by_lon.items()
        }
        return cls(
            bin_deg=bin_deg,
            cells=dict(sorted(cells.items())),
            lon_cells=tuple(sorted(cells_by_lon)),
            cells_by_lon=dict(sorted(cells_by_lon.items())),
        )


def load_coverage_mapping_config(config_dir: Path | None) -> CoverageMappingConfig:
    if config_dir is None or not config_dir:
        return CoverageMappingConfig()
    path = config_dir / "config.yaml"
    if not path.is_file():
        return CoverageMappingConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a mapping")
    section = raw.get("coverage_mapping", {})
    if not section:
        return CoverageMappingConfig()
    if not isinstance(section, dict):
        raise ValueError(f"{path}: coverage_mapping must be a mapping")
    method = str(section.get("method", DEFAULT_COVERAGE_MAPPING_CONFIG.method))
    if method not in {"indexed", "simple"}:
        raise ValueError(f"{path}: coverage_mapping.method must be indexed or simple")
    return CoverageMappingConfig(
        method=method,
        spatial_bin_deg=float(
            section.get(
                "spatial_bin_deg",
                DEFAULT_COVERAGE_MAPPING_CONFIG.spatial_bin_deg,
            )
        ),
    )


def _spatial_cell(lon_deg: float, lat_deg: float, bin_deg: float) -> tuple[int, int]:
    return (math.floor(lon_deg / bin_deg), math.floor(lat_deg / bin_deg))


def _iter_bbox_cells(
    min_lon: float,
    max_lon: float,
    min_lat: float,
    max_lat: float,
    *,
    bin_deg: float,
):
    lon_start = math.floor(min_lon / bin_deg)
    lon_end = math.floor(max_lon / bin_deg)
    lat_start = math.floor(min_lat / bin_deg)
    lat_end = math.floor(max_lat / bin_deg)
    for lon_cell in range(lon_start, lon_end + 1):
        for lat_cell in range(lat_start, lat_end + 1):
            yield (lon_cell, lat_cell)


def _bbox_cell_ranges(
    min_lon: float,
    max_lon: float,
    min_lat: float,
    max_lat: float,
    *,
    bin_deg: float,
) -> tuple[int, int, int, int]:
    return (
        math.floor(min_lon / bin_deg),
        math.floor(max_lon / bin_deg),
        math.floor(min_lat / bin_deg),
        math.floor(max_lat / bin_deg),
    )


def build_coverage_sample_index(
    case: RegionalCoverageCase,
    config: CoverageMappingConfig,
) -> SpatialSampleIndex | None:
    if config.method == "simple":
        return None
    if config.method == "indexed":
        return SpatialSampleIndex.build(
            case.coverage_grid.samples,
            bin_deg=config.spatial_bin_deg,
        )
    raise ValueError(f"unsupported coverage mapping method {config.method!r}")


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


def _latitude_margin_deg(half_width_m: float) -> float:
    return math.degrees(max(0.0, half_width_m) / EARTH_RADIUS_M)


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
    *,
    stats: CoverageStats | None = None,
) -> tuple[int, ...]:
    if not centerline:
        return ()
    min_lon, max_lon, min_lat, max_lat = _expanded_bbox(centerline, half_width_m)
    latitude_margin_deg = _latitude_margin_deg(half_width_m)
    covered: set[int] = set()
    for sample in samples:
        if stats is not None:
            stats.candidate_bbox_sample_checks += 1
        if not (min_lat <= sample.latitude_deg <= max_lat):
            continue
        if not (min_lon <= sample.longitude_deg <= max_lon):
            continue
        for lon, lat in centerline:
            if abs(sample.latitude_deg - lat) > latitude_margin_deg:
                if stats is not None:
                    stats.candidate_centerline_latitude_prefilter_skips += 1
                continue
            if stats is not None:
                stats.candidate_exact_distance_checks += 1
            if haversine_m(lon, lat, sample.longitude_deg, sample.latitude_deg) <= half_width_m:
                covered.add(sample.index)
                break
    return tuple(sorted(covered))


def sample_indices_near_centerline_indexed(
    centerline: tuple[tuple[float, float], ...],
    sample_index: SpatialSampleIndex,
    half_width_m: float,
    *,
    stats: CoverageStats | None = None,
) -> tuple[int, ...]:
    if not centerline:
        return ()
    min_lon, max_lon, min_lat, max_lat = _expanded_bbox(centerline, half_width_m)
    latitude_margin_deg = _latitude_margin_deg(half_width_m)
    lon_start, lon_end, lat_start, lat_end = _bbox_cell_ranges(
        min_lon,
        max_lon,
        min_lat,
        max_lat,
        bin_deg=sample_index.bin_deg,
    )
    covered: set[int] = set()
    seen_samples: set[int] = set()
    nonempty_cell_visits = 0
    lon_index_start = bisect_left(sample_index.lon_cells, lon_start)
    lon_index_end = bisect_right(sample_index.lon_cells, lon_end)
    for lon_cell in sample_index.lon_cells[lon_index_start:lon_index_end]:
        lat_rows = sample_index.cells_by_lon.get(lon_cell, ())
        lat_cells = tuple(lat_cell for lat_cell, _ in lat_rows)
        start_index = bisect_left(lat_cells, lat_start)
        end_index = bisect_right(lat_cells, lat_end)
        for _, samples in lat_rows[start_index:end_index]:
            nonempty_cell_visits += 1
            for sample in samples:
                if sample.index in seen_samples:
                    continue
                seen_samples.add(sample.index)
                if stats is not None:
                    stats.candidate_bbox_sample_checks += 1
                if not (min_lat <= sample.latitude_deg <= max_lat):
                    continue
                if not (min_lon <= sample.longitude_deg <= max_lon):
                    continue
                for lon, lat in centerline:
                    if abs(sample.latitude_deg - lat) > latitude_margin_deg:
                        if stats is not None:
                            stats.candidate_centerline_latitude_prefilter_skips += 1
                        continue
                    if stats is not None:
                        stats.candidate_exact_distance_checks += 1
                    if haversine_m(
                        lon,
                        lat,
                        sample.longitude_deg,
                        sample.latitude_deg,
                    ) <= half_width_m:
                        covered.add(sample.index)
                        break
    if stats is not None:
        range_cell_count = (lon_end - lon_start + 1) * (lat_end - lat_start + 1)
        stats.candidate_cell_range_visits += range_cell_count
        stats.candidate_cell_visits += nonempty_cell_visits
        stats.candidate_empty_cell_skips += range_cell_count - nonempty_cell_visits
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


def _summarize_coverage(
    candidates: list[StripCandidate],
    mapping: dict[str, tuple[int, ...]],
) -> CoverageSummary:
    unique_samples: set[int] = set()
    sizes: list[int] = []
    for candidate in candidates:
        sample_indices = mapping.get(candidate.candidate_id, ())
        unique_samples.update(sample_indices)
        sizes.append(len(sample_indices))
    histogram = Counter(str(size) for size in sizes)
    return CoverageSummary(
        candidate_count=len(candidates),
        zero_coverage_count=sum(1 for size in sizes if size == 0),
        unique_sample_count=len(unique_samples),
        min_samples_per_candidate=min(sizes) if sizes else 0,
        max_samples_per_candidate=max(sizes) if sizes else 0,
        mean_samples_per_candidate=(sum(sizes) / len(sizes) if sizes else 0.0),
        coverage_count_histogram=dict(sorted(histogram.items(), key=lambda kv: int(kv[0]))),
    )


def build_candidate_coverage_with_runtime(
    case: RegionalCoverageCase,
    candidates: list[StripCandidate],
    *,
    config: CoverageMappingConfig | None = None,
    context: PropagationContext | None = None,
    sample_index: SpatialSampleIndex | None = None,
) -> tuple[dict[str, tuple[int, ...]], CoverageSummary, CoverageRuntimeSummary]:
    config = config or CoverageMappingConfig()
    if context is None:
        context = PropagationContext(
            case.satellites,
            step_s=float(max(1, case.manifest.coverage_sample_step_s)),
        )
    stats = CoverageStats()
    mapping: dict[str, tuple[int, ...]] = {}
    if sample_index is None:
        sample_index = build_coverage_sample_index(case, config)

    for candidate in candidates:
        satellite = case.satellites[candidate.satellite_id]
        centerline, half_width_m = strip_centerline_and_half_width_m(
            case.manifest,
            satellite,
            candidate,
            context=context,
        )
        if sample_index is None:
            sample_indices = sample_indices_near_centerline(
                centerline,
                case.coverage_grid.samples,
                half_width_m,
                stats=stats,
            )
        else:
            sample_indices = sample_indices_near_centerline_indexed(
                centerline,
                sample_index,
                half_width_m,
                stats=stats,
            )
        mapping[candidate.candidate_id] = sample_indices

    summary = _summarize_coverage(candidates, mapping)
    runtime = CoverageRuntimeSummary(
        method=config.method,
        spatial_bin_deg=config.spatial_bin_deg if sample_index is not None else None,
        sample_count=len(case.coverage_grid.samples),
        spatial_cell_count=sample_index.cell_count if sample_index is not None else 0,
        candidate_count=len(candidates),
        candidate_sample_upper_bound=len(case.coverage_grid.samples) * len(candidates),
        candidate_cell_range_visits=stats.candidate_cell_range_visits,
        candidate_cell_visits=stats.candidate_cell_visits,
        candidate_empty_cell_skips=stats.candidate_empty_cell_skips,
        candidate_bbox_sample_checks=stats.candidate_bbox_sample_checks,
        candidate_centerline_latitude_prefilter_skips=(
            stats.candidate_centerline_latitude_prefilter_skips
        ),
        candidate_exact_distance_checks=stats.candidate_exact_distance_checks,
    )
    return mapping, summary, runtime


def build_candidate_coverage(
    case: RegionalCoverageCase,
    candidates: list[StripCandidate],
    *,
    config: CoverageMappingConfig | None = None,
) -> tuple[dict[str, tuple[int, ...]], CoverageSummary]:
    mapping, summary, _ = build_candidate_coverage_with_runtime(
        case,
        candidates,
        config=config,
    )
    return mapping, summary
