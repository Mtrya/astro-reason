# AstroReason-Bench

A benchmark suite for evaluating LLM agents on space mission planning problems.

## Why This Project?

**Aerospace lacks rigorous, standardized, algorithm-agnostic benchmarks.** While AI has ImageNet and GLUE, space mission planning has no standardized evaluation suite. This project fills that gap with:

- **Datasets**: Well-defined problem instances
- **Verifiers**: Standalone scoring logic, independent of solution method
- **Baselines**: Reference implementations to establish performance floors

Any approach can be evaluated — LLM agents, metaheuristics, RL, or human experts.

## Repository Structure

```
astro-reason/
├── benchmarks/{name}/   # Each benchmark is standalone
│   ├── dataset/         # Problem instances
│   ├── verifier.py      # Validation + scoring
│   ├── baselines/       # Optional reference implementations
│   └── README.md        # Problem specification
├── skills/              # Teaching materials for space agents
│   ├── libraries/       # How to use brahe, tudatpy, basilisk
│   └── problems/        # Problem-solving patterns
└── tests/               # Test suites mirroring source structure
```

## Roadmap

| Phase | Focus | Examples |
|-------|-------|----------|
| 1 | Legacy benchmarks | spot5 ✅, satnet, aeosbench |
| 2 | LEO constellation (6DOF) | revisit gaps, relay networks, imaging & cartography |
| 3 | Deep space (3DOF) | interplanetary, small body rendezvous |
| 4 | Rocket trajectories | ascent, descent, reentry *(pending library)* |

## Environment

Uses `pixi` for dependency management (supports Python, Rust, C++ verifiers).

```bash
pixi shell        # Activate environment
pytest tests/...  # Run tests
```
