# Phase 2: Sequence Propagation And Feasibility

## Goal

Implement per-satellite sequence feasibility checks with Lemaitre-style earliest/latest propagation and benchmark-shaped slew/settle constraints.

## Inputs To Read

- `solvers/stereo_imaging/roadmap/cp_local_search_stereo_insertion/ROADMAP.md`
- Phase 1 implementation
- Issue #90
- `solvers/stereo_imaging/literature/lemaitre-2002-cp-local-search.md`
- `tests/benchmarks/test_stereo_imaging_verifier.py`

## In Scope

- Add sequence data structures per satellite.
- Implement insertion-position enumeration for a candidate observation or product.
- Compute earliest/latest feasible timing intervals around existing sequence neighbors.
- Check:
  - observation duration bounds
  - non-overlap
  - benchmark-style slew-plus-settle gaps
  - access interval containment
  - product partner placement consistency
- Implement atomic transaction/rollback helpers for product insertion and removal.
- Write propagation debug records for rejected insertions.

## Out Of Scope

- Search policy.
- Product quality tuning.
- Official experiment wiring.

## Implementation Notes

- Lemaitre's LSA computes possible positions, inserts an image, then propagates earliest and latest start times through the sequence. Preserve that shape in code.
- For this benchmark, candidates may already have fixed or narrow sampled times; propagation may choose among discrete candidate variants instead of continuously shifting starts.
- Product insertion must fail atomically if any paired observation or tri-stereo anchor cannot be placed.
- Keep deterministic tie-breaking even when many positions are feasible.

## Validation

- Unit-test empty, beginning, middle, and end insertion positions.
- Unit-test rollback after failed partner insertion.
- Use fixture-inspired cases for overlap and slew-too-fast rejection.
- Run direct smoke and inspect propagation debug output.

## Exit Criteria

- Sequence feasibility can accept and reject product insertions deterministically.
- Earliest/latest or equivalent discrete feasibility state is inspectable.
- Failed insertion leaves sequence state unchanged.
- Tests cover overlap, insufficient slew, and partner rollback.

## Suggested Prompt

Read the CP/local-search roadmap, Phase 1 code, Lemaitre insertion/propagation sections, and this phase doc. Implement per-satellite sequence feasibility, possible insertion positions, propagation, and atomic rollback for product insertions. Add focused tests for overlap, slew, and rollback.
