# Regional Coverage CELF Submodular Solver

Phase 5 reproduction-fidelity scaffold for issue #82.

This solver reads only public `regional_coverage` case files, enumerates
deterministic strip candidates on the public action grid, maps those candidates
to coverage-grid sample indices using solver-local approximate geometry, and
selects candidates with unit-cost and cost-benefit CELF lazy forward selection,
keeps the higher-reward CEF variant, then applies deterministic solver-local
schedule repair.

The solver is wired into `experiments/main_solver` through CLI/file contracts.
The repaired `solution.json` includes only public `strip_observation` action
fields.

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
selection:
  run_unit_cost: true
  run_cost_benefit: true
  cost_mode: action_count
  budget: null
  min_marginal_gain: 0.0
  write_iteration_trace: true
  max_iteration_debug: 2000
```

The default cap is reported in `status.json` so this scaffold stays fast on the
current 72-hour public cases.

## Debug Artifacts

The solver writes:

- `status.json` with candidate, coverage, and CELF summaries
- `solution.json` with the selected candidate actions
- `candidate_debug.json` with a small root-level candidate sample
- `debug/candidate_summary.json`
- `debug/celf_summary.json`
- `debug/celf_iterations.jsonl`
- `debug/selected_candidates.json`
- `debug/feasibility_summary.json`
- `debug/repair_log.json`
- `debug/repaired_candidates.json`
- `debug/reproduction_summary.json`

CELF uses fixed candidate coverage sets and the unique weighted sample objective.
The debug summary records true marginal recomputations, an estimated naive
recomputation bound, lazy recomputation savings, and the unit-cost versus
cost-benefit CEF comparison outcome.

The repair pass locally checks action caps, public candidate shape rules,
same-satellite half-open interval overlap, the benchmark bang-coast-bang slew
formula plus settling, and approximate battery/duty risk. It removes conflicting
candidates deterministically by lowest estimated unique coverage loss, then
higher energy burden, duration, start offset, and candidate id.

## Paper-To-Benchmark Adaptation

The paper's sensor-node ground set is adapted to fixed timed strip-observation
candidates. Scenario/item coverage is adapted to public coverage-grid sample
indices with weighted unique coverage. The paper budget is adapted to the
benchmark action cap or explicit solver selection budget. Both unit-cost
greedy and cost-benefit greedy are run when configured, matching the CEF
comparison pattern, and the higher-reward result is reported.

The main benchmark-specific adaptation is that schedule feasibility is not part
of the paper's pure set selection model. This solver reports CELF selection and
post-selection repair separately: repair can remove same-satellite overlaps,
slew-infeasible actions, action-cap excess, and conservative battery/duty risks.
Coverage geometry also remains solver-local and approximate; official validity
comes from `experiments/main_solver` invoking the benchmark verifier.

## Main Solver Smoke

Official smoke verification through `main_solver`:

```bash
uv run python experiments/main_solver/run.py \
  --benchmark regional_coverage \
  --solver regional_coverage_celf_submodular \
  --case test/case_0001
```

This solver is registered in `experiments/main_solver` with
`evidence_type: reproduced_solver`. Current Phase 5 smoke verification passes on
`test/case_0001`; broader non-smoke tuning remains future work.
