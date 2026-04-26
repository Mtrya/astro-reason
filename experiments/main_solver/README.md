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

Run the RGT/APC constructive `revisit_constellation` smoke case:

```bash
uv run python experiments/main_solver/run.py \
    --benchmark revisit_constellation \
    --solver revisit_constellation_rgt_apc_gap_constructive \
    --case test/case_0001
```

Run the RGT/APC constructive public cases with the profile declared in the solver
config:

```bash
uv run python experiments/main_solver/run.py \
    --benchmark revisit_constellation \
    --solver revisit_constellation_rgt_apc_gap_constructive
```

The `revisit_constellation_rgt_apc_gap_constructive` solver profile embeds the
experiment-owned `smoke` default plus deterministic `fair`,
`scaled_architecture`, and `stress` profile definitions. The default is kept
contract-speed for routine official smoke verification; the scaled profiles
broaden the minmax-architecture RGT/APC candidate pool, phase grid, RGT ratio
breadth, and visibility workers for reproduction-frontier evidence. The profile
is intentionally not promoted to `repro_ci: true`; solver CI remains
contract-focused, while this experiment owns the verifier command, run policy,
and result artifacts.

For `revisit_constellation`, aggregated summaries treat
`capped_max_revisit_gap_hours` as the benchmark primary metric: per-target capped
maximum revisit gap aggregated by mean. `worst_target_capped_max_revisit_gap_hours`
and `mean_revisit_gap_hours` are diagnostics.

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

Benchmark verifiers are consumed as executables. The runner does not import benchmark-internal functions, classes, or modules.
