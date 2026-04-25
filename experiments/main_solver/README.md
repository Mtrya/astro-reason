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

Experiment profiles own evidence metadata such as `evidence_type`. The hardened solver-contract registry at `solvers/finished_solvers.json` owns only `repro_ci` metadata and case/fixture paths.

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

Run the regional-coverage CP/local-search CI smoke envelope:

```bash
uv run python experiments/main_solver/run.py \
    --config experiments/main_solver/config_regional_coverage_cp_local_search_ci_smoke.yaml
```

Run the regional-coverage reproduction envelope, comparing greedy-only,
local-search, and CP-enabled modes over all public regional cases:

```bash
uv run python experiments/main_solver/run.py \
    --config experiments/main_solver/config_regional_coverage_cp_local_search_reproduction.yaml
uv run python experiments/main_solver/aggregate.py
```

The latest regional-coverage CP/local-search comparison verifies all fifteen
jobs under the dense reproduction envelope. Average official weighted coverage
is `0.8961799799329526` for greedy-only, `0.8983754575177383` for local search,
and `0.9013044997801305` for CP-enabled local search. The CP-enabled profile
records `214` OR-Tools CP-SAT calls and `57` improving local repairs across the
five public cases. Candidate generation uses deterministic process-pool
parallelism with `candidate_workers: 8`.

## Result Layout

```text
results/main_solver/<benchmark>/<solver>/<case_slug>/
├── config/
├── solution/
├── logs/
└── run.json
```

Benchmark verifiers are consumed as executables. The runner does not import benchmark-internal functions, classes, or modules.

## Solver Status Reporting

For runnable solvers that write `status.json`, aggregation preserves official
verifier metrics while also surfacing selected solver-status fields such as
execution mode, solve/verifier durations, phase timings, candidate counts,
search seeds, local-search move counts, and CP backend/call/timing summaries.
These fields are supplemental audit data; official validity and benchmark
scores remain the verifier-owned fields in `run.json`.
