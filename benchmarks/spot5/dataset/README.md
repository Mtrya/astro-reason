# SPOT-5 Dataset Layout

The canonical SPOT-5 dataset is stored case by case under `cases/`.

Each case directory contains exactly one raw instance file:

```text
dataset/
├── index.json
├── example_solution.json
└── cases/
    └── <case_id>/
        └── <case_id>.spot
```

Examples:

- `cases/8/8.spot`
- `cases/1502/1502.spot`
- `cases/1021/1021.spot`

`index.json` records the benchmark name, upstream provenance, the list of
published case IDs, and optional `example_smoke_case_id` for pairing the
example solution with a case in CI (see `docs/benchmark_contract.md`).

`example_solution.json` is one minimal runnable solution (same schema as a real
submission) for verifier smoke tests. These are not baselines.

To regenerate this layout from the upstream Mendeley release, run:

```bash
uv run python benchmarks/spot5/generator.py
```

To regenerate from a local directory of raw `.spot` files instead, run:

```bash
uv run python benchmarks/spot5/generator.py --source-dir /path/to/raw-spot-files
```
