# Phase 7: Docs, Cleanup, And Promotion

## Goal

Finish the Kim-style stereo MILP solver with comprehensive documentation, cleanup, and promotion metadata following the standard set by `solvers/aeossp_standard/mwis_conflict_graph/README.md`.

## Inputs To Read

- `solvers/aeossp_standard/mwis_conflict_graph/README.md`
- `solvers/stereo_imaging/roadmap/time_window_pruned_stereo_milp/ROADMAP.md`
- Phase 6 reproduction/tuning notes
- `docs/solver_contract.md`
- `experiments/main_solver/README.md`
- `solvers/finished_solvers.json`

## In Scope

- Write or finalize `solvers/stereo_imaging/time_window_pruned_stereo_milp/README.md`.
- README should include:
  - solver identity
  - citation and BibTeX
  - method summary
  - benchmark adaptation
  - solver contract
  - candidate observation library
  - pair/tri product variables
  - time-window pruning
  - backend and fallback behavior
  - decode and repair
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

- Include BibTeX for Kim et al.:

```bibtex
@article{kim2020stereo,
  title = {Task Scheduling of Agile Satellites with Transition Time and Stereoscopic Imaging Constraints},
  author = {Kim, Junhong and Cho, Doo-Hyun and Ahn, Jaemyung and Choi, Han-Lim},
  journal = {Journal of Aerospace Information Systems},
  volume = {17},
  number = {6},
  pages = {285--293},
  year = {2020},
  doi = {10.2514/1.I010775},
  eprint = {1912.00374},
  archivePrefix = {arXiv}
}
```

- README must state that benchmark product variables replace Kim's pitch-difference stereo constraint.
- README must state that downlink/storage constraints are omitted because the benchmark excludes them.
- README must describe the validation/tuning evidence used to support solver-audit claims: correctness, benchmark contract compliance, and timeout/resource realism.

## Validation

- Run focused solver tests.
- Run official main-solver smoke.
- Run README commands.
- Check that no generated debug/result artifacts are committed.

## Exit Criteria

- README is complete enough for an external reader to understand both the paper and benchmark adaptation.
- BibTeX is included.
- Solver is promoted only if official smoke verification passes.
- Final handoff lists validation commands and residual limitations.

## Suggested Prompt

Read the Kim stereo MILP roadmap, Phase 6 notes, current solver, and `solvers/aeossp_standard/mwis_conflict_graph/README.md`. Finish documentation and cleanup for the stereo MILP solver. Include BibTeX, benchmark adaptation, config/debug docs, known limitations, and promotion metadata only after official smoke verification passes.
