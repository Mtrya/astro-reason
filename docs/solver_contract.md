# Solver Contract

This document defines the initial public contract for `solvers/`.

The contract is intentionally light because the first issue-55 PR does not require a serious solver implementation. The immediate goal is to reserve a clear home for traditional methods without weakening benchmark independence.

## Purpose

`solvers/` owns reusable traditional non-agentic methods.

Examples may eventually include:

- heuristic solvers
- optimization-based baselines
- reproducible classical pipelines
- solver-local evaluation helpers

Solvers consume benchmarks. Benchmarks must not depend on solvers.

## Current Expectation

For the first vertical slice:

- `solvers/` needs ownership and documentation scaffolding
- substantial solver implementations are out of scope
- no benchmark contract should assume a solver exists in this directory

## Ownership Boundaries

Solvers may own:

- reusable solver implementations
- solver-local dependencies and environment files
- scripts for running solver outputs against benchmark verifiers

Solvers must not become a shared dependency layer for:

- `benchmarks/`
- `experiments/`
- `runtimes/`

## Standalone Principle

Solver code should stay standalone unless a concrete need proves otherwise.

If shared code is needed later, it should remain layer-local rather than introducing a repository-wide shared abstraction that weakens the benchmark and method boundaries.

## What This Contract Does Not Promise Yet

This document does not yet standardize:

- solver directory layout
- solver manifest schemas
- solver orchestration entrypoints
- solver result formats beyond benchmark-owned verifier contracts
