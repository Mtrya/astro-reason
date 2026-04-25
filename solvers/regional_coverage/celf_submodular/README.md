# Regional Coverage CELF Submodular Solver

This solver is a runnable reproduced solver for `regional_coverage`.

It follows the CELF and CEF method family described by Leskovec, Krause,
Guestrin, Faloutsos, VanBriesen, and Glance in "Cost-effective Outbreak
Detection in Networks", adapted to the benchmark's public strip-observation
case and solution contract.

## Citation

```bibtex
@inproceedings{leskovec2007cost,
  title={Cost-effective outbreak detection in networks},
  author={Leskovec, Jure and Krause, Andreas and Guestrin, Carlos and Faloutsos, Christos and VanBriesen, Jeanne and Glance, Natalie},
  booktitle={Proceedings of the 13th ACM SIGKDD International Conference on Knowledge Discovery and Data Mining},
  pages={420--429},
  year={2007},
  doi={10.1145/1281192.1281239}
}

@article{nemhauser1978analysis,
  title={An analysis of approximations for maximizing submodular set functions---I},
  author={Nemhauser, George L. and Wolsey, Laurence A. and Fisher, Marshall L.},
  journal={Mathematical Programming},
  volume={14},
  number={1},
  pages={265--294},
  year={1978},
  doi={10.1007/BF01588971}
}

@article{khuller1999budgeted,
  title={The budgeted maximum coverage problem},
  author={Khuller, Samir and Moss, Anna and Naor, Joseph},
  journal={Information Processing Letters},
  volume={70},
  number={1},
  pages={39--45},
  year={1999},
  doi={10.1016/S0020-0190(99)00031-9}
}
```

The solver is standalone. It reads benchmark case files and writes a benchmark
solution JSON, but it does not import or execute benchmark, experiment, runtime,
or other solver internals.

## Method Summary

The paper models outbreak detection as monotone submodular reward maximization
over selected sensors or information sources:

- each element is a candidate node to select
- each scenario receives reward once it is detected by at least one selected
  element
- greedy selection adds the element with highest marginal reward
- CELF avoids most naive greedy recomputations by lazily refreshing stale
  marginal gains only when an element reaches the priority-queue head
- CEF handles nonuniform costs by running both unit-cost greedy and
  benefit-per-cost greedy, then returning the higher-reward solution

This reproduction keeps that shape and adapts it to `regional_coverage`:

- element: one fixed timed `strip_observation` candidate
- scenario/item: one public coverage-grid sample index
- reward: unique weighted sample coverage over fixed candidate sample sets
- unit-cost policy: marginal weighted coverage
- cost-benefit policy: marginal weighted coverage divided by configured cost
- final CEF policy: higher objective value among unit-cost and cost-benefit
  lazy greedy outputs

## Benchmark Adaptation

The benchmark differs from the paper in several important ways:

- The paper selects abstract sensors on a graph; the benchmark requires timed
  satellite actions with roll, duration, slew, power, duty, and horizon rules.
- The paper's reward can model detection likelihood, detection time, or
  population affected; this solver uses the benchmark-facing unique weighted
  coverage of public grid samples.
- The paper's budget is an abstract selection budget; this solver maps it to
  `max_actions_total` unless an explicit solver selection budget is configured.
- Nonuniform cost is optional. Supported cost modes are action count, imaging
  time, estimated imaging energy, and a simple roll transition burden.
- Candidate geometry is solver-local and approximate. It uses public TLEs,
  Brahe SGP4 propagation, roll-only WGS84 ray hits, and coverage-grid samples.
  Official region geometry, validity, and scoring remain benchmark-owned.
- Schedule feasibility is not part of the paper's pure set-selection model, so
  this solver reports CELF selection and deterministic post-selection repair
  separately.

