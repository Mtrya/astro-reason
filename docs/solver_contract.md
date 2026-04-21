# Solver Contract

This document defines the initial public contract for `solvers/`.

The contract is intentionally light. It gives experiments a stable way to call
traditional methods without forcing every solver into the same language,
package manager, or runtime model.

## Purpose

`solvers/` owns reusable traditional non-agentic methods.

Examples may eventually include:

- heuristic solvers
- optimization-based baselines
- reproducible classical pipelines
- solver-local evaluation helpers

Solvers consume benchmarks. Benchmarks must not depend on solvers.

Solvers should treat benchmark verifiers as executable contracts. They should
not import benchmark-internal functions, classes, or modules.

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

`finished_solvers.json` is the repository-level registry for solvers that are
ready to be used by experiments or discussed in reports.

## Runnable Solver Contract

Runnable solvers expose two shell entrypoints:

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` prepares solver-local dependencies. It may be a no-op.

`solve.sh` receives:

- `case_dir`: required benchmark case directory
- `config_dir`: optional experiment-owned config directory
- `solution_dir`: optional directory where solution artifacts should be written

Experiments should usually pass both optional arguments explicitly. The solver
should write its primary solution artifact into `solution_dir` and exit nonzero
for unsupported cases or execution failures.

Solver code may be Python, shell, C++, Julia, MiniZinc, or anything else. The
shell entrypoints are the boundary.

## Evidence Types

The initial registry distinguishes:

- `reproduced_solver`: a runnable solver produces a solution for a case
- `fixture_backed_lookup`: a runnable lookup emits a known reference solution
- `transitional_literature`: documented metrics without a runnable solver

Fixture-backed lookups and transitional literature entries must be labeled as
such in reports. They are useful baselines, but they are not general solver
claims.

## Ownership Boundaries

Solvers may own:

- reusable solver implementations
- solver-local dependencies and environment files
- scripts for running solver outputs against benchmark verifiers
- solver-owned assets needed by the method, with provenance documented

Solvers must not become a shared dependency layer for:

- `benchmarks/`
- `experiments/`
- `runtimes/`

## Standalone Principle

Solver code should stay standalone unless a concrete need proves otherwise.

If shared code is needed later, it should remain layer-local rather than introducing a repository-wide shared abstraction that weakens the benchmark and method boundaries.

## What This Contract Does Not Promise Yet

This document does not yet standardize:

- solver result formats beyond benchmark-owned verifier contracts
- per-language environment management
- cross-solver shared libraries
