# Regional Coverage CP-Assisted Local-Search Solver

This solver is a runnable benchmark-adapted reproduction of the acquisition-planning control flow for `regional_coverage`.

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

- acquisition: fixed-start `strip_observation` candidates, with optional conservative opportunity grouping for interval repair
- satellite sequence: one ordered list of strip candidates per satellite
- transition time: roll-delta bang-coast-bang slew plus settling time
- greedy insertion: choose the feasible candidate and position with best marginal unique coverage, using deterministic tie breaks
- neighborhood move: remove selected satellite-local candidates from bounded time windows or deterministic conflict components, then rebuild the neighborhood greedily
- CP assistance: run bounded OR-Tools CP-SAT repair inside local neighborhoods, either as fixed-start subset repair or interval/TSPTW-style repair snapped back to public candidates

The solver's objective is benchmark-facing rather than paper-native: it maximizes unique weighted coverage over `coverage_grid.json` samples while preserving valid public actions.

## Benchmark Adaptation

The benchmark differs from the paper in several important ways:

- The paper uses fixed additive acquisition profits; the benchmark scores unique regional coverage, so candidate value is recomputed as marginal uncovered sample weight.
- The paper has precomputed acquisition opportunities; the benchmark exposes no access windows, so this solver generates deterministic fixed-start, roll-grid strip candidates from public case files.
- The paper includes downloads and onboard memory planning; the benchmark solution contract has no download or memory actions.
- The benchmark has hard battery and imaging-duty constraints. This solver avoids known sequence conflicts and reports solver-local validation, while official validity remains owned by `experiments/main_solver` plus the benchmark verifier.
- The paper uses Tempo for CP-based TSPTW insertion; this solver uses a solver-local OR-Tools CP-SAT backend prepared by `setup.sh`.

This solver reproduces the paper's acquisition-planning structure under the benchmark contract, not every industrial subsystem or every result table. The selected configuration uses a dense benchmark-adapted optimization envelope, while the interval/opportunity configuration is kept as a comparison path for interval-style modeling.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` creates a solver-local `.venv/`, installs the pinned dependencies from `requirements.txt`, and writes `.solver-env` for direct and experiment-owned runs.

`solve.sh` writes:

- `solution.json`: primary benchmark solution with `strip_observation` actions
- `status.json`: solver summary, timings, reproduction notes, local validation, and CP metrics
- `debug/candidate_summary.json`
- `debug/candidates.json`
- `debug/greedy_summary.json`
- `debug/local_search_summary.json`
- `debug/opportunities.json` when opportunity grouping is enabled
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
6. Build bounded satellite-time neighborhoods or same-satellite conflict-component neighborhoods.
7. Rebuild each neighborhood with greedy insertion against the current covered-sample set.
8. If CP is enabled, call bounded OR-Tools CP-SAT repair on non-improving local neighborhoods.
9. Emit the selected candidate sequence as `strip_observation` actions.
10. Write debug summaries and status metadata.

The defaults are deterministic and bounded. Restart and randomized-neighborhood behavior is explicit in config and recorded in `status.json`.

## CP Backend

`cp_backend: ortools_cp_sat` is the supported backend.

It is a solver-local CP-SAT model over a small TSPTW-style neighborhood. Two repair modes are available:

- `fixed_start_subset`: preserves the original fixed-start repair used by the reproduction comparison profile.
- `interval_tsptw`: gives each selected opportunity a bounded start interval, then snaps the selected member back to a concrete public `strip_observation` candidate before solution emission.

Both modes keep the same public solution contract:

- input: kept incumbent candidates plus one bounded neighborhood candidate pool
- feasibility: satellite-local transition conflict constraints against selected candidates and outside-neighborhood anchors
- objective: maximize marginal unique coverage over samples not already covered by kept candidates
- objective key: valid first, coverage weight, lower energy estimate, lower slew burden, fewer actions
- limits: `cp_max_calls`, `cp_max_candidates`, `cp_max_conflicts`, and `cp_time_limit_s`

This backend is not Tempo and does not claim Tempo performance. It preserves the paper's control flow: try greedy sequence repair first, then call bounded CP repair when the neighborhood warrants it. OR-Tools is installed only into the solver-local `.venv/` created by `setup.sh`; no system-wide dependency is required.

CP metrics are recorded in `status.json` and `debug/local_search_summary.json`:

- `calls`
- `successful_calls`
- `call_success_rate`
- `improving_solutions`
- `improving_success_rate`
- skipped-call counters
- model-build and solve times
- solver status counts, branches, conflicts, model sizes, timeout stops, and conflict-limit stops

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
- `candidate_workers`
- `include_zero_coverage_candidates`
- `max_zero_coverage_candidates_per_satellite`
- `greedy_policy`
- `greedy_max_iterations`
- `greedy_wall_time_limit_s`
- `local_search_enabled`
- `local_search_neighborhood_mode`
- `local_search_max_iterations`
- `local_search_component_gap_s`
- `local_search_time_padding_s`
- `local_search_max_component_size`
- `local_search_component_subwindow_s`
- `local_search_include_sample_competition`
- `local_search_max_neighborhoods_per_iteration`
- `local_search_max_neighborhood_candidates`
- `opportunity_grouping_enabled`
- `opportunity_max_time_gap_s`
- `opportunity_min_coverage_jaccard`
- `cp_enabled`
- `cp_backend`
- `cp_repair_mode`
- `cp_interval_start_window_s`
- `cp_max_calls`
- `cp_max_candidates`
- `cp_max_conflicts`
- `cp_time_limit_s`
- `cp_min_improvement_weight_m2`
- `write_insertion_attempts`
- `write_local_search_moves`
- `search_restart_count`
- `search_run_seeds`
- `greedy_random_choice_probability`
- `local_search_randomize_neighborhood_order`

