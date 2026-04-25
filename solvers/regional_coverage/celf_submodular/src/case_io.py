"""Public case-file loading for the regional-coverage CELF solver scaffold."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class Manifest:
    case_id: str
    benchmark: str
    spec_version: str
    seed: int | None
    horizon_start: datetime
    horizon_end: datetime
    time_step_s: int
    coverage_sample_step_s: int
    max_actions_total: int | None

    @property
    def horizon_seconds(self) -> int:
        return int((self.horizon_end - self.horizon_start).total_seconds())


@dataclass(frozen=True, slots=True)
class Sensor:
    min_edge_off_nadir_deg: float
    max_edge_off_nadir_deg: float
    cross_track_fov_deg: float
    min_strip_duration_s: float
    max_strip_duration_s: float


@dataclass(frozen=True, slots=True)
class Agility:
    max_roll_rate_deg_per_s: float
    max_roll_acceleration_deg_per_s2: float
    settling_time_s: float


@dataclass(frozen=True, slots=True)
class Power:
    battery_capacity_wh: float
    initial_battery_wh: float
    idle_power_w: float
    imaging_power_w: float
    slew_power_w: float
    sunlit_charge_power_w: float
    imaging_duty_limit_s_per_orbit: float | None


@dataclass(frozen=True, slots=True)
class Satellite:
    satellite_id: str
    tle_line1: str
    tle_line2: str
    tle_epoch: datetime
    sensor: Sensor
    agility: Agility
    power: Power


@dataclass(frozen=True, slots=True)
class Region:
    region_id: str
    weight: float
    min_required_coverage_ratio: float | None
    polygon_lon_lat: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class CoverageSample:
    index: int
    sample_id: str
    region_id: str
    longitude_deg: float
    latitude_deg: float
    weight_m2: float


@dataclass(frozen=True, slots=True)
class CoverageGrid:
    grid_version: int
    sample_spacing_m: float | None
    samples: tuple[CoverageSample, ...]
    total_weight_by_region_m2: dict[str, float]


@dataclass(frozen=True, slots=True)
class RegionalCoverageCase:
    case_dir: Path
    manifest: Manifest
    satellites: dict[str, Satellite]
    regions: dict[str, Region]
    coverage_grid: CoverageGrid


def parse_iso_z(value: str, *, field: str = "timestamp") -> datetime:
    text = value.strip()
    if not text:
        raise ValueError(f"{field}: empty timestamp")
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field}: invalid ISO 8601 timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field}: timestamp must include Z or an explicit offset")
    return parsed.astimezone(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def _require_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a mapping")
    return value


def _require_sequence(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a sequence")
    return value


def _require_str(row: dict[str, Any], key: str, context: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: {key} must be a non-empty string")
    return value


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def load_manifest(case_dir: Path) -> Manifest:
    path = case_dir / "manifest.json"
    raw = _require_mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    scoring = _require_mapping(raw.get("scoring", {}), f"{path}.scoring")
    return Manifest(
        case_id=_require_str(raw, "case_id", str(path)),
        benchmark=_require_str(raw, "benchmark", str(path)),
        spec_version=_require_str(raw, "spec_version", str(path)),
        seed=int(raw["seed"]) if raw.get("seed") is not None else None,
        horizon_start=parse_iso_z(_require_str(raw, "horizon_start", str(path)), field="manifest.horizon_start"),
        horizon_end=parse_iso_z(_require_str(raw, "horizon_end", str(path)), field="manifest.horizon_end"),
        time_step_s=int(raw["time_step_s"]),
        coverage_sample_step_s=int(raw["coverage_sample_step_s"]),
        max_actions_total=(
            int(scoring["max_actions_total"]) if scoring.get("max_actions_total") is not None else None
        ),
    )


def load_satellites(case_dir: Path) -> dict[str, Satellite]:
    path = case_dir / "satellites.yaml"
    rows = _require_sequence(yaml.safe_load(path.read_text(encoding="utf-8")), str(path))
    satellites: dict[str, Satellite] = {}
    for index, value in enumerate(rows):
        context = f"{path}[{index}]"
        row = _require_mapping(value, context)
        sensor = _require_mapping(row.get("sensor"), f"{context}.sensor")
        agility = _require_mapping(row.get("agility"), f"{context}.agility")
        power = _require_mapping(row.get("power"), f"{context}.power")
        satellite_id = _require_str(row, "satellite_id", context)
        if satellite_id in satellites:
            raise ValueError(f"{context}: duplicate satellite_id {satellite_id!r}")
        satellites[satellite_id] = Satellite(
            satellite_id=satellite_id,
            tle_line1=_require_str(row, "tle_line1", context),
            tle_line2=_require_str(row, "tle_line2", context),
            tle_epoch=parse_iso_z(_require_str(row, "tle_epoch", context), field=f"{context}.tle_epoch"),
            sensor=Sensor(
                min_edge_off_nadir_deg=float(sensor["min_edge_off_nadir_deg"]),
                max_edge_off_nadir_deg=float(sensor["max_edge_off_nadir_deg"]),
                cross_track_fov_deg=float(sensor["cross_track_fov_deg"]),
                min_strip_duration_s=float(sensor["min_strip_duration_s"]),
                max_strip_duration_s=float(sensor["max_strip_duration_s"]),
            ),
            agility=Agility(
                max_roll_rate_deg_per_s=float(agility["max_roll_rate_deg_per_s"]),
                max_roll_acceleration_deg_per_s2=float(agility["max_roll_acceleration_deg_per_s2"]),
                settling_time_s=float(agility["settling_time_s"]),
            ),
            power=Power(
                battery_capacity_wh=float(power["battery_capacity_wh"]),
                initial_battery_wh=float(power["initial_battery_wh"]),
                idle_power_w=float(power["idle_power_w"]),
                imaging_power_w=float(power["imaging_power_w"]),
                slew_power_w=float(power["slew_power_w"]),
                sunlit_charge_power_w=float(power["sunlit_charge_power_w"]),
                imaging_duty_limit_s_per_orbit=_float_or_none(
                    power.get("imaging_duty_limit_s_per_orbit")
                ),
            ),
        )
    return satellites


def load_regions(case_dir: Path) -> dict[str, Region]:
    path = case_dir / "regions.geojson"
    raw = _require_mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    features = _require_sequence(raw.get("features"), f"{path}.features")
    regions: dict[str, Region] = {}
    for index, feature_value in enumerate(features):
        context = f"{path}.features[{index}]"
        feature = _require_mapping(feature_value, context)
        properties = _require_mapping(feature.get("properties"), f"{context}.properties")
        geometry = _require_mapping(feature.get("geometry"), f"{context}.geometry")
        coordinates = _require_sequence(geometry.get("coordinates"), f"{context}.geometry.coordinates")
        if geometry.get("type") != "Polygon" or not coordinates:
            raise ValueError(f"{context}: only Polygon geometry with one outer ring is supported")
        ring = _require_sequence(coordinates[0], f"{context}.geometry.coordinates[0]")
        region_id = _require_str(properties, "region_id", f"{context}.properties")
        if region_id in regions:
            raise ValueError(f"{context}: duplicate region_id {region_id!r}")
        regions[region_id] = Region(
            region_id=region_id,
            weight=float(properties.get("weight", 1.0)),
            min_required_coverage_ratio=_float_or_none(
                properties.get("min_required_coverage_ratio")
            ),
            polygon_lon_lat=tuple((float(point[0]), float(point[1])) for point in ring),
        )
    return regions


def load_coverage_grid(case_dir: Path) -> CoverageGrid:
    path = case_dir / "coverage_grid.json"
    raw = _require_mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    samples: list[CoverageSample] = []
    total_weight_by_region: dict[str, float] = {}
    regions = _require_sequence(raw.get("regions"), f"{path}.regions")
    for region_value in regions:
        region = _require_mapping(region_value, f"{path}.regions[]")
        region_id = _require_str(region, "region_id", f"{path}.regions[]")
        region_samples = _require_sequence(region.get("samples"), f"{path}.{region_id}.samples")
        total = 0.0
        for sample_value in region_samples:
            sample = _require_mapping(sample_value, f"{path}.{region_id}.samples[]")
            weight = float(sample["weight_m2"])
            total += weight
            samples.append(
                CoverageSample(
                    index=len(samples),
                    sample_id=_require_str(sample, "sample_id", f"{path}.{region_id}.samples[]"),
                    region_id=region_id,
                    longitude_deg=float(sample["longitude_deg"]),
                    latitude_deg=float(sample["latitude_deg"]),
                    weight_m2=weight,
                )
            )
        total_weight_by_region[region_id] = float(region.get("total_weight_m2", total))
    return CoverageGrid(
        grid_version=int(raw["grid_version"]),
        sample_spacing_m=(
            float(raw["sample_spacing_m"]) if raw.get("sample_spacing_m") is not None else None
        ),
        samples=tuple(samples),
        total_weight_by_region_m2=total_weight_by_region,
    )


def load_case(case_dir: Path) -> RegionalCoverageCase:
    case_dir = case_dir.resolve()
    manifest = load_manifest(case_dir)
    if manifest.horizon_end <= manifest.horizon_start:
        raise ValueError("manifest horizon_end must be after horizon_start")
    return RegionalCoverageCase(
        case_dir=case_dir,
        manifest=manifest,
        satellites=load_satellites(case_dir),
        regions=load_regions(case_dir),
        coverage_grid=load_coverage_grid(case_dir),
    )
