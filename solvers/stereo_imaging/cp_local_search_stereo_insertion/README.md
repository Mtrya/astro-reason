# CP/Local-Search Stereo Insertion Solver

This solver is a runnable reproduced solver for `stereo_imaging`.

It follows the method family described by Lemaître et al. in "Selecting and Scheduling Observations of Agile Satellites", adapted to the benchmark's public case and solution contract.

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

- **Phase 1** (current): scaffold, public YAML parsing, candidate observation enumeration, and pair/tri-stereo product library.
- **Phase 2**: per-satellite sequence feasibility with earliest/latest propagation.
- **Phase 3**: deterministic greedy seed construction.
- **Phase 4**: local-search product insertion/removal/replacement moves.
- **Phase 5+**: experiment wiring, validation, tuning, and documentation cleanup.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` is effectively a no-op when using the project environment.

`solve.sh` writes:

- `solution.json`: primary benchmark solution (currently empty valid actions for Phase 1)
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

## Phase 1 Exit Criteria

- Solver scaffold is runnable and standalone.
- Candidate and product debug summaries are deterministic.
- Product objects contain all observations needed for atomic insertion/removal.
- No benchmark, experiment, runtime, or other solver imports are introduced.

## Known Limitations

- This is a reproduction of the paper's method family, not a claim to reproduce every runtime or every table from the paper.
- Phase 1 does not yet implement sequence propagation, greedy seeding, or local search moves.
- Solver-local product predicates are designed to match the verifier geometry, but minor drift is possible due to floating-point ordering.
