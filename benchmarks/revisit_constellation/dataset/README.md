# Revisit Constellation Dataset

This directory contains the canonical committed dataset for the
`revisit_constellation` benchmark.

## Layout

- `index.json`
- `example_solution.json`
- `cases/<case_id>/assets.json`
- `cases/<case_id>/mission.json`

Each case directory contains only the two canonical machine-readable files used
by the verifier. `example_solution.json` is a single minimal runnable solution
(same schema as a real submission) for verifier smoke tests; these are not baselines.

## Canonical Generation

This committed dataset is intended to be rebuilt with:

```bash
uv run python -m benchmarks.revisit_constellation.generator.run
```

The generator downloads the documented source dataset automatically via
`kagglehub`, stores the raw source data under `dataset/source_data/` by
default, and then rebuilds the canonical cases.

Source dataset:

- world cities: `juanmah/world-cities`
