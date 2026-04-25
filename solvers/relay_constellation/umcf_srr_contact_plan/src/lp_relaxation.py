"""Path-restricted LP relaxation for per-sample UMCF instances."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .umcf import UMCFInstance


class LPBackendError(RuntimeError):
    """Raised when the configured LP backend cannot solve the relaxation."""


@dataclass(frozen=True)
class LPRelaxationConfig:
    """Configuration for the path-restricted LP relaxation."""

    backend: str = "scipy-highs"
    tolerance: float = 1e-9
    path_cost_epsilon: float = 0.0


@dataclass
class LPRelaxationResult:
    """Fractional path values and diagnostics for one per-sample LP."""

    sample_index: int
    path_values: dict[str, list[float]]
    success: bool
    status: str
    message: str
    objective_value: float
    solve_time_s: float
    variable_count: int
    constraint_count: int
    commodity_count: int
    zero_path_commodities: list[str] = field(default_factory=list)
    positive_variable_count: int = 0
    fractional_variable_count: int = 0

    def compact_summary(self) -> dict[str, Any]:
        return {
            "sample_index": self.sample_index,
            "success": self.success,
            "status": self.status,
            "message": self.message,
            "objective_value": round(self.objective_value, 6),
            "solve_time_s": round(self.solve_time_s, 6),
            "variable_count": self.variable_count,
            "constraint_count": self.constraint_count,
            "commodity_count": self.commodity_count,
            "zero_path_commodities": list(self.zero_path_commodities),
            "positive_variable_count": self.positive_variable_count,
            "fractional_variable_count": self.fractional_variable_count,
        }


def path_node_usage(path: Any) -> dict[str, int]:
    """Return per-node degree consumed by a selected path-like object."""
    usage: dict[str, int] = {}
    for a, b in path.edges:
        usage[a] = usage.get(a, 0) + 1
        usage[b] = usage.get(b, 0) + 1
    return usage


def solve_path_restricted_lp(
    instance: UMCFInstance,
    path_sets: dict[str, list[Any]],
    config: LPRelaxationConfig | None = None,
) -> LPRelaxationResult:
    """Solve the finite-path UMCF LP relaxation for one sample."""
    config = config or LPRelaxationConfig()
    if config.backend != "scipy-highs":
        raise LPBackendError(f"unsupported LP backend: {config.backend!r}")

    try:
        from scipy.optimize import linprog
    except Exception as exc:  # pragma: no cover - exercised only without setup
        raise LPBackendError(
            "scipy is required for LP mode; run the solver-local setup.sh first"
        ) from exc

    variable_keys: list[tuple[str, int]] = []
    zero_path_commodities: list[str] = []
    for commodity in instance.commodities:
        paths = path_sets.get(commodity.demand_id, [])
        if not paths:
            zero_path_commodities.append(commodity.demand_id)
            continue
        for path_index in range(len(paths)):
            variable_keys.append((commodity.demand_id, path_index))

    variable_count = len(variable_keys)
    if variable_count == 0:
        return LPRelaxationResult(
            sample_index=instance.sample_index,
            path_values={commodity.demand_id: [] for commodity in instance.commodities},
            success=True,
            status="no_variables",
            message="no reachable commodity paths",
            objective_value=0.0,
            solve_time_s=0.0,
            variable_count=0,
            constraint_count=0,
            commodity_count=len(instance.commodities),
            zero_path_commodities=zero_path_commodities,
        )

    commodity_by_id = {commodity.demand_id: commodity for commodity in instance.commodities}
    c: list[float] = []
    for demand_id, path_index in variable_keys:
        commodity = commodity_by_id[demand_id]
        path = path_sets[demand_id][path_index]
        path_penalty = config.path_cost_epsilon * float(path.total_distance_m)
        c.append(-(float(commodity.weight) - path_penalty))

    rows: list[list[float]] = []
    rhs: list[float] = []

    for commodity in instance.commodities:
        row = [0.0] * variable_count
        for column, (demand_id, _) in enumerate(variable_keys):
            if demand_id == commodity.demand_id:
                row[column] = 1.0
        if any(row):
            rows.append(row)
            rhs.append(1.0)

    for edge, capacity in sorted(instance.edge_capacity.items()):
        row = [0.0] * variable_count
        for column, (demand_id, path_index) in enumerate(variable_keys):
            if edge in path_sets[demand_id][path_index].edges:
                row[column] = 1.0
        if any(row):
            rows.append(row)
            rhs.append(float(capacity))

    for node, capacity in sorted(instance.node_capacity.items()):
        row = [0.0] * variable_count
        for column, (demand_id, path_index) in enumerate(variable_keys):
            usage = path_node_usage(path_sets[demand_id][path_index]).get(node, 0)
            if usage:
                row[column] = float(usage)
        if any(row):
            rows.append(row)
            rhs.append(float(capacity))

    t0 = time.perf_counter()
    result = linprog(
        c=c,
        A_ub=rows,
        b_ub=rhs,
        bounds=[(0.0, 1.0)] * variable_count,
        method="highs",
    )
    solve_time = time.perf_counter() - t0

    if not result.success:
        return LPRelaxationResult(
            sample_index=instance.sample_index,
            path_values={commodity.demand_id: [0.0] * len(path_sets.get(commodity.demand_id, [])) for commodity in instance.commodities},
            success=False,
            status=str(result.status),
            message=str(result.message),
            objective_value=0.0,
            solve_time_s=solve_time,
            variable_count=variable_count,
            constraint_count=len(rows),
            commodity_count=len(instance.commodities),
            zero_path_commodities=zero_path_commodities,
        )

    values = [max(0.0, float(value)) for value in result.x]
    path_values = {
        commodity.demand_id: [0.0] * len(path_sets.get(commodity.demand_id, []))
        for commodity in instance.commodities
    }
    for value, (demand_id, path_index) in zip(values, variable_keys):
        if abs(value) <= config.tolerance:
            value = 0.0
        elif abs(value - 1.0) <= config.tolerance:
            value = 1.0
        path_values[demand_id][path_index] = value

    positive_count = sum(1 for value in values if value > config.tolerance)
    fractional_count = sum(
        1
        for value in values
        if config.tolerance < value < 1.0 - config.tolerance
    )

    return LPRelaxationResult(
        sample_index=instance.sample_index,
        path_values=path_values,
        success=True,
        status=str(result.status),
        message=str(result.message),
        objective_value=-float(result.fun),
        solve_time_s=solve_time,
        variable_count=variable_count,
        constraint_count=len(rows),
        commodity_count=len(instance.commodities),
        zero_path_commodities=zero_path_commodities,
        positive_variable_count=positive_count,
        fractional_variable_count=fractional_count,
    )


def summarize_lp_results(results: list[LPRelaxationResult]) -> dict[str, Any]:
    """Return compact aggregate diagnostics for a sequence of LP solves."""
    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1

    total_solve_time = sum(result.solve_time_s for result in results)
    total_variables = sum(result.variable_count for result in results)
    total_constraints = sum(result.constraint_count for result in results)
    return {
        "backend": "scipy-highs",
        "num_lps": len(results),
        "successful_lps": sum(1 for result in results if result.success),
        "status_counts": status_counts,
        "total_solve_time_s": round(total_solve_time, 6),
        "total_variables": total_variables,
        "total_constraints": total_constraints,
        "total_positive_variables": sum(result.positive_variable_count for result in results),
        "total_fractional_variables": sum(result.fractional_variable_count for result in results),
        "total_zero_path_commodities": sum(len(result.zero_path_commodities) for result in results),
        "objective_value_sum": round(sum(result.objective_value for result in results), 6),
        "samples": [result.compact_summary() for result in results],
    }
