# SPOT-5 Dataset Layout

The canonical SPOT-5 dataset is stored case by case under `cases/`.

Each case directory contains exactly one raw instance file:

```text
dataset/
├── index.json
├── example_solution.json
└── cases/
    └── <split>/
        └── <case_id>/
            └── <case_id>.spot
```

Examples:

- `cases/single_orbit/8/8.spot`
- `cases/multi_orbit/1502/1502.spot`
- `cases/test/1021/1021.spot`

`index.json` records the benchmark name, upstream provenance, the list of
published split-aware case placements, and `example_smoke_case` for pairing the
example solution with a case in CI (see `docs/benchmark_contract.md`).

`example_solution.json` is one minimal runnable solution (same schema as a real
submission) for verifier smoke tests. These are not baselines.

The committed split assignment is recorded in [splits.yaml](../splits.yaml).
It defines the full `single_orbit` and `multi_orbit` families plus an
overlapping 5-case `test` split sampled with seed `42`.

To regenerate this layout from the upstream Mendeley release, run:

```bash
uv run python benchmarks/spot5/generator.py benchmarks/spot5/splits.yaml
```

To regenerate from a local directory of raw `.spot` files instead, run:

```bash
uv run python benchmarks/spot5/generator.py benchmarks/spot5/splits.yaml --source-dir /path/to/raw-spot-files
```
