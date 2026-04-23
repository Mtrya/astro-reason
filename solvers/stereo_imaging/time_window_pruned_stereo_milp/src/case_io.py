"""Public case file parsing without benchmark imports."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from models import (
    Mission,
    QualityModel,
    Satellite,
    Target,
    ValidityThresholds,
)


def _parse_iso_strict(value: str) -> datetime:
    """Reject naive timestamps; require explicit offset or Z."""
    # yaml may have parsed it already
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"naive timestamp rejected: {value!r}")
    return dt.astimezone(UTC)


def load_case(case_dir: Path) -> tuple[Mission, dict[str, Satellite], dict[str, Target]]:
    sat_path = case_dir / "satellites.yaml"
    tgt_path = case_dir / "targets.yaml"
    mis_path = case_dir / "mission.yaml"

    if not sat_path.exists():
        raise FileNotFoundError(f"satellites.yaml not found in {case_dir}")
    if not tgt_path.exists():
        raise FileNotFoundError(f"targets.yaml not found in {case_dir}")
    if not mis_path.exists():
        raise FileNotFoundError(f"mission.yaml not found in {case_dir}")

    with sat_path.open("r", encoding="utf-8") as fh:
        sat_raw = yaml.safe_load(fh)
    with tgt_path.open("r", encoding="utf-8") as fh:
        tgt_raw = yaml.safe_load(fh)
    with mis_path.open("r", encoding="utf-8") as fh:
        mis_raw = yaml.safe_load(fh)

    satellites: dict[str, Satellite] = {}
    for entry in sat_raw or []:
        sid = str(entry["id"])
        satellites[sid] = Satellite(
            id=sid,
            norad_catalog_id=int(entry["norad_catalog_id"]),
            tle_line1=str(entry["tle_line1"]),
            tle_line2=str(entry["tle_line2"]),
            pixel_ifov_deg=float(entry["pixel_ifov_deg"]),
            cross_track_pixels=int(entry["cross_track_pixels"]),
            max_off_nadir_deg=float(entry["max_off_nadir_deg"]),
            max_slew_velocity_deg_per_s=float(entry["max_slew_velocity_deg_per_s"]),
            max_slew_acceleration_deg_per_s2=float(entry["max_slew_acceleration_deg_per_s2"]),
            settling_time_s=float(entry["settling_time_s"]),
            min_obs_duration_s=float(entry["min_obs_duration_s"]),
            max_obs_duration_s=float(entry["max_obs_duration_s"]),
        )

    targets: dict[str, Target] = {}
    for entry in tgt_raw or []:
        tid = str(entry["id"])
        targets[tid] = Target(
            id=tid,
            latitude_deg=float(entry["latitude_deg"]),
            longitude_deg=float(entry["longitude_deg"]),
            aoi_radius_m=float(entry["aoi_radius_m"]),
            elevation_ref_m=float(entry["elevation_ref_m"]),
            scene_type=str(entry["scene_type"]),
        )

    m = mis_raw["mission"]
    mission = Mission(
        horizon_start=_parse_iso_strict(m["horizon_start"]),
        horizon_end=_parse_iso_strict(m["horizon_end"]),
        allow_cross_satellite_stereo=bool(m.get("allow_cross_satellite_stereo", False)),
        allow_cross_date_stereo=bool(m.get("allow_cross_date_stereo", False)),
        validity_thresholds=ValidityThresholds.from_mapping(m["validity_thresholds"]),
        quality_model=QualityModel.from_mapping(m["quality_model"]),
    )

    return mission, satellites, targets


def load_solver_config(config_dir: Path | None) -> dict[str, Any]:
    """Read optional solver config from a directory."""
    if config_dir is None:
        return {}
    candidates = [
        "config.yaml",
        "config.yml",
        "config.json",
        "time_window_pruned_stereo_milp.yaml",
        "time_window_pruned_stereo_milp.yml",
        "time_window_pruned_stereo_milp.json",
    ]
    for name in candidates:
        p = config_dir / name
        if p.exists():
            if p.suffix == ".json":
                import json
                with p.open("r", encoding="utf-8") as fh:
                    return dict(json.load(fh))
            with p.open("r", encoding="utf-8") as fh:
                return dict(yaml.safe_load(fh) or {})
    return {}
