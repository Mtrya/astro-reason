# CP/Local-Search Stereo Insertion Solver

This solver is a runnable reproduced solver for `stereo_imaging`.

It draws on the method family described by Lemaître et al. in "Selecting and Scheduling Observations of Agile Satellites", adapted to the benchmark's public case and solution contract.

**Important:** this solver is currently a deterministic greedy baseline with constraint-propagated sequences and a weak local-search veneer. It is not yet a faithful reproduction of Lemaître's stochastic local-search method. See [SOLVER_AUDIT.md](./SOLVER_AUDIT.md) for details.

## Citation

```bibtex
@article{lemaitre2002selecting,
  title={Selecting and Scheduling Observations of Agile Satellites},
  author={Lema{\^i}tre, Michel and Verfaillie, G{\'e}rard and Jouhaud, Frank and Lachiver, Jean-Michel and Bataille, Nicolas},
  journal={Aerospace Science and Technology},
  volume={6},
  number={5},
  pages={367--381},
  year={2002},
  doi={10.1016/S1270-9638(02)01173-2}
}
```

Related reference for binary/ternary repair ideas:

```bibtex
@article{vasquez2001logic,
  title={A Logic-Constrained Knapsack Formulation and a Tabu Algorithm for the Daily Photograph Scheduling of an Earth Observation Satellite},
  author={Vasquez, Michel and Hao, Jin-Kao},
  journal={Computational Optimization and Applications},
  volume={20},
  number={2},
  pages={137--157},
  year={2001},
  doi={10.1023/A:1012300271919}
}
```

The solver is standalone. It reads benchmark case files and writes a benchmark solution JSON, but it does not import or execute benchmark, experiment, runtime, or other solver internals.

## Method Summary

Lemaître et al. maintain feasible per-satellite image sequences, propagate earliest/latest feasible positions, and perform insertion/removal moves that handle stereoscopic observations as coupled products.

This reproduction keeps that structure and adapts it to `stereo_imaging`:

- **Phase 1** — scaffold, public YAML parsing, candidate observation enumeration, and pair/tri-stereo product library.
- **Phase 2** — per-satellite sequence feasibility with earliest/latest propagation.
- **Phase 3** — deterministic greedy seed construction with coverage-first dynamic ranking.
- **Phase 4** — local-search product insertion/removal/replacement moves.
- **Phase 5** — conservative repair pass and main-solver experiment wiring.
- **Phase 6** — performance tuning (satellite-state cache), validation matrix, and solver audit.
- **Phase 7a** — tri-stereo seed architecture: weighted lexicographic ranking plus tri-stereo upgrade pass.
- **Phase 7b** — multi-run harness with deterministic perturbation; parallel candidate generation across satellites.

## Validation

All 5 public cases pass the benchmark verifier. Runtimes are on a warm-cache single-threaded Python run.

| Case | Candidates | Seed accepted | Tri accepted | Coverage | Norm. quality | Runtime |
|---|---|---|---|---|---|---|
| test/case_0001 | 556 | 30 | 13 | 30 / 47 (0.638) | 0.636 | 12.4 s |
| test/case_0002 | 235 | 11 | 6 | 11 / 36 (0.306) | 0.305 | 5.2 s |
| test/case_0003 | 289 | 22 | 6 | 22 / 36 (0.611) | 0.604 | 7.8 s |
| test/case_0004 | 666 | 31 | 10 | 31 / 39 (0.795) | 0.793 | 13.1 s |
| test/case_0005 | 236 | 0 | 0 | 0 / 19 (0.000) | 0.000 | 4.1 s |

**Seed-only vs local search:** on all public cases, the greedy seed is already at a local optimum for the current move neighborhood; local search accepts 0 improving moves on all 5 cases. Dedicated `remove` moves were added in Phase 7b but the seed remains locally optimal. The multi-run harness (with RNG perturbation) is the primary mechanism for exploring alternative solutions.

**Determinism:** two consecutive runs on the same case produce byte-identical `solution.json`.

