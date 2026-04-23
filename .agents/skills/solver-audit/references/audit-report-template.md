# Audit Report Template

## Purpose

Every audit targets a single endpoint:

**faithful reproduction adapted to the benchmark**

The report should explain what prevents that endpoint today, with compute and implementation realism treated as the main issue whenever they are the real bottleneck.

## Priority Order

Write the report in this order:

1. Is the solver being evaluated under a fair compute envelope?
2. What optimization, parallelization, and time-budget work is needed?
3. What literature elements are still partial or missing?
4. Is there any benchmark-validity note worth adding as a short footnote?

Do not center the report on choosing a weaker claim.

## Compute Status Labels

Use one overall compute label in `## Bottom Line`:

### `FAIR_TO_EVALUATE`

The current implementation and runtime budget are good enough to judge the method itself.

### `UNDERPROVISIONED`

The solver may be structurally fine, but the current budget, thread count, or run policy is too small to evaluate it fairly.

### `OPTIMIZATION_BLOCKED`

More time alone is not enough because the implementation is too inefficient or the heavy-search path is not really exercised.

### `BOTH`

The solver is both underprovisioned and held back by implementation or workflow weaknesses.

## Reproduction Labels

Use these only inside `## Reproduction Gaps`:

### `IMPLEMENTED`

The literature element is present closely enough for the target claim.

### `ADAPTED`

The element changed for benchmark reasons but still supports the target claim.

### `PARTIAL`

The element exists in a simplified or weakened form and still needs work before the target claim is earned.

### `MISSING`

The element is absent and blocks the target claim.

### `EXTRA`

The implementation adds logic beyond the reference. This is usually secondary unless it distorts behavior.

## Writing Rules

Use sections, short paragraphs, and bullets. Do not use tables.

Prefer this posture:
- "the target is fixed; here is what blocks it,"
- "this solver is not getting a fair run yet because ...",
- "the dominant execution model is still single-threaded Python, which is itself a major blocker here,"
- "optimize this first, then increase the budget to ...",
- "a planning algorithm should often be given minutes, not forced to complete in 60-120 s,"
- "after that, implement the remaining missing literature pieces."

Avoid this posture:
- "the solver is valid, so the audit is mostly done,"
- "let's weaken the claim to match the implementation,"
- "120 s is enough to judge it" when preprocessing or Python overhead dominates,
- treating compute issues as a minor appendix.

## Report Schema

```markdown
# Solver Audit: <solver-name>

## Bottom Line
- Target claim: faithful reproduction adapted to the benchmark
- Status: <READY / NOT_YET>
- Compute status: <FAIR_TO_EVALUATE / UNDERPROVISIONED / OPTIMIZATION_BLOCKED / BOTH>
- Headline blockers:
  - <highest-impact compute or implementation blocker>
  - <highest-impact remaining method blocker>

## Compute And Runtime

### Literature regime
- <runtime, hardware, multi-run policy, exact subcalls, search depth, etc.>

### Current regime
- <timeout, threads, restart policy, population size, refinement caps, hot-path language choices>

### Execution model
- <single-threaded Python / multiprocessing / threaded native backend / external compiled solver / mixed>
- <say explicitly whether lack of parallelism or native acceleration is a major blocker>

### Runtime profile
- <where time is actually going, if measured>

### Why the current budget is or is not fair
- <clear judgment>

## Optimization And Time Budget

### Bottlenecks
- <what currently dominates runtime>

### What to optimize first
- <parallelization or hot-path implementation work>
- <explicitly name the dominant execution-model issue, e.g. single-threaded Python candidate generation>

### Recommended budget and run policy
- <multi-minute target budget, restart policy, multi-seed policy, or repeated-run guidance>

## Reproduction Gaps

### Implemented and adapted pieces
- <element>: <IMPLEMENTED / ADAPTED> — <why>

### Partial or missing pieces
- <element>: <PARTIAL / MISSING> — <why it still blocks the target claim>

### What must change to reach the target claim
- <concrete algorithmic completion work>

## Action Plan
- <optimization and parallelization work>
- <runtime-budget or run-policy changes>
- <remaining algorithmic completion work>

## Sanity Footnote
- <brief verifier or benchmark-validity note, only if relevant>
```

## Guidance

Good audit language:
- "The dominant execution model is single-threaded Python, and that is a major reason the solver is not getting a fair run."
- "The main problem is not correctness; it is that candidate generation consumes most of a too-small single-thread budget."
- "This needs parallel preprocessing and a longer run budget before the search method can be judged."
- "A realistic target here is several minutes, not an artificially short 60-120 s run."
- "Even with more time, the target claim is still blocked until the missing exact repair stage is implemented."

Bad audit language:
- "Safe claim: ..."
- "Unsafe claim: ..."
- "Benchmark-correct, therefore acceptable."
