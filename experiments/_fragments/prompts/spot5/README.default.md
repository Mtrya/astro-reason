# Satellite Photography Selection Problem

This workspace contains one satellite photography selection problem with logical conflict constraints.

You are given one instance file in `case/` with extension `.spot`. It defines:

- candidate photographs
- profit values
- allowed camera-assignment domains
- binary and ternary forbidden combinations
- optional memory usage data for larger instances

Your job is to produce `solution.json`, choosing which photographs to keep and which camera assignment to use for each selected photograph while respecting all conflict and capacity constraints.

This problem is modeled as a constrained assignment-and-selection problem rather than as orbital propagation. Each candidate photograph has a profit and an allowed assignment domain. Setting an assignment to `0` means rejecting that photograph; setting it to `1`, `2`, `3`, or sometimes `13` means selecting it with a specific camera mode. Validity comes from the logical conflict tuples and, for the larger multi-orbit cases, a normalized memory-capacity limit.

## What Good Solutions Do

A strong solution should:

- satisfy all hard validity rules
- maximize total profit
- respect the memory limit on multi-orbit instances

In practical terms, this is a constrained assignment-and-selection problem. A photograph that is not selected should receive assignment `0`.

## Files In This Workspace

- `case/*.spot`: the problem instance
- `{example_solution_name}`: example output shape when present
- `{verifier_location}`: local validation helper when present

## Expected Output

Write one JSON object named `solution.json` at the workspace root.

The expected fields are:

- `claimed_profit`
- `claimed_weight`
- `n_candidates`
- `n_selected`
- `assignments`

`assignments` should contain one value per candidate photograph.

Allowed assignment values are:

- `0` for not selected
- `1`, `2`, or `3` for one camera choice
- `13` for the special two-camera choice when allowed by the instance

Header mismatches in `claimed_profit` or `claimed_weight` may produce warnings rather than immediate invalidity, but the assignment vector itself must still satisfy all domain, conflict, and capacity rules.

## Modeling Contract

This is an assignment-and-selection problem over the variables in the `.spot` file. The first non-empty line is `n_variables`. The next `n_variables` lines define candidate photographs in file order, and `assignments[i]` is the assignment for the `i`th variable. Your `assignments` array must contain exactly `n_variables` integers.

Assignment `0` rejects the photograph. A nonzero assignment selects it and must be in that variable's domain. Values `1`, `2`, and `3` are mono-camera choices. Value `13` is the dual-camera choice and is legal only when the variable's domain explicitly contains `13`.

Each variable line is interpreted as:

```text
var_id profit domain_size value_1 consumption_1 ... value_domain_size consumption_domain_size [ignored extra fields...]
```

Only the first `domain_size` value/consumption pairs define the allowed domain and per-value recorder consumption. Later fields on the line are ignored. Profit is counted once for every selected variable, regardless of which allowed nonzero value is chosen:

```text
computed_profit = sum(profit_i for i where assignments[i] != 0)
```

After the variable block, the file gives `n_constraints`, followed by binary or ternary forbidden-tuple constraints:

```text
arity var_id_1 ... var_id_arity forbidden_tuple_values...
```

For `arity = 2`, forbidden values are read as pairs; for `arity = 3`, they are read as triples. Constraint `var_id` values index the assignment vector. A forbidden tuple applies only when every involved assignment is nonzero and the tuple exactly matches the involved assignment values in the listed order. If any involved assignment is `0`, that constraint is satisfied.

Single-orbit cases have no active recorder-capacity limit and their computed weight is `0`. Multi-orbit cases are exactly `1021`, `1401`, `1403`, `1405`, `1502`, `1504`, and `1506`. For those cases, the capacity line in the `.spot` file is ignored and the hard capacity is fixed at `200`.

For a selected variable in a multi-orbit case, use the recorder consumption attached to the chosen assignment value:

```text
normalized_weight_i = round(recorder_consumption_i_value / 451)
computed_weight = sum(normalized_weight_i for selected variables)
computed_weight <= 200
```

Different values for the same variable may have different consumption. Hard invalidity comes from assignment-count mismatch, assignment outside a variable domain, any violated forbidden tuple, or multi-orbit `computed_weight > 200`.

`claimed_profit`, `claimed_weight`, `n_candidates`, and `n_selected` are bookkeeping fields. The result recomputes profit, weight, and selected count from `assignments`. Mismatched `claimed_profit`, `claimed_weight`, `n_candidates`, or `n_selected` produce warnings, not invalidity, as long as the assignment vector itself is valid. Residual ambiguity is minimal; the only non-obvious behavior is that normalized weights are rounded to the nearest integer with ties to even, so confirm close capacity cases with the local helper.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
