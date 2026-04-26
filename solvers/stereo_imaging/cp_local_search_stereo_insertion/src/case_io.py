"""Standalone public case-file loading for the stereo_imaging CP/local-search solver."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class Mission:
    horizon_start: datetime
    horizon_end: datetime
    allow_cross_satellite_stereo: bool
    max_stereo_pair_separation_s: float
    min_overlap_fraction: float
    min_convergence_deg: float
    max_convergence_deg: float
    max_pixel_scale_ratio: float
    min_solar_elevation_deg: float
    near_nadir_anchor_max_off_nadir_deg: float
    pair_weights: dict[str, float]
    tri_stereo_bonus_by_scene: dict[str, float]


@dataclass(frozen=True, slots=True)
class SatelliteDef:
    sat_id: str
    norad_catalog_id: int
    tle_line1: str
    tle_line2: str
    pixel_ifov_deg: float
    cross_track_pixels: int
    max_off_nadir_deg: float
    max_slew_velocity_deg_per_s: float
    max_slew_acceleration_deg_per_s2: float
    settling_time_s: float
    min_obs_duration_s: float
    max_obs_duration_s: float

    @property
    def cross_track_fov_deg(self) -> float:
        return float(self.cross_track_pixels) * self.pixel_ifov_deg

    @property
    def half_cross_track_fov_deg(self) -> float:
        return 0.5 * self.cross_track_fov_deg


@dataclass(frozen=True, slots=True)
class TargetDef:
    target_id: str
    latitude_deg: float
    longitude_deg: float
    aoi_radius_m: float
    elevation_ref_m: float
    scene_type: str


@dataclass(frozen=True, slots=True)
class StereoCase:
    case_dir: Path
    mission: Mission
    satellites: dict[str, SatelliteDef]
    targets: dict[str, TargetDef]


_SCENE_TYPES = frozenset(
    {"urban_structured", "vegetated", "rugged", "open"},
)


def _parse_iso_utc(value: str, *, field: str) -> datetime:
    s = value.strip()
    if not s:
        raise ValueError(f"{field}: empty timestamp")
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as e:
        raise ValueError(f"{field}: invalid ISO 8601 timestamp {value!r}") from e
    if dt.tzinfo is None:
        raise ValueError(
            f"{field}: timestamp must end with Z or include an explicit timezone offset "
            f"(naive timestamps are not allowed; got {value!r})"
        )
    return dt.astimezone(UTC)


def _require_float(d: dict[str, Any], key: str, ctx: str) -> float:
    if key not in d:
        raise ValueError(f"{ctx}: missing {key}")
    return float(d[key])


def _require_str(d: dict[str, Any], key: str, ctx: str) -> str:
    if key not in d:
        raise ValueError(f"{ctx}: missing {key}")
    v = d[key]
    if not isinstance(v, str):
        raise ValueError(f"{ctx}: {key} must be a string")
    return v


def _require_dict(d: dict[str, Any], key: str, ctx: str) -> dict[str, Any]:
    if key not in d:
        raise ValueError(f"{ctx}: missing {key}")
    v = d[key]
    if not isinstance(v, dict):
        raise ValueError(f"{ctx}: {key} must be a mapping")
    return v


def _require_bool(d: dict[str, Any], key: str, ctx: str) -> bool:
    if key not in d:
        raise ValueError(f"{ctx}: missing {key}")
    v = d[key]
    if not isinstance(v, bool):
        raise ValueError(f"{ctx}: {key} must be a boolean")
    return v


def load_mission(case_dir: Path) -> Mission:
    path = case_dir / "mission.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Missing mission.yaml in {case_dir}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "mission" not in raw:
        raise ValueError("mission.yaml must contain a top-level 'mission' mapping")
    ctx = "mission.yaml mission"
    m = _require_dict(raw, "mission", "mission.yaml")
    vt = _require_dict(m, "validity_thresholds", ctx)
    qm = _require_dict(m, "quality_model", ctx)
    pair_weights = _require_dict(qm, "pair_weights", f"{ctx}.quality_model")
    tri_stereo_bonus_by_scene = _require_dict(
        qm, "tri_stereo_bonus_by_scene", f"{ctx}.quality_model"
    )
    return Mission(
        horizon_start=_parse_iso_utc(_require_str(m, "horizon_start", ctx), field=f"{ctx}.horizon_start"),
        horizon_end=_parse_iso_utc(_require_str(m, "horizon_end", ctx), field=f"{ctx}.horizon_end"),
        allow_cross_satellite_stereo=_require_bool(m, "allow_cross_satellite_stereo", ctx),
        max_stereo_pair_separation_s=_require_float(m, "max_stereo_pair_separation_s", ctx),
        min_overlap_fraction=_require_float(vt, "min_overlap_fraction", f"{ctx}.validity_thresholds"),
        min_convergence_deg=_require_float(vt, "min_convergence_deg", f"{ctx}.validity_thresholds"),
        max_convergence_deg=_require_float(vt, "max_convergence_deg", f"{ctx}.validity_thresholds"),
        max_pixel_scale_ratio=_require_float(vt, "max_pixel_scale_ratio", f"{ctx}.validity_thresholds"),
        min_solar_elevation_deg=_require_float(vt, "min_solar_elevation_deg", f"{ctx}.validity_thresholds"),
        near_nadir_anchor_max_off_nadir_deg=_require_float(
            vt, "near_nadir_anchor_max_off_nadir_deg", f"{ctx}.validity_thresholds"
        ),
        pair_weights=dict(pair_weights),
        tri_stereo_bonus_by_scene=dict(tri_stereo_bonus_by_scene),
    )


def load_satellites(case_dir: Path) -> dict[str, SatelliteDef]:
    path = case_dir / "satellites.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Missing satellites.yaml in {case_dir}")
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("satellites.yaml must be a YAML sequence")
    out: dict[str, SatelliteDef] = {}
    for i, row in enumerate(rows):
        ctx = f"satellites.yaml[{i}]"
        if not isinstance(row, dict):
            raise ValueError(f"{ctx} must be a mapping")
        sid = _require_str(row, "id", ctx)
        if sid in out:
            raise ValueError(f"{ctx}: duplicate satellite id {sid!r}")
        out[sid] = SatelliteDef(
            sat_id=sid,
            norad_catalog_id=int(row["norad_catalog_id"]),
            tle_line1=_require_str(row, "tle_line1", ctx),
            tle_line2=_require_str(row, "tle_line2", ctx),
            pixel_ifov_deg=_require_float(row, "pixel_ifov_deg", ctx),
            cross_track_pixels=int(row["cross_track_pixels"]),
            max_off_nadir_deg=_require_float(row, "max_off_nadir_deg", ctx),
            max_slew_velocity_deg_per_s=_require_float(row, "max_slew_velocity_deg_per_s", ctx),
            max_slew_acceleration_deg_per_s2=_require_float(row, "max_slew_acceleration_deg_per_s2", ctx),
            settling_time_s=_require_float(row, "settling_time_s", ctx),
            min_obs_duration_s=_require_float(row, "min_obs_duration_s", ctx),
            max_obs_duration_s=_require_float(row, "max_obs_duration_s", ctx),
        )
    return out


def load_targets(case_dir: Path) -> dict[str, TargetDef]:
    path = case_dir / "targets.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Missing targets.yaml in {case_dir}")
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("targets.yaml must be a YAML sequence")
    out: dict[str, TargetDef] = {}
    for i, row in enumerate(rows):
        ctx = f"targets.yaml[{i}]"
        if not isinstance(row, dict):
            raise ValueError(f"{ctx} must be a mapping")
        tid = _require_str(row, "id", ctx)
        if tid in out:
            raise ValueError(f"{ctx}: duplicate target id {tid!r}")
        st = _require_str(row, "scene_type", ctx)
        if st not in _SCENE_TYPES:
            raise ValueError(f"{ctx}: unknown scene_type {st!r}")
        out[tid] = TargetDef(
            target_id=tid,
            latitude_deg=_require_float(row, "latitude_deg", ctx),
            longitude_deg=_require_float(row, "longitude_deg", ctx),
            aoi_radius_m=_require_float(row, "aoi_radius_m", ctx),
            elevation_ref_m=_require_float(row, "elevation_ref_m", ctx),
            scene_type=st,
        )
    return out


def load_case(case_dir: str | Path) -> StereoCase:
    p = Path(case_dir).resolve()
    mission = load_mission(p)
    satellites = load_satellites(p)
    targets = load_targets(p)
    return StereoCase(
        case_dir=p,
        mission=mission,
        satellites=satellites,
        targets=targets,
    )


def load_solver_config(config_dir: str | Path | None) -> dict[str, Any]:
    if not config_dir:
        return {}
    path = Path(config_dir)
    if not path.exists():
        raise FileNotFoundError(f"config path does not exist: {path}")
    if path.is_file():
        candidates = [path]
    else:
        candidates = [
            path / "config.yaml",
            path / "config.yml",
            path / "config.json",
            path / "cp_local_search_stereo_insertion.yaml",
            path / "cp_local_search_stereo_insertion.yml",
            path / "cp_local_search_stereo_insertion.json",
        ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        if candidate.suffix == ".json":
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        else:
            payload = yaml.safe_load(candidate.read_text(encoding="utf-8"))
        if payload is None:
            raise ValueError(f"{candidate} is empty")
        if not isinstance(payload, dict):
            raise ValueError(f"{candidate} must contain a mapping/object")
        return payload
    attempted = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"no supported config file found under {path}; tried: {attempted}")
