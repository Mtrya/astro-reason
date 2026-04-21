# Experiment Contract

This document defines the initial public contract for `experiments/`.

The contract is intentionally minimal. It captures the canonical shape needed for the first runnable vertical slice and should not be read as a complete long-term method-layer design.

## Purpose

`experiments/` owns runnable benchmark-facing configurations.

A runnable experiment family defines:

- which benchmark it targets
- which method substrate it runs against
- which benchmark-owned files are copied into the prepared Docker workspace
- which prompts and config files shape the run

In the first vertical slice, that substrate is a runtime. Future experiments may also target a reusable solver instead of a runtime.

Experiments consume benchmarks and method layers such as runtimes or solvers. Benchmarks, runtimes, and solvers must not depend on experiments.

## Required Entry Point

Each experiment lives under:

```text
experiments/<family>/
```

The only stable required artifact for the first slice is an experiment-owned runnable entrypoint:

```text
experiments/<family>/
└── run.py
```

## Recommended Agent-Run Shape

For runtime-backed agent runs, the recommended structure in the first vertical slice is:

```text
experiments/
├── _fragments/
│   ├── prompts/
│   └── configs/
└── <family>/
    ├── run.py
    └── configs/
```

`_fragments/` is a visible shared asset root for reusable prompt and config fragments. It is not a runnable experiment family.

## Family Config

Experiment families may keep one or more runner-owned YAML config files under `configs/`.

In the first slice, those config files commonly describe:

- the benchmark to run
- the runtime to use
- assembly rules that copy prompt/config/case assets into prepared container paths
- collection rules that preserve runtime-owned artifacts after execution
- optional compute and memory limits for the containerized run
- timeout defaults
- headless shell commands

The exact YAML shape is still runner-owned and is not yet standardized as a public repository-wide contract.

## Ownership Boundaries

`run.py` is experiment-owned. It is the canonical runnable entrypoint for the family.

Family-local `configs/` are experiment-owned. They describe concrete runnable configurations for that family.

`_fragments/prompts/` contains reusable prompt and helper fragments such as `README.md`, `AGENTS.md`, and `PROMPT.md`. These are assembled into the prepared workspace at run time.

`_fragments/configs/` contains reusable checked-in config examples and may also contain ignored machine-local real config files.

## Workspace Preparation

Experiments may request that benchmark-owned files be copied into a temporary prepared workspace at run time, including:

- the selected case directory
- the benchmark verifier source
- the benchmark example solution

These files are prepared-at-run-time artifacts, not experiment-owned checked-in assets.

## Execution Notes

For the first slice:

- direct-path execution like `python experiments/.../run.py` is the natural style
- module-style execution may also be allowed
- headless and interactive modes are both in scope
- official verification uses the benchmark-owned verifier outside the container
- the exact family config selection logic is runner-owned for now

## What This Contract Does Not Promise Yet

This document does not yet standardize:

- cross-experiment shared libraries
- batch orchestration interfaces
- solver-backed experiment configs
- stable cross-benchmark verifier result schemas
- non-Docker execution backends
