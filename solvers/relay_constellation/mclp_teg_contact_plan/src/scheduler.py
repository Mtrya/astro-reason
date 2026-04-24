"""Deterministic greedy contact scheduler with interval compaction."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable

from .case_io import Case, DemandWindow
from .link_cache import LinkRecord
from .time_grid import build_time_grid


def _isoformat_z(value: datetime) -> str:
    return value.astimezone(__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z")


def build_per_sample_links(
    link_records: Iterable[LinkRecord],
) -> dict[int, list[LinkRecord]]:
    """Group link records by sample index."""
    result: dict[int, list[LinkRecord]] = defaultdict(list)
    for rec in link_records:
        result[rec.sample_index].append(rec)
    return dict(result)


def _build_demands_by_sample(
    case: Case,
    sample_times: tuple[datetime, ...],
) -> dict[int, list[DemandWindow]]:
    """Map each sample index to the list of demands active at that sample."""
    result: dict[int, list[DemandWindow]] = defaultdict(list)
    for demand in case.demands.demanded_windows:
        for sidx, st in enumerate(sample_times):
            if demand.start_time <= st <= demand.end_time:
                result[sidx].append(demand)
    return dict(result)


def _build_ground_adjacency_at_sample(
    link_records: Iterable[LinkRecord],
    sample_index: int,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return (endpoint_to_sats, sat_to_endpoints) for a single sample."""
    ep_to_sats: dict[str, set[str]] = defaultdict(set)
    sat_to_eps: dict[str, set[str]] = defaultdict(set)
    for rec in link_records:
        if rec.sample_index != sample_index:
            continue
        if rec.link_type == "ground":
            ep_to_sats[rec.node_a].add(rec.node_b)
            ep_to_sats[rec.node_b].add(rec.node_a)
            sat_to_eps[rec.node_a].add(rec.node_b)
            sat_to_eps[rec.node_b].add(rec.node_a)
    return (
        {k: set(v) for k, v in ep_to_sats.items()},
        {k: set(v) for k, v in sat_to_eps.items()},
    )


def _build_isl_adjacency_at_sample(
    link_records: Iterable[LinkRecord],
    sample_index: int,
) -> dict[str, set[str]]:
    """Return sat_to_sats ISL adjacency for a single sample."""
    sat_to_sats: dict[str, set[str]] = defaultdict(set)
    for rec in link_records:
        if rec.sample_index != sample_index:
            continue
        if rec.link_type == "isl":
            sat_to_sats[rec.node_a].add(rec.node_b)
            sat_to_sats[rec.node_b].add(rec.node_a)
    return {k: set(v) for k, v in sat_to_sats.items()}


def score_ground_link(
    record: LinkRecord,
    active_demands: list[DemandWindow],
) -> float:
    """Utility of a ground link = sum of weights of active demands involving the endpoint."""
    # Determine which node is the endpoint
    # In our link cache, ground links store endpoint as node_a and satellite as node_b
    # But we also added the reverse in build_ground_and_isl_maps. Here we only use LinkRecord.
    # The original build_link_cache stores: node_a=endpoint_id, node_b=satellite_id
    endpoint_id = record.node_a
    utility = 0.0
    for demand in active_demands:
        if demand.source_endpoint_id == endpoint_id or demand.destination_endpoint_id == endpoint_id:
            utility += demand.weight
    return utility


def score_isl(
    record: LinkRecord,
    active_demands: list[DemandWindow],
    sat_to_eps: dict[str, set[str]],
) -> float:
    """Utility of an ISL = sum of weights of active demands it could help bridge."""
    sat_a = record.node_a
    sat_b = record.node_b
    eps_a = sat_to_eps.get(sat_a, set())
    eps_b = sat_to_eps.get(sat_b, set())
    if not eps_a or not eps_b:
        return 0.0
    utility = 0.0
    for demand in active_demands:
        src = demand.source_endpoint_id
        dst = demand.destination_endpoint_id
        if (src in eps_a and dst in eps_b) or (src in eps_b and dst in eps_a):
            utility += demand.weight
    return utility


def _normalize_link_key(link_type: str, node_a: str, node_b: str) -> tuple[str, str, str]:
    if link_type == "isl":
        a, b = sorted((node_a, node_b))
        return ("isl", a, b)
    # ground_link: endpoint is node_a, satellite is node_b (preserve orientation for clarity)
    return ("ground", node_a, node_b)


