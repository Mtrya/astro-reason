# Phase 7: Docs, Cleanup, And Promotion

## Goal

Finish the Lemaitre-style stereo insertion solver with comprehensive documentation, cleanup, and promotion metadata following the standard set by `solvers/aeossp_standard/mwis_conflict_graph/README.md`.

## Inputs To Read

- `solvers/aeossp_standard/mwis_conflict_graph/README.md`
- `solvers/stereo_imaging/roadmap/cp_local_search_stereo_insertion/ROADMAP.md`
- Phase 6 reproduction/tuning notes
- `docs/solver_contract.md`
- `experiments/main_solver/README.md`
- `solvers/finished_solvers.json`

## In Scope

- Write or finalize `solvers/stereo_imaging/cp_local_search_stereo_insertion/README.md`.
- README should include:
  - solver identity
  - citation and BibTeX
  - method summary
  - benchmark adaptation
  - solver contract
  - candidate/product library
  - sequence propagation
  - greedy seed
  - local-search product moves
  - optional Vasquez-inspired repair/diversification
  - configuration
  - debug artifacts
  - running commands
  - sanity baseline and tuning notes
  - known limitations
  - evidence type
- Finalize `config.example.yaml`.
- Ensure entrypoints are executable.
- Remove temporary debug/results artifacts.
- Add to `solvers/finished_solvers.json` only after official smoke validity and docs are complete.

## Out Of Scope

- New solver features.
- Large score sweeps.
- Benchmark or dataset edits.

## Implementation Notes

- Include BibTeX for Lemaitre and Vasquez:

```bibtex
@article{lemaitre2002selecting,
  title = {Selecting and Scheduling Observations of Agile Satellites},
  author = {Lema{\^i}tre, Michel and Verfaillie, G{\'e}rard and Jouhaud, Frank and Lachiver, Jean-Michel and Bataille, Nicolas},
  journal = {Aerospace Science and Technology},
  volume = {6},
  number = {5},
  pages = {367--381},
  year = {2002},
  doi = {10.1016/S1270-9638(02)01173-2}
}

@article{vasquez2001logic,
  title = {A Logic-Constrained Knapsack Formulation and a Tabu Algorithm for the Daily Photograph Scheduling of an Earth Observation Satellite},
  author = {Vasquez, Michel and Hao, Jin-Kao},
  journal = {Computational Optimization and Applications},
  volume = {20},
  number = {2},
  pages = {137--157},
  year = {2001},
  doi = {10.1023/A:1012300271919}
}
```

- README must explain that product insertion/removal preserves Lemaitre's coupled stereoscopic request behavior.
- README must distinguish the core Lemaitre reproduction from optional Vasquez-inspired repair ideas.
- README must describe the validation/tuning evidence used to support solver-audit claims: correctness, benchmark contract compliance, and timeout/resource realism.

## Validation

- Run focused solver tests.
- Run official main-solver smoke.
- Run README commands.
- Check that no generated debug/result artifacts are committed.

## Exit Criteria

- README is complete enough for an external reader to understand both the papers and benchmark adaptation.
- BibTeX is included.
- Solver is promoted only if official smoke verification passes.
- Final handoff lists validation commands and residual limitations.

## Suggested Prompt

Read the CP/local-search stereo roadmap, Phase 6 notes, current solver, and `solvers/aeossp_standard/mwis_conflict_graph/README.md`. Finish documentation and cleanup for the stereo insertion solver. Include BibTeX, benchmark adaptation, config/debug docs, known limitations, and promotion metadata only after official smoke verification passes.
