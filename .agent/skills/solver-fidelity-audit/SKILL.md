---
name: solver-fidelity-audit
description: Audit whether a solver implementation faithfully reproduces the original paper method. Use when: (1) comparing solver code to a research paper, (2) verifying algorithmic reproduction correctness, (3) checking for missing steps or unauthorized deviations, (4) validating that an implementation matches published pseudocode or methodology, (5) reviewing solver pull requests for fidelity.
---

# Solver Fidelity Audit

Audit a solver implementation against its original paper, accounting for benchmark-specific adaptations.

## Inputs

Require from user:
- Path to solver implementation (file or directory)
- Paper reference (PDF path, URL, arXiv ID, DOI, or local file)
- Benchmark name (to locate benchmark contract)

If any input is missing, ask before proceeding.

## Workflow

### 1. Parse paper

Use the `mineru` skill to parse the paper to Markdown.

```bash
mineru-parse.sh <paper-url-or-path> --output /tmp/mineru-<task-id> --extract
```

Read the resulting Markdown file.

### 2. Extract method specification

Search the parsed Markdown for the algorithm description:
- Look for sections containing: `Algorithm`, `pseudocode`, `Procedure`, `Method`, `Approach`
- If explicit numbered steps exist: extract them verbatim
- If prose-only: extract sequential operations, mathematical formulation, heuristics, parameters, and stopping criteria

### 3. Map implementation control flow

Read the solver code and trace:
- Entry point and main loop structure
- Core operators/steps and their execution order
- Constraint handling mechanisms
- Randomness vs deterministic choices
- Termination conditions

Ignore implementation details (language idioms, data structures) unless they alter the algorithmic logic.

### 4. Check benchmark contract for adaptations

Read:
- `benchmarks/<benchmark-name>/README.md`
- `docs/benchmark_contract.md`

Identify any documented differences between the paper's problem formulation and the benchmark's contract. Note these as potential `ADAPTATION` entries.

### 5. Compare and classify

Create a side-by-side mapping table. For each paper step:

| Paper Step | Implementation | Status | Benchmark Context | Notes |
|------------|---------------|--------|-------------------|-------|

**Status labels:**
- `MATCH` — Directly corresponds to paper
- `ADAPTATION` — Different from paper, but justified by benchmark contract
- `DEVIATION` — Different from paper with no benchmark justification (flag for review)
- `EXTENSION` — Not in paper, added in implementation
- `MISSING` — In paper but not implemented

Classification rules:
- If the step matches the paper -> `MATCH`
- If the step differs but the benchmark contract documents the difference -> `ADAPTATION`
- If the step differs and no benchmark justification exists -> `DEVIATION`
- If the implementation adds logic not in the paper -> `EXTENSION`
- If the paper describes a step absent from the code -> `MISSING`

For every `DEVIATION`, write a specific suggestion for how to bring the implementation closer to the paper, or explain why the deviation might be acceptable if there is a defensible reason.

For every `MISSING`, explain the impact on correctness or solution quality.

### 6. Output audit report

Produce a Markdown report with this structure:

```markdown
# Solver Fidelity Audit: <solver-name>

## Summary
- Match rate: X/Y steps
- Adaptations: N (benchmark-justified differences)
- Deviations: M (unauthorized differences requiring review)
- Extensions: P
- Missing: Q

## Detailed Comparison
<table from step 5>

## Suggested Improvements
<List of actionable fixes for DEVIATION and MISSING items>

## Notes
<Any other observations>
```

Do not print the full report to stdout unless the user asks. Save it to a file named `<solver-name>-fidelity-audit.md` in the current working directory.

## Reference

See [references/audit-report-template.md](references/audit-report-template.md) for the report schema and status definitions.
