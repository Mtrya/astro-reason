# Solver Audit: j2_rgt_set_cover

## Bottom Line

- Target claim: certified J2 RGT pipeline for `revisit_constellation`, with analytical J2 used only for ranked candidate-target claims and numerical J2 used as the selection/emission gate.
- Status: READY. The current adaptive one-day profile is verifier-valid on all five public `revisit_constellation` test cases with zero threshold violations.
- Compute status: IMPROVED_BUT_NUMERICAL_HOT_PATH_BOUND.
- Envelope status: READY_PUBLIC_TEST_SPLIT, still numerically hot-path-bound.
- Headline blockers:
  - The old single-threaded DP selection blow-up is fixed by bitset branch-and-bound.
  - Numerical certification and final numerical state-provider construction are again the dominant runtime.
  - Denser one-day RAAN search plus adaptive one-day deepening fixed `case_0003` target_014 without using two-day candidates.
  - Full five-case quality for the adaptive one-day profile is now measured and passes.

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

After replacing per-target frontiers with a global candidate leaderboard, exact
certified set-cover selection, and the staged one-day-first default:

- `test/case_0001`: verifier-valid, 203.2 s solver time, 28/28 assigned targets, 0 high-gap targets, 20 satellites, capped max revisit gap 6.0 h.
- Strategy stopped after the first pass: `one_day_first`, `max_repeat_days=1`, 768 candidates, 48 checked candidates, 772 checked candidate-target records, 360 confirmed records.
- Selected candidates were five four-satellite variants with assigned target counts of 8, 4, 5, 8, and 3.
- Stage timing: closure 8.1 s, coverage 9.7 s, certification 63.2 s, exact initial selection 65.1 s, solution build 56.8 s.
- Benchmark verifier metrics: `is_valid=true`, `threshold_violation_count=0`, `max_revisit_gap_hours=5.9836`.

Partial all-case rerun after the staged default:

| Case | Solver s | Passes | Chosen pass | Initial selection s | Assigned targets | High-gap targets | Satellites | Note |
|---|---:|---:|---|---:|---:|---:|---:|---|
| test/case_0001 | 200.7 | 1 | one_day_first | 65.0 | 28 | 0 | 20 | Full coverage |
| test/case_0002 | 631.6 | 1 | one_day_first | 525.1 | 28 | 0 | 15 | Full coverage, exact-selection blow-up |
| test/case_0003 | 439.1 | 2 | one_day_first | 77.6 | 28 | 1 | 20 | Fallback was worse; `target_014` remains high-gap |
| test/case_0004 | stopped | unknown | unknown | >700 | unknown | unknown | unknown | Single hot Python process, likely exact-selection blow-up |

The partial rerun was stopped during `test/case_0004` because the process had
spent more than 12 minutes in a single CPU-bound solver process with no
certification worker children. This identifies exact certified selection, not
the one-day candidate sweep itself, as the immediate time blocker.

After replacing the mask-DP selector with bitset branch-and-bound and removing
the two-day fallback:

| Case/profile | Solver s | Passes | Checked candidates | Initial selection s | Assigned targets | High-gap targets | Satellites | Verifier |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| test/case_0002, raan48/c48 | 107.5 | 1 | 48 | 1.5 | 28 | 0 | 15 | valid |
| test/case_0003, raan96/c48 | 150.7 | 1 | 48 | 0.1 | 28 | 1 | 20 | local valid |
| test/case_0003, raan96/c96 | 227.0 | 1 | 96 | 9.8 | 29 | 0 | 20 | valid |
| test/case_0003, adaptive raan96 c48->c96 | 380.1 | 2 | 48 then 96 | 0.1 then 9.4 | 29 | 0 | 20 | valid |
| test/case_0004, raan96/c48 | 163.6 | 1 | 48 | 0.6 | 29 | 0 | 15 | valid |
| test/case_0004, raan96/c96 | timeout >420 | 1 | 96 | unknown | unknown | unknown | unknown | no status |

