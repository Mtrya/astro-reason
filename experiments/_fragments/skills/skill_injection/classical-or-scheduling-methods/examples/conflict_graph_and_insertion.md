# Conflict Graph And Insertion Example

This is a neutral scheduling sketch. It uses jobs, products, actions, and resources so the pattern can transfer to many benchmark tasks.

## Toy Data

Products:

| product | job | value | required actions |
|---|---|---:|---|
| `p1` | `j1` | 90 | `a1`, `a2` |
| `p2` | `j1` | 84 | `a3` |
| `p3` | `j2` | 70 | `a4` |
| `p4` | `j3` | 65 | `a5` |
| `p5` | `j4` | 50 | `a6` |

Actions:

| action | resource | start | end |
|---|---|---:|---:|
| `a1` | `r1` | 10 | 20 |
| `a2` | `r2` | 14 | 24 |
| `a3` | `r1` | 30 | 38 |
| `a4` | `r1` | 18 | 28 |
| `a5` | `r2` | 25 | 32 |
| `a6` | `r1` | 40 | 46 |

Hard conflicts:

- `a1` conflicts with `a4` because they overlap on `r1`.
- `a2` conflicts with `a5` if the resource requires a minimum gap after `a2`.
- Products for the same job conflict with each other: `p1` conflicts with `p2`.

## Greedy Seed

Rank products by:

1. uncovered job first,
2. higher value,
3. fewer conflicts,
4. stable product ID.

Walk the ranked list:

1. Try `p1`: insert both `a1` and `a2`; accept because no current actions conflict.
2. Try `p2`: reject because `j1` is already covered by `p1`.
3. Try `p3`: reject because `a4` conflicts with selected `a1`.
4. Try `p4`: reject if `a5` violates the gap after selected `a2`.
5. Try `p5`: accept `a6`.

The seed covers `j1` and `j4`.

## Product-Atomic Insertion

When testing `p3` after the seed:

```text
snapshot = selected products {p1, p5}
conflicts = selected products that share conflicting actions with p3
conflicts = {p1}

candidate score if replacing p1 with p3:
  coverage change: -0 because j1 would be lost and j2 gained
  value change: -20

decision: reject the repair insertion
restore snapshot exactly
```

When testing a new product `p6` for `j2` with one action on `r2` at `[33, 39]`, the insertion may be accepted because it does not conflict with `p1` or `p5`.

## Local Search Pass

Use bounded, deterministic passes:

1. Insert any uncovered product that fits without removals.
2. For each covered job, try replacing its selected product with a higher-value product for the same job.
3. Try remove-then-insert: temporarily remove the lowest-value selected product, then greedily refill uncovered jobs.
4. Keep a move only if it improves the task's true lexicographic score.

Recompute the score from selected products after every accepted move. Avoid accumulating score deltas across many moves unless you also have a full recomputation check.

## Repair Pass

If the final selected action list contains a conflict:

1. Identify the selected products involved in the conflict.
2. Remove the product with the smallest lexicographic loss: fewer unique jobs lost, lower value lost, and stable product ID.
3. Recompute timelines and repeat.

This repair rule is conservative. It should prevent invalid output, but if it removes many products, the conflict model or candidate generator probably needs attention.
