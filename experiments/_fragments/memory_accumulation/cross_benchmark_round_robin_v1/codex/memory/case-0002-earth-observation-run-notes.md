# Case 0002 Earth-Observation Run Notes

- Final verified `solution.json`:
  - `valid: true`
  - `CR: 0.7395348837209302`
  - `WCR: 0.7179921037789058`
  - `TAT: 934.1544374563242`
  - `PC: 20965.799285155772`
  - `num_actions: 1431`
- Working approach:
  - Loaded the PyInstaller-bundled verifier modules directly from `verifier` with `PyInstaller.archive.readers`.
  - Reused the verifier’s `load_case`, `_PropagationContext`, `_target_vector_eci`, `_slew_time_s`, and `analyze` functions instead of reimplementing propagation or scoring.
  - Precomputed ECEF and ECI satellite states on the mission `5 s` grid, then built observation candidates by vectorized visibility and off-nadir checks inside each task window.
  - Used denser candidate start sampling for `weight >= 4` tasks and infrared tasks; kept earliest, latest, midpoint, quartiles, and best-off-nadir starts, plus all starts for short high-value runs.
  - Compared several deterministic greedy schedules and kept the verifier-best result.
- Useful reminder:
  - The first observation on a satellite still needs an initial slew from nadir at mission start, so the pre-observation gap check cannot be skipped for the first action.
