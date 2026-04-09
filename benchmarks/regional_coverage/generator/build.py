"""Deterministic canonical dataset generator for regional_coverage."""

from __future__ import annotations

import json
import math
import random
import shutil
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from pyproj import CRS, Geod, Transformer
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import transform

from .cached_satellites import CACHED_SATELLITES


CANONICAL_SEED = 20260408
NUM_CANONICAL_CASES = 5
SAMPLE_SPACING_M = 5_000.0
TIME_STEP_S = 10
COVERAGE_SAMPLE_STEP_S = 5
HORIZON_HOURS = 72
MAX_ACTIONS_TOTAL = 64
MIN_TOTAL_REGION_AREA_M2 = 1.0e11
MAX_TOTAL_REGION_AREA_M2 = 4.5e11
MIN_REGION_AREA_M2 = 2.5e10
MAX_REGION_AREA_M2 = 1.8e11
MIN_SAMPLES_PER_CASE = 5_000
MAX_SAMPLES_PER_CASE = 20_000
MIN_REGION_SEPARATION_DEG = 12.0
DATASET_ATTEMPT_STRIDE = 1_000_003
CASE_ATTEMPT_STRIDE = 10_007
WGS84_GEOD = Geod(ellps="WGS84")
_EARTH_MEAN_RADIUS_M = 6_371_008.8
_REGION_LIBRARY_PATH = Path(__file__).with_name("region_library.geojson")


@dataclass(frozen=True)
class RegionRecord:
    region_id: str
    weight: float
    polygon_lonlat: Polygon
    area_m2: float
    centroid_lon: float
    centroid_lat: float


@dataclass(frozen=True)
class SensorDef:
    min_edge_off_nadir_deg: float
    max_edge_off_nadir_deg: float
    cross_track_fov_deg: float
    min_strip_duration_s: int
    max_strip_duration_s: int


@dataclass(frozen=True)
class AgilityDef:
    max_roll_rate_deg_per_s: float
    max_roll_acceleration_deg_per_s2: float
    settling_time_s: float


@dataclass(frozen=True)
class PowerDef:
    battery_capacity_wh: int
    initial_battery_wh: int
    idle_power_w: int
    imaging_power_w: int
    slew_power_w: int
    sunlit_charge_power_w: int
    imaging_duty_limit_s_per_orbit: int | None


@dataclass(frozen=True)
class SatelliteDef:
    satellite_id: str
    tle_line1: str
    tle_line2: str
    tle_epoch: str
    sensor: SensorDef
    agility: AgilityDef
    power: PowerDef


@dataclass(frozen=True)
class GridSample:
    sample_id: str
    longitude_deg: float
    latitude_deg: float
    weight_m2: float


@dataclass(frozen=True)
class RegionCoverageGrid:
    region_id: str
    total_weight_m2: float
    samples: tuple[GridSample, ...]


@dataclass(frozen=True)
class BuiltCase:
    case_id: str
    case_seed: int
    horizon_start: str
    horizon_end: str
    satellites: tuple[dict[str, Any], ...]
    regions_geojson: dict[str, Any]
    coverage_grid: dict[str, Any]
    total_region_area_m2: float
    satellite_class_ids: tuple[str, ...]
    num_regions: int


