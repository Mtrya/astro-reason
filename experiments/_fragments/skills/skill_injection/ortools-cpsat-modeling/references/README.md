# OR-Tools CP-SAT Modeling References

Use this file as an agent-facing API reminder. The runnable examples are in this skill directory under `examples/`.

## Official API Links

- CP-SAT guide: https://developers.google.com/optimization/cp/cp_solver
- Solver limits guide: https://developers.google.com/optimization/cp/cp_tasks
- Python install overview: https://developers.google.com/optimization/install/python
- Python API reference: https://or-tools.github.io/docs/pdoc/ortools/sat/python/cp_model.html

## Python API Names

Modern OR-Tools Python examples use:

- `from ortools.sat.python import cp_model`
- `model = cp_model.CpModel()`
- `model.new_bool_var(name)`
- `model.new_int_var(lb, ub, name)`
- `model.add(expr)`
- `model.maximize(expr)` or `model.minimize(expr)`
- `solver = cp_model.CpSolver()`
- `solver.parameters.max_time_in_seconds = seconds`
- `status = solver.solve(model)`
- `solver.value(var)`
- `solver.status_name(status)`
- `solver.objective_value`
- `solver.best_objective_bound`
- `solver.wall_time`

If your installed package exposes only camel-case aliases, adapt locally, but keep the model logic unchanged.

## Status Handling

Solution-bearing statuses:

- `cp_model.OPTIMAL`
- `cp_model.FEASIBLE`

Non-solution statuses unless you saved an incumbent yourself:

- `cp_model.INFEASIBLE`
- `cp_model.MODEL_INVALID`
- `cp_model.UNKNOWN`

Always branch on status before reading variable values.

## Modeling Reminders

- CP-SAT is integer-based. Scale decimal scores before putting them in an objective.
- Build variables only for candidates that are already locally feasible.
- Put conflict logic in explicit constraints such as `x[a] + x[b] <= 1`.
- Link coverage variables to selected products with both upper and lower implications.
- Use sequential solves for lexicographic objectives when weighted sums are fragile.
- Log the solver status, objective value, best bound, and wall time when available.
