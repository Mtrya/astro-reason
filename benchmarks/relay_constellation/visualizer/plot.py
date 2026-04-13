"""Plotting helpers for the relay_constellation development visualizer."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
import io
import json
import math
from pathlib import Path
import urllib.request
import zipfile

import brahe
import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from .geometry import (
    build_state_cache,
    build_state_cache_for_times,
    compute_connectivity_summaries,
    midpoint_index,
    relevant_satellites_for_demand,
    representative_demands,
    sampled_times_for_demands,
    visible_endpoint_links_at_index,
)
from .io import RelayCase, load_case


_VISUALIZER_DIR = Path(__file__).resolve().parent
DEFAULT_PLOTS_DIR = _VISUALIZER_DIR / "plots"
_TEXTURE_CACHE_DIR = _VISUALIZER_DIR / "cache" / "earth_textures"
_PREFERRED_TEXTURE_FILENAMES = (
    "world.topo.200410.3x5400x2700.png",
    "world.topo.200410.3x5400x2700.jpg",
    "blue_marble.jpg",
    "natural_earth.tif",
)
_WORLD_TOPO_DIRECT_URLS = (
    "https://neo.gsfc.nasa.gov/archive/bluemarble/bmng/world_8km/world.topo.200410.3x5400x2700.png",
)
_BLUE_MARBLE_DIRECT_URLS = (
    "https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57730/land_ocean_ice_2048.jpg",
)
_NATURAL_EARTH_ZIP_URL = "https://naciscdn.org/naturalearth/50m/raster/HYP_50M_SR_W.zip"
_ROUTE_COLORS = matplotlib.colormaps.get_cmap("tab20")


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%m-%d %H:%M")


def _serialize_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _download_bytes(url: str, *, timeout_s: float = 30.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout_s) as response:
        return response.read()


def _is_equirectangular_texture(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        return False
    if width <= 0 or height <= 0:
        return False
    aspect_ratio = width / height
    return 1.9 <= aspect_ratio <= 2.1


def _write_texture_if_valid(path: Path, payload: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    if _is_equirectangular_texture(path):
        return True
    path.unlink(missing_ok=True)
    return False


def _download_blue_marble_texture(cache_dir: Path) -> Path:
    topo_texture_path = cache_dir / "world.topo.200410.3x5400x2700.png"
    if topo_texture_path.exists() and _is_equirectangular_texture(topo_texture_path):
        return topo_texture_path

    for url in _WORLD_TOPO_DIRECT_URLS:
        try:
            payload = _download_bytes(url)
        except Exception:
            continue
        if not payload:
            continue
        if _write_texture_if_valid(topo_texture_path, payload):
            return topo_texture_path

    texture_path = cache_dir / "blue_marble.jpg"
    if texture_path.exists() and _is_equirectangular_texture(texture_path):
        return texture_path

    for url in _BLUE_MARBLE_DIRECT_URLS:
        try:
            payload = _download_bytes(url)
        except Exception:
            continue
        if not payload:
            continue
        if _write_texture_if_valid(texture_path, payload):
            return texture_path
    raise FileNotFoundError("Unable to download a NASA Blue Marble texture")


def _download_natural_earth_texture(cache_dir: Path) -> Path:
    tif_path = cache_dir / "natural_earth.tif"
    if tif_path.exists():
        return tif_path

    payload = _download_bytes(_NATURAL_EARTH_ZIP_URL)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if name.lower().endswith((".tif", ".tiff", ".jpg", ".jpeg", ".png"))
        ]
        if not candidates:
            raise FileNotFoundError("Natural Earth archive did not contain a raster texture")
        best_name = sorted(candidates, key=lambda name: len(name))[0]
        tif_path.parent.mkdir(parents=True, exist_ok=True)
        tif_path.write_bytes(archive.read(best_name))
    return tif_path


def resolve_texture_path(texture_path: Path | None = None) -> Path:
    if texture_path is not None:
        texture_path = Path(texture_path).resolve()
        if not texture_path.is_file():
            raise FileNotFoundError(f"Texture path does not exist: {texture_path}")
        return texture_path

    _TEXTURE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for filename in _PREFERRED_TEXTURE_FILENAMES:
        candidate = _TEXTURE_CACHE_DIR / filename
        if candidate.is_file() and _is_equirectangular_texture(candidate):
            return candidate
    try:
        return _download_blue_marble_texture(_TEXTURE_CACHE_DIR)
    except Exception:
        return _download_natural_earth_texture(_TEXTURE_CACHE_DIR)


def _load_texture_image(texture_path: Path) -> np.ndarray:
    image = Image.open(texture_path).convert("RGB")
    width, height = image.size
    max_width = 2048
    if width > max_width:
        scale = max_width / width
        image = image.resize(
            (max_width, max(2, int(height * scale))),
            resample=Image.Resampling.BILINEAR,
        )
    return np.asarray(image, dtype=np.uint8)


def _route_color(route_nodes: tuple[str, ...]) -> tuple[float, float, float, float]:
    key = abs(hash(route_nodes)) % 20
    return _ROUTE_COLORS(key / 19.0 if key else 0.0)


def _sample_lonlat_segments(
    sample_times: list[datetime],
    ecef_rows: np.ndarray,
    *,
    start_time: datetime,
    end_time: datetime,
) -> list[tuple[list[float], list[float]]]:
    lons: list[float] = []
    lats: list[float] = []
    for index, instant in enumerate(sample_times):
        if instant < start_time or instant >= end_time:
            continue
        lon_deg, lat_deg, _ = brahe.position_ecef_to_geodetic(
            ecef_rows[index],
            brahe.AngleFormat.DEGREES,
        )
        lons.append(float(lon_deg))
        lats.append(float(lat_deg))
    if not lons:
        return []
    return brahe.split_ground_track_at_antimeridian(lons, lats)


def render_overview_png(
    case: RelayCase,
    demand_id: str,
    output_path: Path,
    *,
    texture_path: Path | None = None,
    sample_times: list[datetime] | None = None,
    states_ecef_by_satellite: dict[str, np.ndarray] | None = None,
) -> Path:
    demand = next(demand for demand in case.demands if demand.demand_id == demand_id)
    actual_texture_path = resolve_texture_path(texture_path)
    texture = _load_texture_image(actual_texture_path)

    if sample_times is None or states_ecef_by_satellite is None:
        sample_times, states_ecef_by_satellite = build_state_cache(case)
    relevant_satellite_ids = relevant_satellites_for_demand(
        case,
        demand,
        sample_times=sample_times,
        states_ecef_by_satellite=states_ecef_by_satellite,
    )
    midpoint_sample_index = midpoint_index(sample_times, demand)
    visible_links = visible_endpoint_links_at_index(
        case,
        demand,
        sample_index=midpoint_sample_index,
        states_ecef_by_satellite=states_ecef_by_satellite,
        satellite_ids=relevant_satellite_ids,
    )
    figure = plt.figure(figsize=(14, 8))
    figure.patch.set_facecolor("#ffffff")
    grid = figure.add_gridspec(1, 2, width_ratios=[2.5, 1.0], wspace=0.12)
    axis = figure.add_subplot(grid[0, 0])
    summary_axis = figure.add_subplot(grid[0, 1])

    axis.set_facecolor("#09121a")
    axis.imshow(
        texture,
        origin="upper",
        extent=[-180.0, 180.0, -90.0, 90.0],
        aspect="auto",
        interpolation="bilinear",
        zorder=0,
        alpha=0.96,
    )
    axis.set_xlim(-180.0, 180.0)
    axis.set_ylim(-90.0, 90.0)
    axis.set_xlabel("Longitude (deg)")
    axis.set_ylabel("Latitude (deg)")
    axis.grid(True, color="#d5dbe3", linewidth=0.7, alpha=0.45)

    src = case.ground_endpoints[demand.source_endpoint_id]
    dst = case.ground_endpoints[demand.destination_endpoint_id]
    other_endpoints = [
        endpoint
        for endpoint_id, endpoint in sorted(case.ground_endpoints.items())
        if endpoint_id not in {src.endpoint_id, dst.endpoint_id}
    ]

    for satellite_id in sorted(relevant_satellite_ids):
        segments = _sample_lonlat_segments(
            sample_times,
            states_ecef_by_satellite[satellite_id],
            start_time=demand.start_time,
            end_time=demand.end_time,
        )
        for lon_seg, lat_seg in segments:
            axis.plot(
                lon_seg,
                lat_seg,
                color="#60a5fa",
                linewidth=1.5,
                alpha=0.95,
                zorder=2,
            )

    axis.scatter(
        [src.longitude_deg],
        [src.latitude_deg],
        color="#16a34a",
        s=70,
        label=f"Source {src.endpoint_id}",
        edgecolors="white",
        linewidths=0.8,
        zorder=4,
    )
    axis.scatter(
        [dst.longitude_deg],
        [dst.latitude_deg],
        color="#dc2626",
        s=70,
        label=f"Destination {dst.endpoint_id}",
        edgecolors="white",
        linewidths=0.8,
        zorder=4,
    )
    if other_endpoints:
        axis.scatter(
            [endpoint.longitude_deg for endpoint in other_endpoints],
            [endpoint.latitude_deg for endpoint in other_endpoints],
            color="#6b7280",
            s=28,
            label="Other endpoints",
            edgecolors="white",
            linewidths=0.5,
            zorder=3,
        )

    if relevant_satellite_ids:
        midpoint_lons: list[float] = []
        midpoint_lats: list[float] = []
        for satellite_id in sorted(relevant_satellite_ids):
            lon_deg, lat_deg, _ = brahe.position_ecef_to_geodetic(
                states_ecef_by_satellite[satellite_id][midpoint_sample_index],
                brahe.AngleFormat.DEGREES,
            )
            midpoint_lons.append(float(lon_deg))
            midpoint_lats.append(float(lat_deg))
        axis.scatter(
            midpoint_lons,
            midpoint_lats,
            color="#2563eb",
            s=26,
            label="Relevant backbone satellites",
            edgecolors="white",
            linewidths=0.5,
            zorder=5,
        )

    for endpoint_id, satellite_id in visible_links:
        endpoint = case.ground_endpoints[endpoint_id]
        lon_deg, lat_deg, _ = brahe.position_ecef_to_geodetic(
            states_ecef_by_satellite[satellite_id][midpoint_sample_index],
            brahe.AngleFormat.DEGREES,
        )
        axis.plot(
            [endpoint.longitude_deg, float(lon_deg)],
            [endpoint.latitude_deg, float(lat_deg)],
            color="#f59e0b" if endpoint_id == src.endpoint_id else "#8b5cf6",
            linewidth=1.1,
            alpha=0.8,
            zorder=4,
        )
    axis.legend(loc="upper left", bbox_to_anchor=(0.01, 0.99))

    summary_axis.axis("off")
    summary_lines = [
        f"Case: {case.manifest.case_id}",
        f"Demand: {demand.demand_id}",
        "",
        f"Source: {src.endpoint_id}",
        f"  lat/lon: {src.latitude_deg:.2f}, {src.longitude_deg:.2f}",
        f"Destination: {dst.endpoint_id}",
        f"  lat/lon: {dst.latitude_deg:.2f}, {dst.longitude_deg:.2f}",
        "",
        f"Window start: {_utc_text(demand.start_time)} UTC",
        f"Window end:   {_utc_text(demand.end_time)} UTC",
        f"Midpoint:     {_utc_text(sample_times[midpoint_sample_index])} UTC",
        "",
        f"Relevant satellites: {len(relevant_satellite_ids)}",
        f"Visible midpoint links: {len(visible_links)}",
    ]
    if relevant_satellite_ids:
        summary_lines.extend(
            [
                "",
                "Satellite IDs:",
                *[f"  - {sat_id}" for sat_id in sorted(relevant_satellite_ids)[:10]],
            ]
        )
        if len(relevant_satellite_ids) > 10:
            summary_lines.append(f"  ... ({len(relevant_satellite_ids) - 10} more)")
    summary_axis.text(
        0.0,
        1.0,
        "\n".join(summary_lines),
        ha="left",
        va="top",
        fontsize=10,
        family="monospace",
        color="#1f2933",
    )
    figure.suptitle(
        (
            f"{case.manifest.case_id} | {demand.demand_id} | "
            f"{demand.source_endpoint_id} -> {demand.destination_endpoint_id}\n"
            f"Window {_utc_text(demand.start_time)} to {_utc_text(demand.end_time)} UTC | "
            f"midpoint {_utc_text(sample_times[midpoint_sample_index])} UTC"
        ),
        fontsize=13,
        y=0.96,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return output_path


def render_overview_set(
    case_dir: Path | str,
    output_dir: Path | str,
    *,
    texture_path: Path | None = None,
) -> dict[str, object]:
    case = load_case(case_dir)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_times = sampled_times_for_demands(case)
    sample_times, states_ecef_by_satellite = build_state_cache_for_times(case, sample_times)

    overview_paths: list[str] = []
    for demand in representative_demands(case):
        overview_path = output_dir / f"overview_{demand.demand_id}.png"
        render_overview_png(
            case,
            demand.demand_id,
            overview_path,
            texture_path=texture_path,
            sample_times=sample_times,
            states_ecef_by_satellite=states_ecef_by_satellite,
        )
        overview_paths.append(overview_path.name)

    manifest = {
        "case_id": case.manifest.case_id,
        "case_dir": str(case.case_dir),
        "overview_pngs": overview_paths,
        "num_backbone_satellites": len(case.backbone_satellites),
        "num_ground_endpoints": len(case.ground_endpoints),
        "num_demanded_windows": len(case.demands),
    }
    _serialize_json(output_dir / "manifest.json", manifest)
    return manifest


def render_connectivity_png(
    case: RelayCase,
    output_path: Path,
    *,
    sample_times: list[datetime] | None = None,
    states_ecef_by_satellite: dict[str, np.ndarray] | None = None,
) -> Path:
    summaries = compute_connectivity_summaries(
        case,
        sample_times=sample_times,
        states_ecef_by_satellite=states_ecef_by_satellite,
    )
    if not summaries:
        raise ValueError(f"{case.manifest.case_id} does not contain any endpoint pairs")

    height = max(4.0, 1.8 + (1.4 * len(summaries)))
    figure = plt.figure(figsize=(16, height))
    grid = figure.add_gridspec(1, 2, width_ratios=[3.4, 1.6], wspace=0.15)
    axis = figure.add_subplot(grid[0, 0])
    text_axis = figure.add_subplot(grid[0, 1])

    horizon_start = case.manifest.horizon_start
    horizon_end = case.manifest.horizon_end
    lane_height = 0.7

    for lane_index, summary in enumerate(summaries):
        y_base = lane_index
        for window_start, window_end in summary.demand_windows:
            axis.barh(
                y_base,
                width=(window_end - window_start).total_seconds() / 86_400.0,
                left=mdates.date2num(window_start),
                height=0.92,
                color="#dbeafe",
                alpha=0.45,
            )
        for interval in summary.route_intervals:
            axis.barh(
                y_base,
                width=(interval.end_time - interval.start_time).total_seconds() / 86_400.0,
                left=mdates.date2num(interval.start_time),
                height=lane_height,
                color=_route_color(interval.route_nodes),
                edgecolor="white",
                linewidth=0.5,
            )

    axis.set_ylim(-0.8, len(summaries) - 0.2)
    axis.set_yticks(range(len(summaries)))
    axis.set_yticklabels([summary.pair_id for summary in summaries])
    axis.set_xlim(mdates.date2num(horizon_start), mdates.date2num(horizon_end))
    axis.xaxis.set_major_locator(mdates.HourLocator(interval=12))
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M", tz=UTC))
    axis.grid(True, axis="x", color="#d1d5db", linewidth=0.8, alpha=0.7)
    axis.set_facecolor("#f8fafc")
    axis.set_xlabel("UTC time")
    axis.set_title(
        f"{case.manifest.case_id}: baseline infinite-concurrency connectivity",
        fontsize=13,
    )

    text_axis.axis("off")
    text_lines = [
        "Requested-window route intervals",
        "",
    ]
    for summary in summaries:
        if summary.requested_sample_count > 0:
            availability = summary.served_sample_count / summary.requested_sample_count
        else:
            availability = 0.0
        text_lines.append(
            f"{summary.pair_id}  availability={availability:.2f}"
        )
        intervals = summary.route_intervals_overlapping_demands
        if not intervals:
            text_lines.append("  no geometry-feasible route during requested windows")
            text_lines.append("")
            continue
        for interval in intervals:
            route_text = " -> ".join(interval.route_nodes)
            text_lines.append(
                f"  {_utc_text(interval.start_time)} - {_utc_text(interval.end_time)}"
            )
            text_lines.append(f"  {route_text}")
        text_lines.append("")
    text_axis.text(
        0.0,
        1.0,
        "\n".join(text_lines),
        ha="left",
        va="top",
        fontsize=8.8,
        family="monospace",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(figure)
    return output_path


def render_connectivity_report(
    case_dir: Path | str,
    output_path: Path,
) -> dict[str, object]:
    case = load_case(case_dir)
    output_path = Path(output_path).resolve()
    sample_times, states_ecef_by_satellite = build_state_cache(case)
    summaries = compute_connectivity_summaries(
        case,
        sample_times=sample_times,
        states_ecef_by_satellite=states_ecef_by_satellite,
    )
    render_connectivity_png(
        case,
        output_path,
        sample_times=sample_times,
        states_ecef_by_satellite=states_ecef_by_satellite,
    )
    manifest = {
        "case_id": case.manifest.case_id,
        "case_dir": str(case.case_dir),
        "connectivity_png": output_path.name,
        "endpoint_pairs": [
            {
                "pair_id": summary.pair_id,
                "requested_sample_count": summary.requested_sample_count,
                "served_sample_count": summary.served_sample_count,
                "route_interval_count": len(summary.route_intervals),
            }
            for summary in summaries
        ],
    }
    _serialize_json(output_path.parent / "connectivity_manifest.json", manifest)
    return manifest


def render_case_plots(
    case_dir: Path | str,
    output_dir: Path | str,
    *,
    texture_path: Path | None = None,
) -> dict[str, object]:
    case = load_case(case_dir)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_times, states_ecef_by_satellite = build_state_cache(case)

    overview_paths: list[str] = []
    for demand in representative_demands(case):
        overview_path = output_dir / f"overview_{demand.demand_id}.png"
        render_overview_png(
            case,
            demand.demand_id,
            overview_path,
            texture_path=texture_path,
            sample_times=sample_times,
            states_ecef_by_satellite=states_ecef_by_satellite,
        )
        overview_paths.append(overview_path.name)

    connectivity_path = output_dir / "connectivity.png"
    render_connectivity_png(
        case,
        connectivity_path,
        sample_times=sample_times,
        states_ecef_by_satellite=states_ecef_by_satellite,
    )

    manifest = {
        "case_id": case.manifest.case_id,
        "case_dir": str(case.case_dir),
        "connectivity_png": connectivity_path.name,
        "overview_pngs": overview_paths,
        "num_backbone_satellites": len(case.backbone_satellites),
        "num_ground_endpoints": len(case.ground_endpoints),
        "num_demanded_windows": len(case.demands),
    }
    _serialize_json(output_dir / "manifest.json", manifest)
    return manifest


def render_dataset_plots(
    dataset_dir: Path | str,
    output_dir: Path | str,
    *,
    case_id: str | None = None,
    texture_path: Path | None = None,
) -> list[dict[str, object]]:
    dataset_dir = Path(dataset_dir).resolve()
    output_dir = Path(output_dir).resolve()
    cases_root = dataset_dir / "cases"
    case_dirs = sorted(path for path in cases_root.iterdir() if path.is_dir())
    if case_id is not None:
        case_dirs = [path for path in case_dirs if path.name == case_id]
    if not case_dirs:
        raise FileNotFoundError(f"No case directories found under {cases_root}")

    manifests: list[dict[str, object]] = []
    for case_dir in case_dirs:
        manifests.append(
            render_case_plots(
                case_dir,
                output_dir / case_dir.name,
                texture_path=texture_path,
            )
        )
    _serialize_json(output_dir / "index.json", {"cases": manifests})
    return manifests
