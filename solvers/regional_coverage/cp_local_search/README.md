# Regional Coverage CP-Local-Search Solver

Phase 3 scaffold for the Antuori, Wojtowicz, and Hebrard CP/local-search adaptation.

This solver currently parses public `regional_coverage` case files, builds deterministic fixed-start strip candidates, maps approximate solver-local coverage over `coverage_grid.json`, exposes roll-transition helpers, creates satellite-local sequences, runs a deterministic greedy insertion baseline scored by marginal unique coverage, and applies bounded deterministic local-search neighborhoods with greedy rebuild.

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

Solver code is standalone and does not import benchmark, experiment, runtime, or other solver internals.

Greedy and local-search debug artifacts are written under `debug/greedy_summary.json`, `debug/local_search_summary.json`, and `debug/selected_candidates.json`. Optional JSONL logs can be enabled with `write_insertion_attempts: true` or `write_local_search_moves: true` in the solver config.
