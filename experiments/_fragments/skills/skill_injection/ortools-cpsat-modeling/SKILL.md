---
name: ortools-cpsat-modeling
description: Use when building small-to-medium OR-Tools CP-SAT models in Python for binary selection, conflict constraints, coverage linkage, lexicographic objectives, solver limits, status handling, incumbent extraction, and fallback decisions; keep it generic to CP-SAT and do not use for stereo-imaging-specific formulas or first-party solver reproduction.
---

# OR-Tools CP-SAT Modeling

Use this skill when candidate or product data is already clean and you want an exact or bounded CP-SAT selection model. CP-SAT is a modeling layer, not a data-cleaning substitute: build candidates, product ids, conflict edges, and objective terms first.

For validated API notes and runnable examples, see `references/README.md`, `examples/binary_coverage_cp_sat.py`, and `examples/sequential_lexicographic_solve.py`.

## Minimal Pattern

```python
from ortools.sat.python import cp_model

model = cp_model.CpModel()
x = model.new_bool_var("select_x")
model.add(x <= 1)
model.maximize(x)

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 10.0
status = solver.solve(model)

if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    selected = solver.value(x)
```

Use the lowercase Python API (`new_bool_var`, `add`, `maximize`, `solve`, `value`) unless the installed package shows otherwise. Check `solver.status_name(status)` when logging.

## Binary Selection

- Create one Boolean variable per selectable candidate, product, task, or assignment.
- Keep an immutable id list beside the variables: `x[item_id] = model.new_bool_var(f"select_{item_id}")`.
- Scale non-integer objective terms to integers before modeling. CP-SAT is integer-based.
- Avoid creating variables for impossible items; reject them before building the model.

## Conflict Constraints

For pairwise conflicts:

```python
for left, right in conflict_edges:
    model.add(x[left] + x[right] <= 1)
```

Use this for mutual exclusion, capacity-one overlaps, incompatible assignments, or any precomputed "cannot both be selected" relation. If conflict construction is huge, profile it separately; model construction can dominate runtime.

## Coverage Linkage

Create one coverage Boolean per covered entity and link it to the selected products that cover it:

```python
cover = model.new_bool_var("cover_target_a")
covering = [x[p] for p in products_covering_target_a]
model.add(cover <= sum(covering))
for var in covering:
    model.add(cover >= var)
```

If no product covers an entity, fix its coverage variable to zero. This pattern makes `cover == 1` exactly when at least one covering product is selected.

## Objectives

- For a single priority, use `model.maximize(sum(weight[i] * x[i] for i in ids))`.
- For lexicographic priorities, prefer sequential solves when weights become awkward:
  1. maximize primary objective
  2. add `primary_expr == best_primary`
  3. maximize secondary objective
- Weighted objectives are fine when the scale is obvious, for example `1000 * covered_count + quality_score`, but document why the primary weight dominates all secondary variation.

## Solver Limits And Status

- Set `solver.parameters.max_time_in_seconds` for bounded runs.
- Treat `cp_model.OPTIMAL` and `cp_model.FEASIBLE` as solution-bearing statuses.
- Treat `cp_model.INFEASIBLE`, `cp_model.MODEL_INVALID`, and `cp_model.UNKNOWN` as no-incumbent unless your own callback or wrapper has saved one.
- Log `solver.objective_value`, `solver.best_objective_bound`, `solver.wall_time`, and `solver.status_name(status)` when a solution exists.

## Incumbents And Fallback

- Always emit the best feasible solution when status is `FEASIBLE`.
- If CP-SAT returns no solution-bearing status under the time limit, fall back to a deterministic greedy seed or previously checkpointed feasible solution rather than emitting nothing.
- Do not silently switch from exact CP-SAT to greedy; record the backend/status in a sidecar.

## When Not To Use CP-SAT Yet

- Candidate/product generation is still wrong or unstable.
- Conflict edges are not trusted.
- Most runtime is spent before model construction finishes.
- The instance is tiny and greedy already reaches the known target.
- You need continuous nonlinear geometry rather than an integer selection model.

## Boundaries

- Keep this generic to OR-Tools CP-SAT.
- Do not include benchmark-specific product formulas, hidden case details, repository solver code, or commands that ask a solver to solve the task for the space agent.
- Do not install packages system-wide. Use an isolated environment when validating OR-Tools examples.
