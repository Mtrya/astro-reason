# Phase 3: Time-Window Cluster Pruning

## Goal

Implement Kim-style time-window pruning so larger candidate sets remain tractable while preserving the benchmark's coverage-first objective.

## Inputs To Read

- `solvers/stereo_imaging/roadmap/time_window_pruned_stereo_milp/ROADMAP.md`
- Phase 2 implementation
- Issue #89
- `solvers/stereo_imaging/literature/kim-2020-stereo-milp.md`
- `solvers/stereo_imaging/literature/table.md`

## In Scope

- Cluster dense candidate time windows per satellite using a max-slew-time-inspired temporal gap.
- Compute opportunity count per target and product scarcity per access interval.
- Retain candidates by:
  - coverage scarcity
  - product feasibility count
  - product quality potential
  - lower opportunity count
  - steering similarity within a cluster
  - deterministic time tie-breakers
- Add config knobs for lambda-style cluster capacity, lower-bound auto sizing, and max products per target/access interval.
- Write `debug/pruning_summary.json`.

## Out Of Scope

- Solver backend model.
- Re-tuning product scoring weights.
- Deleting all products for a target unless unavoidable.

## Implementation Notes

- Kim's pruning sorted by priority and lowest observation opportunity; the benchmark has no target priority, so use uncovered-target scarcity and product potential as the faithful adaptation.
- Steering similarity should reduce transition burden but must not eliminate the only near-nadir anchor for a tri-stereo candidate.
- Preserve at least one feasible pair candidate per target when one exists, unless global candidate caps make that impossible and the debug summary says so.

## Validation

- Test pruning on synthetic clustered windows to prove it keeps scarce/high-quality opportunities.
- Run direct smoke on public cases with pruning disabled and enabled.
- Confirm candidate and product counts drop while at least some feasible products remain on cases that had products before pruning.

## Exit Criteria

- Pruning is configurable, deterministic, and explainable.
- Debug output reports pre/post candidate and product counts by target and cluster.
- The implementation can run with pruning disabled for audit comparisons in Phase 6.
- No target silently loses all product opportunities without a recorded reason.

## Suggested Prompt

Read the stereo MILP roadmap, Kim pruning section, Phase 2 code, and this phase doc. Implement deterministic time-window cluster pruning adapted to coverage scarcity and product quality. Add debug summaries and tests that show pruning reduces model size while retaining representative product opportunities.
