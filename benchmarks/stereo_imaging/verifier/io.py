"""Load stereo_imaging case files and solution JSON."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .models import Mission, ObservationAction, SatelliteDef, TargetDef

_SCENE_TYPES = frozenset(
    {"urban_structured", "vegetated", "rugged", "open"},
)


def _parse_iso_utc(value: str, *, field: str) -> datetime:
    """Parse an ISO 8601 instant as UTC. Rejects timezone-naive strings so behavior is not host-local."""
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


def load_mission(case_dir: Path) -> Mission:
    path = case_dir / "mission.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Missing mission.yaml in {case_dir}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "mission" not in raw:
        raise ValueError("mission.yaml must contain a top-level 'mission' mapping")
    m = raw["mission"]
    ctx = "mission.yaml mission"
    vt = m["validity_thresholds"]
    qm = m["quality_model"]
    max_pair_sep_s = float(m.get("max_stereo_pair_separation_s", 3600.0))
    if max_pair_sep_s <= 0.0:
        raise ValueError(f"{ctx}.max_stereo_pair_separation_s must be positive")
    return Mission(
        horizon_start=_parse_iso_utc(_require_str(m, "horizon_start", ctx), field=f"{ctx}.horizon_start"),
        horizon_end=_parse_iso_utc(_require_str(m, "horizon_end", ctx), field=f"{ctx}.horizon_end"),
        allow_cross_satellite_stereo=bool(m.get("allow_cross_satellite_stereo", False)),
        max_stereo_pair_separation_s=max_pair_sep_s,
        min_overlap_fraction=_require_float(vt, "min_overlap_fraction", f"{ctx}.validity_thresholds"),
        min_convergence_deg=_require_float(vt, "min_convergence_deg", f"{ctx}.validity_thresholds"),
        max_convergence_deg=_require_float(vt, "max_convergence_deg", f"{ctx}.validity_thresholds"),
        max_pixel_scale_ratio=_require_float(vt, "max_pixel_scale_ratio", f"{ctx}.validity_thresholds"),
        min_solar_elevation_deg=_require_float(vt, "min_solar_elevation_deg", f"{ctx}.validity_thresholds"),
        near_nadir_anchor_max_off_nadir_deg=_require_float(
            vt, "near_nadir_anchor_max_off_nadir_deg", f"{ctx}.validity_thresholds"
        ),
        pair_weights=dict(qm["pair_weights"]),
        tri_stereo_bonus_by_scene=dict(qm["tri_stereo_bonus_by_scene"]),
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


def load_case(case_dir: str | Path) -> tuple[Mission, dict[str, SatelliteDef], dict[str, TargetDef]]:
    p = Path(case_dir)
    return load_mission(p), load_satellites(p), load_targets(p)


def load_solution_actions(solution_path: str | Path, _case_id: str) -> list[ObservationAction]:
    path = Path(solution_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Solution JSON must be an object")
    actions_raw = raw.get("actions")
    if not isinstance(actions_raw, list):
        raise ValueError("Solution must contain an 'actions' array")
    actions: list[ObservationAction] = []
    for i, a in enumerate(actions_raw):
        ctx = f"solution.actions[{i}]"
        if not isinstance(a, dict):
            raise ValueError(f"{ctx} must be an object")
        if a.get("type") != "observation":
            continue
        actions.append(
            ObservationAction(
                satellite_id=_require_str(a, "satellite_id", ctx),
                target_id=_require_str(a, "target_id", ctx),
                start=_parse_iso_utc(_require_str(a, "start_time", ctx), field=f"{ctx}.start_time"),
                end=_parse_iso_utc(_require_str(a, "end_time", ctx), field=f"{ctx}.end_time"),
                off_nadir_along_deg=_require_float(a, "off_nadir_along_deg", ctx),
                off_nadir_across_deg=_require_float(a, "off_nadir_across_deg", ctx),
            )
        )
    return actions
