"""Solution inspection visualizer for relay_constellation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
import textwrap

import brahe
import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from ..verifier import analyze_solution
from ..verifier.models import (
    ActionFailure,
    SampleAllocation,
    SolutionAnalysis,
    ValidatedAction,
)
from .geometry import build_state_cache_for_satellites
from .plot import (
    coarsen_ground_track_cache,
    _route_color,
    render_ground_tracks_png,
)


def _utc_text(value: datetime) -> str:
    return value.strftime("%m-%d %H:%M UTC")


def _demand_lookup(analysis: SolutionAnalysis) -> dict[str, object]:
    return {
        demand.demand_id: demand
        for demand in analysis.case.demands
    }


def _validated_actions_by_index(analysis: SolutionAnalysis) -> dict[int, ValidatedAction]:
    return {
        action.action_index: action
        for action in analysis.validated_actions
    }


def _allocations_by_sample(analysis: SolutionAnalysis) -> dict[int, SampleAllocation]:
    return {
        allocation.sample_index: allocation
        for allocation in analysis.sample_allocations
    }


def _route_signature(allocation: SampleAllocation) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (route.demand_id, route.nodes)
        for route in allocation.served_routes
    )


def _metric_text(value: object, *, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int | float):
        return f"{float(value):.{digits}f}"
    return str(value)


def _pick_snapshot_indices(analysis: SolutionAnalysis, *, max_snapshots: int = 6) -> list[int]:
    chosen: list[int] = []
    seen: set[int] = set()

    def _add(sample_index: int | None) -> None:
        if sample_index is None or sample_index in seen:
            return
        seen.add(sample_index)
        chosen.append(sample_index)

    for allocation in analysis.sample_allocations:
        if allocation.served_routes:
            _add(allocation.sample_index)
            break
    for allocation in analysis.sample_allocations:
        if allocation.active_demand_ids and not allocation.served_routes:
            _add(allocation.sample_index)
            break

    seen_signatures: set[tuple[tuple[str, tuple[str, ...]], ...]] = set()
    for allocation in analysis.sample_allocations:
        signature = _route_signature(allocation)
        if not signature or signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        _add(allocation.sample_index)

    for failure in analysis.action_failures:
        _add(failure.sample_index)

    return chosen[:max_snapshots]


def _contiguous_intervals(sample_indices: list[int]) -> list[tuple[int, int]]:
    if not sample_indices:
        return []
    intervals: list[tuple[int, int]] = []
    start = sample_indices[0]
    prev = sample_indices[0]
    for sample_index in sample_indices[1:]:
        if sample_index == prev + 1:
            prev = sample_index
            continue
        intervals.append((start, prev + 1))
        start = sample_index
        prev = sample_index
    intervals.append((start, prev + 1))
    return intervals


def _interval_datetimes(
    analysis: SolutionAnalysis,
    start_index: int,
    end_exclusive_index: int,
) -> tuple[datetime, datetime]:
    start_time = analysis.case.manifest.horizon_start + timedelta(
        seconds=start_index * analysis.case.manifest.routing_step_s
    )
    end_time = analysis.case.manifest.horizon_start + timedelta(
        seconds=end_exclusive_index * analysis.case.manifest.routing_step_s
    )
    return start_time, end_time


def _route_intervals_by_demand(
    analysis: SolutionAnalysis,
) -> dict[str, list[tuple[int, int, tuple[str, ...]]]]:
    grouped: dict[str, list[tuple[int, tuple[str, ...]]]] = defaultdict(list)
    for allocation in analysis.sample_allocations:
        for route in allocation.served_routes:
            grouped[route.demand_id].append((allocation.sample_index, route.nodes))

    collapsed: dict[str, list[tuple[int, int, tuple[str, ...]]]] = {}
    for demand_id, samples in grouped.items():
        if not samples:
            collapsed[demand_id] = []
            continue
        samples.sort()
        start_index, prev_index, route_nodes = samples[0][0], samples[0][0], samples[0][1]
        intervals: list[tuple[int, int, tuple[str, ...]]] = []
        for sample_index, current_nodes in samples[1:]:
            if current_nodes == route_nodes and sample_index == prev_index + 1:
                prev_index = sample_index
                continue
            intervals.append((start_index, prev_index + 1, route_nodes))
            start_index = sample_index
            prev_index = sample_index
            route_nodes = current_nodes
        intervals.append((start_index, prev_index + 1, route_nodes))
        collapsed[demand_id] = intervals
    return collapsed


def _route_color_legend(
    intervals: list[tuple[int, int, tuple[str, ...]]],
) -> list[tuple[str, tuple[str, ...]]]:
    seen: dict[tuple[str, ...], str] = {}
    for _, _, route_nodes in intervals:
        if route_nodes in seen:
            continue
        seen[route_nodes] = f"R{len(seen) + 1}"
    return [(label, route_nodes) for route_nodes, label in seen.items()]


def _action_timeline_records(
    analysis: SolutionAnalysis,
) -> list[dict[str, object]]:
    validated_by_index = _validated_actions_by_index(analysis)
    failures_by_index: dict[int, ActionFailure] = {
        failure.action_index: failure
        for failure in analysis.action_failures
    }
    records: list[dict[str, object]] = []
    for action_index, action in enumerate(analysis.solution.actions):
        label = action.action_type
        if action.action_type == "ground_link":
            label = f"{action.action_type} {action.endpoint_id} <-> {action.satellite_id}"
        elif action.action_type == "inter_satellite_link":
            label = (
                f"{action.action_type} {action.satellite_id_1} <-> {action.satellite_id_2}"
            )
        status = "valid" if action_index in validated_by_index else "invalid"
        records.append(
            {
                "action_index": action_index,
                "label": label,
                "status": status,
                "start_time": action.start_time,
                "end_time": action.end_time,
                "failure": failures_by_index.get(action_index),
                "action_type": action.action_type,
            }
        )
    records.sort(
        key=lambda row: (
            0 if row["action_type"] == "ground_link" else 1,
            row["start_time"],
            row["action_index"],
        )
    )
    return records


def _render_scheduled_connectivity_png(
    analysis: SolutionAnalysis,
    output_path: Path,
) -> Path:
    demand_lookup = _demand_lookup(analysis)
    route_intervals = _route_intervals_by_demand(analysis)
    demand_rows = sorted(demand_lookup)
    total_rows = len(demand_rows)
    figure_height = max(5.0, 0.42 * total_rows + 2.5)
    figure = plt.figure(figsize=(18, figure_height))
    grid = figure.add_gridspec(1, 2, width_ratios=[4.0, 1.4], wspace=0.08)
    axis = figure.add_subplot(grid[0, 0])
    summary_axis = figure.add_subplot(grid[0, 1])
    axis.set_facecolor("#f7f8fa")
    summary_axis.axis("off")

    bar_height = 0.8
    demand_y = {
        demand_id: (len(demand_rows) - row_index - 1)
        for row_index, demand_id in enumerate(demand_rows)
    }

    for demand_id in demand_rows:
        demand = demand_lookup[demand_id]
        y = demand_y[demand_id]
        axis.broken_barh(
            [
                (
                    mdates.date2num(demand.start_time),
                    mdates.date2num(demand.end_time) - mdates.date2num(demand.start_time),
                )
            ],
            (y - bar_height / 2.0, bar_height),
            facecolors="#d5dbe3",
            edgecolors="none",
            alpha=0.75,
        )
        for start_index, end_index, route_nodes in route_intervals.get(demand_id, []):
            start_time, end_time = _interval_datetimes(analysis, start_index, end_index)
            axis.broken_barh(
                [
                    (
                        mdates.date2num(start_time),
                        mdates.date2num(end_time) - mdates.date2num(start_time),
                    )
                ],
                (y - bar_height / 2.0, bar_height),
                facecolors=_route_color(route_nodes),
                edgecolors="none",
                alpha=0.95,
            )

    yticks: list[float] = []
    ylabels: list[str] = []
    for demand_id in demand_rows:
        metrics = analysis.result.metrics["per_demand"].get(demand_id, {})
        service_fraction = metrics.get("service_fraction")
        yticks.append(demand_y[demand_id])
        service_text = "n/a" if service_fraction is None else f"{service_fraction:.2f}"
        ylabels.append(f"{demand_id} ({service_text})")

    axis.set_yticks(yticks)
    axis.set_yticklabels(ylabels, fontsize=8)
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    axis.grid(True, axis="x", color="#d5dbe3", linewidth=0.7, alpha=0.7)
    axis.set_title(
        f"{analysis.case.manifest.case_id}: scheduled connectivity",
        fontsize=15,
        fontweight="bold",
    )
    axis.set_xlabel("UTC time")

    legend_handles = [
        Line2D([0], [0], color="#d5dbe3", linewidth=8, label="Demanded window"),
        Line2D([0], [0], color="#1d4ed8", linewidth=8, label="Served routes"),
    ]
    axis.legend(handles=legend_handles, loc="upper right", frameon=True)

    summary_lines = [
        f"Valid: {analysis.result.valid}",
        f"Service fraction: {_metric_text(analysis.result.metrics['service_fraction'])}",
        f"Worst demand service: {_metric_text(analysis.result.metrics['worst_demand_service_fraction'])}",
        f"Mean latency ms: {_metric_text(analysis.result.metrics['mean_latency_ms'])}",
        f"Latency p95 ms: {_metric_text(analysis.result.metrics['latency_p95_ms'])}",
        f"Added satellites: {analysis.result.metrics['num_added_satellites']}",
        f"Demanded windows: {analysis.result.metrics['num_demanded_windows']}",
        f"Validated actions: {analysis.result.diagnostics.get('action_counts', {}).get('validated_actions', 0)}",
        f"Action failures: {len(analysis.action_failures)}",
        "",
        "Failures:",
    ]
    if analysis.action_failures:
        for failure in analysis.action_failures[:12]:
            summary_lines.append(f"- a{failure.action_index:03d}: {failure.reason}")
    else:
        summary_lines.append("- none")

    summary_axis.text(
        0.0,
        1.0,
        "\n".join(summary_lines),
        ha="left",
        va="top",
        fontsize=9.0,
        family="monospace",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(figure)
    return output_path


def _render_demand_window_png(
    analysis: SolutionAnalysis,
    demand_id: str,
    intervals: list[tuple[int, int, tuple[str, ...]]],
    output_path: Path,
) -> Path:
    demand = _demand_lookup(analysis)[demand_id]
    metrics = analysis.result.metrics["per_demand"].get(demand_id, {})
    route_legend = _route_color_legend(intervals)
    displayed_route_legend = route_legend[:8]

    duration_s = (demand.end_time - demand.start_time).total_seconds()
    padding_s = max(600.0, duration_s * 0.25)
    x_min = demand.start_time - timedelta(seconds=padding_s)
    x_max = demand.end_time + timedelta(seconds=padding_s)

    figure = plt.figure(figsize=(15, 4.8))
    grid = figure.add_gridspec(1, 2, width_ratios=[3.4, 1.4], wspace=0.08)
    axis = figure.add_subplot(grid[0, 0])
    summary_axis = figure.add_subplot(grid[0, 1])
    axis.set_facecolor("#f7f8fa")
    summary_axis.axis("off")

    axis.broken_barh(
        [
            (
                mdates.date2num(demand.start_time),
                mdates.date2num(demand.end_time) - mdates.date2num(demand.start_time),
            )
        ],
        (-0.38, 0.76),
        facecolors="#d5dbe3",
        edgecolors="none",
        alpha=0.75,
        label="Demanded window",
    )

    for start_index, end_index, route_nodes in intervals:
        start_time, end_time = _interval_datetimes(analysis, start_index, end_index)
        clipped_start = max(start_time, demand.start_time)
        clipped_end = min(end_time, demand.end_time)
        if clipped_end <= clipped_start:
            continue
        axis.broken_barh(
            [
                (
                    mdates.date2num(clipped_start),
                    mdates.date2num(clipped_end) - mdates.date2num(clipped_start),
                )
            ],
            (-0.30, 0.60),
            facecolors=_route_color(route_nodes),
            edgecolors="white",
            linewidth=0.4,
            alpha=0.96,
        )

    axis.set_xlim(mdates.date2num(x_min), mdates.date2num(x_max))
    axis.set_ylim(-1.0, 1.0)
    axis.set_yticks([])
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    axis.grid(True, axis="x", color="#d5dbe3", linewidth=0.7, alpha=0.75)
    axis.set_xlabel("UTC time")
    axis.set_title(
        (
            f"{analysis.case.manifest.case_id}: {demand_id} "
            f"{demand.source_endpoint_id} -> {demand.destination_endpoint_id}"
        ),
        fontsize=13,
        fontweight="bold",
    )

    legend_handles = [
        Line2D([0], [0], color="#d5dbe3", linewidth=9, label="Demanded window"),
    ]
    for label, route_nodes in displayed_route_legend:
        legend_handles.append(
            Line2D(
                [0],
                [0],
                color=_route_color(route_nodes),
                linewidth=9,
                label=label,
            )
        )
    if len(route_legend) > len(displayed_route_legend):
        legend_handles.append(
            Line2D([0], [0], color="#64748b", linewidth=9, label="other routes")
        )
    axis.legend(handles=legend_handles, loc="upper right", frameon=True)

    summary_lines = [
        f"Demand: {demand_id}",
        f"Pair: {demand.source_endpoint_id} -> {demand.destination_endpoint_id}",
        f"Weight: {_metric_text(demand.weight)}",
        "",
        f"Requested samples: {metrics.get('requested_sample_count', 'n/a')}",
        f"Served samples: {metrics.get('served_sample_count', 'n/a')}",
        f"Service fraction: {_metric_text(metrics.get('service_fraction'))}",
        f"Mean latency ms: {_metric_text(metrics.get('mean_latency_ms'))}",
        f"Latency p95 ms: {_metric_text(metrics.get('latency_p95_ms'))}",
        "",
        "Route colors:",
    ]
    if not route_legend:
        summary_lines.append("- no served route")
    for label, route_nodes in displayed_route_legend:
        route_text = f"{label}: {' -> '.join(route_nodes)}"
        wrapped = textwrap.wrap(
            route_text,
            width=58,
            subsequent_indent="    ",
            break_long_words=False,
        )
        summary_lines.extend(f"- {line}" if index == 0 else f"  {line}" for index, line in enumerate(wrapped))
    if len(route_legend) > len(displayed_route_legend):
        summary_lines.append(f"... ({len(route_legend) - len(displayed_route_legend)} more routes)")
    summary_axis.text(
        0.0,
        1.0,
        "\n".join(summary_lines),
        ha="left",
        va="top",
        fontsize=8.4,
        family="monospace",
        color="#1f2933",
        transform=summary_axis.transAxes,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(figure)
    return output_path


def _horizon_sample_times(analysis: SolutionAnalysis) -> list[datetime]:
    sample_times: list[datetime] = []
    current = analysis.case.manifest.horizon_start
    step_s = max(analysis.case.manifest.routing_step_s, 300)
    step = timedelta(seconds=step_s)
    while current < analysis.case.manifest.horizon_end:
        sample_times.append(current)
        current = current + step
    return sample_times


def _node_lonlat(
    analysis: SolutionAnalysis,
    node_id: str,
    sample_index: int,
) -> tuple[float, float] | None:
    endpoint = analysis.case.ground_endpoints.get(node_id)
    if endpoint is not None:
        return endpoint.longitude_deg, endpoint.latitude_deg
    if node_id not in analysis.positions_ecef_by_satellite:
        return None
    if sample_index not in analysis.sample_lookup:
        return None
    row_index = analysis.sample_lookup[sample_index]
    lon_deg, lat_deg, _ = brahe.position_ecef_to_geodetic(
        analysis.positions_ecef_by_satellite[node_id][row_index],
        brahe.AngleFormat.DEGREES,
    )
    return float(lon_deg), float(lat_deg)


def _render_snapshot_png(
    analysis: SolutionAnalysis,
    sample_index: int,
    output_path: Path,
    *,
    texture_path: Path | None = None,
) -> Path:
    from .plot import _load_texture_image

    texture = _load_texture_image(texture_path)
    figure = plt.figure(figsize=(16, 8))
    grid = figure.add_gridspec(1, 2, width_ratios=[2.8, 1.2], wspace=0.08)
    axis = figure.add_subplot(grid[0, 0])
    summary_axis = figure.add_subplot(grid[0, 1])
    summary_axis.axis("off")

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

    allocation_by_sample = _allocations_by_sample(analysis)
    allocation = allocation_by_sample.get(sample_index)
    active_edges = [
        action
        for action in analysis.validated_actions
        if sample_index in action.sample_indices
    ]
    route_edge_ids = {
        edge_id
        for route in (allocation.served_routes if allocation is not None else ())
        for edge_id in route.edge_ids
    }
    failed_edges = [
        failure
        for failure in analysis.action_failures
        if failure.sample_index == sample_index
    ]

    for endpoint in analysis.case.ground_endpoints.values():
        axis.scatter(
            [endpoint.longitude_deg],
            [endpoint.latitude_deg],
            color="#6b7280",
            s=28,
            edgecolors="white",
            linewidths=0.5,
            zorder=3,
        )

    active_satellite_ids = {
        node_id
        for action in active_edges
        for node_id in (action.node_a, action.node_b)
        if node_id.startswith("backbone_") or node_id.startswith("added_")
    }
    for satellite_id in sorted(active_satellite_ids):
        point = _node_lonlat(analysis, satellite_id, sample_index)
        if point is None:
            continue
        axis.scatter(
            [point[0]],
            [point[1]],
            color="#2563eb",
            s=42,
            edgecolors="white",
            linewidths=0.5,
            zorder=5,
        )

    for action in active_edges:
        point_a = _node_lonlat(analysis, action.node_a, sample_index)
        point_b = _node_lonlat(analysis, action.node_b, sample_index)
        if point_a is None or point_b is None:
            continue
        color = "#93c5fd"
        linewidth = 1.6
        zorder = 4
        if action.action_id in route_edge_ids:
            color = "#f59e0b"
            linewidth = 3.0
            zorder = 6
        axis.plot(
            [point_a[0], point_b[0]],
            [point_a[1], point_b[1]],
            color=color,
            linewidth=linewidth,
            alpha=0.95,
            zorder=zorder,
        )

    for failure in failed_edges:
        if failure.node_a is None or failure.node_b is None:
            continue
        point_a = _node_lonlat(analysis, failure.node_a, sample_index)
        point_b = _node_lonlat(analysis, failure.node_b, sample_index)
        if point_a is None or point_b is None:
            continue
        axis.plot(
            [point_a[0], point_b[0]],
            [point_a[1], point_b[1]],
            color="#dc2626",
            linewidth=2.3,
            linestyle="--",
            alpha=0.95,
            zorder=7,
        )

    instant = analysis.case.manifest.horizon_start + timedelta(
        seconds=sample_index * analysis.case.manifest.routing_step_s
    )
    axis.set_title(
        f"{analysis.case.manifest.case_id}: topology snapshot at {_utc_text(instant)}",
        fontsize=15,
        fontweight="bold",
    )

    summary_lines = [
        f"Sample index: {sample_index}",
        f"Time: {_utc_text(instant)}",
        "",
        f"Active demands: {0 if allocation is None else len(allocation.active_demand_ids)}",
        f"Served routes: {0 if allocation is None else len(allocation.served_routes)}",
        f"Active valid links: {len(active_edges)}",
        f"Failing links: {len(failed_edges)}",
        "",
        "Routes:",
    ]
    if allocation is not None and allocation.served_routes:
        for route in allocation.served_routes:
            summary_lines.append(
                f"- {route.demand_id}: {' -> '.join(route.nodes)}"
            )
            summary_lines.append(f"  latency_ms={route.latency_ms:.3f}")
    else:
        summary_lines.append("- none")
    if failed_edges:
        summary_lines.append("")
        summary_lines.append("Failures:")
        for failure in failed_edges[:8]:
            summary_lines.append(f"- a{failure.action_index:03d}: {failure.reason}")

    summary_axis.text(
        0.0,
        1.0,
        "\n".join(summary_lines),
        ha="left",
        va="top",
        fontsize=9.0,
        family="monospace",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(figure)
    return output_path


def render_solution_report(
    case_dir: Path | str,
    solution_path: Path | str,
    output_dir: Path | str,
    *,
    texture_path: Path | None = None,
) -> dict[str, object]:
    case_path = Path(case_dir).resolve()
    solution_file = Path(solution_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    analysis = analyze_solution(
        case_path,
        solution_file,
        include_demand_sample_positions=False,
    )

    all_satellites = {
        **analysis.case.backbone_satellites,
        **analysis.solution.added_satellites,
    }
    sample_times = _horizon_sample_times(analysis)
    sample_times, states_ecef_by_satellite = build_state_cache_for_satellites(
        analysis.case,
        all_satellites,
        sample_times,
    )
    track_times, track_states = coarsen_ground_track_cache(
        sample_times,
        states_ecef_by_satellite,
    )

    ground_tracks_path = output_dir / "ground_tracks.png"
    render_ground_tracks_png(
        analysis.case,
        ground_tracks_path,
        sample_times=track_times,
        states_ecef_by_satellite=track_states,
        texture_path=texture_path,
        added_satellite_ids=set(analysis.solution.added_satellites),
        max_added_tracks=1,
        title=f"{analysis.case.manifest.case_id}: backbone + added ground tracks",
    )

    scheduled_connectivity_path = output_dir / "scheduled_connectivity.png"
    _render_scheduled_connectivity_png(analysis, scheduled_connectivity_path)

    route_intervals = _route_intervals_by_demand(analysis)
    demand_windows_dir = output_dir / "demand_windows"
    demand_window_files: list[str] = []
    for demand in sorted(analysis.case.demands, key=lambda row: row.demand_id):
        demand_window_path = demand_windows_dir / f"{demand.demand_id}.png"
        _render_demand_window_png(
            analysis,
            demand.demand_id,
            route_intervals.get(demand.demand_id, []),
            demand_window_path,
        )
        demand_window_files.append(str(demand_window_path.relative_to(output_dir)))

    return {
        "case_id": analysis.case.manifest.case_id,
        "case_dir": str(case_path),
        "solution_path": str(solution_file),
        "ground_tracks_png": ground_tracks_path.name,
        "scheduled_connectivity_png": scheduled_connectivity_path.name,
        "demand_window_pngs": demand_window_files,
        "verifier_result": analysis.result.to_dict(),
        "action_failures": [failure.to_dict() for failure in analysis.action_failures],
    }


def render_solution(
    case_dir: Path | str,
    solution_path: Path | str,
    output_dir: Path | str,
    *,
    texture_path: Path | None = None,
) -> dict[str, object]:
    return render_solution_report(
        case_dir,
        solution_path,
        output_dir,
        texture_path=texture_path,
    )
