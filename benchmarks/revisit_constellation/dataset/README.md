# Revisit Constellation Dataset

This directory contains the canonical committed dataset for the
`revisit_constellation` benchmark.

## Layout

- `index.json`
- `example_solutions.json`
- `cases/<case_id>/assets.json`
- `cases/<case_id>/mission.json`

Each case directory contains only the two canonical machine-readable files used
by the verifier. `example_solutions.json` maps case IDs to minimal runnable
examples for verifier smoke tests; these are not baselines.

## Canonical Generation

This committed dataset is intended to be rebuilt with:

```bash
uv run python benchmarks/revisit_constellation/generator/run.py
```

The generator downloads the documented source datasets automatically via
`kagglehub`, stores the raw source data under `dataset/source_data/` by
default, and then rebuilds the canonical cases.

Source datasets:

- world cities: `juanmah/world-cities`
- ground stations: `pratiksharm/ground-station-dataset`