The repair stage checks action caps, public strip shape rules, same-satellite
half-open interval overlap, benchmark-style bang-coast-bang slew plus settling,
and conservative battery/duty risk. It removes conflicting candidates
deterministically by lowest estimated unique coverage loss, then higher energy
burden, duration, start offset, and candidate id.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` verifies that the project environment can import `yaml`.

`solve.sh` writes:

- `solution.json`: primary benchmark solution, with a top-level `actions` array
  of `strip_observation` actions
- `status.json`: case parsing, candidate generation, coverage mapping, CELF,
  repair, reproduction, output policy, and timing summaries
- `candidate_debug.json`: root-level sample of generated candidates and their
  mapped sample coverage
- `debug/*`: detailed debug artifacts described below

## Configuration

The solver reads optional configuration from `<config_dir>/config.yaml`.

See [config.example.yaml](./config.example.yaml) for a commented example.

Candidate-generation knobs:

- `time_stride_s`: start-time stride over the public action grid
- `roll_step_deg`: default symmetric roll-grid spacing
- `max_candidates_total`: deterministic candidate cap; `null` disables it
- `cap_strategy`: `balanced_stride` evenly samples the stable full candidate
  grid, while `first_n` keeps the legacy prefix behavior for debugging
- `duration_values_s`: optional explicit strip durations
- `roll_values_deg`: optional explicit roll values
- `debug_candidate_limit`: number of candidates copied to `candidate_debug.json`

Selection knobs:

- `run_unit_cost`: run the CELF unit-cost greedy variant
- `run_cost_benefit`: run the CELF benefit-per-cost greedy variant
- `cost_mode`: `action_count`, `imaging_time`, `estimated_energy`, or
  `transition_burden`
- `budget`: optional explicit selection budget; `null` uses benchmark
  `max_actions_total`
- `min_marginal_gain`: stop threshold for accepting candidates
- `write_iteration_trace`: write `debug/celf_iterations.jsonl`
- `max_iteration_debug`: maximum recompute/accept/reject rows to keep per
  CELF variant

The default candidate cap is reported in `status.json`. It keeps smoke runs
fast on the current 72-hour public cases, but it is a tuning knob rather than a
paper requirement.

## Debug Artifacts

The solver writes:

- `debug/candidate_summary.json`: candidate counts, active caps, per-satellite,
  per-roll, and per-duration histograms
- `debug/celf_summary.json`: algorithm metadata, selected ids, objective value,
  covered sample count, true marginal recomputations, estimated naive
  recomputation bound, lazy savings, stale pops, and CEF comparison result
- `debug/celf_iterations.jsonl`: bounded trace of recompute, accept, and
  nonpositive-reject events when enabled
- `debug/selected_candidates.json`: candidates selected before schedule repair
- `debug/feasibility_summary.json`: before/after validity flags and issue
  counts for solver-local schedule checks
- `debug/repair_log.json`: deterministic removal reasons and estimated unique
  coverage loss
- `debug/repaired_candidates.json`: candidates remaining after repair
- `debug/reproduction_summary.json`: paper-faithful elements,
  paper-to-benchmark adaptations, known fidelity limits, and selection audit

Useful checks:

- If `estimated_lazy_recomputations_saved` is zero on a tiny unit test, the
  lazy queue is not demonstrating CELF behavior.
- If `zero_coverage_count` equals `candidate_count`, inspect solver-local
  candidate geometry, roll values, candidate cap balance, and coverage-grid
  placement.
- If repair removes many actions, inspect `repair_log.json` before tuning CELF
  selection; the bottleneck is likely sequence feasibility or power risk.

## Running It

Direct setup:

```bash
./solvers/regional_coverage/celf_submodular/setup.sh
```

Direct solve on a public smoke case:

```bash
./solvers/regional_coverage/celf_submodular/solve.sh \
  benchmarks/regional_coverage/dataset/cases/test/case_0001
```

Direct solve with a config directory:

```bash
./solvers/regional_coverage/celf_submodular/solve.sh \
  benchmarks/regional_coverage/dataset/cases/test/case_0001 \
  /path/to/config_dir \
  /tmp/regional_coverage_celf_solution
```

Official smoke verification through `main_solver`:

```bash
uv run python experiments/main_solver/run.py \
  --benchmark regional_coverage \
  --solver regional_coverage_celf_submodular \
  --case test/case_0001
```

Aggregate experiment results:

```bash
uv run python experiments/main_solver/aggregate.py
```

## Sanity Baseline

The paper's theoretical baselines apply to fixed monotone submodular selection,
not directly to verifier-scored satellite schedules. Treat them as algorithmic
sanity checks:

- unit-cost greedy should match naive greedy on small fixed-candidate tests
- CELF should use no more marginal recomputations than naive greedy, and should
  save recomputations on cases with stale-but-still-dominant queue heads
- cost-benefit greedy can differ from unit-cost greedy when configured costs
  differ
- the final CEF result should be the higher-reward solution among the enabled
  unit-cost and cost-benefit variants

For benchmark smoke, official verification is the validity gate. The current
smoke case is valid with no verifier violations, but it is not evidence of
coverage quality tuning; coverage remains sensitive to the solver-local strip
geometry and candidate cap.

## Known Limitations

- This is a reproduction of the CELF/CEF method family, not a reproduction of
  every experiment table or online-bound calculation from the paper.
- The online optimality bound from Leskovec et al. Section 3.2 is not
  implemented.
- Candidate coverage uses deterministic solver-local Brahe SGP4 propagation and
  WGS84 ray intersections from public TLE fields, not benchmark verifier
  internals.
- Post-selection repair can remove CELF-selected candidates, so repaired output
  may have lower reward than the pure fixed-set selection result.
- Battery and duty checks are conservative solver-local approximations; the
  official verifier remains the source of truth.
- The default `max_candidates_total` is intentionally small for smoke speed and
  should be tuned before quality comparisons.

## Evidence Type

Official `main_solver` smoke verification passes on `test/case_0001` with
`status: verified`, `valid: true`, and no verifier violations. This solver is
therefore registered in `experiments/main_solver` with
`evidence_type: reproduced_solver`.
