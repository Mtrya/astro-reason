"""Development visualizer for the regional_coverage benchmark."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import brahe
import matplotlib
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from brahe.plots.texture_utils import load_earth_texture
from matplotlib.lines import Line2D
from shapely.geometry import Polygon as ShapelyPolygon

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from ..verifier import (
    GridSample,
    ParsedAction,
    RegionGrid,
    _build_propagators,
    _datetime_to_epoch,
    _ensure_brahe_ready,
    _inspect_solution,
    _iso_z,
    load_case,
)


_VISUALIZER_DIR = Path(__file__).resolve().parent
_DEFAULT_OUTPUT_ROOT = _VISUALIZER_DIR / "plots"
_EARTH_RADIUS_M = float(brahe.R_EARTH)
_WORLD_TEXTURE_EXTENT = (-180.0, 180.0, -90.0, 90.0)
_WORLD_TEXTURE: np.ndarray | None = None
_EARTH_TRACE_CACHE: dict[str, go.BaseTraceType] = {}
_COLOR_CYCLE = [
    "#f97316",
    "#06b6d4",
    "#10b981",
    "#8b5cf6",
    "#ef4444",
    "#eab308",
    "#14b8a6",
    "#ec4899",
]
_REGION_COLORS = [
    "#0f766e",
    "#7c3aed",
    "#2563eb",
    "#b45309",
    "#be123c",
    "#047857",
]
_SAMPLE_STATE_COLORS = {
    "selected": "#ef4444",
    "covered_other": "#f59e0b",
    "uncovered": "#94a3b8",
}
_THEME = {
    "background": "#ffffff",
    "panel": "#f7f8fa",
    "grid": "#d5dbe3",
    "axis": "#39424e",
    "text": "#1f2933",
    "muted": "#52606d",
}


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _serialize_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sanitize_solution_stem(solution_path: Path) -> str:
    stem = solution_path.stem.strip().replace(" ", "_")
    filtered = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem)
    return filtered or "solution"


def _overview_output_path(case_dir: Path, out_path: Path | None) -> Path:
    if out_path is not None:
        return out_path
    return _DEFAULT_OUTPUT_ROOT / case_dir.name / "overview.png"


def _inspect_output_dir(case_dir: Path, solution_path: Path, out_dir: Path | None) -> Path:
    if out_dir is not None:
        return out_dir
    return _DEFAULT_OUTPUT_ROOT / case_dir.name / _sanitize_solution_stem(solution_path)


def _lonlat_to_ecef_m(lon_deg: float, lat_deg: float, alt_m: float = 0.0) -> np.ndarray:
    geodetic = np.asarray([lon_deg, lat_deg, alt_m], dtype=float)
    return np.asarray(
        brahe.position_geodetic_to_ecef(geodetic, brahe.AngleFormat.DEGREES),
        dtype=float,
    )


def _lonlat_series_to_ecef(
    lonlat: list[tuple[float, float]], *, alt_m: float = 0.0
) -> tuple[list[float], list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for lon_deg, lat_deg in lonlat:
        ecef = _lonlat_to_ecef_m(lon_deg, lat_deg, alt_m=alt_m)
        xs.append(float(ecef[0]))
        ys.append(float(ecef[1]))
        zs.append(float(ecef[2]))
    return xs, ys, zs


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


def _earth_surface_trace() -> go.BaseTraceType:
    cached = _EARTH_TRACE_CACHE.get("default")
    if cached is not None:
        return cached

    radius_m = _EARTH_RADIUS_M
    try:
        texture = _load_world_texture()
    except FileNotFoundError:
        lon_values = np.linspace(-180.0, 180.0, 120)
        lat_values = np.linspace(-90.0, 90.0, 60)
        lon_grid, lat_grid = np.meshgrid(lon_values, lat_values)
        lon_rad = np.radians(lon_grid)
        lat_rad = np.radians(lat_grid)
        x = radius_m * np.cos(lat_rad) * np.cos(lon_rad)
        y = radius_m * np.cos(lat_rad) * np.sin(lon_rad)
        z = radius_m * np.sin(lat_rad)
        surface_color = np.sin(lat_rad)
        trace = go.Surface(
            x=x,
            y=y,
            z=z,
            surfacecolor=surface_color,
            colorscale=[
                [0.0, "#0f172a"],
                [0.35, "#1d4ed8"],
                [0.5, "#0ea5e9"],
                [0.7, "#38bdf8"],
                [1.0, "#e0f2fe"],
            ],
            showscale=False,
            opacity=0.92,
            hoverinfo="skip",
            name="Earth",
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
        opacity=0.97,
    )
    _EARTH_TRACE_CACHE["default"] = trace
    return trace


def _sample_satellite_positions_ecef(
    propagator: brahe.SGPPropagator,
    start_time: datetime,
    end_time: datetime,
    *,
    step_s: float,
) -> list[np.ndarray]:
    points: list[np.ndarray] = []
    current = start_time
    step = timedelta(seconds=step_s)
    while current <= end_time:
        epoch = _datetime_to_epoch(current)
        state_ecef = np.asarray(propagator.state_ecef(epoch), dtype=float).reshape(6)
        points.append(state_ecef[:3].copy())
        current += step
    if not points or current - step < end_time:
        epoch = _datetime_to_epoch(end_time)
        state_ecef = np.asarray(propagator.state_ecef(epoch), dtype=float).reshape(6)
        points.append(state_ecef[:3].copy())
    return points


def _sample_ground_track_lonlat(
    propagator: brahe.SGPPropagator,
    start_time: datetime,
    end_time: datetime,
    *,
    step_s: float,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    current = start_time
    step = timedelta(seconds=step_s)
    while current <= end_time:
        epoch = _datetime_to_epoch(current)
        state_ecef = np.asarray(propagator.state_ecef(epoch), dtype=float).reshape(6)
        lon_deg, lat_deg, _ = brahe.position_ecef_to_geodetic(
            state_ecef[:3], brahe.AngleFormat.DEGREES
        )
        points.append((float(lon_deg), float(lat_deg)))
        current += step
    if not points or current - step < end_time:
        epoch = _datetime_to_epoch(end_time)
        state_ecef = np.asarray(propagator.state_ecef(epoch), dtype=float).reshape(6)
        lon_deg, lat_deg, _ = brahe.position_ecef_to_geodetic(
            state_ecef[:3], brahe.AngleFormat.DEGREES
        )
        points.append((float(lon_deg), float(lat_deg)))
    return points


def _sample_ground_track_segments(
    propagator: brahe.SGPPropagator,
    start_time: datetime,
    end_time: datetime,
    *,
    step_s: float,
) -> list[tuple[list[float], list[float]]]:
    lonlat = _sample_ground_track_lonlat(
        propagator,
        start_time,
        end_time,
        step_s=step_s,
    )
    longitudes = [point[0] for point in lonlat]
    latitudes = [point[1] for point in lonlat]
    return brahe.split_ground_track_at_antimeridian(longitudes, latitudes)


def _selected_actions(
    actions: list[ParsedAction], action_indices: list[int] | None
) -> list[ParsedAction]:
    if not action_indices:
        return actions
    allowed = set(action_indices)
    return [action for action in actions if action.index in allowed]


def _add_region_traces_3d(
    fig: go.Figure, case: Any, *, row: int | None = None, col: int | None = None
) -> None:
    for index, region in enumerate(case.regions.values()):
        xs, ys, zs = _lonlat_series_to_ecef(list(region.polygon_lonlat))
        trace = go.Scatter3d(
            x=xs,
            y=ys,
            z=zs,
            mode="lines",
            line=dict(color=_REGION_COLORS[index % len(_REGION_COLORS)], width=5),
            name=f"Region {region.region_id}",
            hovertemplate=(
                f"region={region.region_id}<br>weight={region.weight:.3f}<extra></extra>"
            ),
            showlegend=True,
        )
        if row is None or col is None:
            fig.add_trace(trace)
        else:
            fig.add_trace(trace, row=row, col=col)


def _add_region_traces_2d(fig: go.Figure, case: Any) -> None:
    for index, region in enumerate(case.regions.values()):
        lons = [vertex[0] for vertex in region.polygon_lonlat]
        lats = [vertex[1] for vertex in region.polygon_lonlat]
        fig.add_trace(
            go.Scattergl(
                x=lons,
                y=lats,
                mode="lines",
                line=dict(color=_REGION_COLORS[index % len(_REGION_COLORS)], width=3),
                name=f"Region {region.region_id}",
                hovertemplate=f"region={region.region_id}<extra></extra>",
                showlegend=False,
            ),
            row=1,
            col=2,
        )


def _add_coverage_samples_2d(
    fig: go.Figure,
    region_grids: dict[str, RegionGrid],
    selected_actions: list[ParsedAction],
    all_actions: list[ParsedAction],
) -> None:
    selected_sample_ids = {
        sample_id for action in selected_actions for sample_id in action.covered_sample_ids
    }
    all_covered_sample_ids = {
        sample_id for action in all_actions for sample_id in action.covered_sample_ids
    }
    by_state: dict[str, list[GridSample]] = defaultdict(list)
    for region_grid in region_grids.values():
        for sample in region_grid.samples:
            if sample.sample_id in selected_sample_ids:
                by_state["selected"].append(sample)
            elif sample.sample_id in all_covered_sample_ids:
                by_state["covered_other"].append(sample)
            else:
                by_state["uncovered"].append(sample)
    for state, samples in by_state.items():
        if not samples:
            continue
        fig.add_trace(
            go.Scattergl(
                x=[sample.longitude_deg for sample in samples],
                y=[sample.latitude_deg for sample in samples],
                mode="markers",
                marker=dict(
                    color=_SAMPLE_STATE_COLORS[state],
                    size=6 if state == "selected" else 4,
                    opacity=0.8 if state == "selected" else 0.55,
                ),
                name=f"Samples: {state}",
                hovertemplate=(
                    "sample=%{customdata[0]}<br>"
                    "weight_m2=%{customdata[1]:.1f}<extra></extra>"
                ),
                customdata=[[sample.sample_id, sample.weight_m2] for sample in samples],
                showlegend=False,
            ),
            row=1,
            col=2,
        )


def _add_action_traces(
    fig: go.Figure,
    actions: list[ParsedAction],
    propagators: dict[str, brahe.SGPPropagator],
    *,
    orbit_window_s: float,
) -> None:
    for ordinal, action in enumerate(actions):
        color = _COLOR_CYCLE[ordinal % len(_COLOR_CYCLE)]
        legend_name = f"Action {action.index}"
        if action.accepted_for_geometry and action.sample_center_hits_ecef_m:
            inner_hits = action.sample_inner_hits_ecef_m
            outer_hits = action.sample_outer_hits_ecef_m
            for segment_index in range(len(inner_hits) - 1):
                vertices = np.asarray(
                    [
                        inner_hits[segment_index],
                        outer_hits[segment_index],
                        outer_hits[segment_index + 1],
                        inner_hits[segment_index + 1],
                    ],
                    dtype=float,
                )
                fig.add_trace(
                    go.Mesh3d(
                        x=vertices[:, 0],
                        y=vertices[:, 1],
                        z=vertices[:, 2],
                        i=[0, 0],
                        j=[1, 2],
                        k=[2, 3],
                        color=color,
                        opacity=0.34,
                        flatshading=True,
                        hovertemplate=(
                            f"action={action.index}<br>"
                            f"segment={segment_index}<br>"
                            f"satellite={action.satellite_id}<extra></extra>"
                        ),
                        name=legend_name,
                        showlegend=segment_index == 0,
                    ),
                    row=1,
                    col=1,
                )
            xs = [float(point[0]) for point in action.sample_center_hits_ecef_m]
            ys = [float(point[1]) for point in action.sample_center_hits_ecef_m]
            zs = [float(point[2]) for point in action.sample_center_hits_ecef_m]
            fig.add_trace(
                go.Scatter3d(
                    x=xs,
                    y=ys,
                    z=zs,
                    mode="lines",
                    line=dict(color=color, width=6),
                    name=f"{legend_name} centerline",
                    hovertemplate=(
                        f"action={action.index}<br>"
                        f"satellite={action.satellite_id}<extra></extra>"
                    ),
                    showlegend=False,
                ),
                row=1,
                col=1,
            )
            for polygon_index, polygon in enumerate(action.segment_polygons):
                coords = list(polygon.exterior.coords)
                fig.add_trace(
                    go.Scattergl(
                        x=[coord[0] for coord in coords],
                        y=[coord[1] for coord in coords],
                        mode="lines",
                        fill="toself",
                        line=dict(color=color, width=2),
                        fillcolor=f"rgba{(*_hex_to_rgb(color), 0.24)}",
                        name=f"{legend_name} footprint",
                        hovertemplate=(
                            f"action={action.index}<br>"
                            f"segment={polygon_index}<extra></extra>"
                        ),
                        showlegend=False,
                    ),
                    row=1,
                    col=2,
                )
            fig.add_trace(
                go.Scattergl(
                    x=[point[0] for point in action.derived_centerline_lonlat],
                    y=[point[1] for point in action.derived_centerline_lonlat],
                    mode="lines",
                    line=dict(color=color, width=2),
                    name=f"{legend_name} centerline",
                    hovertemplate=(
                        f"action={action.index}<br>"
                        f"satellite={action.satellite_id}<extra></extra>"
                    ),
                    showlegend=False,
                ),
                row=1,
                col=2,
            )
        if action.accepted_for_schedule:
            action_start = action.start_time - timedelta(seconds=orbit_window_s)
            action_end = (action.end_time or action.start_time) + timedelta(seconds=orbit_window_s)
            propagator = propagators[action.satellite_id]
            orbit_points = _sample_satellite_positions_ecef(
                propagator,
                action_start,
                action_end,
                step_s=max(5.0, orbit_window_s / 40.0),
            )
            fig.add_trace(
                go.Scatter3d(
                    x=[float(point[0]) for point in orbit_points],
                    y=[float(point[1]) for point in orbit_points],
                    z=[float(point[2]) for point in orbit_points],
                    mode="lines",
                    line=dict(color=color, width=3, dash="dot"),
                    name=f"{legend_name} orbit",
                    hovertemplate=(
                        f"action={action.index}<br>"
                        f"orbit segment<extra></extra>"
                    ),
                    showlegend=False,
                ),
                row=1,
                col=1,
            )
            if action.sample_satellite_positions_ecef_m:
                start_marker = action.sample_satellite_positions_ecef_m[0]
                end_marker = action.sample_satellite_positions_ecef_m[-1]
                for label, marker_symbol, point in (
                    ("start", "diamond", start_marker),
                    ("end", "circle", end_marker),
                ):
                    fig.add_trace(
                        go.Scatter3d(
                            x=[float(point[0])],
                            y=[float(point[1])],
                            z=[float(point[2])],
                            mode="markers",
                            marker=dict(size=3, color=color, symbol=marker_symbol),
                            name=f"{legend_name} {label}",
                            hovertemplate=(
                                f"action={action.index}<br>{label}={_iso_z(action.start_time if label == 'start' else action.end_time or action.start_time)}<extra></extra>"
                            ),
                            showlegend=False,
                        ),
                        row=1,
                        col=1,
                    )


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _metrics_annotation_text(report: dict[str, Any], selected_actions: list[ParsedAction]) -> str:
    metrics = report["metrics"]
    violations = report["violations"]
    selected_indexes = [str(action.index) for action in selected_actions]
    lines = [
        f"<b>Verifier valid:</b> {'yes' if report['valid'] else 'no'}",
        f"<b>Coverage ratio:</b> {metrics.get('coverage_ratio', 0.0):.6f}",
        f"<b>Covered weight:</b> {metrics.get('covered_weight_m2_equivalent', 0.0):.1f}",
        f"<b>Num actions:</b> {metrics.get('num_actions', 0)}",
        f"<b>Total slew angle:</b> {metrics.get('total_slew_angle_deg', 0.0):.3f} deg",
        f"<b>Min battery:</b> {metrics.get('min_battery_wh', 0.0):.3f} Wh",
        f"<b>Selected actions:</b> {', '.join(selected_indexes) if selected_indexes else '(none)'}",
    ]
    if violations:
        lines.append("<b>Violations:</b>")
        lines.extend(violation for violation in violations[:8])
        if len(violations) > 8:
            lines.append(f"... and {len(violations) - 8} more")
    return "<br>".join(lines)


def _region_area_summary(case: Any) -> str:
    total_samples = sum(len(region_grid.samples) for region_grid in case.region_grids.values())
    total_weight = sum(region_grid.total_weight_m2 for region_grid in case.region_grids.values())
    return (
        f"<b>Case:</b> {case.manifest.case_id}<br>"
        f"<b>Satellites:</b> {len(case.satellites)}<br>"
        f"<b>Regions:</b> {len(case.regions)}<br>"
        f"<b>Grid samples:</b> {total_samples}<br>"
        f"<b>Total region area:</b> {total_weight / 1_000_000.0:.1f} km^2"
    )


def _overview_summary_lines(case: Any, *, shown_ground_tracks: int) -> list[str]:
    total_samples = sum(len(region_grid.samples) for region_grid in case.region_grids.values())
    total_weight_m2 = sum(region_grid.total_weight_m2 for region_grid in case.region_grids.values())
    lines = [
        f"Case: {case.manifest.case_id}",
        f"Horizon: {_utc_iso(case.manifest.horizon_start)} to {_utc_iso(case.manifest.horizon_end)}",
        "",
        f"Satellites ({len(case.satellites)}):",
        *[f"  - {satellite_id}" for satellite_id in case.satellites],
        "",
        f"Regions ({len(case.regions)}):",
    ]
    for region_grid in case.region_grids.values():
        lines.append(
            f"  - {region_grid.region.region_id}: {region_grid.total_weight_m2 / 1_000_000.0:.1f} km^2"
        )
    lines.extend(
        [
            "",
            f"Coverage samples: {total_samples}",
            f"Sample spacing: {case.manifest.sample_spacing_m:.0f} m",
            f"Total region area: {total_weight_m2 / 1_000_000.0:.1f} km^2",
            f"Ground tracks shown: {shown_ground_tracks} / {len(case.satellites)}",
        ]
    )
    return lines


def _write_figure_html(fig: go.Figure, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(out_path, include_plotlyjs="directory", full_html=True)
    return out_path


def _region_polygon(region: Any) -> ShapelyPolygon:
    return ShapelyPolygon(region.polygon_lonlat)


def _actions_for_region(region: Any, actions: list[ParsedAction]) -> list[ParsedAction]:
    region_poly = _region_polygon(region)
    relevant: list[ParsedAction] = []
    for action in actions:
        if region.region_id in action.covered_region_ids:
            relevant.append(action)
            continue
        if not action.accepted_for_geometry:
            continue
        if any(segment.intersects(region_poly) for segment in action.segment_polygons):
            relevant.append(action)
    return relevant


def _sample_states_for_region(
    region_grid: RegionGrid,
    selected_actions: list[ParsedAction],
    all_actions: list[ParsedAction],
) -> dict[str, list[GridSample]]:
    selected_ids = {
        sample_id
        for action in selected_actions
        if region_grid.region.region_id in action.covered_region_ids
        for sample_id in action.covered_sample_ids
    }
    covered_other_ids = {
        sample_id
        for action in all_actions
        if region_grid.region.region_id in action.covered_region_ids
        for sample_id in action.covered_sample_ids
    } - selected_ids

    states: dict[str, list[GridSample]] = defaultdict(list)
    for sample in region_grid.samples:
        if sample.sample_id in selected_ids:
            states["selected"].append(sample)
        elif sample.sample_id in covered_other_ids:
            states["covered_other"].append(sample)
        else:
            states["uncovered"].append(sample)
    return states


def _zoom_limits(region: Any, actions: list[ParsedAction]) -> tuple[float, float, float, float]:
    lons = [vertex[0] for vertex in region.polygon_lonlat]
    lats = [vertex[1] for vertex in region.polygon_lonlat]
    for action in actions:
        if not action.accepted_for_geometry:
            continue
        for polygon in action.segment_polygons:
            if not polygon.intersects(_region_polygon(region)):
                continue
            min_lon, min_lat, max_lon, max_lat = polygon.bounds
            lons.extend([min_lon, max_lon])
            lats.extend([min_lat, max_lat])

    min_lon = min(lons)
    max_lon = max(lons)
    min_lat = min(lats)
    max_lat = max(lats)
    lon_span = max(max_lon - min_lon, 0.2)
    lat_span = max(max_lat - min_lat, 0.2)
    pad_lon = max(0.08, 0.15 * lon_span)
    pad_lat = max(0.08, 0.15 * lat_span)
    return min_lon - pad_lon, max_lon + pad_lon, min_lat - pad_lat, max_lat + pad_lat


def _render_region_zoom_png(
    case: Any,
    selected_actions: list[ParsedAction],
    all_actions: list[ParsedAction],
    out_path: Path,
) -> Path:
    regions = list(case.region_grids.values())
    num_regions = len(regions)
    cols = 2 if num_regions > 1 else 1
    rows = math.ceil(num_regions / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(7.2 * cols, 5.2 * rows), squeeze=False)
    fig.patch.set_facecolor(_THEME["background"])
    axes_flat = list(axes.flat)

    for axis, region_grid in zip(axes_flat, regions, strict=False):
        _apply_axes_theme(axis, facecolor="#fbfcfe")
        region = region_grid.region
        region_poly = _region_polygon(region)
        region_actions = _actions_for_region(region, selected_actions if selected_actions else all_actions)
        lons = [vertex[0] for vertex in region.polygon_lonlat]
        lats = [vertex[1] for vertex in region.polygon_lonlat]
        region_color = _REGION_COLORS[regions.index(region_grid) % len(_REGION_COLORS)]
        axis.fill(lons, lats, facecolor=region_color, edgecolor=region_color, linewidth=2.2, alpha=0.16, zorder=1)
        axis.plot(lons, lats, color=region_color, linewidth=2.3, alpha=0.95, zorder=2)

        states = _sample_states_for_region(region_grid, selected_actions, all_actions)
        for state, samples in states.items():
            if not samples:
                continue
            axis.scatter(
                [sample.longitude_deg for sample in samples],
                [sample.latitude_deg for sample in samples],
                s=16 if state == "selected" else 9,
                c=_SAMPLE_STATE_COLORS[state],
                alpha=0.82 if state == "selected" else 0.45,
                linewidths=0.0,
                zorder=3,
            )

        for ordinal, action in enumerate(region_actions):
            color = _COLOR_CYCLE[ordinal % len(_COLOR_CYCLE)]
            for polygon in action.segment_polygons:
                if not polygon.intersects(region_poly):
                    continue
                coords = list(polygon.exterior.coords)
                axis.fill(
                    [coord[0] for coord in coords],
                    [coord[1] for coord in coords],
                    facecolor=color,
                    edgecolor=color,
                    linewidth=1.4,
                    alpha=0.14,
                    zorder=4,
                )
                axis.plot(
                    [coord[0] for coord in coords],
                    [coord[1] for coord in coords],
                    color=color,
                    linewidth=1.4,
                    alpha=0.95,
                    zorder=5,
                )
            if action.derived_centerline_lonlat:
                axis.plot(
                    [point[0] for point in action.derived_centerline_lonlat],
                    [point[1] for point in action.derived_centerline_lonlat],
                    color=color,
                    linewidth=1.6,
                    alpha=0.95,
                    zorder=6,
                )

        xmin, xmax, ymin, ymax = _zoom_limits(region, region_actions)
        axis.set_xlim(xmin, xmax)
        axis.set_ylim(ymin, ymax)
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlabel("Longitude (deg)", color=_THEME["text"])
        axis.set_ylabel("Latitude (deg)", color=_THEME["text"])
        axis.set_title(
            (
                f"{region.region_id}  "
                f"({region_grid.total_weight_m2 / 1_000_000.0:.0f} km², "
                f"{len(region_actions)} strip{'s' if len(region_actions) != 1 else ''})"
            ),
            color=_THEME["text"],
            fontsize=11,
            fontweight="bold",
        )

    for axis in axes_flat[num_regions:]:
        axis.axis("off")

    legend_handles = [
        Line2D([0], [0], color=_REGION_COLORS[0], linewidth=2.2, label="region"),
        Line2D([0], [0], color=_COLOR_CYCLE[0], linewidth=1.6, label="strip centerline"),
        Line2D([0], [0], color=_COLOR_CYCLE[0], linewidth=4.0, alpha=0.2, label="strip footprint"),
        Line2D([0], [0], marker="o", linestyle="None", markersize=5, markerfacecolor=_SAMPLE_STATE_COLORS["selected"], markeredgewidth=0, label="selected covered sample"),
        Line2D([0], [0], marker="o", linestyle="None", markersize=5, markerfacecolor=_SAMPLE_STATE_COLORS["covered_other"], markeredgewidth=0, label="covered by other action"),
        Line2D([0], [0], marker="o", linestyle="None", markersize=5, markerfacecolor=_SAMPLE_STATE_COLORS["uncovered"], markeredgewidth=0, label="uncovered sample"),
    ]
    fig.legend(
        handles=legend_handles,
        loc="lower center",
        ncol=3,
        frameon=False,
        fontsize=9,
        bbox_to_anchor=(0.5, 0.01),
    )
    fig.suptitle(
        f"Regional Coverage Zoom: {case.manifest.case_id}",
        fontsize=14,
        color=_THEME["text"],
        fontweight="bold",
        y=0.98,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.9, bottom=0.12, hspace=0.28, wspace=0.2)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def render_overview(
    case_dir: str | Path,
    out_path: str | Path | None = None,
    *,
    ground_track_step_s: float = 300.0,
    max_ground_tracks: int | None = None,
) -> Path:
    _ensure_brahe_ready()
    case_path = Path(case_dir)
    case = load_case(case_path)
    propagators = _build_propagators(case)
    output_path = _overview_output_path(case_path, Path(out_path) if out_path is not None else None)
    fig = plt.figure(figsize=(13.5, 7.5))
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
        f"Regional Coverage Case Overview: {case.manifest.case_id}",
        color=_THEME["text"],
        fontsize=14,
        fontweight="bold",
    )

    satellite_items = sorted(propagators.items(), key=lambda item: item[0])
    if max_ground_tracks is not None:
        satellite_items = satellite_items[: max(0, max_ground_tracks)]

    track_handles: list[Line2D] = []
    for index, (satellite_id, propagator) in enumerate(satellite_items):
        color = _COLOR_CYCLE[index % len(_COLOR_CYCLE)]
        track_handles.append(Line2D([0], [0], color=color, linewidth=2.0, label=satellite_id))
        for lon_seg, lat_seg in _sample_ground_track_segments(
            propagator,
            case.manifest.horizon_start,
            case.manifest.horizon_end,
            step_s=ground_track_step_s,
        ):
            ax_map.plot(
                lon_seg,
                lat_seg,
                color=color,
                linewidth=1.4,
                alpha=0.72,
                zorder=2,
            )

    region_handles: list[Line2D] = []
    for index, region in enumerate(case.regions.values()):
        color = _REGION_COLORS[index % len(_REGION_COLORS)]
        region_handles.append(
            Line2D([0], [0], color=color, linewidth=2.8, label=region.region_id)
        )
        lons = [vertex[0] for vertex in region.polygon_lonlat]
        lats = [vertex[1] for vertex in region.polygon_lonlat]
        ax_map.fill(
            lons,
            lats,
            facecolor=color,
            edgecolor=color,
            linewidth=2.0,
            alpha=0.18,
            zorder=3,
        )
        ax_map.plot(
            lons,
            lats,
            color=color,
            linewidth=2.2,
            alpha=0.95,
            zorder=4,
        )

    track_legend = ax_map.legend(
        handles=track_handles,
        title="Ground tracks",
        loc="lower left",
        bbox_to_anchor=(0.0, -0.26),
        ncol=max(1, min(2, len(track_handles))),
        fontsize=9,
        title_fontsize=9,
        frameon=False,
    )
    ax_map.add_artist(track_legend)
    ax_map.legend(
        handles=region_handles,
        title="Regions",
        loc="lower right",
        bbox_to_anchor=(1.0, -0.26),
        ncol=max(1, min(2, len(region_handles))),
        fontsize=9,
        title_fontsize=9,
        frameon=False,
    )

    ax_summary.axis("off")
    ax_summary.set_facecolor(_THEME["panel"])
    ax_summary.text(
        0.0,
        1.0,
        "\n".join(_overview_summary_lines(case, shown_ground_tracks=len(satellite_items))),
        va="top",
        ha="left",
        fontsize=10,
        color=_THEME["text"],
        family="monospace",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.93, bottom=0.2, wspace=0.22)
    fig.savefig(output_path, dpi=130)
    plt.close(fig)
    return output_path


def _build_inspection_figure(
    report: dict[str, Any],
    case: Any,
    selected_actions: list[ParsedAction],
    all_actions: list[ParsedAction],
    propagators: dict[str, brahe.SGPPropagator],
    *,
    orbit_window_s: float,
    title: str,
) -> go.Figure:
    fig = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "scene"}, {"type": "xy"}]],
        column_widths=[0.58, 0.42],
        horizontal_spacing=0.04,
        subplot_titles=("3D Earth and pushbrooms", "Coverage grid and strip footprints"),
    )
    fig.add_trace(_earth_surface_trace(), row=1, col=1)
    _add_region_traces_3d(fig, case, row=1, col=1)
    _add_region_traces_2d(fig, case)
    _add_action_traces(fig, selected_actions, propagators, orbit_window_s=orbit_window_s)
    _add_coverage_samples_2d(fig, case.region_grids, selected_actions, all_actions)
    fig.update_scenes(
        aspectmode="data",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        zaxis=dict(visible=False),
        camera=dict(eye=dict(x=1.45, y=1.5, z=1.1)),
        bgcolor="#050816",
        row=1,
        col=1,
    )
    fig.update_xaxes(title_text="Longitude [deg]", row=1, col=2, showgrid=True, gridcolor="#cbd5e1")
    fig.update_yaxes(title_text="Latitude [deg]", row=1, col=2, showgrid=True, gridcolor="#cbd5e1")
    fig.update_layout(
        title=title,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        margin=dict(l=10, r=310, t=65, b=10),
        legend=dict(
            x=0.01,
            y=0.99,
            bgcolor="rgba(255,255,255,0.82)",
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
                bordercolor="#cbd5e1",
                borderwidth=1,
                borderpad=8,
                bgcolor="#f8fafc",
                font=dict(size=12, color="#0f172a"),
                text=_metrics_annotation_text(report, selected_actions),
            )
        ],
    )
    return fig


def render_inspection(
    case_dir: str | Path,
    solution_path: str | Path,
    out_dir: str | Path | None = None,
    *,
    action_indices: list[int] | None = None,
    orbit_window_s: float = 300.0,
) -> Path:
    case_path = Path(case_dir)
    solution_file = Path(solution_path)
    artifacts = _inspect_solution(case_path, solution_file)
    report = {
        "valid": not artifacts.violations,
        "metrics": artifacts.metrics,
        "violations": artifacts.violations,
        "diagnostics": artifacts.diagnostics,
    }
    output_dir = _inspect_output_dir(case_path, solution_file, Path(out_dir) if out_dir is not None else None)
    output_dir.mkdir(parents=True, exist_ok=True)

    selected = _selected_actions(artifacts.parsed_actions, action_indices)
    summary_figure = _build_inspection_figure(
        report,
        artifacts.case,
        selected,
        artifacts.parsed_actions,
        artifacts.propagators,
        orbit_window_s=orbit_window_s,
        title=f"regional_coverage inspection: {artifacts.case.manifest.case_id}",
    )
    summary_path = _write_figure_html(summary_figure, output_dir / "summary.html")
    region_zoom_path = _render_region_zoom_png(
        artifacts.case,
        selected,
        artifacts.parsed_actions,
        output_dir / "region_zoom.png",
    )

    action_pages: dict[int, Path] = {}
    for action in selected:
        figure = _build_inspection_figure(
            report,
            artifacts.case,
            [action],
            artifacts.parsed_actions,
            artifacts.propagators,
            orbit_window_s=orbit_window_s,
            title=f"regional_coverage action {action.index}: {artifacts.case.manifest.case_id}",
        )
        action_pages[action.index] = _write_figure_html(
            figure, output_dir / f"action_{action.index:03d}.html"
        )

    manifest = {
        "case_id": artifacts.case.manifest.case_id,
        "solution_path": str(solution_file),
        "verifier_valid": report["valid"],
        "verifier_violations": report["violations"],
        "metrics": report["metrics"],
        "summary_path": str(summary_path),
        "region_zoom_path": str(region_zoom_path),
        "selected_action_indices": [action.index for action in selected],
        "regions": [
            {
                "region_id": region_grid.region.region_id,
                "area_km2_equivalent": region_grid.total_weight_m2 / 1_000_000.0,
                "intersecting_action_indices": [
                    action.index
                    for action in _actions_for_region(
                        region_grid.region,
                        selected if selected else artifacts.parsed_actions,
                    )
                ],
            }
            for region_grid in artifacts.case.region_grids.values()
        ],
        "actions": [
            {
                "action_index": action.index,
                "satellite_id": action.satellite_id,
                "accepted_for_schedule": action.accepted_for_schedule,
                "accepted_for_geometry": action.accepted_for_geometry,
                "start_time": _utc_iso(action.start_time),
                "end_time": _utc_iso(action.end_time or action.start_time),
                "duration_s": action.duration_s,
                "roll_deg": action.roll_deg,
                "covered_sample_count": len(action.covered_sample_ids),
                "covered_weight_m2_equivalent": action.covered_weight_m2_equivalent,
                "covered_region_ids": action.covered_region_ids,
                "page_path": str(action_pages.get(action.index, "")),
                "violations": action.violations,
            }
            for action in selected
        ],
    }
    _serialize_json(manifest, output_dir / "manifest.json")
    return output_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Development visualizer for regional_coverage geometry and coverage inspection.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    overview_parser = subparsers.add_parser("overview", help="Render a case overview PNG.")
    overview_parser.description = "Render a 2D Earth-texture case overview PNG."
    overview_parser.add_argument("case_dir", help="Path to dataset/cases/<case_id>")
    overview_parser.add_argument(
        "--out-path",
        type=Path,
        default=None,
        help="Where to write the overview PNG (default: benchmarks/regional_coverage/visualizer/plots/<case_id>/overview.png)",
    )
    overview_parser.add_argument(
        "--ground-track-step-s",
        type=float,
        default=300.0,
        help="Ground-track sampling step in seconds (default: 300)",
    )
    overview_parser.add_argument(
        "--max-ground-tracks",
        type=int,
        default=None,
        help="Optional cap on how many satellite ground tracks to draw, using satellite_id sort order",
    )

    inspect_parser = subparsers.add_parser(
        "inspect", help="Render inspection HTML and manifest for one case and solution."
    )
    inspect_parser.add_argument("case_dir", help="Path to dataset/cases/<case_id>")
    inspect_parser.add_argument("solution_path", help="Path to solution JSON")
    inspect_parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for generated HTML artifacts (default: benchmarks/regional_coverage/visualizer/plots/<case>/<solution_stem>)",
    )
    inspect_parser.add_argument(
        "--action-index",
        type=int,
        action="append",
        default=None,
        help="Restrict rendering to one or more action indices",
    )
    inspect_parser.add_argument(
        "--orbit-window-s",
        type=float,
        default=300.0,
        help="Seconds of orbit context to show before and after each selected action (default: 300)",
    )

    args = parser.parse_args(argv)
    if args.command == "overview":
        out_path = render_overview(
            args.case_dir,
            args.out_path,
            ground_track_step_s=args.ground_track_step_s,
            max_ground_tracks=args.max_ground_tracks,
        )
        print(f"Wrote overview PNG to {out_path}")
        return 0

    output_dir = render_inspection(
        args.case_dir,
        args.solution_path,
        args.out_dir,
        action_indices=args.action_index,
        orbit_window_s=args.orbit_window_s,
    )
    print(f"Wrote inspection artifacts to {output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
