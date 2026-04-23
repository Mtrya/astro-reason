# Phase 5: Decode, Repair, Experiment Wiring, And Tests

## Goal

Decode selected products into benchmark solution actions, apply conservative local repair, add focused tests, and wire the solver into `experiments/main_solver`.

## Inputs To Read

- `solvers/stereo_imaging/roadmap/time_window_pruned_stereo_milp/ROADMAP.md`
- Phase 4 implementation
- `docs/solver_contract.md`
- `experiments/main_solver/README.md`
- `experiments/main_solver/config.yaml`
- Existing solver registration examples in `experiments/main_solver/solvers/`

## In Scope

- Decode selected candidate observations into sorted action JSON.
- Deduplicate observations shared by multiple products.
- Add conservative solver-local repair:
  - remove overlapping same-satellite actions
  - remove actions that violate local slew/settle checks
  - drop products whose required actions were removed
  - prefer preserving coverage before quality
- Add or update tests under `tests/solvers/` for solver-local behavior.
- Add `experiments/main_solver/solvers/stereo_imaging_time_window_pruned_stereo_milp.yaml`.
- Add main-solver config entry with `evidence_type: reproduced_solver` only after the solver is runnable.

## Out Of Scope

- Tuning for best scores.
- Documentation finalization.
- Benchmark verifier imports inside solver code.

## Implementation Notes

- Repair should be auditable, not magical. Write `debug/repair_log.json` when debug is enabled.
- If repair removes an observation, remove or recompute any product credit connected to it in `status.json`.
- Main-solver registration should use the same naming pattern as existing reproduced solvers.

## Validation

- Run focused solver tests.
- Run direct smoke.
- Run official main-solver smoke:

```bash
uv run python experiments/main_solver/run.py --benchmark stereo_imaging --solver stereo_imaging_time_window_pruned_stereo_milp --case test/case_0001
```

- Run the benchmark verifier manually on at least one direct output if main-solver wiring is not ready.

## Exit Criteria

- `solution.json` contains only valid observation action objects.
- Solver-local tests pass.
- Main-solver smoke reaches official verification.
- Repair decisions are recorded and deterministic.

## Suggested Prompt

Read the stereo MILP roadmap, Phase 4 code, main-solver contract, and this phase doc. Implement decoding, conservative repair, focused tests, and main-solver registration for the Kim-style stereo MILP solver. Run direct and official smoke validation.
