# Regional Coverage CP-Assisted Local-Search Solver

This solver is a runnable reproduced solver for `regional_coverage`.

It follows the acquisition-planning method described by Valentin Antuori, Damien T. Wojtowicz, and Emmanuel Hebrard in "Solving the Agile Earth Observation Satellite Scheduling Problem with CP and Local Search", adapted to the benchmark's public strip-coverage contract.

## Citation

```bibtex
@inproceedings{antuori2025solving,
  title={Solving the Agile Earth Observation Satellite Scheduling Problem with {CP} and Local Search},
  author={Antuori, Valentin and Wojtowicz, Damien T. and Hebrard, Emmanuel},
  booktitle={31st International Conference on Principles and Practice of Constraint Programming (CP 2025)},
  series={Leibniz International Proceedings in Informatics (LIPIcs)},
  volume={340},
  pages={3:1--3:22},
  year={2025},
  publisher={Schloss Dagstuhl -- Leibniz-Zentrum fuer Informatik},
  doi={10.4230/LIPIcs.CP.2025.3}
}
```

The solver is standalone. It reads public benchmark case files and writes a benchmark solution JSON, but it does not import or execute benchmark, experiment, runtime, or other solver internals.

## Method Summary

Antuori et al. decompose AEOS scheduling into acquisition planning and download planning. The acquisition planner maintains satellite-local acquisition sequences, builds an initial solution with greedy insertion, and improves selected sequence neighborhoods with local search. When greedy insertion cannot place an acquisition, the paper calls Tempo on a bounded TSPTW-style subproblem.

This reproduction keeps the acquisition-planning structure:

- acquisition: one fixed-start `strip_observation` candidate
- satellite sequence: one ordered list of strip candidates per satellite
- transition time: roll-delta bang-coast-bang slew plus settling time
- greedy insertion: choose the feasible candidate/position with best marginal unique coverage, with deterministic tie breaks
- neighborhood move: remove selected satellite-local candidates, then rebuild the neighborhood greedily
- CP assistance: run a bounded exact TSPTW-style sequence repair inside local neighborhoods

The solver's objective is benchmark-facing rather than paper-native: it maximizes unique weighted coverage over `coverage_grid.json` samples while preserving valid public actions.

## Benchmark Adaptation

The benchmark differs from the paper in several important ways:

- The paper uses fixed additive acquisition profits; the benchmark scores unique regional coverage, so candidate value is recomputed as marginal uncovered sample weight.
- The paper has precomputed acquisition opportunities; the benchmark exposes no access windows, so this solver generates deterministic fixed-start, roll-grid strip candidates from public case files.
- The paper includes downloads and onboard memory planning; the benchmark solution contract has no download or memory actions.
- The benchmark has hard battery and imaging-duty constraints. This solver avoids known sequence conflicts and reports solver-local validation, while official validity remains owned by `experiments/main_solver` plus the benchmark verifier.
- The paper uses Tempo for CP-SAT TSPTW insertion; this repository currently has no public CP backend configured, so the solver uses a clearly labeled bounded exact fallback.

That means this solver is a faithful adaptation of the paper's acquisition-planning control flow, not a reproduction of every industrial subsystem or every result table.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` is a no-op under the project environment.

`solve.sh` writes:

- `solution.json`: primary benchmark solution with `strip_observation` actions
- `status.json`: solver summary, timings, reproduction notes, local validation, and CP metrics
- `debug/candidate_summary.json`
- `debug/candidates.json`
- `debug/greedy_summary.json`
- `debug/local_search_summary.json`
- `debug/selected_candidates.json`
- optional `debug/insertion_attempts.jsonl`
- optional `debug/moves.jsonl`

The primary solution artifact is a JSON object with a top-level `actions` array. Each action has:

- `type: strip_observation`
- `satellite_id`
- `start_time`
- `duration_s`
- `roll_deg`

## Search Pipeline

The solver pipeline is:

1. Load `manifest.json`, `satellites.yaml`, `regions.geojson`, and `coverage_grid.json`.
2. Generate grid-aligned strip candidates using the public action grid, valid roll bands, and fixed deterministic roll samples.
3. Score candidate coverage with solver-local strip segment geometry shaped to match the public verifier's roll-only WGS84 strip model.
4. Build an empty satellite-local sequence state.
5. Run deterministic greedy insertion with marginal unique coverage scoring.
6. Build bounded satellite-time and sample-competition neighborhoods.
7. Rebuild each neighborhood with greedy insertion against the current covered-sample set.
8. If CP is enabled, call the bounded exact fallback on non-improving local neighborhoods.
9. Emit the selected candidate sequence as `strip_observation` actions.
10. Write debug summaries and status metadata for reproduction auditing.

The defaults are deterministic and bounded. There is no hidden random restart path.

## CP Backend

`cp_backend: tiny_exact_fallback` is the only supported backend today.

It is a solver-local exact subset search over a small fixed-start TSPTW-style neighborhood:

- input: kept incumbent candidates plus one bounded neighborhood candidate pool
- feasibility: satellite-local sequence insertion and transition checks
- objective key: valid first, coverage weight, lower energy estimate, lower slew burden, fewer actions
- limits: `cp_max_calls`, `cp_max_candidates`, `cp_max_subsets`, and `cp_time_limit_s`

