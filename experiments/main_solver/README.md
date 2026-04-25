# Main Solver Experiment

`main_solver` is the first non-agentic experiment scaffold.

It runs benchmark-grouped solvers through the public solver contract:

```bash
./setup.sh
./solve.sh <case_dir> <config_dir> <solution_dir>
```

The experiment owns run selection, result layout, verification, and aggregation.
Solvers own implementation details and may use any language behind their shell
entrypoints.

Unlike agentic runs, traditional solver entries are benchmark-specific. The
experiment therefore keeps one solver-centered config:

```text
experiments/main_solver/
├── config.yaml
└── solvers/
```

Each solver profile carries the benchmark name, case list or reported metrics,
executable verifier command when the solver is runnable, and optional
solver-owned config written to each job's `config/config.yaml`.

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

Runnable rows include setup, solve, and verifier sections. Citation-reported
rows include reported metrics and provenance instead of execution logs.

Benchmark verifiers are consumed as executables. The runner does not import
benchmark-internal functions, classes, or modules.

## AEOSSP Fair Profiles

The AEOSSP standard Greedy-LNS profile uses `total_time_budget_s: 300` with
quality-preserving search enabled: eight restarts, stochastic component
ordering with a fixed seed, bounded exact reinsertion, battery guardrails,
satellite-scoped candidate workers, and deterministic restart-wave local-search
workers. Each connected-component descent remains sequential, but independent
restart starts can run in process-pool waves.

The AEOSSP standard MWIS profile uses `total_time_budget_s: 300` as the public
fair-run envelope while keeping the stronger refinement profile enabled:
sixteen local passes, population size eight, twenty-four recombination rounds,
satellite-scoped candidate and graph workers, and the internal reduction-backed
backend. Candidate generation, graph build, reduction, search, and repair remain
reported separately so the status artifacts show how much budget reached each
solver stage. A run longer than the nominal envelope should be interpreted with
the status timing and repair-impact artifacts rather than by wall clock alone.
