# Regional Coverage CELF Submodular Solver

Phase 1 scaffold for issue #82.

This solver reads only public `regional_coverage` case files, enumerates
deterministic strip candidates on the public action grid, maps those candidates
to coverage-grid sample indices using solver-local approximate geometry, and
writes an empty benchmark-shaped `solution.json`.

CELF selection, same-satellite sequence repair, battery/duty repair, experiment
registration, and verifier-guided validation are intentionally deferred to later
roadmap phases.

## Entrypoints

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

Optional `config.yaml`:

```yaml
candidate_generation:
  time_stride_s: 600
  roll_step_deg: 4.0
  max_candidates_total: 512
  duration_values_s: [20, 60, 120]
  roll_values_deg: [-31.0, -27.0, 27.0, 31.0]
  debug_candidate_limit: 50
```

The default cap is reported in `status.json` so this scaffold stays fast on the
current 72-hour public cases.
