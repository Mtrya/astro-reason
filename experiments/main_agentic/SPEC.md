# Main Agentic Experiment Spec

This document guides the first implementation of issue `#57`, the main agentic evaluation matrix across the current finished benchmark set.

The goal of this spec is to lock the family layout and the main execution model before we implement batch planning, harness integration, and aggregation.

This spec is intentionally temporary. Once the family shape stabilizes, the durable parts of this document should be absorbed into `experiments/main_agentic/README.md`.

The purpose of Phase 0 is not to finish the family. It is to make later implementation and prompt-writing phases depend on explicit decisions rather than on drift or guesswork.

## Goal

Build one experiment family under `experiments/main_agentic/` that can:

- run the canonical benchmark x harness matrix in batch by default
- support a separate interactive debugging config
- write stable run artifacts for every benchmark/harness/case combination
- aggregate run artifacts into reviewable benchmark-level and matrix-level summaries

This family should encode the stable benchmark-facing and harness-facing structure. Exact provider or model choices stay machine-local and are not the tracked contract.

## Decisions Locked In Phase 0

The following decisions are considered settled unless a later phase finds a concrete implementation blocker:

- `experiments/main_agentic/` is one flat experiment family rather than a benchmark-nested subtree.
- `_fragments/prompts/<benchmark>/README.<variant>.md` and `PROMPT.<variant>.md` are benchmark-specific reusable prompt fragments.
- `README.md` and `PROMPT.md` should vary benchmark-by-benchmark; `AGENTS.md` should stay shared across benchmarks unless a later phase finds a real need for benchmark-specific variants.
- `run.py` is the main execution entrypoint, batch by default.
- `aggregate.py` is the main aggregation entrypoint.
- `plan.py` is the planning and matrix-expansion entrypoint.
- `matrix.yaml` is the canonical batch config.
- `interactive.yaml` is the canonical interactive debugging config.
- `interactive.yaml` should target one benchmark and one case while including all harnesses for easier debugging.
- run artifacts stay artifact-first, with one stable `run.json` per concrete run.
- the family should support both verifier directory/module layouts and single-file verifier layouts.
- concrete case enumeration should come from committed dataset directories rather than from inventing a new split schema.

## Canonical Axes

The tracked implementation treats these as the primary axes:

- benchmarks
- harnesses
- benchmark-facing prompt fragments

The underlying model names are intentionally not part of the tracked family shape. They belong in untracked local harness configs such as `opencode.json`, `config.local.yaml`, or similar machine-local files.

## Current Scaffold Status

The scaffold already contains useful structure, but not all files carry the same level of commitment.

### Considered structurally real now

- `experiments/main_agentic/run.py`
- `experiments/main_agentic/plan.py`
- `experiments/main_agentic/aggregate.py`
- `experiments/main_agentic/configs/matrix.yaml`
- `experiments/main_agentic/configs/interactive.yaml`
- benchmark profile files under `experiments/main_agentic/benchmarks/`
- harness profile files under `experiments/main_agentic/harnesses/`
- benchmark-specific prompt-fragment roots under `experiments/_fragments/prompts/`

### Considered provisional now

- the exact YAML schema of `matrix.yaml`
- the exact YAML schema of `interactive.yaml`
- the exact YAML schema of benchmark profiles
- the exact YAML schema of harness profiles
- the final helper-module decomposition beyond `run.py`, `plan.py`, and `aggregate.py`
- benchmark-specific aggregation normalization fields
- all non-OpenCode harness command/config details
- the actual benchmark-facing prompt contents

The family should treat these files as family-owned implementation scaffolding, not as public repository-wide contracts yet.

## Family Layout

The family layout is:

```text
experiments/
├── _fragments/
│   ├── prompts/
│   │   ├── aeossp_standard/
│   │   ├── regional_coverage/
│   │   ├── relay_constellation/
│   │   ├── revisit_constellation/
│   │   ├── satnet/
│   │   ├── spot5/
│   │   └── stereo_imaging/
│   └── configs/
└── main_agentic/
    ├── run.py
    ├── plan.py
    ├── aggregate.py
    ├── configs/
    │   ├── matrix.yaml
    │   └── interactive.yaml
    ├── benchmarks/
    ├── harnesses/
    └── SPEC.md
```

