"""Public case-file loading for the regional_coverage CP/local-search solver."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


NUMERICAL_EPS = 1e-6


@dataclass(frozen=True, slots=True)
class Mission:
    case_id: str
    horizon_start: datetime
    horizon_end: datetime
    time_step_s: int
    coverage_sample_step_s: int
    max_actions_total: int
    primary_metric: str
    revisit_bonus_alpha: float

    @property
    def horizon_duration_s(self) -> int:
        return int((self.horizon_end - self.horizon_start).total_seconds())


@dataclass(frozen=True, slots=True)
class Sensor:
    min_edge_off_nadir_deg: float
    max_edge_off_nadir_deg: float
    cross_track_fov_deg: float
    min_strip_duration_s: int
    max_strip_duration_s: int

    @property
    def min_center_roll_abs_deg(self) -> float:
        return self.min_edge_off_nadir_deg + 0.5 * self.cross_track_fov_deg

    @property
    def max_center_roll_abs_deg(self) -> float:
        return self.max_edge_off_nadir_deg - 0.5 * self.cross_track_fov_deg


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
    polygon: tuple[tuple[float, float], ...]
    total_weight_m2: float


@dataclass(frozen=True, slots=True)
class CoverageSample:
    sample_id: str
    region_id: str
    longitude_deg: float
    latitude_deg: float
    weight_m2: float


@dataclass(frozen=True, slots=True)
class RegionalCoverageCase:
    case_dir: Path
    mission: Mission
    satellites: dict[str, Satellite]
    regions: dict[str, Region]
    samples: tuple[CoverageSample, ...]
    samples_by_region: dict[str, tuple[CoverageSample, ...]]

    @property
    def total_sample_weight_m2(self) -> float:
        return sum(sample.weight_m2 for sample in self.samples)


@dataclass(frozen=True, slots=True)
class SolverConfig:
    candidate_stride_s: int = 600
    roll_samples_per_side: int = 3
    max_candidates_per_satellite: int = 256
    max_zero_coverage_candidates_per_satellite: int = 8
    include_zero_coverage_candidates: bool = True
    candidate_debug_limit: int = 250

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "SolverConfig":
        payload = payload or {}
        return cls(
            candidate_stride_s=_positive_int(payload.get("candidate_stride_s", 600), "candidate_stride_s"),
            roll_samples_per_side=_positive_int(
                payload.get("roll_samples_per_side", 3), "roll_samples_per_side"
            ),
            max_candidates_per_satellite=_positive_int(
                payload.get("max_candidates_per_satellite", 256),
                "max_candidates_per_satellite",
            ),
            max_zero_coverage_candidates_per_satellite=_non_negative_int(
                payload.get("max_zero_coverage_candidates_per_satellite", 8),
                "max_zero_coverage_candidates_per_satellite",
            ),
            include_zero_coverage_candidates=bool(payload.get("include_zero_coverage_candidates", True)),
            candidate_debug_limit=_non_negative_int(
                payload.get("candidate_debug_limit", 250), "candidate_debug_limit"
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_stride_s": self.candidate_stride_s,
            "roll_samples_per_side": self.roll_samples_per_side,
            "max_candidates_per_satellite": self.max_candidates_per_satellite,
            "max_zero_coverage_candidates_per_satellite": self.max_zero_coverage_candidates_per_satellite,
            "include_zero_coverage_candidates": self.include_zero_coverage_candidates,
            "candidate_debug_limit": self.candidate_debug_limit,
        }


def parse_iso_z(value: str, *, field: str = "timestamp") -> datetime:
    text = value.strip()
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
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def load_case(case_dir: str | Path) -> RegionalCoverageCase:
    root = Path(case_dir).resolve()
    manifest = _load_json(root / "manifest.json")
    satellites = _load_satellites(root / "satellites.yaml")
    regions = _load_regions(root / "regions.geojson")
    samples, samples_by_region, totals = _load_coverage_grid(root / "coverage_grid.json")

    scoring = _require_dict(manifest, "scoring", "manifest.json")
    mission = Mission(
        case_id=_require_str(manifest, "case_id", "manifest.json"),
        horizon_start=parse_iso_z(_require_str(manifest, "horizon_start", "manifest.json"), field="horizon_start"),
        horizon_end=parse_iso_z(_require_str(manifest, "horizon_end", "manifest.json"), field="horizon_end"),
        time_step_s=_positive_int(manifest.get("time_step_s"), "time_step_s"),
        coverage_sample_step_s=_positive_int(
            manifest.get("coverage_sample_step_s"), "coverage_sample_step_s"
        ),
        max_actions_total=_positive_int(scoring.get("max_actions_total"), "scoring.max_actions_total"),
        primary_metric=_require_str(scoring, "primary_metric", "manifest.json.scoring"),
        revisit_bonus_alpha=float(scoring.get("revisit_bonus_alpha", 0.0)),
    )
    if mission.horizon_end <= mission.horizon_start:
        raise ValueError("manifest.json: horizon_end must be after horizon_start")

    merged_regions: dict[str, Region] = {}
    for region_id, region in regions.items():
        merged_regions[region_id] = Region(
            region_id=region.region_id,
            weight=region.weight,
            min_required_coverage_ratio=region.min_required_coverage_ratio,
            polygon=region.polygon,
            total_weight_m2=totals.get(region_id, 0.0),
        )

    return RegionalCoverageCase(
        case_dir=root,
        mission=mission,
        satellites=satellites,
        regions=merged_regions,
        samples=samples,
        samples_by_region=samples_by_region,
    )


def load_solver_config(config_dir: str | Path | None) -> dict[str, Any]:
    if config_dir is None or str(config_dir) == "":
        return {}
    path = Path(config_dir)
    if not path.exists():
        raise FileNotFoundError(f"config path does not exist: {path}")
    if path.is_dir():
        candidates = [path / "config.yaml", path / "config.yml", path / "config.json"]
        found = next((item for item in candidates if item.is_file()), None)
        if found is None:
            return {}
        path = found
    if path.suffix.lower() == ".json":
        data = _load_json(path)
    else:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: config must be a mapping")
    return data


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def _load_satellites(path: Path) -> dict[str, Satellite]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required file: {path}")
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("satellites.yaml must be a YAML sequence")
    out: dict[str, Satellite] = {}
    for idx, row in enumerate(rows):
        ctx = f"satellites.yaml[{idx}]"
        if not isinstance(row, dict):
            raise ValueError(f"{ctx}: expected mapping")
        sid = _require_str(row, "satellite_id", ctx)
        if sid in out:
            raise ValueError(f"{ctx}: duplicate satellite_id {sid!r}")
        sensor = _require_dict(row, "sensor", ctx)
        agility = _require_dict(row, "agility", ctx)
        power = _require_dict(row, "power", ctx)
        sat = Satellite(
            satellite_id=sid,
            tle_line1=_require_str(row, "tle_line1", ctx),
            tle_line2=_require_str(row, "tle_line2", ctx),
            tle_epoch=parse_iso_z(_require_str(row, "tle_epoch", ctx), field=f"{ctx}.tle_epoch"),
            sensor=Sensor(
                min_edge_off_nadir_deg=float(sensor["min_edge_off_nadir_deg"]),
                max_edge_off_nadir_deg=float(sensor["max_edge_off_nadir_deg"]),
                cross_track_fov_deg=float(sensor["cross_track_fov_deg"]),
                min_strip_duration_s=_positive_int(sensor["min_strip_duration_s"], f"{ctx}.sensor.min_strip_duration_s"),
                max_strip_duration_s=_positive_int(sensor["max_strip_duration_s"], f"{ctx}.sensor.max_strip_duration_s"),
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
                imaging_duty_limit_s_per_orbit=(
                    None
                    if power.get("imaging_duty_limit_s_per_orbit") is None
                    else float(power["imaging_duty_limit_s_per_orbit"])
                ),
            ),
        )
        if sat.sensor.min_center_roll_abs_deg > sat.sensor.max_center_roll_abs_deg + NUMERICAL_EPS:
            raise ValueError(f"{ctx}: sensor off-nadir band cannot fit the cross-track FOV")
        out[sid] = sat
    return out


def _load_regions(path: Path) -> dict[str, Region]:
    raw = _load_json(path)
    if raw.get("type") != "FeatureCollection":
        raise ValueError("regions.geojson must be a FeatureCollection")
    features = raw.get("features")
    if not isinstance(features, list):
        raise ValueError("regions.geojson: features must be a sequence")
    out: dict[str, Region] = {}
    for idx, feature in enumerate(features):
        ctx = f"regions.geojson.features[{idx}]"
        if not isinstance(feature, dict):
            raise ValueError(f"{ctx}: expected mapping")
        props = _require_dict(feature, "properties", ctx)
        geom = _require_dict(feature, "geometry", ctx)
        if geom.get("type") != "Polygon":
            raise ValueError(f"{ctx}: only Polygon geometries are supported")
        coords = geom.get("coordinates")
        if not isinstance(coords, list) or not coords or not isinstance(coords[0], list):
            raise ValueError(f"{ctx}: polygon must include an exterior ring")
        region_id = _require_str(props, "region_id", ctx)
        if region_id in out:
            raise ValueError(f"{ctx}: duplicate region_id {region_id!r}")
        ring = tuple((float(lon), float(lat)) for lon, lat in coords[0])
        out[region_id] = Region(
            region_id=region_id,
            weight=float(props.get("weight", 1.0)),
            min_required_coverage_ratio=(
                None
                if props.get("min_required_coverage_ratio") is None
                else float(props["min_required_coverage_ratio"])
            ),
            polygon=ring,
            total_weight_m2=0.0,
        )
    return out


def _load_coverage_grid(
    path: Path,
) -> tuple[tuple[CoverageSample, ...], dict[str, tuple[CoverageSample, ...]], dict[str, float]]:
    raw = _load_json(path)
    regions = raw.get("regions")
    if not isinstance(regions, list):
        raise ValueError("coverage_grid.json: regions must be a sequence")
    samples: list[CoverageSample] = []
    by_region: dict[str, list[CoverageSample]] = {}
    totals: dict[str, float] = {}
    seen: set[str] = set()
    for idx, region in enumerate(regions):
        ctx = f"coverage_grid.json.regions[{idx}]"
        if not isinstance(region, dict):
            raise ValueError(f"{ctx}: expected mapping")
        region_id = _require_str(region, "region_id", ctx)
        totals[region_id] = float(region.get("total_weight_m2", 0.0))
        rows = region.get("samples")
        if not isinstance(rows, list):
            raise ValueError(f"{ctx}: samples must be a sequence")
        by_region.setdefault(region_id, [])
        for sample_idx, row in enumerate(rows):
            sctx = f"{ctx}.samples[{sample_idx}]"
            if not isinstance(row, dict):
                raise ValueError(f"{sctx}: expected mapping")
            sample_id = _require_str(row, "sample_id", sctx)
            if sample_id in seen:
                raise ValueError(f"{sctx}: duplicate sample_id {sample_id!r}")
            seen.add(sample_id)
            sample = CoverageSample(
                sample_id=sample_id,
                region_id=region_id,
                longitude_deg=float(row["longitude_deg"]),
                latitude_deg=float(row["latitude_deg"]),
                weight_m2=float(row["weight_m2"]),
            )
            samples.append(sample)
            by_region[region_id].append(sample)
    return (
        tuple(samples),
        {region_id: tuple(items) for region_id, items in by_region.items()},
        totals,
    )


def _require_str(data: dict[str, Any], key: str, ctx: str) -> str:
    if key not in data:
        raise ValueError(f"{ctx}: missing {key}")
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"{ctx}: {key} must be a string")
    return value


def _require_dict(data: dict[str, Any], key: str, ctx: str) -> dict[str, Any]:
    if key not in data:
        raise ValueError(f"{ctx}: missing {key}")
    value = data[key]
    if not isinstance(value, dict):
        raise ValueError(f"{ctx}: {key} must be a mapping")
    return value


def _positive_int(value: Any, field: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _non_negative_int(value: Any, field: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative")
    return parsed
