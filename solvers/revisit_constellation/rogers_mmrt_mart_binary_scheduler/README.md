# Rogers MMRT/MART Binary Scheduler

This is the Phase 1 scaffold for a reproduced `revisit_constellation` solver based on Rogers MMRT/MART constellation-design models followed by a later binary observation scheduler.

The current implementation is intentionally limited to standalone preprocessing:

- parse public `assets.json` and `mission.json`
- build a deterministic finite circular-orbit slot library
- propagate slots with Brahe J2 dynamics
- generate a sparse visibility matrix `V[t,j,p]`
- write an empty benchmark-shaped `solution.json`
- write `status.json` and `model_prep/*` summaries

It does not import benchmark internals and does not implement MMRT/MART optimization or scheduling yet.

## Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`solve.sh` writes:

- `solution.json`
- `status.json`
- `model_prep/slots.json`
- `model_prep/time_grid.json`
- `model_prep/visibility_matrix.json`

Optional configuration can be provided with `config.yaml`, `config.yml`, or `config.json` in the config directory. Supported keys are:

- `sample_step_sec` (default `7200`)
- `altitude_count` (default `1`)
- `inclination_deg` (default `[55.0, 97.6]`)
- `raan_count` (default `4`)
- `phase_count` (default `2`)
- `max_slots` (default `16`)
- `write_visibility_matrix`
