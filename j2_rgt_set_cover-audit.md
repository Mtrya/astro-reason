# Solver Audit: j2_rgt_set_cover

## Bottom Line

- Target claim: certified J2 RGT pipeline for `revisit_constellation`, with analytical J2 used only for ranked candidate-target claims and numerical J2 used as the selection/emission gate.
- Status: NOT_YET for quality evaluation.
- Compute status: OPTIMIZATION_BLOCKED.
- Envelope status: between CONTRACT_SMOKE and REPRODUCTION, not QUALITY_OPTIMIZATION.
- Headline blockers:
  - Numerical certification is currently too expensive to reach selection on the public profile.
  - The main implementation issue is repeated per-claim numerical J2 state-provider construction and opportunity refinement.
  - The anti-patterns are now mostly control-flow mitigated, but the implementation still behaves like an expensive claim-by-claim verifier rather than a candidate-grouped optimizer.

## Current Measurements

Measured on `test/case_0001` with the public solver config:

- Load: about 0.002 s.
- Closure search: about 19.9 s.
- Coverage: about 40.2 s total elapsed.
- Coverage pool: 1,152 RAAN candidates, 15,706 windows, 15,726 hints, 10,679 candidate-target pairs.
- Analytical claims: 10,679 claims across 28 targets.
- Numerical certification probe: checking only one claim per target did not finish before a 180 s timeout.
- Analytical-only certification probe on the same one-claim-per-target frontier finished at about 39.7 s total elapsed, which is less than 1 s after coverage.

Interpretation: closure and coverage are not free, but they are not the current existential blocker. Numerical certification is.

## Anti-Pattern Check

The standing anti-pattern reference is in `docs/internal/revisit_constellation_j2_rgt_certified_pipeline.md`.

Current assessment:

- Step 1 candidate pool richness: likely rich enough for at least reproduction-scale probing on `case_0001`; 10,679 claims is not sparse. This may still fail hard targets, but time fails first.
- Step 1 returns all candidates instead of a ranked subset: partially true. Claims are ranked and certification is capped per target, but all claims are still built and serialized. More importantly, the certification frontier is still target-wise rather than selection-driven.
- Step 2 finds most candidates are bad: unknown from public runs because numerical certification does not finish. The system needs partial-progress instrumentation to answer this before full completion.
- Step 2 finds a bad candidate but uses it anyway: false at the candidate-target record level; rejected records cannot be selected. Partially unresolved at candidate-ID level because the current design may still use another passing target record from a candidate that also had a rejected claim.
- Step 2 verifies all candidates no matter what: false literally, because there is a per-target frontier and early stop. True in spirit for the current performance issue: it verifies claims independently and expensively instead of grouping by candidate plus satellite count and reusing propagation.
- Opportunistic observations cover unselected targets: fixed in final emission. `build_opportunities` and `select_assigned_first_actions` are assigned-only.

## Fair Optimization Envelope

The current public profile is not yet a fair quality/optimization envelope because the implementation cannot cheaply execute the intended numerical gate.

This is not mainly a worker-count problem. Parallelism helps, but the repeated work unit is too heavy:

- `_certify_claim_worker` certifies one candidate-target claim.
- Each claim calls `_refined_candidate_target_quality`.
- That builds a single-candidate selection, generates phased satellites, constructs `NumericalJ2StateProvider`, and refines opportunities.
- The same candidate and required satellite count can be rebuilt repeatedly for different targets.

This is bad optimization inside the fair envelope. More wall time would help only linearly and would mostly pay for duplicated propagation setup.

## Key Blockers

1. Certification work is grouped by target claim instead of by candidate variant.

   The natural reusable unit is `(candidate_id, required_satellite_count)`, not `(candidate_id, target_id)`. One propagated phased constellation can certify all candidate-target records for that variant.

2. Numerical state providers are rebuilt too often.

   `NumericalJ2StateProvider(case, satellites)` is expensive and should be cached or built once per selected candidate variant frontier batch.

3. Certification has no cheap numerical pre-screen.

   Analytical claim quality is used for ranking, but numerical refinement immediately pays the full propagation/refinement cost. A cheaper phase-offset or window-level screen could reject hopeless records before full opportunity refinement.

4. Certification progress is invisible until completion.

   Since `status.json` is written only after all stages, timeout runs cannot report checked/pass/fail rates. Add incremental debug or stage-progress artifacts before interpreting long public runs.

5. Candidate-level badness is not yet explicit.

   The current certified-record design is safe for emitted target assignments, but it does not expose or enforce the stricter rule: if a candidate claimed any target falsely, mark that candidate ID bad. We need diagnostics, and possibly a config switch, for candidate-global blacklisting.

## Recommended Fix Order

1. Rework certification around candidate variants:
   - group ranked claims by `(candidate_id, required_satellites)`;
   - build phased satellites and numerical state provider once;
   - certify all target records for that variant in one pass.

2. Make certification selection-driven:
   - maintain per-target passing counts;
   - prioritize variants that cover high-need targets;
   - stop checking variants that cannot improve selection.

3. Add progress artifacts:
   - write `debug/certification_progress.jsonl` or periodic summaries;
   - include checked, passed, failed, elapsed, and candidate-level bad counts.

4. Add candidate-level bad diagnostics:
   - `candidate_bad_if_any_claim_failed`;
   - selected candidates with any rejected claim;
   - selected candidate-target records by certificate ID.

5. Then rerun the public all-case profile.

Only after these changes should the timeout or worker count be treated as the main fair-envelope question.

## Sanity Footnote

Smoke runs can still produce verifier-valid partial or empty solutions because the benchmark verifier allows valid solutions with high revisit gaps. That proves contract compatibility, not solution quality.
