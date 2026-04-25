---
name: solver-audit
description: Audit a solver against the fixed target of faithful reproduction adapted to the benchmark, prioritizing explicit compute-envelope realism, optimization, and remaining paper-to-code gaps.
---

# Solver Audit

The target claim is fixed: **faithful reproduction adapted to the benchmark with an explicit optimization-and-compute envelope**.

The audit identifies what blocks that target today, especially when the blocker is insufficient computation, weak implementation, or an unfair/runtime-light envelope. A short run or the absence of timeout is not sufficient evidence of fairness.

You focus on three main aspects:
1. whether the code, the control flow is correct,
2. whether the adaptation is benchmark-faithful,
3. whether the optimization, parallelization, and runtime regime is fair for the intended method.

## Priorities

Audit in this order:
1. whether the solver is given a contract/smoke envelope,
2. whether it reaches a meaningful reproduction envelope,
3. whether it is currently in a quality/optimization envelope,
4. what optimization, parallelization, or run-policy work is needed,
5. what literature elements are still partial or missing after benchmark adaptation,
6. benchmark-validity only as a short sanity note if relevant.

## Inputs

Require from user:
- Path to solver implementation
- Solver name
- Benchmark name

Strongly preferred:
- Paper or method reference

If any required input is missing, ask before proceeding.

## Workflow

### Envelope model

Treat envelopes explicitly:

1. **Contract or smoke envelope**
   - Enough for a runnable, standalone solver that is verifier-compatible and CI-safe.
   - Typical checks: command/run completes, status is well-formed, outputs are structurally valid, and no obvious crash path.

2. **Reproduction envelope**
   - Enough to show the method is implemented and adapted faithfully on meaningful benchmark-sized data.
   - Typical checks: representative candidate sizes, constraint modeling behavior, and core algorithm stages are executed.

3. **Quality/optimization envelope**
   - Sufficient search depth, candidate density, restart policy, refinement limits, parallelism, and budget so score reflects method merit instead of configuration poverty.
   - Typical checks: parameter values and policies that materially exercise the planner (candidate caps, sample/grid density, restarts, refinement caps, and time allocation).

Never treat `valid` or `no timeout` as equivalent to quality envelope adequacy.

### 1. Read the target method and benchmark adaptation

If a paper or method reference is available, parse it to Markdown. Use `mineru` if it is available and helpful; otherwise use a local transcript or careful manual reading.

Extract:
- method-defining steps,
- expected search regime,
- expected compute regime,
- benchmark-driven modeling differences.

Read:
- `benchmarks/<benchmark-name>/README.md`

The benchmark read is for adaptation context, not to redefine the target claim.

### 2. Map the implementation and runtime reality

Trace:
- end-to-end control flow,
- implemented vs simplified vs omitted literature elements,
- actual stop conditions,
- execution model: single-threaded, multi-threaded, multi-process, distributed, or native-backed,
- hot-path runtime stack: pure Python, vectorized NumPy, compiled extension, external solver, or mixed,
- where time goes,
- whether the named search method really gets to run.

If practical, run the solver or inspect profiler/status outputs so the audit uses measured runtime splits rather than guesses.
If there is no meaningful parallelism or native acceleration in the hot path, say that explicitly. Prefer precise wording like `single-threaded Python` over softer wording like `pure Python`.

### 3. Judge compute realism first

Answer these questions:
- Does the current run meet at least the contract/smoke envelope?
- Is it in a meaningful reproduction envelope, not just smoke-level verification?
- Is timeout configured for realism, or is it merely an upper bound that does not resolve underpowered method parameters?
- Is there enough parameter space (candidate cap, restart count, refinement depth, etc.) to characterize optimization quality?
- Is the current timeout, thread count, and run policy fair for the target method?
- Is the implementation leaving obvious performance on the table (single-thread hot path, missing vectorization/native acceleration)?
- Would more time materially help right now?
- Or is the solver blocked by missing optimization, missing parallelism, or missing heavy-search components? (very likely)
- Is the time budget long enough for the algorithm to genuinely execute as a planning method, rather than being artificially forced to finish in 60-120 s when a fair evaluation should often allow at least several minutes? (very likely)
- Is the execution model itself a blocker, for example because the dominant stages are still running as single-threaded Python even though they are obviously data-parallel or compute-heavy?

Call out cases like:
- single-threaded Python in candidate generation, graph construction, repair, or other dominant hot paths,
- single-thread Python preprocessing consuming most of the budget,
- literature expecting multi-run or restart-heavy evaluation but implementation using one run,
- very modest candidate caps, seed counts, or iteration limits that keep the method in a tiny-search regime despite available compute headroom,
- one run with a small timeout or tiny settings followed by no schedule to test larger caps/restarts before declaring optimizer behavior blocked,
- exact or refinement phases capped so tightly that the claimed method never really executes,
- short benchmark budgets that only measure setup overhead,
- implementations being shaped around "always finish quickly" instead of using a realistic multi-minute or multi-hour time budget that lets the planning algorithm actually work.

### 4. Assess optimization and time budget

Keep this separate from reproduction gaps.

State clearly:
- what the dominant bottlenecks are,
- what the execution model is today and why it is or is not acceptable,
- what should be parallelized,
- what should be optimized before simply increasing runtime,
- what time budget would be a fair next target after basic optimization,
- whether the method should be evaluated with repeated runs, restarts, or multi-seed regimes instead of a single short run.

The audit should explicitly push back on the common anti-pattern where a planning solver is engineered to complete in 60-120 s even though the intended algorithm family really needs sustained multi-minute or multi-hour search to do its job.

### 5. Assess reproduction gaps against the fixed target

For each method-defining element, classify it as:
- `IMPLEMENTED`
- `ADAPTED`
- `PARTIAL`
- `MISSING`
- `EXTRA`

Use `ADAPTED` only for benchmark-driven changes that still fit the target claim.

The important question is not "what claim is safe?" It is "what still needs to change before this becomes a faithful benchmark-adapted reproduction?"

### 6. Write the report

Use section-based Markdown only. Do not use tables.

Required structure:

```markdown
# Solver Audit: <solver-name>

## Bottom Line
- Target claim: faithful reproduction adapted to the benchmark with explicit optimization-and-compute envelope
- Status: <VALID_REPRODUCED / QUALITY_FAIR_REPRODUCED / NOT_YET>
- Compute status: <FAIR_TO_EVALUATE / UNDERPROVISIONED / OPTIMIZATION_BLOCKED / BOTH>
- Envelope status: <CONTRACT_SMOKE / REPRODUCTION / QUALITY_OPTIMIZATION>
- Headline blockers:

## Compute And Runtime
### Literature regime
### Current regime
### Execution model
### Runtime profile
### Why the current budget is or is not fair

## Optimization And Time Budget
### Bottlenecks
### What to optimize first
### Recommended budget and run policy

## Reproduction Gaps
### Implemented and adapted pieces
### Partial or missing pieces
### What must change to reach the target claim

## Action Plan
- optimization and parallelization work
- runtime-budget or run-policy changes
- remaining algorithmic completion work

## Sanity Footnote
- verifier or benchmark-validity note, only if relevant
```

Bias the report toward an actionable answer to:
- why this solver is or is not getting a fair shot,
- what engineering work would materially improve it,
- what algorithmic work still blocks the target claim.

Do not print the full report to stdout unless the user asks. Save it to `<solver-name>-audit.md` in the current working directory.

## Reference

See [references/audit-report-template.md](references/audit-report-template.md).
