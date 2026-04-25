# Verifier Exposure

`verifier_exposure` is a focused ablation for relay-network augmentation. It
varies what local verifier help the space agent sees inside the workspace while
holding the benchmark, cases, prompts, runtime image, and official external
evaluation fixed.

`relay_constellation` is used deliberately because it stresses both physics
implementation and optimization. The task uses J2 propagation from Cartesian
states rather than the more familiar SGP4/TLE workflow, and it requires building
a time-varying relay graph before any routing or augmentation strategy can be
tested.

A transparent verifier can help for reasons that an opaque verifier cannot: it
demonstrates how to use less-common astrodynamics libraries and coordinate
frames, and it exposes internal routines the agent may call directly instead of
reimplementing propagation, frame conversion, and access logic from scratch. The
opaque tier preserves only local feedback, while the `none` tier removes both
source guidance and executable feedback but uses a more explicit problem brief
to avoid turning the ablation into a task-description failure.

The three exposure tiers are:

- `transparent`: readable relay verifier source is assembled into the workspace.
- `opaque`: a runnable opaque verifier artifact is assembled into the workspace.
- `none`: no runnable verifier helper is assembled; the README carries a more
  explicit validation pseudocode description.

Official evaluation always runs outside the agent workspace through the
benchmark-owned relay verifier CLI.

The default matrix runs:

- benchmark: `relay_constellation`
- split: `test`
- exposures: `transparent`, `opaque`, `none`
- harnesses: `codex`, `opencode_dpsk`
- cases: `case_0001` through `case_0005`

Interpret summaries primarily by exposure tier, then by harness. A large gap
between `transparent` and `opaque` suggests agents benefit from implementation
guidance for the underlying orbital mechanics and graph construction, not just
from validation feedback. A large gap between `opaque` and `none` suggests local
checker feedback is important even when verifier source is unavailable. If all
tiers remain weak, the bottleneck is more likely the optimization strategy after
the physics layer is understood.

## Run

Preview the default 30-run matrix:

```bash
uv run python experiments/verifier_exposure/run.py --dry-run
```

Run all exposures and harnesses across all five relay test cases:

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
results/agent_runs/experiments/verifier_exposure/<config>/<exposure>/relay_constellation/<harness>/test/<case>/
```

Every run records `exposure`, assembled workspace files, local verifier helper
state, agent status, external verifier status, and parsed verifier results in
`run.json`.
