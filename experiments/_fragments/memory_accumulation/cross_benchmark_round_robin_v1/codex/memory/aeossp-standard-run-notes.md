# AEOSSP Standard Run Notes

- Final verified `solution.json`:
  - `valid: true`
  - `CR: 0.7993216506500848`
  - `WCR: 0.7755437012720559`
  - `TAT: 1090.6506364922207`
  - `PC: 21823.687008844532`
  - `num_actions: 1414`
- Effective workflow:
  - Loaded the PyInstaller-bundled verifier modules directly from `verifier` and reused `load_case`, `_PropagationContext`, `_target_vector_eci`, `_off_nadir_deg`, `_slew_time_s`, and `analyze`.
  - Precomputed exact satellite states on the mission `5 s` grid, then generated candidate observation starts by vectorized horizon and off-nadir checks over each task window.
  - For each contiguous feasible-start run, keeping `start`, `mid`, and `end` representatives gave enough flexibility without exploding the candidate count.
  - Built several deterministic greedy schedules with different task orderings and candidate-choice policies, then kept the best verifier-scored result.
  - A local improvement pass allowing profitable single-candidate insertions with up to two conflicting removals improved the greedy baseline.
- Important verifier detail:
  - The first observation on each satellite still needs an initial slew from nadir at the mission start. Treat its required gap as `slew(off_nadir_at_start) + settling_time`, not zero.
- Geometry detail that mattered:
  - The verifier’s off-nadir angle uses the satellite position vector and the line of sight vector. Using the negated satellite vector flips the angle to `180 - off_nadir` and silently kills candidate generation.
