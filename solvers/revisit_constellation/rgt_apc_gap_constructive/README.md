# RGT/APC Gap-Constructive Solver Scaffold

Phase 1 scaffold for `revisit_constellation`.

The solver currently parses public `assets.json` and `mission.json` files, builds a deterministic RGT/APC-style candidate satellite library, samples target visibility opportunities, writes debug artifacts, and intentionally emits an empty benchmark solution:

```bash
./solvers/revisit_constellation/rgt_apc_gap_constructive/setup.sh
./solvers/revisit_constellation/rgt_apc_gap_constructive/solve.sh \
  benchmarks/revisit_constellation/dataset/cases/test/case_0001 \
  /tmp/empty_config \
  /tmp/revisit_rgt_phase1
```

Outputs:

- `solution.json`: empty `satellites` and `actions` arrays
- `status.json`: case metadata, candidate counts, visibility-window counts, caps, and timings
- `debug/orbit_candidates.json`: generated candidate states at mission start
- `debug/visibility_windows.json`: sampled candidate-target visibility opportunities

Later phases add gap-aware constellation selection, constructive observation scheduling, and solver-local repair.

