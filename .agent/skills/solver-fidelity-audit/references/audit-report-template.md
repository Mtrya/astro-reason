# Audit Report Template

## Status Definitions

| Status | Meaning |
|--------|---------|
| MATCH | Step or formula directly corresponds to the original paper. |
| ADAPTATION | Step differs from the paper, but the difference is justified by the benchmark contract or README. |
| DEVIATION | Step differs from the paper with no benchmark justification. Flagged for review. |
| EXTENSION | Logic present in the implementation that does not appear in the paper. |
| MISSING | Step or formula described in the paper that is absent from the implementation. |

## Report Schema

```markdown
# Solver Fidelity Audit: <solver-name>

## Summary
- Match rate: X/Y steps
- Adaptations: N
- Deviations: M
- Extensions: P
- Missing: Q

## Detailed Comparison

| Paper Step | Implementation | Status | Benchmark Context | Notes |
|------------|---------------|--------|-------------------|-------|
| ...        | ...           | ...    | ...               | ...   |

## Suggested Improvements

1. **[DEVIATION] <brief description>**
   - Current behavior: ...
   - Expected per paper: ...
   - Suggestion: ...

2. **[MISSING] <brief description>**
   - Impact: ...
   - Suggestion: ...

## Notes
- <any additional observations>
```

## Comparison Rules

1. Always check the benchmark contract before classifying a difference as DEVIATION.
2. If a difference is documented in the benchmark README or contract, classify as ADAPTATION and cite the source.
3. A deviation is only actionable if it can be traced to a specific paper step or formula.
4. Extensions are not inherently bad; note them for awareness.
5. Missing steps should include an assessment of whether the omission is material to correctness.
