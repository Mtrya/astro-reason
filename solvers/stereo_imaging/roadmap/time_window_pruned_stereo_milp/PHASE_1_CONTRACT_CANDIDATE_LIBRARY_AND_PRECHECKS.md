# Phase 1: Contract, Candidate Library, And Prechecks

## Goal

Create the standalone solver scaffold and a deterministic observation-candidate library that reads public case files and emits locally plausible benchmark actions without using benchmark imports.

## Inputs To Read

- `solvers/stereo_imaging/roadmap/time_window_pruned_stereo_milp/ROADMAP.md`
- Issue #89
- `benchmarks/stereo_imaging/README.md`
- `docs/solver_contract.md`
- `solvers/stereo_imaging/literature/kim-2020-stereo-milp.md`
- `tests/benchmarks/test_stereo_imaging_verifier.py`

## In Scope

- Add `solvers/stereo_imaging/time_window_pruned_stereo_milp/`.
- Add `setup.sh`, `solve.sh`, `README.md` placeholder, and `config.example.yaml`.
- Add solver-local parsing for `satellites.yaml`, `targets.yaml`, and `mission.yaml`.
- Define data models for satellites, targets, mission thresholds, candidate observations, and access intervals.
- Enumerate candidate observations per satellite-target pass with deterministic time samples and steering angles.
- Implement solver-local prechecks for:
  - mission horizon containment
  - duration bounds
  - combined off-nadir limit
  - solar-elevation threshold approximation or sampled filter
  - same access interval grouping
- Emit empty valid `solution.json` when no candidates survive.

## Out Of Scope

- Stereo pair/tri scoring.
- MILP model construction.
- Main-solver registration.
- Calling benchmark verifier from solver code.

## Implementation Notes

- Keep all code standalone under the solver directory.
- Prefer small modules such as `io.py`, `models.py`, `geometry.py`, `candidates.py`, and `solve.py`.
- Candidate generation should record why candidates were rejected, because later phases need pruning and audit diagnostics.
- Use a configurable sample stride and cap candidates per `(satellite, target, access_interval)`.
- If exact SGP4/access reproduction is expensive, this phase may use a conservative approximate generator, but it must flag approximation drift as a Phase 6 item.

## Validation

- Run direct `setup.sh`.
- Run direct `solve.sh benchmarks/stereo_imaging/dataset/cases/test/case_0001`.
- Run the official verifier manually on the emitted empty or candidate-light solution.
- Add focused tests for parsing and combined off-nadir/duration checks if a solver-local test package exists.

## Exit Criteria

- Solver can read a public case and write schema-valid `solution.json`.
- Candidate debug summary reports counts by satellite, target, access interval, and rejection reason.
- No benchmark, experiment, runtime, or other solver imports are introduced.
- The implementation is deterministic for identical config and inputs.

## Suggested Prompt

Read the stereo MILP roadmap, this phase doc, issue #89, and `benchmarks/stereo_imaging/README.md`. Implement only the standalone scaffold, public YAML parsing, deterministic candidate observation library, and cheap local prechecks for `solvers/stereo_imaging/time_window_pruned_stereo_milp/`. Do not import benchmark internals. Run the direct smoke command and verifier on the emitted solution.
