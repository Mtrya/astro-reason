"""CLI entry point for the stereo_imaging visualizer."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import types
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from itertools import combinations
from pathlib import Path
from typing import Any

_VISUALIZER_DIR = Path(__file__).resolve().parent
_BENCHMARK_DIR = _VISUALIZER_DIR.parent

import brahe
import matplotlib
import plotly.graph_objects as go

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from brahe.plots.texture_utils import load_earth_texture
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Polygon
from skyfield.api import EarthSatellite


def _ensure_runtime_package(name: str, path: Path) -> types.ModuleType:
    package = sys.modules.get(name)
    if package is None:
        package = types.ModuleType(name)
        package.__path__ = [str(path)]
        sys.modules[name] = package
    return package


def _load_runtime_modules():
    """Support `python path/to/visualizer/run.py` without package context."""
    package_name = "_stereo_imaging_visualizer_runtime"

    _ensure_runtime_package(package_name, _BENCHMARK_DIR)
    _ensure_runtime_package(f"{package_name}.verifier", _BENCHMARK_DIR / "verifier")

    loaded: dict[str, Any] = {}
    for module_name, rel_path in (
        ("verifier.io", "verifier/io.py"),
        ("verifier.engine", "verifier/engine.py"),
    ):
        qualified_name = f"{package_name}.{module_name}"
        module = sys.modules.get(qualified_name)
        if module is None:
            spec = importlib.util.spec_from_file_location(
                qualified_name,
                _BENCHMARK_DIR / rel_path,
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"Unable to load {qualified_name}")
            module = importlib.util.module_from_spec(spec)
            module.__package__ = qualified_name.rpartition(".")[0]
            sys.modules[qualified_name] = module
            spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded["verifier.io"], loaded["verifier.engine"]


if __package__ in {None, ""}:  # pragma: no cover - script-path import support
    _io_module, _engine_module = _load_runtime_modules()
    load_case = _io_module.load_case
    load_solution_actions = _io_module.load_solution_actions
    verify_solution = _engine_module.verify_solution
    _TS = _engine_module._TS
    _angle_between_deg = _engine_module._angle_between_deg
    _ecef_to_enz = _engine_module._ecef_to_enz
    _pair_geom_quality = _engine_module._pair_geom_quality
    _monte_carlo_overlap_fraction = _engine_module._monte_carlo_overlap_fraction
    _monte_carlo_tri_overlap = _engine_module._monte_carlo_tri_overlap
    _satellite_state_ecef_m = _engine_module._satellite_state_ecef_m
    _strip_polyline_en = _engine_module._strip_polyline_en
    _target_ecef_m = _engine_module._target_ecef_m
    _tri_bonus_R = _engine_module._tri_bonus_R
    _tri_quality_from_valid_pairs = _engine_module._tri_quality_from_valid_pairs
else:  # pragma: no cover
    from ..verifier.engine import (
        _TS,
        _angle_between_deg,
        _ecef_to_enz,
        _monte_carlo_overlap_fraction,
        _monte_carlo_tri_overlap,
        _pair_geom_quality,
        _satellite_state_ecef_m,
        _strip_polyline_en,
        _target_ecef_m,
        _tri_bonus_R,
        _tri_quality_from_valid_pairs,
        verify_solution,
    )
    from ..verifier.io import load_case, load_solution_actions


_SCENE_COLORS = {
    "urban_structured": "#ff8a76",
    "vegetated": "#65c466",
    "rugged": "#d0976b",
    "open": "#66c6ff",
}

_OBS_COLORS = [
    "#ffd166",
    "#ef476f",
    "#06d6a0",
    "#118ab2",
    "#ff9f1c",
    "#c77dff",
]

_THEME = {
    "background": "#ffffff",
    "panel": "#f7f8fa",
    "grid": "#d5dbe3",
    "axis": "#39424e",
    "text": "#1f2933",
    "muted": "#52606d",
    "target": "#111827",
    "aoi": "#9aa5b1",
    "invalid": "#b42318",
    "valid": "#18794e",
}

_DEFAULT_OUTPUT_ROOT = _VISUALIZER_DIR / "plots"
_WORLD_TEXTURE_EXTENT = (-180.0, 180.0, -90.0, 90.0)
_WORLD_TEXTURE: np.ndarray | None = None
_EARTH_TRACE_CACHE: dict[str, go.BaseTraceType] = {}


def _apply_axes_theme(ax: plt.Axes, *, facecolor: str | None = None) -> None:
    ax.set_facecolor(facecolor or _THEME["panel"])
    ax.grid(True, color=_THEME["grid"], alpha=0.7, linewidth=0.8)
    ax.tick_params(colors=_THEME["muted"])
    for spine in ax.spines.values():
        spine.set_color(_THEME["axis"])


def _load_world_texture() -> np.ndarray:
    global _WORLD_TEXTURE
    if _WORLD_TEXTURE is None:
        for texture_name in ("blue_marble", "natural_earth_50m"):
            try:
                image = load_earth_texture(texture_name)
            except Exception:
                continue
            if image is not None:
                _WORLD_TEXTURE = np.asarray(image)
                break
    if _WORLD_TEXTURE is None:
        raise FileNotFoundError("No Brahe Earth texture is available")
    return _WORLD_TEXTURE


def _earth_trace() -> go.BaseTraceType:
    cached = _EARTH_TRACE_CACHE.get("default")
    if cached is not None:
        return cached

    radius_m = float(brahe.R_EARTH)
    try:
        texture = _load_world_texture()
    except FileNotFoundError:
        u = np.linspace(0.0, 2.0 * math.pi, 50)
        v = np.linspace(0.0, math.pi, 30)
        x = radius_m * np.outer(np.cos(u), np.sin(v))
        y = radius_m * np.outer(np.sin(u), np.sin(v))
        z = radius_m * np.outer(np.ones(np.size(u)), np.cos(v))
        trace = go.Surface(
            x=x,
            y=y,
            z=z,
            colorscale="Blues",
            showscale=False,
            opacity=0.9,
            name="Earth",
            hoverinfo="skip",
        )
        _EARTH_TRACE_CACHE["default"] = trace
        return trace

    n_lon = 120
    n_lat = 60
    lons = np.linspace(0.0, 2.0 * math.pi, n_lon)
    lats = np.linspace(0.0, math.pi, n_lat)

    vertices = []
    for lat in lats:
        for lon in lons:
            x = radius_m * math.sin(lat) * math.cos(lon)
            y = radius_m * math.sin(lat) * math.sin(lon)
            z = radius_m * math.cos(lat)
            vertices.append((x, y, z))
    verts = np.asarray(vertices, dtype=float)

    faces = []
    for i in range(n_lat - 1):
        for j in range(n_lon - 1):
            v0 = i * n_lon + j
            v1 = i * n_lon + (j + 1)
            v2 = (i + 1) * n_lon + j
            v3 = (i + 1) * n_lon + (j + 1)
            faces.append((v0, v1, v2))
            faces.append((v1, v3, v2))
    face_array = np.asarray(faces, dtype=int)

    img_h, img_w = texture.shape[:2]
    face_colors: list[str] = []
    for face in face_array:
        avg = verts[face].mean(axis=0)
        r = float(np.linalg.norm(avg))
        if r <= 0.0:
            tex_x = tex_y = 0
        else:
            lat = math.acos(max(-1.0, min(1.0, avg[2] / r)))
            lon = math.atan2(avg[1], avg[0])
            u_coord = (lon % (2.0 * math.pi)) / (2.0 * math.pi)
            v_coord = lat / math.pi
            tex_x = min(img_w - 1, max(0, int(u_coord * (img_w - 1))))
            tex_y = min(img_h - 1, max(0, int(v_coord * (img_h - 1))))
        rgb = texture[tex_y, tex_x, :3]
        face_colors.append(f"rgb({int(rgb[0])},{int(rgb[1])},{int(rgb[2])})")

    trace = go.Mesh3d(
        x=verts[:, 0],
        y=verts[:, 1],
        z=verts[:, 2],
        i=face_array[:, 0],
        j=face_array[:, 1],
        k=face_array[:, 2],
        facecolor=face_colors,
        showscale=False,
        name="Earth",
        hoverinfo="skip",
        lighting=dict(ambient=0.65, diffuse=0.75, specular=0.15, roughness=0.85),
        lightposition=dict(x=100000.0, y=100000.0, z=100000.0),
    )
    _EARTH_TRACE_CACHE["default"] = trace
    return trace


def _draw_world_texture(ax: plt.Axes) -> None:
    xmin, xmax, ymin, ymax = _WORLD_TEXTURE_EXTENT
    try:
        texture = _load_world_texture()
    except FileNotFoundError:
        return
    ax.imshow(
        texture,
        origin="upper",
        extent=[xmin, xmax, ymin, ymax],
        aspect="auto",
        interpolation="bilinear",
        zorder=0,
        alpha=0.96,
    )


def _parse_iso_utc(value: str, *, field: str = "timestamp") -> datetime:
    """Parse ISO 8601 as UTC; reject naive strings (same rules as verifier `io._parse_iso_utc`)."""
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


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _serialize_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _satellite_cache(satellites: dict[str, Any]) -> dict[str, EarthSatellite]:
    return {
        sid: EarthSatellite(sd.tle_line1, sd.tle_line2, name=sid, ts=_TS)
        for sid, sd in satellites.items()
    }


def _sample_track_segments(
    sf_sat: EarthSatellite,
    start: datetime,
    end: datetime,
    *,
    step_s: float,
) -> list[tuple[list[float], list[float]]]:
    lons: list[float] = []
    lats: list[float] = []
    current = start
    while current <= end:
        pos_ecef_m, _ = _satellite_state_ecef_m(sf_sat, current)
        lon_deg, lat_deg, _alt_m = brahe.position_ecef_to_geodetic(
            pos_ecef_m,
            brahe.AngleFormat.DEGREES,
        )
        lons.append(float(lon_deg))
        lats.append(float(lat_deg))
        current += timedelta(seconds=step_s)
    if not lons or current - timedelta(seconds=step_s) < end:
        pos_ecef_m, _ = _satellite_state_ecef_m(sf_sat, end)
        lon_deg, lat_deg, _alt_m = brahe.position_ecef_to_geodetic(
            pos_ecef_m,
            brahe.AngleFormat.DEGREES,
        )
        lons.append(float(lon_deg))
        lats.append(float(lat_deg))
    return brahe.split_ground_track_at_antimeridian(lons, lats)


def _scene_counts(targets: dict[str, Any]) -> Counter[str]:
    return Counter(target.scene_type for target in targets.values())


def _target_ranges(targets: dict[str, Any]) -> dict[str, float]:
    aoi_values = [target.aoi_radius_m for target in targets.values()]
    elevation_values = [target.elevation_ref_m for target in targets.values()]
    latitudes = [target.latitude_deg for target in targets.values()]
    longitudes = [target.longitude_deg for target in targets.values()]
    return {
        "aoi_min_m": min(aoi_values),
        "aoi_max_m": max(aoi_values),
        "elev_min_m": min(elevation_values),
        "elev_max_m": max(elevation_values),
        "lat_min_deg": min(latitudes),
        "lat_max_deg": max(latitudes),
        "lon_min_deg": min(longitudes),
        "lon_max_deg": max(longitudes),
    }


def render_overview(
    case_dir: str | Path,
    out_path: str | Path,
    *,
    ground_track_step_s: float,
) -> Path:
    case_path = Path(case_dir)
    out_file = Path(out_path)
    mission, satellites, targets = load_case(case_path)
    sf_sats = _satellite_cache(satellites)

    fig = plt.figure(figsize=(13, 7.5))
    fig.patch.set_facecolor(_THEME["background"])
    gs = fig.add_gridspec(1, 2, width_ratios=[2.4, 1.2])
    ax_map = fig.add_subplot(gs[0, 0])
    ax_summary = fig.add_subplot(gs[0, 1])

    _apply_axes_theme(ax_map, facecolor="#09121a")
    ax_map.set_xlim(-180.0, 180.0)
    ax_map.set_ylim(-90.0, 90.0)
    _draw_world_texture(ax_map)
    ax_map.set_xlabel("Longitude (deg)", color=_THEME["text"])
    ax_map.set_ylabel("Latitude (deg)", color=_THEME["text"])
    ax_map.set_title(
        f"Stereo Imaging Case Overview: {case_path.name}",
        color=_THEME["text"],
        fontsize=14,
        fontweight="bold",
    )

    sat_legend_handles: list[Line2D] = []
    for sat_index, (sat_id, sf_sat) in enumerate(sf_sats.items()):
        segments = _sample_track_segments(
            sf_sat,
            mission.horizon_start,
            mission.horizon_end,
            step_s=ground_track_step_s,
        )
        color = _OBS_COLORS[sat_index % len(_OBS_COLORS)]
        sat_legend_handles.append(
            Line2D([0], [0], color=color, linewidth=2.0, label=sat_id)
        )
        for seg_idx, (lon_seg, lat_seg) in enumerate(segments):
            ax_map.plot(
                lon_seg,
                lat_seg,
                color=color,
                linewidth=1.6,
                alpha=0.95,
                zorder=2,
            )

    scene_legend_handles: list[Line2D] = []
    for scene_type, color in _SCENE_COLORS.items():
        scene_targets = [t for t in targets.values() if t.scene_type == scene_type]
        if not scene_targets:
            continue
        scene_legend_handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="None",
                markersize=7,
                markerfacecolor=color,
                markeredgecolor="white",
                markeredgewidth=0.8,
                label=scene_type,
            )
        )
        ax_map.scatter(
            [target.longitude_deg for target in scene_targets],
            [target.latitude_deg for target in scene_targets],
            s=28,
            color=color,
            edgecolors="white",
            linewidths=0.6,
            zorder=3,
        )

    sat_legend = ax_map.legend(
        handles=sat_legend_handles,
        title="Ground tracks",
        loc="lower left",
        bbox_to_anchor=(0.0, -0.24),
        ncol=max(1, min(2, len(sat_legend_handles))),
        fontsize=9,
        title_fontsize=9,
        frameon=False,
    )
    ax_map.add_artist(sat_legend)
    ax_map.legend(
        handles=scene_legend_handles,
        title="Target scenes",
        loc="lower right",
        bbox_to_anchor=(1.0, -0.24),
        ncol=max(1, min(2, len(scene_legend_handles))),
        fontsize=9,
        title_fontsize=9,
        frameon=False,
    )

    counts = _scene_counts(targets)
    ranges = _target_ranges(targets)
    summary_lines = [
        f"Case: {case_path.name}",
        f"Horizon: {_utc_iso(mission.horizon_start)} to {_utc_iso(mission.horizon_end)}",
        "",
        f"Satellites ({len(satellites)}):",
        *[f"  - {sat_id}" for sat_id in satellites],
        "",
        f"Targets: {len(targets)}",
        f"  urban_structured: {counts.get('urban_structured', 0)}",
        f"  vegetated: {counts.get('vegetated', 0)}",
        f"  rugged: {counts.get('rugged', 0)}",
        f"  open: {counts.get('open', 0)}",
        "",
        f"AOI radius: {ranges['aoi_min_m']:.1f} to {ranges['aoi_max_m']:.1f} m",
        f"Elevation: {ranges['elev_min_m']:.1f} to {ranges['elev_max_m']:.1f} m",
        f"Latitude: {ranges['lat_min_deg']:.2f} to {ranges['lat_max_deg']:.2f} deg",
        f"Longitude: {ranges['lon_min_deg']:.2f} to {ranges['lon_max_deg']:.2f} deg",
    ]

    ax_summary.axis("off")
    ax_summary.set_facecolor(_THEME["panel"])
    ax_summary.text(
        0.0,
        1.0,
        "\n".join(summary_lines),
        va="top",
        ha="left",
        fontsize=10,
        color=_THEME["text"],
        family="monospace",
    )

    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.93, bottom=0.18, wspace=0.22)
    fig.savefig(out_file, dpi=130)
    plt.close(fig)
    return out_file


def _candidate_output_dir(case_path: Path, out_dir: str | Path | None) -> Path:
    if out_dir is not None:
        return Path(out_dir)
    return _DEFAULT_OUTPUT_ROOT / case_path.name / "batch"


def _overview_output_path(case_path: Path, out_path: str | Path | None) -> Path:
    if out_path is not None:
        return Path(out_path)
    return _DEFAULT_OUTPUT_ROOT / case_path.name / "overview.png"


def _known_action_indices(
    actions: list[Any],
    satellites: dict[str, Any],
    targets: dict[str, Any],
) -> list[int]:
    return [
        idx
        for idx, action in enumerate(actions)
        if action.satellite_id in satellites and action.target_id in targets
    ]


def _derived_by_action_index(
    report: Any,
    actions: list[Any],
    satellites: dict[str, Any],
    targets: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    known_indices = _known_action_indices(actions, satellites, targets)
    return {
        action_idx: derived
        for action_idx, derived in zip(
            known_indices,
            report.derived_observations,
            strict=True,
        )
    }


def _candidate_groups(
    actions: list[Any],
    satellites: dict[str, Any],
    targets: dict[str, Any],
) -> list[tuple[tuple[str, str], list[int]]]:
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for idx in _known_action_indices(actions, satellites, targets):
        action = actions[idx]
        groups[(action.satellite_id, action.target_id)].append(idx)
    return sorted(groups.items(), key=lambda item: (min(item[1]), item[0][0], item[0][1]))


def _observation_cache(
    actions: list[Any],
    derived_by_idx: dict[int, dict[str, Any]],
    satellites: dict[str, Any],
    targets: dict[str, Any],
    sf_sats: dict[str, EarthSatellite],
    target_ecef: dict[str, np.ndarray],
) -> dict[int, dict[str, Any]]:
    cache: dict[int, dict[str, Any]] = {}
    for idx, derived in derived_by_idx.items():
        action = actions[idx]
        sat_def = satellites[action.satellite_id]
        target_vec = target_ecef[action.target_id]
        sf_sat = sf_sats[action.satellite_id]
        mid = action.start + (action.end - action.start) / 2
        sat_mid_ecef, _sat_mid_vel = _satellite_state_ecef_m(sf_sat, mid)
        sat_mid_enz = _ecef_to_enz(target_vec, sat_mid_ecef)
        horizontal_m = float(np.linalg.norm(sat_mid_enz[:2]))
        up_m = float(sat_mid_enz[2])
        az_deg = math.degrees(math.atan2(float(sat_mid_enz[0]), float(sat_mid_enz[1]))) % 360.0
        el_deg = math.degrees(math.atan2(up_m, max(horizontal_m, 1.0e-9)))
        half_width_m = float(derived["slant_range_m"]) * math.tan(
            math.radians(sat_def.half_cross_track_fov_deg)
        )
        polyline = _strip_polyline_en(
            sf_sat,
            target_vec,
            action.start,
            action.end,
            sample_step_s=8.0,
            off_nadir_along_deg=action.off_nadir_along_deg,
            off_nadir_across_deg=action.off_nadir_across_deg,
        )
        cache[idx] = {
            "action": action,
            "derived": derived,
            "sat_def": sat_def,
            "target_def": targets[action.target_id],
            "target_ecef": target_vec,
            "sf_sat": sf_sat,
            "mid_time": mid,
            "sat_mid_ecef": sat_mid_ecef,
            "sat_mid_enz": sat_mid_enz,
            "horizontal_m": horizontal_m,
            "up_m": up_m,
            "az_deg": az_deg,
            "elevation_deg": el_deg,
            "half_width_m": half_width_m,
            "polyline_en": polyline,
        }
    return cache


def _polyline_buffer_polygon(polyline: list[tuple[float, float]], half_width_m: float) -> list[tuple[float, float]]:
    if not polyline:
        return []
    if len(polyline) == 1:
        cx, cy = polyline[0]
        angles = np.linspace(0.0, 2.0 * math.pi, 40, endpoint=False)
        return [
            (cx + half_width_m * math.cos(angle), cy + half_width_m * math.sin(angle))
            for angle in angles
        ]

    normals: list[np.ndarray] = []
    points = [np.asarray(point, dtype=float) for point in polyline]
    for point_idx in range(len(points)):
        candidate_normals: list[np.ndarray] = []
        if point_idx > 0:
            delta = points[point_idx] - points[point_idx - 1]
            if np.linalg.norm(delta) > 1.0e-9:
                tangent = delta / np.linalg.norm(delta)
                candidate_normals.append(np.array([-tangent[1], tangent[0]]))
        if point_idx < len(points) - 1:
            delta = points[point_idx + 1] - points[point_idx]
            if np.linalg.norm(delta) > 1.0e-9:
                tangent = delta / np.linalg.norm(delta)
                candidate_normals.append(np.array([-tangent[1], tangent[0]]))
        if candidate_normals:
            normal = np.sum(candidate_normals, axis=0)
            if np.linalg.norm(normal) < 1.0e-9:
                normal = candidate_normals[0]
            normal = normal / np.linalg.norm(normal)
        else:
            normal = np.array([0.0, 1.0])
        normals.append(normal)

    left = [tuple((point + half_width_m * normal).tolist()) for point, normal in zip(points, normals, strict=True)]
    right = [tuple((point - half_width_m * normal).tolist()) for point, normal in zip(points, normals, strict=True)]
    return left + list(reversed(right))


def _pair_metric_record(
    i: int,
    j: int,
    obs_cache: dict[int, dict[str, Any]],
    mission: Any,
) -> dict[str, Any]:
    oi = obs_cache[i]
    oj = obs_cache[j]
    target_def = oi["target_def"]
    sat_def = oi["sat_def"]
    target_ecef = oi["target_ecef"]

    ui = (oi["sat_mid_ecef"] - target_ecef) / np.linalg.norm(oi["sat_mid_ecef"] - target_ecef)
    uj = (oj["sat_mid_ecef"] - target_ecef) / np.linalg.norm(oj["sat_mid_ecef"] - target_ecef)
    gamma_deg = _angle_between_deg(ui, uj)
    overlap_fraction = _monte_carlo_overlap_fraction(
        target_def.aoi_radius_m,
        oi["polyline_en"],
        oi["half_width_m"],
        oj["polyline_en"],
        oj["half_width_m"],
        n_samples=150,
        rng=np.random.default_rng(20260406),
    )
    scale_i = float(oi["derived"]["effective_pixel_scale_m"])
    scale_j = float(oj["derived"]["effective_pixel_scale_m"])
    pixel_scale_ratio = max(scale_i, scale_j) / min(scale_i, scale_j)
    mean_alt = max(
        1000.0,
        0.5
        * (
            float(np.linalg.norm(oi["sat_mid_ecef"])) - 6378137.0
            + float(np.linalg.norm(oj["sat_mid_ecef"])) - 6378137.0
        ),
    )
    b_h_proxy = float(np.linalg.norm(oi["sat_mid_ecef"] - oj["sat_mid_ecef"])) / mean_alt
    same_access = (
        oi["derived"]["access_interval_id"] != "none"
        and oi["derived"]["access_interval_id"] == oj["derived"]["access_interval_id"]
    )
    valid = (
        same_access
        and overlap_fraction + 1.0e-6 >= mission.min_overlap_fraction
        and mission.min_convergence_deg - 1.0e-6 <= gamma_deg <= mission.max_convergence_deg + 1.0e-6
        and pixel_scale_ratio <= mission.max_pixel_scale_ratio + 1.0e-6
    )
    q_overlap = min(1.0, overlap_fraction / 0.95)
    q_res = max(0.0, 1.0 - (pixel_scale_ratio - 1.0) / 0.5)
    q_geom = _pair_geom_quality(gamma_deg, target_def.scene_type)
    weights = mission.pair_weights
    q_pair_raw = (
        weights["geometry"] * q_geom
        + weights["overlap"] * q_overlap
        + weights["resolution"] * q_res
    )
    return {
        "indices": (i, j),
        "overlap_fraction": overlap_fraction,
        "gamma_deg": gamma_deg,
        "pixel_scale_ratio": pixel_scale_ratio,
        "b_h_proxy": b_h_proxy,
        "same_access": same_access,
        "valid": valid,
        "score": q_pair_raw if valid else 0.0,
        "q_pair_raw": q_pair_raw,
    }


def _tri_metric_record(
    indices: tuple[int, int, int],
    obs_cache: dict[int, dict[str, Any]],
    pair_cache: dict[tuple[int, int], dict[str, Any]],
    mission: Any,
) -> dict[str, Any]:
    obs = [obs_cache[idx] for idx in indices]
    target_def = obs[0]["target_def"]
    overlap_fraction = _monte_carlo_tri_overlap(
        target_def.aoi_radius_m,
        [entry["polyline_en"] for entry in obs],
        [entry["half_width_m"] for entry in obs],
        n_samples=150,
        rng=np.random.default_rng(20260407),
    )
    pair_records = [
        pair_cache[tuple(sorted(pair))]
        for pair in combinations(indices, 2)
    ]
    pair_flags = [record["valid"] for record in pair_records]
    pair_qs = [record["q_pair_raw"] for record in pair_records]
    anchor = any(
        float(entry["derived"]["boresight_off_nadir_deg"])
        <= mission.near_nadir_anchor_max_off_nadir_deg + 1.0e-6
        for entry in obs
    )
    same_access = len({entry["derived"]["access_interval_id"] for entry in obs}) == 1 and obs[0]["derived"]["access_interval_id"] != "none"
    valid = (
        same_access
        and overlap_fraction + 1.0e-6 >= mission.min_overlap_fraction
        and sum(1 for flag in pair_flags if flag) >= 2
        and anchor
    )
    beta = mission.tri_stereo_bonus_by_scene[target_def.scene_type]
    tri_bonus_R = _tri_bonus_R(pair_flags, anchor)
    q_tri = _tri_quality_from_valid_pairs(
        pair_flags,
        pair_qs,
        beta=beta,
        tri_bonus_R=tri_bonus_R,
    )
    return {
        "indices": indices,
        "overlap_fraction": overlap_fraction,
        "pair_flags": pair_flags,
        "anchor": anchor,
        "same_access": same_access,
        "valid": valid,
        "score": q_tri if valid else 0.0,
        "q_tri_raw": q_tri,
        "pair_records": pair_records,
    }


def _candidate_extent(obs_entries: list[dict[str, Any]], aoi_radius_m: float) -> tuple[float, float, float, float]:
    xs = [0.0]
    ys = [0.0]
    padding = aoi_radius_m
    for entry in obs_entries:
        if entry["polyline_en"]:
            xs.extend(point[0] for point in entry["polyline_en"])
            ys.extend(point[1] for point in entry["polyline_en"])
        padding = max(padding, entry["half_width_m"])
    xmin = min(xs) - padding - aoi_radius_m * 0.2
    xmax = max(xs) + padding + aoi_radius_m * 0.2
    ymin = min(ys) - padding - aoi_radius_m * 0.2
    ymax = max(ys) + padding + aoi_radius_m * 0.2
    return xmin, xmax, ymin, ymax


def _draw_observation_footprint(ax: plt.Axes, obs_entry: dict[str, Any], color: str, action_idx: int) -> None:
    polygon = _polyline_buffer_polygon(obs_entry["polyline_en"], obs_entry["half_width_m"])
    if polygon:
        ax.add_patch(
            Polygon(
                polygon,
                closed=True,
                facecolor=color,
                edgecolor=color,
                linewidth=1.2,
                alpha=0.18,
            )
        )
    if obs_entry["polyline_en"]:
        xs = [point[0] for point in obs_entry["polyline_en"]]
        ys = [point[1] for point in obs_entry["polyline_en"]]
        ax.plot(xs, ys, color=color, linewidth=2.2)
        mid_idx = len(obs_entry["polyline_en"]) // 2
        ax.scatter([xs[mid_idx]], [ys[mid_idx]], color=color, s=28, zorder=4)
        ax.text(
            xs[mid_idx],
            ys[mid_idx],
            f" #{action_idx}",
            color=color,
            fontsize=9,
            fontweight="bold",
            va="bottom",
            ha="left",
        )


def _render_candidate_figure(
    kind: str,
    metric_record: dict[str, Any],
    obs_entries: list[tuple[int, dict[str, Any]]],
    out_path: Path,
) -> None:
    target_def = obs_entries[0][1]["target_def"]
    validity_color = _THEME["valid"] if metric_record["valid"] else _THEME["invalid"]
    access_ids = [entry["derived"]["access_interval_id"] for _, entry in obs_entries]
    action_lines = [
        f"#{action_idx}: {obs_entry['derived']['start_time']} -> {obs_entry['derived']['end_time']}"
        for action_idx, obs_entry in obs_entries
    ]
    if kind == "pair":
        metric_lines = [
            f"Valid: {metric_record['valid']}",
            f"Same access: {metric_record['same_access']}",
            f"Access IDs: {', '.join(access_ids)}",
            f"Overlap: {metric_record['overlap_fraction']:.3f}",
            f"Convergence: {metric_record['gamma_deg']:.2f} deg",
            f"Pixel ratio: {metric_record['pixel_scale_ratio']:.3f}",
            f"B/H proxy: {metric_record['b_h_proxy']:.3f}",
            f"Score: {metric_record['score']:.3f}",
        ]
    else:
        metric_lines = [
            f"Valid: {metric_record['valid']}",
            f"Same access: {metric_record['same_access']}",
            f"Access IDs: {', '.join(access_ids)}",
            f"Common overlap: {metric_record['overlap_fraction']:.3f}",
            f"Pair valids: {metric_record['pair_flags']}",
            f"Anchor present: {metric_record['anchor']}",
            f"Score: {metric_record['score']:.3f}",
        ]
    fig = go.Figure()
    fig.add_trace(_earth_trace())

    target_vec = np.asarray(obs_entries[0][1]["target_ecef"], dtype=float)
    fig.add_trace(
        go.Scatter3d(
            x=[target_vec[0]],
            y=[target_vec[1]],
            z=[target_vec[2]],
            mode="markers+text",
            name="Target",
            text=[target_def.target_id],
            textposition="top center",
            marker=dict(size=7, color="#ffffff", line=dict(color="#111827", width=2)),
            hovertemplate=(
                f"Target: {target_def.target_id}<br>"
                f"Scene: {target_def.scene_type}<br>"
                f"Lat/Lon: {target_def.latitude_deg:.4f}, {target_def.longitude_deg:.4f}<br>"
                f"AOI radius: {target_def.aoi_radius_m:.1f} m<br>"
                f"Elevation: {target_def.elevation_ref_m:.1f} m"
                "<extra></extra>"
            ),
        )
    )

    extents = [float(np.linalg.norm(target_vec))]
    for obs_number, (action_idx, obs_entry) in enumerate(obs_entries):
        color = _OBS_COLORS[obs_number % len(_OBS_COLORS)]
        sat_vec = np.asarray(obs_entry["sat_mid_ecef"], dtype=float)
        extents.append(float(np.linalg.norm(sat_vec)))
        hover = (
            f"Action #{action_idx}<br>"
            f"Satellite: {obs_entry['action'].satellite_id}<br>"
            f"Target: {obs_entry['action'].target_id}<br>"
            f"Midpoint: {_utc_iso(obs_entry['mid_time'])}<br>"
            f"Off-nadir: {obs_entry['derived']['boresight_off_nadir_deg']:.2f} deg<br>"
            f"Azimuth: {obs_entry['derived']['boresight_azimuth_deg']:.2f} deg<br>"
            f"Effective pixel scale: {obs_entry['derived']['effective_pixel_scale_m']:.2f} m<br>"
            f"Access interval: {obs_entry['derived']['access_interval_id']}"
            "<extra></extra>"
        )
        fig.add_trace(
            go.Scatter3d(
                x=[sat_vec[0]],
                y=[sat_vec[1]],
                z=[sat_vec[2]],
                mode="markers+text",
                name=f"Obs #{action_idx}",
                text=[f"#{action_idx}"],
                textposition="top center",
                marker=dict(size=5, color=color, line=dict(color="#ffffff", width=1)),
                hovertemplate=hover,
            )
        )
        fig.add_trace(
            go.Scatter3d(
                x=[sat_vec[0], target_vec[0]],
                y=[sat_vec[1], target_vec[1]],
                z=[sat_vec[2], target_vec[2]],
                mode="lines",
                name=f"Ray #{action_idx}",
                line=dict(color=color, width=6),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    axis_limit = max(extents) * 1.1
    metrics_text = "<br>".join(
        [
            f"<b>{kind.upper()} candidate</b>",
            f"Target: {target_def.target_id}",
            f"Scene: {target_def.scene_type}",
            f"Valid: <span style='color:{validity_color}'>{metric_record['valid']}</span>",
            f"Same access: {metric_record['same_access']}",
            f"Access IDs: {', '.join(access_ids)}",
            *metric_lines[2:],
            "",
            "<b>Observations</b>",
            *action_lines,
        ]
    )

    fig.update_layout(
        title=dict(
            text=f"{kind.upper()} ECEF view: {target_def.target_id}",
            x=0.03,
            xanchor="left",
        ),
        scene=dict(
            domain=dict(x=[0.0, 0.72], y=[0.0, 1.0]),
            xaxis=dict(
                title="ECEF X (m)",
                showbackground=False,
                showgrid=False,
                zeroline=False,
                range=[-axis_limit, axis_limit],
            ),
            yaxis=dict(
                title="ECEF Y (m)",
                showbackground=False,
                showgrid=False,
                zeroline=False,
                range=[-axis_limit, axis_limit],
            ),
            zaxis=dict(
                title="ECEF Z (m)",
                showbackground=False,
                showgrid=False,
                zeroline=False,
                range=[-axis_limit, axis_limit],
            ),
            aspectmode="cube",
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.1)),
            bgcolor="#0b1220",
        ),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        margin=dict(l=10, r=280, t=60, b=10),
        legend=dict(
            x=0.01,
            y=0.98,
            bgcolor="rgba(255,255,255,0.8)",
        ),
        annotations=[
            dict(
                x=1.02,
                y=0.98,
                xref="paper",
                yref="paper",
                xanchor="left",
                yanchor="top",
                align="left",
                showarrow=False,
                bordercolor=validity_color,
                borderwidth=2,
                borderpad=8,
                bgcolor="#fbfcfe",
                font=dict(size=12, color=_THEME["text"]),
                text=metrics_text,
            )
        ],
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(out_path, include_plotlyjs="directory", full_html=True)


def render_batch(
    case_dir: str | Path,
    solution_path: str | Path,
    out_dir: str | Path | None = None,
    *,
    limit: int | None = None,
) -> Path:
    case_path = Path(case_dir)
    solution_file = Path(solution_path)
    mission, satellites, targets = load_case(case_path)
    actions = load_solution_actions(solution_file, case_path.name)
    report = verify_solution(case_path, solution_file)
    output_dir = _candidate_output_dir(case_path, out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for pattern in ("pair__*.png", "tri__*.png", "pair__*.html", "tri__*.html"):
        for stale_path in output_dir.glob(pattern):
            stale_path.unlink(missing_ok=True)
    (output_dir / "manifest.json").unlink(missing_ok=True)

    derived_by_idx = _derived_by_action_index(report, actions, satellites, targets)
    sf_sats = _satellite_cache(satellites)
    target_ecef = {target_id: _target_ecef_m(target) for target_id, target in targets.items()}
    obs_cache = _observation_cache(actions, derived_by_idx, satellites, targets, sf_sats, target_ecef)

    pair_cache: dict[tuple[int, int], dict[str, Any]] = {}
    manifest_items: list[dict[str, Any]] = []
    render_count = 0

    for (_group_key, action_indices) in _candidate_groups(actions, satellites, targets):
        for pair in combinations(action_indices, 2):
            if limit is not None and render_count >= limit:
                break
            pair_record = _pair_metric_record(pair[0], pair[1], obs_cache, mission)
            pair_cache[tuple(sorted(pair))] = pair_record
            out_path = output_dir / (
                f"pair__{actions[pair[0]].satellite_id}__{actions[pair[0]].target_id}__"
                f"{pair[0]}_{pair[1]}.html"
            )
            _render_candidate_figure(
                "pair",
                pair_record,
                [(pair[0], obs_cache[pair[0]]), (pair[1], obs_cache[pair[1]])],
                out_path,
            )
            manifest_items.append(
                {
                    "kind": "pair",
                    "action_indices": [pair[0], pair[1]],
                    "satellite_id": actions[pair[0]].satellite_id,
                    "target_id": actions[pair[0]].target_id,
                    "access_interval_ids": [
                        obs_cache[pair[0]]["derived"]["access_interval_id"],
                        obs_cache[pair[1]]["derived"]["access_interval_id"],
                    ],
                    "valid": pair_record["valid"],
                    "score": pair_record["score"],
                    "output_path": str(out_path),
                }
            )
            render_count += 1
        if limit is not None and render_count >= limit:
            break
        for tri in combinations(action_indices, 3):
            if limit is not None and render_count >= limit:
                break
            tri_record = _tri_metric_record(tuple(tri), obs_cache, pair_cache, mission)
            out_path = output_dir / (
                f"tri__{actions[tri[0]].satellite_id}__{actions[tri[0]].target_id}__"
                f"{tri[0]}_{tri[1]}_{tri[2]}.html"
            )
            _render_candidate_figure(
                "tri",
                tri_record,
                [(tri[0], obs_cache[tri[0]]), (tri[1], obs_cache[tri[1]]), (tri[2], obs_cache[tri[2]])],
                out_path,
            )
            manifest_items.append(
                {
                    "kind": "tri",
                    "action_indices": list(tri),
                    "satellite_id": actions[tri[0]].satellite_id,
                    "target_id": actions[tri[0]].target_id,
                    "access_interval_ids": [obs_cache[idx]["derived"]["access_interval_id"] for idx in tri],
                    "valid": tri_record["valid"],
                    "score": tri_record["score"],
                    "output_path": str(out_path),
                }
            )
            render_count += 1
        if limit is not None and render_count >= limit:
            break

    manifest = {
        "case_id": case_path.name,
        "solution_path": str(solution_file),
        "verifier_valid": report.valid,
        "verifier_violations": report.violations,
        "rendered_pairs": sum(1 for item in manifest_items if item["kind"] == "pair"),
        "rendered_tris": sum(1 for item in manifest_items if item["kind"] == "tri"),
        "items": manifest_items,
    }
    _serialize_json(manifest, output_dir / "manifest.json")
    return output_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stereo imaging visualizer with overview and batch geometry rendering.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    overview_parser = subparsers.add_parser("overview", help="Render a case overview PNG.")
    overview_parser.add_argument("case_dir", help="Path to dataset/cases/<case_id>")
    overview_parser.add_argument(
        "--out-path",
        type=Path,
        default=None,
        help="Where to write the overview PNG (default: benchmarks/stereo_imaging/visualizer/plots/<case>/overview.png)",
    )
    overview_parser.add_argument(
        "--ground-track-step-s",
        type=float,
        default=300.0,
        help="Satellite ground-track sampling step in seconds (default: 300)",
    )

    batch_parser = subparsers.add_parser("batch", help="Render pair and tri geometry snapshots.")
    batch_parser.add_argument("case_dir", help="Path to dataset/cases/<case_id>")
    batch_parser.add_argument("solution_path", help="Path to solution JSON")
    batch_parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for batch HTML outputs (default: benchmarks/stereo_imaging/visualizer/plots/<case>/batch)",
    )
    batch_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on total rendered images",
    )

    args = parser.parse_args(argv)

    if args.command == "overview":
        out_path = _overview_output_path(Path(args.case_dir), args.out_path)
        render_overview(
            args.case_dir,
            out_path,
            ground_track_step_s=args.ground_track_step_s,
        )
        print(f"Wrote overview image to {out_path}")
        return 0

    output_dir = render_batch(
        args.case_dir,
        args.solution_path,
        args.out_dir,
        limit=args.limit,
    )
    print(f"Wrote batch outputs to {output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
