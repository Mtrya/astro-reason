# Verifier Exposure

`verifier_exposure` is a focused ablation for relay-network augmentation with
the Codex harness. It varies only what local verifier help the space agent sees
inside the workspace.

The three exposure tiers are:

- `transparent`: readable relay verifier source is assembled into the workspace.
- `opaque`: a runnable opaque verifier artifact is assembled into the workspace.
- `none`: no runnable verifier helper is assembled; the README carries a more
  explicit validation pseudocode description.

Official evaluation always runs outside the agent workspace through the
benchmark-owned relay verifier CLI.

## Run

Preview the default 15-run matrix:

```bash
uv run python experiments/verifier_exposure/run.py --dry-run
```

Run all exposures across all five relay test cases:

```bash
uv run python experiments/verifier_exposure/run.py
```

Filter by exposure or case:

```bash
uv run python experiments/verifier_exposure/run.py \
  --exposure none \
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
results/agent_runs/experiments/verifier_exposure/<config>/<exposure>/relay_constellation/codex/test/<case>/
```

Every run records `exposure`, assembled workspace files, local verifier helper
state, agent status, external verifier status, and parsed verifier results in
`run.json`.
