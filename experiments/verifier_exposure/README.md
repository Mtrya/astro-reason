# Verifier Exposure

`verifier_exposure` is a focused ablation for stereo-imaging scheduling. It varies what local verifier help the space agent sees inside the workspace while holding the benchmark, cases, prompts, runtime image, and official external evaluation fixed.

`stereo_imaging` is used deliberately because it stresses both orbital access geometry and schedule optimization. The task uses real TLE propagation, target access checks, boresight steering, slew timing, and deterministic stereo and tri-stereo product scoring before any quality-improvement strategy can be trusted.

A transparent verifier can help for reasons that an opaque verifier cannot: it demonstrates how to use the exact astrodynamics, access, footprint-overlap, and quality-scoring routines, and it exposes internal routines the agent may call directly instead of reimplementing geometry from scratch. The opaque tier preserves only local feedback, while the `none` tier removes both source guidance and executable feedback but uses a more explicit problem brief to avoid turning the ablation into a task-description failure.

The three exposure tiers are:

- `transparent`: readable stereo verifier source is assembled into the workspace.
- `opaque`: a runnable opaque verifier artifact is assembled into the workspace.
- `none`: no runnable verifier helper is assembled; the README carries a more explicit validation pseudocode description.

Official evaluation always runs outside the agent workspace through the benchmark-owned stereo verifier CLI.

The default matrix runs:

- benchmark: `stereo_imaging`
- split: `test`
- exposures: `transparent`, `opaque`, `none`
- harnesses: `codex`, `opencode_dpsk`
- cases: `case_0001` through `case_0005`

Interpret summaries primarily by exposure tier, then by harness. A large gap between `transparent` and `opaque` suggests agents benefit from implementation guidance for the underlying access geometry, overlap approximation, and product scoring, not just from validation feedback. A large gap between `opaque` and `none` suggests local checker feedback is important even when verifier source is unavailable. If all tiers remain weak, the bottleneck is more likely the search strategy after the geometry layer is understood.

## Run

Preview the default 30-run matrix:

```bash
uv run python experiments/verifier_exposure/run.py --dry-run
```

Run all exposures and harnesses across all five stereo-imaging test cases:

```bash
uv run python experiments/verifier_exposure/run.py
```

Filter by exposure, harness, or case:

```bash
uv run python experiments/verifier_exposure/run.py \
  --exposure none \
  --harness opencode_dpsk \
  --case case_0001
```

Prepare one interactive workspace:

```bash
uv run python experiments/verifier_exposure/run.py --interactive
```

Aggregate completed runs:

```bash
uv run python experiments/verifier_exposure/aggregate.py
```

## Results

Batch run artifacts live under:

```text
results/agent_runs/experiments/verifier_exposure/<config>/<exposure>/stereo_imaging/<harness>/test/<case>/
```

Every run records `exposure`, assembled workspace files, local verifier helper state, agent status, external verifier status, and parsed verifier results in `run.json`.