## Role Of Each File Group

### `configs/`

`matrix.yaml` is the canonical batch config for the main matrix run.

It owns:

- the frozen benchmark list
- the frozen harness list
- batch defaults such as batch size, concurrency, and retries
- family-wide resource defaults
- result-root defaults

For the current scaffold, `matrix.yaml` is expected to remain runner-owned. It is a family implementation config, not a public cross-family experiment contract.

`interactive.yaml` is the canonical interactive debugging config.

It owns:

- one benchmark
- all harnesses
- one split and case
- interactive resource and timeout defaults

For the current scaffold, `interactive.yaml` is intended to help local debugging and harness comparison. It is not meant to imply that all future experiment families should follow the same interactive config shape.

### `benchmarks/`

Each benchmark profile owns benchmark-specific run shape:

- which prompt fragments to use
- how the workspace should assemble case and verifier files
- whether the verifier is a module directory or a single file
- any benchmark-specific aggregation normalization that later needs to be defined

Benchmark profiles should stay benchmark-specific rather than family-specific. The same prompt fragments and benchmark assembly rules should be reusable by later ablation families when appropriate.

For Phase 0, benchmark profiles should be read as structurally useful placeholders. Their prompt paths and workspace assembly roots are meaningful now, while their aggregation metadata is still intentionally incomplete.

### `harnesses/`

Each harness profile owns harness-specific run shape:

- runtime choice
- local real-config location
- tracked example-config location when known
- headless command definition
- interactive command definition
- artifact collection rules

The important design rule is:

- tracked files describe harness behavior and workspace assembly
- untracked local files describe provider/model/account details

For Phase 0, only the OpenCode harness profile should be treated as a partial working reference. The other harness profiles are explicit placeholders to be hardened in Phase 4.

### `_fragments/prompts/`

Prompt fragments are benchmark-specific and variant-specific.

The intended naming style is:

- `README.default.md`
- `PROMPT.default.md`
- future variants like `README.no_verifier.md`, `PROMPT.skill_brahe.md`, and similar

This makes them reusable across `main_agentic` and later ablation families.

`AGENTS.md` does not need to vary benchmark-by-benchmark unless we later discover a real need. The current expectation is that `main_agentic` can use one shared agent-facing `AGENTS.md` fragment across benchmarks while keeping `README.md` and `PROMPT.md` benchmark-specific.

## Prompt Contract

Phase 1 locks the role split between workspace-facing prompt files strongly enough that later prompt-writing phases should not improvise a different model.

### `README.md`

`README.md` is the orientation layer.

It should answer:

- what problem this workspace contains
- what the expected solution artifact is
- what a good solution should achieve in practical terms
- what files are available in the prepared workspace
- what file or directory contains the case data
- whether an example solution is present
- whether a workspace verifier helper is present for local iteration
- any benchmark-specific success-shape reminders that help the agent start correctly

`README.md` should not try to reproduce the full public benchmark README. It should condense only the problem information that is useful at solve time inside the prepared workspace.

`README.md` should also avoid:

- explicit benchmark framing
- explicit split framing
- harness details
- Docker details
- repository-internal workflow notes
- evaluation-matrix context
- score or leaderboard language
- testing or interview language
- long-form methodological exposition

### `PROMPT.md`

`PROMPT.md` is the immediate task instruction.

It should answer:

- what the agent should do now
- what the final required deliverable is
- what a minimal good next step is
- what problem-specific priorities or cautions deserve emphasis right at execution time

`PROMPT.md` should be shorter and more action-oriented than `README.md`.

The intended tone is straightforward task assignment, like handing a concrete case to an engineer and asking them to solve it with the provided materials.

`PROMPT.md` may include:

- a concise statement of the task
- output reminders
- brief problem-specific cautions

`PROMPT.md` should not duplicate the whole workspace inventory from `README.md`, and it should not contain family-generic working rules that belong in shared `AGENTS.md`.

`PROMPT.md` should also avoid:

