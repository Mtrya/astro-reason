# AstroReason: Coding Agent Guide

This document guides coding agents working on this repository.

## Project Vision

AstroReason is a monorepo for space mission design benchmarks, reproducible experiments, and first-party method layers.

## Terminology

| Term | Meaning |
|------|---------|
| **Coding agents** | Agents developing this repository |
| **Space agents** | Agents being evaluated on benchmark tasks |

Do not mix these two meanings of "agent" in code or documentation.

## Repository Shape

```text
astro-reason/
├── benchmarks/   # canonical benchmark definitions and benchmark-side tooling
├── experiments/  # reproducible evaluated runs of methods against benchmarks
├── solvers/      # reusable traditional solver implementations
├── runtimes/     # reusable execution substrates for agentic systems
├── scripts/      # repo-owned orchestration and validation entrypoints
├── docs/         # public repository and contract documentation
└── tests/        # focused tests for benchmarks and repository tooling
```

Directory roles:

- `benchmarks/` owns public benchmark definitions, datasets, verifiers, generators, and optional visualizers.
- `experiments/` owns flat runnable experiment families, runner-owned configs, and shared prompt/config fragments under `experiments/_fragments/`.
- `solvers/` owns reusable non-agentic methods and solver-local tooling.
- `runtimes/` owns reusable agent runtime environments, build logic, installation steps, and shared runtime assets.

## Core Rules

1. Keep the benchmark core algorithm-agnostic.
2. Keep every benchmark standalone.
3. Keep top-level modules standalone; prefer executable and file contracts across module boundaries.
4. Preserve reproducibility for both benchmarks and method layers.
5. Keep public repository content understandable to external readers.

## Benchmark Work

When implementing or refactoring a benchmark:

1. Start with the benchmark `README.md`.
2. Treat the verifier as the source of truth for validity and scoring.
3. Keep verifier and generator code standalone, with no imports from other benchmarks or method layers.
4. Update benchmark documentation, verifier behavior, tests, and generator-facing interfaces together when the benchmark contract changes.
5. Add or update focused tests under `tests/benchmarks/`.

Benchmark contract details belong in `docs/benchmark_contract.md` and related public contract docs, not in this guide.

Dataset rules:

- Do not casually modify committed benchmark datasets.
- If a dataset needs redesign or regeneration, prefer benchmark-local generator tooling.
- If generator inputs depend on unstable or external sources, document that clearly in the benchmark README.

## Experiment And Method Work

`experiments/` is the home of runnable evaluated configurations, not reusable method implementations.

Use these ownership boundaries:

- experiments decide what benchmark-facing run is performed
- solvers own reusable traditional method implementations
- runtimes own reusable execution environments for agentic systems
- benchmarks, experiments, solvers, and runtimes should not import internal code from one another

Keep the `experiments/` and `runtimes/` boundary explicit:

- `experiments/` owns prompts, family configs, workspace assembly choices, and run settings
- `runtimes/` owns images, installation/build logic, copied runtime assets, and custom-built agent systems when needed

Prompt and workspace rules for space-agent-facing runs:

- only expose the files needed to solve the current case
- avoid benchmark, evaluation, Docker, harness, or repository-internal leakage in prompts
- do not turn the solving workspace into a mirror of the whole repository

Detailed shapes, entrypoints, and CLI contracts for experiments and methods should live in `docs/*_contract.md`, not in this guide.

## Practical Workflow

- Prefer focused tests over broad test runs when working on one benchmark or tool.
- Prefer readable scripts over opaque one-liners for non-trivial debugging.
- Trace data flow before patching behavior.
- Avoid silent fallbacks or broad exception handling that hides root causes.
- Do not degrade repository design just to fit tooling or sandbox limitations.

## What Not To Do

1. Do not create runtime dependencies between benchmarks.
2. Do not import internal functions, classes, or modules across `benchmarks/`, `experiments/`, `solvers/`, and `runtimes/`; consume benchmark verifiers as executables.
3. Do not casually edit committed datasets by hand when a generator should own the change.
4. Do not leak benchmark or harness internals into space-agent prompts.
5. Do not install packages system-wide for repository work.

## Quick Pointers

- Start benchmark-specific work from the benchmark `README.md`.
- Treat `docs/benchmark_contract.md` as the benchmark-side contract source of truth.
- Put detailed method and experiment contracts in public `docs/*_contract.md` files.
- Keep this guide focused on repository philosophy, ownership boundaries, and working norms.
