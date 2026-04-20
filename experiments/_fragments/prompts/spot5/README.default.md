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

## Important Task Semantics

- If a photograph is not selected, assign `0`.
- For selected photographs, the chosen value must belong to that variable’s allowed domain.
- Values `1`, `2`, and `3` represent mono-camera choices, while `13` is the special dual-camera choice used only when that variable's domain allows it.
- Binary and ternary forbidden tuples must not be activated.
- A binary or ternary forbidden tuple matters only when all participating photographs are selected with exactly that value combination.
- Some larger instances also enforce a memory-capacity limit of `200` after normalization from the per-value recorder-consumption numbers in the instance.
- Single-orbit instances effectively have zero memory usage, but the logical conflict constraints still matter.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