def greedy_select_links(
    sample_index: int,
    feasible_links: list[LinkRecord],
    active_demands: list[DemandWindow],
    max_links_per_satellite: int,
    max_links_per_endpoint: int,
) -> set[tuple[str, str, str]]:
    """Select a subset of feasible links at one sample via deterministic greedy.

    Returns a set of normalized link keys.
    """
    _, sat_to_eps = _build_ground_adjacency_at_sample(feasible_links, sample_index)
    isl_adj = _build_isl_adjacency_at_sample(feasible_links, sample_index)

    scored: list[tuple[float, float, str, str, str]] = []
    for rec in feasible_links:
        if rec.link_type == "ground":
            utility = score_ground_link(rec, active_demands)
        else:
            utility = score_isl(rec, active_demands, sat_to_eps)
        scored.append((utility, rec.distance_m, rec.link_type, rec.node_a, rec.node_b))

    # Sort by utility desc, distance asc, then deterministic tie-break on normalized key
    def sort_key(item: tuple[float, float, str, str, str]) -> tuple:
        utility, distance, link_type, node_a, node_b = item
        norm = _normalize_link_key(link_type, node_a, node_b)
        return (-utility, distance, norm)

    scored.sort(key=sort_key)

    selected: set[tuple[str, str, str]] = set()
    sat_degree: dict[str, int] = defaultdict(int)
    ep_degree: dict[str, int] = defaultdict(int)

    for utility, _distance, link_type, node_a, node_b in scored:
        key = _normalize_link_key(link_type, node_a, node_b)
        if key in selected:
            continue

        if link_type == "ground":
            endpoint_id = node_a
            satellite_id = node_b
            if ep_degree[endpoint_id] >= max_links_per_endpoint:
                continue
            if sat_degree[satellite_id] >= max_links_per_satellite:
                continue
            selected.add(key)
            ep_degree[endpoint_id] += 1
            sat_degree[satellite_id] += 1
        else:  # isl
            sat_a = node_a
            sat_b = node_b
            if sat_degree[sat_a] >= max_links_per_satellite:
                continue
            if sat_degree[sat_b] >= max_links_per_satellite:
                continue
            selected.add(key)
            sat_degree[sat_a] += 1
            sat_degree[sat_b] += 1

    return selected


def compact_intervals(
    selected_links_by_sample: dict[int, set[tuple[str, str, str]]],
    sample_times: tuple[datetime, ...],
    routing_step_s: int,
) -> list[dict]:
    """Turn per-sample selected links into compacted interval actions."""
    # The verifier's total_samples = len(sample_times) - 1 because sample_times
    # includes horizon_end as the last entry, but no action can cover that sample.
    total_samples = len(sample_times) - 1

    # Collect sample indices per link
    link_samples: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for sidx, links in selected_links_by_sample.items():
        for key in links:
            link_samples[key].append(sidx)

    actions: list[dict] = []
    for key, sidxs in link_samples.items():
        sidxs_sorted = sorted(set(sidxs))
        # Group into consecutive runs
        runs: list[list[int]] = []
        current_run: list[int] = []
        for sidx in sidxs_sorted:
            if not current_run or sidx == current_run[-1] + 1:
                current_run.append(sidx)
            else:
                runs.append(current_run)
                current_run = [sidx]
        if current_run:
            runs.append(current_run)

        link_type, node_a, node_b = key
        for run in runs:
            start_idx = run[0]
            # Runs that start at or after total_samples cannot be scheduled
            if start_idx >= total_samples:
                continue
            end_idx = min(run[-1] + 1, total_samples)  # exclusive, capped at horizon_end
            start_time = sample_times[start_idx]
            end_time = sample_times[end_idx]

            if link_type == "ground":
                actions.append({
                    "action_type": "ground_link",
                    "endpoint_id": node_a,
                    "satellite_id": node_b,
                    "start_time": _isoformat_z(start_time),
                    "end_time": _isoformat_z(end_time),
                })
            else:
                actions.append({
                    "action_type": "inter_satellite_link",
                    "satellite_id_1": node_a,
                    "satellite_id_2": node_b,
                    "start_time": _isoformat_z(start_time),
                    "end_time": _isoformat_z(end_time),
                })

    # Deterministic output order
    actions.sort(key=lambda a: (a["action_type"], a.get("endpoint_id", ""), a.get("satellite_id", ""), a.get("satellite_id_1", ""), a.get("satellite_id_2", ""), a["start_time"]))
    return actions


