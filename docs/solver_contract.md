# Solver Contract

This document defines the initial public contract for `solvers/`.

The contract is intentionally light. It gives experiments a stable way to call traditional methods without forcing every solver into the same language, package manager, or runtime model.

## Purpose

`solvers/` owns reusable traditional non-agentic methods.

Examples may eventually include:

- heuristic solvers
- optimization-based baselines
- reproducible classical pipelines
- solver-local evaluation helpers

Solvers consume benchmark case files and produce benchmark-shaped solution files. Benchmarks must not depend on solvers.

Solvers must be standalone method implementations. They should not import benchmark-internal functions, classes, or modules, and they should not call benchmark verifiers or other benchmark executables. A solver that needs preflight checks should implement those checks in solver-local code.

Experiments own official solver-vs-benchmark orchestration. They may run solver entrypoints and benchmark verifier entrypoints through CLI/file contracts.

## Directory Shape

Solvers are grouped by benchmark:

```text
solvers/
├── finished_solvers.json
└── <benchmark>/
    └── <solver>/
        ├── README.md
        ├── setup.sh
        ├── solve.sh
        ├── src/      # optional
        └── assets/   # optional
```

`finished_solvers.json` is the repository-level registry for solvers that are ready to be used by experiments or discussed in reports.

## Runnable Solver Contract

Runnable solvers expose two shell entrypoints:

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` prepares solver-local dependencies. It may be a no-op.

Python solvers may use the repository project environment when that is sufficient, but they are not limited to it. Solvers are encouraged to own a solver-local environment when they need additional PyPI packages or other dependencies that are not present globally. Solvers may also use their own package managers, compiled binaries, or other languages such as Rust, Julia, C++, or MiniZinc. Those choices should stay solver-local, be prepared by `setup.sh`, and be hidden behind `solve.sh`.

Python solvers that create their own virtual environment may write a solver-local `.solver-env` handoff file after setup. The file should contain simple `KEY=VALUE` lines such as `SOLVER_VENV_DIR=/abs/path/to/.venv` and `SOLVER_PYTHON=/abs/path/to/.venv/bin/python`. `solve.sh` should still work directly after setup by reading this file, and experiment runners may pass those values into the solve subprocess.

`solve.sh` receives:

- `case_dir`: required benchmark case directory
- `config_dir`: optional experiment-owned config directory
- `solution_dir`: optional directory where solution artifacts should be written

Experiments should usually pass both optional arguments explicitly. The solver should write its primary solution artifact into `solution_dir` and exit nonzero for unsupported cases or execution failures.

Solver code may be Python, shell, C++, Julia, MiniZinc, Rust, or anything else. The shell entrypoints are the boundary.

## Evidence Types

The initial registry distinguishes:

- `reproduced_solver`: a runnable solver produces a solution for a case
- `fixture_backed_lookup`: a runnable lookup emits a known reference solution
- `citation_reported`: documented metrics copied from cited literature without a runnable solver

Fixture-backed lookups and citation-reported entries must be labeled as such in reports. They are useful baselines, but they are not general solver claims.

## Ownership Boundaries

Solvers may own:

- reusable solver implementations
- solver-local dependencies and environment files
- solver-local validation and debug helpers
- solver-owned assets needed by the method, with provenance documented

Solvers must not become a shared dependency layer for:

- `benchmarks/`
- `experiments/`
- `runtimes/`

Solvers must also not depend on those layers at runtime. Reading documented case files is allowed; importing or executing benchmark, experiment, runtime, or other solver internals is not.

## Standalone Principle

Solver code should stay standalone. If similar behavior is needed in another solver, repeat the small amount of code or define a public file format instead of importing another solver's internals.

If shared code is needed later, it should remain layer-local rather than introducing a repository-wide shared abstraction that weakens the benchmark and method boundaries.

## What This Contract Does Not Promise Yet

This document does not yet standardize:

- solver result formats beyond benchmark-owned verifier contracts
- per-language environment management
- cross-solver shared libraries
