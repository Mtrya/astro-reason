"""Solution inspection visualizer for aeossp_standard."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
import math
from pathlib import Path
from typing import Any

import brahe
import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from ..verifier import analyze_solution
from ..verifier.models import (
    BatteryTraceSegment,
    ManeuverWindow,
    SolutionAnalysis,
    ValidatedAction,
)
from .plot import (
    DEFAULT_PLOTS_DIR,
    _TASK_COLORS,
    _draw_world_texture,
    _sanitize_axes,
    _serialize_json,
    _source_kind,
)


_WORLD_LIMITS = (-180.0, 180.0, -90.0, 90.0)
_OBS_COLOR = "#1d4ed8"
_INVALID_COLOR = "#dc2626"
_MANEUVER_COLOR = "#d97706"
_SATELLITE_FAINT = "#64748b"


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%m-%d %H:%M:%S UTC")


def _ensure_brahe_ready() -> None:
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )


def _datetime_to_epoch(value: datetime) -> brahe.Epoch:
    value = value.astimezone(UTC)
    second = float(value.second) + (value.microsecond / 1_000_000.0)
    return brahe.Epoch.from_datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        second,
        0.0,
        brahe.TimeSystem.UTC,
    )


def _task_color(task: Any, *, completed: bool) -> str:
    if not completed:
        return "#cbd5e1"
    return _TASK_COLORS[(_source_kind({"name": task.name}), task.required_sensor_type)]


def _task_marker(task: Any) -> str:
    return "^" if str(task.name).startswith("background_") else "o"


def _split_track_segments(longitudes_deg: np.ndarray, latitudes_deg: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
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


def _active_satellite_ids(analysis: SolutionAnalysis) -> list[str]:
    ids = {
        action.satellite_id
        for action in analysis.validated_actions
    }
    ids.update(window.satellite_id for window in analysis.maneuver_windows)
    ids.update(
        failure.satellite_id
        for failure in analysis.action_failures
        if failure.satellite_id in analysis.case.satellites
    )
    return sorted(ids)


def _action_lookup(analysis: SolutionAnalysis) -> dict[int, Any]:
    return {
        index: action
        for index, action in enumerate(analysis.solution.actions)
    }


def _validated_actions_by_satellite(
    analysis: SolutionAnalysis,
) -> dict[str, list[ValidatedAction]]:
    grouped: dict[str, list[ValidatedAction]] = defaultdict(list)
    for action in analysis.validated_actions:
        grouped[action.satellite_id].append(action)
    for satellite_id in grouped:
        grouped[satellite_id].sort(key=lambda item: (item.start_time, item.end_time, item.action_index))
    return grouped


def _maneuver_windows_by_satellite(
    analysis: SolutionAnalysis,
) -> dict[str, list[ManeuverWindow]]:
    grouped: dict[str, list[ManeuverWindow]] = defaultdict(list)
    for window in analysis.maneuver_windows:
        grouped[window.satellite_id].append(window)
    for satellite_id in grouped:
        grouped[satellite_id].sort(key=lambda item: (item.start_time, item.end_time, item.action_index))
    return grouped


def _build_propagators(case: Any, satellite_ids: set[str] | None = None) -> dict[str, brahe.SGPPropagator]:
    _ensure_brahe_ready()
    selected_ids = satellite_ids or set(case.satellites)
    return {
        sat_id: brahe.SGPPropagator.from_tle(
            case.satellites[sat_id].tle_line1,
            case.satellites[sat_id].tle_line2,
            float(case.mission.geometry_sample_step_s),
        )
        for sat_id in sorted(selected_ids)
    }


def _satellite_lon_lat(
    propagators: dict[str, brahe.SGPPropagator],
    satellite_id: str,
    instant: datetime,
) -> tuple[float, float]:
    epoch = _datetime_to_epoch(instant)
    state_ecef = np.asarray(propagators[satellite_id].state_ecef(epoch), dtype=float).reshape(6)
    lon_deg, lat_deg, _alt_m = brahe.position_ecef_to_geodetic(
        state_ecef[:3],
        brahe.AngleFormat.DEGREES,
    )
    return float(lon_deg), float(lat_deg)


def _target_lon_lat(task: Any) -> tuple[float, float]:
    return float(task.longitude_deg), float(task.latitude_deg)


def _active_valid_actions(analysis: SolutionAnalysis, instant: datetime) -> list[ValidatedAction]:
    return [
        action
        for action in analysis.validated_actions
        if action.start_time <= instant < action.end_time
    ]


def _active_maneuvers(analysis: SolutionAnalysis, instant: datetime) -> list[ManeuverWindow]:
    return [
        window
        for window in analysis.maneuver_windows
        if window.start_time <= instant < window.end_time
    ]


def _failures_at_time(analysis: SolutionAnalysis, instant: datetime) -> list[Any]:
    return [
        failure
        for failure in analysis.action_failures
        if failure.time is not None and abs((failure.time - instant).total_seconds()) < 0.5
    ]


def _completed_count_by_time(analysis: SolutionAnalysis, instant: datetime) -> int:
    return sum(
        1
        for outcome in analysis.task_outcomes.values()
        if outcome.completion_time is not None and outcome.completion_time <= instant
    )


def _pick_snapshot_times(
    analysis: SolutionAnalysis,
    *,
    max_snapshots: int = 6,
) -> list[datetime]:
    candidates: list[datetime] = []

    def _add_candidate(value: datetime | None) -> None:
        if value is None:
            return
        candidates.append(value.astimezone(UTC))

    for action in analysis.validated_actions[:2]:
        midpoint = action.start_time + ((action.end_time - action.start_time) / 2)
        _add_candidate(midpoint)

    failure_times = [failure.time for failure in analysis.action_failures if failure.time is not None]
    if failure_times:
        _add_candidate(min(failure_times))

    stressed_satellite_id = None
    stressed_minimum = math.inf
    for satellite_id, summary in analysis.per_satellite_resource_summary.items():
        minimum = summary.get("minimum_battery_wh")
        if isinstance(minimum, (int, float)) and minimum < stressed_minimum:
            stressed_minimum = float(minimum)
            stressed_satellite_id = satellite_id
    if stressed_satellite_id is not None:
        minimum_time = analysis.per_satellite_resource_summary[stressed_satellite_id].get("minimum_battery_time")
        if isinstance(minimum_time, str):
            _add_candidate(
                datetime.fromisoformat(minimum_time.replace("Z", "+00:00")).astimezone(UTC)
            )

    for action in analysis.validated_actions:
        midpoint = action.start_time + ((action.end_time - action.start_time) / 2)
        _add_candidate(midpoint)
    for value in analysis.snapshot_candidates:
        _add_candidate(value)

    selected: list[datetime] = []
    for candidate in candidates:
        if any(abs((candidate - existing).total_seconds()) < 60.0 for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= max_snapshots:
            break
    return selected


def _render_timeline_png(
    analysis: SolutionAnalysis,
    output_path: Path,
) -> Path:
    active_satellite_ids = _active_satellite_ids(analysis)
    action_lookup = _action_lookup(analysis)
    actions_by_satellite = defaultdict(list)
    for index, action in action_lookup.items():
        actions_by_satellite[action.satellite_id].append((index, action))
    for satellite_id in actions_by_satellite:
        actions_by_satellite[satellite_id].sort(key=lambda item: (item[1].start_time, item[1].end_time, item[0]))
    failures_by_action = {
        failure.action_index: failure
        for failure in analysis.action_failures
        if failure.action_index >= 0
    }
    maneuvers_by_satellite = _maneuver_windows_by_satellite(analysis)

    if not active_satellite_ids:
        active_satellite_ids = sorted(analysis.case.satellites)[: min(6, len(analysis.case.satellites))]

    figure_height = max(6.5, 0.8 * len(active_satellite_ids) + 2.5)
    figure = plt.figure(figsize=(17, figure_height), constrained_layout=True)
    grid = figure.add_gridspec(1, 2, width_ratios=[4.6, 1.4], wspace=0.04)
    axis = figure.add_subplot(grid[0, 0])
    summary_axis = figure.add_subplot(grid[0, 1])
    _sanitize_axes(axis)
    summary_axis.axis("off")

    row_height = 0.8
    row_positions = {
        satellite_id: (len(active_satellite_ids) - idx - 1)
        for idx, satellite_id in enumerate(active_satellite_ids)
    }

    for satellite_id in active_satellite_ids:
        y = row_positions[satellite_id]
        for window in maneuvers_by_satellite.get(satellite_id, []):
            axis.broken_barh(
                [
                    (
                        mdates.date2num(window.start_time),
                        mdates.date2num(window.end_time) - mdates.date2num(window.start_time),
                    )
                ],
                (y - row_height / 2.0, row_height),
                facecolors=_MANEUVER_COLOR,
                edgecolors="none",
                alpha=0.45,
            )
        for action_index, action in actions_by_satellite.get(satellite_id, []):
            failure = failures_by_action.get(action_index)
            color = _INVALID_COLOR if failure is not None else _OBS_COLOR
            axis.broken_barh(
                [
                    (
                        mdates.date2num(action.start_time),
                        mdates.date2num(action.end_time) - mdates.date2num(action.start_time),
                    )
                ],
                (y - row_height / 3.0, row_height * 0.66),
                facecolors=color,
                edgecolors="none",
                alpha=0.9,
            )
            if failure is not None and failure.time is not None:
                axis.scatter(
                    [failure.time],
                    [y],
                    color="#7f1d1d",
                    s=18,
                    zorder=5,
                )

    axis.set_yticks([row_positions[sat_id] for sat_id in active_satellite_ids])
    axis.set_yticklabels(active_satellite_ids, fontsize=9)
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    axis.set_xlabel("UTC")
    axis.set_title(f"{analysis.case.mission.case_id} solution timeline")
    axis.grid(True, axis="x", color="#d5dbe3", linewidth=0.8, alpha=0.7)

    summary_lines = [
        f"Valid: {analysis.result.valid}",
        f"CR: {analysis.result.metrics['CR']:.6f}",
        f"WCR: {analysis.result.metrics['WCR']:.6f}",
        f"TAT: {analysis.result.metrics['TAT']}",
        f"PC: {analysis.result.metrics['PC']:.3f}",
        "",
        f"Actions: {len(analysis.solution.actions)}",
        f"Validated: {len(analysis.validated_actions)}",
        f"Failures: {len(analysis.action_failures)}",
        f"Completed tasks: {sum(1 for outcome in analysis.task_outcomes.values() if outcome.completed)}",
    ]
    if analysis.action_failures:
        first_failure = min(
            analysis.action_failures,
            key=lambda failure: (
                failure.time or analysis.case.mission.horizon_start,
                failure.action_index,
            ),
        )
        summary_lines.extend(
            [
                "",
                "First failure:",
                f"  stage: {first_failure.stage}",
                f"  action: {first_failure.action_index}",
                f"  time: {_utc_text(first_failure.time) if first_failure.time else 'n/a'}",
            ]
        )
    summary_axis.text(
        0.02,
        0.98,
        "\n".join(summary_lines),
        ha="left",
        va="top",
        fontsize=10.5,
        family="monospace",
        color="#1f2933",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return output_path


def _render_task_outcomes_png(
    analysis: SolutionAnalysis,
    output_path: Path,
    *,
    texture_path: Path | None,
) -> Path:
    figure = plt.figure(figsize=(15, 8.5), constrained_layout=True)
    grid = figure.add_gridspec(1, 2, width_ratios=[3.7, 1.3])
    axis = figure.add_subplot(grid[0, 0])
    summary_axis = figure.add_subplot(grid[0, 1])
    _sanitize_axes(axis)
    _draw_world_texture(axis, texture_path=texture_path)
    axis.set_xlim(_WORLD_LIMITS[0], _WORLD_LIMITS[1])
    axis.set_ylim(_WORLD_LIMITS[2], _WORLD_LIMITS[3])
    axis.set_xlabel("Longitude (deg)")
    axis.set_ylabel("Latitude (deg)")
    axis.set_title(f"{analysis.case.mission.case_id} task outcomes")

    completed_ids = {
        task_id
        for task_id, outcome in analysis.task_outcomes.items()
        if outcome.completed
    }

    completed_tasks = []
    uncompleted_tasks = []
    for task in analysis.case.tasks.values():
        if task.task_id in completed_ids:
            completed_tasks.append(task)
        else:
            uncompleted_tasks.append(task)

    if uncompleted_tasks:
        axis.scatter(
            [task.longitude_deg for task in uncompleted_tasks],
            [task.latitude_deg for task in uncompleted_tasks],
            s=12,
            color="#cbd5e1",
            alpha=0.55,
            edgecolors="none",
            label="uncompleted",
            zorder=2,
        )

    for sensor_type in ("visible", "infrared"):
        for source_kind in ("city", "background"):
            group = [
                task
                for task in completed_tasks
                if task.required_sensor_type == sensor_type
                and _source_kind({"name": task.name}) == source_kind
            ]
            if not group:
                continue
            axis.scatter(
                [task.longitude_deg for task in group],
                [task.latitude_deg for task in group],
                s=26 if source_kind == "city" else 22,
                marker="o" if source_kind == "city" else "^",
                color=_TASK_COLORS[(source_kind, sensor_type)],
                alpha=0.9,
                edgecolors="#0f172a",
                linewidths=0.2,
                label=f"completed {source_kind} / {sensor_type}",
                zorder=3,
            )
    for task_id, outcome in analysis.task_outcomes.items():
        if not outcome.completed:
            continue
        task = analysis.case.tasks[task_id]
        axis.text(
            task.longitude_deg,
            task.latitude_deg,
            task_id,
            fontsize=6.3,
            color="#111827",
            ha="left",
            va="bottom",
            zorder=4,
        )

    completed_count = len(completed_ids)
    summary_axis.axis("off")
    summary_axis.text(
        0.02,
        0.98,
        "\n".join(
            [
                f"Completed: {completed_count}/{len(analysis.case.tasks)}",
                f"CR: {analysis.result.metrics['CR']:.6f}",
                f"WCR: {analysis.result.metrics['WCR']:.6f}",
                "",
                "Legend:",
                "  gray: uncompleted",
                "  colored: completed",
                "  circle: city",
                "  triangle: background",
            ]
        ),
        ha="left",
        va="top",
        fontsize=10.5,
        family="monospace",
        color="#1f2933",
    )

    axis.legend(loc="lower left", fontsize=8, frameon=True, framealpha=0.9)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return output_path


def _choose_battery_satellites(analysis: SolutionAnalysis, *, limit: int = 8) -> list[str]:
    ranked = sorted(
        analysis.per_satellite_resource_summary.items(),
        key=lambda item: (
            item[1].get("minimum_battery_wh", math.inf),
            item[0],
        ),
    )
    interesting = [sat_id for sat_id, summary in ranked if summary.get("total_imaging_time_s", 0.0) > 0.0]
    for sat_id, _summary in ranked:
        if sat_id not in interesting:
            interesting.append(sat_id)
    return interesting[:limit]


def _render_battery_traces_png(
    analysis: SolutionAnalysis,
    output_path: Path,
) -> Path:
    selected_satellites = _choose_battery_satellites(analysis)
    if not selected_satellites:
        selected_satellites = sorted(analysis.case.satellites)[:1]

    n_cols = 2 if len(selected_satellites) > 1 else 1
    n_rows = int(math.ceil(len(selected_satellites) / n_cols))
    figure, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(15, max(4.5, 3.3 * n_rows)),
        constrained_layout=True,
        squeeze=False,
    )
    flat_axes = axes.ravel()
    for ax in flat_axes:
        _sanitize_axes(ax)

    for ax, satellite_id in zip(flat_axes, selected_satellites, strict=False):
        trace = analysis.battery_traces.get(satellite_id, tuple())
        if not trace:
            ax.text(0.5, 0.5, "No trace", ha="center", va="center", color="#475569")
            ax.set_axis_off()
            continue
        times = [trace[0].start_time] + [segment.end_time for segment in trace]
        levels = [trace[0].battery_start_wh] + [segment.battery_end_wh for segment in trace]
        ax.plot(times, levels, color="#1d4ed8", linewidth=1.6)
        for segment in trace:
            if segment.mode == "observation":
                color = "#93c5fd"
            elif segment.mode == "slew":
                color = "#fdba74"
            elif segment.mode == "observation+slew":
                color = "#c084fc"
            else:
                continue
            ax.axvspan(segment.start_time, segment.end_time, color=color, alpha=0.35)
        summary = analysis.per_satellite_resource_summary.get(satellite_id, {})
        minimum_time = summary.get("minimum_battery_time")
        if isinstance(minimum_time, str):
            min_time_dt = datetime.fromisoformat(minimum_time.replace("Z", "+00:00")).astimezone(UTC)
            ax.axvline(min_time_dt, color="#be123c", linestyle="--", linewidth=1.0)
        ax.set_title(satellite_id, fontsize=10)
        ax.set_ylabel("Battery (Wh)")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.tick_params(axis="x", labelrotation=25)

    for ax in flat_axes[len(selected_satellites):]:
        ax.set_axis_off()

    figure.suptitle(f"{analysis.case.mission.case_id} battery traces", fontsize=14)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return output_path


def _off_nadir_deg(satellite_position_ecef_m: np.ndarray, target_ecef_m: np.ndarray) -> float:
    a = -satellite_position_ecef_m
    b = target_ecef_m - satellite_position_ecef_m
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a <= 1.0e-9 or norm_b <= 1.0e-9:
        return 0.0
    cosine = float(np.dot(a, b) / (norm_a * norm_b))
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _off_nadir_at_time(
    propagator: brahe.SGPPropagator,
    task: Any,
    instant: datetime,
) -> float:
    epoch = _datetime_to_epoch(instant)
    state_ecef = np.asarray(propagator.state_ecef(epoch), dtype=float).reshape(6)
    return _off_nadir_deg(state_ecef[:3], np.asarray(task.target_ecef_m, dtype=float))


def _derived_attitude_curve(
    analysis: SolutionAnalysis,
    satellite_id: str,
    propagator: brahe.SGPPropagator,
) -> tuple[list[datetime], list[float], datetime, datetime]:
    actions = _validated_actions_by_satellite(analysis).get(satellite_id, [])
    maneuvers = _maneuver_windows_by_satellite(analysis).get(satellite_id, [])
    if actions:
        start_time = min(
            min(action.start_time for action in actions),
            min((window.start_time for window in maneuvers), default=actions[0].start_time),
        ) - timedelta(seconds=20)
        end_time = max(action.end_time for action in actions) + timedelta(seconds=20)
    elif maneuvers:
        start_time = min(window.start_time for window in maneuvers) - timedelta(seconds=20)
        end_time = max(window.end_time for window in maneuvers) + timedelta(seconds=20)
    else:
        start_time = analysis.case.mission.horizon_start
        end_time = start_time + timedelta(minutes=10)

    actions_by_index = {action.action_index: action for action in actions}
    task_lookup = analysis.case.tasks
    settling_time_s = analysis.case.satellites[satellite_id].attitude_model.settling_time_s

    instants: list[datetime] = []
    values: list[float] = []
    current = start_time
    while current <= end_time:
        angle_deg = 0.0
        active_action = next(
            (action for action in actions if action.start_time <= current < action.end_time),
            None,
        )
        if active_action is not None:
            angle_deg = _off_nadir_at_time(propagator, task_lookup[active_action.task_id], current)
        else:
            active_window = next(
                (window for window in maneuvers if window.start_time <= current < window.end_time),
                None,
            )
            if active_window is not None:
                target_action = actions_by_index.get(active_window.action_index)
                target_angle = (
                    _off_nadir_at_time(propagator, task_lookup[target_action.task_id], target_action.start_time)
                    if target_action is not None
                    else 0.0
                )
                if active_window.from_action_index is None:
                    from_angle = 0.0
                else:
                    previous_action = actions_by_index.get(active_window.from_action_index)
                    from_angle = (
                        _off_nadir_at_time(propagator, task_lookup[previous_action.task_id], previous_action.end_time)
                        if previous_action is not None
                        else 0.0
                    )
                slew_only_s = max(0.0, active_window.required_gap_s - settling_time_s)
                settling_start = active_window.end_time - timedelta(seconds=settling_time_s)
                if current >= settling_start or slew_only_s <= 1.0e-9:
                    angle_deg = target_angle
                else:
                    progress = (current - active_window.start_time).total_seconds() / max(slew_only_s, 1.0e-9)
                    progress = max(0.0, min(1.0, progress))
                    angle_deg = from_angle + ((target_angle - from_angle) * progress)
        instants.append(current)
        values.append(angle_deg)
        current += timedelta(seconds=1)
    return instants, values, start_time, end_time


def _choose_attitude_satellites(analysis: SolutionAnalysis, *, limit: int = 6) -> list[str]:
    active = _active_satellite_ids(analysis)
    return active[:limit]


def _render_attitude_curves_png(
    analysis: SolutionAnalysis,
    output_path: Path,
) -> Path:
    selected_satellites = _choose_attitude_satellites(analysis)
    if not selected_satellites:
        selected_satellites = sorted(analysis.case.satellites)[:1]
    propagators = _build_propagators(analysis.case, set(selected_satellites))

    n_cols = 2 if len(selected_satellites) > 1 else 1
    n_rows = int(math.ceil(len(selected_satellites) / n_cols))
    figure, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(15, max(4.5, 3.3 * n_rows)),
        constrained_layout=True,
        squeeze=False,
    )
    flat_axes = axes.ravel()
    maneuvers_by_satellite = _maneuver_windows_by_satellite(analysis)
    actions_by_satellite = _validated_actions_by_satellite(analysis)

    for ax in flat_axes:
        _sanitize_axes(ax)

    for ax, satellite_id in zip(flat_axes, selected_satellites, strict=False):
        instants, values, _start_time, _end_time = _derived_attitude_curve(
            analysis,
            satellite_id,
            propagators[satellite_id],
        )
        ax.plot(instants, values, color="#1d4ed8", linewidth=1.5)
        for window in maneuvers_by_satellite.get(satellite_id, []):
            ax.axvspan(window.start_time, window.end_time, color="#fdba74", alpha=0.35)
        for action in actions_by_satellite.get(satellite_id, []):
            ax.axvspan(action.start_time, action.end_time, color="#93c5fd", alpha=0.4)
        for failure in analysis.action_failures:
            if failure.satellite_id == satellite_id and failure.time is not None:
                ax.axvline(failure.time, color="#dc2626", linestyle="--", linewidth=1.0)
        max_off_nadir = analysis.case.satellites[satellite_id].attitude_model.max_off_nadir_deg
        ax.axhline(max_off_nadir, color="#be185d", linestyle=":", linewidth=1.0)
        ax.set_title(satellite_id, fontsize=10)
        ax.set_ylabel("Off-nadir (deg)")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        ax.tick_params(axis="x", labelrotation=25)

    for ax in flat_axes[len(selected_satellites):]:
        ax.set_axis_off()

    figure.suptitle(f"{analysis.case.mission.case_id} derived attitude curves", fontsize=14)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return output_path


def _render_snapshot_png(
    analysis: SolutionAnalysis,
    instant: datetime,
    output_path: Path,
    *,
    texture_path: Path | None,
    propagators: dict[str, brahe.SGPPropagator],
) -> Path:
    figure = plt.figure(figsize=(15, 8.5), constrained_layout=True)
    grid = figure.add_gridspec(1, 2, width_ratios=[3.8, 1.3])
    axis = figure.add_subplot(grid[0, 0])
    summary_axis = figure.add_subplot(grid[0, 1])
    _sanitize_axes(axis)
    _draw_world_texture(axis, texture_path=texture_path)
    axis.set_xlim(_WORLD_LIMITS[0], _WORLD_LIMITS[1])
    axis.set_ylim(_WORLD_LIMITS[2], _WORLD_LIMITS[3])
    axis.set_xlabel("Longitude (deg)")
    axis.set_ylabel("Latitude (deg)")
    axis.set_title(f"{analysis.case.mission.case_id} snapshot @ {_utc_text(instant)}")

    completed_ids = {
        task_id
        for task_id, outcome in analysis.task_outcomes.items()
        if outcome.completed
    }
    axis.scatter(
        [task.longitude_deg for task in analysis.case.tasks.values()],
        [task.latitude_deg for task in analysis.case.tasks.values()],
        s=9,
        color="#cbd5e1",
        alpha=0.35,
        edgecolors="none",
        zorder=1,
    )
    for task_id in completed_ids:
        task = analysis.case.tasks[task_id]
        axis.scatter(
            [task.longitude_deg],
            [task.latitude_deg],
            s=20,
            marker=_task_marker(task),
            color=_task_color(task, completed=True),
            alpha=0.85,
            edgecolors="#0f172a",
            linewidths=0.2,
            zorder=2,
        )

    all_satellite_ids = sorted(analysis.case.satellites)
    sat_lons = []
    sat_lats = []
    for satellite_id in all_satellite_ids:
        lon_deg, lat_deg = _satellite_lon_lat(propagators, satellite_id, instant)
        sat_lons.append(lon_deg)
        sat_lats.append(lat_deg)
    axis.scatter(
        sat_lons,
        sat_lats,
        s=10,
        color=_SATELLITE_FAINT,
        alpha=0.35,
        zorder=2,
    )

    active_actions = _active_valid_actions(analysis, instant)
    active_maneuvers = _active_maneuvers(analysis, instant)
    failures = _failures_at_time(analysis, instant)
    highlight_lines: list[str] = []

    for action in active_actions:
        task = analysis.case.tasks[action.task_id]
        sat_lon, sat_lat = _satellite_lon_lat(propagators, action.satellite_id, instant)
        task_lon, task_lat = _target_lon_lat(task)
        axis.scatter([sat_lon], [sat_lat], s=44, color=_OBS_COLOR, zorder=4)
        axis.plot([sat_lon, task_lon], [sat_lat, task_lat], color=_OBS_COLOR, linewidth=1.2, alpha=0.9, zorder=3)
        highlight_lines.append(f"obs {action.satellite_id} -> {action.task_id}")

    for window in active_maneuvers:
        sat_lon, sat_lat = _satellite_lon_lat(propagators, window.satellite_id, instant)
        axis.scatter([sat_lon], [sat_lat], s=42, color=_MANEUVER_COLOR, zorder=4)
        highlight_lines.append(f"slew {window.satellite_id} -> {window.to_task_id}")

    for failure in failures:
        if failure.action_index >= 0:
            raw_action = analysis.solution.actions[failure.action_index]
            if failure.satellite_id in analysis.case.satellites and failure.task_id in analysis.case.tasks:
                sat_lon, sat_lat = _satellite_lon_lat(propagators, failure.satellite_id, instant)
                task = analysis.case.tasks[failure.task_id]
                task_lon, task_lat = _target_lon_lat(task)
                axis.scatter([sat_lon], [sat_lat], s=48, color=_INVALID_COLOR, zorder=5)
                axis.plot(
                    [sat_lon, task_lon],
                    [sat_lat, task_lat],
                    color=_INVALID_COLOR,
                    linewidth=1.3,
                    alpha=0.95,
                    zorder=4,
                )
                highlight_lines.append(f"fail a{failure.action_index}: {raw_action.task_id}")

    summary_axis.axis("off")
    summary_lines = [
        f"Time: {_utc_text(instant)}",
        f"Valid result: {analysis.result.valid}",
        f"Completed so far: {_completed_count_by_time(analysis, instant)}/{len(analysis.case.tasks)}",
        f"Active observations: {len(active_actions)}",
        f"Active maneuvers: {len(active_maneuvers)}",
        f"Failures here: {len(failures)}",
        "",
        "Highlights:",
    ]
    if highlight_lines:
        summary_lines.extend(f"  {line}" for line in highlight_lines[:8])
    else:
        summary_lines.append("  none")
    summary_axis.text(
        0.02,
        0.98,
        "\n".join(summary_lines),
        ha="left",
        va="top",
        fontsize=10.0,
        family="monospace",
        color="#1f2933",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return output_path


def _build_summary(
    analysis: SolutionAnalysis,
    *,
    artifact_names: dict[str, Any],
    snapshot_times: list[datetime],
) -> dict[str, Any]:
    completed_count = sum(1 for outcome in analysis.task_outcomes.values() if outcome.completed)
    return {
        "case_id": analysis.case.mission.case_id,
        "valid": analysis.result.valid,
        "metrics": analysis.result.metrics,
        "num_actions": len(analysis.solution.actions),
        "num_validated_actions": len(analysis.validated_actions),
        "num_failures": len(analysis.action_failures),
        "completed_task_count": completed_count,
        "per_satellite_battery_minima_wh": {
            satellite_id: summary.get("minimum_battery_wh")
            for satellite_id, summary in analysis.per_satellite_resource_summary.items()
        },
        "selected_snapshot_times": [_iso_z(instant) for instant in snapshot_times],
        "artifacts": artifact_names,
    }


def render_solution_bundle(
    case_dir: str | Path,
    solution_path: str | Path,
    out_dir: str | Path | None = None,
    *,
    texture_path: str | Path | None = None,
) -> dict[str, Any]:
    analysis = analyze_solution(case_dir, solution_path)
    case_dir_path = Path(case_dir).resolve()
    solution_path_obj = Path(solution_path).resolve()
    output_dir = (
        Path(out_dir).resolve()
        if out_dir is not None
        else (DEFAULT_PLOTS_DIR / case_dir_path.name / "solution" / solution_path_obj.stem).resolve()
    )
    texture = Path(texture_path).resolve() if texture_path is not None else None

    propagators = _build_propagators(analysis.case)

    timeline_path = output_dir / "timeline.png"
    task_outcomes_path = output_dir / "task_outcomes.png"
    battery_path = output_dir / "battery_traces.png"
    attitude_path = output_dir / "attitude_curves.png"

    _render_timeline_png(analysis, timeline_path)
    _render_task_outcomes_png(analysis, task_outcomes_path, texture_path=texture)
    _render_battery_traces_png(analysis, battery_path)
    _render_attitude_curves_png(analysis, attitude_path)

    snapshot_times = _pick_snapshot_times(analysis)
    snapshots_dir = output_dir / "snapshots"
    snapshot_paths: list[str] = []
    for index, instant in enumerate(snapshot_times, start=1):
        snapshot_path = snapshots_dir / f"snapshot_{index:02d}.png"
        _render_snapshot_png(
            analysis,
            instant,
            snapshot_path,
            texture_path=texture,
            propagators=propagators,
        )
        snapshot_paths.append(snapshot_path.name)

    artifact_names = {
        "timeline_png": timeline_path.name,
        "task_outcomes_png": task_outcomes_path.name,
        "battery_traces_png": battery_path.name,
        "attitude_curves_png": attitude_path.name,
        "snapshot_pngs": snapshot_paths,
    }
    summary = _build_summary(
        analysis,
        artifact_names=artifact_names,
        snapshot_times=snapshot_times,
    )
    _serialize_json(summary, output_dir / "summary.json")
    return summary
