# Experiment Contract

This document defines the initial public contract for `experiments/`.

The contract is intentionally minimal. It captures the canonical shape needed for the first runnable vertical slice and should not be read as a complete long-term method-layer design.

## Purpose

`experiments/` owns runnable benchmark-facing configurations.

An experiment defines:

- which benchmark it targets
- which method substrate it runs against
- which benchmark-owned files are copied into the prepared Docker workspace
- which prompts, adapters, and config files shape the run

In the first vertical slice, that substrate is a runtime. Future experiments may also target a reusable solver instead of a runtime.

Experiments consume benchmarks and method layers such as runtimes or solvers. Benchmarks, runtimes, and solvers must not depend on experiments.

## Required Entry Point

Each experiment lives under:

```text
experiments/<benchmark>/<experiment>/
```

The only stable required artifact for the first slice is an experiment-owned runnable entrypoint:

```text
experiments/<benchmark>/<experiment>/
└── run.py
```

## Recommended Agent-Run Shape

For runtime-backed agent runs, the recommended structure in the first vertical slice is:

```text
experiments/<benchmark>/<experiment>/
├── experiment.yaml
├── run.py
├── adapter.py
├── workspace/
└── config/
```

## Manifest

For runtime-backed agent runs, `experiment.yaml` is the recommended manifest file.

When present in the first slice, it should contain:

- `name`
- `benchmark`
- `runtime`
- `required_config_files`

For the first slice, `runtime` is the recommended substrate field for agent runs.

An experiment may also declare runtime-specific extras such as additional Python requirements, but those are optional. Shared benchmark-adjacent Python tooling may instead live directly in the runtime image.

Future experiment variants may use a solver-backed contract instead, but that is not standardized by this first document.

Likely optional fields include:

- `include_example_solution`
- `include_verifier`
- `timeout_seconds_default`
- `task_prompt_file`

## Ownership Boundaries

`run.py` is experiment-owned. It is the canonical runnable entrypoint for the experiment.

`adapter.py` is experiment-owned. In the first slice, it defines the experiment-specific bridge to the selected runtime and agent CLI.

`workspace/` contains experiment-authored prompt and helper files. It does not contain benchmark-owned case data or checked-in verifier copies.

`config/` contains experiment-local config examples and expected config filenames.

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

## What This Contract Does Not Promise Yet

This document does not yet standardize:

- cross-experiment shared libraries
- batch orchestration interfaces
- solver-backed experiment manifests
- stable cross-benchmark verifier result schemas
- non-Docker execution backends
