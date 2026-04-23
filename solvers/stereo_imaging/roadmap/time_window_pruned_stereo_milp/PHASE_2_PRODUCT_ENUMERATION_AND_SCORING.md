# Phase 2: Product Enumeration And Scoring

## Goal

Lift candidate observations into benchmark-native stereo pair and tri-stereo product candidates with reproducible scores and explicit links to benchmark validity predicates.

## Inputs To Read

- `solvers/stereo_imaging/roadmap/time_window_pruned_stereo_milp/ROADMAP.md`
- Phase 1 implementation
- `benchmarks/stereo_imaging/README.md`
- `solvers/stereo_imaging/literature/summary.md`
- `tests/benchmarks/test_stereo_imaging_verifier.py`

## In Scope

- Add product models for pairs and tri-stereo sets.
- Group candidates by `(satellite_id, target_id, access_interval_id)`.
- Precompute pair feasibility using:
  - same satellite, target, and access interval
  - convergence angle thresholds
  - AOI overlap fraction threshold
  - pixel-scale ratio threshold
  - action-level feasibility flags
- Precompute tri-stereo feasibility using:
  - same group
  - at least two valid constituent pairs
  - near-nadir anchor threshold
  - common overlap approximation
- Implement benchmark-shaped pair and tri quality scoring.
- Produce debug artifacts such as `debug/product_summary.json`.

## Out Of Scope

- MILP construction.
- Time-window pruning.
- Search or repair over selected products.

## Implementation Notes

- The issue requires product candidates to use convergence angle, AOI overlap, pixel-scale ratio, same-access grouping, and near-nadir-anchor requirements.
- If overlap is approximated, keep the approximation deterministic and configurable, and record calibration fields so Phase 6 can compare against verifier diagnostics.
- Do not give mono observations objective credit except as actions linked to a valid pair/tri product.
- Tie-break products deterministically by coverage contribution, quality, target id, satellite id, access interval, and time tuple.

## Validation

- Unit-test product grouping and threshold logic on synthetic candidate observations.
- Run a smoke solve that writes product debug artifacts even if no products are selected.
- Compare product counts and selected products against verifier `diagnostics.pair_evaluations` for at least one hand-built solution when possible.

## Exit Criteria

- Pair and tri product candidates are reproducible and inspectable.
- Quality computation follows benchmark weights and scene-type preferred convergence bands.
- Debug artifacts distinguish no-access, no-product, and product-filtered cases.
- Known approximation drift is listed for Phase 6 instead of hidden.

## Suggested Prompt

Read the stereo MILP roadmap, Phase 1 code, this phase doc, and the benchmark stereo product definitions. Implement benchmark-native pair and tri-stereo product enumeration and scoring. Add deterministic debug summaries and focused tests for threshold behavior. Do not build the MILP yet.
