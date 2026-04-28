"""Human-facing visualizer for the SatNet benchmark."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from ..verifier import (
    ALL_ANTENNAS,
    Instance,
    Request,
    Solution,
    Track,
    load_case,
    load_solution,
    verify,
)


_VISUALIZER_DIR = Path(__file__).resolve().parent
_BENCHMARK_DIR = _VISUALIZER_DIR.parent
_DEFAULT_OUTPUT_ROOT = _VISUALIZER_DIR / "plots"
_MISSION_COLOR_MAP_PATH = _BENCHMARK_DIR / "dataset" / "mission_color_map.json"
_DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
_THEME = {
    "background": "#ffffff",
    "panel": "#f7f8fa",
    "grid": "#d5dbe3",
    "axis": "#39424e",
    "text": "#1f2933",
    "muted": "#52606d",
    "maintenance": "#111827",
}


@dataclass(frozen=True)
class LogicalTrack:
    track_id: str
    sc: int
    resources: tuple[str, ...]
    start_time: int
    tracking_on: int
    tracking_off: int
    end_time: int


def _to_datetime(timestamp_s: int) -> datetime:
    return datetime.fromtimestamp(timestamp_s, tz=UTC)


def _case_week_start(instance: Instance) -> datetime:
    return datetime.fromisocalendar(int(instance.year), int(instance.week), 1).replace(
        tzinfo=UTC
    )


def _case_week_end(instance: Instance) -> datetime:
    return _case_week_start(instance) + timedelta(days=7)


def _apply_axes_theme(ax: plt.Axes, *, grid_axis: str = "both") -> None:
    ax.set_facecolor(_THEME["panel"])
    ax.grid(True, axis=grid_axis, color=_THEME["grid"], alpha=0.75, linewidth=0.8)
    ax.tick_params(colors=_THEME["muted"])
    ax.xaxis.label.set_color(_THEME["text"])
    ax.yaxis.label.set_color(_THEME["text"])
    ax.title.set_color(_THEME["text"])
    for spine in ax.spines.values():
        spine.set_color(_THEME["axis"])


def _load_mission_colors() -> dict[str, tuple[str, str]]:
    if not _MISSION_COLOR_MAP_PATH.exists():
        return {}
    with _MISSION_COLOR_MAP_PATH.open("r", encoding="utf-8") as file_obj:
        raw = json.load(file_obj)
    colors: dict[str, tuple[str, str]] = {}
    for mission_id, pair in raw.items():
        if isinstance(pair, list) and len(pair) >= 2:
            colors[str(mission_id)] = (str(pair[0]), str(pair[1]))
    return colors


def _fallback_color(mission_id: str) -> tuple[str, str]:
    palette = plt.get_cmap("tab20")
    index = sum((idx + 1) * ord(char) for idx, char in enumerate(mission_id)) % palette.N
    fill = palette(index)
    rgb = tuple(max(0.0, channel * 0.65) for channel in fill[:3])
    edge = "#{:02x}{:02x}{:02x}".format(
        int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
    )
    return matplotlib.colors.to_hex(fill), edge


def _mission_color(
    mission_id: str, mission_colors: dict[str, tuple[str, str]]
) -> tuple[str, str]:
    return mission_colors.get(str(mission_id), _fallback_color(str(mission_id)))


def _mission_bar_color(
    mission_id: str, mission_colors: dict[str, tuple[str, str]]
) -> tuple[str, str]:
    return _mission_color(mission_id, mission_colors)


def _mission_timeline_color(
    mission_id: str, mission_colors: dict[str, tuple[str, str]]
) -> tuple[str, str]:
    light_color, strong_color = _mission_color(mission_id, mission_colors)
    return strong_color, light_color


def _sorted_antennas(instance: Instance) -> list[str]:
    antennas = set(ALL_ANTENNAS)
    antennas.update(window.antenna for window in instance.maintenance)
    for request in instance.requests.values():
        for combo_key in request.resource_vp_dict:
            antennas.update(combo_key.split("_"))
    return sorted(antennas, key=lambda item: int(item.split("-")[-1]))


def _iter_vp_antenna_intervals(request: Request) -> list[tuple[str, int, int]]:
    intervals: list[tuple[str, int, int]] = []
    for combo_key, vps in request.resource_vp_dict.items():
        for antenna in combo_key.split("_"):
            for start, end in vps:
                intervals.append((antenna, int(start), int(end)))
    return intervals


def _overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    return not (a1 <= b0 or b1 <= a0)


def _availability_counts(instance: Instance) -> tuple[list[str], np.ndarray]:
    antennas = _sorted_antennas(instance)
    antenna_index = {antenna: idx for idx, antenna in enumerate(antennas)}
    counts = np.zeros((len(antennas), 7), dtype=int)
    week_start = _case_week_start(instance)
    day_edges = [int((week_start + timedelta(days=day)).timestamp()) for day in range(8)]

    for request in instance.requests.values():
        for antenna, vp_start, vp_end in _iter_vp_antenna_intervals(request):
            if antenna not in antenna_index:
                continue
            for day in range(7):
                if _overlaps(vp_start, vp_end, day_edges[day], day_edges[day + 1]):
                    counts[antenna_index[antenna], day] += 1

    return antennas, counts


def _annotate_heatmap(ax: plt.Axes, counts: np.ndarray, cmap: matplotlib.colors.Colormap) -> None:
    max_value = max(1, int(counts.max(initial=0)))
    for row in range(counts.shape[0]):
        for col in range(counts.shape[1]):
            value = int(counts[row, col])
            rgba = cmap(value / max_value)
            luminance = 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2]
            color = "white" if luminance < 0.48 else "#172033"
            ax.text(
                col,
                row,
                str(value),
                ha="center",
                va="center",
                color=color,
                fontsize=9,
            )


def render_availability(case_dir: str | Path, out_path: str | Path | None = None) -> Path:
    """Render a case-only antenna/day opportunity heatmap."""

    case_path = Path(case_dir)
    instance = load_case(case_path)
    output_path = (
        Path(out_path)
        if out_path is not None
        else _DEFAULT_OUTPUT_ROOT
        / str(instance.case_id or case_path.name)
        / "availability.png"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    antennas, counts = _availability_counts(instance)
    fig_height = max(5.2, 0.34 * len(antennas) + 1.7)
    fig, ax = plt.subplots(figsize=(9.5, fig_height), dpi=180)
    fig.patch.set_facecolor(_THEME["background"])

    cmap = plt.get_cmap("viridis_r")
    image = ax.imshow(counts, cmap=cmap, aspect="auto")
    ax.set_title(
        f"{instance.case_id or case_path.name}: request opportunities by antenna and day",
        pad=14,
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xticks(range(7), _DAY_NAMES, rotation=0)
    ax.set_yticks(range(len(antennas)), antennas)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_xticks(np.arange(-0.5, 7, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(antennas), 1), minor=True)
    ax.grid(which="minor", color="#ffffff", linewidth=1.0)
    ax.tick_params(which="minor", bottom=False, left=False)
    _annotate_heatmap(ax, counts, cmap)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.025, pad=0.02)
    colorbar.set_label("View-period opportunities", color=_THEME["text"])
    colorbar.ax.tick_params(colors=_THEME["muted"])

    fig.text(
        0.01,
        0.015,
        "Each cell counts request view-period intervals touching that antenna/day; arrayed requests contribute to each antenna in the array.",
        ha="left",
        va="bottom",
        fontsize=8.5,
        color=_THEME["muted"],
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _logical_tracks(solution: Solution) -> list[LogicalTrack]:
    grouped: dict[tuple[str, int, int, int, int], list[Track]] = defaultdict(list)
    for track in solution.tracks:
        grouped[
            (
                track.track_id,
                track.start_time,
                track.tracking_on,
                track.tracking_off,
                track.end_time,
            )
        ].append(track)

    logical: list[LogicalTrack] = []
    for (track_id, start, on, off, end), group in grouped.items():
        resources = tuple(sorted({track.resource for track in group}))
        sc = group[0].sc
        logical.append(
            LogicalTrack(
                track_id=track_id,
                sc=sc,
                resources=resources,
                start_time=start,
                tracking_on=on,
                tracking_off=off,
                end_time=end,
            )
        )
    return sorted(logical, key=lambda track: (track.start_time, track.track_id))


def _solution_output_dir(
    case_dir: Path, solution_path: Path, out_dir: str | Path | None
) -> Path:
    if out_dir is not None:
        return Path(out_dir)
    return _DEFAULT_OUTPUT_ROOT / case_dir.name / "schedule" / solution_path.stem


def render_satisfaction(
    case_dir: str | Path,
    solution_path: str | Path,
    out_path: str | Path | None = None,
) -> Path:
    """Render mission satisfaction bars for one case and solution."""

    case_path = Path(case_dir)
    solution_file = Path(solution_path)
    instance = load_case(case_path)
    solution = load_solution(solution_file)
    result = verify(instance, solution)
    mission_colors = _load_mission_colors()

    output_path = Path(out_path) if out_path is not None else (
        _solution_output_dir(case_path, solution_file, None) / "satisfaction.png"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    requested_hours_by_mission: dict[str, float] = defaultdict(float)
    for request in instance.requests.values():
        requested_hours_by_mission[str(request.subject)] += float(request.duration)

    mission_ids = sorted(
        requested_hours_by_mission,
        key=lambda mission_id: (
            1.0 - result.per_mission_u_i.get(mission_id, 0.0),
            mission_id,
        ),
    )
    satisfaction = [
        100.0 * (1.0 - result.per_mission_u_i.get(mission_id, 0.0))
        for mission_id in mission_ids
    ]
    y_positions = np.arange(len(mission_ids))
    colors = [
        _mission_bar_color(mission_id, mission_colors)[0] for mission_id in mission_ids
    ]
    edge_colors = [
        _mission_bar_color(mission_id, mission_colors)[1] for mission_id in mission_ids
    ]

    fig_height = max(6.0, 0.26 * len(mission_ids) + 1.8)
    fig, ax = plt.subplots(figsize=(10.5, fig_height), dpi=180)
    fig.patch.set_facecolor(_THEME["background"])
    _apply_axes_theme(ax, grid_axis="x")

    ax.barh(y_positions, satisfaction, color=colors, edgecolor=edge_colors, linewidth=0.8)
    ax.set_yticks(y_positions, mission_ids)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Requested mission hours satisfied (%)")
    ax.set_ylabel("Mission")
    ax.set_title(
        f"{instance.case_id or case_path.name}: mission satisfaction",
        pad=12,
        fontweight="bold",
    )
    for tick in [20, 40, 60, 80, 100]:
        ax.axvline(tick, color="#111827", linestyle="--", linewidth=0.7, alpha=0.6)

    status = "VALID" if result.is_valid else "INVALID"
    requested_total = sum(requested_hours_by_mission.values())
    summary = (
        f"{status} solution | tracking {result.total_hours:.1f}h / requested {requested_total:.1f}h | "
        f"satisfied requests {result.n_satisfied_requests}/{len(instance.requests)} | "
        f"U_rms {result.u_rms:.3f} | U_max {result.u_max:.3f}"
    )
    fig.text(
        0.01,
        0.012,
        summary,
        ha="left",
        va="bottom",
        fontsize=9,
        color=_THEME["muted"],
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _setup_timedelta(track: LogicalTrack) -> tuple[float, float, float, float]:
    full_start = mdates.date2num(_to_datetime(track.start_time))
    full_end = mdates.date2num(_to_datetime(track.end_time))
    trx_start = mdates.date2num(_to_datetime(track.tracking_on))
    trx_end = mdates.date2num(_to_datetime(track.tracking_off))
    return full_start, full_end, trx_start, trx_end


def render_timeline(
    case_dir: str | Path,
    solution_path: str | Path,
    out_path: str | Path | None = None,
) -> Path:
    """Render an antenna timeline with solution tracks and maintenance windows."""

    case_path = Path(case_dir)
    solution_file = Path(solution_path)
    instance = load_case(case_path)
    solution = load_solution(solution_file)
    mission_colors = _load_mission_colors()
    logical_tracks = _logical_tracks(solution)

    output_path = Path(out_path) if out_path is not None else (
        _solution_output_dir(case_path, solution_file, None) / "timeline.png"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    antennas = _sorted_antennas(instance)
    y_by_antenna = {antenna: idx for idx, antenna in enumerate(antennas)}
    fig_height = max(6.5, 0.42 * len(antennas) + 2.2)
    fig, ax = plt.subplots(figsize=(15.5, fig_height), dpi=180)
    fig.patch.set_facecolor(_THEME["background"])
    _apply_axes_theme(ax, grid_axis="x")

    row_height = 0.72
    for window in instance.maintenance:
        if window.antenna not in y_by_antenna:
            continue
        y = y_by_antenna[window.antenna] - row_height / 2
        start = mdates.date2num(_to_datetime(window.start_time))
        end = mdates.date2num(_to_datetime(window.end_time))
        ax.broken_barh(
            [(start, end - start)],
            (y, row_height),
            facecolors=_THEME["maintenance"],
            edgecolors="none",
            alpha=0.96,
            zorder=2,
        )

    for track in logical_tracks:
        fill_color, edge_color = _mission_timeline_color(str(track.sc), mission_colors)
        full_start, full_end, trx_start, trx_end = _setup_timedelta(track)
        for antenna in track.resources:
            if antenna not in y_by_antenna:
                continue
            y = y_by_antenna[antenna] - row_height / 2
            ax.broken_barh(
                [(full_start, full_end - full_start)],
                (y, row_height),
                facecolors=fill_color,
                edgecolors="none",
                alpha=0.16,
                zorder=3,
            )
            ax.broken_barh(
                [(trx_start, trx_end - trx_start)],
                (y, row_height),
                facecolors=fill_color,
                edgecolors=edge_color,
                linewidth=0.45,
                alpha=0.95,
                zorder=4,
            )

    week_start = _case_week_start(instance)
    week_end = _case_week_end(instance)
    ax.set_xlim(mdates.date2num(week_start), mdates.date2num(week_end))
    ax.set_ylim(-0.8, len(antennas) - 0.2)
    ax.set_yticks(range(len(antennas)), antennas)
    ax.invert_yaxis()
    ax.set_ylabel("Antenna")
    ax.set_xlabel("UTC time")
    ax.set_title(
        f"{instance.case_id or case_path.name}: scheduled antenna timeline",
        pad=12,
        fontweight="bold",
    )
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%a", tz=UTC))
    ax.xaxis.set_minor_locator(mdates.HourLocator(interval=6))

    unique_missions = sorted({str(track.sc) for track in logical_tracks})
    busiest = sorted(
        unique_missions,
        key=lambda mission_id: sum(
            track.tracking_off - track.tracking_on
            for track in logical_tracks
            if str(track.sc) == mission_id
        ),
        reverse=True,
    )[:8]
    handles = [Patch(facecolor=_THEME["maintenance"], label="maintenance")]
    for mission_id in busiest:
        fill_color, edge_color = _mission_timeline_color(mission_id, mission_colors)
        handles.append(
            Patch(facecolor=fill_color, edgecolor=edge_color, label=f"SC {mission_id}")
        )
    ax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        frameon=False,
        fontsize=8,
        title="Color key",
        title_fontsize=9,
    )

    arrayed_count = sum(1 for track in logical_tracks if len(track.resources) > 1)
    footer = (
        f"{len(logical_tracks)} logical tracks, {len(solution.tracks)} antenna rows; "
        f"{arrayed_count} tracks use multiple antennas. Solid bars are tracking time; faint same-color shoulders are setup/teardown."
    )
    fig.text(0.01, 0.012, footer, ha="left", va="bottom", fontsize=9, color=_THEME["muted"])
    fig.tight_layout(rect=(0, 0.04, 0.91, 1))
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def render_schedule(
    case_dir: str | Path,
    solution_path: str | Path,
    out_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Render the solution-aware SatNet visualizer bundle."""

    case_path = Path(case_dir)
    solution_file = Path(solution_path)
    output_dir = _solution_output_dir(case_path, solution_file, out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    satisfaction_path = render_satisfaction(
        case_path, solution_file, output_dir / "satisfaction.png"
    )
    timeline_path = render_timeline(case_path, solution_file, output_dir / "timeline.png")
    return satisfaction_path, timeline_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render SatNet case and solution plots.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    availability_parser = subparsers.add_parser(
        "availability",
        help="Render a case-only antenna/day opportunity heatmap.",
    )
    availability_parser.add_argument(
        "--case-dir",
        required=True,
        help="Path to a canonical SatNet case directory.",
    )
    availability_parser.add_argument(
        "--out-path",
        type=Path,
        default=None,
        help="Output PNG path (default: benchmarks/satnet/visualizer/plots/<case_id>/availability.png).",
    )

    schedule_parser = subparsers.add_parser(
        "schedule",
        help="Render solution-aware satisfaction and antenna timeline plots.",
    )
    schedule_parser.add_argument(
        "--case-dir",
        required=True,
        help="Path to a canonical SatNet case directory.",
    )
    schedule_parser.add_argument(
        "--solution-path",
        required=True,
        help="Path to a SatNet solution JSON file.",
    )
    schedule_parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: benchmarks/satnet/visualizer/plots/<case_id>/schedule/<solution_stem>).",
    )

    args = parser.parse_args(argv)
    if args.command == "availability":
        out_path = render_availability(args.case_dir, args.out_path)
        print(f"Wrote {out_path.resolve()}")
        return 0

    satisfaction_path, timeline_path = render_schedule(
        args.case_dir,
        args.solution_path,
        args.out_dir,
    )
    print(f"Wrote {satisfaction_path.resolve()}")
    print(f"Wrote {timeline_path.resolve()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
