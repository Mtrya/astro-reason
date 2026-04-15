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


SUPPORTED_CELESTRAK_SNAPSHOT_EPOCH_UTC = "2025-07-17T00:00:00Z"
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


def _validate_path_segment(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "/" in value or "\\" in value:
        raise ValueError(f"{label} must be a non-empty single path segment")
    return value


def _require_mapping(mapping: object, label: str) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        raise ValueError(f"{label} must be a mapping")
    return mapping


def _require_sequence(values: object, label: str) -> list[Any]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{label} must be a non-empty list")
    return values


def _require_int(mapping: dict[str, Any], key: str, label: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label}.{key} must be an integer")
    return value


def _require_float(mapping: dict[str, Any], key: str, label: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label}.{key} must be numeric")
    return float(value)


def _require_bool(mapping: dict[str, Any], key: str, label: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{label}.{key} must be a boolean")
    return value


def _parse_iso8601_utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty ISO 8601 string")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _load_weighted_options(mapping: object, label: str) -> tuple[tuple[Any, ...], tuple[int, ...]]:
    payload = _require_mapping(mapping, label)
    values = _require_sequence(payload.get("values"), f"{label}.values")
    weights = _require_sequence(payload.get("weights"), f"{label}.weights")
    if len(values) != len(weights):
        raise ValueError(f"{label}.values and {label}.weights must have the same length")
    normalized_weights: list[int] = []
    for weight in weights:
        if not isinstance(weight, int) or isinstance(weight, bool) or weight <= 0:
            raise ValueError(f"{label}.weights entries must be positive integers")
        normalized_weights.append(weight)
    return tuple(values), tuple(normalized_weights)


def load_generator_config(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"missing required splits config: {path}") from exc
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"failed to load splits config {path}: {exc}") from exc

    config = _require_mapping(payload, "splits config")
    source = _require_mapping(config.get("source"), "source")
    celestrak = _require_mapping(source.get("celestrak"), "source.celestrak")
    snapshot_epoch_utc = str(celestrak.get("snapshot_epoch_utc"))
    if snapshot_epoch_utc != SUPPORTED_CELESTRAK_SNAPSHOT_EPOCH_UTC:
        raise ValueError(
            "regional_coverage only supports the cached CelesTrak snapshot epoch "
            f"{SUPPORTED_CELESTRAK_SNAPSHOT_EPOCH_UTC}; got {snapshot_epoch_utc!r}"
        )

    splits = _require_mapping(config.get("splits"), "splits")
    if not splits:
        raise ValueError("splits config must contain a non-empty top-level 'splits' mapping")
    for split_name, split_config in splits.items():
        _validate_path_segment(split_name, "split name")
        split_payload = _require_mapping(split_config, f"splits.{split_name}")
        case_count = _require_int(split_payload, "case_count", f"splits.{split_name}")
        if case_count <= 0:
            raise ValueError(f"splits.{split_name}.case_count must be positive")
        _require_int(split_payload, "seed", f"splits.{split_name}")

    smoke_case = config.get("example_smoke_case")
    if not isinstance(smoke_case, str) or not smoke_case:
        raise ValueError("splits config must include example_smoke_case")
    parts = smoke_case.split("/")
    if len(parts) != 2:
        raise ValueError("example_smoke_case must be formatted as <split>/<case_id>")
    smoke_split = _validate_path_segment(parts[0], "example_smoke_case split")
    smoke_case_id = _validate_path_segment(parts[1], "example_smoke_case case_id")
    smoke_split_config = _require_mapping(splits.get(smoke_split), f"splits.{smoke_split}")
    case_count = _require_int(smoke_split_config, "case_count", f"splits.{smoke_split}")
    try:
        smoke_case_number = int(smoke_case_id.removeprefix("case_"))
    except ValueError as exc:
        raise ValueError("example_smoke_case case_id must look like case_0001") from exc
    if smoke_case_number < 1 or smoke_case_number > case_count:
        raise ValueError(
            f"example_smoke_case {smoke_case} is outside the configured case_count"
        )
    return config


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


def _datetime_at(base_start: datetime, hour_offset: int) -> datetime:
    return base_start + timedelta(hours=hour_offset)


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


def _weighted_choice(rng: random.Random, values: tuple[Any, ...], weights: tuple[int, ...]) -> Any:
    return rng.choices(values, weights=weights, k=1)[0]


def _satellite_class_assignments(
    rng: random.Random,
    num_satellites: int,
    assignment_config: dict[str, Any],
    class_ids: tuple[str, ...],
) -> list[str]:
    if rng.random() < _require_float(assignment_config, "single_class_probability", "satellites.assignment"):
        class_id = rng.choice(class_ids)
        return [class_id] * num_satellites
    wide_fraction_range = _require_mapping(
        assignment_config.get("wide_fraction"),
        "satellites.assignment.wide_fraction",
    )
    wide_fraction = rng.uniform(
        _require_float(wide_fraction_range, "min", "satellites.assignment.wide_fraction"),
        _require_float(wide_fraction_range, "max", "satellites.assignment.wide_fraction"),
    )
    min_per_class = _require_int(assignment_config, "min_per_class", "satellites.assignment")
    wide_count = round(num_satellites * wide_fraction)
    wide_count = max(min_per_class, min(num_satellites - min_per_class, wide_count))
    assignments = ["sar_wide"] * wide_count + ["sar_narrow"] * (num_satellites - wide_count)
    rng.shuffle(assignments)
    return assignments


def _build_satellite_entry(
    source: dict[str, str],
    class_id: str,
    satellite_classes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    sat_class = _require_mapping(satellite_classes[class_id], f"satellites.classes.{class_id}")
    sat = SatelliteDef(
        satellite_id=source["satellite_id"],
        tle_line1=source["tle_line1"],
        tle_line2=source["tle_line2"],
        tle_epoch=source["tle_epoch"],
        sensor=SensorDef(**_require_mapping(sat_class.get("sensor"), f"satellites.classes.{class_id}.sensor")),
        agility=AgilityDef(**_require_mapping(sat_class.get("agility"), f"satellites.classes.{class_id}.agility")),
        power=PowerDef(**_require_mapping(sat_class.get("power"), f"satellites.classes.{class_id}.power")),
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


def _generate_region_grid(region: RegionRecord, sample_spacing_m: float) -> RegionCoverageGrid:
    local_crs = _region_crs(region)
    to_local = Transformer.from_crs("EPSG:4326", local_crs, always_xy=True)
    to_lonlat = Transformer.from_crs(local_crs, "EPSG:4326", always_xy=True)
    projected_poly = transform(to_local.transform, region.polygon_lonlat)
    min_x, min_y, max_x, max_y = projected_poly.bounds
    start_x = math.floor(min_x / sample_spacing_m) * sample_spacing_m
    start_y = math.floor(min_y / sample_spacing_m) * sample_spacing_m
    end_x = math.ceil(max_x / sample_spacing_m) * sample_spacing_m
    end_y = math.ceil(max_y / sample_spacing_m) * sample_spacing_m

    samples: list[GridSample] = []
    sample_counter = 0
    x = start_x
    while x < end_x:
        y = start_y
        while y < end_y:
            cell = box(x, y, x + sample_spacing_m, y + sample_spacing_m)
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
            y += sample_spacing_m
        x += sample_spacing_m
    total_weight_m2 = sum(sample.weight_m2 for sample in samples)
    return RegionCoverageGrid(
        region_id=region.region_id,
        total_weight_m2=total_weight_m2,
        samples=tuple(samples),
    )


def _coverage_grid_payload(grids: tuple[RegionCoverageGrid, ...], sample_spacing_m: float) -> dict[str, Any]:
    return {
        "grid_version": 1,
        "sample_spacing_m": sample_spacing_m,
        "regions": [
            {
                "region_id": grid.region_id,
                "total_weight_m2": grid.total_weight_m2,
                "samples": [asdict(sample) for sample in grid.samples],
            }
            for grid in grids
        ],
    }


def _manifest_payload(
    case_id: str,
    case_seed: int,
    horizon_start: str,
    horizon_end: str,
    *,
    schedule_config: dict[str, Any],
    grid_config: dict[str, Any],
    scoring_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "benchmark": "regional_coverage",
        "spec_version": "v1",
        "seed": case_seed,
        "horizon_start": horizon_start,
        "horizon_end": horizon_end,
        "time_step_s": _require_int(schedule_config, "time_step_s", "schedule"),
        "coverage_sample_step_s": _require_int(
            schedule_config,
            "coverage_sample_step_s",
            "schedule",
        ),
        "earth_model": {
            "shape": "wgs84",
        },
        "grid_parameters": {
            "sample_spacing_m": _require_float(grid_config, "sample_spacing_m", "grid"),
        },
        "scoring": {
            "primary_metric": "coverage_ratio",
            "revisit_bonus_alpha": _require_float(
                scoring_config,
                "revisit_bonus_alpha",
                "scoring",
            ),
            "max_actions_total": _require_int(
                scoring_config,
                "max_actions_total",
                "scoring",
            ),
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
    split_name: str,
    case_id: str,
    case_index: int,
    split_config: dict[str, Any],
    dataset_attempt: int,
    region_library: tuple[RegionRecord, ...],
    region_use_counts: Counter[str],
) -> BuiltCase:
    regions_config = _require_mapping(split_config.get("regions"), f"splits.{split_name}.regions")
    satellites_config = _require_mapping(split_config.get("satellites"), f"splits.{split_name}.satellites")
    schedule_config = _require_mapping(split_config.get("schedule"), f"splits.{split_name}.schedule")
    grid_config = _require_mapping(split_config.get("grid"), f"splits.{split_name}.grid")
    seed = _require_int(split_config, "seed", f"splits.{split_name}")
    dataset_attempt_stride = _require_int(
        split_config,
        "dataset_attempt_stride",
        f"splits.{split_name}",
    )
    case_attempt_stride = _require_int(
        split_config,
        "case_attempt_stride",
        f"splits.{split_name}",
    )
    satellite_classes = _require_mapping(
        satellites_config.get("classes"),
        f"splits.{split_name}.satellites.classes",
    )
    assignment_config = _require_mapping(
        satellites_config.get("assignment"),
        f"splits.{split_name}.satellites.assignment",
    )
    num_satellite_values, num_satellite_weights = _load_weighted_options(
        satellites_config.get("count"),
        "satellites.count",
    )
    num_region_values, num_region_weights = _load_weighted_options(
        regions_config.get("count"),
        "regions.count",
    )
    max_region_reuse = _require_int(regions_config, "max_region_reuse", "regions")
    min_region_separation_deg = _require_float(regions_config, "min_separation_deg", "regions")
    total_area_range = _require_mapping(regions_config.get("total_area_m2"), "regions.total_area_m2")
    per_region_area_range = _require_mapping(
        regions_config.get("per_region_area_m2"),
        "regions.per_region_area_m2",
    )
    sample_count_range = _require_mapping(grid_config.get("sample_count"), "grid.sample_count")
    sample_spacing_m = _require_float(grid_config, "sample_spacing_m", "grid")
    base_horizon_start = _parse_iso8601_utc(
        str(schedule_config.get("base_horizon_start")),
        f"splits.{split_name}.schedule.base_horizon_start",
    )
    case_start_spacing_hours = _require_int(
        schedule_config,
        "case_start_spacing_hours",
        f"splits.{split_name}.schedule",
    )
    horizon_hours = _require_int(schedule_config, "horizon_hours", f"splits.{split_name}.schedule")
    for case_attempt in range(512):
        case_seed = (
            seed
            + dataset_attempt * dataset_attempt_stride
            + (case_index + 1) * case_attempt_stride
            + case_attempt
        )
        rng = random.Random(case_seed)
        num_satellites = int(_weighted_choice(rng, num_satellite_values, num_satellite_weights))
        num_regions = int(_weighted_choice(rng, num_region_values, num_region_weights))
        chosen_regions = tuple(rng.sample(region_library, num_regions))
        region_ids = [region.region_id for region in chosen_regions]
        if any(region_use_counts[region_id] >= max_region_reuse for region_id in region_ids):
            continue
        if any(
            _angular_distance_deg(region_a, region_b) < min_region_separation_deg
            for idx, region_a in enumerate(chosen_regions)
            for region_b in chosen_regions[idx + 1 :]
        ):
            continue
        total_region_area_m2 = sum(region.area_m2 for region in chosen_regions)
        if not (
            _require_float(total_area_range, "min", "regions.total_area_m2")
            <= total_region_area_m2
            <= _require_float(total_area_range, "max", "regions.total_area_m2")
        ):
            continue
        if any(
            not (
                _require_float(per_region_area_range, "min", "regions.per_region_area_m2")
                <= region.area_m2
                <= _require_float(per_region_area_range, "max", "regions.per_region_area_m2")
            )
            for region in chosen_regions
        ):
            continue

        selected_satellites = list(rng.sample(list(CACHED_SATELLITES), num_satellites))
        rng.shuffle(selected_satellites)
        class_assignments = _satellite_class_assignments(
            rng,
            num_satellites,
            assignment_config,
            tuple(sorted(satellite_classes)),
        )
        satellites = tuple(
            _build_satellite_entry(source, class_id, satellite_classes)
            for source, class_id in zip(selected_satellites, class_assignments, strict=True)
        )
        class_ids = tuple(sorted(set(class_assignments)))

        grids = tuple(_generate_region_grid(region, sample_spacing_m) for region in chosen_regions)
        sample_count = sum(len(grid.samples) for grid in grids)
        if not (
            _require_int(sample_count_range, "min", "grid.sample_count")
            <= sample_count
            <= _require_int(sample_count_range, "max", "grid.sample_count")
        ):
            continue

        horizon_start_dt = _datetime_at(base_horizon_start, case_index * case_start_spacing_hours)
        horizon_end_dt = horizon_start_dt + timedelta(hours=horizon_hours)
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
            coverage_grid=_coverage_grid_payload(grids, sample_spacing_m),
            total_region_area_m2=total_region_area_m2,
            satellite_class_ids=class_ids,
            num_regions=num_regions,
        )
    raise RuntimeError(f"Could not sample a valid {case_id} after repeated attempts.")


def _dataset_constraints(
    cases: tuple[BuiltCase, ...],
    region_use_counts: Counter[str],
    split_config: dict[str, Any],
) -> None:
    regions_config = _require_mapping(split_config.get("regions"), "regions")
    satellites_config = _require_mapping(split_config.get("satellites"), "satellites")
    mixed_cases = sum(1 for case in cases if len(case.satellite_class_ids) == 2)
    single_cases = sum(1 for case in cases if len(case.satellite_class_ids) == 1)
    if mixed_cases < _require_int(satellites_config, "mixed_case_min", "satellites"):
        raise ValueError("Dataset rejected: expected at least two mixed-class cases.")
    if single_cases < _require_int(satellites_config, "single_class_min", "satellites"):
        raise ValueError("Dataset rejected: expected at least one single-class case.")
    if any(count > _require_int(regions_config, "max_region_reuse", "regions") for count in region_use_counts.values()):
        raise ValueError("Dataset rejected: a region was used more than twice.")
    all_satellite_ids = {sat["satellite_id"] for case in cases for sat in case.satellites}
    if len(all_satellite_ids) < _require_int(satellites_config, "min_unique_satellite_ids", "satellites"):
        raise ValueError("Dataset rejected: too few unique satellites were used.")
    region_sets = [
        tuple(sorted(feature["properties"]["region_id"] for feature in case.regions_geojson["features"]))
        for case in cases
    ]
    if len(set(region_sets)) != len(region_sets):
            raise ValueError("Dataset rejected: duplicate region set sampled for multiple cases.")


def build_cases(split_name: str, split_config: dict[str, Any]) -> tuple[BuiltCase, ...]:
    region_library = _load_region_library()
    case_count = _require_int(split_config, "case_count", f"splits.{split_name}")
    for dataset_attempt in range(512):
        region_use_counts: Counter[str] = Counter()
        cases: list[BuiltCase] = []
        try:
            for case_index in range(case_count):
                case_id = f"case_{case_index + 1:04d}"
                built_case = _sample_case(
                    split_name=split_name,
                    case_id=case_id,
                    case_index=case_index,
                    split_config=split_config,
                    dataset_attempt=dataset_attempt,
                    region_library=region_library,
                    region_use_counts=region_use_counts,
                )
                cases.append(built_case)
                region_use_counts.update(
                    feature["properties"]["region_id"] for feature in built_case.regions_geojson["features"]
                )
            built_cases = tuple(cases)
            _dataset_constraints(built_cases, region_use_counts, split_config)
            return built_cases
        except (RuntimeError, ValueError):
            continue
    raise RuntimeError("Could not sample a valid canonical dataset after repeated attempts.")


def generate_dataset(
    output_dir: Path,
    *,
    split_configs: dict[str, dict[str, Any]],
    example_smoke_case: str,
    source_config: dict[str, Any],
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    _cleanup_output_dir(output_dir)
    cases_root = output_dir / "cases"
    smoke_split, smoke_case_id = example_smoke_case.split("/")
    smoke_found = False
    all_cases: list[tuple[str, BuiltCase]] = []

    for split_name, split_config_obj in split_configs.items():
        split_config = _require_mapping(split_config_obj, f"splits.{split_name}")
        built_cases = build_cases(split_name, split_config)
        for built_case in built_cases:
            all_cases.append((split_name, built_case))
            if split_name == smoke_split and built_case.case_id == smoke_case_id:
                smoke_found = True

    for split_name, built_case in all_cases:
        split_config = _require_mapping(split_configs[split_name], f"splits.{split_name}")
        schedule_config = _require_mapping(split_config.get("schedule"), f"splits.{split_name}.schedule")
        grid_config = _require_mapping(split_config.get("grid"), f"splits.{split_name}.grid")
        scoring_config = _require_mapping(split_config.get("scoring"), f"splits.{split_name}.scoring")
        case_dir = cases_root / split_name / built_case.case_id
        _write_json(
            case_dir / "manifest.json",
            _manifest_payload(
                built_case.case_id,
                built_case.case_seed,
                built_case.horizon_start,
                built_case.horizon_end,
                schedule_config=schedule_config,
                grid_config=grid_config,
                scoring_config=scoring_config,
            ),
        )
        _write_yaml(case_dir / "satellites.yaml", list(built_case.satellites))
        _write_json(case_dir / "regions.geojson", built_case.regions_geojson)
        _write_json(case_dir / "coverage_grid.json", built_case.coverage_grid)

    if not smoke_found:
        raise ValueError(f"example_smoke_case {example_smoke_case} was not generated")

    _write_json(output_dir / "example_solution.json", {"actions": []})
    unique_seeds = {
        _require_int(_require_mapping(split_config, f"splits.{split_name}"), "seed", f"splits.{split_name}")
        for split_name, split_config in split_configs.items()
    }
    index_doc = {
        "benchmark": "regional_coverage",
        "spec_version": "v1",
        "source": source_config,
        "example_smoke_case": example_smoke_case,
        "cases": [
            {
                "split": split_name,
                "case_id": built_case.case_id,
                "path": f"cases/{split_name}/{built_case.case_id}",
                "horizon_hours": _require_int(
                    _require_mapping(split_configs[split_name]["schedule"], f"splits.{split_name}.schedule"),
                    "horizon_hours",
                    "schedule",
                ),
                "num_satellites": len(built_case.satellites),
                "num_regions": built_case.num_regions,
                "total_region_area_m2": built_case.total_region_area_m2,
                "satellite_class_ids": list(built_case.satellite_class_ids),
            }
            for split_name, built_case in all_cases
        ],
    }
    if len(unique_seeds) == 1:
        index_doc["generator_seed"] = next(iter(unique_seeds))
    _write_json(output_dir / "index.json", index_doc)
    return index_doc


__all__ = [
    "build_cases",
    "load_generator_config",
    "generate_dataset",
]