`test/case_0003` target_014 was not ignored: it had passing one-day certified
records in the 48-candidate pool, but exhaustive 5-candidate/20-satellite set
cover over that pool still topped out at 28/29. Increasing the one-day
candidate depth to 96 introduced a full 29/29 cover. `test/case_0004` shows why
96 should be adaptive rather than unconditional: the 48-candidate pass already
solves it, while the 96-candidate pass timed out before writing status.

READY validation on the public test split:

| Case | Solver s | Chosen pass | Checked records | Passed records | Assigned targets | High-gap targets | Satellites | Actions | Capped gap h |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| test/case_0001 | 140.1 | one_day | 828 | 398 | 28 | 0 | 16 | 225 | 6.0 |
| test/case_0002 | 122.1 | one_day | 803 | 401 | 28 | 0 | 15 | 179 | 8.0 |
| test/case_0003 | 377.3 | one_day_deep | 1634 | 696 | 29 | 0 | 20 | 234 | 6.0 |
| test/case_0004 | 163.3 | one_day | 837 | 429 | 29 | 0 | 15 | 185 | 8.0 |
| test/case_0005 | 149.3 | one_day | 752 | 324 | 27 | 0 | 20 | 217 | 6.0 |

## Anti-Pattern Check

The standing anti-pattern reference is in `docs/internal/revisit_constellation_j2_rgt_certified_pipeline.md`.

Current assessment:

- Step 1 candidate pool richness: sufficient for the public test split. One-day candidates are sufficient when the RAAN grid is dense enough and candidate depth can adapt from 48 to 96.
- Step 1 returns all candidates instead of a ranked subset: fixed for certification. All analytical claims are still serialized for debug, but certification consumes only the bounded global candidate leaderboard.
- Step 2 finds most candidates are bad: mixed. On the full run, checked records fail roughly 44-52% by case, mostly revisit-gap failures. Analytical ranking is useful but still noisy.
- Step 2 finds a bad candidate but uses it anyway: false at the candidate-target record level; rejected records cannot be selected. Partially unresolved at candidate-ID level because the current design may still use another passing target record from a candidate that also had a rejected claim.
- Step 2 verifies all candidates no matter what: improved. Certification checks a bounded candidate leaderboard and adaptively deepens only when the first one-day pass leaves quality issues, but it is not yet incrementally reused between passes.
- Opportunistic observations cover unselected targets: fixed in final emission. `build_opportunities` and `select_assigned_first_actions` are assigned-only.

## Fair Optimization Envelope

The current public profile is ready for the public test split. It uses numerical certificates, avoids opportunistic emission, and has successful full-coverage runs on all five public test cases. The remaining issue is numerical hot-path optimization rather than validity or target coverage.

This is not mainly a worker-count problem. Parallelism helps, but each checked candidate variant still pays expensive Brahe J2 propagation for every phased satellite, and final solution construction repeats that cost for selected satellites.

## Key Blockers

1. Numerical certification and state providers are the hot path again.

   The old exact-selection blow-up dropped from 525 s to 1.5 s on `case_0002`.
   Current expensive stages are certification and final selected-satellite
   propagation. `case_0003` adaptive spends about 136 s in deep certification
   and about 56 s in solution build.

2. Certification is not fully selection-driven.

   The global leaderboard is much better than per-target rank-only, but the
   deep pass still recomputes search, coverage, and the first 48 candidates
   instead of incrementally checking candidates 49-96.

3. Certification has no cheap numerical pre-screen.

   Analytical claim quality is used for ranking, but numerical refinement immediately pays the full propagation/refinement cost. A cheaper phase-offset or window-level screen could reject hopeless records before full opportunity refinement.

4. Candidate-level badness is not yet explicit.

   The current certified-record design is safe for emitted target assignments, but it does not expose or enforce the stricter rule: if a candidate claimed any target falsely, mark that candidate ID bad. We need diagnostics, and possibly a config switch, for candidate-global blacklisting.

5. Some residual high-gap targets in unmeasured cases may be budget-impossible for the current RGT family, but that is not proven.

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
