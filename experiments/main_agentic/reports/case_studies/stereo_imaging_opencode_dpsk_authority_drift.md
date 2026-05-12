# Stereo Imaging Opencode DPSK Case Study: Geometry Fixes That Did Not Stick

This note diagnoses the `opencode_dpsk` stereo imaging runs in the `main_agentic` report. Unlike `kimi_cli`, DPSK did not uniformly fail every case in the same way. It produced one strong valid solution, one high-quality but invalid solution, and three valid zero-score schedules. The recurring failure pattern was not lack of effort or schema ignorance; it was unstable authority discipline. DPSK repeatedly built a private access and footprint model, used the verifier as a late debugger, sometimes discovered the right geometry convention, but did not consistently preserve verifier-valid, score-producing solutions across cases.

## Evidence Base

Aggregate outcomes come from `experiments/main_agentic/reports/stereo_imaging.md`. Behavioral evidence comes from the tracked trace exports:

- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__opencode_dpsk__test__case_0001.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__opencode_dpsk__test__case_0002.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__opencode_dpsk__test__case_0003.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__opencode_dpsk__test__case_0004.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__opencode_dpsk__test__case_0005.js`

Contract evidence comes from `experiments/_fragments/prompts/stereo_imaging/README.default.md`, the benchmark config `experiments/main_agentic/benchmarks/stereo_imaging.yaml`, and the verifier implementation under `benchmarks/stereo_imaging/verifier/`. The evaluated space agent saw an opaque verifier helper and the rendered README, not the verifier source code. The source is used here only to explain retrospectively why the submitted schedules scored as they did.

I also replayed the saved local final `solution.json` files and inspected the local `run.json` verifier payloads while preparing this report. Those ignored run outputs are diagnostics, not the primary evidence base. The primary claims are anchored to the aggregate report, tracked trace exports, and the public workspace/verifier contract.

## Aggregate Outcome

The aggregate report shows a mixed outcome:

| Case | Valid | Duration (s) | normalized_quality | coverage_ratio |
| --- | --- | ---: | ---: | ---: |
| `case_0001` | true | 5879.5 | 0.0000 | 0.0000 |
| `case_0002` | true | 7200.9 | 0.0000 | 0.0000 |
| `case_0003` | true | 5456.1 | 0.6498 | 0.9421 |
| `case_0004` | false | 5591.7 | 0.7248 | 0.8016 |
| `case_0005` | true | 5857.2 | 0.0000 | 0.0000 |

This is the key fact: DPSK did not simply fail to understand the benchmark. `case_0003` proves it could produce a strong, verifier-valid stereo solution. The failure was reproducibility of the solving process. Across the five cases, it did not reliably keep the final deliverable aligned with the verifier's hard-validity and product-validity requirements.

## Intended Contract

The assembled README tells the space agent that it submits raw observation actions only. The verifier derives stereo pair and tri-stereo products after parsing the actions. Each action must include `type: "observation"`, satellite and target IDs, a start/end time, and signed `off_nadir_along_deg` and `off_nadir_across_deg`.

The README also separates three ideas that DPSK repeatedly blurred:

- hard observation validity: horizon, duration, target IDs, off-nadir limits, access interval membership, and same-satellite slew/settle;
- product eligibility: same target, allowed stereo mode, and bounded midpoint separation;
- product validity and score: overlap fraction, convergence angle, and pixel scale ratio.

The verifier implements that separation directly. It first checks same-satellite overlap and slew/settle, then derives observation metadata and access interval membership, then builds same-target pair evaluations. A valid pair requires:

```text
overlap_fraction >= min_overlap_fraction
min_convergence_deg <= gamma_deg <= max_convergence_deg
pixel_scale_ratio <= max_pixel_scale_ratio
```

The overlap term is not implied by access. The verifier samples each commanded pushbroom strip centerline every 8 seconds, projects those boresight ground intercepts into the target-local tangent plane, and Monte Carlo samples the AOI disk. This is why a schedule can be hard-valid but still have zero coverage.

## Immediate Pattern

DPSK usually did the right initial authority-acquisition steps. It listed the workspace, read the README, read the case YAML files, loaded the Brahe skill, and ran the local verifier. The failures came later, after it had built a substantial private model for access windows, steering angles, strip overlap, and scheduling.

The trace pattern by case is:

- `case_0001`: DPSK ended with a hard-valid schedule containing many interpreted observations, but the verifier reported `coverage_ratio=0.0` and `normalized_quality=0.0`. The trace ends with DPSK acknowledging that all evaluated pairs had `overlap_fraction=0.0`, then accepting the current solution as "valid."
- `case_0002`: DPSK timed out. It spent much of the run debugging verifier access and overlap issues, including an unfinished attempt to inspect/decompile the opaque verifier. The final saved solution contained only one same-pass pair and scored zero.
- `case_0003`: DPSK recovered. It explicitly recorded "Fix zero overlap: sign of across_hat was wrong" and finished with high coverage and no violations.
- `case_0004`: DPSK built a high-scoring schedule but finalized it while it was still verifier-invalid. It knew the compact verifier output contained seven violations, then described the solution as strong enough.
- `case_0005`: DPSK fell back to a sparse nadir-only schedule. It produced a hard-valid file, but only three pairs were evaluated and all had zero overlap.

The common thread is not "DPSK never found the geometry." In some cases it did. The common thread is that verifier feedback was not consistently used as the final acceptance authority for both hard validity and score.

## Root Cause 1: Access Was Treated As A Proxy For Footprint Overlap

The most common zero-score symptom was valid observations with no valid stereo products. In the local verifier payloads for the final submissions:

| Case | Actions | Derived observations | Pair evaluations | Valid pairs | Zero-overlap pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| `case_0001` | 653 | 653 | 120 | 0 | 120 |
| `case_0002` | 2 | 2 | 1 | 0 | 1 |
| `case_0003` | 230 | 230 | 115 | 114 | 0 |
| `case_0004` | 1381 | 1381 | 1713 | 650 | 0 |
| `case_0005` | 14 | 14 | 3 | 0 | 3 |

`case_0001`, `case_0002`, and `case_0005` show the failure clearly. The observations were hard-valid, so the verifier could derive observation records and pair evaluations. But product coverage stayed zero because overlap failed. DPSK repeatedly reasoned as though a target inside a Brahe access window, or a boresight that looked close at a midpoint, should imply a useful footprint. The verifier's product check is stricter: both commanded strip centerlines must jointly cover enough of the AOI disk.

In `case_0001`, the trace records the final compact verifier output:

```json
{
  "valid": true,
  "metrics": {
    "valid": true,
    "coverage_ratio": 0.0,
    "normalized_quality": 0.0
  },
  "violations": []
}
```

DPSK then says the solution is valid with 653 observations, despite also observing that all 120 evaluated pairs have zero overlap. This is an acceptance-discipline failure: hard-validity was treated as sufficient even though the benchmark objective was explicitly product coverage and normalized quality.

## Root Cause 2: Cross-Track Convention Was Discovered, But Not Reliably Applied

The verifier's signed steering convention uses the local across-track axis defined as:

```python
across = np.cross(along, nadir)
```

A common alternative is `np.cross(nadir, along)`, which is the negative axis. If a solver computes `off_nadir_across_deg` in the opposite convention and submits it unchanged, the commanded strip is mirrored to the wrong side of the ground track. That produces the classic symptom: hard-valid observations and plausible convergence, but zero AOI overlap.

DPSK's traces show both failure and recovery around this issue. In `case_0003`, the final todo list includes "Fix zero overlap: sign of across_hat was wrong," and the resulting solution scores strongly. In `case_0004`, the final todo list also includes "Fix across-direction sign convention," and the derived product metrics are high before hard-validity violations zero out the benchmark score.

The failed cases show why this insight was not enough. I mirrored the final submitted `off_nadir_across_deg` values as a counterfactual:

| Case | Original coverage | Original quality | Mirrored coverage | Mirrored quality | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| `case_0001` | 0.0000 | 0.0000 | 0.1127 | 0.0960 | Sign mismatch was important, but the schedule also had many bad pair choices and pixel-scale failures. |
| `case_0002` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | Mirroring moved the only pair near threshold, but overlap was still 0.76 under a 0.8 requirement. |
| `case_0003` | 0.9421 | 0.6498 | 0.0083 | 0.0063 | The successful final solution already used the verifier's convention. |
| `case_0004` | 0.8016 | 0.7248 | 0.0079 | 0.0078 | The high-derived-score final solution already used the verifier's convention. |
| `case_0005` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | The final schedule was mostly nadir-only and too sparse; mirroring does not help. |

This distinguishes DPSK from Kimi. Kimi's main productive schedules were largely rescued by mirroring. DPSK's pattern is more unstable: it sometimes had the wrong sign, sometimes fixed it, and sometimes failed for unrelated schedule sparsity or validity reasons.

## Root Cause 3: Hard Validity Was Not Preserved During Optimization

`case_0004` is the cleanest hard-validity failure. The final aggregate row is `valid=false`, so the benchmark score is zero, but the verifier-derived metrics inside the invalid report are high: `coverage_ratio=0.8016` and `normalized_quality=0.7248`.

The final local verifier report contained seven violations:

- two slew/settle violations for `sat_skysat_a`,
- one slew/settle violation for `sat_skysat_c3`,
- four actions not fully contained inside continuous access intervals.

The trace shows DPSK saw essentially this compact output after rerunning its scheduler:

```json
{
  "valid": false,
  "metrics": {
    "valid": false,
    "coverage_ratio": 0.8174603174603174,
    "normalized_quality": 0.740696690113217
  },
  "violations": [
    "satellite sat_skysat_a: insufficient slew/settle ...",
    "satellite sat_skysat_a: insufficient slew/settle ...",
    "satellite sat_skysat_c3: insufficient slew/settle ...",
    "actions[450]: observation is not fully contained inside a continuous access interval",
    "actions[467]: observation is not fully contained inside a continuous access interval",
    "actions[518]: observation is not fully contained inside a continuous access interval",
    "actions[741]: observation is not fully contained inside a continuous access interval"
  ]
}
```

DPSK then reasoned that this was "the best result so far" and "strong enough." That is exactly the wrong acceptance rule for this benchmark. Invalid solutions receive zero normalized score in the aggregate, even if the diagnostic product metrics look attractive.

This failure is especially important because it shows the opposite of `case_0001`. In `case_0001`, DPSK preserved hard validity and lost all product value. In `case_0004`, it found product value and lost hard validity. The benchmark required both.

## Root Cause 4: Runtime Search Drift And Late Fallbacks

`case_0002` and `case_0005` show search instability under the two-hour budget.

In `case_0002`, DPSK timed out after heavy debugging. It read the README, loaded the Brahe skill, generated candidate observations, found verifier access failures, and then pursued increasingly deep explanations, including attempts to inspect the PyInstaller verifier archive. The final `solution.json` had only two actions. The one evaluated pair had good convergence and pixel-scale ratio, but overlap was zero as submitted. Mirroring raised overlap to 0.76, still below the 0.8 threshold.

In `case_0005`, DPSK's final trace summary blamed Brahe access instability and Earth-occultation filtering. It wrote 14 valid observations across 11 targets, using mostly zero along/across steering. That produced only three pair evaluations, all with zero overlap. Here the final deliverable was a conservative hard-valid fallback, not a stereo solution.

The pattern is that DPSK spent a lot of time building and debugging a private access generator. When that generator diverged from verifier behavior or ran out of time, the final file was whatever hard-valid or likely-hard-valid artifact existed, even when the verifier metric was already known to be zero.

## The Successful Control: Case 0003

`case_0003` is the control that keeps this report honest. DPSK did not fail because stereo imaging was impossible or because the prompt was unusable. In this case, it:

- read the README and case files,
- loaded Brahe,
- iterated against the verifier,
- diagnosed the across-track sign convention,
- checked the final metrics,
- preserved a valid final `solution.json`.

The final trace reports:

```text
Valid: True
Coverage Ratio: 0.942149
Normalized Quality: 0.648288
Violations: 0
Total Pairs: 115
Valid Pairs: 114
```

The aggregate report records the same shape: valid, `coverage_ratio=0.9421`, `normalized_quality=0.6498`. This is not a lucky empty schedule. It is a genuine high-coverage solution.

That success also reveals what the other cases lacked. DPSK needed all of these at once: verifier-aligned across-track signs, overlap-aware strip placement, enough same-target pair construction, and hard-validity preservation after optimization. Missing any one of those pieces was enough to produce a zero aggregate score.

## Case-By-Case Failure Mode

`case_0001` was a valid zero-score schedule. DPSK produced 653 actions and 120 pair evaluations, but every pair had zero overlap. It recognized the zero-overlap symptom late, speculated about projection and strip sampling, and accepted hard validity as the deliverable. Mirroring across-track signs partially rescues the schedule, but only to `coverage_ratio=0.1127`, because many candidate pairs still fail pixel-scale ratio, overlap threshold, or geometry.

`case_0002` was a timeout and late minimal fallback. The final two actions formed one same-satellite same-pass pair with good convergence and scale, but no valid overlap. The run became consumed by access/overlap debugging and unfinished verifier inspection. The final artifact was valid but not useful.

`case_0003` was the successful control. DPSK fixed the across-track convention, achieved 114 valid pairs out of 115 pair evaluations, and finished hard-valid.

`case_0004` was an invalid high-score schedule. DPSK fixed enough geometry to create many valid stereo products, but finalized with three slew/settle violations and four access-membership violations. The aggregate score is therefore zero even though the diagnostic product metrics are strong.

`case_0005` was a sparse hard-valid fallback. DPSK focused on Brahe access and Earth occultation, then submitted 14 mostly nadir-pointing observations. Only three stereo pairs were even evaluated, and all failed overlap. The trace explicitly states `coverage_ratio=0.0`.

## Comparison To Kimi

Kimi's recurring failure was cleaner: in three cases, it expressed target-pointing commands in the opposite cross-track convention, so mirroring the final schedules produced dramatic recoveries. DPSK's story is more heterogeneous.

DPSK also hit the cross-track sign trap, but it sometimes solved it. Its failures come from a broader process-level instability:

- in some runs, it did not fix the sign before finalizing;
- in one run, it fixed the sign but allowed hard-validity violations to remain;
- in one run, it fell back to sparse nadir-only observations;
- in one run, it timed out while debugging the verifier rather than preserving a useful verified solution.

So if Kimi is a case study in a persistent coordinate-convention mismatch, DPSK is a case study in inconsistent verifier-centered iteration. The two reports overlap on cross-track handedness, but DPSK should not be reduced to that one bug.

## Root Cause

The root cause is verifier-authority drift during private model construction. DPSK correctly acquired much of the workspace contract and often used the verifier, but its internal solver model repeatedly became the active source of truth for the next step. When the verifier contradicted that model, DPSK sometimes repaired the model, sometimes pursued the wrong diagnostic path, and sometimes finalized anyway.

The immediate root causes by failed case were:

- `case_0001`: footprint overlap model not aligned with the verifier; hard-valid actions did not create any valid products.
- `case_0002`: timeout after access/overlap debugging; final pair missed the overlap threshold.
- `case_0004`: hard-validity preservation failure after optimization; high diagnostic metrics were invalidated by seven violations.
- `case_0005`: sparse nadir-only fallback after access-model confusion; too few useful pairs and zero overlap.

The successful `case_0003` shows the required antidote: use the verifier not only to check syntax or hard validity, but to close the loop on product overlap, signed steering convention, and final hard-validity status.

## Implications

For interpreting the benchmark, DPSK should not be grouped with Kimi as "the same cross-track bug" without qualification. Cross-track handedness was a shared trap, but DPSK's failure pattern was broader: it was brittle under iterative optimization and timeout pressure.

For future workspace design, the README could make the signed local frame explicit, for example by stating `across_hat = along_hat x nadir_hat`. That would reduce one ambiguity. But DPSK's `case_0004` would still fail under a perfectly specified frame, because it knowingly finalized an invalid schedule. Better diagnostics should therefore emphasize both sides of the benchmark contract:

- a valid schedule with `coverage_ratio=0.0` is not a useful solution;
- an invalid schedule with high diagnostic product metrics is still a failed submission.

For case-study grouping, Kimi and DPSK probably belong near each other but not as one identical case. Kimi demonstrates a persistent signed-coordinate mismatch. DPSK demonstrates unstable verifier-grounded iteration: the same system could discover the right fix in one case, forget or bypass it in another, and finally accept either zero-product hard validity or invalid high-product quality.
