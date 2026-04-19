# AstroReason-Bench

AstroReason-Bench is evolving into a monorepo for space mission design benchmarks and first-party method layers.

The benchmark core remains algorithm-agnostic: benchmarks define problems, datasets, and verifiers; methods consume benchmarks and never the reverse.

For historical paper reproduction, use the `v1` branch.

## Repository Shape

```text
astro-reason/
├── benchmarks/   # canonical problems, datasets, verifiers, generators
├── experiments/  # reproducible evaluated runs of methods
├── solvers/      # traditional solver implementations
├── runtimes/     # reusable execution substrates for agentic systems
├── scripts/      # repo-owned orchestration and validation entrypoints
└── tests/        # focused benchmark and tooling tests
```

## Design Principles

- **Algorithm-agnostic benchmark core**: `benchmarks/` does not encode preferred solving strategies.
- **One-way contracts**: methods may depend on benchmarks; benchmarks must not depend on method code.
- **Standalone benchmarks**: each benchmark remains self-contained.
- **Reproducible method layers**: experiments, solvers, and runtimes should be runnable and inspectable.

## Directory Roles

- `benchmarks/` owns public benchmark definitions and benchmark-side tooling.
- `experiments/` owns flat runnable experiment families and shared prompt/config fragments.
- `solvers/` owns traditional non-agentic solver methods.
- `runtimes/` owns reusable agent runtime environments, build logic, and shared runtime assets.

## Environment

Benchmark-core development uses `uv`:

```bash
uv run pytest tests/benchmarks
```

Method-owned directories may use different tooling when justified, as long as benchmark contracts stay clean.

## Status

Current work is focused on:

- refining benchmark definitions and verifier contracts
- migrating the initial solver/harness scaffolding into this repository