SATELLITE_CLASSES: dict[str, dict[str, Any]] = {
    "sar_narrow": {
        "sensor": SensorDef(
            min_edge_off_nadir_deg=18.0,
            max_edge_off_nadir_deg=34.0,
            cross_track_fov_deg=2.8,
            min_strip_duration_s=20,
            max_strip_duration_s=120,
        ),
        "agility": AgilityDef(
            max_roll_rate_deg_per_s=1.2,
            max_roll_acceleration_deg_per_s2=0.4,
            settling_time_s=2.0,
        ),
        "power": PowerDef(
            battery_capacity_wh=900,
            initial_battery_wh=540,
            idle_power_w=85,
            imaging_power_w=290,
            slew_power_w=35,
            sunlit_charge_power_w=170,
            imaging_duty_limit_s_per_orbit=900,
        ),
    },
    "sar_wide": {
        "sensor": SensorDef(
            min_edge_off_nadir_deg=16.0,
            max_edge_off_nadir_deg=40.0,
            cross_track_fov_deg=4.8,
            min_strip_duration_s=20,
            max_strip_duration_s=180,
        ),
        "agility": AgilityDef(
            max_roll_rate_deg_per_s=1.8,
            max_roll_acceleration_deg_per_s2=0.7,
            settling_time_s=1.5,
        ),
        "power": PowerDef(
            battery_capacity_wh=1300,
            initial_battery_wh=780,
            idle_power_w=105,
            imaging_power_w=360,
            slew_power_w=45,
            sunlit_charge_power_w=230,
            imaging_duty_limit_s_per_orbit=1200,
        ),
    },
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_yaml(path: Path, payload: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def _isoformat_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _datetime_at(hour_offset: int) -> datetime:
    return datetime(2025, 7, 17, 0, 0, tzinfo=UTC) + timedelta(hours=hour_offset)


def _ring_area_m2(poly: Polygon) -> float:
    lon, lat = poly.exterior.xy
    area_m2, _ = WGS84_GEOD.polygon_area_perimeter(lon, lat)
    return abs(area_m2)


def _angular_distance_deg(region_a: RegionRecord, region_b: RegionRecord) -> float:
    _, _, distance_m = WGS84_GEOD.inv(
        region_a.centroid_lon,
        region_a.centroid_lat,
        region_b.centroid_lon,
        region_b.centroid_lat,
    )
    return math.degrees(distance_m / _EARTH_MEAN_RADIUS_M)


def _region_crs(region: RegionRecord) -> CRS:
    return CRS.from_proj4(
        "+proj=laea +lat_0={lat:.8f} +lon_0={lon:.8f} +datum=WGS84 +units=m +no_defs".format(
            lat=region.centroid_lat,
            lon=region.centroid_lon,
        )
    )


def _load_region_library() -> tuple[RegionRecord, ...]:
    raw = json.loads(_REGION_LIBRARY_PATH.read_text(encoding="utf-8"))
    records: list[RegionRecord] = []
    for feature in raw["features"]:
        region_id = str(feature["properties"]["region_id"])
        weight = float(feature["properties"].get("weight", 1.0))
        polygon = shape(feature["geometry"])
        if not isinstance(polygon, Polygon):
            raise TypeError(f"Region {region_id} is not a Polygon.")
        bounds = polygon.bounds
        if bounds[2] - bounds[0] >= 180.0:
            raise ValueError(f"Region {region_id} appears to cross the antimeridian.")
        area_m2 = _ring_area_m2(polygon)
        centroid = polygon.centroid
        records.append(
            RegionRecord(
                region_id=region_id,
                weight=weight,
                polygon_lonlat=polygon,
                area_m2=area_m2,
                centroid_lon=float(centroid.x),
                centroid_lat=float(centroid.y),
            )
        )
    return tuple(records)


def _weighted_choice(rng: random.Random, values: tuple[int, ...], weights: tuple[int, ...]) -> int:
    return rng.choices(values, weights=weights, k=1)[0]


def _satellite_class_assignments(rng: random.Random, num_satellites: int) -> list[str]:
    if rng.random() < 0.35:
        class_id = rng.choice(tuple(SATELLITE_CLASSES))
        return [class_id] * num_satellites
    wide_fraction = rng.uniform(0.35, 0.55)
    wide_count = round(num_satellites * wide_fraction)
    wide_count = max(2, min(num_satellites - 2, wide_count))
    assignments = ["sar_wide"] * wide_count + ["sar_narrow"] * (num_satellites - wide_count)
    rng.shuffle(assignments)
    return assignments


def _build_satellite_entry(source: dict[str, str], class_id: str) -> dict[str, Any]:
    sat_class = SATELLITE_CLASSES[class_id]
    sat = SatelliteDef(
        satellite_id=source["satellite_id"],
        tle_line1=source["tle_line1"],
        tle_line2=source["tle_line2"],
        tle_epoch=source["tle_epoch"],
        sensor=sat_class["sensor"],
        agility=sat_class["agility"],
        power=sat_class["power"],
    )
    return asdict(sat)


def _region_feature(region: RegionRecord) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "region_id": region.region_id,
            "weight": region.weight,
        },
        "geometry": mapping(region.polygon_lonlat),
    }