`greedy_wall_time_limit_s` bounds greedy insertion only. `cp_time_limit_s` bounds each CP-SAT repair call only. Candidate generation, solution writing, and local validation still run before the solver exits.

## Debug Artifacts

Debug summaries are intended to explain solver behavior and score differences:

- `candidate_summary.json`: candidate counts, positive-coverage counts, zero-coverage counts, per-satellite counts, and max candidate weight
- `candidates.json`: first `candidate_debug_limit` candidate records
- `opportunities.json`: opportunity groups, member counts, public candidate mappings, and omitted-group counts when `opportunity_grouping_enabled` is true
- `greedy_summary.json`: accepted candidate IDs, marginal coverage totals, insertion attempts, feasibility rejects, and deterministic tie-break order
- `local_search_summary.json`: generated neighborhoods, accepted moves, objective deltas, incumbent progression, and CP metrics
- `selected_candidates.json`: final selected candidate records in solution order, including source opportunity IDs when opportunity grouping is enabled
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

Run the all-case reproduction comparison:

```bash
uv run python experiments/main_solver/run.py \
  --config experiments/main_solver/config_regional_coverage_cp_local_search_reproduction.yaml
uv run python experiments/main_solver/aggregate.py
```

Run the interval/opportunity comparison profile:

```bash
uv run python experiments/main_solver/run.py \
  --config experiments/main_solver/config_regional_coverage_cp_local_search_faithful.yaml
uv run python experiments/main_solver/aggregate.py
```

Aggregate experiment results:

```bash
uv run python experiments/main_solver/aggregate.py
```

## Experiment Profiles

The CI smoke profile remains light and unchanged. It is intended for quick contract checks, not full reproduction evidence.

The selected reproduction profile uses the benchmark configuration chosen for current all-case reporting: 60-second candidate stride, nine roll magnitudes per side, positive-coverage candidates only, thirty search seeds, bounded local-search neighborhoods, fixed-start OR-Tools CP-SAT repair, and eight candidate workers.

The interval/opportunity comparison profile uses five search seeds, deterministic same-satellite conflict-component neighborhoods, conservative opportunity grouping, and `interval_tsptw` OR-Tools repair. Emitted actions remain public `strip_observation` actions.

Use `experiments/main_solver/aggregate.py` and `results/main_solver/summary.csv` for current metrics. The README intentionally avoids a fixed metrics snapshot so the documentation does not drift when experiments are rerun.

## Scope

Implemented and adapted pieces include standalone case parsing, deterministic candidate generation, verifier-shaped unique-coverage scoring, satellite-local sequences, greedy insertion, bounded local-search neighborhoods, conflict-component neighborhoods, conservative opportunity grouping, restart/multi-start plumbing, selectable OR-Tools CP-SAT neighborhood repair, structured timings, and official main-solver validation.

The benchmark adaptation is explicit: this is not Tempo itself and it does not reproduce download or memory planning. Within the public regional-coverage contract, the selected method provides a dense candidate envelope, process-parallel candidate generation, verified all-case experiment outputs, and observable local-search/CP improvements over greedy.

## Known Limitations

- This solver reproduces the Antuori acquisition-planning method family, not the full integrated acquisition/download/memory planner.
- Tempo is not available as a project dependency; OR-Tools CP-SAT is used as the public backend for bounded fixed-start or interval/TSPTW-style neighborhoods.
- Candidate generation uses deterministic time and roll grids, so finer opportunities between grid points are intentionally missed.
- Opportunity grouping is conservative and snaps back to public fixed candidates; it is mainly useful for comparing interval-style modeling against fixed-start repair.
- The interval repair mode permits bounded start flexibility inside the model but still emits concrete public actions, not continuous industrial access-window schedules.
- Battery and duty constraints are not globally optimized inside the search objective. Official validity is still checked by the benchmark verifier through experiments.
- Local search is intentionally bounded and deterministic. It is not an ALNS or broad metaheuristic sweep.
- Server-side reproduction can raise `candidate_workers` to `16`; the public profile uses `8` workers as a fair laptop-safe default.

## Evidence Type

The `experiments/main_solver` profile carries `evidence_type: reproduced_solver`, meaning the experiment can run the solver and verify benchmark-shaped outputs through the public verifier. `solvers/finished_solvers.json` is only the hardened solver-contract registry; it carries `repro_ci` metadata and case paths, not experiment evidence metadata.
