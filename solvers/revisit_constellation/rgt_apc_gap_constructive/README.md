# RGT/APC Gap-Constructive Solver

Phase 2 solver scaffold for `revisit_constellation`.

The solver currently parses public `assets.json` and `mission.json` files, builds a deterministic RGT/APC-style candidate satellite library, samples target visibility opportunities, scores those opportunities with benchmark-style midpoint revisit gaps, greedily selects satellites by marginal gap improvement, and writes debug artifacts:

```bash
./solvers/revisit_constellation/rgt_apc_gap_constructive/setup.sh
./solvers/revisit_constellation/rgt_apc_gap_constructive/solve.sh \
  benchmarks/revisit_constellation/dataset/cases/test/case_0001 \
  /tmp/empty_config \
  /tmp/revisit_rgt_phase1
```

Outputs:

- `solution.json`: selected `satellites` and an empty `actions` array
- `status.json`: case metadata, candidate counts, visibility-window counts, selection scores, caps, and timings
- `debug/orbit_candidates.json`: generated candidate states at mission start
- `debug/visibility_windows.json`: sampled candidate-target visibility opportunities
- `debug/selection_rounds.json`: greedy satellite-selection marginal improvements

Later phases add constructive observation scheduling and solver-local slew/battery repair.