- language about being tested or benchmarked
- language about scores or leaderboards
- long procedural instructions that belong in `README.md`

### Shared `AGENTS.md`

Shared `AGENTS.md` is the stable working-style layer for the space agent.

It should encode benchmark-neutral rules such as:

- stay within the prepared workspace
- keep helper scripts and notes inside the workspace
- treat `solution.json` as the required final deliverable unless the workspace says otherwise
- use scripts or direct case-specific work as appropriate for the task
- use any exposed verifier helper for local iteration when it helps

Shared `AGENTS.md` should not contain:

- benchmark-specific domain content
- benchmark-specific file inventories
- harness-specific instructions
- matrix-level evaluation context

If a later phase discovers a benchmark that truly needs benchmark-specific `AGENTS.md`, that should be treated as an exception to justify explicitly rather than as the default model.

### Tone And Information Density

The intended style for all three files is:

- operational
- technically clear
- workspace-local
- natural for a real engineering handoff
- free of internal evaluation leakage

`README.md` may be comprehensive if that helps the agent understand the task correctly.

`PROMPT.md` and shared `AGENTS.md` should both stay thin.

The workspace should feel like a well-prepared task handoff, not a benchmark package and not an interview.

### Shared Placeholder Set

Phase 1 also locks the placeholder vocabulary that later prompt-writing phases may rely on in rendered prompt fragments.

The current shared placeholder set should stay minimal and should avoid evaluation-framing fields when possible.

The current preferred shared placeholder set is:

- `{example_solution_name}`
- `{verifier_location}`
- `{verifier_command}`

Later phases may add new placeholders if they are clearly reusable across multiple benchmark prompts, but they should avoid inventing benchmark-specific one-off placeholders unless that is clearly worth the extra rendering complexity.

### Prompt-Writing Checklist

Later benchmark prompt-writing phases should follow this checklist:

1. `README.md` should orient the agent to the prepared workspace, not to the repository.
2. `README.md` should describe the problem and expected solution without saying “benchmark”, “split”, or similar evaluation framing.
3. `PROMPT.md` should make the task and final deliverable obvious in a concise, task-assignment tone.
4. Shared `AGENTS.md` should carry only generic work rules instead of duplicating them in every benchmark prompt.
5. Benchmark-facing files should avoid harness, Docker, and evaluation-matrix leakage.
6. Benchmark-facing files should not assume access to repository files outside the prepared workspace.
7. Use problem-specific reminders only when they materially help the agent avoid a common wrong start.
8. Prefer concrete output-shape reminders over long background exposition.
9. Do not over-prescribe a scripted solve loop; reusable scripts and one-off case-specific work can both be appropriate.
10. Keep prompt fragments reusable across `main_agentic` and likely ablation families.

## Execution Model

The main execution entrypoint is `run.py`.

The default user flow should be:

```text
python experiments/main_agentic/run.py
```

That default should mean: expand `configs/matrix.yaml` and execute the batch matrix.

Interactive debugging should be:

```text
python experiments/main_agentic/run.py --interactive
```

That default should mean: use `configs/interactive.yaml`.

Aggregation should be separate:

```text
python experiments/main_agentic/aggregate.py
```

The family may also use `plan.py` to expand matrix configs into concrete benchmark/harness/case runs and to support dry-run planning, filtering, ordering, and retry decisions.

For Phase 0, the existence of `run.py`, `plan.py`, and `aggregate.py` is a locked structural decision. Their internal helper decomposition remains open.

## Current Placeholder Inventory

The following are deliberately unresolved and should not be mistaken for finished contracts:

- placeholder harness command values such as `__TODO__`
- missing tracked example-config files for non-OpenCode harnesses
- benchmark aggregation sections that only identify verifier layout but not score extraction
- starter prompt fragments whose contents are still intentionally light
- the absence of a durable `experiments/main_agentic/README.md`

## Why The Family Is Split This Way

The benchmark axis and the harness axis have different sources of complexity.

Benchmark profiles vary by:

- prompt defaults
- workspace assembly
- verifier layout
- aggregation normalization

Harness profiles vary by:

