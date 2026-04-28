"""Human-facing visualizer for the revisit_constellation benchmark."""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import brahe
import matplotlib
import numpy as np

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from brahe.plots.texture_utils import load_earth_texture
from matplotlib.lines import Line2D

from ..verifier import Action, Instance, Solution, Target, load_case, load_solution
from ..verifier.engine import _build_propagators, _datetime_to_epoch, _ensure_brahe_ready


_VISUALIZER_DIR = Path(__file__).resolve().parent
_DEFAULT_OUTPUT_ROOT = _VISUALIZER_DIR / "plots"
_WORLD_TEXTURE_EXTENT = (-180.0, 180.0, -90.0, 90.0)
_WORLD_TEXTURE: np.ndarray | None = None
_THEME = {
    "background": "#ffffff",
    "panel": "#f7f8fa",
    "grid": "#d5dbe3",
    "axis": "#39424e",
    "text": "#1f2933",
    "muted": "#52606d",
    "target": "#ef4444",
    "observer": "#06b6d4",
    "other_satellite": "#334155",
    "track": "#64748b",
}


def _utc_label(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%SZ")


def _target_order(instance: Instance) -> list[Target]:
    return list(instance.targets.values())


def _solution_output_dir(
    case_dir: Path, solution_path: Path, out_dir: str | Path | None
) -> Path:
    if out_dir is not None:
        return Path(out_dir)
    return _DEFAULT_OUTPUT_ROOT / case_dir.name / "solution" / solution_path.stem


def _load_world_texture() -> np.ndarray | None:
    global _WORLD_TEXTURE
    if _WORLD_TEXTURE is None:
        for texture_name in ("natural_earth_50m", "blue_marble"):
            try:
                image = load_earth_texture(texture_name)
            except Exception:
                continue
            if image is not None:
                _WORLD_TEXTURE = np.asarray(image)
                break
    return _WORLD_TEXTURE


def _draw_world(ax: plt.Axes) -> None:
    texture = _load_world_texture()
    if texture is not None:
        xmin, xmax, ymin, ymax = _WORLD_TEXTURE_EXTENT
        ax.imshow(
            texture,
            origin="upper",
            extent=[xmin, xmax, ymin, ymax],
            aspect="auto",
            interpolation="bilinear",
            zorder=0,
            alpha=0.92,
        )
    ax.set_xlim(-180.0, 180.0)
    ax.set_ylim(-90.0, 90.0)
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.grid(True, color=_THEME["grid"], linewidth=0.6, alpha=0.55)
    ax.set_facecolor(_THEME["panel"])
    ax.tick_params(colors=_THEME["muted"], labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(_THEME["axis"])


def _case_output_path(case_dir: Path, out_path: str | Path | None) -> Path:
    if out_path is not None:
        return Path(out_path)
    return _DEFAULT_OUTPUT_ROOT / case_dir.name / "overview.png"


def render_overview(case_dir: str | Path, out_path: str | Path | None = None) -> Path:
    """Render case-only target distribution overview."""

    case_path = Path(case_dir)
    instance = load_case(case_path)
    output_path = _case_output_path(case_path, out_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    targets = _target_order(instance)
    longitudes = np.asarray([target.longitude_deg for target in targets], dtype=float)
    latitudes = np.asarray([target.latitude_deg for target in targets], dtype=float)
    revisit_hours = np.asarray(
        [target.expected_revisit_period_hours for target in targets], dtype=float
    )

    fig, ax = plt.subplots(figsize=(11.5, 6.4), dpi=180)
    fig.patch.set_facecolor(_THEME["background"])
    _draw_world(ax)
    scatter = ax.scatter(
        longitudes,
        latitudes,
        c=revisit_hours,
        cmap="plasma_r",
        s=55,
        edgecolors="#111827",
        linewidths=0.55,
        zorder=4,
    )
    ax.set_title(f"{case_path.name}: target distribution", fontweight="bold", pad=12)
    colorbar = fig.colorbar(scatter, ax=ax, fraction=0.026, pad=0.025)
    colorbar.set_label("Expected revisit period (hours)", color=_THEME["text"])
    colorbar.ax.tick_params(colors=_THEME["muted"])

    horizon_hours = instance.horizon_duration_sec / 3600.0
    fig.text(
        0.01,
        0.015,
        f"{len(targets)} targets | {horizon_hours:.1f}h horizon | "
        f"up to {instance.max_num_satellites} satellites | "
        f"altitude {instance.satellite_model.min_altitude_m / 1000:.0f}-"
        f"{instance.satellite_model.max_altitude_m / 1000:.0f} km",
        ha="left",
        va="bottom",
        fontsize=9,
        color=_THEME["muted"],
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _observation_actions_by_target(solution: Solution) -> dict[str, list[Action]]:
    actions_by_target: dict[str, list[Action]] = defaultdict(list)
    for action in solution.actions:
        if action.action_type != "observation" or action.target_id is None:
            continue
        actions_by_target[action.target_id].append(action)
    for actions in actions_by_target.values():
        actions.sort(key=lambda item: (item.start, item.end, item.satellite_id))
    return actions_by_target


def _satellite_ids_for_target(actions: list[Action]) -> list[str]:
    return sorted({action.satellite_id for action in actions})


def _satellite_lonlat(
    propagator: brahe.NumericalOrbitPropagator, instant: datetime
) -> tuple[float, float]:
    epoch = _datetime_to_epoch(instant)
    state_ecef = np.asarray(propagator.state_ecef(epoch), dtype=float).reshape(6)
    lon_deg, lat_deg, _alt_m = brahe.position_ecef_to_geodetic(
        state_ecef[:3], brahe.AngleFormat.DEGREES
    )
    return float(lon_deg), float(lat_deg)


def _sample_ground_track_segments(
    propagator: brahe.NumericalOrbitPropagator,
    start: datetime,
    end: datetime,
    *,
    step_s: float,
) -> list[tuple[list[float], list[float]]]:
    longitudes: list[float] = []
    latitudes: list[float] = []
    current = start
    step = timedelta(seconds=step_s)
    while current <= end:
        lon_deg, lat_deg = _satellite_lonlat(propagator, current)
        longitudes.append(lon_deg)
        latitudes.append(lat_deg)
        current += step
    if not longitudes or current - step < end:
        lon_deg, lat_deg = _satellite_lonlat(propagator, end)
        longitudes.append(lon_deg)
        latitudes.append(lat_deg)
    return brahe.split_ground_track_at_antimeridian(longitudes, latitudes)


def _action_midpoint(action: Action) -> datetime:
    return action.start + (action.end - action.start) / 2


def _track_window(
    instance: Instance, midpoint: datetime, track_window_min: float
) -> tuple[datetime, datetime]:
    half_window = timedelta(minutes=track_window_min / 2.0)
    start = max(instance.horizon_start, midpoint - half_window)
    end = min(instance.horizon_end, midpoint + half_window)
    return start, end


def _target_page_path(output_dir: Path, target: Target, index: int) -> Path:
    safe_id = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_" for char in target.target_id
    )
    return output_dir / f"target_{index:02d}_{safe_id}.png"


def _plot_snapshot(
    ax: plt.Axes,
    *,
    instance: Instance,
    target: Target,
    action: Action,
    relevant_satellite_ids: list[str],
    propagators: dict[str, brahe.NumericalOrbitPropagator],
    track_window_min: float,
    track_step_s: float,
) -> None:
    _draw_world(ax)
    midpoint = _action_midpoint(action)
    track_start, track_end = _track_window(instance, midpoint, track_window_min)

    for satellite_id in relevant_satellite_ids:
        propagator = propagators.get(satellite_id)
        if propagator is None:
            continue
        is_observer = satellite_id == action.satellite_id
        track_color = _THEME["observer"] if is_observer else _THEME["track"]
        alpha = 0.88 if is_observer else 0.52
        linewidth = 1.4 if is_observer else 0.85
        for lons, lats in _sample_ground_track_segments(
            propagator,
            track_start,
            track_end,
            step_s=track_step_s,
        ):
            ax.plot(
                lons,
                lats,
                color=track_color,
                linewidth=linewidth,
                alpha=alpha,
                zorder=2,
            )
        lon_deg, lat_deg = _satellite_lonlat(propagator, midpoint)
        marker = "o" if is_observer else "^"
        size = 56 if is_observer else 34
        face = _THEME["observer"] if is_observer else _THEME["other_satellite"]
        ax.scatter(
            [lon_deg],
            [lat_deg],
            s=size,
            marker=marker,
            color=face,
            edgecolors="white",
            linewidths=0.65,
            zorder=5,
        )

    ax.scatter(
        [target.longitude_deg],
        [target.latitude_deg],
        s=72,
        marker="*",
        color=_THEME["target"],
        edgecolors="#111827",
        linewidths=0.55,
        zorder=6,
    )
    ax.set_title(
        f"{_utc_label(midpoint)}\nobserver {action.satellite_id}",
        fontsize=8.5,
        color=_THEME["text"],
    )


def _snapshot_legend_handles() -> list[Line2D]:
    return [
        Line2D(
            [0],
            [0],
            marker="*",
            linestyle="none",
            color="none",
            markerfacecolor=_THEME["target"],
            markeredgecolor="#111827",
            markersize=9,
            label="target",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            color="none",
            markerfacecolor=_THEME["observer"],
            markeredgecolor="white",
            markersize=6,
            label="observing satellite",
        ),
        Line2D(
            [0],
            [0],
            marker="^",
            linestyle="none",
            color="none",
            markerfacecolor=_THEME["other_satellite"],
            markeredgecolor="white",
            markersize=6,
            label="other observing satellite",
        ),
    ]


def _selected_targets_with_actions(
    instance: Instance, actions_by_target: dict[str, list[Action]], max_targets: int | None
) -> list[Target]:
    targets = [
        target
        for target in _target_order(instance)
        if actions_by_target.get(target.target_id)
    ]
    if max_targets is None:
        return targets
    return targets[: max(0, max_targets)]


def _filtered_solution_for_satellites(solution: Solution, satellite_ids: set[str]) -> Solution:
    return Solution(
        satellites={
            satellite_id: satellite
            for satellite_id, satellite in solution.satellites.items()
            if satellite_id in satellite_ids
        },
        actions=[],
    )


def _target_max_gap_hours(instance: Instance, target: Target, actions: list[Action]) -> float:
    midpoints = sorted({_action_midpoint(action) for action in actions})
    times = [instance.horizon_start, *midpoints, instance.horizon_end]
    return max(
        (right - left).total_seconds() / 3600.0
        for left, right in zip(times, times[1:])
    )


def render_solution(
    case_dir: str | Path,
    solution_path: str | Path,
    out_dir: str | Path | None = None,
    *,
    max_targets: int | None = 8,
    max_actions_per_target: int | None = 4,
    track_window_min: float = 90.0,
    track_step_s: float = 90.0,
) -> list[Path]:
    """Render per-target action snapshot pages for one solution."""

    case_path = Path(case_dir)
    solution_file = Path(solution_path)
    instance = load_case(case_path)
    solution = load_solution(solution_file)
    actions_by_target = _observation_actions_by_target(solution)
    targets = _selected_targets_with_actions(instance, actions_by_target, max_targets)
    selected_satellite_ids = {
        action.satellite_id
        for target in targets
        for action in actions_by_target[target.target_id]
        if action.satellite_id in solution.satellites
    }
    _ensure_brahe_ready()
    propagators = _build_propagators(
        instance, _filtered_solution_for_satellites(solution, selected_satellite_ids)
    )

    output_dir = _solution_output_dir(case_path, solution_file, out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for target_index, target in enumerate(targets, start=1):
        actions = actions_by_target[target.target_id]
        selected_actions = actions
        if max_actions_per_target is not None:
            selected_actions = actions[: max(0, max_actions_per_target)]
        if not selected_actions:
            continue
        relevant_satellite_ids = _satellite_ids_for_target(actions)
        ncols = min(2, len(selected_actions))
        nrows = math.ceil(len(selected_actions) / ncols)
        fig, axes = plt.subplots(
            nrows,
            ncols,
            figsize=(6.4 * ncols, 4.2 * nrows + 0.7),
            dpi=180,
            squeeze=False,
        )
        fig.patch.set_facecolor(_THEME["background"])
        for ax in axes.ravel()[len(selected_actions) :]:
            ax.axis("off")
        for ax, action in zip(axes.ravel(), selected_actions):
            _plot_snapshot(
                ax,
                instance=instance,
                target=target,
                action=action,
                relevant_satellite_ids=relevant_satellite_ids,
                propagators=propagators,
                track_window_min=track_window_min,
                track_step_s=track_step_s,
            )
        axes.ravel()[0].legend(
            handles=_snapshot_legend_handles(),
            loc="lower left",
            fontsize=7.2,
            frameon=True,
            framealpha=0.78,
            facecolor="white",
            edgecolor=_THEME["grid"],
        )

        fig.suptitle(
            f"{target.target_id}: {target.name}",
            fontsize=13,
            fontweight="bold",
            color=_THEME["text"],
        )
        max_gap_hours = _target_max_gap_hours(instance, target, actions)
        footer = (
            f"{len(actions)} observations by {len(relevant_satellite_ids)} satellites | "
            f"expected revisit {target.expected_revisit_period_hours:.1f}h"
        )
        footer += f" | scheduled max gap {max_gap_hours:.1f}h"
        fig.text(
            0.01,
            0.015,
            footer,
            ha="left",
            va="bottom",
            fontsize=9,
            color=_THEME["muted"],
        )
        fig.tight_layout(rect=(0, 0.06, 1, 0.93))
        output_path = _target_page_path(output_dir, target, target_index)
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        written.append(output_path)

    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render revisit_constellation case and solution plots."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    overview_parser = subparsers.add_parser(
        "overview",
        help="Render case-only target distribution overview.",
    )
    overview_parser.add_argument(
        "--case-dir",
        required=True,
        help="Path to dataset/cases/<split>/<case_id>.",
    )
    overview_parser.add_argument(
        "--out-path",
        type=Path,
        default=None,
        help="Output PNG path (default: benchmarks/revisit_constellation/visualizer/plots/<case_id>/overview.png).",
    )

    solution_parser = subparsers.add_parser(
        "solution",
        help="Render per-target solution action snapshots.",
    )
    solution_parser.add_argument(
        "--case-dir",
        required=True,
        help="Path to dataset/cases/<split>/<case_id>.",
    )
    solution_parser.add_argument(
        "--solution-path",
        required=True,
        help="Path to a revisit_constellation solution JSON file.",
    )
    solution_parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: benchmarks/revisit_constellation/visualizer/plots/<case_id>/solution/<solution_stem>).",
    )
    solution_parser.add_argument(
        "--max-targets",
        type=int,
        default=8,
        help="Maximum observed targets to render. Use 0 to render none.",
    )
    solution_parser.add_argument(
        "--max-actions-per-target",
        type=int,
        default=4,
        help="Maximum snapshots per target image.",
    )
    solution_parser.add_argument(
        "--track-window-min",
        type=float,
        default=90.0,
        help="Minutes of local ground-track context around each snapshot.",
    )
    solution_parser.add_argument(
        "--track-step-s",
        type=float,
        default=90.0,
        help="Ground-track sampling interval in seconds.",
    )

    args = parser.parse_args(argv)
    if args.command == "overview":
        out_path = render_overview(args.case_dir, args.out_path)
        print(f"Wrote {out_path.resolve()}")
        return 0

    paths = render_solution(
        args.case_dir,
        args.solution_path,
        args.out_dir,
        max_targets=args.max_targets,
        max_actions_per_target=args.max_actions_per_target,
        track_window_min=args.track_window_min,
        track_step_s=args.track_step_s,
    )
    for path in paths:
        print(f"Wrote {path.resolve()}")
    if not paths:
        print("No observed targets rendered")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
