# Satellite Photography Selection Run Notes

## Case 54.spot Results
- Valid: True
- Profit: 70
- Weight: 0 (single-orbit case)
- Selected: 45 / 67
- 20 / 35 {13}-vars selected, all profit-2 non-{13} vars selected, 19/26 profit-1 {1,2,3} selected

### Structure
- 67 vars, 204 constraints, 12 connected components
- Profit tiers: 40 vars with profit=2 (35 {13}, 3 {1,2,3}, 2 {2}), 27 vars profit=1
- MIS of {13}-{13} binary conflict graph: 22 vars (profit 44). Max independent set exact via BnB.
- Component decomposition: C0 (31 vars, profit 43), C1 (20 vars, profit 35), C2 (5 vars, profit 10), C3 (3 vars, profit 4), 7 singleton {13} vars
- C1 exhaustive search: 18 is optimal (270K evaluations over all {13}-subsets × {1,2,3}-value combos)
- All singletons, C2, C3 are at max; only C0 has room for improvement

### Solver
- Greedy + perturb-and-rebuild + local swap improvement (same approach as case 507)
- Exhaustive search on C1 confirmed 18 optimal
- BnB on {13}-vars with greedy {123} assignment for C0 gave 23 (same as current)

### Failed Approaches
- BnB on full {1,2,3} vars within C0: too slow (19 vars, 3 colors each + 0)
- Simulated annealing: profit tracking bugs made it unreliable
- MIS-based initialization: 22 {13}-vars force too many {1,2,3} out, net worse than 70

### Key Bug Pattern
- `try_assign(var, val, assignments)` MUST temporarily SET `assignments[var]=val` before checking constraints. Checking without setting means the constraint can never be fully matched (var still at 0).
- Profit tracking in swap-based local search is error-prone; always recompute from assignments.

## Case 507.spot Results (prior run)
- Valid: True, Profit: 15132, Weight: 0, Selected: 93/311
- 15/42 high-profit (1000) vars selected

## Output Schema
```json
{
  "claimed_profit": 70,
  "claimed_weight": 0,
  "n_candidates": 67,
  "n_selected": 45,
  "assignments": [0, 0, 0, ...]
}
```
- Assignment values: 0 (unselected), 1/2/3 (camera modes), 13 (dual-camera)
- `assignments[i]` corresponds to the i-th candidate variable in file order

## Key Command Patterns
- Verifier: `./verifier case/ solution.json`
- Parse: first line = n_vars, next n_vars lines = variable definitions, then n_constraints, then constraint lines
- Single-orbit cases have `computed_weight = 0` (no capacity limit)
- Multi-orbit cases: instances 1021, 1401, 1403, 1405, 1502, 1504, 1506; capacity = 200; weight = round(consumption/451)
