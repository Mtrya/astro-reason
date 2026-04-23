# Phase 3: Deterministic Greedy Seed

## Goal

Build a reproducible initial schedule that maximizes coverage quickly before local search spends effort improving product quality.

## Inputs To Read

- `solvers/stereo_imaging/roadmap/cp_local_search_stereo_insertion/ROADMAP.md`
- Phase 2 implementation
- Issue #90
- `benchmarks/stereo_imaging/README.md`
- `solvers/stereo_imaging/literature/summary.md`

## In Scope

- Rank products by:
  - uncovered target first
  - scarcity of remaining products for the target
  - valid tri-stereo potential
  - estimated quality
  - lower sequence disruption
  - deterministic ids/time tie-breakers
- Insert whole products atomically into per-satellite sequences.
- Preserve same-satellite, same-target, same-access product semantics.
- Emit seed debug artifacts:
  - considered products
  - accepted products
  - rejected products with reason
  - coverage and quality estimates

## Out Of Scope

- Randomized local search.
- Replacement neighborhoods.
- Final docs.

## Implementation Notes

- The benchmark ranks coverage before quality; greedy seed should reflect that directly.
- A product that covers a new target should generally beat a higher-quality product for an already covered target.
- If tri-stereo products block too many pair products, seed should prefer a configurable pair-first or tri-first policy and record the policy.
- Keep the seed deterministic even if a config seed is present; randomization belongs only to a controlled later phase.

## Validation

- Unit-test ranking and deterministic tie-breaking.
- Run seed-only mode twice and compare identical `solution.json` and `status.json`.
- Verify direct output manually with the benchmark verifier.

## Exit Criteria

- Seed-only mode produces a coherent schedule and debug summary.
- Coverage-first ranking is visible in code and docs.
- Repeated runs are byte-stable except for allowed runtime fields.
- Rejected products have actionable reasons.

## Suggested Prompt

Read the CP/local-search roadmap, Phase 2 code, benchmark ranking rules, and this phase doc. Implement deterministic greedy seed construction over whole stereo/tri products with coverage-first ordering, seed-only config, debug summaries, and repeatability checks.
