# Phase 5: Repair, Experiment Wiring, And Tests

## Goal

Add final conservative repair, focused tests, and main-solver wiring so the local-search solver is runnable through the official experiment path.

## Inputs To Read

- `solvers/stereo_imaging/roadmap/cp_local_search_stereo_insertion/ROADMAP.md`
- Phase 4 implementation
- `docs/solver_contract.md`
- `experiments/main_solver/README.md`
- `experiments/main_solver/config.yaml`
- Existing solver registration examples in `experiments/main_solver/solvers/`

## In Scope

- Decode per-satellite sequences into sorted benchmark actions.
- Repair any remaining local conflicts by removing the least valuable affected product.
- Recompute final product coverage and quality estimates after repair.
- Add tests under `tests/solvers/` for:
  - deterministic repeatability
  - insertion rollback
  - local-search acceptance
  - repair removal
  - output schema
- Add `experiments/main_solver/solvers/stereo_imaging_cp_local_search_stereo_insertion.yaml`.
- Add main-solver config entry with `evidence_type: reproduced_solver` only after the solver is runnable.

## Out Of Scope

- Extensive tuning.
- README finalization.
- Benchmark verifier imports inside solver code.

## Implementation Notes

- Repair should preserve coverage before improving quality.
- If repair removes every product for a target, record that target and the blocking reason.
- Main-solver naming should be stable and specific enough to distinguish from the MILP solver.

## Validation

- Run focused solver tests.
- Run direct smoke.
- Run official main-solver smoke:

```bash
uv run python experiments/main_solver/run.py --benchmark stereo_imaging --solver stereo_imaging_cp_local_search_stereo_insertion --case test/case_0001
```

- Run the benchmark verifier manually on a direct output if main-solver wiring is not ready.

## Exit Criteria

- Solver-local tests pass.
- Direct and official smoke paths produce `solution.json`.
- Repair is deterministic and auditable.
- Main-solver registration uses `evidence_type: reproduced_solver`.

## Suggested Prompt

Read the CP/local-search roadmap, Phase 4 code, main-solver contract, and this phase doc. Implement final repair, focused tests, and main-solver registration for the Lemaitre-style stereo insertion solver. Run direct and official smoke validation.
