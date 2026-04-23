# Phase 1: Contract, Candidates, And Product Library

## Goal

Create the standalone solver scaffold and reusable candidate/product library needed by the Lemaitre-style insertion search.

## Inputs To Read

- `solvers/stereo_imaging/roadmap/cp_local_search_stereo_insertion/ROADMAP.md`
- Issue #90
- `benchmarks/stereo_imaging/README.md`
- `docs/solver_contract.md`
- `solvers/stereo_imaging/literature/lemaitre-2002-cp-local-search.md`
- `solvers/stereo_imaging/literature/summary.md`

## In Scope

- Add `solvers/stereo_imaging/cp_local_search_stereo_insertion/`.
- Add `setup.sh`, `solve.sh`, `README.md` placeholder, and `config.example.yaml`.
- Add standalone parsing for `satellites.yaml`, `targets.yaml`, and `mission.yaml`.
- Enumerate candidate observations and group them by `(satellite_id, target_id, access_interval_id)`.
- Enumerate valid or likely-valid pair and tri-stereo products.
- Store each product as an atomic move unit containing all required observations, target id, estimated quality, and feasibility metadata.
- Emit empty valid `solution.json` and candidate/product debug summaries.

## Out Of Scope

- Sequence propagation.
- Greedy seed construction.
- Local search moves.
- Main-solver registration.

## Implementation Notes

- This phase can reuse conceptual candidate logic from the MILP roadmap if available, but must not import from another solver.
- Product candidates should be sorted deterministically by coverage value, quality, target id, satellite id, access interval, and time tuple.
- Keep tri-stereo candidates bounded per target/access interval to avoid later search blowups.
- Record enough metadata to explain why a product failed or was not generated.

## Validation

- Run direct `setup.sh`.
- Run direct `solve.sh benchmarks/stereo_imaging/dataset/cases/test/case_0001`.
- Add focused tests for parser behavior and product library ordering.
- Verify emitted empty or candidate-light solution with the benchmark verifier manually.

## Exit Criteria

- Solver scaffold is runnable and standalone.
- Candidate and product debug summaries are deterministic.
- Product objects contain all observations needed for atomic insertion/removal.
- No benchmark, experiment, runtime, or other solver imports are introduced.

## Suggested Prompt

Read the CP/local-search stereo roadmap, this phase doc, issue #90, and the benchmark README. Implement only the standalone scaffold, public YAML parsing, candidate observation enumeration, and pair/tri product library for `solvers/stereo_imaging/cp_local_search_stereo_insertion/`. Do not implement local search yet.
