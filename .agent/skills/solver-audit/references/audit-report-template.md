# Audit Report Template

## Status Definitions

| Status | Meaning |
|--------|---------|
| MATCH | Step or formula directly corresponds to the reference method or paper. |
| ADAPTATION | Step differs from the reference, but the difference is justified by the benchmark contract or README. |
| DEVIATION | Step differs from the reference **and** the difference affects algorithmic correctness or benchmark compliance. Performance or implementation-style differences that do not affect correctness are **not** deviations. |
| EXTENSION | Logic present in the implementation that does not appear in the reference. |
| MISSING | Step or formula described in the reference that is absent from the implementation and is material to correctness. |

## Correctness Status Definitions

| Status | Meaning |
|--------|---------|
| PASS | No `DEVIATION` or `MISSING` items that impact correctness. |
| NEEDS_REVIEW | `DEVIATION` or `MISSING` items exist but their impact is ambiguous or requires human judgment. |
| FAIL | Clear `DEVIATION` or `MISSING` items that invalidate the algorithmic correctness or violate the benchmark contract. |

## Performance Assessment

Evaluate whether the solver's configuration is fair for the method it claims to implement.

| Aspect | Literature / Theory | Benchmark Config | Assessment | Notes |
|--------|--------------------|------------------|------------|-------|
| Timeout | e.g., 20 h on 16 cores | 120 s single-thread | MISALIGNED | Literature MILP baseline exceeds timeout by orders of magnitude |
| Threads | 16 | 1 | MISALIGNED | ... |
| Memory | — | 4 GB | REALISTIC | ... |

**Assessment values:**
- `REALISTIC` — The benchmark envelope reasonably accommodates the method.
- `MISALIGNED` — The timeout or resource limit makes success practically impossible for the claimed method.
- `UNKNOWN` — No literature baseline or complexity argument is available.

Rules:
- A correct but unoptimized implementation is **not** a failure. Note optimization gaps separately from deviations.
- Flag only configurations that make the claimed method infeasible, not configurations that merely yield slower solves.

## Report Schema

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

| Reference Step | Implementation | Status | Benchmark Context | Notes |
|----------------|---------------|--------|-------------------|-------|
| ...            | ...           | ...    | ...               | ...   |

## Performance & Configuration Assessment

| Aspect | Literature / Theory | Benchmark Config | Assessment | Notes |
|--------|--------------------|------------------|------------|-------|
| ...    | ...                | ...              | ...        | ...   |

## Suggested Improvements

1. **[DEVIATION] <brief description>**
   - Current behavior: ...
   - Expected per reference: ...
   - Suggestion: ...

2. **[MISSING] <brief description>**
   - Impact: ...
   - Suggestion: ...

3. **[PERFORMANCE] <brief description>** (optional)
   - Observation: ...
   - Recommendation: ...

## Notes
- <any additional observations>
```

## Comparison Rules

1. Always check the benchmark contract before classifying a difference as DEVIATION.
2. If a difference is documented in the benchmark README or contract, classify as ADAPTATION and cite the source.
3. A deviation is only actionable if it can be traced to a specific reference step or formula **and** it affects correctness.
4. Performance-only differences (e.g., slower loop, simpler data structure) are not deviations unless they violate benchmark requirements.
5. Extensions are not inherently bad; note them for awareness.
6. Missing steps should include an assessment of whether the omission is material to correctness.
7. Timeout or resource complaints belong in the Performance section, not as algorithmic deviations.
