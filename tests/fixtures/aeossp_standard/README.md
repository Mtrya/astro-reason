These fixtures lock the standalone `aeossp_standard` verifier behavior.

Principles:

- keep cases tiny and interpretable
- prefer one behavior per fixture
- assert only stable, behavior-defining report fields
- use the canonical benchmark case files:
  - `mission.yaml`
  - `satellites.yaml`
  - `tasks.yaml`
  - `solution.json`
  - `expected.json`

Fixture set:

- `full_completion_valid`
  - one task, one valid observation, exact metrics
- `zero_completion_valid`
  - valid zero-observation schedule with `TAT = null`
- `duplicate_observation_no_bonus_valid`
  - two valid observations of the same task only count once
- `sensor_type_mismatch_invalid`
  - observation uses the wrong sensor modality
- `visibility_invalid`
  - observation fails continuous visibility geometry
- `observation_overlap_invalid`
  - same-satellite observations overlap
- `slew_gap_invalid`
  - same-satellite observations are too close for slew-plus-settle
- `battery_depletion_invalid`
  - battery underflow invalidates the solution
