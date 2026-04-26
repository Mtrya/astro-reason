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

- acquisition: one fixed-start `strip_observation` candidate
- satellite sequence: one ordered list of strip candidates per satellite
- transition time: roll-delta bang-coast-bang slew plus settling time
- greedy insertion: choose the feasible candidate/position with best marginal unique coverage, with deterministic tie breaks
- neighborhood move: remove selected satellite-local candidates, then rebuild the neighborhood greedily
- CP assistance: run bounded OR-Tools CP-SAT TSPTW-style sequence repair inside local neighborhoods

The solver's objective is benchmark-facing rather than paper-native: it maximizes unique weighted coverage over `coverage_grid.json` samples while preserving valid public actions.

## Benchmark Adaptation

The benchmark differs from the paper in several important ways:

- The paper uses fixed additive acquisition profits; the benchmark scores unique regional coverage, so candidate value is recomputed as marginal uncovered sample weight.
- The paper has precomputed acquisition opportunities; the benchmark exposes no access windows, so this solver generates deterministic fixed-start, roll-grid strip candidates from public case files.
- The paper includes downloads and onboard memory planning; the benchmark solution contract has no download or memory actions.
- The benchmark has hard battery and imaging-duty constraints. This solver avoids known sequence conflicts and reports solver-local validation, while official validity remains owned by `experiments/main_solver` plus the benchmark verifier.
- The paper uses Tempo for CP-SAT TSPTW insertion; this solver uses a solver-local OR-Tools CP-SAT backend prepared by `setup.sh`.

That means this solver reproduces the paper's acquisition-planning structure under the benchmark contract, not every industrial subsystem or every result table. Current evidence supports a valid, auditable reproduction scaffold with CP-assisted neighborhood repair; it does not yet support the stronger claim of a faithful reproduction with a fully fair optimization and compute envelope.

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
8. If CP is enabled, call bounded OR-Tools CP-SAT repair on non-improving local neighborhoods.
9. Emit the selected candidate sequence as `strip_observation` actions.
10. Write debug summaries and status metadata for reproduction auditing.

The defaults are deterministic and bounded. Restart and randomized-neighborhood behavior is explicit in config and recorded in `status.json`.

## CP Backend

`cp_backend: ortools_cp_sat` is the supported backend.

It is a solver-local CP-SAT model over a small fixed-start TSPTW-style neighborhood:

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
- `local_search_max_iterations`
- `local_search_component_gap_s`
- `local_search_time_padding_s`
- `local_search_max_neighborhoods_per_iteration`
- `local_search_max_neighborhood_candidates`
- `cp_enabled`
- `cp_backend`
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

The current dense CP-enabled reproduction profile verifies `test/case_0001`
through `experiments/main_solver` with:

- `valid: true`
- `num_actions: 50`
- `coverage_ratio: 0.8983077474393012`
- `weighted_coverage_ratio: 0.90179098116373`
- `min_battery_wh: 492.8958333333384`
- CP calls: `64`
- CP feasible calls: `64`
- CP improving calls: `51`
- candidate generation: process pool with `8` workers

The CI smoke profile remains lighter, but the reproduction profile now uses a
fairer dense candidate envelope: 120-second candidate stride, seven roll
magnitudes per side, positive-coverage candidates only, and eight candidate
workers.

## Public Evidence Snapshot

The public reproduction comparison lives in:

```bash
uv run python experiments/main_solver/run.py \
  --config experiments/main_solver/config_regional_coverage_cp_local_search_reproduction.yaml
uv run python experiments/main_solver/aggregate.py
```

The profile compares greedy-only, local-search-without-CP, and CP-enabled modes over all five public regional-coverage `test` cases. All fifteen jobs verify. The current average official metrics are:

| mode | average coverage ratio | average weighted coverage ratio | average actions | average solve time |
| --- | ---: | ---: | ---: | ---: |
| greedy-only | `0.8964373077399344` | `0.8961799799329526` | `25.4` | `8.365175425197231 s` |
| local-search | `0.8989634205760888` | `0.8983754575177383` | `25.2` | `9.137866019795183 s` |
| CP-enabled | `0.9018473856666462` | `0.9013044997801305` | `25.4` | `13.954553109407424 s` |

The CP-enabled profile made `214` OR-Tools CP-SAT calls across the five cases, all feasible, with `57` improving neighborhood repairs. CP improves the final official score on `test/case_0001` and `test/case_0003`; the other public cases are already saturated or locally strong under greedy/local-search.

Candidate generation uses deterministic process-pool parallelism. With `candidate_workers: 8`, CP-enabled candidate generation averages about `7.768 s` per case and search averages about `5.701 s`.

## Audit Status

The current audit status for the target claim, "faithful reproduction adapted to the benchmark with fair optimization and compute envelope", is `READY`.

Implemented and adapted pieces include standalone case parsing, deterministic candidate generation, verifier-shaped unique-coverage scoring, satellite-local sequences, greedy insertion, bounded local-search neighborhoods, restart/multi-start plumbing, OR-Tools CP-SAT neighborhood repair, structured timings, and official main-solver validation.

The benchmark adaptation is still explicit: this is not Tempo itself and it does not reproduce download or memory planning. Within the public regional-coverage contract, however, the solver now has a fair dense candidate envelope, process-parallel candidate generation, verified all-case results, and observable local-search/CP improvements over greedy.

## Known Limitations

- This solver reproduces the Antuori acquisition-planning method family, not the full integrated acquisition/download/memory planner.
- Tempo is not available as a project dependency; OR-Tools CP-SAT is used as the public backend for tiny fixed-start neighborhoods.
- Candidate generation uses deterministic time and roll grids, so finer opportunities between grid points are intentionally missed.
- The CP backend searches fixed-start candidate subsets; it does not continuously reschedule action start times.
- Battery and duty constraints are not globally optimized inside the search objective. Official validity is still checked by the benchmark verifier through experiments.
- Local search is intentionally bounded and deterministic. It is not an ALNS or broad metaheuristic sweep.
- Server-side reproduction can raise `candidate_workers` to `16`; the public profile uses `8` workers as a fair laptop-safe default.

## Evidence Type

The `experiments/main_solver` profile carries `evidence_type: reproduced_solver`, meaning the experiment can run the solver and verify benchmark-shaped outputs through the public verifier. `solvers/finished_solvers.json` is only the hardened solver-contract registry; it carries `repro_ci` metadata and case paths, not experiment evidence metadata.