def _local_validate(
    actions: list[dict],
    case: Case,
    sample_times: tuple[datetime, ...],
) -> list[str]:
    """Solver-side sanity checks (not a full verifier replica)."""
    violations: list[str] = []
    step = timedelta(seconds=case.manifest.routing_step_s)
    horizon_start = sample_times[0]
    horizon_end = sample_times[-1]

    # Check grid alignment and non-zero duration
    for idx, action in enumerate(actions):
        try:
            start = datetime.fromisoformat(action["start_time"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(action["end_time"].replace("Z", "+00:00"))
        except Exception as exc:
            violations.append(f"actions[{idx}] invalid datetime: {exc}")
            continue

        if end <= start:
            violations.append(f"actions[{idx}] has zero or negative duration")
            continue

        delta_start = start - horizon_start
        idx_start_float = delta_start.total_seconds() / step.total_seconds()
        if abs(idx_start_float - round(idx_start_float)) > 1e-9:
            violations.append(f"actions[{idx}] start_time is not grid-aligned")

        delta_end = end - horizon_start
        idx_end_float = delta_end.total_seconds() / step.total_seconds()
        if abs(idx_end_float - round(idx_end_float)) > 1e-9:
            violations.append(f"actions[{idx}] end_time is not grid-aligned")

    # Check no overlapping actions on same physical link
    link_intervals: dict[tuple, list[tuple[int, int, int]]] = defaultdict(list)
    for idx, action in enumerate(actions):
        atype = action["action_type"]
        if atype == "ground_link":
            key = ("ground_link", action["endpoint_id"], action["satellite_id"])
        else:
            a, b = sorted((action["satellite_id_1"], action["satellite_id_2"]))
            key = ("inter_satellite_link", a, b)

        start = datetime.fromisoformat(action["start_time"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(action["end_time"].replace("Z", "+00:00"))
        sidx = int(round((start - horizon_start).total_seconds() / step.total_seconds()))
        eidx = int(round((end - horizon_start).total_seconds() / step.total_seconds()))
        link_intervals[key].append((sidx, eidx, idx))

    for key, intervals in link_intervals.items():
        intervals.sort()
        prev_end = None
        prev_idx = None
        for sidx, eidx, idx in intervals:
            if prev_end is not None and sidx < prev_end:
                violations.append(
                    f"actions[{idx}] overlaps another action on link {key}"
                )
            prev_end = eidx
            prev_idx = idx

    # Check per-sample degree caps
    satellite_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    endpoint_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for idx, action in enumerate(actions):
        start = datetime.fromisoformat(action["start_time"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(action["end_time"].replace("Z", "+00:00"))
        sidx = int(round((start - horizon_start).total_seconds() / step.total_seconds()))
        eidx = int(round((end - horizon_start).total_seconds() / step.total_seconds()))
        for sample_idx in range(sidx, eidx):
            if action["action_type"] == "ground_link":
                ep = action["endpoint_id"]
                sat = action["satellite_id"]
                endpoint_counts[sample_idx][ep] += 1
                satellite_counts[sample_idx][sat] += 1
            else:
                sat1 = action["satellite_id_1"]
                sat2 = action["satellite_id_2"]
                satellite_counts[sample_idx][sat1] += 1
                satellite_counts[sample_idx][sat2] += 1

    for sample_idx, counts in satellite_counts.items():
        for sat_id, count in counts.items():
            if count > case.manifest.constraints.max_links_per_satellite:
                violations.append(
                    f"Satellite {sat_id} has {count} links at sample {sample_idx}, "
                    f"exceeding max={case.manifest.constraints.max_links_per_satellite}"
                )
    for sample_idx, counts in endpoint_counts.items():
        for ep_id, count in counts.items():
            if count > case.manifest.constraints.max_links_per_endpoint:
                violations.append(
                    f"Endpoint {ep_id} has {count} links at sample {sample_idx}, "
                    f"exceeding max={case.manifest.constraints.max_links_per_endpoint}"
                )

    return violations


def _run_greedy_scheduler(
    case: Case,
    sample_times: tuple[datetime, ...],
    link_records: Iterable[LinkRecord],
    selected_satellite_ids: set[str] | None = None,
) -> tuple[list[dict], dict]:
    """Run the full greedy scheduler and return actions plus summary."""
    # Filter links to only involve selected candidates (plus backbone)
    backbone_ids = {s.satellite_id for s in case.network.backbone_satellites}
    allowed_sats = backbone_ids | (selected_satellite_ids or set())
    filtered_records = [
        rec for rec in link_records
        if (rec.link_type == "ground" and rec.node_b in allowed_sats)
        or (rec.link_type == "isl" and rec.node_a in allowed_sats and rec.node_b in allowed_sats)
    ]
    per_sample = build_per_sample_links(filtered_records)
    demands_by_sample = _build_demands_by_sample(case, sample_times)

    max_sat = case.manifest.constraints.max_links_per_satellite
    max_ep = case.manifest.constraints.max_links_per_endpoint

    selected_by_sample: dict[int, set[tuple[str, str, str]]] = {}
    total_selected = 0
    total_utility = 0.0

    for sidx in sorted(per_sample.keys()):
        active_demands = demands_by_sample.get(sidx, [])
        feasible = per_sample[sidx]
        selected = greedy_select_links(
            sidx, feasible, active_demands, max_sat, max_ep
        )
        selected_by_sample[sidx] = selected
        total_selected += len(selected)
        # Recompute utility for summary
        _, sat_to_eps = _build_ground_adjacency_at_sample(feasible, sidx)
        for key in selected:
            link_type, node_a, node_b = key
            # Find the original record to score
            for rec in feasible:
                if rec.link_type == link_type:
                    nkey = _normalize_link_key(rec.link_type, rec.node_a, rec.node_b)
                    if nkey == key:
                        if link_type == "ground":
                            total_utility += score_ground_link(rec, active_demands)
                        else:
                            total_utility += score_isl(rec, active_demands, sat_to_eps)
                        break

    actions = compact_intervals(
        selected_by_sample, sample_times, case.manifest.routing_step_s
    )

    local_violations = _local_validate(actions, case, sample_times)

    num_ground = sum(1 for a in actions if a["action_type"] == "ground_link")
    num_isl = sum(1 for a in actions if a["action_type"] == "inter_satellite_link")

    summary = {
        "scheduler_mode": "greedy",
        "milp_attempted": False,
        "milp_fallback_reason": None,
        "milp_model_variables": None,
        "milp_model_constraints": None,
        "milp_total_solve_time_s": None,
        "milp_per_sample_solve_times_s": None,
        "num_samples_with_links": len(selected_by_sample),
        "total_selected_links": total_selected,
        "total_utility": round(total_utility, 6),
        "num_actions": len(actions),
        "num_ground_actions": num_ground,
        "num_isl_actions": num_isl,
        "local_violations": local_violations,
    }

    return actions, summary


def run_scheduler(
    case: Case,
    sample_times: tuple[datetime, ...],
    link_records: Iterable[LinkRecord],
    selected_satellite_ids: set[str] | None = None,
    scheduler_mode: str = "auto",
    milp_config: dict[str, Any] | None = None,
) -> tuple[list[dict], dict]:
    """Run the contact scheduler (MILP or greedy) and return actions plus summary.

    Parameters
    ----------
    scheduler_mode : "auto", "greedy", or "milp"
        "auto" tries MILP for small problems and falls back to greedy.
        "greedy" always uses the greedy scheduler.
        "milp" requires MILP to succeed; raises RuntimeError on failure.
    milp_config : optional dict with keys:
        - max_total_variables (int, default 500)
        - max_samples (int, default 50)
        - milp_time_limit_per_sample (float, default 5.0)
    """
    cfg = milp_config or {}
    mode = scheduler_mode.lower().strip()

    if mode == "greedy":
        return _run_greedy_scheduler(case, sample_times, link_records, selected_satellite_ids)

    # Lazy import to avoid circular dependency at module load time
    from .milp_scheduler import milp_scheduler_available, run_milp_scheduler

    if mode == "milp":
        result = run_milp_scheduler(
            case,
            sample_times,
            link_records,
            selected_satellite_ids=selected_satellite_ids,
            milp_time_limit_per_sample=cfg.get("milp_time_limit_per_sample", 5.0),
            max_total_variables=cfg.get("max_total_variables", 500),
            max_samples=cfg.get("max_samples", 50),
        )
        if result is None:
            raise RuntimeError("MILP scheduler failed or exceeded bounds")
        return result

    # auto mode
    if not milp_scheduler_available():
        actions, summary = _run_greedy_scheduler(
            case, sample_times, link_records, selected_satellite_ids
        )
        summary["milp_attempted"] = False
        summary["milp_fallback_reason"] = "pulp_cbc_unavailable"
        return actions, summary

    result = run_milp_scheduler(
        case,
        sample_times,
        link_records,
        selected_satellite_ids=selected_satellite_ids,
        milp_time_limit_per_sample=cfg.get("milp_time_limit_per_sample", 5.0),
        max_total_variables=cfg.get("max_total_variables", 500),
        max_samples=cfg.get("max_samples", 50),
    )
    if result is not None:
        return result

    actions, summary = _run_greedy_scheduler(
        case, sample_times, link_records, selected_satellite_ids
    )
    summary["milp_attempted"] = True
    summary["milp_fallback_reason"] = "problem_too_large_or_solver_failed"
    return actions, summary
