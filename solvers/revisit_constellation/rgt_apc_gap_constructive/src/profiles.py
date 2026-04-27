"""Deterministic solver run-profile resolution and sweep summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import copy


PROFILE_METADATA_KEYS = {
    "active_profile",
    "run_profile",
    "profile",
    "profiles",
    "parameter_sweep",
}


@dataclass(frozen=True, slots=True)
class ProfileResolution:
    profile_name: str
    available_profiles: list[str]
    resolved_config: dict[str, Any]
    summary: dict[str, Any]
    sweep_summary: dict[str, Any]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _profile_base_config(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in payload.items()
        if key not in PROFILE_METADATA_KEYS
    }


def _active_profile_name(payload: dict[str, Any]) -> str:
    for key in ("active_profile", "run_profile", "profile"):
        value = payload.get(key)
        if value is not None:
            return str(value)
    return "custom"


def _profile_payloads(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profiles_raw = payload.get("profiles", {})
    if profiles_raw is None:
        return {}
    if not isinstance(profiles_raw, dict):
        raise ValueError("profiles config must be a mapping/object")
    profiles: dict[str, dict[str, Any]] = {}
    for name, profile_payload in sorted(profiles_raw.items(), key=lambda item: str(item[0])):
        if not isinstance(profile_payload, dict):
            raise ValueError(f"profiles.{name} must be a mapping/object")
        profiles[str(name)] = profile_payload
    return profiles


def _sweep_points(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sweep_raw = payload.get("parameter_sweep", {})
    if sweep_raw is None:
        return []
    if not isinstance(sweep_raw, dict):
        raise ValueError("parameter_sweep config must be a mapping/object")
    points_raw = sweep_raw.get("points", [])
    if points_raw is None:
        return []
    if not isinstance(points_raw, list):
        raise ValueError("parameter_sweep.points must be an array")

    points: list[dict[str, Any]] = []
    for index, point in enumerate(points_raw):
        if not isinstance(point, dict):
            raise ValueError(f"parameter_sweep.points[{index}] must be a mapping/object")
        point_name = str(point.get("name", f"point_{index:02d}"))
        profile_name = str(point.get("profile", point_name))
        overrides = point.get("overrides", {})
        if overrides is None:
            overrides = {}
        if not isinstance(overrides, dict):
            raise ValueError(
                f"parameter_sweep.points[{index}].overrides must be a mapping/object"
            )
        points.append(
            {
                "index": index,
                "name": point_name,
                "profile": profile_name,
                "overrides": copy.deepcopy(overrides),
            }
        )
    points.sort(key=lambda item: (str(item["profile"]), str(item["name"]), int(item["index"])))
    return points


def _config_summary(config: dict[str, Any]) -> dict[str, Any]:
    orbit = config.get("orbit_library")
    visibility = config.get("visibility")
    selection = config.get("selection")
    if not isinstance(orbit, dict):
        orbit = {}
    if not isinstance(visibility, dict):
        visibility = {}
    if not isinstance(selection, dict):
        selection = {}
    return {
        "orbit_library": {
            "max_candidates": orbit.get("max_candidates"),
            "search_mode": orbit.get("search_mode"),
            "max_rgt_days": orbit.get("max_rgt_days"),
            "min_revolutions_per_day": orbit.get("min_revolutions_per_day"),
            "max_revolutions_per_day": orbit.get("max_revolutions_per_day"),
            "phase_slot_count": orbit.get("phase_slot_count"),
            "fallback_altitude_count": orbit.get("fallback_altitude_count"),
        },
        "visibility": {
            "sample_step_sec": visibility.get("sample_step_sec"),
            "worker_count": visibility.get("worker_count"),
            "max_windows": visibility.get("max_windows"),
        },
        "selection": {
            "max_selected_satellites": selection.get("max_selected_satellites"),
            "require_positive_improvement": selection.get("require_positive_improvement"),
        },
    }


def resolve_profile_config(payload: dict[str, Any]) -> ProfileResolution:
    if not isinstance(payload, dict):
        raise ValueError("solver config must be a mapping/object")

    base_config = _profile_base_config(payload)
    profiles = _profile_payloads(payload)
    profile_name = _active_profile_name(payload)

    if profile_name == "custom" and not profiles:
        resolved_config = base_config
    else:
        if profile_name not in profiles:
            raise ValueError(
                f"run profile {profile_name!r} is not defined; available profiles: "
                f"{', '.join(sorted(profiles)) or '<none>'}"
            )
        resolved_config = _deep_merge(base_config, profiles[profile_name])

    sweep_points = _sweep_points(payload)
    sweep_rows: list[dict[str, Any]] = []
    for point in sweep_points:
        point_profile = str(point["profile"])
        if point_profile not in profiles:
            raise ValueError(
                f"parameter_sweep point {point['name']!r} references undefined "
                f"profile {point_profile!r}"
            )
        point_config = _deep_merge(base_config, profiles[point_profile])
        point_config = _deep_merge(point_config, point["overrides"])
        sweep_rows.append(
            {
                "index": int(point["index"]),
                "name": str(point["name"]),
                "profile": point_profile,
                "summary": _config_summary(point_config),
            }
        )

    return ProfileResolution(
        profile_name=profile_name,
        available_profiles=sorted(profiles),
        resolved_config=resolved_config,
        summary={
            "active_profile": profile_name,
            "available_profiles": sorted(profiles),
            "resolved": _config_summary(resolved_config),
        },
        sweep_summary={
            "point_count": len(sweep_rows),
            "points": sweep_rows,
        },
    )
