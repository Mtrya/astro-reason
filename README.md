# AstroReason-Bench

AstroReason-Bench is a benchmark-core repository for evaluating LLM agents on space mission design and planning problems.

This branch is under active development as we expand the suite with more subtasks and decouple benchmarks from solution implementations. To reproduce the results from the current paper, use the `v1` branch, where benchmarks and solutions are still coupled. A separate solutions repository is planned and will be released in the future.

## Why This Project?

**Aerospace lacks rigorous, standardized, algorithm-agnostic benchmarks.** While AI has ImageNet and GLUE, space mission design still lacks a shared evaluation suite built around well-defined problems and verifiable scoring.

This repository focuses on:

- **Datasets**: Canonical benchmark instances
- **Verifiers**: Standalone validation and scoring logic
- **Reproducibility tools**: Optional benchmark-local generators and visualizers

Any approach can be evaluated: LLM agents, metaheuristics, RL systems, or human experts. This repository defines the benchmark; it does **not** ship solution implementations.

## Repository Structure

```text
astro-reason/
├── benchmarks/{name}/
│   ├── dataset/              # Problem instances
│   ├── verifier.py           # or verifier/run.py
│   ├── visualizer.py         # optional, or visualizer/run.py
│   ├── generator.py          # optional, or generator/run.py
│   └── README.md             # Problem specification and file formats
└── tests/
    └── benchmarks/           # Focused tests for verifiers and benchmark tooling
```

## Benchmark Design Principles

- **Algorithm-agnostic**: Benchmarks define problems and verification, not the method used to solve them.
- **Standalone**: Each benchmark is self-contained with no dependencies on other benchmarks.
- **Reproducible**: Optional generators can recreate or extend datasets when appropriate.
- **Solution-free core**: Solutions and baselines live outside this repository.

## Environment

This project uses `uv` for environment management. To ensure verifier integrity, run:

```bash
uv run pytest tests/benchmarks/test_<name>_verifier.py
```

Run focused tests instead of the full suite unless you specifically need a broader check.

## Status

Current priorities include
- refactoring several newer benchmarks
- reimplementing several existing verifiers, 
- and writing dataset generators for reproducibility.
