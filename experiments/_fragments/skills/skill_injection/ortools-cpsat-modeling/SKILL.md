---
name: ortools-cpsat-modeling
description: Use when building small-to-medium OR-Tools CP-SAT models in Python for binary selection, conflict constraints, coverage linkage, lexicographic objectives, solver limits, status handling, incumbent extraction, and fallback decisions.
---

# OR-Tools CP-SAT Modeling

When candidate or product data is already clean and an exact or bounded CP-SAT selection model is useful, treat CP-SAT as a modeling layer, not a data-cleaning substitute: build candidates, product ids, conflict edges, and objective terms first.

Use `examples/binary_coverage_cp_sat.py` or `examples/sequential_lexicographic_solve.py` only when you need a runnable synthetic pattern. Use `references/README.md` only for API-name or status-code lookup.

## Modeling Recipe

1. Build trusted products, action ids, conflict edges, and objective terms outside CP-SAT.
2. Create one Boolean `x[product_id]` per selectable product.
3. Add conflict constraints such as `x[a] + x[b] <= 1`.
4. Link target/job coverage or best-score variables to selected products.
5. Maximize the task's actual priority order, using sequential solves when weights are awkward.
6. Set a time limit and treat only `OPTIMAL` or `FEASIBLE` as solution-bearing statuses.
7. Convert selected products back into the required raw output actions; keep scratch solver logs out of the final submission unless requested.

## Minimal Pattern

```python
from ortools.sat.python import cp_model

model = cp_model.CpModel()
x = {pid: model.new_bool_var(f"select_{pid}") for pid in product_ids}
for left, right in conflict_edges:
    model.add(x[left] + x[right] <= 1)
model.maximize(sum(weight[pid] * x[pid] for pid in product_ids))

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 10.0
status = solver.solve(model)

if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    selected = [pid for pid in product_ids if solver.value(x[pid])]
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
- Do not silently switch from exact CP-SAT to greedy; record the backend/status in a local scratch sidecar, not as part of the final task submission unless explicitly requested.

## When Not To Use CP-SAT Yet

- Candidate/product generation is still wrong or unstable.
- Conflict edges are not trusted.
- Most runtime is spent before model construction finishes.
- The instance is tiny and greedy already reaches the known target.
- You need continuous nonlinear geometry rather than an integer selection model.

## Keep It Safe

- Model only candidates and conflicts you already trust.
- Keep domain-specific feasibility checks outside the CP-SAT model unless they are already converted to integer variables and constraints.
- Preserve a deterministic fallback solution when a time-limited solve returns no feasible status.
