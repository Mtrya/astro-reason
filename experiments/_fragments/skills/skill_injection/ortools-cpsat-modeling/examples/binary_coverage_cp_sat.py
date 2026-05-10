#!/usr/bin/env python3
"""Tiny synthetic CP-SAT product-selection example with coverage and conflicts."""

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


def solve() -> dict[str, object]:
    model = cp_model.CpModel()
    selected = {product["id"]: model.new_bool_var(f"select_{product['id']}") for product in PRODUCTS}
    covered = {target: model.new_bool_var(f"cover_{target}") for target in TARGETS}

    for left, right in CONFLICTS:
        model.add(selected[left] + selected[right] <= 1)

    for target in TARGETS:
        covering = [selected[product["id"]] for product in PRODUCTS if target in product["covers"]]
        if covering:
            model.add(covered[target] <= sum(covering))
            for variable in covering:
                model.add(covered[target] >= variable)
        else:
            model.add(covered[target] == 0)

    covered_count = sum(covered.values())
    quality = sum(int(product["quality"]) * selected[product["id"]] for product in PRODUCTS)
    model.maximize(1000 * covered_count + quality)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
    status = solver.solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": solver.status_name(status), "selected": []}

    chosen = [product["id"] for product in PRODUCTS if solver.value(selected[product["id"]])]
    result = {
        "status": solver.status_name(status),
        "selected": chosen,
        "coverage": sum(int(solver.value(covered[target])) for target in TARGETS),
        "quality": sum(int(product["quality"]) for product in PRODUCTS if product["id"] in chosen),
        "objective": int(solver.objective_value),
        "bound": int(solver.best_objective_bound),
    }
    assert result["status"] == "OPTIMAL"
    assert result["selected"] == ["p_a", "p_d", "p_e"]
    assert result["coverage"] == 4
    assert result["quality"] == 78
    return result


if __name__ == "__main__":
    print(json.dumps(solve(), sort_keys=True))
