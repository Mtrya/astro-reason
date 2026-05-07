#!/usr/bin/env python3
"""Plot main-agentic harness radar summaries."""

from __future__ import annotations

import argparse
import csv
import functools
import json
import math
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import aggregate as family_aggregate  # type: ignore[no-redef]
    import plan as family_plan  # type: ignore[no-redef]
else:
    from . import aggregate as family_aggregate
    from . import plan as family_plan

from experiments._shared import score_normalization as score_norm


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "matrix.yaml"
DEFAULT_OUTPUT = FAMILY_DIR / "reports" / "harness_radar.png"
DEFAULT_BASELINES = FAMILY_DIR / "baselines" / "main_solver.yaml"
BENCHMARK_ORDER = (
    "aeossp_standard",
    "regional_coverage",
    "relay_constellation",
    "revisit_constellation",
    "satnet",
    "spot5",
    "stereo_imaging",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot a radar chart of harness performance across main-agentic benchmarks."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Batch config whose aggregate summaries should be plotted.",
    )
    parser.add_argument(
        "--harness",
        action="append",
        default=[],
        help="Harness to include. May be repeated. Defaults to every harness with a plottable score.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output image path. Defaults to experiments/main_agentic/reports/harness_radar.png.",
    )
    parser.add_argument(
        "--no-aggregate",
        action="store_true",
        help="Do not regenerate aggregate summaries when the summary CSV is missing.",
    )
    parser.add_argument(
        "--baseline-data",
        type=Path,
        default=DEFAULT_BASELINES,
        help="YAML file containing main-solver baseline metrics.",
    )
    return parser.parse_args(argv)


def _summaries_root(config_path: Path) -> Path:
    plan = family_plan.build_batch_plan(
        config_path=config_path.resolve(),
        benchmark_filters=(),
        harness_filters=(),
        require_real_configs=False,
    )
    return plan.config.results.root / plan.config.config_path.stem / plan.config.results.aggregate_dir


def _summary_csv_path(config_path: Path) -> Path:
    return _summaries_root(config_path) / "benchmark_harness_summary.csv"


def _ensure_summary_csv(config_path: Path, *, no_aggregate: bool) -> Path:
    summary_csv = _summary_csv_path(config_path)
    if summary_csv.exists():
        return summary_csv
    if no_aggregate:
        raise SystemExit(f"Aggregate summary does not exist: {summary_csv}")
    family_aggregate.main(["--config", str(config_path)])
    if not summary_csv.exists():
        raise SystemExit(f"Aggregate summary was not created: {summary_csv}")
    return summary_csv


def _float_field(row: dict[str, str], key: str) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _numeric_row_metrics(row: dict[str, str]) -> dict[str, object]:
    metadata_fields = {
        "config_name",
        "benchmark",
        "harness",
        "split",
        "case_id",
        "result_path",
        "artifact_state",
        "mode",
        "overall_status",
        "agent_status",
        "verifier_status",
        "valid",
        "start_time",
        "end_time",
    }
    metrics: dict[str, object] = {}
    for key, value in row.items():
        if key in metadata_fields or value in (None, ""):
            continue
        numeric = _float_field(row, key)
        if numeric is not None:
            metrics[key] = numeric
    return metrics


def _parse_iso_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


def _case_key(split: str, case_id: str) -> str:
    return f"{split}/{case_id}"


def _case_dir(*, benchmark: str, split: str, case_id: str) -> Path:
    return (
        family_plan.REPO_ROOT
        / "benchmarks"
        / benchmark
        / "dataset"
        / "cases"
        / split
        / case_id
    )