def _generate_region_grid(region: RegionRecord) -> RegionCoverageGrid:
    local_crs = _region_crs(region)
    to_local = Transformer.from_crs("EPSG:4326", local_crs, always_xy=True)
    to_lonlat = Transformer.from_crs(local_crs, "EPSG:4326", always_xy=True)
    projected_poly = transform(to_local.transform, region.polygon_lonlat)
    min_x, min_y, max_x, max_y = projected_poly.bounds
    start_x = math.floor(min_x / SAMPLE_SPACING_M) * SAMPLE_SPACING_M
    start_y = math.floor(min_y / SAMPLE_SPACING_M) * SAMPLE_SPACING_M
    end_x = math.ceil(max_x / SAMPLE_SPACING_M) * SAMPLE_SPACING_M
    end_y = math.ceil(max_y / SAMPLE_SPACING_M) * SAMPLE_SPACING_M

    samples: list[GridSample] = []
    sample_counter = 0
    x = start_x
    while x < end_x:
        y = start_y
        while y < end_y:
            cell = box(x, y, x + SAMPLE_SPACING_M, y + SAMPLE_SPACING_M)
            clipped = projected_poly.intersection(cell)
            if not clipped.is_empty and clipped.area > 0.0:
                centroid = clipped.centroid
                lon, lat = to_lonlat.transform(float(centroid.x), float(centroid.y))
                sample_counter += 1
                samples.append(
                    GridSample(
                        sample_id=f"{region.region_id}_s{sample_counter:06d}",
                        longitude_deg=float(lon),
                        latitude_deg=float(lat),
                        weight_m2=float(clipped.area),
                    )
                )
            y += SAMPLE_SPACING_M
        x += SAMPLE_SPACING_M
    total_weight_m2 = sum(sample.weight_m2 for sample in samples)
    return RegionCoverageGrid(
        region_id=region.region_id,
        total_weight_m2=total_weight_m2,
        samples=tuple(samples),
    )


def _coverage_grid_payload(grids: tuple[RegionCoverageGrid, ...]) -> dict[str, Any]:
    return {
        "grid_version": 1,
        "sample_spacing_m": SAMPLE_SPACING_M,
        "regions": [
            {
                "region_id": grid.region_id,
                "total_weight_m2": grid.total_weight_m2,
                "samples": [asdict(sample) for sample in grid.samples],
            }
            for grid in grids
        ],
    }


def _manifest_payload(case_id: str, case_seed: int, horizon_start: str, horizon_end: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "benchmark": "regional_coverage",
        "spec_version": "v1",
        "seed": case_seed,
        "horizon_start": horizon_start,
        "horizon_end": horizon_end,
        "time_step_s": TIME_STEP_S,
        "coverage_sample_step_s": COVERAGE_SAMPLE_STEP_S,
        "earth_model": {
            "shape": "wgs84",
        },
        "grid_parameters": {
            "sample_spacing_m": SAMPLE_SPACING_M,
        },
        "scoring": {
            "primary_metric": "coverage_ratio",
            "revisit_bonus_alpha": 0.0,
            "max_actions_total": MAX_ACTIONS_TOTAL,
        },
    }


def _cleanup_output_dir(output_dir: Path) -> None:
    for path in output_dir.glob("case_*"):
        if path.is_dir():
            shutil.rmtree(path)
    shutil.rmtree(output_dir / "cases", ignore_errors=True)
    for path in (output_dir / "index.json", output_dir / "example_solution.json"):
        if path.exists():
            path.unlink()


def _sample_case(
    *,
    case_id: str,
    case_index: int,
    seed: int,
    dataset_attempt: int,
    region_library: tuple[RegionRecord, ...],
    region_use_counts: Counter[str],
) -> BuiltCase:
    for case_attempt in range(512):
        case_seed = (
            seed
            + dataset_attempt * DATASET_ATTEMPT_STRIDE
            + (case_index + 1) * CASE_ATTEMPT_STRIDE
            + case_attempt
        )
        rng = random.Random(case_seed)
        num_satellites = _weighted_choice(rng, (6, 8, 10, 12), (2, 2, 2, 1))
        num_regions = _weighted_choice(rng, (2, 3, 4), (1, 2, 1))
        chosen_regions = tuple(rng.sample(region_library, num_regions))
        region_ids = [region.region_id for region in chosen_regions]
        if any(region_use_counts[region_id] >= 2 for region_id in region_ids):
            continue
        if any(
            _angular_distance_deg(region_a, region_b) < MIN_REGION_SEPARATION_DEG
            for idx, region_a in enumerate(chosen_regions)
            for region_b in chosen_regions[idx + 1 :]
        ):
            continue
        total_region_area_m2 = sum(region.area_m2 for region in chosen_regions)
        if not (MIN_TOTAL_REGION_AREA_M2 <= total_region_area_m2 <= MAX_TOTAL_REGION_AREA_M2):
            continue
        if any(not (MIN_REGION_AREA_M2 <= region.area_m2 <= MAX_REGION_AREA_M2) for region in chosen_regions):
            continue

        selected_satellites = list(rng.sample(list(CACHED_SATELLITES), num_satellites))
        rng.shuffle(selected_satellites)
        class_assignments = _satellite_class_assignments(rng, num_satellites)
        satellites = tuple(
            _build_satellite_entry(source, class_id)
            for source, class_id in zip(selected_satellites, class_assignments, strict=True)
        )
        class_ids = tuple(sorted(set(class_assignments)))

        grids = tuple(_generate_region_grid(region) for region in chosen_regions)
        sample_count = sum(len(grid.samples) for grid in grids)
        if not (MIN_SAMPLES_PER_CASE <= sample_count <= MAX_SAMPLES_PER_CASE):
            continue

        horizon_start_dt = _datetime_at(case_index * 12)
        horizon_end_dt = horizon_start_dt + timedelta(hours=HORIZON_HOURS)
        return BuiltCase(
            case_id=case_id,
            case_seed=case_seed,
            horizon_start=_isoformat_utc(horizon_start_dt),
            horizon_end=_isoformat_utc(horizon_end_dt),
            satellites=satellites,
            regions_geojson={
                "type": "FeatureCollection",
                "features": [_region_feature(region) for region in chosen_regions],
            },
            coverage_grid=_coverage_grid_payload(grids),
            total_region_area_m2=total_region_area_m2,
            satellite_class_ids=class_ids,
            num_regions=num_regions,
        )
    raise RuntimeError(f"Could not sample a valid {case_id} after repeated attempts.")


