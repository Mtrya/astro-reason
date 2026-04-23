---
name: solver-audit
description: Audit whether a solver implementation is valid, correctly implements its claimed method, and is reasonably configured for the benchmark. Use when: (1) validating solver correctness against a research paper or documented method, (2) checking benchmark contract compliance, (3) reviewing whether timeouts and resource limits are realistic for the claimed approach, (4) verifying algorithmic reproduction correctness without penalizing unoptimized implementations, (5) reviewing solver pull requests.
---

# Solver Audit

Audit a solver implementation for correctness, benchmark contract compliance, and reasonable configuration. Paper comparison is one input to the audit, not the sole criterion. An unoptimized or slow implementation of a correct algorithm is not automatically a failure.

## Inputs

Require from user:
- Path to solver implementation (file or directory)
- Solver name (e.g., "satnet-milp")
- Paper or method reference (PDF path, URL, arXiv ID, DOI, local file, or design doc) — optional but recommended
- Benchmark name (to locate benchmark contract)

If any required input is missing, ask before proceeding.

## Workflow

### 1. Parse reference (if provided)

If a paper or method reference is available, use the `mineru` skill to parse it to Markdown.


Read the resulting Markdown file.

### 2. Extract method specification

Search the parsed reference for the algorithm description:
- Look for sections containing: `Algorithm`, `pseudocode`, `Procedure`, `Method`, `Approach`
- If explicit numbered steps exist: extract them verbatim
- If prose-only: extract sequential operations, mathematical formulation, heuristics, parameters, and stopping criteria

If no reference is provided, extract the intended method from solver documentation or code comments.

### 3. Map implementation control flow

Read the solver code and trace:
- Entry point and main loop structure
- Core operators/steps and their execution order
- Constraint handling mechanisms
- Randomness vs deterministic choices
- Termination conditions

Ignore language idioms and data-structure choices unless they alter algorithmic logic.

### 4. Check benchmark contract

Read:
- `benchmarks/<benchmark-name>/README.md`
- `docs/benchmark_contract.md`

Identify:
- Required input/output formats and interfaces
- Documented adaptations between the paper's problem formulation and the benchmark's contract
- Any benchmark-specific rules the solver must obey

### 5. Compare and classify

Create a side-by-side mapping table. For each reference step:

| Reference Step | Implementation | Status | Benchmark Context | Notes |
|----------------|---------------|--------|-------------------|-------|

**Status labels:**
- `MATCH` — Directly corresponds to the reference method
- `ADAPTATION` — Different from reference, but justified by benchmark contract
- `DEVIATION` — Different from reference in a way that affects correctness or validity (flag for review)
- `EXTENSION` — Not in reference, added in implementation
- `MISSING` — In reference but not implemented

**Classification rules:**
- `MATCH` if the step matches the reference
- `ADAPTATION` if the step differs but the benchmark contract documents the difference
- `DEVIATION` only if the difference changes algorithmic correctness or violates the benchmark contract. Cosmetic or performance-related differences that do not affect correctness are **not** deviations.
- `EXTENSION` for added logic that does not contradict the reference
- `MISSING` for omitted steps that are material to correctness or solution validity

For every `DEVIATION`, write a specific suggestion for how to fix the correctness issue, or explain why it might be acceptable.

For every `MISSING`, explain the impact on correctness or solution quality.

### 6. Assess performance baseline and timeout realism

Evaluate whether the solver is configured fairly for the method it implements:

- **Literature baseline**: What runtime does the reference report (e.g., hours, minutes)? On what hardware?
- **Benchmark envelope**: What timeout, thread count, or memory limit is the solver given?
- **Complexity fit**: Does the timeout realistically accommodate the algorithm's known complexity? Example: a MILP taking ~20 h in the literature should not be expected to finish in 120 s single-threaded.
- **Resource mismatch**: Flag only if the solver is given resources that make success practically impossible for the claimed method. Do **not** flag a correct-but-slow implementation as invalid.

**Performance notes format:**

| Aspect | Literature / Theory | Benchmark Config | Assessment | Notes |
|--------|--------------------|------------------|------------|-------|

### 7. Output audit report

Produce a Markdown report with this structure:

```markdown
# Solver Audit: <solver-name>

## Summary
- Correctness: <PASS / NEEDS_REVIEW / FAIL>
- Match rate: X/Y steps (if reference provided)
- Adaptations: N
- Deviations: M
- Extensions: P
- Missing: Q
- Performance baseline: <REALISTIC / MISALIGNED / UNKNOWN>

## Detailed Comparison
<table from step 5>

## Performance & Configuration Assessment
<table from step 6>

## Suggested Improvements
<List of actionable fixes for DEVIATION and MISSING items>
<List of timeout/resource recommendations if applicable>

## Notes
<Any other observations>
```

Do not print the full report to stdout unless the user asks. Save it to a file named `<solver-name>-audit.md` in the current working directory.

## Reference

See [references/audit-report-template.md](references/audit-report-template.md) for the report schema and status definitions.
