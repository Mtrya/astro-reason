"""Solution inspection visualizer for relay_constellation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

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
from .plot import (
    _load_texture_image,
    _route_color,
    _serialize_json,
    resolve_texture_path,
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


def _render_timeline_png(
    analysis: SolutionAnalysis,
    output_path: Path,
) -> Path:
    demand_lookup = _demand_lookup(analysis)
    route_intervals = _route_intervals_by_demand(analysis)
    action_records = _action_timeline_records(analysis)
    demand_rows = sorted(demand_lookup)
    total_rows = len(demand_rows) + len(action_records)
    figure_height = max(7.0, 0.36 * total_rows + 2.5)
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
    action_y_start = len(demand_rows) + 1
    action_y = {
        record["action_index"]: action_y_start + row_index
        for row_index, record in enumerate(action_records)
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

    for record in action_records:
        y = action_y[int(record["action_index"])]
        color = "#4b7bec" if record["status"] == "valid" else "#dc2626"
        axis.broken_barh(
            [
                (
                    mdates.date2num(record["start_time"]),
                    mdates.date2num(record["end_time"]) - mdates.date2num(record["start_time"]),
                )
            ],
            (y - bar_height / 2.0, bar_height),
            facecolors=color,
            edgecolors="none",
            alpha=0.9,
        )
        failure = record["failure"]
        if isinstance(failure, ActionFailure) and failure.time is not None:
            axis.axvline(
                mdates.date2num(failure.time),
                ymin=max(0.0, (y - 0.45) / max(1.0, total_rows + 2)),
                ymax=min(1.0, (y + 0.45) / max(1.0, total_rows + 2)),
                color="#991b1b",
                linewidth=1.2,
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
    for record in action_records:
        yticks.append(action_y[int(record["action_index"])])
        ylabels.append(f"a{int(record['action_index']):03d} {record['label']}")

    axis.set_yticks(yticks)
    axis.set_yticklabels(ylabels, fontsize=8)
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    axis.grid(True, axis="x", color="#d5dbe3", linewidth=0.7, alpha=0.7)
    axis.set_title(
        f"{analysis.case.manifest.case_id}: solution timeline",
        fontsize=15,
        fontweight="bold",
    )
    axis.set_xlabel("UTC time")

    legend_handles = [
        Line2D([0], [0], color="#d5dbe3", linewidth=8, label="Demanded window"),
        Line2D([0], [0], color="#4b7bec", linewidth=8, label="Valid action"),
        Line2D([0], [0], color="#dc2626", linewidth=8, label="Invalid action"),
    ]
    axis.legend(handles=legend_handles, loc="upper right", frameon=True)

    summary_lines = [
        f"Valid: {analysis.result.valid}",
        f"Service fraction: {analysis.result.metrics['service_fraction']:.3f}",
        f"Worst demand service: {analysis.result.metrics['worst_demand_service_fraction']:.3f}",
        f"Mean latency ms: {analysis.result.metrics['mean_latency_ms']}",
        f"Latency p95 ms: {analysis.result.metrics['latency_p95_ms']}",
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
    texture_path = resolve_texture_path(texture_path)
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
        include_demand_sample_positions=True,
    )
    timeline_path = output_dir / "timeline.png"
    _render_timeline_png(analysis, timeline_path)

    snapshot_indices = _pick_snapshot_indices(analysis)
    snapshots_dir = output_dir / "snapshots"
    snapshot_files: list[str] = []
    for sample_index in snapshot_indices:
        snapshot_path = snapshots_dir / f"snapshot_{sample_index:04d}.png"
        _render_snapshot_png(
            analysis,
            sample_index,
            snapshot_path,
            texture_path=texture_path,
        )
        snapshot_files.append(snapshot_path.name)

    route_intervals = _route_intervals_by_demand(analysis)
    summary = {
        "case_id": analysis.case.manifest.case_id,
        "case_dir": str(case_path),
        "solution_path": str(solution_file),
        "timeline_png": timeline_path.name,
        "snapshot_pngs": snapshot_files,
        "snapshot_sample_indices": snapshot_indices,
        "verifier_result": analysis.result.to_dict(),
        "action_failures": [failure.to_dict() for failure in analysis.action_failures],
        "route_intervals_by_demand": {
            demand_id: [
                {
                    "start_time": _interval_datetimes(analysis, start_index, end_index)[0]
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "end_time": _interval_datetimes(analysis, start_index, end_index)[1]
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "route_nodes": list(route_nodes),
                }
                for start_index, end_index, route_nodes in intervals
            ]
            for demand_id, intervals in route_intervals.items()
        },
    }
    _serialize_json(output_dir / "summary.json", summary)
    return summary