- config schema and mount location
- CLI command shape
- auth expectations
- log/session artifact locations

Trying to encode both axes in one large config would make the family harder to extend and harder to review.

## Known Challenges That Shape The Implementation

### 1. Harness config schema drift

This is likely the biggest engineering challenge in the main matrix.

Different harnesses may need:

- different config file names
- different config file directories
- different environment variables
- different interactive behaviors
- different session-log collection rules
- different headless command forms

This is why harness profiles are first-class files, not just fields in one matrix config.

### 2. Batch execution policy

The family needs batch execution from the start, not as a later add-on.

That means we need:

- stable result paths
- skip-if-complete behavior
- retry-on-failure behavior
- bounded concurrency
- benchmark and harness filtering for debugging

`matrix.yaml` should own the default batch size and retry policy.

For the current family, these fields should be interpreted as:

- `batch.batch_size`: the default maximum number of concrete run items selected in one batch invocation unless later filters shrink the set first
- `batch.max_concurrency`: the default maximum number of concrete run items executed concurrently
- `batch.max_retries`: the default retry count for eligible non-success outcomes
- `batch.skip_completed`: whether concrete runs with already acceptable artifacts should be skipped by default

### 3. Split and case enumeration are not uniform across benchmarks

The seven benchmarks do not all expose the same split semantics.

Some expose explicit split lists like `satnet` and `spot5`, while others use seeded split metadata and committed case directories.

For the first pass, the implementation should enumerate concrete cases from committed dataset directories rather than forcing a new shared split schema.

### 4. Verifier entrypoints are not uniform

Current benchmark verifier shapes already differ:

- directory/module style: `aeossp_standard`, `relay_constellation`, `revisit_constellation`, `stereo_imaging`
- single-file style: `regional_coverage`, `satnet`, `spot5`

The family runner must support both verifier layouts cleanly.

### 5. Aggregation schemas are not uniform

The top-level verifier JSON shape is not identical across benchmarks.

So aggregation should not assume one universal score key. Instead:

- `run.json` remains the stable artifact contract
- benchmark profiles should later define how to extract primary scores and supporting metrics from verifier output

### 6. Prompt defaults are benchmark-specific

Issue `#57` explicitly includes writing per-benchmark default `README.md` and `PROMPT.md`.

Those should be benchmark-specific reusable fragments, not files nested under the family itself.

## Result Shape

The implementation should preserve the current artifact-first philosophy:

- one concrete run writes a stable `run.json`
- aggregation reads run artifacts rather than raw logs

The intended result root for this family is:

```text
results/agent_runs/experiments/main_agentic/
```

Phase 0 locks the intended nested shape strongly enough that later phases should not invent alternatives casually:

```text
results/agent_runs/experiments/main_agentic/<config>/<benchmark>/<harness>/<split>/<case>/
```

The summary root should live under the family result root, for example:

```text
results/agent_runs/experiments/main_agentic/<config>/summaries/
```

Interactive workspaces should mirror the same identifying dimensions under:

```text
.runtime/interactive_workspaces/experiments/main_agentic/<config>/<benchmark>/<harness>/<split>/<case>/
```

These path conventions are still family-owned, but they are locked strongly enough for later phases to build against them.

## Immediate Implementation Scope

The next implementation pass should focus on:

1. matrix expansion and planning
2. batch execution for concrete benchmark/harness/case items
3. stable result-path layout
4. aggregation from run artifacts
5. the first real harness beyond the current `opencode` prototype path

The next pass should not try to settle every future ablation contract.

## What Is Intentionally Deferred

This spec does not yet settle:

- the final cross-family shared Python helper layout
- the final benchmark-score normalization schema
- the complete tracked example-config set for every harness
- prompt ablation variants
- no-verifier and skill-accumulation workflows

Those belong in later issues once the main matrix family is real.

## Phase 0 Exit Condition For This Spec

This spec is hardened enough for later phases when:

- later phases can tell which decisions are already locked and which are still provisional
- prompt phases can write benchmark-facing fragments without reopening family structure
- harness phases can harden profiles without guessing result paths or execution ownership
- runner phases can implement batch and interactive paths without inventing a new directory model
