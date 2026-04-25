# RGT/APC Gap-Constructive Solver

Runnable reproduced-solver scaffold for `revisit_constellation`.

The solver currently parses public `assets.json` and `mission.json` files, builds a deterministic RGT/APC-style candidate satellite library, samples target visibility opportunities, scores those opportunities with benchmark-style midpoint revisit gaps, greedily selects satellites by marginal gap improvement, constructs observation actions using Mercado-style freshness, flexibility, and opportunity-cost priorities, and writes debug artifacts:

```bash
./solvers/revisit_constellation/rgt_apc_gap_constructive/setup.sh
./solvers/revisit_constellation/rgt_apc_gap_constructive/solve.sh \
  benchmarks/revisit_constellation/dataset/cases/test/case_0001 \
  /tmp/empty_config \
  /tmp/revisit_rgt_phase1
```

Outputs:

- `solution.json`: selected `satellites` and constructive `observation` actions
- `status.json`: case metadata, candidate counts, visibility-window counts, selection, scheduling, local validation, repair scores, caps, and timings
- `debug/orbit_candidates.json`: generated candidate states at mission start
- `debug/visibility_windows.json`: sampled candidate-target visibility opportunities
- `debug/selection_rounds.json`: greedy satellite-selection marginal improvements
- `debug/scheduling_decisions.json`: constructive observation decisions and marginal gap improvements
- `debug/scheduling_rejections.json`: skipped options with solver-local reasons
- `debug/local_validation.json`: solver-local hard-validity and high-gap report
- `debug/repair_steps.json`: deterministic insertion/removal repair actions

Later phases tune solver-local repair against official verifier outcomes.

Experiment-owned smoke verification:

```bash
uv run python experiments/main_solver/run.py \
  --benchmark revisit_constellation \
  --solver revisit_constellation_rgt_apc_gap_constructive \
  --case test/case_0001
```