**Repair:** the conservative repair pass removes 0 products on all public cases, confirming that solver-local propagation matches verifier geometry.

**Tri-stereo:** Phase 7a added weighted lexicographic ranking and a tri-stereo upgrade pass. Tri-stereo products are now scheduled on 4 of 5 public cases (13 on case_0001, 6 on case_0002, 6 on case_0003, 10 on case_0004). Coverage does not regress on any case.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` is effectively a no-op when using the project environment.

`solve.sh` writes:

- `solution.json`: primary benchmark solution with an `actions` array of `observation` actions
- `status.json`: solver summary, timings, and candidate/product library details
- `debug/*`: optional debug artifacts when `debug: true`

The primary solution artifact is one JSON object with a top-level `actions` array of `observation` actions.

## Configuration

The solver reads optional config from either:

- `<config_dir>/config.yaml`
- `<config_dir>/config.yml`
- `<config_dir>/config.json`
- `<config_dir>/cp_local_search_stereo_insertion.yaml`
- `<config_dir>/cp_local_search_stereo_insertion.yml`
- `<config_dir>/cp_local_search_stereo_insertion.json`

See [config.example.yaml](./config.example.yaml) for a commented example.

### Default knobs

```yaml
seed_only: false
tri_stereo_seed_phase: true
max_seed_products: null
pair_weight: 1.0
tri_weight: 1.5
max_passes: 10
max_moves_per_pass: 500
max_time_seconds: 120.0
enable_repair: true
repair_candidates_limit: 20
remove_move_enabled: true
remove_candidates_limit: 50
num_runs: 1
random_seed: 42
parallel_workers: null   # null = auto (CPU count), 0 = disable
debug: false
```

### Seed ranking

The greedy seed uses a lexicographic sort key (higher is better):

1. `coverage_value` — `1.0` if target is uncovered, `0.0` otherwise
2. `scarcity + weighted_quality` — combined scarcity and quality score
3. `scarcity` — `1.0 / remaining_count` for this target
4. `weighted_quality` — `quality * tri_weight` for tri-stereo, `quality * pair_weight` for pairs
5. `product_id` — deterministic tie-break

The upgrade pass then tries to replace pair-covered targets with tri-stereo products when the tri product offers strictly better weighted quality and fits in the freed sequence capacity.

## Running It

Direct setup:

```bash
./solvers/stereo_imaging/cp_local_search_stereo_insertion/setup.sh
```

Direct solve on a public smoke case:

```bash
./solvers/stereo_imaging/cp_local_search_stereo_insertion/solve.sh \
  benchmarks/stereo_imaging/dataset/cases/test/case_0001
```

Direct solve with a config directory:

```bash
./solvers/stereo_imaging/cp_local_search_stereo_insertion/solve.sh \
  benchmarks/stereo_imaging/dataset/cases/test/case_0001 \
  /path/to/config_dir \
  /tmp/stereo_cp_solution
```

Official main-solver run:

```bash
uv run python experiments/main_solver/run.py \
  --benchmark stereo_imaging \
  --solver stereo_imaging_cp_local_search_stereo_insertion \
  --case test/case_0001
```

## Known Limitations

- The solver is a deterministic greedy baseline with multi-run evaluation, not yet a faithful reproduction of Lemaître's stochastic local-search method. The audit flags a weak move neighborhood and the fact that the greedy seed is not the paper's GA.
- Candidate generation can be parallelized across satellites via `parallel_workers`. The seed and local search remain single-threaded.
- Solver-local product predicates are designed to match the verifier geometry, but minor drift is possible due to floating-point ordering.
- The greedy seed dominates runtime (~50–60 % of total time on large cases). The seed algorithm is an implementation invention (pool-based coverage-first greedy), not the sequential track-builder described in the paper.

## Audit

See [SOLVER_AUDIT.md](./SOLVER_AUDIT.md) for the full solver-audit report covering compute realism, reproduction gaps, and recommended run policy.
