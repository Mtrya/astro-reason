"""CLI entry point for the stereo_imaging visualizer."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from itertools import combinations
from pathlib import Path
from typing import Any

_VISUALIZER_DIR = Path(__file__).resolve().parent
_BENCHMARK_DIR = _VISUALIZER_DIR.parent

import brahe
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from brahe.plots.texture_utils import load_earth_texture
from matplotlib import colors as mpl_colors
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Polygon
from skyfield.api import EarthSatellite

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
_SATELLITE_TRACK_COLOR = "#64748b"

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
_NATURAL_EARTH_10M_CACHE_PATH = (
    Path(brahe.get_brahe_cache_dir()) / "textures" / "ne_10m_sr" / "NE1_HR_LC_SR_W.tif"
)
_WORLD_TEXTURE: np.ndarray | None = None
_ORTHOGRAPHIC_GLOBE_CACHE: dict[tuple[float, float, float], np.ndarray] = {}


def _apply_axes_theme(ax: plt.Axes, *, facecolor: str | None = None) -> None:
    ax.set_facecolor(facecolor or _THEME["panel"])
    ax.grid(True, color=_THEME["grid"], alpha=0.7, linewidth=0.8)
    ax.tick_params(colors=_THEME["muted"])
    for spine in ax.spines.values():
        spine.set_color(_THEME["axis"])


def _load_world_texture() -> np.ndarray:
    global _WORLD_TEXTURE
    if _WORLD_TEXTURE is None:
        texture_names = ["natural_earth_50m", "blue_marble"]
        if _NATURAL_EARTH_10M_CACHE_PATH.exists():
            texture_names.insert(0, "natural_earth_10m")
        for texture_name in texture_names:
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


def _action_midpoint(action: Any) -> datetime:
    return action.start + (action.end - action.start) / 2


def _product_time_separation_s(actions: list[Any]) -> float:
    if len(actions) < 2:
        return 0.0
    midpoints = [_action_midpoint(action) for action in actions]
    return (max(midpoints) - min(midpoints)).total_seconds()


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


def _select_track_satellites(
    satellites: dict[str, Any],
    *,
    max_ground_tracks: int | None,
) -> list[str]:
    satellite_ids = sorted(satellites)
    if max_ground_tracks is None or max_ground_tracks >= len(satellite_ids):
        return satellite_ids
    if max_ground_tracks <= 0:
        return []
    if max_ground_tracks == 1:
        return [satellite_ids[0]]

    selected_indices = np.linspace(
        0,
        len(satellite_ids) - 1,
        num=max_ground_tracks,
        dtype=int,
    )
    return [satellite_ids[int(idx)] for idx in selected_indices]


def render_overview(
    case_dir: str | Path,
    out_path: str | Path,
    *,
    ground_track_step_s: float,
    max_ground_tracks: int | None = 4,
) -> Path:
    case_path = Path(case_dir)
    out_file = Path(out_path)
    mission, satellites, targets = load_case(case_path)
    sf_sats = _satellite_cache(satellites)

    fig = plt.figure(figsize=(15, 8.5), constrained_layout=True)
    fig.patch.set_facecolor(_THEME["background"])
    gs = fig.add_gridspec(1, 2, width_ratios=[3.6, 1.2])
    ax_map = fig.add_subplot(gs[0, 0])
    ax_summary = fig.add_subplot(gs[0, 1])

    _apply_axes_theme(ax_map)
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

    plotted_satellite_ids = _select_track_satellites(
        satellites,
        max_ground_tracks=max_ground_tracks,
    )
    for sat_id in plotted_satellite_ids:
        sf_sat = sf_sats[sat_id]
        segments = _sample_track_segments(
            sf_sat,
            mission.horizon_start,
            mission.horizon_end,
            step_s=ground_track_step_s,
        )
        for lon_seg, lat_seg in segments:
            ax_map.plot(
                lon_seg,
                lat_seg,
                color=_SATELLITE_TRACK_COLOR,
                linewidth=0.8,
                alpha=0.36,
                zorder=1,
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
            s=32,
            color=color,
            edgecolors="white",
            linewidths=0.7,
            zorder=3,
        )

    ax_map.legend(
        handles=scene_legend_handles,
        title="Target scenes",
        loc="lower left",
        ncol=max(1, min(2, len(scene_legend_handles))),
        fontsize=9,
        title_fontsize=9,
        frameon=True,
        framealpha=0.92,
    )

    counts = _scene_counts(targets)
    ranges = _target_ranges(targets)
    horizon_hours = (
        mission.horizon_end - mission.horizon_start
    ).total_seconds() / 3600.0
    summary_lines = [
        f"Case: {case_path.name}",
        f"Horizon: {_utc_iso(mission.horizon_start)}",
        f"to {_utc_iso(mission.horizon_end)}",
        f"Duration: {horizon_hours:.1f} h",
        "",
        f"Satellites: {len(satellites)}",
        "Ground tracks:",
        f"  shown: {len(plotted_satellite_ids)}/{len(satellites)}",
        "  muted representative layer",
        f"  step: {ground_track_step_s:g}s",
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
    fig.savefig(out_file, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_file


def _products_output_dir(
    case_path: Path,
    out_dir: str | Path | None,
) -> Path:
    if out_dir is not None:
        return Path(out_dir)
    return _DEFAULT_OUTPUT_ROOT / case_path.name / "products"


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
        segment_normals: list[np.ndarray] = []
        if point_idx > 0:
            delta = points[point_idx] - points[point_idx - 1]
            if np.linalg.norm(delta) > 1.0e-9:
                tangent = delta / np.linalg.norm(delta)
                segment_normals.append(np.array([-tangent[1], tangent[0]]))
        if point_idx < len(points) - 1:
            delta = points[point_idx + 1] - points[point_idx]
            if np.linalg.norm(delta) > 1.0e-9:
                tangent = delta / np.linalg.norm(delta)
                segment_normals.append(np.array([-tangent[1], tangent[0]]))
        if segment_normals:
            normal = np.sum(segment_normals, axis=0)
            if np.linalg.norm(normal) < 1.0e-9:
                normal = segment_normals[0]
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
    stereo_mode: str,
) -> dict[str, Any]:
    oi = obs_cache[i]
    oj = obs_cache[j]
    target_def = oi["target_def"]
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
    valid = (
        overlap_fraction + 1.0e-6 >= mission.min_overlap_fraction
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
        "stereo_mode": stereo_mode,
        "time_separation_s": _product_time_separation_s([oi["action"], oj["action"]]),
        "overlap_fraction": overlap_fraction,
        "gamma_deg": gamma_deg,
        "pixel_scale_ratio": pixel_scale_ratio,
        "b_h_proxy": b_h_proxy,
        "valid": valid,
        "score": q_pair_raw if valid else 0.0,
        "q_pair_raw": q_pair_raw,
    }


def _tri_metric_record(
    indices: tuple[int, int, int],
    obs_cache: dict[int, dict[str, Any]],
    pair_cache: dict[tuple[int, int], dict[str, Any]],
    mission: Any,
    edge_modes: list[str],
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
    valid = (
        overlap_fraction + 1.0e-6 >= mission.min_overlap_fraction
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
        "edge_modes": edge_modes,
        "time_separation_s": _product_time_separation_s([entry["action"] for entry in obs]),
        "overlap_fraction": overlap_fraction,
        "pair_flags": pair_flags,
        "anchor": anchor,
        "valid": valid,
        "score": q_tri if valid else 0.0,
        "q_tri_raw": q_tri,
        "pair_records": pair_records,
    }


def _product_extent(obs_entries: list[dict[str, Any]], aoi_radius_m: float) -> tuple[float, float, float, float]:
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


def _draw_observation_footprint(
    ax: plt.Axes,
    obs_entry: dict[str, Any],
    color: str,
    action_idx: int,
    obs_number: int,
) -> None:
    line_styles = ("-", "--", ":")
    start_markers = ("s", "D", "P")
    end_markers = ("^", "v", "X")
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
        ax.plot(
            xs,
            ys,
            color=color,
            linewidth=2.2,
            linestyle=line_styles[obs_number % len(line_styles)],
        )
        ax.scatter(
            [xs[0]],
            [ys[0]],
            color=color,
            marker=start_markers[obs_number % len(start_markers)],
            edgecolor="white",
            linewidth=0.8,
            s=34,
            zorder=4,
        )
        ax.scatter(
            [xs[-1]],
            [ys[-1]],
            color=color,
            marker=end_markers[obs_number % len(end_markers)],
            edgecolor="white",
            linewidth=0.8,
            s=42,
            zorder=4,
        )
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


def _product_metric_lines(
    kind: str,
    metric_record: dict[str, Any],
    obs_entries: list[tuple[int, dict[str, Any]]],
) -> list[str]:
    target_def = obs_entries[0][1]["target_def"]
    access_ids = [entry["derived"]["access_interval_id"] for _, entry in obs_entries]
    access_lines = _access_summary_lines(access_ids)
    action_lines: list[str] = []
    for action_idx, obs_entry in obs_entries:
        action_lines.extend(
            [
                f"#{action_idx}: {obs_entry['action'].satellite_id}",
                f"  {obs_entry['derived']['start_time']} to {obs_entry['derived']['end_time']}",
            ]
        )
    if kind == "pair":
        return [
            "PAIR product",
            f"Target: {target_def.target_id}",
            f"Scene: {target_def.scene_type}",
            f"Valid: {metric_record['valid']}",
            f"Mode: {metric_record['stereo_mode']}",
            f"Time span: {metric_record['time_separation_s']:.1f} s",
            *access_lines,
            f"Overlap: {metric_record['overlap_fraction']:.3f}",
            f"Convergence: {metric_record['gamma_deg']:.2f} deg",
            f"Pixel ratio: {metric_record['pixel_scale_ratio']:.3f}",
            f"B/H proxy: {metric_record['b_h_proxy']:.3f}",
            f"Score: {metric_record['score']:.3f}",
            "",
            *action_lines,
        ]
    return [
        "TRI product",
        f"Target: {target_def.target_id}",
        f"Scene: {target_def.scene_type}",
        f"Valid: {metric_record['valid']}",
        f"Time span: {metric_record['time_separation_s']:.1f} s",
        f"Edge modes: {', '.join(metric_record['edge_modes'])}",
        *access_lines,
        f"Common overlap: {metric_record['overlap_fraction']:.3f}",
        f"Pair valids: {metric_record['pair_flags']}",
        f"Anchor present: {metric_record['anchor']}",
        f"Score: {metric_record['score']:.3f}",
        "",
        *action_lines,
    ]


def _format_access_id(access_id: str) -> str:
    parts = access_id.split("::")
    if len(parts) == 3:
        return f"{parts[0]} pass {parts[2]}"
    return access_id


def _access_summary_lines(access_ids: list[str]) -> list[str]:
    unique_access_ids = list(dict.fromkeys(access_ids))
    if len(unique_access_ids) == 1:
        return [f"Access: {_format_access_id(unique_access_ids[0])} ({len(access_ids)} obs)"]
    lines = ["Accesses:"]
    lines.extend(f"  {_format_access_id(access_id)}" for access_id in unique_access_ids[:4])
    if len(unique_access_ids) > 4:
        lines.append(f"  ... +{len(unique_access_ids) - 4} more")
    return lines


def _submitted_pair_mode(
    mission: Any,
    first_entry: dict[str, Any],
    second_entry: dict[str, Any],
) -> str | None:
    first_action = first_entry["action"]
    second_action = second_entry["action"]
    first_derived = first_entry["derived"]
    second_derived = second_entry["derived"]
    if first_action.target_id != second_action.target_id:
        return None
    if first_derived["access_interval_id"] == "none" or second_derived["access_interval_id"] == "none":
        return None
    separation_s = _product_time_separation_s([first_action, second_action])
    if separation_s - 1.0e-6 > mission.max_stereo_pair_separation_s:
        return None
    if first_action.satellite_id == second_action.satellite_id:
        if first_derived["access_interval_id"] != second_derived["access_interval_id"]:
            return None
        return "same_satellite_same_pass"
    if not mission.allow_cross_satellite_stereo:
        return None
    return "cross_satellite"


def _target_frame_axes(target_vec: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    up = target_vec / np.linalg.norm(target_vec)
    east = np.cross(np.array([0.0, 0.0, 1.0]), up)
    if float(np.linalg.norm(east)) < 1.0e-9:
        east = np.array([0.0, 1.0, 0.0])
    else:
        east = east / np.linalg.norm(east)
    north = np.cross(up, east)
    north = north / np.linalg.norm(north)
    return east, north, up


def _rotate_ecef_to_target_frame(points: np.ndarray, target_vec: np.ndarray) -> np.ndarray:
    east, north, up = _target_frame_axes(target_vec)
    rotation = np.vstack([east, north, up])
    return np.tensordot(rotation, points, axes=(1, 0))


def _orthographic_globe_image(target_vec: np.ndarray, *, pixels: int = 900) -> np.ndarray:
    target_unit = target_vec / np.linalg.norm(target_vec)
    cache_key = tuple(round(float(value), 6) for value in target_unit)
    cached = _ORTHOGRAPHIC_GLOBE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    texture = _load_world_texture()
    if texture.max(initial=1) > 1:
        texture = texture.astype(float) / 255.0
    else:
        texture = texture.astype(float)

    coords = np.linspace(-1.0, 1.0, pixels)
    xx, yy = np.meshgrid(coords, coords)
    rr2 = xx * xx + yy * yy
    mask = rr2 <= 1.0
    zz = np.zeros_like(xx)
    zz[mask] = np.sqrt(1.0 - rr2[mask])

    east, north, up = _target_frame_axes(target_vec)
    ecef_x = east[0] * xx + north[0] * yy + up[0] * zz
    ecef_y = east[1] * xx + north[1] * yy + up[1] * zz
    ecef_z = east[2] * xx + north[2] * yy + up[2] * zz
    lon = np.arctan2(ecef_y, ecef_x)
    lat = np.arcsin(np.clip(ecef_z, -1.0, 1.0))

    tex_h, tex_w = texture.shape[:2]
    tex_x = ((lon + math.pi) / (2.0 * math.pi) * (tex_w - 1)).astype(int)
    tex_y = ((math.pi / 2.0 - lat) / math.pi * (tex_h - 1)).astype(int)
    globe = np.ones((pixels, pixels, 4), dtype=float)
    globe[:, :, :3] = mpl_colors.to_rgb("#eef3f7")
    globe[:, :, 3] = 0.0
    globe[mask, :3] = texture[tex_y[mask], tex_x[mask], :3]
    globe[mask, 3] = 1.0
    _ORTHOGRAPHIC_GLOBE_CACHE[cache_key] = globe
    return globe


def _draw_product_3d(
    ax: plt.Axes,
    kind: str,
    metric_record: dict[str, Any],
    obs_entries: list[tuple[int, dict[str, Any]]],
) -> None:
    target_def = obs_entries[0][1]["target_def"]
    target_vec = np.asarray(obs_entries[0][1]["target_ecef"], dtype=float)
    radius_m = float(brahe.R_EARTH)
    ax.imshow(
        _orthographic_globe_image(target_vec),
        extent=[-1.0, 1.0, -1.0, 1.0],
        origin="upper",
        interpolation="bilinear",
        zorder=0,
    )
    ax.scatter(
        [0.0],
        [0.0],
        s=38,
        color="#ffffff",
        edgecolor="#111827",
        linewidth=1.0,
        zorder=5,
    )
    ax.text(
        0.022,
        0.022,
        f" {target_def.target_id}",
        color=_THEME["text"],
        fontsize=7.2,
        zorder=6,
    )

    for obs_number, (action_idx, obs_entry) in enumerate(obs_entries):
        color = _OBS_COLORS[obs_number % len(_OBS_COLORS)]
        sat_vec = np.asarray(obs_entry["sat_mid_ecef"], dtype=float)
        sat_xyz = _rotate_ecef_to_target_frame(sat_vec.reshape(3, 1), target_vec).reshape(3)
        sat_x = float(sat_xyz[0] / radius_m)
        sat_y = float(sat_xyz[1] / radius_m)
        ax.plot(
            [sat_x, 0.0],
            [sat_y, 0.0],
            color=color,
            linewidth=0.9,
            alpha=0.72,
            zorder=3,
        )
        ax.scatter(
            [sat_x],
            [sat_y],
            s=14,
            color=color,
            edgecolor="#ffffff",
            linewidth=0.45,
            zorder=4,
        )

    ax.set_xlim(-0.3, 0.3)
    ax.set_ylim(-0.3, 0.3)
    ax.set_aspect("equal", adjustable="box")
    ax.set_axis_off()
    ax.set_facecolor("#eef3f7")
    validity = "valid" if metric_record["valid"] else "invalid"
    ax.set_title(f"{kind.upper()} target-facing Earth view ({validity})", color=_THEME["text"], fontsize=9, pad=2)


def _draw_product_local_view(
    ax: plt.Axes,
    kind: str,
    metric_record: dict[str, Any],
    obs_entries: list[tuple[int, dict[str, Any]]],
) -> None:
    target_def = obs_entries[0][1]["target_def"]
    obs_only = [entry for _, entry in obs_entries]
    _apply_axes_theme(ax, facecolor="#fbfcfe")
    ax.add_patch(
        Circle(
            (0.0, 0.0),
            target_def.aoi_radius_m,
            facecolor="#f8fafc",
            edgecolor=_THEME["target"],
            linewidth=1.0,
            alpha=0.85,
        )
    )
    ax.scatter([0.0], [0.0], marker="x", color=_THEME["target"], s=30, zorder=5)
    for obs_number, (action_idx, obs_entry) in enumerate(obs_entries):
        _draw_observation_footprint(
            ax,
            obs_entry,
            _OBS_COLORS[obs_number % len(_OBS_COLORS)],
            action_idx,
            obs_number,
        )

    xmin, xmax, ymin, ymax = _product_extent(obs_only, target_def.aoi_radius_m)
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("East (m)", color=_THEME["text"], fontsize=8)
    ax.set_ylabel("North (m)", color=_THEME["text"], fontsize=8)
    ax.tick_params(labelsize=7)
    validity = "valid" if metric_record["valid"] else "invalid"
    ax.set_title(f"Ground swath overlap ({validity})", color=_THEME["text"], fontsize=9, pad=2)
    ax.text(
        0.5,
        -0.22,
        "AOI circle; colored bands = image swaths; lines = boresight paths",
        transform=ax.transAxes,
        va="top",
        ha="center",
        fontsize=6.8,
        color=_THEME["muted"],
    )


def _draw_product_look_view(
    ax: plt.Axes,
    kind: str,
    metric_record: dict[str, Any],
    obs_entries: list[tuple[int, dict[str, Any]]],
) -> None:
    target_def = obs_entries[0][1]["target_def"]
    _apply_axes_theme(ax, facecolor="#fbfcfe")
    ax.scatter([0.0], [0.0], marker="x", color=_THEME["target"], s=34, zorder=5)

    max_radius = target_def.aoi_radius_m
    for obs_number, (action_idx, obs_entry) in enumerate(obs_entries):
        color = _OBS_COLORS[obs_number % len(_OBS_COLORS)]
        sat_enz = np.asarray(obs_entry["sat_mid_enz"], dtype=float)
        east_m = float(sat_enz[0])
        north_m = float(sat_enz[1])
        up_m = float(sat_enz[2])
        max_radius = max(max_radius, math.hypot(east_m, north_m))
        ax.plot([0.0, east_m], [0.0, north_m], color=color, linewidth=1.5, alpha=0.85)
        ax.scatter([east_m], [north_m], color=color, edgecolor="white", linewidth=0.8, s=34, zorder=4)
        ax.text(
            east_m,
            north_m,
            f" #{action_idx}\nel {obs_entry['elevation_deg']:.1f} deg\nup {up_m / 1000.0:.0f} km",
            color=color,
            fontsize=7,
            ha="left",
            va="bottom",
        )

    lim = max_radius * 1.15 if max_radius > 0.0 else 1.0
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("East from target (m)", color=_THEME["text"], fontsize=8)
    ax.set_ylabel("North from target (m)", color=_THEME["text"], fontsize=8)
    ax.tick_params(labelsize=7)
    validity = "valid" if metric_record["valid"] else "invalid"
    ax.set_title(f"{kind.upper()} look geometry ({validity})", color=_THEME["text"], fontsize=9, pad=2)


def _product_sort_key(product: dict[str, Any]) -> tuple[bool, float, float, bool]:
    metric_record = product["metric_record"]
    raw_score = float(
        metric_record.get("q_tri_raw", metric_record.get("q_pair_raw", metric_record.get("score", 0.0)))
    )
    return (
        bool(metric_record["valid"]),
        float(metric_record.get("score", 0.0)),
        raw_score,
        product["kind"] == "tri",
    )


def _collect_product_records(
    actions: list[Any],
    satellites: dict[str, Any],
    targets: dict[str, Any],
    mission: Any,
    obs_cache: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    pair_cache: dict[tuple[int, int], dict[str, Any]] = {}
    products: list[dict[str, Any]] = []
    by_target: dict[str, list[int]] = defaultdict(list)
    for action_idx, obs_entry in obs_cache.items():
        by_target[obs_entry["action"].target_id].append(action_idx)

    for _target_id, action_indices in sorted(by_target.items()):
        action_indices = sorted(action_indices)
        for pair in combinations(action_indices, 2):
            stereo_mode = _submitted_pair_mode(mission, obs_cache[pair[0]], obs_cache[pair[1]])
            if stereo_mode is None:
                continue
            pair_record = _pair_metric_record(pair[0], pair[1], obs_cache, mission, stereo_mode)
            pair_cache[tuple(sorted(pair))] = pair_record
            products.append(
                {
                    "kind": "pair",
                    "metric_record": pair_record,
                    "obs_entries": [(pair[0], obs_cache[pair[0]]), (pair[1], obs_cache[pair[1]])],
                }
            )

        for tri in combinations(action_indices, 3):
            edge_modes: list[str] = []
            tri_pair_records: dict[tuple[int, int], dict[str, Any]] = {}
            for edge in combinations(tri, 2):
                edge_key = tuple(sorted(edge))
                stereo_mode = _submitted_pair_mode(mission, obs_cache[edge[0]], obs_cache[edge[1]])
                if stereo_mode is None:
                    break
                edge_modes.append(stereo_mode)
                if edge_key not in pair_cache:
                    pair_cache[edge_key] = _pair_metric_record(edge[0], edge[1], obs_cache, mission, stereo_mode)
                tri_pair_records[edge_key] = pair_cache[edge_key]
            if len(edge_modes) != 3:
                continue
            tri_record = _tri_metric_record(tuple(tri), obs_cache, tri_pair_records, mission, edge_modes)
            products.append(
                {
                    "kind": "tri",
                    "metric_record": tri_record,
                    "obs_entries": [
                        (tri[0], obs_cache[tri[0]]),
                        (tri[1], obs_cache[tri[1]]),
                        (tri[2], obs_cache[tri[2]]),
                    ],
                }
            )

    return sorted(products, key=_product_sort_key, reverse=True)


def _render_product_pages(
    products: list[dict[str, Any]],
    output_dir: Path,
    *,
    case_path: Path,
    solution_file: Path,
    report: Any,
    max_products: int | None,
    products_per_page: int,
) -> list[Path]:
    shown_products = products if max_products is None else products[: max(0, max_products)]
    products_per_page = max(1, products_per_page)
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale_path in output_dir.glob("products_*.png"):
        stale_path.unlink(missing_ok=True)

    if not shown_products:
        pages: list[list[dict[str, Any]]] = [[]]
    else:
        pages = [
            shown_products[start : start + products_per_page]
            for start in range(0, len(shown_products), products_per_page)
        ]

    output_paths: list[Path] = []
    for page_idx, page_products in enumerate(pages, start=1):
        n_rows = max(1, len(page_products))
        fig_height = 1.2 + 3.1 * n_rows
        fig = plt.figure(figsize=(18, fig_height), constrained_layout=True)
        fig.patch.set_facecolor(_THEME["background"])
        gs = fig.add_gridspec(
            n_rows + 1,
            4,
            height_ratios=[0.38, *([1.0] * n_rows)],
            width_ratios=[1.05, 1.05, 1.05, 1.25],
        )

        ax_header = fig.add_subplot(gs[0, :])
        ax_header.axis("off")
        ax_header.text(
            0.0,
            0.95,
            f"Stereo imaging evaluated products: {case_path.name}",
            va="top",
            ha="left",
            fontsize=14,
            fontweight="bold",
            color=_THEME["text"],
        )
        ax_header.text(
            0.0,
            0.35,
            (
                f"Solution: {solution_file.name}  |  Verifier valid: {report.valid}  |  "
                f"Products shown: {len(shown_products)}/{len(products)}  |  Page {page_idx}/{len(pages)}"
            ),
            va="top",
            ha="left",
            fontsize=10,
            color=_THEME["muted"],
        )

        if not page_products:
            ax_empty = fig.add_subplot(gs[1, :])
            ax_empty.axis("off")
            ax_empty.text(
                0.5,
                0.5,
                "No evaluated pair or tri-stereo products found in this solution.",
                ha="center",
                va="center",
                fontsize=12,
                color=_THEME["muted"],
            )
        else:
            for row_idx, product in enumerate(page_products, start=1):
                kind = product["kind"]
                metric_record = product["metric_record"]
                obs_entries = product["obs_entries"]
                ax_3d = fig.add_subplot(gs[row_idx, 0])
                _draw_product_3d(ax_3d, kind, metric_record, obs_entries)

                ax_local = fig.add_subplot(gs[row_idx, 1])
                _draw_product_local_view(ax_local, kind, metric_record, obs_entries)

                ax_look = fig.add_subplot(gs[row_idx, 2])
                _draw_product_look_view(ax_look, kind, metric_record, obs_entries)

                ax_text = fig.add_subplot(gs[row_idx, 3])
                ax_text.axis("off")
                validity_color = _THEME["valid"] if metric_record["valid"] else _THEME["invalid"]
                ax_text.text(
                    0.0,
                    1.0,
                    "\n".join(_product_metric_lines(kind, metric_record, obs_entries)),
                    va="top",
                    ha="left",
                    fontsize=8.2,
                    color=_THEME["text"],
                    family="monospace",
                    linespacing=1.25,
                    bbox=dict(
                        boxstyle="round,pad=0.45",
                        facecolor="#fbfcfe",
                        edgecolor=validity_color,
                        linewidth=1.2,
                    ),
                )

        out_path = output_dir / f"products_{page_idx:03d}.png"
        fig.savefig(out_path, dpi=160, bbox_inches="tight")
        plt.close(fig)
        output_paths.append(out_path)
    return output_paths


def render_products(
    case_dir: str | Path,
    solution_path: str | Path,
    out_dir: str | Path | None = None,
    *,
    max_products: int | None = 24,
    products_per_page: int = 4,
) -> list[Path]:
    case_path = Path(case_dir)
    solution_file = Path(solution_path)
    mission, satellites, targets = load_case(case_path)
    actions = load_solution_actions(solution_file, case_path.name)
    report = verify_solution(case_path, solution_file)
    output_dir = _products_output_dir(case_path, out_dir)

    legacy_output_dir = _DEFAULT_OUTPUT_ROOT / case_path.name / "batch"
    cleanup_dirs = {output_dir, legacy_output_dir}
    for cleanup_dir in cleanup_dirs:
        for pattern in ("pair__*.png", "tri__*.png", "pair__*.html", "tri__*.html"):
            for stale_path in cleanup_dir.glob(pattern):
                stale_path.unlink(missing_ok=True)
        for stale_path in (cleanup_dir / "manifest.json", cleanup_dir / "plotly.min.js"):
            stale_path.unlink(missing_ok=True)

    derived_by_idx = _derived_by_action_index(report, actions, satellites, targets)
    sf_sats = _satellite_cache(satellites)
    target_ecef = {target_id: _target_ecef_m(target) for target_id, target in targets.items()}
    obs_cache = _observation_cache(actions, derived_by_idx, satellites, targets, sf_sats, target_ecef)
    products = _collect_product_records(actions, satellites, targets, mission, obs_cache)
    return _render_product_pages(
        products,
        output_dir,
        case_path=case_path,
        solution_file=solution_file,
        report=report,
        max_products=max_products,
        products_per_page=products_per_page,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stereo imaging visualizer with overview and evaluated-product rendering.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    overview_parser = subparsers.add_parser("overview", help="Render a case overview PNG.")
    overview_parser.add_argument(
        "--case-dir",
        required=True,
        help="Path to dataset/cases/<case_id>",
    )
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
    overview_parser.add_argument(
        "--max-ground-tracks",
        type=int,
        default=4,
        help="Maximum representative satellite tracks to draw; use 0 to hide tracks (default: 4)",
    )

    def add_products_args(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument(
            "--case-dir",
            required=True,
            help="Path to dataset/cases/<case_id>",
        )
        command_parser.add_argument(
            "--solution-path",
            required=True,
            help="Path to solution JSON",
        )
        command_parser.add_argument(
            "--out-dir",
            type=Path,
            default=None,
            help="Directory for products_*.png pages (default: benchmarks/stereo_imaging/visualizer/plots/<case>/products)",
        )
        command_parser.add_argument(
            "--max-products",
            type=int,
            default=24,
            help="Maximum evaluated products to render across all pages (default: 24)",
        )
        command_parser.add_argument(
            "--products-per-page",
            type=int,
            default=4,
            help="Maximum evaluated products per PNG page (default: 4)",
        )

    products_parser = subparsers.add_parser("products", help="Render evaluated stereo product PNG pages.")
    add_products_args(products_parser)

    args = parser.parse_args(argv)

    if args.command == "overview":
        out_path = _overview_output_path(Path(args.case_dir), args.out_path)
        render_overview(
            args.case_dir,
            out_path,
            ground_track_step_s=args.ground_track_step_s,
            max_ground_tracks=args.max_ground_tracks,
        )
        print(f"Wrote overview image to {out_path}")
        return 0

    output_paths = render_products(
        args.case_dir,
        args.solution_path,
        args.out_dir,
        max_products=args.max_products,
        products_per_page=args.products_per_page,
    )
    print(f"Wrote {len(output_paths)} product image page(s) to {output_paths[0].parent}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