def _dataset_constraints(cases: tuple[BuiltCase, ...], region_use_counts: Counter[str]) -> None:
    mixed_cases = sum(1 for case in cases if len(case.satellite_class_ids) == 2)
    single_cases = sum(1 for case in cases if len(case.satellite_class_ids) == 1)
    if mixed_cases < 2:
        raise ValueError("Dataset rejected: expected at least two mixed-class cases.")
    if single_cases < 1:
        raise ValueError("Dataset rejected: expected at least one single-class case.")
    if any(count > 2 for count in region_use_counts.values()):
        raise ValueError("Dataset rejected: a region was used more than twice.")
    all_satellite_ids = {sat["satellite_id"] for case in cases for sat in case.satellites}
    if len(all_satellite_ids) < 8:
        raise ValueError("Dataset rejected: too few unique satellites were used.")
    region_sets = [
        tuple(sorted(feature["properties"]["region_id"] for feature in case.regions_geojson["features"]))
        for case in cases
    ]
    if len(set(region_sets)) != len(region_sets):
        raise ValueError("Dataset rejected: duplicate region set sampled for multiple cases.")


def build_cases(seed: int = CANONICAL_SEED) -> tuple[BuiltCase, ...]:
    region_library = _load_region_library()
    for dataset_attempt in range(512):
        region_use_counts: Counter[str] = Counter()
        cases: list[BuiltCase] = []
        try:
            for case_index in range(NUM_CANONICAL_CASES):
                case_id = f"case_{case_index + 1:04d}"
                built_case = _sample_case(
                    case_id=case_id,
                    case_index=case_index,
                    seed=seed,
                    dataset_attempt=dataset_attempt,
                    region_library=region_library,
                    region_use_counts=region_use_counts,
                )
                cases.append(built_case)
                region_use_counts.update(
                    feature["properties"]["region_id"] for feature in built_case.regions_geojson["features"]
                )
            built_cases = tuple(cases)
            _dataset_constraints(built_cases, region_use_counts)
            return built_cases
        except (RuntimeError, ValueError):
            continue
    raise RuntimeError("Could not sample a valid canonical dataset after repeated attempts.")


def generate_dataset(output_dir: Path, seed: int = CANONICAL_SEED) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    _cleanup_output_dir(output_dir)
    built_cases = build_cases(seed)
    cases_root = output_dir / "cases"

    for built_case in built_cases:
        case_dir = cases_root / built_case.case_id
        _write_json(
            case_dir / "manifest.json",
            _manifest_payload(
                built_case.case_id,
                built_case.case_seed,
                built_case.horizon_start,
                built_case.horizon_end,
            ),
        )
        _write_yaml(case_dir / "satellites.yaml", list(built_case.satellites))
        _write_json(case_dir / "regions.geojson", built_case.regions_geojson)
        _write_json(case_dir / "coverage_grid.json", built_case.coverage_grid)

    _write_json(output_dir / "example_solution.json", {"actions": []})
    index_doc = {
        "benchmark": "regional_coverage",
        "spec_version": "v1",
        "generator_seed": seed,
        "example_smoke_case_id": "case_0001",
        "cases": [
            {
                "case_id": built_case.case_id,
                "path": f"cases/{built_case.case_id}",
                "horizon_hours": HORIZON_HOURS,
                "num_satellites": len(built_case.satellites),
                "num_regions": built_case.num_regions,
                "total_region_area_m2": built_case.total_region_area_m2,
                "satellite_class_ids": list(built_case.satellite_class_ids),
            }
            for built_case in built_cases
        ],
    }
    _write_json(output_dir / "index.json", index_doc)
    return index_doc


__all__ = [
    "CANONICAL_SEED",
    "NUM_CANONICAL_CASES",
    "SAMPLE_SPACING_M",
    "build_cases",
    "generate_dataset",
]
