# Verifier Exposure

`verifier_exposure` is a focused ablation of local verifier help. It varies what local verifier help the space agent sees inside the workspace while holding cases, prompts, runtime image, and official external evaluation fixed within each benchmark.

The default matrix now covers two complementary benchmarks. `stereo_imaging` stresses both orbital access geometry and schedule optimization: the task uses real TLE propagation, target access checks, boresight steering, slew timing, and deterministic stereo and tri-stereo product scoring before any quality-improvement strategy can be trusted. `satnet` is an easier-to-state interval scheduling task: view periods are given directly, but agents must still respect setup/teardown timing, maintenance, antenna exclusivity, arrayed contacts, and fairness-related scoring.

A transparent verifier can help for reasons that an opaque verifier cannot: it demonstrates exact validity and scoring details, and for geometry-heavy tasks it exposes internal routines the agent may call directly instead of reimplementing them from scratch. The opaque tier preserves local feedback, while the `none` tier removes both source guidance and executable feedback.

The three exposure tiers are:

- `transparent`: readable benchmark verifier source is assembled into the workspace.
- `opaque`: a runnable opaque verifier artifact is assembled into the workspace.
- `none`: no runnable verifier helper is assembled.

Official evaluation always runs outside the agent workspace through the benchmark-owned verifier CLI.

The default matrix runs:

- benchmarks: `stereo_imaging`, `satnet`
- split: `test` for both benchmarks
- exposures: `transparent`, `opaque`, `none`
- harnesses: `codex`, `opencode_dpsk`
- stereo cases: `case_0001` through `case_0005`
- SatNet cases: `W10_2018`, `W20_2018`, `W30_2018`, `W40_2018`, `W50_2018`

Interpret summaries primarily by exposure tier, then by harness. A large gap between `transparent` and `opaque` suggests agents benefit from implementation guidance for the underlying access geometry, overlap approximation, and product scoring, not just from validation feedback. A large gap between `opaque` and `none` suggests local checker feedback is important even when verifier source is unavailable. If all tiers remain weak, the bottleneck is more likely the search strategy after the geometry layer is understood.

## Run

Preview the default 40-run matrix:

```bash
uv run python experiments/verifier_exposure/run.py --dry-run
```

Run all configured transparent and none exposures across both benchmarks:

```bash
uv run python experiments/verifier_exposure/run.py
```

Filter by benchmark, exposure, harness, or case:

```bash
uv run python experiments/verifier_exposure/run.py \
  --benchmark satnet \
  --exposure none \
  --harness opencode_dpsk \
  --case W10_2018
```

Prepare one interactive workspace:

```bash
uv run python experiments/verifier_exposure/run.py --interactive
```

Aggregate completed runs:

```bash
uv run python experiments/verifier_exposure/aggregate.py
```

Aggregation also includes `opaque` agent rows from the matching `main_agentic`
runs and solver baseline rows parsed from `experiments/main_solver/README.md`.

Write the markdown report from aggregate artifacts:

```bash
uv run python experiments/verifier_exposure/write_reports.py
```

Plot normalized scores by verifier exposure tier:

```bash
uv run python experiments/verifier_exposure/plot_exposure.py
```

The plotted score uses the shared benchmark-specific normalized score. For
stereo imaging this is `normalized_quality` clipped to `[0, 1]` and reported as
percentage points. For SatNet this is the shared `u_rms`/`u_max` normalized
score. Missing and invalid runs receive score `0`, matching the main-agentic
radar plot convention.

Generate chat-style trace reports:

```bash
uv run python experiments/verifier_exposure/trace_viewer.py
```

## Results

Batch run artifacts live under:

```text
results/agent_runs/experiments/verifier_exposure/<config>/<exposure>/<benchmark>/<harness>/test/<case>/
```

Every run records `exposure`, assembled workspace files, local verifier helper state, agent status, external verifier status, and parsed verifier results in `run.json`.

The `opaque` exposure is read from:

```text
results/agent_runs/experiments/main_agentic/matrix/<benchmark>/<harness>/test/<case>/
```
