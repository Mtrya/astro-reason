# Phase 4: Local Search Product Moves

## Goal

Implement bounded, reproducible local search that improves the greedy seed through product insertions, removals, and replacements while preserving sequence feasibility.

## Inputs To Read

- `solvers/stereo_imaging/roadmap/cp_local_search_stereo_insertion/ROADMAP.md`
- Phase 3 implementation
- Issue #90
- `solvers/stereo_imaging/literature/lemaitre-2002-cp-local-search.md`
- `solvers/stereo_imaging/literature/vasquez-2001-logic-knapsack-tabu.md`

## In Scope

- Implement local moves over whole products:
  - insert uncovered-target product
  - replace lower-quality product for same target
  - remove blocking product then insert one or more better products
  - optional Vasquez-inspired short tabu on recently removed products
- Maintain deterministic or seeded move ordering.
- Use coverage-first, quality-second acceptance criteria.
- Add configurable time, pass, and move-attempt limits.
- Track incumbent schedule and rollback failed moves.
- Write `debug/local_search_log.json`.

## Out Of Scope

- Exact CP-SAT model for the whole problem.
- Non-reproducible stochastic search.
- Large private sweeps.

## Implementation Notes

- Lemaitre's local search uses insertion/removal moves and attempts the corresponding stereo image, rolling back on failure. Preserve that product-coupled behavior.
- The optional tabu layer should be framed as repair/diversification support from Vasquez and Hao, not as the solver's primary method.
- Acceptance should never reduce coverage for quality unless the move immediately restores coverage in the same transaction.
- Every accepted move should update product-level objective estimates and sequence state together.

## Validation

- Unit-test replacement and rollback behavior.
- Run seed-only and local-search-enabled modes on the same case to compare metrics.
- Run repeatability checks with fixed seed and deterministic mode.
- Verify output manually with benchmark verifier.

## Exit Criteria

- Local search improves or preserves seed objective under the configured acceptance rule.
- Product moves remain atomic.
- Search stops cleanly at pass/time/move limits.
- Debug log explains accepted and rejected moves.

## Suggested Prompt

Read the CP/local-search roadmap, Phase 3 code, Lemaitre local-search pseudocode, Vasquez repair notes, and this phase doc. Implement bounded product-level insertion/removal/replacement local search with deterministic replay, rollback, and debug logs. Validate seed versus improved modes.
