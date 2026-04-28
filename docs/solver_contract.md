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

Solver entrypoints must not rely on the repository Python workspace. Contract validation runs `setup.sh`, `solve.sh`, and `test.sh` with Python/workspace leakage scrubbed from the inherited environment. In particular, the validator removes inherited `VIRTUAL_ENV`, `PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE`, other inherited `PYTHON*` variables, uv project-discovery settings such as `UV_PROJECT`, `UV_WORKING_DIR`, `UV_ENV_FILE`, and `UV_CONFIG_FILE`, and repository-local entries from `PATH`. It preserves ordinary system access such as `PATH`, locale, temporary-directory, proxy, certificate, `HOME`, explicit `SOLVER_*` values, and uv package-resolution settings such as `UV_INDEX_URL`, `UV_DEFAULT_INDEX`, `UV_EXTRA_INDEX_URL`, `UV_INDEX_*` per-index credentials, `UV_FIND_LINKS`, `UV_KEYRING_PROVIDER`, `UV_CACHE_DIR`, and runner-managed Python settings. The validator also sets `UV_NO_PROJECT=1`, `UV_NO_CONFIG=1`, and `UV_NO_ENV_FILE=1` so `uv` bootstrap commands do not discover the repository workspace by walking upward from a solver directory.

`uv` may be used as a bootstrap tool, for example `uv venv` or `uv pip install` inside `setup.sh`. Do not use `uv run` in solver entrypoints, because it can implicitly execute against the repository project environment. Python solvers should create or reuse a solver-local virtual environment, write `.solver-env` when helpful, and run `solve.sh` / `test.sh` through `SOLVER_PYTHON` or another solver-owned runtime.

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
- Solver entrypoints run without inherited repository Python environment state.
- Solver entrypoints do not use `uv run` to discover the repository workspace.
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

Experiment profiles own evidence type, verifier commands, result layout, solver-specific configs, and reporting metadata. Do not add experiment metadata such as `evidence_type`, `runnable`, solver paths, verifier commands, or smoke labels to `solvers/finished_solvers.json`.

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
