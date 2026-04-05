# Benchmark Contract

This document defines the repository contract for benchmark layout, public
entrypoints, and CI enforcement.

The contract is enforced only for benchmarks listed in
`benchmarks/finished_benchmarks.json`. Benchmarks that are still under active construction are documented by repository conventions, but they are not yet subject to strict CI checks.

## Finished Benchmark Metadata

`benchmarks/finished_benchmarks.json` is the source of truth for which
benchmarks are considered finished.

Each finished benchmark entry records:

- the benchmark name
- whether generator reproducibility should run in dedicated CI
- which dataset paths are generator-owned canonical outputs

Promoting a benchmark to finished status should happen only when its public
README, dataset layout, generator, verifier, and tests are ready to be treated as stable.

## Required Benchmark Shape

Each finished benchmark must live under `benchmarks/<name>/` and must contain:

- `README.md`
- `dataset/`
- a generator entrypoint: `generator.py` or `generator/run.py`
- a verifier entrypoint: `verifier.py` or `verifier/run.py`

Optional:

- `visualizer.py` or `visualizer/run.py`
- `dataset/index.json`
- `dataset/README.md`

No other tracked top-level benchmark entries are allowed for finished
benchmarks.

## Dataset Contract

The canonical dataset layout for finished benchmarks is:

```text
dataset/
├── cases/
│   └── <case_id>/
│       └── example_solution.json  # required in at least one canonical case
├── index.json      # optional
└── README.md       # optional
```

Rules:

- `dataset/cases/` is mandatory.
- Case identifiers are benchmark-specific. CI does not require a `case_####` naming pattern.
- At least one canonical case must include `example_solution.json`,
  `example_solution.yaml`, or `example_solution.yml` so CI can run the public verifier against a real benchmark case automatically.
- `index.json` is optional. If present, it is benchmark metadata, not a second source of truth for completion status.
- Generators must not write `dataset/README.md`.
- Additional tracked dataset files are allowed when they are benchmark-owned public artifacts and are documented in the benchmark README.
- `dataset/source_data/` may be used as a download/cache directory, but it must stay gitignored and must not be required to exist before running the generator.

## Generator Contract

Finished benchmark generators must satisfy the following:

- They are runnable with `python benchmarks/<name>/generator.py` or
  `python benchmarks/<name>/generator/run.py`.
- Running without flags produces the default canonical dataset for that
  benchmark.
- Reproducing the canonical dataset must not require a manual multi-step setup with many required flags.
- Extra CLI flags may expand or redirect generation, but the no-flag path is the canonical one.
- If source downloads are needed, the generator may cache them under
  `dataset/source_data/`, but it must also be able to perform a live download when that cache is absent.

## Verifier Contract

Finished benchmark verifiers must satisfy the following:

- They are runnable with `python benchmarks/<name>/verifier.py` or
  `python benchmarks/<name>/verifier/run.py`.
- The public CLI accepts two positional arguments:
  - `case_dir`
  - `solution_path`
- Any additional CLI options must be optional.
- Verifiers must be runnable directly as scripts and must be able to load
  canonical cases without crashing.

Case-local `example_solution.json` or `example_solution.yaml` files are the
preferred verifier smoke-test convention for finished benchmarks. They are
runnable examples, not baselines.

## Enforced CI Checks

For finished benchmarks, CI enforces:

- benchmark presence in `benchmarks/finished_benchmarks.json`
- required top-level files and directories
- canonical dataset case layout under `dataset/cases/`
- example solution for verifier smoke tests at dataset root
- no tracked `dataset/source_data/`
- no tracked editor backup artifacts such as files ending in `~`
- no `sys.path` hacks in benchmark generator/verifier/visualizer code
- no `from benchmarks.` imports in benchmark generator/verifier/visualizer code
- passing repository tests

GitHub Actions runs:

- PR/push CI for tests plus contract validation
- a separate reproducibility workflow for finished benchmarks whose metadata has
  `"repro_ci": true`

The reproducibility workflow compares only generator-owned dataset outputs from `generated_paths`, because finished benchmarks may also keep documented, hand-written dataset artifacts such as dataset-level notes.

## Documented But Not Fully Automated Yet

The following are part of the public contract even when CI does not fully
enforce them yet:

- benchmark public code and public artifacts must not reference internal-only guidance such as `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or `docs/internal/`
- public verifier/generator/visualizer code should avoid path hacks and other brittle bootstrapping
- public benchmark-facing data and comments should avoid benchmark-leakage
  phrasing that explicitly tells a space agent it is inside a verification
  harness
- the repository remains solution-free; example solutions are only for verifier smoke tests and are not baselines
