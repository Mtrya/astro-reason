"""Case-only plots for the aeossp_standard visualizer."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from brahe.plots.texture_utils import load_earth_texture

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from .geometry import (
    access_mask_for_satellite,
    derive_task_access_intervals,
    sample_orbit_grid,
    utc_iso,
)
from .io import CaseData, load_case


DEFAULT_PLOTS_DIR = Path(__file__).resolve().parent / "plots"
_WORLD_TEXTURE_EXTENT = (-180.0, 180.0, -90.0, 90.0)
_WORLD_TEXTURE: np.ndarray | None = None
_THEME = {
    "background": "#ffffff",
    "panel": "#f7f8fa",
    "grid": "#d5dbe3",
    "axis": "#39424e",
    "text": "#1f2933",
    "muted": "#52606d",
}
_TASK_COLORS = {
    ("city", "visible"): "#d97706",
    ("city", "infrared"): "#be185d",
    ("background", "visible"): "#2563eb",
    ("background", "infrared"): "#7c3aed",
}
_SATELLITE_TRACK_COLOR = "#64748b"


def _serialize_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sanitize_axes(ax: plt.Axes, *, facecolor: str | None = None) -> None:
    ax.set_facecolor(facecolor or _THEME["panel"])
    ax.grid(True, color=_THEME["grid"], alpha=0.75, linewidth=0.8)
    ax.tick_params(colors=_THEME["muted"])
    for spine in ax.spines.values():
        spine.set_color(_THEME["axis"])


def _load_world_texture(texture_path: Path | None) -> np.ndarray | None:
    global _WORLD_TEXTURE
    if texture_path is not None and texture_path.is_file():
        return plt.imread(texture_path)
    if _WORLD_TEXTURE is None:
        for texture_name in ("blue_marble", "natural_earth_50m"):
            try:
                image = load_earth_texture(texture_name)
            except Exception:
                continue
            if image is not None:
                _WORLD_TEXTURE = np.asarray(image)
                break
    return _WORLD_TEXTURE


def _draw_world_texture(ax: plt.Axes, *, texture_path: Path | None) -> None:
    texture = _load_world_texture(texture_path)
    if texture is None:
        return
    ax.imshow(
        texture,
        origin="upper",
        extent=list(_WORLD_TEXTURE_EXTENT),
        aspect="auto",
        interpolation="bilinear",
        zorder=0,
        alpha=0.96,
    )


def _source_kind(task: dict[str, Any]) -> str:
    return "background" if str(task["name"]).startswith("background_") else "city"


def _task_key(task: dict[str, Any]) -> tuple[str, str]:
    return (_source_kind(task), str(task["required_sensor_type"]))


def _split_track_segments(
    longitudes_deg: np.ndarray,
    latitudes_deg: np.ndarray,
) -> list[tuple[np.ndarray, np.ndarray]]:
    if longitudes_deg.size == 0:
        return []
    segments: list[tuple[np.ndarray, np.ndarray]] = []
    start_idx = 0
    for idx in range(1, longitudes_deg.size):
        if abs(float(longitudes_deg[idx]) - float(longitudes_deg[idx - 1])) > 180.0:
            segments.append((longitudes_deg[start_idx:idx], latitudes_deg[start_idx:idx]))
            start_idx = idx
    segments.append((longitudes_deg[start_idx:], latitudes_deg[start_idx:]))
    return segments


def _case_counts(case: CaseData) -> dict[str, Any]:
    return {
        "num_satellites": len(case.satellites),
        "num_tasks": len(case.tasks),
        "satellite_sensor_mix": dict(
            Counter(sat["sensor"]["sensor_type"] for sat in case.satellites)
        ),
        "task_sensor_mix": dict(
            Counter(task["required_sensor_type"] for task in case.tasks)
        ),
        "task_source_mix": dict(Counter(_source_kind(task) for task in case.tasks)),
    }


def _compute_access_summary(
    case: CaseData,
    *,
    access_step_s: int,
) -> dict[str, Any]:
    orbit_grid = sample_orbit_grid(
        case.satellites,
        start_time=case.horizon_start,
        end_time=case.horizon_end,
        step_s=access_step_s,
    )
    compatible_satellite_ids = {
        "visible": {
            sat["satellite_id"]
            for sat in case.satellites
            if sat["sensor"]["sensor_type"] == "visible"
        },
        "infrared": {
            sat["satellite_id"]
            for sat in case.satellites
            if sat["sensor"]["sensor_type"] == "infrared"
        },
    }
    task_access_counts: dict[str, int] = {}
    task_access_examples: dict[str, list[dict[str, Any]]] = {}
    satellite_accessible_task_counts = Counter({sat["satellite_id"]: 0 for sat in case.satellites})
    reachable_by_sensor = Counter()
    totals_by_sensor = Counter()
    reachable_by_source = Counter()
    totals_by_source = Counter()
    representative_pool: list[dict[str, Any]] = []

    for task in case.tasks:
        sensor_type = str(task["required_sensor_type"])
        intervals = derive_task_access_intervals(
            task,
            case.satellites,
            orbit_grid,
            compatible_satellite_ids=compatible_satellite_ids[sensor_type],
        )
        unique_satellite_ids = sorted({interval.satellite_id for interval in intervals})
        task_access_counts[task["task_id"]] = len(unique_satellite_ids)
        task_access_examples[task["task_id"]] = [
            {
                "satellite_id": interval.satellite_id,
                "start_time": utc_iso(interval.start_time),
                "end_time": utc_iso(interval.end_time),
                "duration_s": interval.duration_s,
                "max_off_nadir_deg": round(interval.max_off_nadir_deg, 3),
            }
            for interval in intervals[:6]
        ]
        totals_by_sensor[sensor_type] += 1
        totals_by_source[_source_kind(task)] += 1
        if unique_satellite_ids:
            reachable_by_sensor[sensor_type] += 1
            reachable_by_source[_source_kind(task)] += 1
            for satellite_id in unique_satellite_ids:
                satellite_accessible_task_counts[satellite_id] += 1
            longest = max(intervals, key=lambda interval: interval.duration_s)
            representative_pool.append(
                {
                    "task": task,
                    "interval": longest,
                    "num_reaching_satellites": len(unique_satellite_ids),
                }
            )

    representative_pool.sort(
        key=lambda item: (
            -item["interval"].duration_s,
            item["interval"].satellite_id,
            item["task"]["task_id"],
        )
    )
    return {
        "orbit_grid": orbit_grid,
        "task_access_counts": task_access_counts,
        "task_access_examples": task_access_examples,
        "satellite_accessible_task_counts": dict(satellite_accessible_task_counts),
        "reachable_by_sensor": dict(reachable_by_sensor),
        "totals_by_sensor": dict(totals_by_sensor),
        "reachable_by_source": dict(reachable_by_source),
        "totals_by_source": dict(totals_by_source),
        "representative_pool": representative_pool,
        "access_step_s": access_step_s,
    }


def _choose_representative_intervals(
    case: CaseData,
    access_summary: dict[str, Any],
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    by_sensor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in access_summary["representative_pool"]:
        by_sensor[item["task"]["required_sensor_type"]].append(item)
    selected: list[dict[str, Any]] = []
    used_pairs: set[tuple[str, str]] = set()
    for sensor_type in ("visible", "infrared"):
        for item in by_sensor.get(sensor_type, [])[: min(3, limit)]:
            pair = (item["interval"].satellite_id, item["task"]["task_id"])
            if pair in used_pairs:
                continue
            selected.append(item)
            used_pairs.add(pair)
            if len(selected) >= limit:
                return selected
    for item in access_summary["representative_pool"]:
        pair = (item["interval"].satellite_id, item["task"]["task_id"])
        if pair in used_pairs:
            continue
        selected.append(item)
        used_pairs.add(pair)
        if len(selected) >= limit:
            break
    return selected


def _render_overview(
    case: CaseData,
    access_summary: dict[str, Any],
    out_path: Path,
    *,
    texture_path: Path | None,
    track_step_s: int,
) -> None:
    track_grid = sample_orbit_grid(
        case.satellites,
        start_time=case.horizon_start,
        end_time=case.horizon_end,
        step_s=track_step_s,
    )
    counts = _case_counts(case)
    reachable_task_count = sum(
        1 for count in access_summary["task_access_counts"].values() if count > 0
    )

    fig = plt.figure(figsize=(15, 8.5), constrained_layout=True)
    gs = fig.add_gridspec(1, 2, width_ratios=[3.6, 1.2])
    ax = fig.add_subplot(gs[0, 0])
    info = fig.add_subplot(gs[0, 1])
    _sanitize_axes(ax)
    _draw_world_texture(ax, texture_path=texture_path)
    ax.set_xlim(-180.0, 180.0)
    ax.set_ylim(-90.0, 90.0)
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.set_title(f"{case.case_id} overview")

    for satellite in case.satellites:
        sat_id = satellite["satellite_id"]
        for lon_seg, lat_seg in _split_track_segments(
            track_grid.longitudes_deg[sat_id],
            track_grid.latitudes_deg[sat_id],
        ):
            ax.plot(
                lon_seg,
                lat_seg,
                color=_SATELLITE_TRACK_COLOR,
                linewidth=0.7,
                alpha=0.22,
                zorder=1,
            )

    for (source_kind, sensor_type), color in _TASK_COLORS.items():
        group_tasks = [
            task for task in case.tasks if _task_key(task) == (source_kind, sensor_type)
        ]
        if not group_tasks:
            continue
        ax.scatter(
            [task["longitude_deg"] for task in group_tasks],
            [task["latitude_deg"] for task in group_tasks],
            s=12 if source_kind == "background" else 18,
            marker="o" if source_kind == "city" else "^",
            color=color,
            alpha=0.72,
            edgecolors="none",
            label=f"{source_kind} / {sensor_type}",
            zorder=2,
        )

    info.axis("off")
    summary_lines = [
        f"Case: {case.case_id}",
        f"Horizon: {utc_iso(case.horizon_start)}",
        f"to {utc_iso(case.horizon_end)}",
        "",
        f"Satellites: {counts['num_satellites']}",
        f"Tasks: {counts['num_tasks']}",
        "",
        "Satellite mix:",
        f"  visible: {counts['satellite_sensor_mix'].get('visible', 0)}",
        f"  infrared: {counts['satellite_sensor_mix'].get('infrared', 0)}",
        "",
        "Task mix:",
        f"  city: {counts['task_source_mix'].get('city', 0)}",
        f"  background: {counts['task_source_mix'].get('background', 0)}",
        f"  visible: {counts['task_sensor_mix'].get('visible', 0)}",
        f"  infrared: {counts['task_sensor_mix'].get('infrared', 0)}",
        "",
        f"Reachable tasks: {reachable_task_count}/{len(case.tasks)}",
        f"Track step: {track_step_s}s",
        f"Access step: {access_summary['access_step_s']}s",
    ]
    info.text(
        0.02,
        0.98,
        "\n".join(summary_lines),
        ha="left",
        va="top",
        fontsize=11,
        family="monospace",
        color=_THEME["text"],
    )

    ax.legend(loc="lower left", fontsize=9, frameon=True, framealpha=0.92)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _render_task_windows(case: CaseData, out_path: Path) -> None:
    tasks_sorted = sorted(
        case.tasks,
        key=lambda task: (task["release_time"], task["due_time"], task["task_id"]),
    )
    fig, (ax_top, ax_bottom) = plt.subplots(
        2,
        1,
        figsize=(15, max(8.0, len(tasks_sorted) * 0.022)),
        gridspec_kw={"height_ratios": [1, 4]},
        constrained_layout=True,
    )
    _sanitize_axes(ax_top)
    _sanitize_axes(ax_bottom)

    occupancy_visible = []
    occupancy_infrared = []
    time_cursor = case.horizon_start
    time_samples = []
    parsed_windows = [
        (
            task,
            mdates.date2num(
                datetime.fromisoformat(task["release_time"].replace("Z", "+00:00"))
            ),
            mdates.date2num(
                datetime.fromisoformat(task["due_time"].replace("Z", "+00:00"))
            ),
        )
        for task in tasks_sorted
    ]
    while time_cursor <= case.horizon_end:
        visible_count = 0
        infrared_count = 0
        now = mdates.date2num(time_cursor)
        for task, start_time, end_time in parsed_windows:
            if start_time <= now <= end_time:
                if task["required_sensor_type"] == "visible":
                    visible_count += 1
                else:
                    infrared_count += 1
        time_samples.append(time_cursor)
        occupancy_visible.append(visible_count)
        occupancy_infrared.append(infrared_count)
        time_cursor += timedelta(minutes=5)

    ax_top.plot(time_samples, occupancy_visible, color="#2563eb", label="visible windows")
    ax_top.plot(time_samples, occupancy_infrared, color="#be185d", label="infrared windows")
    ax_top.set_ylabel("Active windows")
    ax_top.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax_top.legend(loc="upper right", fontsize=9)
    ax_top.set_title(f"{case.case_id} task windows")

    for row_index, (task, release, due) in enumerate(parsed_windows):
        color = _TASK_COLORS[_task_key(task)]
        ax_bottom.hlines(
            y=row_index,
            xmin=release,
            xmax=due,
            color=color,
            linewidth=1.0,
            alpha=0.85,
        )
    ax_bottom.set_ylabel("Tasks (sorted by release)")
    ax_bottom.set_xlabel("UTC")
    ax_bottom.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _render_access_summary(case: CaseData, access_summary: dict[str, Any], out_path: Path) -> None:
    per_task_counts = list(access_summary["task_access_counts"].values())
    per_sat_counts = list(access_summary["satellite_accessible_task_counts"].values())
    reachable_sensor = access_summary["reachable_by_sensor"]
    total_sensor = access_summary["totals_by_sensor"]
    reachable_source = access_summary["reachable_by_source"]
    total_source = access_summary["totals_by_source"]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    ax_task_hist, ax_sat_hist, ax_sensor_bar, ax_source_bar = axes.ravel()
    for ax in axes.ravel():
        _sanitize_axes(ax)

    ax_task_hist.hist(
        per_task_counts,
        bins=np.arange(0, max(per_task_counts + [1]) + 2) - 0.5,
        color="#2563eb",
        alpha=0.85,
    )
    ax_task_hist.set_title("Reachable satellites per task")
    ax_task_hist.set_xlabel("Compatible satellites with access")
    ax_task_hist.set_ylabel("Tasks")

    ax_sat_hist.hist(
        per_sat_counts,
        bins=min(18, max(8, len(case.satellites) // 2)),
        color="#0f766e",
        alpha=0.85,
    )
    ax_sat_hist.set_title("Accessible tasks per satellite")
    ax_sat_hist.set_xlabel("Tasks with any access")
    ax_sat_hist.set_ylabel("Satellites")

    sensor_labels = ["visible", "infrared"]
    sensor_rates = [
        reachable_sensor.get(label, 0) / max(1, total_sensor.get(label, 0))
        for label in sensor_labels
    ]
    ax_sensor_bar.bar(sensor_labels, sensor_rates, color=["#2563eb", "#be185d"], alpha=0.85)
    ax_sensor_bar.set_ylim(0.0, 1.0)
    ax_sensor_bar.set_title("Reachable share by modality")
    ax_sensor_bar.set_ylabel("Share")

    source_labels = ["city", "background"]
    source_rates = [
        reachable_source.get(label, 0) / max(1, total_source.get(label, 0))
        for label in source_labels
    ]
    ax_source_bar.bar(source_labels, source_rates, color=["#d97706", "#7c3aed"], alpha=0.85)
    ax_source_bar.set_ylim(0.0, 1.0)
    ax_source_bar.set_title("Reachable share by source")
    ax_source_bar.set_ylabel("Share")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _render_pointing_curves(
    case: CaseData,
    access_summary: dict[str, Any],
    out_path: Path,
) -> list[dict[str, Any]]:
    selected = _choose_representative_intervals(case, access_summary)
    if not selected:
        fig, ax = plt.subplots(figsize=(10, 3.5), constrained_layout=True)
        _sanitize_axes(ax)
        ax.text(
            0.5,
            0.5,
            "No representative access intervals were found.",
            ha="center",
            va="center",
            fontsize=12,
            color=_THEME["text"],
        )
        ax.set_axis_off()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        return []

    sat_map = {sat["satellite_id"]: sat for sat in case.satellites}
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.5), constrained_layout=True)
    flat_axes = axes.ravel()
    manifest_entries: list[dict[str, Any]] = []
    for ax in flat_axes:
        _sanitize_axes(ax)
    for ax, item in zip(flat_axes, selected, strict=False):
        interval = item["interval"]
        task = item["task"]
        margin_s = max(30, interval.duration_s // 4)
        fine_start = max(case.horizon_start, interval.start_time - timedelta(seconds=margin_s))
        fine_end = min(case.horizon_end, interval.end_time + timedelta(seconds=margin_s))
        fine_grid = sample_orbit_grid(
            [sat_map[interval.satellite_id]],
            start_time=fine_start,
            end_time=fine_end,
            step_s=1,
        )
        mask, off_nadir_deg = access_mask_for_satellite(
            task,
            sat_map[interval.satellite_id],
            fine_grid.positions_ecef_m[interval.satellite_id],
        )
        time_seconds = np.array(
            [(instant - fine_start).total_seconds() for instant in fine_grid.sample_times],
            dtype=float,
        )
        ax.plot(time_seconds, off_nadir_deg, color="#2563eb", linewidth=1.6)
        ax.fill_between(
            time_seconds,
            0.0,
            off_nadir_deg,
            where=mask,
            color="#93c5fd",
            alpha=0.5,
        )
        ax.axhline(
            y=float(sat_map[interval.satellite_id]["attitude_model"]["max_off_nadir_deg"]),
            color="#be185d",
            linewidth=1.0,
            linestyle="--",
        )
        ax.set_title(f"{interval.satellite_id} -> {task['task_id']}", fontsize=10)
        ax.set_xlabel("Seconds from curve start")
        ax.set_ylabel("Off-nadir (deg)")
        manifest_entries.append(
            {
                "satellite_id": interval.satellite_id,
                "task_id": task["task_id"],
                "task_name": task["name"],
                "start_time": utc_iso(interval.start_time),
                "end_time": utc_iso(interval.end_time),
                "duration_s": interval.duration_s,
                "max_off_nadir_deg": round(interval.max_off_nadir_deg, 3),
            }
        )
    for ax in flat_axes[len(selected) :]:
        ax.set_axis_off()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return manifest_entries


def _build_summary(
    case: CaseData,
    access_summary: dict[str, Any],
    pointing_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    counts = _case_counts(case)
    per_task_counts = list(access_summary["task_access_counts"].values())
    per_sat_counts = list(access_summary["satellite_accessible_task_counts"].values())
    return {
        "case_id": case.case_id,
        "horizon_start": utc_iso(case.horizon_start),
        "horizon_end": utc_iso(case.horizon_end),
        "counts": counts,
        "access_summary": {
            "access_step_s": access_summary["access_step_s"],
            "reachable_task_count": sum(1 for count in per_task_counts if count > 0),
            "zero_access_task_count": sum(1 for count in per_task_counts if count == 0),
            "multi_access_task_count": sum(1 for count in per_task_counts if count >= 2),
            "reachable_share_by_sensor": {
                sensor_type: round(
                    access_summary["reachable_by_sensor"].get(sensor_type, 0)
                    / max(1, access_summary["totals_by_sensor"].get(sensor_type, 0)),
                    6,
                )
                for sensor_type in sorted(access_summary["totals_by_sensor"])
            },
            "reachable_share_by_source": {
                source_kind: round(
                    access_summary["reachable_by_source"].get(source_kind, 0)
                    / max(1, access_summary["totals_by_source"].get(source_kind, 0)),
                    6,
                )
                for source_kind in sorted(access_summary["totals_by_source"])
            },
            "reachable_satellites_per_task": {
                "min": min(per_task_counts) if per_task_counts else 0,
                "max": max(per_task_counts) if per_task_counts else 0,
                "mean": round(sum(per_task_counts) / max(1, len(per_task_counts)), 6),
            },
            "accessible_tasks_per_satellite": {
                "min": min(per_sat_counts) if per_sat_counts else 0,
                "max": max(per_sat_counts) if per_sat_counts else 0,
                "mean": round(sum(per_sat_counts) / max(1, len(per_sat_counts)), 6),
            },
        },
        "representative_pointing_curves": pointing_entries,
    }


def render_case_bundle(
    case_dir: str | Path,
    out_dir: str | Path | None = None,
    *,
    texture_path: str | Path | None = None,
    access_step_s: int = 60,
    track_step_s: int = 300,
) -> dict[str, Any]:
    case = load_case(case_dir)
    output_dir = (
        Path(out_dir).resolve()
        if out_dir is not None
        else (DEFAULT_PLOTS_DIR / case.case_id / "case").resolve()
    )
    texture = Path(texture_path).resolve() if texture_path is not None else None
    access_summary = _compute_access_summary(case, access_step_s=access_step_s)
    overview_path = output_dir / "overview.png"
    task_windows_path = output_dir / "task_windows.png"
    access_summary_path = output_dir / "access_summary.png"
    pointing_path = output_dir / "pointing_curves.png"
    _render_overview(
        case,
        access_summary,
        overview_path,
        texture_path=texture,
        track_step_s=track_step_s,
    )
    _render_task_windows(case, task_windows_path)
    _render_access_summary(case, access_summary, access_summary_path)
    pointing_entries = _render_pointing_curves(case, access_summary, pointing_path)
    manifest = _build_summary(case, access_summary, pointing_entries)
    manifest["artifacts"] = {
        "overview": str(overview_path),
        "task_windows": str(task_windows_path),
        "access_summary": str(access_summary_path),
        "pointing_curves": str(pointing_path),
    }
    _serialize_json(manifest, output_dir / "summary.json")
    return manifest
