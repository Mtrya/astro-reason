# Main Solver Experiment

`main_solver` is the first non-agentic experiment scaffold.

It runs benchmark-grouped solvers through the public solver contract:

```bash
./setup.sh
./solve.sh <case_dir> <config_dir> <solution_dir>
```

The experiment owns run selection, result layout, verification, and aggregation. Solvers own implementation details and may use any language behind their shell entrypoints.

Unlike agentic runs, traditional solver entries are benchmark-specific. The experiment therefore keeps one solver-centered config:

```text
experiments/main_solver/
├── config.yaml
└── solvers/
```

Each solver profile carries the benchmark name, case list or reported metrics, executable verifier command when the solver is runnable, and optional solver-owned config written to each job's `config/config.yaml`.

## Evidence Types

Rows keep an explicit `evidence_type`:

- `reproduced_solver`: runnable solver output verified by a benchmark verifier
- `fixture_backed_lookup`: runnable lookup output verified by a benchmark verifier
- `citation_reported`: non-runnable metrics copied from cited literature

Do not merge these categories in reporting without preserving the label.

## Usage

Preview selected jobs:

```bash
uv run python experiments/main_solver/run.py --dry-run
```

Run a smoke case:

```bash
uv run python experiments/main_solver/run.py \
    --benchmark spot5 \
    --solver spot5_reference_lookup \
    --case test/8
```

Run one solver case:

```bash
uv run python experiments/main_solver/run.py \
    --benchmark <benchmark_id> \
    --solver <solver_id> \
    --case <case_id>
```

Run a named solver policy:

```bash
uv run python experiments/main_solver/run.py \
    --benchmark <benchmark_id> \
    --solver <solver_id> \
    --policy <policy_id>
```

Policy metadata is recorded in `run.json`. Solver-specific quality interpretation belongs in solver documentation and solver profile metadata, not in the shared experiment runner.

Materialize SatNet citation-backed rows:

```bash
uv run python experiments/main_solver/run.py \
    --benchmark satnet \
    --solver satnet_milp_claudet2022
```

Aggregate results:

```bash
uv run python experiments/main_solver/aggregate.py
```

## Result Layout

```text
results/main_solver/<benchmark>/<solver>/<case_slug>/
├── config/
├── solution/
├── logs/
└── run.json
```

Named solver policies append the policy id to the case slug, for example `suite__case_001__large_policy`, so policy artifacts do not overwrite one another.

Benchmark verifiers are consumed as executables. The runner does not import benchmark-internal functions, classes, or modules.
