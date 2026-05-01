# Solver Audit: j2_rgt_set_cover

## Bottom Line

- Target claim: certified J2 RGT pipeline for `revisit_constellation`, with analytical J2 used only for ranked candidate-target claims and numerical J2 used as the selection/emission gate.
- Status: verifier-valid on all five public test cases with partial certified coverage.
- Compute status: IMPROVED_BUT_NUMERICAL_HOT_PATH_BOUND.
- Envelope status: REPRODUCTION_PROBE, not yet QUALITY_OPTIMIZATION.
- Headline blockers:
  - Numerical certification and final numerical state-provider construction remain the dominant runtime.
  - A purely cheap-per-target frontier under-covered globally useful multi-target candidates; the frontier now interleaves cheap claims with coarse set-cover-efficient claims.
  - Selection quality is still partial: current public run covers 18-21 of 26-29 targets depending on case under the satellite budget.

## Current Measurements

Initial measurement on `test/case_0001` with the original public solver config:

- Load: about 0.002 s.
- Closure search: about 19.9 s.
- Coverage: about 40.2 s total elapsed.
- Coverage pool: 1,152 RAAN candidates, 15,706 windows, 15,726 hints, 10,679 candidate-target pairs.
- Analytical claims: 10,679 claims across 28 targets.
- Numerical certification probe: checking only one claim per target did not finish before a 180 s timeout.
- Analytical-only certification probe on the same one-claim-per-target frontier finished at about 39.7 s total elapsed, which is less than 1 s after coverage.

Interpretation: closure and coverage are not free, but they are not the current existential blocker. Numerical certification is.

After grouping certification by `(candidate_id, required_satellites)` and using
the bounded 8/2 hybrid frontier:

- `test/case_0001`: verifier-valid, 172.3 s solver time, 77.2 s certification, 55.6 s final selection/solution build, 21 assigned targets, 7 high-gap targets.
- Full public test split verified all five cases:

| Case | Solver s | Cert s | Solution-build s | Certified targets | Checked records | Checked variants | Assigned targets | High-gap targets | Satellites | Capped gap h |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| test/case_0001 | 172.3 | 77.2 | 55.6 | 28 | 103 | 55 | 21 | 7 | 20 | 16.5 |
| test/case_0002 | 148.6 | 58.8 | 50.4 | 28 | 85 | 52 | 18 | 10 | 18 | 22.3 |
| test/case_0003 | 172.4 | 77.2 | 55.4 | 28 | 102 | 55 | 19 | 10 | 20 | 20.5 |
| test/case_0004 | 193.1 | 51.2 | 100.7 | 29 | 80 | 46 | 18 | 11 | 18 | 23.2 |
| test/case_0005 | 181.9 | 87.6 | 55.5 | 26 | 93 | 58 | 19 | 8 | 20 | 18.4 |

## Anti-Pattern Check

The standing anti-pattern reference is in `docs/internal/revisit_constellation_j2_rgt_certified_pipeline.md`.

Current assessment:

- Step 1 candidate pool richness: improved but still algorithmically sensitive. The pool is large, but a cost-first frontier missed high coarse-coverage candidates; the hybrid frontier fixes that failure mode for the current run.
- Step 1 returns all candidates instead of a ranked subset: mostly fixed for certification. All analytical claims are still serialized for debug, but certification consumes only a bounded interleaved frontier.
- Step 2 finds most candidates are bad: mixed. On the full run, checked records fail roughly 44-52% by case, mostly revisit-gap failures. Analytical ranking is useful but still noisy.
- Step 2 finds a bad candidate but uses it anyway: false at the candidate-target record level; rejected records cannot be selected. Partially unresolved at candidate-ID level because the current design may still use another passing target record from a candidate that also had a rejected claim.
- Step 2 verifies all candidates no matter what: improved. Certification now groups claims by candidate variant and stops after per-target passing counts, but it is not yet fully selection-driven.
- Opportunistic observations cover unselected targets: fixed in final emission. `build_opportunities` and `select_assigned_first_actions` are assigned-only.

## Fair Optimization Envelope

The current public profile is a fair reproduction probe, but not yet an ideal quality envelope. It now completes the all-case run, uses numerical certificates, and avoids opportunistic emission. The remaining issue is hot-path optimization plus selection depth.

This is not mainly a worker-count problem. Parallelism helps, but each checked candidate variant still pays expensive Brahe J2 propagation for every phased satellite, and final solution construction repeats that cost for selected satellites.

## Key Blockers

1. Numerical state providers are still the hot path.

   Case 0001 spends about 77 s in certification and 47 s constructing final numerical state providers. Case 0004 spends about 101 s in solution build, dominated by final selected-satellite propagation.

2. Certification is not fully selection-driven.

   The hybrid frontier is much better than rank-only, but it still certifies records to meet per-target counts before knowing which variants selection needs next.

3. Certification has no cheap numerical pre-screen.

   Analytical claim quality is used for ranking, but numerical refinement immediately pays the full propagation/refinement cost. A cheaper phase-offset or window-level screen could reject hopeless records before full opportunity refinement.

4. Candidate-level badness is not yet explicit.

   The current certified-record design is safe for emitted target assignments, but it does not expose or enforce the stricter rule: if a candidate claimed any target falsely, mark that candidate ID bad. We need diagnostics, and possibly a config switch, for candidate-global blacklisting.

5. Some residual high-gap targets may be budget-impossible for the current RGT family, but that is not proven.

   The solver certifies every target in most cases, but cannot select all certified targets within the satellite budget. Proving impossibility requires either a stronger candidate family or an exact certified set-cover upper-bound/unsat diagnostic.

## Recommended Fix Order

1. Make certification selection-driven:
   - maintain per-target passing counts;
   - prioritize variants that cover high-need targets;
   - stop checking variants that cannot improve selection.

2. Reduce numerical propagation cost:
   - cache final selected state providers where retry attempts reuse variants;
   - investigate lazy/time-ordered propagation for certification;
   - add a cheap numerical pre-screen before full opportunity refinement.

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
