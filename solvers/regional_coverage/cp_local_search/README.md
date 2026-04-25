# Regional Coverage CP-Local-Search Solver

Phase 1 scaffold for the Antuori, Wojtowicz, and Hebrard CP/local-search adaptation.

This solver currently parses public `regional_coverage` case files, builds deterministic fixed-start strip candidates, maps approximate solver-local coverage over `coverage_grid.json`, exposes roll-transition helpers, and creates satellite-local sequences. It intentionally emits an empty `solution.json` until later phases add greedy insertion, local search, CP-assisted repair, and solver-local resource repair.

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

Solver code is standalone and does not import benchmark, experiment, runtime, or other solver internals.