def _load_json_file(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _load_yaml_file(path: Path) -> dict[str, object] | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def _horizon_seconds_from_strings(
    horizon_start: object,
    horizon_end: object,
) -> float | None:
    if not isinstance(horizon_start, str) or not isinstance(horizon_end, str):
        return None
    try:
        start = _parse_iso_datetime(horizon_start)
        end = _parse_iso_datetime(horizon_end)
    except ValueError:
        return None
    horizon_seconds = (end - start).total_seconds()
    return horizon_seconds if horizon_seconds > 0 else None


def _nested_number(payload: dict[str, object], path: tuple[str, ...]) -> float | None:
    current: object = payload
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return score_norm.to_float(current)


def _satellite_resource_models(path: Path) -> list[dict[str, object]]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    raw_satellites = data.get("satellites", data) if isinstance(data, dict) else data
    if not isinstance(raw_satellites, list):
        return []
    models: list[dict[str, object]] = []
    for satellite in raw_satellites:
        if not isinstance(satellite, dict):
            continue
        resource_model = satellite.get("resource_model")
        if isinstance(resource_model, dict):
            models.append(resource_model)
            continue
        power_model = satellite.get("power")
        if isinstance(power_model, dict):
            models.append(power_model)
    return models


def _satellite_battery_capacities(path: Path) -> list[float]:
    capacities: list[float] = []
    for resource_model in _satellite_resource_models(path):
        capacity = score_norm.to_float(resource_model.get("battery_capacity_wh"))
        if capacity is not None:
            capacities.append(capacity)
    return capacities


@functools.lru_cache(maxsize=None)
def _aeossp_case_constants(split: str, case_id: str) -> dict[str, float]:
    case_dir = _case_dir(benchmark="aeossp_standard", split=split, case_id=case_id)
    mission = _load_yaml_file(case_dir / "mission.yaml") or {}
    mission_payload = (
        mission.get("mission") if isinstance(mission.get("mission"), dict) else mission
    )
    horizon_seconds = (
        _horizon_seconds_from_strings(
            mission_payload.get("horizon_start"),
            mission_payload.get("horizon_end"),
        )
        if isinstance(mission_payload, dict)
        else None
    )
    battery_capacities = _satellite_battery_capacities(case_dir / "satellites.yaml")
    constants: dict[str, float] = {}
    if horizon_seconds is not None:
        constants["horizon_seconds"] = horizon_seconds
    if battery_capacities:
        constants["case_energy_budget"] = sum(battery_capacities)
    return constants


@functools.lru_cache(maxsize=None)
def _regional_case_constants(split: str, case_id: str) -> dict[str, float]:
    case_dir = _case_dir(benchmark="regional_coverage", split=split, case_id=case_id)
    manifest = _load_json_file(case_dir / "manifest.json") or {}
    max_actions = _nested_number(manifest, ("scoring", "max_actions_total"))
    battery_capacities = _satellite_battery_capacities(case_dir / "satellites.yaml")
    constants: dict[str, float] = {}
    if max_actions is not None:
        constants["max_actions_total"] = max_actions
    if battery_capacities:
        constants["battery_capacity_wh"] = max(battery_capacities)
    return constants


@functools.lru_cache(maxsize=None)
def _relay_case_constants(split: str, case_id: str) -> dict[str, float]:
    case_dir = _case_dir(benchmark="relay_constellation", split=split, case_id=case_id)
    manifest = _load_json_file(case_dir / "manifest.json") or {}
    max_added = _nested_number(manifest, ("constraints", "max_added_satellites"))
    return {"max_added_satellites": max_added} if max_added is not None else {}


@functools.lru_cache(maxsize=None)
def _revisit_case_constants(split: str, case_id: str) -> dict[str, float]:
    case_dir = _case_dir(benchmark="revisit_constellation", split=split, case_id=case_id)
    mission = _load_json_file(case_dir / "mission.json") or {}
    assets = _load_json_file(case_dir / "assets.json") or {}
    horizon_seconds = _horizon_seconds_from_strings(
        mission.get("horizon_start"),
        mission.get("horizon_end"),
    )
    expected_values: list[float] = []
    targets = mission.get("targets")
    if isinstance(targets, list):
        for target in targets:
            if isinstance(target, dict):
                expected = score_norm.to_float(
                    target.get("expected_revisit_period_hours")
                )
                if expected is not None:
                    expected_values.append(expected)
    max_satellites = score_norm.to_float(assets.get("max_num_satellites"))
    constants: dict[str, float] = {}
    if horizon_seconds is not None:
        constants["horizon_hours"] = horizon_seconds / 3600.0
    if expected_values:
        constants["expected_revisit_hours"] = sum(expected_values) / len(expected_values)
    if max_satellites is not None:
        constants["max_satellites"] = max_satellites
    return constants


def _load_baseline_data(path: Path) -> dict[str, object]:
    data = _load_yaml_file(path)
    if data is None:
        raise SystemExit(f"Baseline data must be a YAML mapping: {path}")
    if not isinstance(data.get("rows"), list):
        raise SystemExit(f"Baseline data must contain a rows list: {path}")
    return data


def _baseline_rows(baseline_data: dict[str, object]) -> list[dict[str, object]]:
    rows = baseline_data.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _normalization_config(
    baseline_data: dict[str, object],
    benchmark: str,
) -> dict[str, object]:
    normalization = baseline_data.get("normalization")
    if not isinstance(normalization, dict):
        return {}
    config = normalization.get(benchmark)
    return config if isinstance(config, dict) else {}


def _normalized_score_pct(
    *,
    benchmark: str,
    split: str,
    case_id: str,
    metrics: dict[str, object],
    baseline_data: dict[str, object],
) -> float | None:
    if benchmark == "aeossp_standard":
        constants = _aeossp_case_constants(split, case_id)
        return score_norm.aeossp_standard_score_pct(
            wcr=metrics.get("WCR"),
            cr=metrics.get("CR"),
            tat=metrics.get("TAT"),
            pc=metrics.get("PC"),
            horizon_seconds=constants.get("horizon_seconds"),
            case_energy_budget=constants.get("case_energy_budget"),
        )
    if benchmark == "regional_coverage":
        constants = _regional_case_constants(split, case_id)
        return score_norm.regional_coverage_score_pct(
            weighted_coverage_ratio=metrics.get("weighted_coverage_ratio"),
            coverage_ratio=metrics.get("coverage_ratio"),
            num_actions=metrics.get("num_actions"),
            min_battery_wh=metrics.get("min_battery_wh"),
            max_actions_total=constants.get("max_actions_total"),
            battery_capacity_wh=constants.get("battery_capacity_wh"),
        )
    if benchmark == "relay_constellation":
        constants = _relay_case_constants(split, case_id)
        config = _normalization_config(baseline_data, benchmark)
        return score_norm.relay_constellation_score_pct(
            service_fraction=metrics.get("service_fraction"),
            worst_demand_service_fraction=metrics.get("worst_demand_service_fraction"),
            num_added_satellites=metrics.get("num_added_satellites"),
            mean_latency_ms=metrics.get("mean_latency_ms"),
            latency_p95_ms=metrics.get("latency_p95_ms"),
            min_added_satellites=config.get("min_added_satellites"),
            max_added_satellites=constants.get("max_added_satellites"),
            latency_cap_ms=config.get("latency_cap_ms"),
        )
    if benchmark == "revisit_constellation":
        constants = _revisit_case_constants(split, case_id)
        max_gap = score_norm.to_float(metrics.get("capped_max_revisit_gap_hours"))
        expected = constants.get("expected_revisit_hours")
        horizon = constants.get("horizon_hours")
        if max_gap is None or expected is None or horizon is None:
            return None
        gap_score = score_norm.revisit_target_gap_score(
            max_gap_hours=max_gap,
            expected_revisit_hours=expected,
            horizon_hours=horizon,
        )
        config = _normalization_config(baseline_data, benchmark)
        return score_norm.revisit_constellation_score_pct(
            gap_score=gap_score,
            num_satellites=metrics.get("num_satellites"),
            min_satellites=config.get("min_satellites"),
            max_satellites=constants.get("max_satellites"),
        )
    if benchmark == "satnet":
        config = _normalization_config(baseline_data, benchmark)
        return score_norm.satnet_score_pct(
            u_rms=metrics.get("u_rms"),
            u_max=metrics.get("u_max"),
            u_rms_cap=config.get("u_rms_cap"),
            u_max_cap=config.get("u_max_cap"),
        )
    if benchmark == "spot5":
        return score_norm.spot5_score_pct(
            computed_profit=metrics.get("computed_profit"),
            total_possible_profit=family_aggregate._spot5_max_profit(split, case_id),
        )
    if benchmark == "stereo_imaging":
        return score_norm.stereo_imaging_score_pct(
            normalized_quality=metrics.get("normalized_quality"),
        )
    return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _best_solver_scores_by_case(
    baseline_data: dict[str, object],
) -> dict[str, dict[str, float]]:
    scores: dict[str, dict[str, float]] = {}
    for row in _baseline_rows(baseline_data):
        benchmark = row.get("benchmark")
        split = row.get("split")
        case_id = row.get("case_id")
        metrics = row.get("metrics")
        if not isinstance(benchmark, str) or not isinstance(split, str):
            continue
        if case_id is None or not isinstance(metrics, dict):
            continue
        normalized_score = _normalized_score_pct(
            benchmark=benchmark,
            split=split,
            case_id=str(case_id),
            metrics=metrics,
            baseline_data=baseline_data,
        )
        if normalized_score is None or normalized_score <= 0:
            continue
        case_key = _case_key(split, str(case_id))
        current = scores.setdefault(benchmark, {}).get(case_key)
        if current is None or normalized_score > current:
            scores[benchmark][case_key] = normalized_score
    return scores


def _load_scores(
    summaries_root: Path,
    baseline_data: dict[str, object],
) -> tuple[list[str], dict[str, dict[str, float]]]:
    best_solver_scores = _best_solver_scores_by_case(baseline_data)
    scores_by_harness_benchmark: dict[str, dict[str, list[float]]] = {}
    for benchmark in BENCHMARK_ORDER:
        csv_path = summaries_root / "benchmarks" / f"{benchmark}.csv"
        if not csv_path.exists():
            continue
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("valid") != "True":
                    score = 0.0
                else:
                    normalized_score = _normalized_score_pct(
                        benchmark=benchmark,
                        split=row.get("split", ""),
                        case_id=row.get("case_id", ""),
                        metrics=_numeric_row_metrics(row),
                        baseline_data=baseline_data,
                    )
                    baseline = best_solver_scores.get(benchmark, {}).get(
                        _case_key(row.get("split", ""), row.get("case_id", ""))
                    )
                    if normalized_score is None or baseline is None or baseline <= 0:
                        continue
                    score = 100.0 * normalized_score / baseline
                scores_by_harness_benchmark.setdefault(row["harness"], {}).setdefault(
                    benchmark, []
                ).append(score)

    scores: dict[str, dict[str, float]] = {}
    for harness, benchmark_scores in scores_by_harness_benchmark.items():
        for benchmark, values in benchmark_scores.items():
            mean_score = _mean(values)
            if mean_score is not None:
                scores.setdefault(harness, {})[benchmark] = mean_score
    benchmarks = [
        benchmark
        for benchmark in BENCHMARK_ORDER
        if any(benchmark in item for item in scores.values())
    ]
    return benchmarks, scores


def _selected_scores(
    scores: dict[str, dict[str, float]],
    requested_harnesses: list[str],
) -> dict[str, dict[str, float]]:
    if not requested_harnesses:
        return scores
    missing = [harness for harness in requested_harnesses if harness not in scores]
    if missing:
        raise SystemExit(
            "No plottable scores for harness(es): " + ", ".join(sorted(missing))
        )
    return {harness: scores[harness] for harness in requested_harnesses}


def _plot_radar(
    *,
    benchmarks: list[str],
    scores: dict[str, dict[str, float]],
    output_path: Path,
) -> None:
    if not benchmarks:
        raise SystemExit("No benchmarks were found in the aggregate summary.")
    if not scores:
        raise SystemExit("No plottable harness scores were found in the aggregate summary.")

    os.environ.setdefault(
        "MPLCONFIGDIR",
        str(Path(tempfile.gettempdir()) / "astroreason-main-agentic-matplotlib"),
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [benchmark.replace("_", "\n") for benchmark in benchmarks]
    angles = [2 * math.pi * index / len(benchmarks) for index in range(len(benchmarks))]
    closed_angles = angles + angles[:1]
    max_score = max(
        [100.0]
        + [
            score
            for harness_scores in scores.values()
            for score in harness_scores.values()
        ]
    )
    radial_max = math.ceil(max_score / 10.0) * 10.0

    fig, ax = plt.subplots(figsize=(9, 7), subplot_kw={"projection": "polar"})
    for harness, harness_scores in sorted(scores.items()):
        values = [harness_scores.get(benchmark, 0.0) for benchmark in benchmarks]
        closed_values = values + values[:1]
        ax.plot(closed_angles, closed_values, linewidth=2, label=harness)
        ax.fill(closed_angles, closed_values, alpha=0.08)

    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, radial_max)
    ax.set_yticks([tick for tick in (25, 50, 75, 100) if tick <= radial_max])
    ax.set_yticklabels([f"{tick:g}%" for tick in ax.get_yticks()], fontsize=8)
    ax.legend(loc="upper right", bbox_to_anchor=(1.28, 1.12), frameon=False)
    ax.grid(True, alpha=0.35)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.resolve()
    _ensure_summary_csv(config_path, no_aggregate=args.no_aggregate)
    baseline_data = _load_baseline_data(args.baseline_data.resolve())
    benchmarks, scores = _load_scores(_summaries_root(config_path), baseline_data)
    selected_scores = _selected_scores(scores, list(args.harness))
    _plot_radar(
        benchmarks=benchmarks,
        scores=selected_scores,
        output_path=args.output.resolve(),
    )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
