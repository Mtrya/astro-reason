#!/usr/bin/env python3
"""Tiny synthetic sequential lexicographic CP-SAT solve."""

from __future__ import annotations

import json

from ortools.sat.python import cp_model


PRODUCTS = [
    {"id": "p_a", "covers": ("alpha",), "quality": 30},
    {"id": "p_b", "covers": ("beta",), "quality": 20},
    {"id": "p_c", "covers": ("alpha", "gamma"), "quality": 34},
    {"id": "p_d", "covers": ("beta", "gamma"), "quality": 33},
    {"id": "p_e", "covers": ("delta",), "quality": 15},
]

CONFLICTS = [("p_a", "p_c"), ("p_b", "p_d"), ("p_c", "p_d")]
TARGETS = ["alpha", "beta", "gamma", "delta"]


def build_model() -> tuple[cp_model.CpModel, dict[str, cp_model.IntVar], dict[str, cp_model.IntVar], object, object]:
    model = cp_model.CpModel()
    selected = {product["id"]: model.new_bool_var(f"select_{product['id']}") for product in PRODUCTS}
    covered = {target: model.new_bool_var(f"cover_{target}") for target in TARGETS}

    for left, right in CONFLICTS:
        model.add(selected[left] + selected[right] <= 1)

    for target in TARGETS:
        covering = [selected[product["id"]] for product in PRODUCTS if target in product["covers"]]
        model.add(covered[target] <= sum(covering))
        for variable in covering:
            model.add(covered[target] >= variable)

    coverage_expr = sum(covered.values())
    quality_expr = sum(int(product["quality"]) * selected[product["id"]] for product in PRODUCTS)
    return model, selected, covered, coverage_expr, quality_expr


def solve() -> dict[str, object]:
    model, selected, covered, coverage_expr, quality_expr = build_model()
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0

    model.maximize(coverage_expr)
    primary_status = solver.solve(model)
    if primary_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"primary_status": solver.status_name(primary_status), "selected": []}
    best_coverage = int(round(solver.objective_value))

    model.add(coverage_expr == best_coverage)
    model.maximize(quality_expr)
    secondary_status = solver.solve(model)
    if secondary_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "primary_status": solver.status_name(primary_status),
            "secondary_status": solver.status_name(secondary_status),
            "selected": [],
        }

    chosen = [product["id"] for product in PRODUCTS if solver.value(selected[product["id"]])]
    result = {
        "primary_status": solver.status_name(primary_status),
        "secondary_status": solver.status_name(secondary_status),
        "selected": chosen,
        "coverage": sum(int(solver.value(covered[target])) for target in TARGETS),
        "quality": sum(int(product["quality"]) for product in PRODUCTS if product["id"] in chosen),
        "bound": int(solver.best_objective_bound),
        "wall_time_s": round(solver.wall_time, 6),
    }
    assert result["primary_status"] == "OPTIMAL"
    assert result["secondary_status"] == "OPTIMAL"
    assert result["selected"] == ["p_a", "p_d", "p_e"]
    assert result["coverage"] == 4
    assert result["quality"] == 78
    return result


if __name__ == "__main__":
    print(json.dumps(solve(), sort_keys=True))
