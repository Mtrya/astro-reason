# Solver Contract

This document defines the public contract for `solvers/`.

The contract gives experiments a stable way to call traditional non-agentic methods without forcing every solver into the same language, package manager, or runtime model.

## Purpose

`solvers/` owns reusable traditional non-agentic methods.

Examples include:

- heuristic solvers
- optimization-based baselines
- reproducible classical pipelines
- fixture-backed lookup baselines
- citation-backed literature baselines

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
        ├── setup.sh          # required when repro_ci is true
        ├── solve.sh          # required when repro_ci is true
        ├── test.sh           # optional solver-local test entrypoint
        ├── src/              # optional
        ├── tests/            # optional solver-local tests
        └── assets/           # optional
```

The path for a registered solver is derived from the registry fields: `solvers/<benchmark>/<solver>/`. The registry does not carry a separate `path` field.

## Runnable Solver Contract

Runnable solvers expose two shell entrypoints:

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` prepares solver-local dependencies, build artifacts, or runtime state. It may be a no-op.

`solve.sh` receives:

- `case_dir`: required benchmark case directory
- `config_dir`: optional experiment-owned config directory
- `solution_dir`: optional directory where solution artifacts should be written

Experiments should usually pass both optional arguments explicitly. The solver should write its primary solution artifact into `solution_dir` and exit nonzero for unsupported cases or execution failures.

Solver code may be Python, shell, C, C++, Java, Kotlin, Julia, MiniZinc, Rust, or anything else. The shell entrypoints are the boundary.

## Setup Outputs

`setup.sh` may create or update solver-local outputs such as:

- Python virtual environments under `.venv/`
- a `.solver-env` file with simple `SOLVER_*=` assignments
- C/C++ build directories and binaries
- Rust `target/` artifacts and Cargo-managed dependencies
- Java/Kotlin jars and Gradle/Maven outputs
- Julia depots or instantiated project environments
- MiniZinc model-local backends or availability checks

Generated setup outputs should stay solver-local and be ignored when they are machine-specific or reproducible build products.

`.solver-env` is a convention, not a CI-enforced requirement. When present, it should be a simple handoff file for values such as:

```text
SOLVER_VENV_DIR=/abs/path/to/.venv
SOLVER_PYTHON=/abs/path/to/.venv/bin/python
```

Experiment runners may read this file and pass `SOLVER_*` values into `solve.sh`, but solvers should still be directly runnable after `setup.sh`.

## Solver-Local Tests

`test.sh` is the optional solver-local test boundary.

It may run any language-native test command, including `pytest`, `cargo test`, `ctest`, `mvn test`, `gradle test`, or Julia test runners. Test-only dependencies should be installed by the solver-local test flow or already be available in the solver's chosen environment.

Top-level pytest must not collect solver-local tests. Repository-wide pytest is for benchmark and repository tooling tests. Solver tests should live under the solver directory and be reached through `test.sh`.

## CI-Enforced Invariants

`scripts/validate_solver_contract.py` enforces repository-wide invariants:

- `solvers/finished_solvers.json` has the documented schema.
- Each registry entry resolves to `solvers/<benchmark>/<solver>/`.
- Each registered solver has `README.md`.
- `repro_ci: true` entries have executable `setup.sh` and `solve.sh`.
- `repro_ci: true` entries declare at least one case path.
- Declared case paths and non-empty fixture paths exist.
- Existing `test.sh` files are executable.
- Top-level pytest is scoped away from solver-local tests.
- Solver runtime code does not import or execute across `benchmarks/`, `experiments/`, `runtimes/`, or other solvers.
- `repro_ci: true` entries run `setup.sh` and `solve.sh` on their declared cases.
- Detected solver-local `test.sh` entrypoints run as part of solver contract validation.

CI enforces boundaries and discoverability. It does not enforce a language, package manager, build system, or internal source layout.

## Finished Solver Registry

`solvers/finished_solvers.json` is a reproducibility and CI registry. It is not the evidence/reporting registry for experiments.

Each entry has:

```json
{
  "benchmark": "aeossp_standard",
  "solver": "greedy_lns",
  "repro_ci": false,
  "repro_ci_reason": "too_expensive",
  "case_and_fixture_paths": []
}
```

For `repro_ci: true`, `case_and_fixture_paths` contains objects:

```json
{
  "case_path": "benchmarks/spot5/dataset/cases/test/8",
  "fixture_path": "solvers/spot5/reference_lookup/assets/solutions/8.spot_sol.txt"
}
```

`fixture_path` may be an empty string when CI should only run setup/solve and not compare against a fixed output fixture.

`repro_ci_reason` is recommended when `repro_ci` is false, but it is not enforced by CI. Useful values include:

- `citation_based`
- `too_expensive`
- `requires_external_toolchain`
- `requires_external_data`
- `not_reproducible_yet`

Experiment profiles own evidence type, verifier commands, result layout, solver-specific configs, and reporting metadata.

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
