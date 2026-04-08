"""Standalone verifier for the regional_coverage benchmark."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
import json
import math

import brahe
import numpy as np
import yaml
from shapely.geometry import Point, Polygon
from shapely.prepared import prep


_NUMERICAL_EPS = 1.0e-9
_WGS84_A_M = 6_378_137.0
_WGS84_B_M = 6_356_752.314_245_179
_BRAHE_EOP_INITIALIZED = False


@dataclass(frozen=True)
class Sensor:
    min_edge_off_nadir_deg: float
    max_edge_off_nadir_deg: float
    cross_track_fov_deg: float
    min_strip_duration_s: float
    max_strip_duration_s: float


@dataclass(frozen=True)
class Agility:
    max_roll_rate_deg_per_s: float
    max_roll_acceleration_deg_per_s2: float
    settling_time_s: float


@dataclass(frozen=True)
class Power:
    battery_capacity_wh: float
    initial_battery_wh: float
    idle_power_w: float
    imaging_power_w: float
    slew_power_w: float
    sunlit_charge_power_w: float
    imaging_duty_limit_s_per_orbit: float | None


@dataclass(frozen=True)
class Satellite:
    satellite_id: str
    tle_line1: str
    tle_line2: str
    tle_epoch: str
    sensor: Sensor
    agility: Agility
    power: Power


@dataclass(frozen=True)
class Region:
    region_id: str
    weight: float
    min_required_coverage_ratio: float | None
    polygon_lonlat: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class GridSample:
    sample_id: str
    longitude_deg: float
    latitude_deg: float
    weight_m2: float
    point: Point = field(repr=False)


@dataclass
class RegionGrid:
    region: Region
    total_weight_m2: float
    samples: list[GridSample]
    longitudes_deg: np.ndarray
    latitudes_deg: np.ndarray
    weights_m2: np.ndarray
    coverage_counts: np.ndarray


@dataclass(frozen=True)
class Manifest:
    case_id: str
    benchmark: str
    spec_version: str
    seed: int
    horizon_start: datetime
    horizon_end: datetime
    time_step_s: int
    coverage_sample_step_s: int
    sample_spacing_m: float
    primary_metric: str
    revisit_bonus_alpha: float
    max_actions_total: int | None


@dataclass(frozen=True)
class CaseData:
    case_dir: Path
    manifest: Manifest
    satellites: dict[str, Satellite]
    regions: dict[str, Region]
    region_grids: dict[str, RegionGrid]


@dataclass
class ParsedAction:
    index: int
    satellite_id: str
    start_time: datetime
    duration_s: float
    roll_deg: float
    raw_type: str
    violations: list[str] = field(default_factory=list)
    accepted_for_schedule: bool = False
    accepted_for_geometry: bool = False
    end_time: datetime | None = None
    theta_inner_deg: float | None = None
    theta_outer_deg: float | None = None
    segment_polygons: list[Polygon] = field(default_factory=list)
    covered_sample_ids: list[str] = field(default_factory=list)
    covered_weight_m2_equivalent: float = 0.0
    derived_centerline_lonlat: list[tuple[float, float]] = field(default_factory=list)


@dataclass(frozen=True)
class ManeuverWindow:
    satellite_id: str
    start_time: datetime
    end_time: datetime
    slew_angle_deg: float
    required_gap_s: float


def _ensure_brahe_ready() -> None:
    global _BRAHE_EOP_INITIALIZED
    if _BRAHE_EOP_INITIALIZED:
        return
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    _BRAHE_EOP_INITIALIZED = True


def _parse_iso_utc(value: str, *, field_name: str) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name}: empty timestamp")
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name}: invalid ISO 8601 timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(
            f"{field_name}: timestamp must end with Z or include an explicit timezone offset"
        )
    return parsed.astimezone(UTC)


def _datetime_to_epoch(value: datetime) -> brahe.Epoch:
    value = value.astimezone(UTC)
    second = float(value.second) + (value.microsecond / 1_000_000.0)
    return brahe.Epoch.from_datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        second,
        0.0,
        brahe.TimeSystem.UTC,
    )


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_mapping(payload: Any, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{context} must be a mapping/object")
    return payload


def _require_list(payload: Any, context: str) -> list[Any]:
    if not isinstance(payload, list):
        raise ValueError(f"{context} must be a list/array")
    return payload


def _require_str(payload: dict[str, Any], key: str, context: str) -> str:
    if key not in payload:
        raise ValueError(f"{context}: missing {key}")
    value = payload[key]
    if not isinstance(value, str):
        raise ValueError(f"{context}: {key} must be a string")
    return value


def _require_float(payload: dict[str, Any], key: str, context: str) -> float:
    if key not in payload:
        raise ValueError(f"{context}: missing {key}")
    value = payload[key]
    if not isinstance(value, (int, float)):
        raise ValueError(f"{context}: {key} must be a number")
    return float(value)


def _optional_float(payload: dict[str, Any], key: str, context: str) -> float | None:
    if key not in payload or payload[key] is None:
        return None
    return _require_float(payload, key, context)


def _load_manifest(case_dir: Path) -> Manifest:
    path = case_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing manifest.json in {case_dir}")
    raw = _require_mapping(json.loads(path.read_text(encoding="utf-8")), "manifest.json")
    earth_model = _require_mapping(raw.get("earth_model"), "manifest.json.earth_model")
    grid_parameters = _require_mapping(
        raw.get("grid_parameters"), "manifest.json.grid_parameters"
    )
    scoring = _require_mapping(raw.get("scoring"), "manifest.json.scoring")
    if _require_str(earth_model, "shape", "manifest.json.earth_model").lower() != "wgs84":
        raise ValueError("manifest.json.earth_model.shape must be 'wgs84'")
    return Manifest(
        case_id=_require_str(raw, "case_id", "manifest.json"),
        benchmark=_require_str(raw, "benchmark", "manifest.json"),
        spec_version=_require_str(raw, "spec_version", "manifest.json"),
        seed=int(_require_float(raw, "seed", "manifest.json")),
        horizon_start=_parse_iso_utc(
            _require_str(raw, "horizon_start", "manifest.json"),
            field_name="manifest.json.horizon_start",
        ),
        horizon_end=_parse_iso_utc(
            _require_str(raw, "horizon_end", "manifest.json"),
            field_name="manifest.json.horizon_end",
        ),
        time_step_s=int(_require_float(raw, "time_step_s", "manifest.json")),
        coverage_sample_step_s=int(
            _require_float(raw, "coverage_sample_step_s", "manifest.json")
        ),
        sample_spacing_m=_require_float(
            grid_parameters, "sample_spacing_m", "manifest.json.grid_parameters"
        ),
        primary_metric=_require_str(scoring, "primary_metric", "manifest.json.scoring"),
        revisit_bonus_alpha=_require_float(
            scoring, "revisit_bonus_alpha", "manifest.json.scoring"
        ),
        max_actions_total=(
            int(_require_float(scoring, "max_actions_total", "manifest.json.scoring"))
            if "max_actions_total" in scoring and scoring["max_actions_total"] is not None
            else None
        ),
    )


def _load_satellites(case_dir: Path) -> dict[str, Satellite]:
    path = case_dir / "satellites.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Missing satellites.yaml in {case_dir}")
    rows = _require_list(yaml.safe_load(path.read_text(encoding="utf-8")), "satellites.yaml")
    satellites: dict[str, Satellite] = {}
    for index, row in enumerate(rows):
        context = f"satellites.yaml[{index}]"
        entry = _require_mapping(row, context)
        sensor_raw = _require_mapping(entry.get("sensor"), f"{context}.sensor")
        agility_raw = _require_mapping(entry.get("agility"), f"{context}.agility")
        power_raw = _require_mapping(entry.get("power"), f"{context}.power")
        satellite = Satellite(
            satellite_id=_require_str(entry, "satellite_id", context),
            tle_line1=_require_str(entry, "tle_line1", context),
            tle_line2=_require_str(entry, "tle_line2", context),
            tle_epoch=_require_str(entry, "tle_epoch", context),
            sensor=Sensor(
                min_edge_off_nadir_deg=_require_float(
                    sensor_raw, "min_edge_off_nadir_deg", f"{context}.sensor"
                ),
                max_edge_off_nadir_deg=_require_float(
                    sensor_raw, "max_edge_off_nadir_deg", f"{context}.sensor"
                ),
                cross_track_fov_deg=_require_float(
                    sensor_raw, "cross_track_fov_deg", f"{context}.sensor"
                ),
                min_strip_duration_s=_require_float(
                    sensor_raw, "min_strip_duration_s", f"{context}.sensor"
                ),
                max_strip_duration_s=_require_float(
                    sensor_raw, "max_strip_duration_s", f"{context}.sensor"
                ),
            ),
            agility=Agility(
                max_roll_rate_deg_per_s=_require_float(
                    agility_raw, "max_roll_rate_deg_per_s", f"{context}.agility"
                ),
                max_roll_acceleration_deg_per_s2=_require_float(
                    agility_raw,
                    "max_roll_acceleration_deg_per_s2",
                    f"{context}.agility",
                ),
                settling_time_s=_require_float(
                    agility_raw, "settling_time_s", f"{context}.agility"
                ),
            ),
            power=Power(
                battery_capacity_wh=_require_float(
                    power_raw, "battery_capacity_wh", f"{context}.power"
                ),
                initial_battery_wh=_require_float(
                    power_raw, "initial_battery_wh", f"{context}.power"
                ),
                idle_power_w=_require_float(power_raw, "idle_power_w", f"{context}.power"),
                imaging_power_w=_require_float(
                    power_raw, "imaging_power_w", f"{context}.power"
                ),
                slew_power_w=_require_float(power_raw, "slew_power_w", f"{context}.power"),
                sunlit_charge_power_w=_require_float(
                    power_raw, "sunlit_charge_power_w", f"{context}.power"
                ),
                imaging_duty_limit_s_per_orbit=_optional_float(
                    power_raw, "imaging_duty_limit_s_per_orbit", f"{context}.power"
                ),
            ),
        )
        if satellite.satellite_id in satellites:
            raise ValueError(f"Duplicate satellite_id {satellite.satellite_id!r}")
        satellites[satellite.satellite_id] = satellite
    return satellites


def _load_regions(case_dir: Path) -> dict[str, Region]:
    path = case_dir / "regions.geojson"
    if not path.is_file():
        raise FileNotFoundError(f"Missing regions.geojson in {case_dir}")
    raw = _require_mapping(json.loads(path.read_text(encoding="utf-8")), "regions.geojson")
    if raw.get("type") != "FeatureCollection":
        raise ValueError("regions.geojson must be a GeoJSON FeatureCollection")
    features = _require_list(raw.get("features"), "regions.geojson.features")
    regions: dict[str, Region] = {}
    for index, feature in enumerate(features):
        context = f"regions.geojson.features[{index}]"
        entry = _require_mapping(feature, context)
        geometry = _require_mapping(entry.get("geometry"), f"{context}.geometry")
        properties = _require_mapping(entry.get("properties"), f"{context}.properties")
        if geometry.get("type") != "Polygon":
            raise ValueError(f"{context}.geometry.type must be 'Polygon'")
        coordinates = _require_list(geometry.get("coordinates"), f"{context}.coordinates")
        if not coordinates:
            raise ValueError(f"{context}.geometry.coordinates must not be empty")
        ring = _require_list(coordinates[0], f"{context}.coordinates[0]")
        polygon_lonlat: list[tuple[float, float]] = []
        for point_index, coordinate in enumerate(ring):
            if (
                not isinstance(coordinate, list)
                or len(coordinate) < 2
                or not isinstance(coordinate[0], (int, float))
                or not isinstance(coordinate[1], (int, float))
            ):
                raise ValueError(f"{context}.coordinates[0][{point_index}] must be [lon, lat]")
            polygon_lonlat.append((float(coordinate[0]), float(coordinate[1])))
        region = Region(
            region_id=_require_str(properties, "region_id", f"{context}.properties"),
            weight=float(properties.get("weight", 1.0)),
            min_required_coverage_ratio=_optional_float(
                properties, "min_required_coverage_ratio", f"{context}.properties"
            ),
            polygon_lonlat=tuple(polygon_lonlat),
        )
        if region.region_id in regions:
            raise ValueError(f"Duplicate region_id {region.region_id!r}")
        regions[region.region_id] = region
    return regions


def _load_coverage_grid(case_dir: Path, regions: dict[str, Region]) -> dict[str, RegionGrid]:
    path = case_dir / "coverage_grid.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing coverage_grid.json in {case_dir}")
    raw = _require_mapping(
        json.loads(path.read_text(encoding="utf-8")), "coverage_grid.json"
    )
    if int(raw.get("grid_version", 0)) != 1:
        raise ValueError("coverage_grid.json.grid_version must be 1")
    region_entries = _require_list(raw.get("regions"), "coverage_grid.json.regions")
    region_grids: dict[str, RegionGrid] = {}
    for index, row in enumerate(region_entries):
        context = f"coverage_grid.json.regions[{index}]"
        entry = _require_mapping(row, context)
        region_id = _require_str(entry, "region_id", context)
        if region_id not in regions:
            raise ValueError(f"{context}: unknown region_id {region_id!r}")
        total_weight_m2 = _require_float(entry, "total_weight_m2", context)
        sample_rows = _require_list(entry.get("samples"), f"{context}.samples")
        samples: list[GridSample] = []
        longitudes: list[float] = []
        latitudes: list[float] = []
        weights: list[float] = []
        for sample_index, sample_row in enumerate(sample_rows):
            sample_context = f"{context}.samples[{sample_index}]"
            sample_payload = _require_mapping(sample_row, sample_context)
            sample = GridSample(
                sample_id=_require_str(sample_payload, "sample_id", sample_context),
                longitude_deg=_require_float(
                    sample_payload, "longitude_deg", sample_context
                ),
                latitude_deg=_require_float(sample_payload, "latitude_deg", sample_context),
                weight_m2=_require_float(sample_payload, "weight_m2", sample_context),
                point=Point(
                    _require_float(sample_payload, "longitude_deg", sample_context),
                    _require_float(sample_payload, "latitude_deg", sample_context),
                ),
            )
            samples.append(sample)
            longitudes.append(sample.longitude_deg)
            latitudes.append(sample.latitude_deg)
            weights.append(sample.weight_m2)
        region_grids[region_id] = RegionGrid(
            region=regions[region_id],
            total_weight_m2=total_weight_m2,
            samples=samples,
            longitudes_deg=np.asarray(longitudes, dtype=float),
            latitudes_deg=np.asarray(latitudes, dtype=float),
            weights_m2=np.asarray(weights, dtype=float),
            coverage_counts=np.zeros(len(samples), dtype=np.int32),
        )
    if set(region_grids) != set(regions):
        missing = sorted(set(regions) - set(region_grids))
        extra = sorted(set(region_grids) - set(regions))
        raise ValueError(
            "coverage_grid.json region mismatch: "
            f"missing={missing or '[]'} extra={extra or '[]'}"
        )
    return region_grids


def load_case(case_dir: str | Path) -> CaseData:
    path = Path(case_dir)
    manifest = _load_manifest(path)
    satellites = _load_satellites(path)
    regions = _load_regions(path)
    region_grids = _load_coverage_grid(path, regions)
    return CaseData(
        case_dir=path,
        manifest=manifest,
        satellites=satellites,
        regions=regions,
        region_grids=region_grids,
    )


def _load_solution_actions(solution_path: str | Path) -> list[dict[str, Any]]:
    path = Path(solution_path)
    raw = _require_mapping(
        json.loads(path.read_text(encoding="utf-8")), f"{path.name}"
    )
    actions = _require_list(raw.get("actions"), f"{path.name}.actions")
    payloads: list[dict[str, Any]] = []
    for index, row in enumerate(actions):
        payloads.append(_require_mapping(row, f"{path.name}.actions[{index}]"))
    return payloads


def _is_aligned(seconds: float, step_s: float) -> bool:
    if step_s <= 0.0:
        return False
    quotient = seconds / step_s
    return abs(quotient - round(quotient)) <= 1.0e-6


def _angle_between_deg(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    norm_a = float(np.linalg.norm(vector_a))
    norm_b = float(np.linalg.norm(vector_b))
    if norm_a <= _NUMERICAL_EPS or norm_b <= _NUMERICAL_EPS:
        return 0.0
    cosine = float(np.dot(vector_a, vector_b) / (norm_a * norm_b))
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _satellite_local_axes(
    sat_pos_m: np.ndarray, sat_vel_mps: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nadir = -sat_pos_m / np.linalg.norm(sat_pos_m)
    along = sat_vel_mps - float(np.dot(sat_vel_mps, nadir)) * nadir
    if float(np.linalg.norm(along)) <= _NUMERICAL_EPS:
        fallback = np.array([0.0, 0.0, 1.0])
        if abs(float(np.dot(fallback, nadir))) > 0.9:
            fallback = np.array([0.0, 1.0, 0.0])
        along = fallback - float(np.dot(fallback, nadir)) * nadir
    along = along / np.linalg.norm(along)
    across = np.cross(along, nadir)
    if float(np.linalg.norm(across)) <= _NUMERICAL_EPS:
        across = np.array([1.0, 0.0, 0.0], dtype=float)
    else:
        across = across / np.linalg.norm(across)
    return along, across, nadir


def _boresight_unit_vector(
    sat_pos_m: np.ndarray, sat_vel_mps: np.ndarray, across_track_off_nadir_deg: float
) -> np.ndarray:
    along_hat, across_hat, nadir_hat = _satellite_local_axes(sat_pos_m, sat_vel_mps)
    del along_hat
    vector = nadir_hat + (
        math.tan(math.radians(float(across_track_off_nadir_deg))) * across_hat
    )
    return vector / np.linalg.norm(vector)


def _ray_ellipsoid_intersection_m(
    origin_m: np.ndarray, direction_unit: np.ndarray
) -> float | None:
    ox, oy, oz = (float(origin_m[i]) for i in range(3))
    dx, dy, dz = (float(direction_unit[i]) for i in range(3))
    a2 = _WGS84_A_M * _WGS84_A_M
    b2 = _WGS84_B_M * _WGS84_B_M
    inv_a2 = 1.0 / a2
    inv_b2 = 1.0 / b2
    aa = (dx * dx + dy * dy) * inv_a2 + dz * dz * inv_b2
    bb = 2.0 * ((ox * dx + oy * dy) * inv_a2 + oz * dz * inv_b2)
    cc = (ox * ox + oy * oy) * inv_a2 + oz * oz * inv_b2 - 1.0
    disc = bb * bb - 4.0 * aa * cc
    if disc < 0.0 or abs(aa) < 1.0e-30:
        return None
    sqrt_disc = math.sqrt(disc)
    t1 = (-bb - sqrt_disc) / (2.0 * aa)
    t2 = (-bb + sqrt_disc) / (2.0 * aa)
    candidates = [value for value in (t1, t2) if value > _NUMERICAL_EPS]
    if not candidates:
        return None
    return min(candidates)


def _ground_intercept_ecef_m(
    sat_pos_m: np.ndarray, sat_vel_mps: np.ndarray, roll_deg: float
) -> np.ndarray | None:
    direction = _boresight_unit_vector(sat_pos_m, sat_vel_mps, roll_deg)
    distance = _ray_ellipsoid_intersection_m(sat_pos_m, direction)
    if distance is None:
        return None
    return sat_pos_m + (distance * direction)


def _ecef_to_lonlat_deg(ecef_position_m: np.ndarray) -> tuple[float, float]:
    lon_deg, lat_deg, _ = brahe.position_ecef_to_geodetic(
        ecef_position_m, brahe.AngleFormat.DEGREES
    )
    return float(lon_deg), float(lat_deg)


def _sample_times(start: datetime, end: datetime, step_s: int) -> list[datetime]:
    if end <= start:
        return [start]
    points = [start]
    current = start
    delta = timedelta(seconds=step_s)
    while current + delta < end:
        current = current + delta
        points.append(current)
    if points[-1] != end:
        points.append(end)
    return points


def _is_sunlit(position_eci_m: np.ndarray, epoch: brahe.Epoch) -> bool:
    sun_position = np.asarray(brahe.sun_position(epoch), dtype=float)
    sun_hat = sun_position / np.linalg.norm(sun_position)
    projection = float(np.dot(position_eci_m, sun_hat))
    perpendicular = float(np.linalg.norm(position_eci_m - (projection * sun_hat)))
    return not (projection < 0.0 and perpendicular < brahe.R_EARTH)


def _slew_time_s(delta_angle_deg: float, satellite: Satellite) -> float:
    delta_angle_deg = abs(delta_angle_deg)
    if delta_angle_deg <= _NUMERICAL_EPS:
        return 0.0
    omega = satellite.agility.max_roll_rate_deg_per_s
    alpha = satellite.agility.max_roll_acceleration_deg_per_s2
    if omega <= 0.0 or alpha <= 0.0:
        return math.inf
    d_tri = (omega * omega) / alpha
    if delta_angle_deg <= d_tri:
        return 2.0 * math.sqrt(delta_angle_deg / alpha)
    return (delta_angle_deg / omega) + (omega / alpha)


def _tle_mean_motion_rev_per_day(line2: str) -> float:
    parts = line2.split()
    if len(parts) < 8:
        raise ValueError(f"Invalid TLE line 2: {line2!r}")
    return float(parts[-2])


def _orbit_period_s(satellite: Satellite) -> float:
    mean_motion = _tle_mean_motion_rev_per_day(satellite.tle_line2)
    if mean_motion <= 0.0:
        return math.inf
    return 86_400.0 / mean_motion


def _parse_actions(case: CaseData, solution_path: str | Path) -> tuple[list[ParsedAction], list[str]]:
    violations: list[str] = []
    raw_actions = _load_solution_actions(solution_path)
    parsed_actions: list[ParsedAction] = []

    if (
        case.manifest.max_actions_total is not None
        and len(raw_actions) > case.manifest.max_actions_total
    ):
        violations.append(
            f"solution.actions has {len(raw_actions)} entries but the case allows at most "
            f"{case.manifest.max_actions_total}"
        )

    for index, raw_action in enumerate(raw_actions):
        raw_type = raw_action.get("type")
        if raw_type != "strip_observation":
            continue
        prefix = f"actions[{index}]"
        try:
            satellite_id = _require_str(raw_action, "satellite_id", prefix)
            start_time = _parse_iso_utc(
                _require_str(raw_action, "start_time", prefix),
                field_name=f"{prefix}.start_time",
            )
            duration_s = _require_float(raw_action, "duration_s", prefix)
            roll_deg = _require_float(raw_action, "roll_deg", prefix)
        except ValueError as exc:
            violations.append(str(exc))
            continue

        action = ParsedAction(
            index=index,
            satellite_id=satellite_id,
            start_time=start_time,
            duration_s=duration_s,
            roll_deg=roll_deg,
            raw_type=raw_type,
        )
        action.end_time = action.start_time + timedelta(seconds=action.duration_s)

        satellite = case.satellites.get(action.satellite_id)
        if satellite is None:
            action.violations.append(
                f"{prefix}: unknown satellite_id {action.satellite_id!r}"
            )
        else:
            fov = satellite.sensor.cross_track_fov_deg
            center_abs = abs(action.roll_deg)
            action.theta_inner_deg = center_abs - (0.5 * fov)
            action.theta_outer_deg = center_abs + (0.5 * fov)
            if action.theta_inner_deg < satellite.sensor.min_edge_off_nadir_deg - 1.0e-6:
                action.violations.append(
                    f"{prefix}: theta_inner_deg={action.theta_inner_deg:.6f} below "
                    f"min_edge_off_nadir_deg={satellite.sensor.min_edge_off_nadir_deg:.6f}"
                )
            if action.theta_outer_deg > satellite.sensor.max_edge_off_nadir_deg + 1.0e-6:
                action.violations.append(
                    f"{prefix}: theta_outer_deg={action.theta_outer_deg:.6f} above "
                    f"max_edge_off_nadir_deg={satellite.sensor.max_edge_off_nadir_deg:.6f}"
                )
            if action.duration_s < satellite.sensor.min_strip_duration_s - 1.0e-6:
                action.violations.append(
                    f"{prefix}: duration_s={action.duration_s:.6f} below "
                    f"min_strip_duration_s={satellite.sensor.min_strip_duration_s:.6f}"
                )
            if action.duration_s > satellite.sensor.max_strip_duration_s + 1.0e-6:
                action.violations.append(
                    f"{prefix}: duration_s={action.duration_s:.6f} above "
                    f"max_strip_duration_s={satellite.sensor.max_strip_duration_s:.6f}"
                )

        if action.duration_s <= 0.0:
            action.violations.append(f"{prefix}: duration_s must be positive")
        if action.end_time <= action.start_time:
            action.violations.append(f"{prefix}: end_time must be after start_time")
        if (
            action.start_time < case.manifest.horizon_start
            or action.end_time > case.manifest.horizon_end
        ):
            action.violations.append(
                f"{prefix}: action lies outside the mission horizon "
                f"({_iso_z(action.start_time)} to {_iso_z(action.end_time)})"
            )

        start_offset_s = (
            action.start_time - case.manifest.horizon_start
        ).total_seconds()
        if not _is_aligned(start_offset_s, float(case.manifest.time_step_s)):
            action.violations.append(
                f"{prefix}: start_time must align to the {case.manifest.time_step_s}s time grid"
            )
        if not _is_aligned(action.duration_s, float(case.manifest.time_step_s)):
            action.violations.append(
                f"{prefix}: duration_s must be an integer multiple of "
                f"{case.manifest.time_step_s}s"
            )

        action.accepted_for_schedule = not action.violations
        parsed_actions.append(action)

    for action in parsed_actions:
        violations.extend(action.violations)
    return parsed_actions, violations


def _build_propagators(case: CaseData) -> dict[str, brahe.SGPPropagator]:
    propagators: dict[str, brahe.SGPPropagator] = {}
    step_size = float(case.manifest.coverage_sample_step_s)
    for satellite_id, satellite in case.satellites.items():
        propagators[satellite_id] = brahe.SGPPropagator.from_tle(
            satellite.tle_line1, satellite.tle_line2, step_size
        )
    return propagators


def _segment_polygon_lonlat(
    inner_a: np.ndarray, outer_a: np.ndarray, outer_b: np.ndarray, inner_b: np.ndarray
) -> Polygon:
    lonlat = [
        _ecef_to_lonlat_deg(inner_a),
        _ecef_to_lonlat_deg(outer_a),
        _ecef_to_lonlat_deg(outer_b),
        _ecef_to_lonlat_deg(inner_b),
    ]
    return Polygon(lonlat)


def _derive_action_geometry(
    case: CaseData,
    parsed_actions: list[ParsedAction],
    propagators: dict[str, brahe.SGPPropagator],
    violations: list[str],
) -> None:
    for action in parsed_actions:
        if not action.accepted_for_schedule:
            continue
        prefix = f"actions[{action.index}]"
        satellite = case.satellites[action.satellite_id]
        propagator = propagators[action.satellite_id]
        sample_times = _sample_times(
            action.start_time,
            action.end_time or action.start_time,
            case.manifest.coverage_sample_step_s,
        )
        if len(sample_times) < 2:
            action.violations.append(f"{prefix}: action sampling produced fewer than two time points")
            action.accepted_for_geometry = False
            violations.extend(action.violations[-1:])
            continue

        edge_hits: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        center_lonlat: list[tuple[float, float]] = []
        signed_inner = math.copysign(action.theta_inner_deg or 0.0, action.roll_deg)
        signed_outer = math.copysign(action.theta_outer_deg or 0.0, action.roll_deg)
        for sample_time in sample_times:
            epoch = _datetime_to_epoch(sample_time)
            state_ecef = np.asarray(propagator.state_ecef(epoch), dtype=float).reshape(6)
            sat_pos_m = state_ecef[:3]
            sat_vel_mps = state_ecef[3:]
            center_hit = _ground_intercept_ecef_m(sat_pos_m, sat_vel_mps, action.roll_deg)
            inner_hit = _ground_intercept_ecef_m(sat_pos_m, sat_vel_mps, signed_inner)
            outer_hit = _ground_intercept_ecef_m(sat_pos_m, sat_vel_mps, signed_outer)
            if center_hit is None or inner_hit is None or outer_hit is None:
                action.violations.append(
                    f"{prefix}: strip rays do not intersect Earth at {_iso_z(sample_time)}"
                )
                break
            edge_hits.append((inner_hit, center_hit, outer_hit))
            center_lonlat.append(_ecef_to_lonlat_deg(center_hit))

        if action.violations:
            action.accepted_for_geometry = False
            violations.extend(action.violations[-1:])
            continue

        segment_polygons: list[Polygon] = []
        for (inner_a, _, outer_a), (inner_b, _, outer_b) in zip(edge_hits, edge_hits[1:]):
            polygon = _segment_polygon_lonlat(inner_a, outer_a, outer_b, inner_b)
            if polygon.is_empty or polygon.area <= _NUMERICAL_EPS:
                action.violations.append(
                    f"{prefix}: derived strip segment collapsed to zero area"
                )
                break
            segment_polygons.append(polygon)
        if action.violations:
            action.accepted_for_geometry = False
            violations.extend(action.violations[-1:])
            continue

        action.segment_polygons = segment_polygons
        action.derived_centerline_lonlat = center_lonlat
        action.accepted_for_geometry = True


def _apply_coverage(
    case: CaseData, parsed_actions: list[ParsedAction]
) -> None:
    for action in parsed_actions:
        if not action.accepted_for_geometry:
            continue
        covered_sample_ids: set[str] = set()
        covered_weight = 0.0
        matches_by_region: dict[str, set[int]] = {
            region_id: set() for region_id in case.region_grids
        }
        for segment in action.segment_polygons:
            segment_min_lon, segment_min_lat, segment_max_lon, segment_max_lat = segment.bounds
            prepared = prep(segment)
            for region_grid in case.region_grids.values():
                candidate_mask = (
                    (region_grid.longitudes_deg >= segment_min_lon)
                    & (region_grid.longitudes_deg <= segment_max_lon)
                    & (region_grid.latitudes_deg >= segment_min_lat)
                    & (region_grid.latitudes_deg <= segment_max_lat)
                )
                candidate_indices = np.flatnonzero(candidate_mask)
                for sample_index in candidate_indices:
                    sample = region_grid.samples[int(sample_index)]
                    if not prepared.covers(sample.point):
                        continue
                    matches_by_region[region_grid.region.region_id].add(int(sample_index))
                    if sample.sample_id in covered_sample_ids:
                        continue
                    covered_sample_ids.add(sample.sample_id)
                    covered_weight += sample.weight_m2
        for region_id, matched_indices in matches_by_region.items():
            if not matched_indices:
                continue
            region_grid = case.region_grids[region_id]
            for sample_index in matched_indices:
                region_grid.coverage_counts[sample_index] += 1
        action.covered_sample_ids = sorted(covered_sample_ids)
        action.covered_weight_m2_equivalent = covered_weight


def _check_overlaps_and_slew(
    case: CaseData,
    parsed_actions: list[ParsedAction],
    propagators: dict[str, brahe.SGPPropagator],
    violations: list[str],
) -> tuple[list[ManeuverWindow], float]:
    maneuvers: list[ManeuverWindow] = []
    total_slew_angle_deg = 0.0
    actions_by_satellite: dict[str, list[ParsedAction]] = {}
    for action in parsed_actions:
        if action.accepted_for_schedule:
            actions_by_satellite.setdefault(action.satellite_id, []).append(action)

    for satellite_id, actions in actions_by_satellite.items():
        actions.sort(key=lambda item: (item.start_time, item.end_time or item.start_time))
        satellite = case.satellites[satellite_id]
        propagator = propagators[satellite_id]
        for previous, current in zip(actions, actions[1:]):
            prefix = f"actions[{current.index}]"
            if (current.start_time < (previous.end_time or previous.start_time)):
                violations.append(
                    f"satellite {satellite_id}: overlapping strip observations "
                    f"[{_iso_z(previous.start_time)}, {_iso_z(previous.end_time or previous.start_time)}) "
                    f"and [{_iso_z(current.start_time)}, {_iso_z(current.end_time or current.start_time)})"
                )
                continue
            previous_epoch = _datetime_to_epoch(previous.end_time or previous.start_time)
            current_epoch = _datetime_to_epoch(current.start_time)
            prev_state = np.asarray(propagator.state_ecef(previous_epoch), dtype=float).reshape(6)
            curr_state = np.asarray(propagator.state_ecef(current_epoch), dtype=float).reshape(6)
            prev_boresight = _boresight_unit_vector(
                prev_state[:3], prev_state[3:], previous.roll_deg
            )
            curr_boresight = _boresight_unit_vector(
                curr_state[:3], curr_state[3:], current.roll_deg
            )
            slew_angle_deg = _angle_between_deg(prev_boresight, curr_boresight)
            total_slew_angle_deg += slew_angle_deg
            required_gap_s = _slew_time_s(slew_angle_deg, satellite) + satellite.agility.settling_time_s
            actual_gap_s = (
                current.start_time - (previous.end_time or previous.start_time)
            ).total_seconds()
            if actual_gap_s + 1.0e-6 < required_gap_s:
                violations.append(
                    f"{prefix}: insufficient slew/settle time on satellite {satellite_id} "
                    f"(need {required_gap_s:.3f}s, gap {actual_gap_s:.3f}s, "
                    f"delta {slew_angle_deg:.4f}deg)"
                )
                continue
            maneuvers.append(
                ManeuverWindow(
                    satellite_id=satellite_id,
                    start_time=current.start_time - timedelta(seconds=required_gap_s),
                    end_time=current.start_time,
                    slew_angle_deg=slew_angle_deg,
                    required_gap_s=required_gap_s,
                )
            )
    return maneuvers, total_slew_angle_deg


def _interval_contains(instant: datetime, start: datetime, end: datetime) -> bool:
    return start <= instant < end


def _build_time_mesh(start: datetime, end: datetime, step_s: int) -> list[datetime]:
    points = [start]
    current = start
    step = timedelta(seconds=step_s)
    while current < end:
        current = min(current + step, end)
        points.append(current)
    return points


def _check_imaging_duty_limits(
    case: CaseData, parsed_actions: list[ParsedAction], violations: list[str]
) -> None:
    actions_by_satellite: dict[str, list[ParsedAction]] = {}
    for action in parsed_actions:
        if action.accepted_for_schedule:
            actions_by_satellite.setdefault(action.satellite_id, []).append(action)

    for satellite_id, actions in actions_by_satellite.items():
        satellite = case.satellites[satellite_id]
        limit_s = satellite.power.imaging_duty_limit_s_per_orbit
        if limit_s is None:
            continue
        orbit_period_s = _orbit_period_s(satellite)
        boundaries: list[datetime] = []
        for action in actions:
            boundaries.append(action.start_time)
            boundaries.append(action.end_time or action.start_time)
        for boundary in sorted(set(boundaries)):
            window_start = boundary - timedelta(seconds=orbit_period_s)
            used_s = 0.0
            for action in actions:
                interval_start = max(window_start, action.start_time)
                interval_end = min(boundary, action.end_time or action.start_time)
                if interval_end > interval_start:
                    used_s += (interval_end - interval_start).total_seconds()
            if used_s > limit_s + 1.0e-6:
                violations.append(
                    f"satellite {satellite_id}: imaging duty limit exceeded over one orbit "
                    f"(used {used_s:.3f}s, limit {limit_s:.3f}s)"
                )
                break


def _simulate_power(
    case: CaseData,
    parsed_actions: list[ParsedAction],
    propagators: dict[str, brahe.SGPPropagator],
    maneuvers: list[ManeuverWindow],
    violations: list[str],
) -> tuple[float, float, dict[str, dict[str, float]]]:
    min_battery_wh = math.inf
    total_imaging_energy_wh = 0.0
    summaries: dict[str, dict[str, float]] = {}
    actions_by_satellite: dict[str, list[ParsedAction]] = {}
    maneuvers_by_satellite: dict[str, list[ManeuverWindow]] = {}

    for action in parsed_actions:
        if action.accepted_for_schedule:
            actions_by_satellite.setdefault(action.satellite_id, []).append(action)
    for maneuver in maneuvers:
        maneuvers_by_satellite.setdefault(maneuver.satellite_id, []).append(maneuver)

    for satellite_id, satellite in case.satellites.items():
        propagator = propagators[satellite_id]
        sat_actions = sorted(
            actions_by_satellite.get(satellite_id, []),
            key=lambda item: (item.start_time, item.end_time or item.start_time),
        )
        sat_maneuvers = maneuvers_by_satellite.get(satellite_id, [])
        time_points = set(
            _build_time_mesh(
                case.manifest.horizon_start,
                case.manifest.horizon_end,
                case.manifest.coverage_sample_step_s,
            )
        )
        for action in sat_actions:
            time_points.add(action.start_time)
            time_points.add(action.end_time or action.start_time)
        for maneuver in sat_maneuvers:
            time_points.add(maneuver.start_time)
            time_points.add(maneuver.end_time)

        battery_wh = satellite.power.initial_battery_wh
        sat_min_battery_wh = battery_wh
        imaging_energy_wh = 0.0
        charging_energy_wh = 0.0
        sorted_points = sorted(time_points)
        for start, end in zip(sorted_points, sorted_points[1:]):
            duration_s = (end - start).total_seconds()
            if duration_s <= 0.0:
                continue
            midpoint = start + ((end - start) / 2)
            epoch = _datetime_to_epoch(midpoint)
            state_eci = np.asarray(propagator.state_eci(epoch), dtype=float).reshape(6)
            imaging_active = any(
                _interval_contains(midpoint, action.start_time, action.end_time or action.start_time)
                for action in sat_actions
            )
            slew_active = any(
                _interval_contains(midpoint, maneuver.start_time, maneuver.end_time)
                for maneuver in sat_maneuvers
            )
            charge_power_w = (
                satellite.power.sunlit_charge_power_w
                if _is_sunlit(state_eci[:3], epoch)
                else 0.0
            )
            load_power_w = satellite.power.idle_power_w
            if imaging_active:
                load_power_w += satellite.power.imaging_power_w
                imaging_energy_wh += (satellite.power.imaging_power_w * duration_s) / 3600.0
            if slew_active:
                load_power_w += satellite.power.slew_power_w
            charging_energy_wh += (charge_power_w * duration_s) / 3600.0
            battery_next_wh = battery_wh + ((charge_power_w - load_power_w) * duration_s / 3600.0)
            if battery_next_wh < -_NUMERICAL_EPS:
                violations.append(
                    f"satellite {satellite_id}: battery depletes below zero around {_iso_z(midpoint)}"
                )
                sat_min_battery_wh = min(sat_min_battery_wh, battery_next_wh)
                battery_wh = battery_next_wh
                break
            battery_wh = min(satellite.power.battery_capacity_wh, battery_next_wh)
            sat_min_battery_wh = min(sat_min_battery_wh, battery_wh)

        summaries[satellite_id] = {
            "initial_battery_wh": satellite.power.initial_battery_wh,
            "final_battery_wh": battery_wh,
            "min_battery_wh": sat_min_battery_wh,
            "battery_capacity_wh": satellite.power.battery_capacity_wh,
            "imaging_energy_wh": imaging_energy_wh,
            "charging_energy_wh": charging_energy_wh,
        }
        min_battery_wh = min(min_battery_wh, sat_min_battery_wh)
        total_imaging_energy_wh += imaging_energy_wh

    if math.isinf(min_battery_wh):
        min_battery_wh = 0.0
    return min_battery_wh, total_imaging_energy_wh, summaries


def _compute_metrics(case: CaseData, parsed_actions: list[ParsedAction]) -> dict[str, Any]:
    region_coverages: dict[str, dict[str, float]] = {}
    total_region_weight = 0.0
    weighted_ratio_sum = 0.0
    covered_weight_total = 0.0

    for region_id, region_grid in case.region_grids.items():
        unique_mask = region_grid.coverage_counts >= 1
        covered_weight = float(region_grid.weights_m2[unique_mask].sum())
        total_weight = region_grid.total_weight_m2
        coverage_ratio = 0.0 if total_weight <= 0.0 else covered_weight / total_weight
        region_coverages[region_id] = {
            "covered_weight_m2_equivalent": covered_weight,
            "total_weight_m2": total_weight,
            "coverage_ratio": coverage_ratio,
            "weight": region_grid.region.weight,
        }
        total_region_weight += region_grid.region.weight
        weighted_ratio_sum += region_grid.region.weight * coverage_ratio
        covered_weight_total += covered_weight

    coverage_ratio = (
        0.0 if total_region_weight <= 0.0 else weighted_ratio_sum / total_region_weight
    )
    num_actions = sum(1 for action in parsed_actions if action.raw_type == "strip_observation")
    total_imaging_time_s = sum(
        action.duration_s for action in parsed_actions if action.accepted_for_schedule
    )

    return {
        "coverage_ratio": coverage_ratio,
        "covered_weight_m2_equivalent": covered_weight_total,
        "num_actions": num_actions,
        "total_imaging_time_s": total_imaging_time_s,
        "total_imaging_energy_wh": 0.0,
        "total_slew_angle_deg": 0.0,
        "min_battery_wh": 0.0,
        "region_coverages": region_coverages,
    }


def _apply_region_requirements(
    case: CaseData, metrics: dict[str, Any], violations: list[str]
) -> None:
    for region_id, region_grid in case.region_grids.items():
        required = region_grid.region.min_required_coverage_ratio
        if required is None:
            continue
        actual = float(metrics["region_coverages"][region_id]["coverage_ratio"])
        if actual + 1.0e-9 < required:
            violations.append(
                f"region {region_id}: coverage_ratio={actual:.6f} below "
                f"min_required_coverage_ratio={required:.6f}"
            )


def _build_diagnostics(
    parsed_actions: list[ParsedAction],
    maneuvers: list[ManeuverWindow],
    power_summaries: dict[str, dict[str, float]],
) -> dict[str, Any]:
    actions_payload: list[dict[str, Any]] = []
    for action in parsed_actions:
        actions_payload.append(
            {
                "index": action.index,
                "type": action.raw_type,
                "satellite_id": action.satellite_id,
                "start_time": _iso_z(action.start_time),
                "end_time": _iso_z(action.end_time or action.start_time),
                "duration_s": action.duration_s,
                "roll_deg": action.roll_deg,
                "accepted_for_schedule": action.accepted_for_schedule,
                "accepted_for_geometry": action.accepted_for_geometry,
                "theta_inner_deg": action.theta_inner_deg,
                "theta_outer_deg": action.theta_outer_deg,
                "segment_count": len(action.segment_polygons),
                "covered_sample_count": len(action.covered_sample_ids),
                "covered_weight_m2_equivalent": action.covered_weight_m2_equivalent,
                "centerline_lonlat": action.derived_centerline_lonlat,
                "violations": action.violations,
            }
        )

    maneuver_payload = [
        {
            "satellite_id": maneuver.satellite_id,
            "start_time": _iso_z(maneuver.start_time),
            "end_time": _iso_z(maneuver.end_time),
            "slew_angle_deg": maneuver.slew_angle_deg,
            "required_gap_s": maneuver.required_gap_s,
        }
        for maneuver in maneuvers
    ]

    return {
        "actions": actions_payload,
        "maneuvers": maneuver_payload,
        "power": power_summaries,
    }


def verify_solution(case_dir: str | Path, solution_path: str | Path) -> dict[str, Any]:
    try:
        _ensure_brahe_ready()
        case = load_case(case_dir)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        return {
            "valid": False,
            "metrics": {},
            "violations": [f"Failed to load case: {exc}"],
            "diagnostics": {},
        }

    try:
        parsed_actions, violations = _parse_actions(case, solution_path)
    except (FileNotFoundError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "valid": False,
            "metrics": {},
            "violations": [f"Failed to load solution: {exc}"],
            "diagnostics": {},
        }

    propagators = _build_propagators(case)
    _derive_action_geometry(case, parsed_actions, propagators, violations)
    _apply_coverage(case, parsed_actions)
    maneuvers, total_slew_angle_deg = _check_overlaps_and_slew(
        case, parsed_actions, propagators, violations
    )
    _check_imaging_duty_limits(case, parsed_actions, violations)
    min_battery_wh, total_imaging_energy_wh, power_summaries = _simulate_power(
        case, parsed_actions, propagators, maneuvers, violations
    )

    metrics = _compute_metrics(case, parsed_actions)
    metrics["total_slew_angle_deg"] = total_slew_angle_deg
    metrics["total_imaging_energy_wh"] = total_imaging_energy_wh
    metrics["min_battery_wh"] = min_battery_wh
    _apply_region_requirements(case, metrics, violations)

    diagnostics = _build_diagnostics(parsed_actions, maneuvers, power_summaries)
    return {
        "valid": not violations,
        "metrics": metrics,
        "violations": violations,
        "diagnostics": diagnostics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a regional_coverage solution against one canonical case directory.",
    )
    parser.add_argument(
        "case_dir",
        help="Path to dataset/cases/<case_id> (contains manifest.json, satellites.yaml, regions.geojson, coverage_grid.json)",
    )
    parser.add_argument(
        "solution_path",
        help="Path to a per-case solution JSON object with an 'actions' array",
    )
    args = parser.parse_args(argv)
    report = verify_solution(args.case_dir, args.solution_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
