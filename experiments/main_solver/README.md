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

Run the regional-coverage CELF smoke case:

```bash
uv run python experiments/main_solver/run.py \
    --benchmark regional_coverage \
    --solver regional_coverage_celf_submodular \
    --case test/case_0001
```

Run the regional-coverage CELF policy envelopes:

```bash
# Fast verifier smoke.
uv run python experiments/main_solver/run.py \
    --benchmark regional_coverage \
    --solver regional_coverage_celf_submodular \
    --policy smoke

# Larger fixed-candidate evaluation envelope with verifier and bound evidence.
uv run python experiments/main_solver/run.py \
    --benchmark regional_coverage \
    --solver regional_coverage_celf_submodular \
    --policy evaluation

# Diagnostic candidate-scaling probe. This is intentionally not promotion
# evidence for a quality-fair optimization envelope.
uv run python experiments/main_solver/run.py \
    --benchmark regional_coverage \
    --solver regional_coverage_celf_submodular \
    --policy quality_probe_32768
```

Policy metadata may include `quality_envelope` fields. These distinguish
contract/smoke, reproduction, and quality-diagnostic envelopes. A solver
finishing before timeout is not enough to call the optimization envelope fair;
candidate density, search depth, repair loss, and verifier score must also be
inspected.

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

Named solver policies append the policy id to the case slug, for example
`test__case_0001__evaluation`, so smoke and evaluation artifacts do not
overwrite one another.

Benchmark verifiers are consumed as executables. The runner does not import benchmark-internal functions, classes, or modules.
