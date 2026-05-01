# Revisit Constellation J2 RGT Certified Pipeline Notes

This note is the standing reference for the two-step certified RGT solver idea
and the anti-patterns to check when performance or quality regresses.

## Core Two-Step Idea

The solver must keep analytical search and numerical truth separate.

Step 1 is an analytical J2 candidate-ranking stage. It may generate RGT
templates, expand RAANs, sample coarse visibility, and rank candidate-target
claims. It must not decide final target coverage.

Step 2 is a numerical J2 certification and selection stage. It refines only a
bounded, ranked frontier of Step 1 claims, certifies candidate-target records
against benchmark-compatible geometry and revisit constraints, and lets
selection and emission use only those certified records.

The invariant is:

```text
No target may be selected or emitted unless a numerical certificate for the
selected candidate-target assignment exists and was selected.
```

If full certified coverage is impossible inside the satellite budget or retry
limit, the solver should emit the best verifier-valid partial solution and
report uncovered or unresolved targets explicitly.

## Six Anti-Patterns

Use this list when auditing `j2_rgt_set_cover` or any replacement method.

1. Step 1 does not produce a rich enough candidate pool.

   The analytical frontier is too sparse, too biased, or too low-resolution to
   contain good candidates for the hard targets. Symptoms include many targets
   with zero or very few analytical claims before certification.

2. Step 1 returns all candidates instead of ranking and selecting a subset.

   A large unranked pool makes Step 2 a brute-force numerical screen. Step 1
   should rank claims and pass only a bounded frontier per target or per
   candidate family.

3. Step 2 finds that most Step 1 candidates are bad.

   For candidate-level audits, define a candidate as bad if it claimed a target
   it cannot cover numerically. For claim-level pipelines, track both rejected
   candidate-target records and candidate IDs with any rejected claim. A high
   rejection rate means analytical ranking is not predictive enough.

4. Step 2 finds a candidate is bad but uses it anyway.

   If the solver uses candidate-level selection, a candidate with any false
   coverage claim should be blacklisted or repaired before use. If the solver
   uses candidate-target certificates, failed records must be unavailable to
   selection and emission, and debug output must make the candidate-level risk
   visible.

5. Step 2 verifies all candidates no matter what instead of greedily and in
   parallel.

   Certification should be demand-driven: process ranked frontiers, stop once a
   target has enough passing claims, and prioritize claims that can affect the
   current selection. Parallel workers should be used for independent numerical
   refinements, but parallelism is not a substitute for pruning.

6. Opportunistic observations cover unselected targets.

   Merely visible targets on selected orbits are not certified assignments.
   Final actions must come only from selected certified candidate-target
   records. Opportunistic observation may be useful for exploratory diagnostics,
   but it must not affect submitted `solution.json`.

## Fair Optimization Envelope

A solver run can be valid but still not be a fair optimization run.

The public or quality envelope should be judged by:

- candidate richness: templates, RAAN density, and target-specific frontier
  depth are large enough to give the method a real shot;
- certification efficiency: numerical refinement is bounded, ranked,
  parallelized, and stopped early when extra checks cannot help selection;
- hot-path efficiency: repeated propagation, state-provider construction, and
  target geometry checks are cached, batched, or vectorized where practical;
- selection usefulness: certified records are selected with a real objective,
  not just the first records that happen to pass;
- retry realism: final scheduling conflicts trigger targeted blacklists and
  reselection, not broad restart loops;
- reporting: status/debug artifacts expose claim counts, pass/fail counts,
  bad-candidate rates, timing by stage, selected records, unresolved targets,
  and retry history.

The fair-envelope failure modes are:

- bad optimization: the algorithm checks or schedules in a wasteful order;
- under-parallelization: independent refinements run serially or workers do
  duplicated expensive setup;
- underpowered search: caps are so small that the solver is only in a smoke
  envelope;
- overbroad search: caps are so large, or pruning so weak, that the solver
  spends its budget proving bad claims;
- implementation overhead: repeated numerical propagator construction or Python
  geometry loops dominate before selection gets a meaningful pool;
- impossible cases: even a strong candidate pool has no verifier-valid way to
  meet every target under the satellite budget and horizon.

## Current `j2_rgt_set_cover` Audit Questions

When investigating a slow or weak run, answer these in order:

1. How many analytical claims were produced per target?
2. How many claims were checked per target before early stop?
3. What fraction of checked claims passed numerical certification?
4. Which candidate IDs had any rejected claim, and were any of those candidate
   IDs still selected for other target records?
5. Which stage dominates `status.json.timing_seconds`?
6. Does certification rebuild phased satellites or numerical propagators for
   the same candidate and satellite count repeatedly?
7. Are targets with zero certified claims impossible, under-searched, or
   blocked by analytical ranking quality?
8. Did final emission use only selected certified assignments?
9. Did retry blacklists target only failed records or did they remove useful
   variants too broadly?
10. Would more time improve the result, or would it mostly repeat the same
    expensive checks?

## Expected Debug Evidence

Useful artifacts for this pipeline are:

- `debug/coverage_summary.json`: analytical candidates, coarse evidence, and
  ranked analytical claims only;
- `debug/certification_summary.json`: numerical pass/fail truth, rejection
  reasons, checked counts, frontier limits, and candidate-level rejection
  diagnostics;
- `debug/selection_summary.json`: selected certified records and uncovered
  targets;
- `debug/solution_summary.json`: emitted selected-assignment actions,
  validation, target gaps, and retry history;
- `status.json`: compact stage timing, compute profile, certification counts,
  selection counts, and high-gap or unresolved targets.

If these artifacts do not make the anti-pattern checks answerable, improve the
instrumentation before drawing quality conclusions.
