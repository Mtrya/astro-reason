# Revisit Constellation Dataset

This directory contains the canonical committed dataset for the `revisit_constellation` benchmark.

## Layout

- `index.json`
- `example_solution.json`
- `cases/<split>/<case_id>/assets.json`
- `cases/<split>/<case_id>/mission.json`

Each case directory contains only the two canonical machine-readable files used by the verifier. `index.json` records split-aware case paths and `example_smoke_case` for pairing `example_solution.json` with one committed case. `example_solution.json` is a single minimal runnable solution (same schema as a real submission) for verifier smoke tests; these are not baselines.

The committed split policy is benchmark-owned:

- `cases/train/case_0001` through `cases/train/case_0010` are public development cases.
- `cases/test/case_0001` through `cases/test/case_0005` are held-out evaluation cases.

Train and test cases are generated from disjoint split seeds and target-selection offsets declared in [splits.yaml](../splits.yaml). Target selection uses log-scaled city population as the primary sampling signal and geographic spread as a secondary balancing term, with one shared policy across both splits.

## Canonical Generation

This committed dataset is intended to be rebuilt with:

```bash
uv run python -m benchmarks.revisit_constellation.generator.run \
  benchmarks/revisit_constellation/splits.yaml
```

The generator stages the vendored world-cities snapshot (`../generator/world_cities_snapshot.csv`, normalized from version 8 of the documented Kaggle dataset) under `dataset/source_data/` by default, and then rebuilds the canonical cases without network access. The committed dataset-shape contract lives in [splits.yaml](../splits.yaml); operational staging controls like `--download-dir` remain CLI options.

Source dataset:

- world cities: `juanmah/world-cities` version 8 (vendored as `../generator/world_cities_snapshot.csv`)