This fallback is not Tempo and does not claim Tempo performance. It is a public-backend substitution point that preserves the paper's control flow: try greedy sequence repair first, then call a bounded exact repair when the neighborhood warrants it.

CP metrics are recorded in `status.json` and `debug/local_search_summary.json`:

- `calls`
- `successful_calls`
- `call_success_rate`
- `improving_solutions`
- `improving_success_rate`
- skipped-call counters
- model-build and solve times
- timeout and subset-limit stops

## Configuration

The solver reads optional config from:

- `<config_dir>/config.yaml`
- `<config_dir>/config.yml`
- `<config_dir>/config.json`

See [config.example.yaml](./config.example.yaml) for a commented example.

Key knobs:

- `candidate_stride_s`
- `roll_samples_per_side`
- `max_candidates_per_satellite`
- `include_zero_coverage_candidates`
- `max_zero_coverage_candidates_per_satellite`
- `greedy_policy`
- `greedy_max_iterations`
- `greedy_wall_time_limit_s`
- `local_search_enabled`
- `local_search_max_iterations`
- `local_search_component_gap_s`
- `local_search_time_padding_s`
- `local_search_max_neighborhoods_per_iteration`
- `local_search_max_neighborhood_candidates`
- `cp_enabled`
- `cp_backend`
- `cp_max_calls`
- `cp_max_candidates`
- `cp_max_subsets`
- `cp_time_limit_s`
- `cp_min_improvement_weight_m2`
- `write_insertion_attempts`
- `write_local_search_moves`

`greedy_wall_time_limit_s` bounds greedy insertion only. `cp_time_limit_s` bounds each CP fallback call only. Candidate generation, solution writing, and local validation still run before the solver exits.

## Debug Artifacts

Debug summaries are intended to explain fidelity and score drift:

- `candidate_summary.json`: candidate counts, positive-coverage counts, zero-coverage counts, per-satellite counts, and max candidate weight
- `candidates.json`: first `candidate_debug_limit` candidate records
- `greedy_summary.json`: accepted candidate IDs, marginal coverage totals, insertion attempts, feasibility rejects, and deterministic tie-break order
- `local_search_summary.json`: generated neighborhoods, accepted moves, objective deltas, incumbent progression, and CP metrics
- `selected_candidates.json`: final selected candidate records in solution order
- `insertion_attempts.jsonl`: optional greedy insertion-attempt details
- `moves.jsonl`: optional local-search move details, including CP repair records
- `status.json`: combined run summary, execution mode, configs, sequence model, validation summary, and reproduction notes

Useful first checks:

- If `positive_coverage_candidate_count` is zero, inspect candidate stride and roll sampling.
- If CP calls are zero, inspect `cp_enabled`, size limits, and neighborhood generation.
- If CP succeeds but does not improve, the greedy sequence is already locally strong for the sampled neighborhood.
- If official coverage is lower than solver-local coverage, inspect strip geometry and candidate conversion.

## Running It

Direct setup:

```bash
./solvers/regional_coverage/cp_local_search/setup.sh
```

Direct solve on the public smoke case:

```bash
./solvers/regional_coverage/cp_local_search/solve.sh \
  benchmarks/regional_coverage/dataset/cases/test/case_0001
```

Direct solve with a config directory:

```bash
./solvers/regional_coverage/cp_local_search/solve.sh \
  benchmarks/regional_coverage/dataset/cases/test/case_0001 \
  /path/to/config_dir \
  /tmp/regional_coverage_cp_local_search_solution
```

Official smoke verification through `main_solver`:

```bash
uv run python experiments/main_solver/run.py \
  --benchmark regional_coverage \
  --solver regional_coverage_cp_local_search \
  --case test/case_0001
```

Aggregate experiment results:

```bash
uv run python experiments/main_solver/aggregate.py
```

## Validation Notes

The official smoke case currently verifies through `experiments/main_solver` with:

- `valid: true`
- `num_actions: 16`
- `coverage_ratio: 0.22613351894435932`
- `weighted_coverage_ratio: 0.22507679044299717`
- `min_battery_wh: 492.8958333333384`
- CP calls: `18`
- CP feasible calls: `18`
- CP improving calls: `0`

Greedy-only, local-search-without-CP, and CP-enabled modes produce the same smoke objective with the current defaults. This is acceptable evidence for the paper-style control flow because CP calls are observable and successful, but the sampled smoke neighborhood does not need CP to improve over greedy insertion.

## Known Limitations

- This solver reproduces the Antuori acquisition-planning method family, not the full integrated acquisition/download/memory planner.
- Tempo is not available as a project dependency; `tiny_exact_fallback` is a bounded exact substitute for tiny fixed-start neighborhoods.
- Candidate generation uses deterministic time and roll grids, so finer opportunities between grid points are intentionally missed.
- The CP fallback searches fixed-start candidate subsets; it does not continuously reschedule action start times.
- Battery and duty constraints are not globally optimized inside the search objective. Official validity is still checked by the benchmark verifier through experiments.
- Local search is intentionally bounded and deterministic. It is not an ALNS or broad metaheuristic sweep.
- Full multi-case tuning may need broader candidate budgets than are comfortable for quick development-laptop smoke runs.

## Evidence Type

This solver is registered in `experiments/main_solver` and `solvers/finished_solvers.json` with `evidence_type: reproduced_solver`.
