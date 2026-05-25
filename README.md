# AstroReason-Bench

**AstroReason-Bench** is a benchmark suite and reproducible experiment harness for
evaluating *agentic* LLM systems on heterogeneous space mission design and
scheduling problems, side by side with traditional solver baselines.

Unlike symbolic or weakly grounded agent benchmarks, every task here is
physics-grounded: instances are built from real satellite orbital elements and
propagation, access geometry, and hard operational constraints. An agent must
read a problem brief, reason about the physics, and produce a solution artifact
that is scored by a standalone, benchmark-owned verifier — the same verifier
used for every method, agentic or classical.

The benchmark core stays algorithm-agnostic: benchmarks define problems,
datasets, and verifiers; methods consume benchmarks and never the reverse.

## Task Families

Seven standalone benchmarks span communication scheduling, agile Earth
observation, imaging geometry, and constellation design:

| Benchmark | Problem |
|---|---|
| `satnet` | Deep Space Network ground-station antenna scheduling: allocate communication tracks under view-period, setup/teardown, exclusivity, and maintenance constraints. |
| `spot5` | SPOT-5 daily photograph selection (ROADEF 2003 / CNES): maximize imaging profit under camera, non-overlap, data-flow, and memory constraints. |
| `aeossp_standard` | Agile Earth-observation satellite scheduling: plan time-stamped observations to maximize weighted task completion under agility and power limits. |
| `stereo_imaging` | Optical same-pass and bounded cross-satellite stereo / tri-stereo acquisition planning over ground targets, with retargeting cost and product-quality scoring. |
| `regional_coverage` | Strip-observation planning over polygonal regions (SAR-like) to maximize unique regional coverage under retargeting and battery feasibility. |
| `revisit_constellation` | Joint constellation design and operating schedule that minimizes target revisit gaps over a mission horizon. |
| `relay_constellation` | Relay-network augmentation and contact-plan design to meet service demand and latency targets with minimal added satellites. |

Each benchmark is self-contained, with its own dataset, generator, verifier, and
(where useful) visualizer. Start from a benchmark's `README.md` for its exact
problem model, solution artifact, and scoring contract.

## How Evaluation Works

- **Agentic harnesses** solve cases inside reproducible container runtimes. A
  space agent receives a problem brief and case files — never benchmark,
  harness, or evaluation internals — and emits a solution artifact.
- **Benchmark-owned verifiers** are the single source of truth for validity and
  scoring. They run outside the agent workspace and are consumed only through
  CLI/file contracts, never source imports.
- **Traditional solvers** provide classical baselines (greedy, local search,
  CP/MILP, and domain methods) under the same verifier.
- **Experiment families** are the reproducible studies that tie these together:
  the main agentic and solver runs plus focused ablations on verifier exposure,
  injected task skills, temporal robustness, and memory accumulation.

## Repository Shape

```text
astro-reason/
├── benchmarks/   # canonical problems, datasets, verifiers, generators, visualizers
├── experiments/  # reproducible evaluated runs of methods and ablations
├── solvers/      # traditional (non-agentic) solver implementations
├── runtimes/     # reusable execution substrates for agentic systems
├── scripts/      # repo-owned orchestration and validation entrypoints
├── docs/         # public contract documentation
└── tests/        # focused benchmark and tooling tests
```

## Design Principles

- **Algorithm-agnostic benchmark core**: `benchmarks/` encodes no preferred solving strategy.
- **One-way contracts**: methods may depend on benchmarks; benchmarks never depend on method code.
- **Standalone everything**: benchmarks, solvers, and runtimes are self-contained and do not import or invoke one another; cross-layer orchestration lives in `experiments/`.
- **Reproducible method layers**: experiments, solvers, and runtimes are runnable and inspectable.
- **Honest agent surface**: agent-facing prompts read like an engineering handoff, with no benchmark, verifier, or harness leakage.

## Getting Started

Benchmark-core development uses [`uv`](https://github.com/astral-sh/uv). Method-owned
directories may use different tooling when justified, as long as benchmark
contracts stay clean.

Useful entry points:

- A benchmark's `README.md` — its problem model and scoring contract.
- `docs/benchmark_contract.md`, `docs/solver_contract.md`, `docs/experiment_contract.md`, `docs/runtime_contract.md` — the public contracts.
- `experiments/main_solver/README.md` and `experiments/main_agentic/README.md` — how to run baseline and agentic evaluations.
- `experiments/{verifier_exposure,skill_injection,temporal_robustness,memory_accumulation}/` — the ablation studies.

Dataset provenance and licensing are documented in `scripts/DATASET_CARD.md`.

## Citation

This repository is anonymized for peer review. Citation details will be added
after the review period.
