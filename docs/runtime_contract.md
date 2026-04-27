# Runtime Contract

This document defines the initial public contract for `runtimes/`.

The contract is intentionally minimal. It captures the canonical Docker-based runtime shape needed for the first runnable vertical slice.

## Purpose

`runtimes/` owns reusable execution substrates for agentic systems.

A runtime defines the environment available to a runnable experiment, including:

- the container image
- how that image is built
- runtime-owned installation logic
- runtime-owned assets needed inside the execution environment

Runtimes are reusable. They do not own benchmark-facing prompts, adapters, or experiment logic.

## Required Shape

Each runtime lives under:

```text
runtimes/<runtime>/
```

The first vertical slice expects:

```text
runtimes/<runtime>/
├── runtime.yaml
└── Dockerfile
```

A runtime-owned helper such as `build.py` is recommended when the runtime needs a local build entrypoint.

## Manifest

`runtime.yaml` must contain:

- `name`
- `image`
- `dockerfile`
- `build_context`

For the first slice, the runtime contract is Docker-only.

## Ownership Boundaries

Runtimes own:

- container build definitions
- installed agent CLIs
- installed shared Python dependencies
- runtime-owned installation and setup logic
- runtime-owned assets needed by multiple runs

Runtimes do not own:

- benchmark definitions
- experiment prompts
- experiment adapters
- experiment-specific benchmark exposure choices

## Runtime Image Expectations

For the first slice, a runtime image may include:

- the primary agent CLI
- benchmark-adjacent Python tooling needed inside the container
- lightweight diagnostic tooling such as shell/debug utilities and a terminal editor

The exact toolset may evolve, but the contract should remain restrained.

## Base Runtime Astrodynamics Tools

The base runtime includes shared astrodynamics tooling that is broadly useful to
solver and experiment workflows:

- Brahe for Python-native orbital dynamics utilities used by benchmark-side and
  solver-side checks.
- Skyfield and scientific Python libraries for lightweight independent orbit and
  geometry analyses.
- Orekit through the `orekit-jpype` Python package. Because Orekit is Java-based,
  the base image installs OpenJDK 17 and sets `JAVA_HOME`.
- Basilisk through the `bsk` Python package as the Python 3.13-compatible
  high-fidelity simulation framework available in this runtime.

`poliastro` is intentionally omitted from the Python 3.13 base image while its
published package metadata requires Python versions below 3.11. If a compatible
release becomes available later, it can be reconsidered as a normal runtime
dependency update.

## What This Contract Does Not Promise Yet

This document does not yet standardize:

- non-Docker runtime backends
- multi-image runtime graphs
- stable shared runtime helper APIs
- long-term packaging conventions beyond the first slice
