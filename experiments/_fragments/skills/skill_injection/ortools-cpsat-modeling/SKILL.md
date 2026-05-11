---
name: ortools-cpsat-modeling
description: Use when building small-to-medium OR-Tools CP-SAT models in Python for binary selection, conflict constraints, coverage linkage, lexicographic objectives, solver limits, status handling, incumbent extraction, and fallback decisions.
---

# OR-Tools CP-SAT Modeling

When candidate or product data is already clean, small enough, and an exact or bounded CP-SAT selection model is useful, treat CP-SAT as a modeling layer, not a data-cleaning substitute: build candidates, product ids, conflict edges, and objective terms first.

CP-SAT does not rescue an oversized or noisy candidate library. If candidate generation is still exploding, prune and validate the library before modeling. A small trusted model that finishes and leaves a feasible incumbent is better than a giant exact model that never reaches a useful submission.

Use `examples/binary_coverage_cp_sat.py` or `examples/sequential_lexicographic_solve.py` only when you need a runnable synthetic pattern. Use `references/README.md` only for API-name or status-code lookup.

## Modeling Recipe

1. Build a small trusted product library, action ids, conflict edges, and objective terms outside CP-SAT.
2. Put hard caps on candidate counts before creating variables. Keep only the best few compatible alternatives per job, target, resource, or time bucket.
3. Run a greedy or insertion baseline first and save it as a fallback incumbent.
4. Create one Boolean `x[product_id]` per selectable product after pruning.
5. Add conflict constraints such as `x[a] + x[b] <= 1`.
6. Link target/job coverage or best-score variables to selected products.
7. Maximize the task's actual priority order, using sequential solves when weights are awkward.
8. Set a time limit and treat only `OPTIMAL` or `FEASIBLE` as solution-bearing statuses.
9. Convert selected products back into the required raw output actions; keep scratch solver logs out of the final submission unless requested.

## Candidate Budget Before CP-SAT

Before building the model, print or inspect these counts:

- raw actions or observations generated
- actions remaining after local feasibility filters
- products/jobs remaining after compatibility filters
- conflict edges
- products per target/job/request
- worst resource timeline density

If these counts are unexpectedly large, stop and prune before creating variables. Practical pruning patterns:

- Keep at most `k` product alternatives per target/job/request for the first model, then enlarge only after a valid incumbent exists.
- Keep candidates near the center of feasible windows before trying edge cases.
- Remove dominated products that cover the same entity with worse quality, tighter margins, and no conflict advantage.
- Bucket time and keep representative alternatives per resource/time bucket rather than every second or every tiny offset.
- Use product-level variables, not raw-action variables, when the score is earned by completed products.
- Reject candidates near known hard thresholds until the baseline is valid; add threshold-hugging upgrades later.

Do not build all pairwise products just because CP-SAT can express the selection. Pairwise product generation can be the real bottleneck.

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
- Avoid creating variables for every raw time sample or every pairwise combination. Model pruned products whenever possible.

## Conflict Constraints

For pairwise conflicts:

```python
for left, right in conflict_edges:
    model.add(x[left] + x[right] <= 1)
```

Use this for mutual exclusion, capacity-one overlaps, incompatible assignments, or any precomputed "cannot both be selected" relation. If conflict construction is huge, the candidate library is probably still too large or insufficiently indexed; profile and prune it separately because model construction can dominate runtime.

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
- The product library is thousands of weak near-duplicates and no greedy valid incumbent exists.
- The instance is tiny and greedy already reaches the known target.
- You need continuous nonlinear geometry rather than an integer selection model.

## Keep It Safe

- Model only candidates and conflicts you already trust.
- Keep domain-specific feasibility checks outside the CP-SAT model unless they are already converted to integer variables and constraints.
- Preserve a deterministic fallback solution when a time-limited solve returns no feasible status.
