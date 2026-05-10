---
name: classical-or-scheduling-methods
description: Use for combinatorial scheduling and selection problems where a solver must build candidates, reason about conflicts, seed a feasible schedule, improve it with insertion/removal/local-search moves, repair violations, and preserve deterministic tie-breaking under coverage-first or lexicographic objectives.
---

# Classical OR Scheduling Methods

Use these patterns when solving a scheduling or selection task with many feasible actions, resource conflicts, and a scoring objective that rewards coverage or profit. Build the schedule from candidates and products you can inspect.

For method reminders, read `references/README.md`. For a compact worked example using neutral jobs/resources/products, read `examples/conflict_graph_and_insertion.md`.

## Core Model

Separate the search into two layers:

- **Action layer:** concrete schedulable units with a resource, start/end time, value, and any local feasibility checks already passed.
- **Product layer:** logical jobs, requests, bundles, or completed services that may require one or more actions. Score products at this layer so duplicate actions do not inflate value.

Keep every accepted product atomic. If a product needs multiple actions, either insert all constituent actions and update indexes together, or roll the whole move back.

## Build The Candidate Space

1. Generate feasible actions first, using cheap filters before expensive checks.
2. Build products or jobs only from compatible actions.
3. Record why candidates or products were rejected.
4. Prune cautiously: cap dominated or low-priority candidates when needed, but keep enough alternatives per job to survive conflicts and repair.

A good candidate library is easier to improve than a clever search over weak candidates.

## Conflict Graph

Represent hard incompatibilities explicitly:

- Add an edge between two actions that cannot share the same resource timeline.
- Add an edge between products if any required actions conflict, or if the problem allows only one product per customer/job.
- Keep conflict checks symmetric and deterministic.

Use the graph both for construction and repair. When a proposed insertion conflicts with the current solution, compute the removable conflicting set before mutating the schedule.

## Greedy Seed

Build a first feasible schedule with stable ordering:

1. Rank uncovered products by objective contribution, feasibility margin, and deterministic IDs.
2. Try the best product for each uncovered job before adding duplicate value to an already-covered job.
3. Insert only if the full product is feasible.
4. After one pass, try upgrade moves that replace a covered job's product with a higher-quality product.

For coverage-first objectives, seed coverage before polishing quality. This prevents high-quality duplicates from blocking many easy wins.

## Insertion And Rollback

Use product-atomic insertion:

1. Snapshot the affected resource timelines and covered-product indexes.
2. Place the product's actions into sorted resource timelines.
3. Check local predecessor/successor gaps and graph conflicts.
4. If any check fails, restore the snapshot.
5. If it succeeds, update product coverage and score indexes.

Most bugs in schedule search come from half-applied moves. Make rollback boring and total.

## Local Search Moves

Prefer a small set of inspectable neighborhoods:

- **Insert:** add an uncovered product that fits.
- **Replace:** swap one selected product for a better product covering the same job.
- **Remove-then-insert:** remove one low-value product, then try to add one or more better products.
- **Swap:** exchange a conflicting selected product for a candidate with better objective contribution.
- **Repair move:** add a product and remove only the selected products needed to restore hard constraints.

Evaluate moves lexicographically when the benchmark does: validity first, then coverage/profit, then quality or secondary value, then fewer redundant actions, then deterministic IDs.

## Conservative Repair

After construction and search, run a repair pass over actual selected actions:

1. Detect every hard conflict in the realized schedule.
2. For each conflict set, remove the selected product with the smallest lexicographic loss.
3. Recompute coverage and score from scratch after repair.
4. Stop when no conflict remains or when a full pass makes no change.

Repair is a guardrail, not a search substitute. If repair removes many products, inspect candidate generation or the conflict model before tuning heuristics.

## Determinism

Make ties explicit:

- Sort candidates, products, resources, and jobs by stable IDs after score fields.
- Use a fixed seed for randomized perturbations.
- Keep construction logs or counters that explain accepted, rejected, removed, and repaired products.
- Report whether time limits stopped search and return the best complete incumbent, not a partially mutated schedule.

Deterministic behavior makes weak improvements easier to trust and regressions much easier to diagnose.
