# Revisit Constellation J2 RGT Certified Pipeline Notes

This note is the standing reference for the two-step certified RGT solver idea
and the anti-patterns to check when performance or quality regresses.

## Core Two-Step Idea

The solver must keep analytical search and numerical truth separate.

Step 1 is an analytical J2 candidate-ranking stage. It may generate RGT
templates, expand RAANs, sample coarse visibility, and produce candidate-target
claims. A claim means "candidate X may cover target Y"; it is evidence for a
candidate, not the primary ranking unit.

Step 1 must build a candidate leaderboard: a deterministic list of candidates
ranked by which candidates Step 2 should check first. A leaderboard entry is
one candidate with a concrete satellite count and the targets it claims.

Step 2 is a numerical J2 checking and selection stage. It consumes the
candidate leaderboard, numerically checks candidate-target pairs for the
leading candidates, records confirmed candidate-target pairs, and lets
selection and emission use only those confirmed records.

The current default strategy checks one-day repeat-track candidates only,
because they give cheaper variants that combine well under the satellite
budget. It uses a denser one-day RAAN grid, checks the top 48 candidates first,
and deepens to 96 one-day candidates only when the first pass leaves high-gap
or uncovered targets. If quality is weak, spend additional compute on denser
one-day RAAN grids or deeper one-day leaderboards before widening to costlier
repeat-day families.

For `test/case_0003`, 48 checked one-day candidates contained passing
target_014 records but no 20-satellite set cover for all 29 targets. Increasing
the one-day RAAN grid and checking 96 leaderboard candidates found a
verifier-valid 29/29 solution, while the old two-day fallback was worse.

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

   The analytical candidate pool is too sparse, too biased, or too low-resolution to
   contain good candidates for the hard targets. Symptoms include many targets
   with zero or very few analytical claims before certification.

2. Step 1 returns all candidates instead of ranking and selecting a subset.

   A large unranked pool makes Step 2 a brute-force numerical screen. Ranking
   candidate-target pairs target-by-target is also not enough: globally strong
   candidates can be locally mediocre for each individual target. Step 1 should
   produce a global candidate leaderboard.

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

   Numerical checking should be demand-driven: process the candidate
   leaderboard, prioritize candidates that can affect selection, and use
   parallel workers for independent candidates. Parallelism is not a substitute
   for a good leaderboard.

6. Opportunistic observations cover unselected targets.

   Merely visible targets on selected orbits are not confirmed assignments.
   Final actions must come only from selected confirmed candidate-target
   records. Opportunistic observation may be useful for exploratory diagnostics,
   but it must not affect submitted `solution.json`.

## Fair Optimization Envelope

A solver run can be valid but still not be a fair optimization run.

The public or quality envelope should be judged by:

- candidate richness: templates and RAAN density are large enough to give the
  method a real shot;
- leaderboard quality: candidates that cover many targets or rare targets
  bubble up before locally cheap but globally weak candidates;
- certification efficiency: numerical checking is bounded, ranked, and
  parallelized;
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
- costly-repeat bias: longer-repeat candidates appear strong by raw target
  count but consume too many satellites to combine well under the case budget;
- implementation overhead: repeated numerical propagator construction or Python
  geometry loops dominate before selection gets a meaningful pool;
- impossible cases: even a strong candidate pool has no verifier-valid way to
  meet every target under the satellite budget and horizon.

## Current `j2_rgt_set_cover` Audit Questions

When investigating a slow or weak run, answer these in order:

1. How many candidates and candidate-target claims did Step 1 produce?
2. Do high analytical-coverage candidates appear near the top of the candidate
   leaderboard?
3. How many candidates and candidate-target pairs did Step 2 check?
4. What fraction of checked candidate-target pairs passed numerical checking?
5. Which candidate IDs had any rejected claim, and were any of those candidate
   IDs still selected for other target records?
6. Which stage dominates `status.json.timing_seconds`?
7. Does certification rebuild phased satellites or numerical propagators for
   the same candidate and satellite count repeatedly?
8. Are targets with zero confirmed pairs impossible, under-searched, or blocked
   by leaderboard quality?
9. Did final emission use only selected confirmed assignments?
10. Did retry blacklists target only failed records or did they remove useful
   variants too broadly?
11. Would more time improve the result, or would it mostly repeat the same
    expensive checks?

## Expected Debug Evidence

Useful artifacts for this pipeline are:

- `debug/coverage_summary.json`: analytical candidates, coarse evidence, and
  analytical candidate-target claims only;
- `debug/certification_summary.json`: numerical pass/fail truth, rejection
  reasons, checked counts, candidate leaderboard, and candidate-level rejection
  diagnostics;
- `debug/selection_summary.json`: selected confirmed records and uncovered
  targets;
- `debug/solution_summary.json`: emitted selected-assignment actions,
  validation, target gaps, and retry history;
- `status.json`: compact stage timing, compute profile, certification counts,
  selection counts, and high-gap or unresolved targets.

If these artifacts do not make the anti-pattern checks answerable, improve the
instrumentation before drawing quality conclusions.
